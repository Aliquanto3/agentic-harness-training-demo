---
title: 'Lot 5a-2 : mode Dérouler, apparition progressive, pas-à-pas et exécution en direct'
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

**Problem:** Tout le schéma est visible d'emblée ; pendant un run, rien ne montre quelle étape travaille ni quels composants elle sollicite, et l'exécution ne se rejoue pas.

**Approach:** Le mode Dérouler fait arriver les étapes et les composants un à un, par un pas-à-pas (`createStepper`) : visite guidée sans run, ou au fil des événements `rag_lab_*` d'un run réel ; l'étape montrée allume ses composants et ses flèches, le focus montre ses chiffres (`vues-atelier-rag.md` §5, §6).

## Boundaries & Constraints

**Always:** AD-1 ; une image par étape de la séquence ; positions stables (étapes et tuiles invisibles gardent leur place) ; `prefers-reduced-motion` respecté ; reconstruction identique depuis `last_run` ; Lancer passe en Dérouler.

**Never:** événement backend nouveau ; `app_session.py` ou `diagram.js` modifiés.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Visite guidée | Dérouler, aucun run | image 1 : Documents seule, tuile Documents ; ▶ : Chunking + tuile Chunks | ◀ grisé à l'image 1 |
| Run en cours | `stage_started` rerank | images jusqu'à Reranking, Reranking et Reranker + Question allumés, flèches animées, « en cours · n / total » | N/A |
| Fin de run | `run_ended` ok | dernière image Generation « non exécutée », légende « rejouez avec ◀ ▶ » | N/A |
| Étape en erreur | `stage_ended` error | pastille ✖, focus avec l'erreur ; étapes suivantes « sautée » | N/A |
| Run sans fin | session `idle` sans `run_ended` | `closeStaleRun` : run en erreur | existant |
| Rechargement | `last_run` | même état, direct sur la dernière image | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/rag.js` -- `applyEnvelope` : étapes atteintes → `stepper.push` ; `renderViews(frameIndex)` ; focus avec le `stage_ended` de l'étape.
- `src/wavestack/web/static/rag.css` -- `is-hidden`, `is-new`, pastilles d'état.
- `tools/e2e/run_e2e.py` -- `_rag_lab_views`.

## Tasks & Acceptance

**Execution:**
- [x] `rag.js` -- images, apparition progressive, flèches, focus du run -- CAP-3.
- [x] `rag.css` -- états.
- [x] `tools/e2e/run_e2e.py` -- `_rag_lab_views` (visite, run, ◀ ▶, rechargement).

**Acceptance Criteria:**
- Given Dérouler sans run, when on clique ▶ trois fois, then quatre étapes BUILD sont visibles et la tuile Vector store apparaît à la quatrième.
- Given un run terminé, when on clique ◀, then l'étape précédente est montrée, les suivantes masquées.

## Implementation Notes

- Images = clés d'étape ; `syncFrames()` pousse les étapes atteintes (une étape de la chaîne avec un événement `rag_lab_stage_*`) ; Documents, Question et l'Embedding de la question arrivent avec l'étape suivante qui leur est propre.
- Un run n'est montré en Dérouler que s'il a exécuté la chaîne éditée (étapes, options, réglages) ; sinon visite guidée de la chaîne éditée.
- Fin de run : atterrissage sur la première étape en erreur ou arrêtée (sinon la dernière image) ; même règle à la reconstruction depuis `last_run` (rejouée sans rendu intermédiaire).
- Textes nouveaux : `legend_{tour,live,done,replay}_text` (fr, en, de, `RagLabContent`). Hôte du pas-à-pas ajouté dans `rag.html` (`#rag-stepper`, `#rag-legend`).
- E2E : `_rag_lab_run(..., compose=True)` revient en Composer après un run (Lancer passe en Dérouler) ; l'étape en erreur est testée avec le reranker en panne (`[reranker-en-panne]`, erreur douce).

## Spec Change Log

- 2026-10-05 : réécrite après la maquette v2 ; id gardé.

## Review Triage Log

Relecture commune de 5a-1 et 5a-2 (un seul diff, un seul commit « lot 5a »), passe 1, 2026-10-05.

