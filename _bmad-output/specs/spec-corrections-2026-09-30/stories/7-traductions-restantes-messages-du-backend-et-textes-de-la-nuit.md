---
title: 'Traductions restantes : messages du backend et textes de la nuit'
type: 'feature'
created: '2026-10-01'
status: 'in-review'
baseline_revision: '27abdfd'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/stories/5-messages-produits-par-le-backend.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** En `en` et `de`, les messages du backend (`content/messages.yaml`) restent français : la story Langues 5 s'est arrêtée après son commit 3 (anglais 126 clés sur ~1 000, allemand 12). Les stories 1 à 6 de la nuit ont ajouté des clés, certaines sans traduction (CAP-7 de `SPEC.md`).

**Approach:** Terminer les commits 4 et 5 de la story Langues 5 et traduire tout texte des stories 1 à 6 manquant en `en` ou `de`, par un relevé mécanique puis deux sous-agents de traduction (un par langue ; l'allemand vouvoie l'utilisateur).

## Boundaries & Constraints

**Always:**
- Relevé mécanique (2026-10-01, sur `27abdfd`) : clés de chaque fichier de `content/` absentes de `content/i18n/{en,de}/`. Résultat : seul `messages.yaml` manque (882 clés en `en`, 997 en `de`), y compris les clés sœurs `compression.install`, `missing`, `unknown_version`, `wrong_version` relevées par la revue de la story 4, et `session.mcp.no_loop`, `session.llm_lab.back_to_idle` relevées par celle de la story 6 ; le glossaire du serveur MCP local a des clés traduites par conception.
- `content/i18n/{en,de}/messages.yaml` complets : mêmes clés, mêmes variables par clé, pluriels `.one`/`.other`, mêmes commentaires ; les valeurs déjà traduites sont gardées. Noms de boutons et de briques alignés sur `content/i18n/{lang}/ui.yaml` et `bricks/*.yaml`. Allemand : « Sie » pour l'utilisateur ; les messages lus par le modèle suivent le registre du prompt système traduit. Ordinaux de `rag_lab.rank.*` : `1st/2nd/3rd/4th` en anglais, `{n}.` en allemand.
- Parité stricte dans `tests/test_i18n.py` (mêmes clés, plus seulement un sous-ensemble).
- `common.language.help` (trois `ui.yaml`) ne dit plus que des messages restent en français.
- `tests/test_backend_messages.py` : tests paramétrés en `en` et `de` des lignes de la matrice de la story Langues 5 côté Python (erreur d'outil lue par le modèle, appel mal formé, refus H1 et H5, troncature, carte indisponible, diagnostic et catalogue, réglage contraire), sans valeur française du catalogue.
- Commit 5 de la story Langues 5 : tranche E2E `backend_language` et motifs `messages.yaml` dans `run_e2e.py` ; README, ARCHITECTURE-SPINE (AD-19), `i18n-conventions.md`, `deferred-work.md`.

**Never:**
- Changer un texte français, une clé, une variable, ou `fr.wikipedia.org`.
- Traduire les journaux, docstrings, commentaires de code, messages de validation de fichiers, ou le texte brut d'une exception tierce.
- Lancer l'E2E, un serveur ou un modèle local sans l'accord d'Anaël (règle de la session du 2026-10-01).

</intent-contract>

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q tests/test_i18n.py tests/test_backend_messages.py tests/test_ui_texts.py` -- expected: tout passe.
- E2E (avec accord) : `--only backend_language annex_language` -- expected: 0 échec.

## Auto Run Result

- **Changement** : `content/i18n/en/messages.yaml` et `content/i18n/de/messages.yaml` complets (1 020 clés chacun, mêmes clés, même ordre, mêmes variables ; deux sous-agents, un par langue) ; parité stricte dans `tests/test_i18n.py` ; `common.language.help` (fr, en, de) sans la mention « messages du harnais restent en français » ; cinq tests paramétrés `en`/`de` dans `tests/test_backend_messages.py` (erreur d'outil lue par le modèle, appel mal formé, troncature, refus H1, cartes ; chacun avec `settings.json` contraire) ; tranche E2E `backend_language` et motifs `messages.yaml` dans `_french_patterns` et `_annex_patterns`, exclusions des textes du backend retirées ; README, ARCHITECTURE-SPINE (AD-19), `i18n-conventions.md`, `deferred-work.md`, note de clôture de la story Langues 5.
- **Choix de traduction à relire** (rapports des sous-agents) : anglais britannique (-ise), « workstation » pour « poste » mais « computer RAM » dans `config.budget.*` (déjà employé par le diagnostic) ; allemand : « Sie » pour l'utilisateur, « du » pour le modèle (prompt système), y compris là où le français vouvoie le modèle (`calculator.unreadable`, `network.year`) ; « Télécharger » rendu par „{noun}-Modell herunterladen“ (pas de libellé court en `de`) ; fragments réécrits pour la déclinaison (`session.load.memory.the_provider`, `llm_lab.tokenizer.*`, `rag_lab.chunking.source_*`, `config.budget.calc.*`) ; rangs „{n}.“ un peu raides dans `rag_lab.rerank.climb` et `compare.move`.
- **Vérification** : `ruff check`, `ruff format --check` OK ; `pytest tests/test_i18n.py tests/test_backend_messages.py tests/test_ui_texts.py` : 3 295 passés. **Non lancé** (accord d'Anaël requis) : E2E `--only backend_language annex_language` (les tranches `ui_language` et `annex_language` deviennent plus strictes : elles ne mettent plus de côté les textes du backend).
- **Revue** : pas encore faite (story de contenu ; revue de suivi recommandée sur les choix ci-dessus et sur la tranche E2E jamais jouée).
