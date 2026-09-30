---
title: 'Langues (3/5) : contenus pédagogiques'
type: 'feature'
created: '2026-09-30'
status: 'in-progress'
baseline_commit: 'd7c87cfb77a75c458e29fbc7bb5f1db4229c8410'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-langues/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Langue réglée sur `en` ou `de`, l'écran principal est traduit (story 2), mais les cartes des briques, les consignes et les prompts suggérés des scénarios, les textes du cloud, de la compression, des types de segments et des éditeurs de modèles restent en français, et `read_file` lit les fichiers de démonstration français. Plusieurs chargeurs ne reçoivent pas la langue de la session et relisent `settings.json`, ou gardent l'ancien texte après un changement de langue.

**Approach:** CAP-2 de `SPEC.md`. D'abord faire suivre la langue de la session à chaque chargeur du périmètre et à `read_file`, sans rien traduire (français inchangé) ; puis écrire les surcouches `en` et `de` ; enfin une tranche E2E `content_language`.

## Boundaries & Constraints

**Always:**
- **Périmètre traduit**, sous `content/i18n/{en,de}/`, mêmes noms, mêmes `id`, validés par le modèle pydantic du français :
  - `bricks/*.yaml` (les 11) ; `scenarios.yaml` (titres des modules, `title_text`, `description_text`, `prompts`) ;
  - `cloud.yaml` (y compris `test.prompt`, `test.tool.description`) ; `compression.yaml` ; `labels/segment_kinds.yaml` ;
  - `models/publishers.yaml` (textes seulement : `id`, `architectures`, `names`, `names_first` identiques) ;
  - `demo_files/**` : contenu traduit, **noms de fichiers et de dossiers inchangés**, dont `confidentiel/` (H1 s'y fie, les préréglages de `tools.yaml` traduits les citent déjà).
- **La langue est un argument.** Chaque chargeur du périmètre prend `lang` et passe par `AppSession._localized` ; aucun ne relit `settings.json`. Ceux que la session garde (`_cloud_content`, `_labels`, le programme des scénarios) sont relus dans la nouvelle langue par `set_language`. `/api/diagnostic` passe la langue de la session aux éditeurs.
- **`read_file` lit dans la langue de la session**, fichier par fichier : la traduction si elle existe, sinon le français. Le confinement et la liste restent ceux du dossier français ; H1 refuse `confidentiel/` dans les trois langues.
- **Les consignes citent l'interface de leur langue.** Un libellé entre guillemets dans une consigne `en` ou `de` est celui du catalogue de cette langue (`ui.yaml`, `tools.yaml`, `subagent.yaml`, `mcp.yaml`, `skills.yaml`). Guillemets : “…” en `en`, „…“ en `de`.
- **Noms des briques** alignés sur les skills de la story 1 et sur `ui.yaml` de la story 2 :
  - `en` : Reasoning, Short-term memory, System prompt, Global memory, Tools, RAG, MCP, Skills, Hooks, Sub-agent, Compression ;
  - `de` : Denkprozess, Kurzzeitgedächtnis, System-Prompt, Globales Gedächtnis, Tools, RAG, MCP, Skills, Hooks, Sub-Agent, Kompression.
- Gabarits : mêmes variables (`{tools}`, `{servers}`, `{candidates}`, `{keep}`, `{tool}`, `{n}`, `{min_chars}`, et les clés françaises de `cloud.yaml` `{fournisseur}`… gardées telles quelles).
- **Fichiers de démonstration** : même structure ; les `.log` gardent le même nombre de lignes, les mêmes horodatages et le même format de ligne ; `guide_harnais.md` garde ses sections ; même longueur à peu près.
- Registre : l'allemand vouvoie. L'infobulle `common.language.help` (fr, en, de) ne dit plus que les briques et les scénarios restent en français : seulement les ateliers, les pages annexes et les messages du harnais.
- Exécution : `pytest` en quarts, E2E par tranches `--only`, au premier plan, une suite à la fois.

**Never:**
- Traduire les textes produits par le code Python (`price_reason_fr`, `_FALLBACK` « Autres éditeurs », messages de `read_file`, `harness_error`) : story 5. Ni le corpus RAG ni les pages annexes : story 4.
- Renommer un fichier de démonstration, un `id`, une clé de gabarit ou le dossier `confidentiel`.
- Changer un fichier français de `content/`, ou un test existant, sauf :
  - les assertions de la story 1 sur les contenus restés français (`test_i18n.py:178`) ;
  - les tests d'un chargeur dont la signature gagne `lang`.
- Rendre le faux fournisseur de l'E2E (`fake_openai.py`) sensible à l'anglais ou à l'allemand : la tranche force ses appels d'outils.
- Ajouter une dépendance ou traduire à l'exécution.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Scénario en allemand | `de`, lancer `native_tools` | Titre, consigne et prompts de `i18n/de/scenarios.yaml` ; aide de la brique Tools en allemand | — |
| Lecture traduite | `de`, `read_file("recette_crepes.txt")` | Le contenu de `i18n/de/demo_files/recette_crepes.txt` | — |
| Fichier non traduit | `en`, fichier absent sous `i18n/en/demo_files/` | Le fichier français | repli par fichier |
| Liste | `de`, `read_file(".")` | Les mêmes noms qu'en `fr` | — |
| Garde-fou | `de`, `read_file("confidentiel/budget_projet.txt")`, H1 actif | Refus de H1, comme en `fr` | — |
| Évasion | `en`, `read_file("../x")` | Refus, comme en `fr` | — |
| Changement de langue | `fr` → `en`, modèle cloud chargé | Bandeau cloud, libellés de la jauge et programme en anglais après rechargement | — |
| Traduction invalide | `i18n/de/scenarios.yaml` casse le schéma | `harness_error`, puis le programme français | repli `_localized` |
| Français inchangé | `fr` | Rendus, résultats d'outils et suite existante identiques | — |

</frozen-after-approval>

## Code Map

- **Résolution** : `config.localized_path` / `content_file` (`config.py:1061-1075`) ; `_localized` (`app_session.py:1552`) ; `_reload_texts` (:5262) ; `set_language` (:5219 : sauvegarde, `clear_content_caches`, `_reload_texts`, MCP local, `_emit_bricks`, `_load_scenarios` :5257).
- **Déjà localisés** (surcouche seule) : `load_brick_content` (`bricks/contract.py:60`, modèle `BrickContent` :43) ; `load_compression_content` (`compression/port.py:58`, validateur des gabarits).
- **À faire suivre** :
  - `load_scenarios(known)` (`scenarios.py:85`, `localized_path` sans langue :88) → `lang`, appelé par `_localized` dans `_load_scenarios` (:5323).
  - `load_cloud_content()` (`cloud.py:51`, `@cache`) → `lang` ; appels `app_session.py:2201`, `:7902`, `cloud.active_model` :153, `diagnostic.py:859`, `:995`. `_cloud_content` relu dans `_reload_texts`.
  - `load_labels()` (`context/segments.py:92`, `@cache`) → `lang` ; `_load_labels` (`app_session.py:2529`, appelé :2157, :2209) ; `_labels` relu au changement de langue.
  - `publishers_path()` / `load_publishers()` (`models/catalog.py:150`, :163) → `lang`, jusqu'à `publisher_for` :179, `group_models` :594, `models_payload` :615 ; route `web/app.py:426`, `_models` :469-474, `app_session._language`.
- **`read_file`** : `demo_dir` / `resolve_demo_path` / `read_file` (`tools/native.py:87-110`) ; `NATIVE_TOOLS` :113, enregistré :923 ; l'exécuteur appelle `spec.run(**arguments)` (`tools/executor.py:137`). Lier la langue comme les outils du harnais (`_harness_tools` :4341, `registry.replace` dans `_reload_texts` :5302). H1 : `hooks.py:23`, `CONFIDENTIAL` :38, `guard` :165-185 (comparer le chemin relatif au dossier de base).
- **Libellés que citent les consignes** : préréglages de `tools.yaml:35-52` (et `i18n/{en,de}/tools.yaml`), `subagent.yaml:19`, `mcp.yaml:7`, `ui.yaml` (`Forcer l'appel` :139, `Afficher les actions forcées` :145, `Rejouer le dernier prompt` :222, `Vider la conversation` :223), `skills.yaml` (« Compte rendu de réunion »).
- **Skills** : `content/i18n/{en,de}/skills/{budget_review,working_days}/SKILL.md:8` nomment la brique « Tools ».
- **Infobulle** : `common.language.help` (`content/ui.yaml:12`, `i18n/en/ui.yaml:6`, `i18n/de/ui.yaml:6`).
- **Tests** :
  - `tests/test_i18n.py` : `_translations()` :83, parité par fichier :112-168 (une branche par fichier, sinon échec :168), `LLM_DEFAULTS` :53, assertion `scenarios.yaml` français en `de` :178 ;
  - `test_program.py:216` (la consigne contient le libellé du préréglage) : modèle du test paramétré ;
  - `test_hooks.py:29-153`, `test_model_catalog.py`, `test_scenarios.py`, `test_cloud*.py` : suivre les signatures.
- **E2E** : `run_e2e.py` — registre `SCENARIOS` :7527 ; `_switch_language` :4931, `_pick_language` :4697 ; `Run.launch` :198, `Run.arm` :305, `Run.show_forced` :300 ; consigne `#scenario-guide-text`, prompts `#suggested-prompts button`, aide `.brick-help` → `#explain-{id}` ; `s_ui_language` :4943 comme modèle (captures, `finally` en `fr`).

## Tasks & Acceptance

**Execution:**
- [ ] Commit 1, la langue suit : `scenarios.py`, `cloud.py`, `context/segments.py`, `models/catalog.py`, `tools/native.py`, `hooks.py`, `app_session.py`, `web/app.py`, `session/diagnostic.py` -- `lang` explicite, `_localized`, relecture au changement de langue, `read_file` lié à la langue -- aucun texte ni fichier de `content/` ne change, suite verte.
- [ ] `tests/test_content_language.py` (nouveau) -- commit 1 puis 2 -- paramétré `fr`, `en`, `de` : chaque ligne de la matrice ; chaque chargeur du périmètre lit sa langue sans `settings.json` (réglage contraire au paramètre) ; `set_language` relit programme, cloud et libellés.
- [ ] Commit 2, traductions : `content/i18n/{en,de}/` -- les fichiers du périmètre -- écrits par deux sous-agents (un par langue), avec la liste des libellés à citer.
- [ ] `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- `common.language.help` -- commit 2.
- [ ] `tests/test_i18n.py` -- commit 2 -- une branche de parité par fichier : mêmes clés, mêmes `id`, champs non textuels identiques (`bricks`, `tools`, `duration_min`, motifs des éditeurs, `test.tool.name`, `tool_reply`), même nombre de prompts, un nom de fichier de démonstration cité en `fr` l'est aussi dans la traduction ; `demo_files` : même ensemble de fichiers, même nombre de lignes pour les `.log`. `cloud.yaml` rejoint `LLM_DEFAULTS`.
- [ ] `tests/test_content_language.py` -- commit 2 -- chaque libellé cité dans une consigne `en`/`de` existe dans un catalogue de sa langue ; le nom de brique cité par les skills égale `label_text` de `bricks/tools.yaml` de sa langue ; `test_program.py:216` rejoué en `en` et `de`.
- [ ] `tools/e2e/run_e2e.py` -- commit 3 -- tranche `content_language` : en `en` puis `de`, lancer `native_tools`, comparer titre, consigne, prompts et aide de la brique Tools aux valeurs de sa langue (et à aucune valeur française qui en diffère) ; forcer `read_file` sur un préréglage et lire le contenu traduit dans Orchestration ; H1 refuse `confidentiel/` en `de` ; captures `de` à 1 280 et 1 600 px, normal et projection ; `finally` : repos puis `fr`.
- [ ] `ARCHITECTURE-SPINE.md` (AD-19), `deferred-work.md` (fermer la part story 3 et le nom des briques des skills) -- commit 3.

**Acceptance Criteria:**
- Given la langue `fr`, when on joue ruff, pytest en quarts et l'E2E par tranches après chaque commit, then tout passe, et aucun fichier français de `content/` n'a changé.
- Given la langue `de`, when la tranche `content_language` joue, then la consigne, les prompts, l'aide de la brique et le fichier lu sont allemands, et aucune valeur française du périmètre n'est visible.
- Given une consigne `en` ou `de` qui cite un libellé, when le test des libellés joue, then ce libellé existe dans un catalogue de sa langue.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

- `read_file` résout comme `localized_path` mais fichier par fichier, sous `content/i18n/{lang}/demo_files/`. Le confinement se juge sur le chemin relatif demandé, par rapport au dossier français, puis la traduction le remplace s'il existe. H1 compare aussi le chemin relatif : `confidentiel/...` est refusé quelle que soit la racine résolue.
- Les `@cache` à langue gardent une entrée par langue ; `clear_content_caches` reste le seul vidage.
- La tranche E2E force `read_file` (préréglage) plutôt que de compter sur le faux fournisseur, qui ne reconnaît que les prompts français.

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` en quatre quarts des `tests/test_*.py` triés, au premier plan -- expected: tout vert
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only …` par tranches de 4 à 6, dont `content_language`, `ui_language`, `language` -- expected: 0 FAIL
- `git diff --stat d7c87cfb77a75c458e29fbc7bb5f1db4229c8410 -- content/ ':!content/i18n' ':!content/ui.yaml'` -- expected: vide
