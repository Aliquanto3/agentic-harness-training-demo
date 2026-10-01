---
title: 'V2 (2/6) : diagnostic du bon extrait dans la vue harnais'
type: 'feature'
created: '2026-10-01'
status: 'draft'
size: 'L'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/brownfield.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
---

> Brouillon non déclenché. Dépend de la story 1.

## Intent

**Problème :** La vue harnais montre déjà les extraits retrouvés : leur score, leur rang avant et après reranking, leur place dans le contexte et leurs tokens. Mais elle ne sait pas lequel est le bon. Quand le SLM répond mal, la salle ne peut pas dire si l'erreur vient de la recherche, du reranking, de la coupe, ou du modèle lui-même.

**Approche :** CAP-2. Pour un tour qui porte un `question_id` (story 1), le harnais repère le bon extrait, puis calcule où il en est à chaque étape **avant la génération** :
- son rang dans tout l'index ;
- son rang parmi les candidats, puis après reranking ;
- s'il est gardé ou coupé ;
- sa position et ses tokens dans le contexte.

Il en tire un verdict, l'étape fautive, qu'il émet comme un événement et que l'interface affiche dans Orchestration et dans Contexte LLM.

## Ce qui existe déjà (V1)

- `RagSearchEndedPayload` et `RagRerankEndedPayload` (`trace/catalog.py`) : position, `chunk_id`, `doc_id`, score, rang d'avant, `keep`, `placement_text`.
- Les segments typés et leurs tokens (`context/segments.py`), la jauge et `ContextWindowPayload`.
- `SqliteVecRetriever` (`top_k = 3`) et le reranker (`rerank_candidates = 8`).

## Boundaries & Constraints

**Always :**
- **Bon extrait** : le ou les extraits de l'index de la langue dont le texte contient `anchor_text` dans le document `doc_id`.
- **Rang dans tout l'index** : recherche exhaustive sur le petit index, faite seulement pour le diagnostic et tracée comme telle. Elle ne change jamais le contexte.
- **Verdicts**, un seul par tour, le premier qui s'applique dans l'ordre de la chaîne :
  - `not_indexed` : l'ancre n'est dans aucun extrait (index périmé ou découpage) ;
  - `not_retrieved` : hors des candidats renvoyés ;
  - `demoted_by_rerank` : parmi les candidats, mais écarté par le reranking ;
  - `cut` : retrouvé, mais au-delà de ce qui entre dans le contexte ;
  - `in_context` : dans le contexte, avec sa position (rang parmi les extraits, tokens avant et après lui, part de la fenêtre).
- Un nouvel événement au catalogue (AD-2), émis après la recherche et le reranking, avant `model_call_started`. Il est rejouable par le rejeu (AD-17).
- Tous les textes passent par `messages.yaml` et `ui.yaml`, en trois langues.
- Le volet Contexte LLM marque le bon extrait (« bon extrait ») quand il est dans le contexte. Le verdict est attribué au harnais.

**Never :**
- Lire, noter ou comparer la réponse du modèle.
- Changer ce qui entre dans le contexte selon le diagnostic.
- Afficher un diagnostic pour un tour sans `question_id`.

## I/O & Edge-Case Matrix

| Cas | État | Verdict attendu |
|---|---|---|
| Bon extrait au rang 1, sans reranking | `top_k = 3` | `in_context`, rang 1 |
| Rang 5 sans reranking | `top_k = 3` | `cut`, rang 5 dans l'index |
| Rang 6 avant reranking, rang 1 après | Reranking actif | `in_context`, avec l'avant et l'après |
| Rang 2 avant reranking, rang 6 après | `keep = 3` | `demoted_by_rerank` |
| Rang 12 dans l'index | 8 candidats | `not_retrieved` |
| Ancre coupée entre deux extraits | — | `not_indexed`, avec la raison « découpage » |
| Compression active sur l'extrait | Brique compression | `in_context`, avec les tokens d'avant et d'après compression |
| Index d'une autre langue ou périmé | — | Brique indisponible (V1) : pas de diagnostic, et la raison est dite |

## Critères d'acceptation

- Les huit cas de la matrice ont un test, avec le moteur, l'embedder et le reranker factices.
- Une tranche E2E montre le verdict dans Orchestration et le marquage dans Contexte LLM, en `fr` et en `de`.
- Le contexte envoyé au modèle est identique, octet pour octet, avec et sans `question_id` (test).

## Vérification

- `ruff`, puis `pytest` en quarts, au premier plan.
- Tranches E2E `--only` du RAG et de la langue.
