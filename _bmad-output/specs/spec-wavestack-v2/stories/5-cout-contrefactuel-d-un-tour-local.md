---
title: "V2 (5/6) : coût contrefactuel d'un tour local"
type: 'feature'
created: '2026-10-01'
status: 'draft'
size: 'M'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/brownfield.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-estimateur-finops-api.md'
---

> Brouillon non déclenché. Indépendante des stories 1 à 4.

## Intent

**Problème :** Le FinOps de la V1 chiffre les appels cloud, et seulement eux. Un tour local n'affiche aucun coût, par choix. Or la gouvernance technique veut savoir ce que le même travail aurait coûté chez un fournisseur : c'est le premier argument du routage par coût (CAP-7).

**Approche :** CAP-5. Pour chaque tour local, on applique les tokens réels du tour aux prix de chaque modèle cloud déclaré avec `pricing`. Le résultat est un ordre de grandeur, marqué « ≈ », avec la date et la source du prix.

## Ce qui existe déjà (V1)

- `pricing = {input_usd_per_mtok, output_usd_per_mtok, checked}` par `[[cloud.models]]` (`wavestack.toml`, `CloudPricing`).
- `CallCost` et les totaux de `openai_chat.py`, `[finops] eur_per_usd`, et l'affichage du coût par appel et par tour (spec FinOps du 2026-09-29).

## Boundaries & Constraints

**Always :**
- Coût contrefactuel d'un appel local = `prompt_tokens` × prix d'entrée + `output_tokens` × prix de sortie, raisonnement compris, pour chaque modèle cloud déclaré avec `pricing`. Le coût du tour est la somme de ses appels (sous-agent compris).
- Toujours marqué « ≈ » : le tokenizer du fournisseur diffère, sa réponse aurait une autre longueur, et ni cache ni remise ne sont comptés. L'infobulle le dit.
- Le prix affiche sa date (`checked`) et sa source. `pricing` gagne un champ `source` (URL) facultatif ; sans lui, l'infobulle affiche « source non déclarée ».
- Calcul fait par la session (AD-1), sans aucun appel réseau.
- L'affichage reste distinct de la « Dépense API » : rien n'a été dépensé. Une ligne dans l'en-tête du tour d'Orchestration, le détail par modèle dans l'infobulle.
- Textes en trois langues ; montants au format de la langue (`common.format.usd`).

**Never :**
- Ajouter un contrefactuel à la dépense de la séance, ou un mot qui le présente comme une économie réalisée.
- Une grille de prix hors des déclarations `[[cloud.models]]`.
- Une comparaison d'énergie cloud du même tour (hors incrément 1).

## I/O & Edge-Case Matrix

| Cas | État | Attendu |
|---|---|---|
| Tour local, trois modèles cloud avec prix | Groq, Mistral, Gemini | Trois montants « ≈ », chacun avec sa date |
| Modèle cloud sans `pricing` | — | Absent de la liste |
| Aucun modèle cloud avec prix | — | Aucune ligne de contrefactuel |
| Tour cloud | Modèle cloud actif | Comportement V1 (coût réel), pas de contrefactuel |
| Tokens estimés | Serveur local sans comptage | « ≈ », comme le reste |

## Critères d'acceptation

- Un test par cas de la matrice, montants calculés en Python.
- Une tranche E2E montre la ligne dans l'en-tête d'un tour local, avec sa date et sa source.

## Vérification

- `ruff`, puis `pytest` en quarts.
- Tranche E2E `--only` du FinOps.
