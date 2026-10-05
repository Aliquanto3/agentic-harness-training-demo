---
title: 'Lot 5b-1 : architectures toutes faites (RAG dense, RAG hybride, RAG + reranking)'
type: 'feature'
created: '2026-10-05'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'fb89e8abb9cd7666f13dc94d06e8882bbc23899b'
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
- [x] `rag/lab.py` + contenus -- préréglages déclarés et validés.
- [x] `rag.html`, `rag.js`, `rag.css` -- boutons, application, `aria-pressed`.
- [x] tests pytest et E2E.

**Acceptance Criteria:**
- Given « RAG hybride » appliqué, when on lance la chaîne, then la Fusion montre les rangs des deux recherches et le run se termine `ok`.
- Given un rechargement, when la page est prête, then la chaîne est gardée et « RAG hybride » reste pressé.

## Implementation Notes

- `Catalog.preset_pipeline(id)` : la chaîne livrée munie du segment du préréglage (ids renumérotés, réglages livrés), jugée par `check_pipeline` ; son refus devient `reason_text`.
- « Catalogue sans reranker » : l'option `("rerank", "declared")` absente ou `available: False` (pytest). Dans l'appli, des fichiers de reranker absents ne donnent qu'une `note_text` (`_rag_lab_catalog`, non modifié) : le préréglage reste disponible et l'étape est sautée au run ; l'E2E simule l'indisponibilité par `page.route`.
- La page compare la suite (kind, option) des étapes déplaçables au segment de chaque préréglage pour `aria-pressed` ; appliquer garde l'id d'une étape de même genre.
- Libellés fr du §8 de `vues-atelier-rag.md` (« RAG hybride (BM25 + dense) »).

## Spec Change Log

- 2026-10-05 : une seule chaîne (A/B retirée), libellés de la maquette v2 ; id gardé.

## Review Triage Log

Passe 1, 2026-10-05.

| # | Source | Constat | Verdict | Preuve | Suite |
| --- | --- | --- | --- | --- | --- |
| 1 | blind, edge, verif | disponibilité calculée sur la chaîne livrée : avec `top_k` > candidats livrés, un préréglage « disponible » donne un refus `too_few_candidates` | low | voulu par l'intention (« chaîne livrée munie du segment ») ; le refus s'affiche aussitôt sur la ligne, cas rare (top_k > 8) | rejeté, signalé à Anaël |
| 2 | blind, edge | reranker absent dans l'appli réelle : seulement `note_text`, « RAG + reranking » reste disponible, l'étape est sautée au run sans que le bouton le dise | low | `_rag_lab_catalog` ; la note est sur la ligne Reranking | patch (note des options du segment dans l'infobulle) |
| 3 | blind | l'E2E « indisponible » ne vérifie pas le refus sur la ligne | low | le refus vient de la session, couvert en pytest (`catalog sans reranker`) ; le rendu des refus est couvert par l'E2E BM25 | rejeté |
| 4 | blind | explication seulement en `title` (clavier, lecteur d'écran) | low | `renderPresets` | patch (`aria-describedby`) |
| 5 | blind | infobulle : explication et raison collées | low | `join(" ")` | patch |
| 6 | blind, edge | un préréglage écrase un segment composé ou des candidats réglés, sans annulation | low | comportement voulu (réglages livrés) ; « Revenir » existe | rejeté |
| 7 | blind | « RAG + reranking » et « Revenir à la chaîne livrée » semblent identiques | low | texte « C'est la chaîne livrée » | patch (texte) |
| 8 | blind | hybride + reranking non enseigné ; coût de l'hybride absent | low | textes `presets.*` | patch (texte) |
| 9 | blind | bouton pressé et indisponible : pas de règle ni de contraste vérifié | low | état atteint seulement par le faux catalogue de l'E2E | rejeté |
| 10 | blind | « ● » du bouton pressé lu par les lecteurs d'écran ; pas de survol | low | `::before` | patch (texte alternatif vide) ; survol rejeté |
| 11 | blind | réglages livrés calculés deux fois (`_presets`, `preset_pipeline`) | low | `lab.py:488,519` : deux sources pour le même segment | patch |
| 12 | blind | tests : indices en dur, langue de la raison non testée | low | — | rejeté |
| 13 | blind | commentaire anglais « default » au lieu de « shipped » | low | `en/rag_lab.yaml` | patch |
| 14 | verif | rien ne vérifie le retour des candidats aux valeurs livrées | medium | `_rag_lab_presets` ne règle aucun candidat | patch (E2E) |
| 15 | verif | rien ne vérifie que l'id d'une étape de même genre est gardé | medium | `chainRun()` dépend des ids | patch (E2E) |
| 16 | verif | retour du focus sur le bouton après redessin non vérifié | low | — | defer |
| 17 | edge | `unavailable_text` vide → « () » | false | champ requis par `RagLabContent` | rejeté |
| 18 | edge | `unroute` sans rechargement : catalogue truqué gardé pour la suite | low | `run_e2e.py` | patch (recharger) |
| 19 | edge | catalogue nul → AttributeError dans l'E2E | low | contenu valide dans l'E2E | rejeté |

## Verification

**Commands:**
- `uv run pytest tests/test_rag_lab.py tests/test_i18n.py -q` -- expected: vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab` -- expected: aucun FAIL
