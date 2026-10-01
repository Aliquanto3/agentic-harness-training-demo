---
title: 'Traductions restantes : messages du backend et textes de la nuit'
type: 'feature'
created: '2026-10-01'
status: 'done'
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
- **Vérification avec processus** (2026-10-01, accord d'Anaël) : E2E `backend_language` 16/16 (après un correctif : retour à l'atelier avant chaque langue), `ui_language` sans échec, `annex_language` 29/29 après deux correctifs : un `Said` (texte rendu qui garde son `Message`, ceux du diagnostic de démarrage) est rendu de nouveau dans la langue demandée par `in_language` ; l'E2E met de côté les seuls textes des événements émis avant le dernier changement de langue (historique du journal : étapes du dernier chargement, contrôles du diagnostic de démarrage). `content_language language` 34/34. Six tests des stories Langues 3 et 4 attendaient encore du français en `en`/`de` : attentes passées au catalogue de la langue.

## Review Triage Log

### 2026-10-01 — Follow-up review pass
- verdicts: 9 findings — high 0, medium 3, low 6, false 0, maybe-false 0
- findings:
  - `[medium]` `[patch]` `de` `models.openai_chat.another_address` inséré après « nach » (datif) : « nach eine andere Adresse » — « einer anderen Adresse ».
  - `[medium]` `[patch]` `rag/lab.py` : le libellé du refus de budget de l'atelier RAG figeait `noun_text` (un `Message`) en français par une f-string (« Not enough memory to load modèle d'embedding X ») — `Lazy` rendu dans la langue du message ; vérifié en `de` (« Embedding-Modell X »).
  - `[medium]` `[patch]` E2E : la mise de côté de l'historique portait sur tout texte émis avant le changement de langue, y compris une raison de carte ou un état restés français — limitée aux événements que les pages rejouent comme historique (`model_load_*`, `diagnostic_check`).
  - `[low]` `[patch]` `en` `models.openai_chat.hint.min_interval` : « today » pour « aujourd'hui » au sens de « actuellement » — « (currently {interval} s) ».
  - `[low]` `[patch]` `en` `diagnostic.starting` : « Startup diagnostic » — « Start-up diagnostics », comme `ui.yaml` et `session.state.diagnostic`.
  - `[low]` `[patch]` `de` `session.forgotten` : « Es wird verworfen. » ne s'accorde pas avec « der Kompressor » — « Die Instanz wird verworfen. ».
  - `[low]` `[reject]` `de` `session.compression.the_compressor` au nominatif dans un refus de budget (« um der Kompressor zu laden ») — chemin jamais pris : la fabrique Headroom donne toujours son `label_text` ; la corriger demanderait un second libellé.
    - Repris le 2026-10-01 (lot des restes, `spec-restes-2026-10-01.md`) : second libellé `session.compression.the_compressor_to_load` (fr, en, de ; « den Kompressor »), pris par `_load_compressor` pour le refus de budget, `the_compressor` gardé au nominatif pour le détail du schéma. Preuve : `tests/test_compression.py::test_budget_refusal_names_the_compressor_in_the_case_of_its_sentence` (échoue sur l'ancien code).
  - `[low]` `[patch]` `de` `session.hooks.failed.effect` : « Er lässt durch » sans complément — « Er lässt den Aufruf durch ».
  - `[low]` `[patch]` `de` `hooks.h2.towards` : « {tool} zu {destination} » — « {tool} an {destination} », comme H5.
- Trouvé ensuite par l'E2E `ui_language`, une fois la mise de côté de l'historique resserrée : la note GreenOps d'un appel (`greenops.not_estimated`, infobulle de l'empreinte) restait française en `en` et `de`, `Impact.fields()` étant appelé sans langue (appel local, `run_call` cloud et test du diagnostic) — `run_call` reçoit la langue de la session (`lang`), et les trois sites la passent. `ui_language` 28/28 ensuite.
- Vérifié sans défaut (relecteur) : les 1 020 clés relues, les fragments listés dans la spec assemblés dans leurs messages, le registre Sie/du, la typographie, les libellés cités ; le `Said` rendu de nouveau (terminal toujours en anglais, texte tiers inchangé).
- Revue de suivi : convergée (aucun `high`), `followup_review_recommended: false`. Vérifié : `pytest tests/test_rag_lab.py tests/test_i18n.py tests/test_ui_texts.py` 224 passés, `test_backend_messages` (hors rendu clé par clé) 61 passés ; E2E de langue rejoués.
