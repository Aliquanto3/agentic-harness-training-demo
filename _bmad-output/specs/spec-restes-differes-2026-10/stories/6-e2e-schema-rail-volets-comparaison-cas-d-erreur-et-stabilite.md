---
title: "E2E : schéma, rail, volets, comparaison, cas d'erreur et stabilité"
type: 'chore'
created: '2026-10-01'
status: 'draft'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/tools/e2e/README.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Le schéma (pose du robot, activité, bacs), le rail d'Orchestration, le redimensionnement des volets, la paire comparée par défaut et deux cas d'erreur (reranker, coût « ≈ ») n'ont aucun contrôle ; `gemini_shape` échoue une fois sur deux sur l'empreinte GreenOps, et le contrôle `aria-expanded` des actions forcées ne protège pas le correctif du lot K (CAP-5).

**Approach:** Contrôles E2E par le DOM, ou par `page.evaluate` sur les fonctions globales d'`app.js` (`robotPose`, `turnRows`, `syncLogGroups`, `moveBoundary`, `loadPaneLayout`) ; doublures d'erreur dans `tools/e2e` ; attente d'un état au lieu d'un délai pour `gemini_shape`.

## Boundaries & Constraints

**Always:**
- Entrées fermées (`closed: <date> (story 6 des restes différés) — <scénario, contrôle>`) :
  - **E020** — `robotPose()` change selon l'état du tour ; la clé de mémorisation de `renderSchema()` inclut la pose (le robot bouge entre deux rendus).
  - **E031** — rail d'Orchestration : lignes dépliées qui le restent, direct et vue figée, « Suivre le direct », repli du tour précédent, fusion des `model_delta` et compte du journal ; chaque `kind` du catalogue (`trace/catalog.py`) a son libellé dans `KIND_LABELS` et un résumé `eventSummary`.
  - **E032** — `schemaActivity` (halo, chemin, ✋ H5, ✖ blocage), `component` gardé sur les étapes `tool` et `hook`, bacs par `kind` et `hosting`, états « désactivé » et « ✖ a bloqué » de la bande des hooks ; et l'assertion pytest `tool_started.component == "tools.<nom>"` dans `tests/test_tools.py`.
  - **E033** — `moveBoundary` (bornes minimales, seuls les voisins changent, sens de la hauteur du schéma), `resetBoundary`, `loadPaneLayout` sur un stockage corrompu et cinq volets masqués, `savePaneLayout` à chaque masquage.
  - **E042** — paire comparée par défaut de « Comparer » (tour rejoué contre son origine).
  - **E094** — échec simulé du téléchargement du reranker (notice sous l'interrupteur) et étape « Reranking » en erreur dans le rail.
  - **E125** — `aria-expanded` lu juste après le clic, avant toute reconstruction du panneau ; la tranche passe aussi sous Edge (`channel="msedge"`) si Edge est installé, sinon le noter.
  - **E135** — faux fournisseur tarifé sans `usage` (sans `stream_usage`) : « ≈ » devant le coût sur la ligne de l'appel, l'en-tête du tour et la barre haute.
  - **E141** — `_footprint_line` attend que l'empreinte soit rendue dans le corps de l'étape « Appelle le modèle » (événement ou état du DOM), sans délai fixe ; `gemini_shape` passe cinq fois de suite dans sa tranche.
- Doublures d'erreur dans `tools/e2e/` (faux fournisseur, faux échec de téléchargement), jamais dans `src/`.
- Chaque contrôle échoue si l'on retire la ligne qu'il protège (constaté une fois à la main).

**Never:**
- Banc de test JS ou dépendance nouvelle.
- Allonger un délai pour faire passer `gemini_shape`.
- Changer le comportement de l'interface ; un défaut trouvé est noté dans `deferred` et `deferred-work.md`.

</intent-contract>

## Verification

**Commands:**
- `uv run ruff check tools/e2e tests/test_tools.py` -- expected: aucun écart.
- `uv run pytest -q tests/test_tools.py` -- expected: tout passe.
- E2E (avec l'accord d'Anaël) : tranches couvrant `native_tools`, `h5`, `replay`, `rag_rerank`, `gemini_shape` (cinq fois), `subagent` -- expected: 0 échec.
