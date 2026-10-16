---
title: 'Menu des modèles 🏠 local / ☁️ cloud (story 5)'
type: 'feature'
created: '2026-10-16'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '46052c9'
---

## Intent

**Problem:** CAP-5 (SPEC.md de `spec-wavestack-v1-1-vague-1`) : dans le menu des
modèles de l'atelier, les modèles locaux et cloud ne se distinguent que par le
texte (« Local · » / « RÉSEAU · »), peu lisible d'un coup d'œil (douleur
constatée par le testeur, voir SPEC.md > Why).

**Approach:** Chaque `<option>` de modèle du sélecteur (`#model-picker`) reçoit
l'emoji de son hébergement (🏠 local, ☁️ cloud) en tête de son texte, et chaque
`<optgroup>` qui le contient reçoit une classe CSS selon l'hébergement du
groupe, stylée avec un fond distinct (jetons existants, contrastés en thème
clair et sombre). Les options qui ne sont ni locales ni cloud (« Ajouter
d'autres modèles… », « Autre fichier… », légende, « Tableau des modèles… »)
restent hors de tout `optgroup` coloré et sans emoji.

## Boundaries & Constraints

**Always:**
- L'emoji et la classe de fond viennent de `m.hosting` / `group.hosting`
  (`"local"` ou `"network"`), déjà fournis par la session (`catalog.py`) ;
  aucune nouvelle donnée côté backend.
- Les deux chemins de rendu du sélecteur (`rebuildModelPicker`, le groupement
  par hébergement/éditeur de la story 25 ; `rebuildModelPickerByKind`, le repli
  historique) reçoivent le même traitement.
- Les couleurs viennent de `tokens.css` déjà déclarés dans les deux thèmes
  (`--color-discipline-context-soft` pour local, `--color-discipline-network-soft`
  pour cloud), sans nouveau jeton ni modification de `DESIGN.md`.

**Never:** ne pas toucher `panes.js`, `mcp.*`, `rag.*` (story 3, en parallèle)
ni le README/docs (story 2) ; pas d'emoji sur « Ajouter d'autres modèles… » ni
« Autre fichier… » (ni locales ni cloud, CAP-5 et contraintes de la story).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Modèle local (fichier, serveur) | `rebuildModelPicker`/`ByKind`, `hosting === "local"` | Option préfixée « 🏠 », dans un `optgroup.model-optgroup-local` | N/A |
| Modèle cloud | `hosting === "network"` | Option préfixée « ☁️ », dans un `optgroup.model-optgroup-network` | N/A |
| « Ajouter d'autres modèles… », « Autre fichier… », légende, table | Options hors `optgroup` de modèles | Aucun emoji, fond par défaut du sélecteur | N/A |
| Thème sombre | `data-theme="dark"` ou `prefers-color-scheme: dark` | Fonds des deux groupes toujours lisibles (jetons déjà adaptés par thème) | N/A |

## Code Map

- `src/wavestack/web/static/app.js` -- `hostingEmoji`, `hostingGroupClass`
  (nouvelles fonctions) ; `rebuildModelPicker` (optgroup par `group.hosting`,
  emoji par `m.hosting`) ; `rebuildModelPickerByKind` (même traitement sur les
  optgroups « local »/« network » construits à la main).
- `src/wavestack/web/static/app.css` -- `.model-optgroup-local`,
  `.model-optgroup-network` : fond et couleur de texte, jetons existants.
- `tools/e2e/run_e2e.py` -- libellés exacts du sélecteur utilisés par
  `_pick_model`/`select_option`/`startswith` : `A_LABEL`, les `a_label`/
  `b_label` locaux, `GEMINI_LABEL`, `PRICED_LABEL`, `LLAMA_OPTION`,
  `OLLAMA_OPTION`, les littéraux inline (reasoning, Anthropic) et l'assertion
  `startswith(("Local · ", "RÉSEAU · "))` de `s_model_catalog`, tous préfixés
  de l'emoji attendu.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/web/static/app.js` -- emoji + classe d'optgroup dans les
  deux fonctions de rendu du sélecteur
- [x] `src/wavestack/web/static/app.css` -- fonds des deux groupes, thème clair
  et sombre
- [x] `tools/e2e/run_e2e.py` -- libellés et assertions du sélecteur adaptés

**Acceptance Criteria:**
- Given le sélecteur de modèles ouvert avec au moins un modèle local et un
  cloud, when il se construit, then chaque option de modèle commence par 🏠 ou
  ☁️ selon son hébergement, et son `optgroup` porte un fond différent de
  l'autre groupe, dans Edge en thème clair et sombre.
- Given les options « Ajouter d'autres modèles… » et « Autre fichier… »,
  when le sélecteur se construit, then elles ne portent aucun emoji
  d'hébergement et restent hors de tout `optgroup` coloré.

## Implementation Notes

- Couleurs choisies parmi les jetons déjà déclarés dans `tokens.css` (clair et
  sombre) pour éviter toute dérive détectée par `tests/test_web_tokens.py` :
  pas de nouveau jeton, pas de changement de `DESIGN.md`.
- `rebuildModelPickerByKind` est le repli historique (avant l'API de groupes
  de la story 25) ; traité par souci de cohérence CAP-5, mais peu probable
  d'être exercé par l'E2E en pratique (la session renvoie toujours `groups`).
- E2E non lancé (consigne de l'orchestrateur) : scénarios `s_model_switch` et
  `s_model_catalog` adaptés par relecture du code (grep des libellés exacts du
  sélecteur dans tout `run_e2e.py`, pas seulement ces deux scénarios, puisque
  les constantes de libellé sont partagées par de nombreux autres scénarios :
  `s_reasoning_locked`, `s_native_anthropic`, `s_gemini_shape`,
  `s_priced_estimate`, `s_local_server`, etc. — tous adaptés en même temps
  qu'eux pour rester cohérents), à vérifier à l'intégration.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `python .claude/cost-kit/controle_rapide.py` -- aucune erreur
- `uv run pytest -q --tb=short tests/test_web_app.py tests/test_web_tokens.py tests/test_model_switch.py tests/test_model_catalog.py` -- tous les tests passent
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only model_switch,model_catalog` -- attendu : vert (laissé à l'orchestrateur)

**Manual checks (if no CLI):**
- Lancer WaveStack, ouvrir le sélecteur de modèles : les options locales
  portent 🏠, les options cloud portent ☁️, et les deux groupes ont des fonds
  visuellement distincts, en thème clair et en thème sombre.

## Revue

## Non vérifié

- E2E non lancé dans cette story (consigne) ; les libellés ont été adaptés par
  relecture seule, sans ouverture réelle du sélecteur dans Edge.
