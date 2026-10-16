---
id: SPEC-corrections-2026-10-16-barre-six-onglets
status: review
companions: []
sources:
  - ../spec-wavestack-v1-1-vague-2/SPEC.md
  - ../spec-wavestack-v1-1-vague-2/ux/DESIGN.md
---

> **Canonical contract.** This SPEC is the complete contract for this correctif.

# Correctif : la barre commune attend six onglets depuis la page Sécurité

## Why

Depuis la story 10 (#61, page Sécurité), la barre commune compte six onglets (`/ /llm /rag /mcp /security /diagnostic`) au lieu de cinq. L'E2E final sur `main` fait échouer 38 vérifications, toutes liées à la barre (`_bar_fits`, `_site_nav_problems` de `tools/e2e/run_e2e.py`) : elles comparaient encore l'ordre des liens à la liste à cinq onglets d'avant la story 10.

## Diagnostic

`_site_nav_problems` (ligne ~3036 de `tools/e2e/run_e2e.py`) compare l'ordre des liens de `nav.site-nav` à la chaîne littérale `'/ / /llm /rag /mcp /diagnostic'`. Le HTML des six pages a déjà `/security` entre `/mcp` et `/diagnostic` (story 10) ; seule l'attente du test est périmée. Un libellé de vérification (« barre commune entière avec cinq onglets ») portait aussi l'ancien compte.

Aucun débordement réel : rejoué après correction, `_bar_fits` passe sur les six onglets plus les boutons Dépense/Journal, aux trois largeurs testées (1600×1000, 1440×900, 1280×720), en mode normal et en projection (scénarios `llm_screen`, `rag_lab`, `bar_panels`, `mcp_lab_page`, `local_server`, `gemini_shape`, `priced_estimate`). Aucune modification CSS n'était nécessaire.

## Fix

- `tools/e2e/run_e2e.py` : la chaîne attendue des liens de `_SITE_NAV_PROBLEMS_JS` passe à `'/ / /llm /rag /mcp /security /diagnostic'` ; le libellé de la vérification MCP passe de « cinq onglets » à « six onglets » ; le commentaire au-dessus de `_SITE_NAV_PROBLEMS_JS` est mis à jour.

## Validation

- `uv run pytest -q --tb=short tests/test_web_app.py tests/test_ui_texts.py` : 69 passés.
- E2E (`--channel msedge`, `PYTHONUTF8=1`) :
  - `--only mcp_lab_page bar_panels llm_screen rag_lab` : toutes les vérifications de barre passent (les 6 échecs restants de `rag_lab`, sur le téléchargement des modèles d'embedding et le déroulé du run, sont préexistants et hors périmètre de ce correctif).
  - `--only local_server gemini_shape priced_estimate` : 92+ vérifications passées, aucune liée à la barre en échec.

## Non-goals

- Pas de changement de mise en page (CSS, `bar.js`, `site-nav`) : la barre tenait déjà sur une ligne aux tailles testées.
- Les 6 échecs non liés à la barre dans `rag_lab` (compte des modèles à télécharger, déroulé du run Generation) restent ouverts, hors périmètre : ils ne touchent ni la navigation ni les boutons Dépense/Journal.