| # | Source | Constat | Verdict | Preuve | Suite |
| --- | --- | --- | --- | --- | --- |
| 1 | blind | « extrait », « contexte » restent dans `params.*` de `rag_lab.yaml` (fr/en/de) | medium | `rag_lab.yaml:183-190` ; Anaël a demandé la cohérence du vocabulaire | patch |
| 1b | blind | idem dans les refus de la session et `rag_lab.noun` | medium | `messages.yaml` est un fichier carrefour (ajouts seulement) | defer |
| 2 | blind | le validateur n'exige `explain_text` que si `stage is None` : Documents et Embedding (question) retombent sur l'explication de leur étape | low | `lab.py:305` | patch |
| 3 | blind | noms d'étape recopiés des noms de stage sans contrôle | medium | 7 copies × 3 langues, aucun test | patch (assertion de test) |
| 4 | blind | traces A/B : clés `rag.*` d'ui.yaml, `compare()` | false | conservées par contrainte (SPEC.md) ; commentaire de rag.css seul à corriger | patch (commentaire) |
| 5 | blind, edge | `#rag-focus` en `aria-live` reconstruit à chaque `stage_progress` | medium | `rag.html:100`, `renderRun` par enveloppe | patch |
| 6 | blind | les deux listes ont le même `aria-label`, émojis des puces lus, groupe des modes nommé « Vue » | low | `rag.html:74,89,91`, `modes_label_text: "Vue"` | patch |
| 7 | blind | en Composer après un run, le focus dit « Lancez la chaîne » | low | `shownRun()` nul hors Dérouler | patch (texte de Composer) |
| 7b | blind | le détail replié montre l'ancien run après édition | low | résumé du run nommé, usage rare | rejeté |
| 8 | blind, edge | « Lancer » passe en Dérouler avant l'acceptation ; un 409 laisse l'utilisateur hors de Composer | medium | `runChain` | patch |
| 9 | blind | « Suivre le direct » visible pendant la visite guidée | low | bouton du pas-à-pas toujours affiché | patch |
| 10 | blind | `chain_help_text` dit « à droite le focus », faux sous 1 300 px (1 280 visé) | low | `rag_lab.yaml:16` | patch |
| 10b | blind, edge | pas de palier sous ~760 px | low | cible PC 1 280-1 600 et projection | rejeté |
| 11 | blind | pédagogie : bandeau RUN « Retrieval » couvre aussi A et G ; Dense retrieval ne lit pas le vecteur de la question ; Reranking ne lit pas les candidats | low | table du §4 de vues-atelier-rag.md | rejeté (corrigerait la spec), signalé à Anaël |
| 12 | blind | « A RAG in two times », « Ein RAG in zwei Zeiten » | low | calques de « en deux temps » | patch |
| 12b | blind | « Frage », « Réponse » traduits | false | mots courants, règle du §2 | rejeté |
| 13 | verif | la persistance du mode n'est pas vérifiée | medium | aucune recharge en Composer vérifiée | patch (E2E) |
| 14 | verif | Dérouler qui abandonne un run après édition non vérifié | medium | seule la visite avant tout run est vérifiée | patch (E2E) |
| 15 | verif | focus de Documents, Question, Embedding (question) après run non vérifié | medium | seul `vector_search` lu | patch (E2E) |
| 16 | verif | raison FAISS/LanceDB visible une fois la ligne choisie non vérifiée | low | branche sans extra seulement | defer |
| 17 | edge | run sans étape atteinte : tout masqué | low | le premier stage émet toujours un événement | rejeté |
| 18 | edge | légende « rejouez » avec zéro image | low | même cas que 17 | rejeté |
| 19 | edge | refus sur une ligne masquée en Dérouler, raison invisible | low | `renderRefusals` | patch |
| 20 | edge | Entrée sur une ligne en Dérouler : le focus clavier tombe sur `body` | medium | lignes reconstruites | patch |
| 21 | edge | `closeStaleRun` : run en échec atterrit sur « terminée » | low | arrêt brutal seulement | rejeté |
| 22 | edge | deux étapes du même type en localStorage : lignes en double | low | la session refuse (« une seule fois ») | rejeté |
| 23 | edge | clés orphelines d'ui.yaml | low | contrainte carrefour | defer (Notes de fusion) |
| 24 | edge | « côte à côte » à 1 280 | false | §9 : focus dessous sous 1 300 px, voulu | rejeté |

## Verification

**Commands:**
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab` -- expected: aucun FAIL
