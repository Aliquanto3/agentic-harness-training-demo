---
title: 'Langues (5/5) : messages produits par le backend'
type: 'feature'
created: '2026-09-30'
status: 'in-progress'
baseline_commit: 'd1c98b17b2577dca4801061ddec044fd6f005209'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-langues/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** En `en` ou `de`, l'interface et les contenus sont traduits (stories 2 à 4), mais environ 770 textes écrits en dur dans le Python restent français : environ 700 vus par l'utilisateur (`harness_error`, raisons de disponibilité, diagnostic, catalogue des modèles, étapes des ateliers, détails HTTP) et environ 70 lus par le LLM (erreurs d'outils, troncature, refus H1 et H5, mémoire, délégation, jour de `get_datetime`, glossaire du serveur MCP local).

**Approach:** CAP-5 de `SPEC.md`. Un catalogue `content/messages.yaml` (surcouches `en`, `de`) et `msg(key, lang, **kw)` remplacent ces littéraux, la langue de la session étant passée explicitement. Cinq commits :
1. Mécanisme, parité, et les trois reprises de la story 1 (`harness_error` de `_localized`, jour de `get_datetime`, « Terme inconnu du glossaire »).
2. Messages lus par le LLM.
3. Messages vus par l'utilisateur (peut se couper en 3a session et web, 3b modèles, diagnostic, ateliers et le reste).
4. Traductions `en` et `de`, tests paramétrés.
5. Tranche E2E `backend_language` et documentation.

## Boundaries & Constraints

**Always:**
- **Catalogue.**
  - `content/messages.yaml` : sections par domaine (`tools`, `hooks`, `memory`, `delegation`, `mcp`, `session`, `availability`, `diagnostic`, `models`, `catalog`, `rag_lab`, `llm_lab`, `greenops`, `web`, `context`…), clés `snake_case` en anglais, variables `{name}`, pluriels `.one` et `.other`.
  - La valeur française est le littéral actuel, octet pour octet : la suite existante passe sans changer une assertion.
  - Les surcouches ont les mêmes clés et le même jeu de variables par clé. Une clé absente d'une traduction prend le français.
- **`msg(key, lang, **kw)`** dans `src/wavestack/messages.py` :
  - `lang` est obligatoire, jamais lu dans `settings.json` ; la session passe `self._language`.
  - Un fichier traduit invalide donne le français. La session le trace une fois par `_localized(load_messages)` au démarrage et à chaque changement de langue.
  - Une clé inconnue ou une variable manquante lève une exception : c'est une erreur de programmation, attrapée par les tests.
  - Les caches sont vidés par `config.clear_content_caches`.
- **Langue jusqu'aux sites d'appel**, explicitement :
  - `ToolExecutor` reçoit un accesseur de langue ;
  - les outils natifs et réseau sont reliés à la langue comme `read_file` (`_native_tools`, `network_tools`) ;
  - H1 et H5 lisent `HookContext`, le serveur MCP local sa langue d'argument ;
  - les exceptions levées loin de la session (`ServerError`, `DownloadError`, `ProviderError`, `ToolError`, `StageFailed`…) portent une clé et ses variables. `str()` rend le français ; la session rend la langue au moment de placer le texte dans un événement, l'état ou le contexte.
- **Périmètre** : tout texte qui finit dans un champ `*_text` d'événement, d'état ou de réponse d'API, un `detail` HTTP, un contrôle du diagnostic, une étape d'atelier, ou le contexte envoyé au modèle. Cela inclut les causes littérales françaises des `harness_error` et les lignes d'audit H2.
- **Terminal** (décision d'Anaël, 2026-09-30) : la sortie en terminal (`cli.py`, dont `wavestack diagnostic` et les `harness_error` imprimés, et `scripts/build_rag_index.py`) passe par le même catalogue, toujours en anglais (`msg(key, "en")`), sans lire `settings.json`. `--lang` du script reste la langue de l'index. Les tests qui lisent cette sortie passent à l'anglais.
- **Infobulle** : `common.language.help` (en `fr`, `en` et `de`) ne dit plus que des messages restent en français.
- **Exécution** : `pytest` en quarts et l'E2E par tranches `--only`, au premier plan, une suite à la fois. Traductions par deux sous-agents, un par langue, qui reçoivent la table des libellés `ui.yaml` déjà traduits et les noms de briques traduits.

**Never:**
- Traduire les journaux (`log.*`), les docstrings, les commentaires, les messages de validation des fichiers YAML ou le texte brut d'une exception tierce placé en `cause`.
- Changer un texte français, une clé d'événement, un nom de champ, ou `fr.wikipedia.org` (retenu par la story 3).
- Relire la langue dans `settings.json`.
- Changer un test existant, sauf un test d'une fonction dont la signature gagne `lang`, les tests de la sortie en terminal (passés à l'anglais) et les exclusions « messages du Python » de `run_e2e.py`.
- Ajouter une dépendance, ou traduire à l'exécution.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Erreur d'outil lue par le modèle | `de`, `read_file` sur un fichier absent | Le résultat d'outil envoyé est allemand, préfixe d'erreur compris ; aucune valeur de `messages.yaml` française | — |
| Appel mal formé | `en`, argument inconnu | « Error: … Fix the call or answer without a tool. » | `reject` |
| Refus H1 et H5 | `de`, fichier confidentiel ; appel réseau refusé | Refus allemands dans le contexte | — |
| Troncature | `en`, résultat trop long | Marque anglaise ; le calcul de la borne tient compte de sa longueur | — |
| `get_datetime` | `de` | « Mittwoch 2026-09-30T… » | — |
| Glossaire | `en`, terme inconnu | Message anglais du serveur MCP local | — |
| Fichier traduit invalide | `i18n/de/ui.yaml` cassé | `harness_error` allemand, puis le français du fichier | `_localized` |
| `messages.yaml` traduit invalide | `i18n/en/messages.yaml` cassé | Un `harness_error` (en français, le catalogue anglais étant illisible), puis les messages français | repli |
| Carte indisponible | `de`, brique requise inactive | Raison allemande | — |
| Diagnostic et catalogue | `en`, `/diagnostic`, `/models` | Contrôles, actions, statuts et sources de fenêtre en anglais | — |
| Réglage contraire | session `de`, `settings.json` en `fr` | Messages allemands | — |
| Français | `fr` | Textes identiques à la base | — |

</frozen-after-approval>

## Code Map

- **Modèle** : `ui_texts.py` (`_check` L22, `_filled` L36, `load_ui_texts` L63) : à factoriser avec `messages.py`, pas à dupliquer. `config.content_file` L1078, `clear_content_caches` L1082. `AppSession._localized` L1553 (message à reprendre L1566-1569, repris aussi à `diagnostic.py:872` et `catalog.py:179`), `_error` L1546, `_language` L776, `set_language` L5249.
- **LLM** :
  - `tools/executor.py` (`_TYPES_FR` L26, `check` L59-83, `reject` L95, `run` L153 et L171), construit une fois à `app_session.py:926` ; `tools/parser.py` L73-117.
  - `tools/native.py` (`_WEEKDAYS_FR` L13 et `get_datetime` L16-18, aussi importé par `hooks.py:22` ; calculatrice L36-78 ; `read_file` L118-126). Précédent de liaison : `_native_tools` `app_session.py:4356-4364`.
  - `tools/network.py` (L42-52, L106-147, `network_tools(cfg)` construit à `app_session.py:923`) ; `mcp/connection.py` (`describe_error` L43-69, L197-202) ; `mcp/local_server.py` L53-55 (`LANGUAGE` L23).
  - `hooks.py` : H1 L182, H5 L300 ; `HookContext` L129 (`content.language` L105) ; `_WEEKDAYS` L55 (en et de, à réutiliser pour `get_datetime`) ; H2 L226-249 ; `_APPROVAL_FR`, `_MONTHS_FR`.
  - `app_session.py` : `_TRUNCATED_FR` L447, `_bound_result` L6504-6536 ; refus H5 L6477 ; `_run_tool` L6455 ; mémoire `_remember` L4848-4873, `_apply_memory` L4897-4905, `memory.py` `check_text` L36-42 ; méta-outils L4819-4839 ; délégation L4445, L4550-4561, `_SubOutcome` L4614-4734, `_NO_SUB_TEXT_FR` L211 ; actions forcées L4285-4302.
- **Utilisateur** :
  - `app_session.py` : environ 25 constantes `_*_FR` (`_TURN_FR` L242, `_PREFIX_CAUSES_FR` L276, `_OVERFLOW_CAUSES_FR` L362, `_LIMITS_FR` L425, `_SAMPLING_NAMES_FR` L7693…), 61 appels à `_error`, `_availability` L3356, `_language_locked_reason` L270, `reason_text` L810, `SendRefused` et `LoadRefused`.
  - `session/diagnostic.py` (environ 60, `self.language` accesseur L159, `SEARCHED_SOURCES_FR` L62) ; `models/catalog.py` (`_WINDOW_SOURCE_FR` L400, légende L140, L466, L589 ; `lang` déjà présent) ; `models/capabilities.py` (`REASONING_FR` L109, statuts L143-177) ; `openai_chat.py` (environ 35, `ProviderError.payload`) ; `servers.py` (environ 30) ; `load_registry.py` L178-255 ; `download.py`, `probe.py`, `reranker.py`, `embedding.py`, `engine.py:320`.
  - `rag/lab.py` (environ 110 : validation L352-447, étapes L1271…, `StageFailed` L1358 et L1489, raisons L656 ; `LabDeps.lang` L920) ; `session/llm_lab.py` (`_DIMENSION_NAMES_FR` L30, `_join_fr`, L300).
  - Terminal, en anglais : `cli.py` (sortie du diagnostic, `harness_error` imprimés ; tests `test_cli_diagnostic.py`, environ 14 lignes) et `scripts/build_rag_index.py` (environ 20 textes, L39, L91, L113).
  - `web/app.py` (`detail` L241-262, L612-760) ; `config.py` (`calc_fr` L458-479, L589, L726, L755, L796) ; `greenops.py` (`_WARNINGS_FR` L38, L117-190) ; `context/render.py` L338 et L390 ; `context/window.py` L190-225 ; `rag/index.py` `INDEX_IN_USE_FR` ; `compression/headroom_adapter.py` `_INSTALL_FR` ; `tools/registry.py` L135.
- **Tests existants** qui figent le français (environ 250 lignes : `test_model_switch`, `test_rag_review`, `test_model_servers`, `test_tools`, `test_hooks`, `test_global_memory`, `test_subagent`…) : ils restent tels quels. `_localized` est vérifié en `de` à `test_content_language.py:362`, `test_i18n.py:496` et `test_ui_texts.py:290` : la reprise change le texte attendu, et c'est la seule exception prévue.
- **E2E** (`tools/e2e/run_e2e.py`) : `_backend_strings` L4872, `_french_left` L4910, `_french_patterns` L4855, `_annex_backend` L5375, `_annex_french_left` L5395, `_annex_patterns`, `s_annex_language` L5526, `SCENARIOS` L7994. Les motifs ne couvrent que les YAML : il faut y ajouter `messages.yaml` et retirer l'exclusion des textes du Python.

## Tasks & Acceptance

**Execution:**
- [ ] Commit 1 : `src/wavestack/messages.py`, `content/messages.yaml` (sections `session`, `tools.datetime`, `mcp.glossary`), `config.clear_content_caches`, `_localized`, `native.get_datetime`, `local_server.py`, `ui_texts.py` (partage de `_check` et `_filled`). Traductions `en` et `de` de ces trois clés dans le même commit, puisqu'elles sont l'objet des reprises.
- [ ] `tests/test_backend_messages.py` (nouveau), commits 1 à 4 :
  - chaque clé rendue en `fr`, `en` et `de` avec des variables fictives : non vide, sans `{` restant ;
  - chaque ligne de la matrice côté Python, session `de` ou `en` et `settings.json` contraire ;
  - un contrôle statique : dans les modules du périmètre, aucun littéral avec un caractère propre au français (accent, « ») hors docstrings, `log.*` et une liste d'exceptions justifiées.
- [ ] Commit 2 : les fichiers « LLM » du Code Map ; `ToolExecutor(registry, language)` ; le contrôle statique couvre ces modules.
- [ ] Commit 3 : les fichiers « Utilisateur » du Code Map ; le contrôle statique couvre tout le périmètre.
- [ ] Commit 4 : `content/i18n/{en,de}/messages.yaml` complets (deux sous-agents) ; `tests/test_i18n.py` : branche de parité de `messages.yaml` (mêmes clés, mêmes variables) ; `common.language.help` dans les trois `ui.yaml`.
- [ ] Commit 5 : `tools/e2e/run_e2e.py` :
  - motifs de `messages.yaml` ajoutés à `_french_patterns` et `_annex_patterns`, exclusions `_backend_strings` et `_annex_backend` retirées ;
  - tranche `backend_language`, en `en` puis `de` : erreur d'outil lue par le modèle (corps de `r.fake_calls()` sans valeur française de `messages.yaml`), carte indisponible, diagnostic, catalogue des modèles, captures `de` à 1 280 et 1 600 px en mode normal et projection sur l'écran principal, `finally` en `fr`.
- [ ] Commit 5 : `README.md`, `ARCHITECTURE-SPINE.md` (AD-19), `i18n-conventions.md` si le détail change, `deferred-work.md` (fermer les entrées « messages du Python »).

**Acceptance Criteria:**
- Given la langue `fr`, when on joue ruff, pytest en quarts et l'E2E par tranches après chaque commit, then tout passe et aucune assertion existante n'a changé hors des trois de `_localized` et de la sortie en terminal.
- Given n'importe quel réglage de langue, when on lance `wavestack diagnostic` ou `build_rag_index.py`, then la sortie est en anglais.
- Given la langue `de`, when les tranches `ui_language`, `content_language`, `annex_language` et `backend_language` jouent sans exclusion des textes du Python, then aucune valeur française des catalogues du périmètre n'est visible ni envoyée au modèle.

## Implementation Notes

**2026-09-30 — arrêt après le commit 3 (demande de l'utilisateur).**
- Faits et commités sur `feat/i18n-5` : commit 1 (`b92efc6`, mécanisme et reprises de la story 1), commit 2 (`e526742`, messages lus par le LLM), commit 3 (`6555fa5`, messages vus par l'utilisateur, terminal en anglais). `ruff` et `pytest` (en huitièmes) verts après chaque commit ; l'E2E n'a pas été rejoué.
- Mécanisme : `msg`, `Message` (un `str` dont la valeur est le français, rendu par `render(lang)`), `KeyedError`, `Lazy` (nombres et tailles dans la langue du rendu), `Said` et `in_language` dans `messages.py`. La session rend les `Message` des charges qu'elle émet (`_journal()`), le web ceux des réponses (`shown`) ; les moteurs servis ont un attribut `language` que la session met à jour.
- Tests existants modifiés : les trois assertions de `_localized` (commit 1), la branche de parité de `test_i18n.py` (`messages.yaml` comparé clé à clé, sous-ensemble tant que les traductions ne sont pas complètes), les 4 assertions de la sortie terminal de `build_rag_index.py` (`test_rag_review.py`).
- Traductions partielles déjà présentes : `content/i18n/en/messages.yaml` a 126 clés sur 1002 (`common`, `session.translation_invalid`, `tools.datetime`, `mcp.glossary`, et pour la sortie terminal `diagnostic`, `cli`, `rag`, `build_rag_index`) ; `content/i18n/de/messages.yaml` a 12 clés (les reprises du commit 1 et `common`). Les autres clés prennent le français.
- Reste à faire :
  - commit 4 : `content/i18n/{en,de}/messages.yaml` complets (deux sous-agents, un par langue, dont `common.units`, `config.budget.*` utilisés par le terminal), parité stricte dans `test_i18n.py` (mêmes clés), `common.language.help` dans les trois `ui.yaml`, tests paramétrés de la matrice en `en`/`de` (erreur d'outil lue par le modèle, appel mal formé, refus H1/H5, troncature, carte indisponible, diagnostic et catalogue, réglage contraire) dans `test_backend_messages.py` ; les ordinaux allemands de `rag_lab.rank.*` (« {n}. »).
  - commit 5 : tranche E2E `backend_language` et motifs `messages.yaml` dans `run_e2e.py` ; `README.md`, `ARCHITECTURE-SPINE.md` (AD-19), `i18n-conventions.md`, `deferred-work.md`.
- Risques connus : une raison de sonde stockée en français (`probe`, `settings.json`) n'est retraduite que si elle correspond exactement à un texte connu (`discovery.reason_message`) ; quand un `publishers.yaml` traduit et le français sont invalides, l'erreur reste française.

## Spec Change Log

## Review Triage Log

## Design Notes

- Exceptions à clé : `ToolError("tools.native.file_missing", path=…, files=…)` garde un `str()` français (journaux, tests existants). La session appelle `exc.render(lang)` là où le texte entre dans un événement ou le contexte. Les modules loin de la session n'ont ainsi pas besoin de connaître la langue.
- Pluriels côté Python : `count` choisit `.one` (`fr` : 0 ou 1 ; `en`, `de` : 1) ou `.other`, sans dépendance.
- Le `harness_error` d'un `messages.yaml` traduit invalide reste en français : c'est le seul catalogue sûr à ce moment-là.

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` en quatre quarts des `tests/test_*.py` triés, au premier plan -- expected: tout vert
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only …` par tranches de 4 à 6, dont `backend_language`, `annex_language`, `content_language`, `ui_language`, `tools`, `hooks`, `diagnostic` -- expected: 0 FAIL
- `git diff d1c98b17b2577dca4801061ddec044fd6f005209 -- tests/ ':!tests/test_backend_messages.py' ':!tests/test_i18n.py'` -- expected: seulement les trois assertions de `_localized`, des signatures gagnant `lang` et la sortie en terminal passée à l'anglais
