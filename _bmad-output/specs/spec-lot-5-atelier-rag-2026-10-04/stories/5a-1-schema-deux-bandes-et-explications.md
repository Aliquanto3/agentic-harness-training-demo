---
title: 'Lot 5a-1 : trois vues (séquence, architecture, focus), mode Composer, noms anglais, sans A/B'
type: 'feature'
created: '2026-10-05'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '370bb36d762c23e5f4af66168316104f5d738ecc'
context:
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/vues-atelier-rag.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La section 1 de `/rag` aligne sept cartes en une ligne, explications en texte ; on n'y voit ni les deux temps d'un RAG (build, run), ni les composants qu'il sollicite ; le vocabulaire mêle français et anglais ; la comparaison A/B encombre une page dont Anaël n'en a pas besoin.

**Approach:** Remplacer les sections 1 à 3 par une section unique : barre (question, Lancer, mode), puis trois vues côte à côte (séquence BUILD/RUN, architecture en groupes, focus d'une étape), le détail de toutes les étapes replié dessous (`vues-atelier-rag.md`, maquette v2 validée). En mode Composer, l'éditeur d'aujourd'hui vit dans les lignes de la séquence. Noms techniques en anglais ; comparaison A/B retirée de la page.

## Boundaries & Constraints

**Always:** la table étape → composants et les textes viennent de la session (`STEPS` de `rag/lab.py`, `content/rag_lab.yaml` fr/en/de validés) ; sélecteurs E2E de l'éditeur gardés (SPEC.md) ; couleurs par tokens, pas d'opacité ; tient dans 1 600 × 1 000.

**Never:** modifier `diagram.js` (import seulement), `app_session.py`, les fichiers carrefour hors ajouts RAG, DESIGN.md/EXPERIENCE.md ; changer le backend du run (pipelines, `compare()`) ; glisser-déposer.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Chaîne livrée, Composer | 7 étapes | séquence de 10 lignes (4 BUILD, 6 RUN), tuiles : Documents, Chunks, Vector store, Embedding model, Reranker, LLM, Question, Augmented prompt, Réponse | N/A |
| Sans reranking | segment = Dense retrieval | pas de tuile Reranker | N/A |
| Clic sur une ligne | Composer | focus : nom, action, explication, composants sollicités ; flèches vers les tuiles | N/A |
| Chaîne refusée | BM25 sans fusion | refus sur la ligne BM25, Lancer grisé | refus de la session |
| Chaîne B en localStorage | ancienne page | seule A est gardée | pas d'erreur |
| Contenu invalide | `rag_lab.yaml` sans `steps` | page servie, erreur affichée | `RagLabContent` refuse |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `STEPS` (clé, phase, étape de la chaîne, usages) près de `KINDS` ; `RagLabContent` : `steps`, `components`, `groups`, `phases`, textes de page nouveaux, champs A/B retirés ; `Catalog.payload()` rend `steps`, `components`, `groups`, `phases`.
- `content/rag_lab.yaml` + `content/i18n/{en,de}/rag_lab.yaml` -- noms anglais, textes nouveaux.
- `src/wavestack/web/static/rag.html` -- section unique, `#rag-views` (`#rag-seq`, `#rag-arch`, `#rag-focus`), `#rag-details`.
- `src/wavestack/web/static/rag.js` -- `renderChains` → `renderViews` ; éditeur dans les lignes ; A/B retirée ; flèches par `wireLayer`.
- `src/wavestack/web/static/rag.css` -- règles `rag-seq-*`, `rag-arch-*`, `rag-focus-*`, `rag-phase-*`, `rag-modes`.
- `tests/test_rag_lab.py`, `tests/test_i18n.py` -- contenu, payload, traductions.
- `tools/e2e/run_e2e.py` -- `_rag_lab`, `_rag_lab_compare` (→ une voie), `_rag_lab_alt`, `_rag_lab_hybrid`, `RAG_LAB_STAGES`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/rag/lab.py` -- STEPS, contenu validé, payload -- AD-1.
- [x] contenus fr/en/de -- vocabulaire et textes.
- [x] `rag.html`, `rag.js`, `rag.css` -- trois vues, Composer, A/B retirée.
- [x] tests pytest et E2E.

**Acceptance Criteria:**
- Given `/rag` en Composer, when la page est prête, then les trois vues sont côte à côte, sans défilement horizontal, et chaque ligne de la séquence ouvre son focus au clic.
- Given les E2E RAG, when ils jouent, then ils passent.

## Implementation Notes

- `rag/lab.py` : `PHASES`, `GROUPS`, `COMPONENTS` (groupe, icône, étape dont l'option donne le sous-titre), `STEPS` (`SequenceStep` : phase, étape de la chaîne, `own`, lu/écrit/appelé). `RagLabContent` valide `steps`, `components`, `groups`, `phases` et les textes de page nouveaux ; champs A/B et `results_title_text` retirés. `Catalog.payload()` rend `steps` (explication à défaut celle de l'étape), `components`, `groups`, `phases`.
- `stages.*.label_text` en anglais dans les trois langues (les refus de la session les citent : « BM25 », « Fusion (RRF) »…). En allemand, l'étape et la tuile `question` disent « Frage » : « Question » est aussi le mot français du catalogue, signalé par le balayage E2E des pages annexes.
- `rag.js` : `renderChains` → `renderViews` (séquence, architecture, focus, flèches par `wireLayer`, `light` en Dérouler) ; éditeur dans les lignes (Composer) ; mode mémorisé (`wavestack.ragLab.mode`, défaut Dérouler) ; une seule chaîne, une chaîne B enregistrée est ignorée. Les raisons d'indisponibilité d'une option ne s'affichent que sur la ligne sélectionnée (séquence compacte).
- Dérouler, dans cette story : toutes les étapes visibles, pastilles d'état et focus avec les chiffres du dernier run ; l'apparition progressive, le pas-à-pas et « Lancer passe en Dérouler » restent à 5a-2.
- E2E : `_rag_lab` (trois vues, focus de chaque ligne, flèches, Dérouler), `_rag_lab_compare` sur une voie (et relecture d'une chaîne A + B enregistrée), `_rag_lab_alt` FAISS sur la voie A, `_rag_lab_hybrid` avec les noms anglais. Capture `57-atelier-rag-comparaison` remplacée par `57-atelier-rag-composer`.

## Spec Change Log

- 2026-10-05 : réécrite après la maquette v2 (retours d'Anaël) ; remplace le schéma à deux bandes de la v1. Id gardé.

## Review Triage Log

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest tests/test_rag_lab.py tests/test_i18n.py tests/test_annex_language.py -q` -- expected: vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab` -- expected: aucun FAIL
