---
title: 'Lot 5b-1 : architectures toutes faites (RAG dense, RAG hybride, RAG + reranking)'
type: 'feature'
created: '2026-10-05'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/vues-atelier-rag.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Composer un RAG hybride ou retirer le reranking demande plusieurs gestes et des refus intermédiaires ; les architectures connues ne sont pas nommées.

**Approach:** Trois préréglages déclarés en Python (`dense`, `hybrid`, `rerank`), rendus par `Catalog.payload()["presets"]` avec textes et disponibilité, offerts en mode Composer par une rangée de boutons qui remplace le segment de récupération (`vues-atelier-rag.md` §8).

## Boundaries & Constraints

**Always:** seul le segment change ; réglages aux valeurs livrées ; disponibilité par `check_pipeline` sur la chaîne livrée munie du segment ; textes fr/en/de validés (exactement les ids de `PRESETS`) ; `aria-pressed` sur le préréglage courant ; validation de la session après application.

**Never:** endpoint nouveau ; `app_session.py` modifié ; préréglage « hybride + reranking ».

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Hybride | chaîne livrée | segment = Dense retrieval, BM25, Fusion (RRF) ; reste inchangé ; « RAG hybride » pressé ; run ok | N/A |
| Réglages édités | 300 caractères, top_k 2 | gardés | N/A |
| Reranker absent | catalogue sans reranker | « RAG + reranking » marqué indisponible, cliquable, refus sur la ligne | N/A |
| Hors préréglage | segment composé à la main | aucun bouton pressé | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `PRESETS`, `RagLabContent.presets`, `Catalog.payload()["presets"]`.
- contenus fr/en/de -- `presets.*`.
- `rag.html`, `rag.js`, `rag.css` -- `#rag-presets`.
- `tests/test_rag_lab.py`, `tests/test_i18n.py`, `tools/e2e/run_e2e.py` (`_rag_lab_presets`).

## Tasks & Acceptance

**Execution:**
- [ ] `rag/lab.py` + contenus -- préréglages déclarés et validés.
- [ ] `rag.html`, `rag.js`, `rag.css` -- boutons, application, `aria-pressed`.
- [ ] tests pytest et E2E.

**Acceptance Criteria:**
- Given « RAG hybride » appliqué, when on lance la chaîne, then la Fusion montre les rangs des deux recherches et le run se termine `ok`.
- Given un rechargement, when la page est prête, then la chaîne est gardée et « RAG hybride » reste pressé.

## Implementation Notes

## Spec Change Log

- 2026-10-05 : une seule chaîne (A/B retirée), libellés de la maquette v2 ; id gardé.

## Review Triage Log

## Verification

**Commands:**
- `uv run pytest tests/test_rag_lab.py tests/test_i18n.py -q` -- expected: vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab` -- expected: aucun FAIL
