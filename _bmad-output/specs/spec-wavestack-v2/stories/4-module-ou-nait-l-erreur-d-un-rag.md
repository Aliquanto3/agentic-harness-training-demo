---
title: "V2 (4/6) : module « Où naît l'erreur d'un RAG »"
type: 'feature'
created: '2026-10-01'
status: 'draft'
size: 'S à M'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/brownfield.md'
---

> Brouillon non déclenché. Dépend des stories 1 à 3.

## Intent

**Problème :** Les stories 1 à 3 donnent l'instrument, mais pas la démonstration. Un formateur a besoin de cas d'échec qui se lancent en un clic et qui tombent chacun à une étape différente.

**Approche :** CAP-4. Un module V2 dans le programme. Ses scénarios jouent au moins trois cas d'échec et une question témoin qui réussit. Chaque scénario rattache ses prompts suggérés à des questions du jeu.

## Ce qui existe déjà (V1)

- `content/scenarios.yaml` et `scenarios.py` : `program` (modules), `transverse`, champs `bricks`, `rag_rerank`, `prompts`. Un scénario s'ajoute sans code.
- Le scénario RAG du palier 2 (UJ-5) et ses prompts.

## Boundaries & Constraints

**Always :**
- Au moins trois cas, à trois étapes différentes. Par exemple :
  - `not_retrieved` : la question emploie un autre vocabulaire que le document ;
  - `demoted_by_rerank` ;
  - `cut` : le bon extrait est quatrième sans reranking.
- Une question témoin `in_context`.
- Les cas se trouvent avec les vrais modèles d'embedding et de reranking de `wavestack.toml`, sur le PC cible, dans les trois langues. Un cas qui ne tient que dans une langue est signalé dans `trainer_note_text`.
- Si le corpus V1 ne donne pas trois cas, on ajoute un document de démonstration. Il doit être non confidentiel, traduit en `en` et en `de`, et l'index de chaque langue est reconstruit.
- Les scénarios du module n'activent que ce que la démonstration demande (RAG, avec ou sans reranking, et la mémoire courte au plus), pour que le contexte reste lisible.
- Le rattachement prompt → question passe par une donnée du scénario. Si le schéma doit gagner un champ, c'est un champ facultatif, validé par pydantic.

**Never :**
- Un cas qui repose sur la réponse du modèle.
- Changer le comportement des scénarios V1.

## Critères d'acceptation

- Les scénarios se valident (`tests/test_scenarios.py`), avec leurs traductions (`tests/test_i18n.py`).
- Un relevé manuel sur le PC cible confirme, pour chaque cas et chaque langue, le verdict attendu. Il est consigné dans la story.

## Vérification

- `ruff`, puis `pytest` en quarts.
- Tranche E2E `--only` des scénarios.
- Passage manuel d'Anaël sur le PC cible.
