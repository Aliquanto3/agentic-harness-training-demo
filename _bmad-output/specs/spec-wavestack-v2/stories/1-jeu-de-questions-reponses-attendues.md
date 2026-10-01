---
title: 'V2 (1/6) : jeu de questions de démonstration avec réponses attendues'
type: 'feature'
created: '2026-10-01'
status: 'draft'
size: 'M'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/brownfield.md'
---

> Brouillon non déclenché. À reprendre en spec d'implémentation (bmad-build) une fois les conditions 1 et 2 de « Déclenchement » remplies.

## Intent

**Problème :** Pour montrer où naît l'erreur d'un RAG sans juger la réponse du SLM, il faut savoir d'avance quel extrait est le bon. WaveStack ne connaît aucune réponse attendue. Seul le banc `tools/bench/story12_bench.py` a 10 requêtes françaises, chacune avec un document attendu, et ce banc ne sert pas à l'interface.

**Approche :** CAP-1. Un fichier de contenu porte le jeu. Pour chaque question : sa réponse attendue, son document et une ancre textuelle du bon passage. Un chargeur validé lit ce fichier, en français avec les surcouches `en` et `de`. Dans l'interface, choisir une question la place dans la saisie, et le tour garde son identifiant pour le diagnostic (stories 2 et 3).

## Ce qui existe déjà (V1)

- Le corpus (`content/corpus/*.md`) et sa traduction ; `content/rag.yaml` (les `id` des documents).
- `config.content_file(rel, lang)`, `clear_content_caches()`, et le test de parité `tests/test_i18n.py`.
- Les 10 requêtes du banc de la story 12, réutilisables comme première matière.

## Boundaries & Constraints

**Always :**
- Pour chaque question : `id`, `question_text`, `expected_answer_text`, `doc_id` (un `id` de `rag.yaml`), `anchor_text` (une phrase tirée telle quelle du bon passage), `failure_case` (le cas d'échec visé, ou `control` pour une question qui doit réussir), et `trainer_note_text` (facultatif).
- Le modèle pydantic est `extra = "forbid"`. Un fichier invalide émet `harness_error`, sans plantage (AD-19).
- Un test vérifie, pour chaque langue, que `anchor_text` figure dans le document `doc_id` de cette langue.
- Les surcouches `en` et `de` gardent les mêmes `id`, `doc_id` et `failure_case`. Seuls les textes changent ; l'ancre est la phrase traduite du corpus traduit.
- La sélection d'une question part avec l'intention d'envoi du message (`question_id`). Si le texte est modifié avant l'envoi, l'identifiant tombe.
- Entre 6 et 12 questions (hypothèse de SPEC.md), relues par Anaël avant traduction.

**Never :**
- Afficher une métrique agrégée (rappel, MRR) ou un score de la réponse du modèle.
- Changer le corpus pour faire réussir une question. Un document ajouté relève de la story 4.
- Comparer automatiquement la réponse du modèle à `expected_answer_text`.

## I/O & Edge-Case Matrix

| Cas | Entrée ou état | Attendu |
|---|---|---|
| Question choisie | Brique RAG active, question `q3` | La saisie reçoit `question_text`, l'envoi porte `question_id = q3`. |
| Texte modifié | `q3` choisie puis éditée | Envoi sans `question_id`, donc sans diagnostic. |
| Ancre absente | `anchor_text` introuvable dans le document de la langue | Le test échoue. À l'exécution, la question est écartée avec `harness_error`. |
| Langue sans surcouche | Pas de fichier `de` | Les questions françaises, comme tout contenu non traduit. |
| Brique RAG inactive | Question choisie | La question s'envoie ; aucun diagnostic n'est possible, et l'interface le dit. |

## Critères d'acceptation

- Le chargeur rend le jeu dans les trois langues, avec repli par fichier, et vide son cache par `clear_content_caches()`.
- Le fichier figure dans les listes de `tests/test_i18n.py` : mêmes clés, mêmes identifiants.
- Choisir une question dans l'interface remplit la saisie, et l'intention d'envoi porte son identifiant (test web et tranche E2E).

## Vérification

- `uv run ruff check . ; uv run ruff format --check .`
- `uv run pytest -q`, en quarts, au premier plan.
- Une tranche E2E `--only` sur la sélection d'une question.
