---
title: "V2 (3/6) : diagnostic du bon extrait dans l'Atelier RAG"
type: 'feature'
created: '2026-10-01'
status: 'draft'
size: 'M'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/brownfield.md'
---

> Brouillon non déclenché. Dépend des stories 1 et 2.

## Intent

**Problème :** L'Atelier RAG compare deux chaînes en A/B, avec leurs extraits communs ou propres et leurs écarts de rang. Mais il ne dit pas laquelle sert la question, faute de savoir quel extrait est le bon. Son étape contexte compte des caractères, alors que le reste de WaveStack parle en tokens.

**Approche :** CAP-3. L'atelier accepte une question du jeu. Chaque étape qui produit des extraits montre le rang du bon extrait, ou son absence. L'étape découpage dit si l'ancre a été coupée. L'étape contexte compte des tokens. La synthèse A/B nomme la chaîne qui place le bon extrait le plus haut.

## Ce qui existe déjà (V1)

- `rag/lab.py` (`LabRun`, `Pipeline`, `Stage`) : découpage, embedding, base vectorielle, recherche vectorielle, BM25, fusion RRF, reranking, contexte ; A/B et sa synthèse ; `content/rag_lab.yaml`.
- Le repérage du bon extrait et les verdicts de la story 2.

## Boundaries & Constraints

**Always :**
- Le bon extrait se repère par l'ancre (story 2), y compris quand l'atelier change la taille des extraits.
- Les tokens de l'étape contexte viennent du tokenizer du modèle actif. Sans modèle local, c'est une estimation marquée « ≈ », comme en mode chat (CAP-31).
- La génération reste dessinée, jamais exécutée (CAP-45).
- Textes en trois langues, dans `rag_lab.yaml` et `ui.yaml`.

**Never :**
- Un classement des chaînes par score agrégé sur tout le jeu de questions : une question à la fois.
- Une écriture dans le dépôt.

## I/O & Edge-Case Matrix

| Cas | Entrée | Attendu |
|---|---|---|
| A sans reranking, B avec | Une question au cas `demoted_by_rerank` | Rang par étape dans chaque colonne ; la synthèse nomme A |
| Extraits de 200 caractères | Ancre de 250 caractères | Découpage : « ancre coupée », verdict `not_indexed` |
| Aucune question choisie | Texte libre | Comportement V1, sans diagnostic |
| Aucun modèle local | Modèle cloud actif | Tokens du contexte marqués « ≈ » |

## Critères d'acceptation

- Un test par cas de la matrice.
- Une tranche E2E sur une comparaison A/B qui montre le rang du bon extrait dans les deux colonnes et la synthèse.

## Vérification

- `ruff`, puis `pytest` en quarts.
- Tranche E2E `--only` de l'Atelier RAG.
