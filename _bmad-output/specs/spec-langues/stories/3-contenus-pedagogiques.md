---
title: 'Langues (3/5) : contenus pédagogiques'
type: 'feature'
created: '2026-09-30'
status: 'done'
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
- [x] Commit 1, la langue suit : `scenarios.py`, `cloud.py`, `context/segments.py`, `models/catalog.py`, `tools/native.py`, `hooks.py`, `app_session.py`, `web/app.py`, `session/diagnostic.py` -- `lang` explicite, `_localized`, relecture au changement de langue, `read_file` lié à la langue -- aucun texte ni fichier de `content/` ne change, suite verte.
- [x] `tests/test_content_language.py` (nouveau) -- commit 1 puis 2 -- paramétré `fr`, `en`, `de` : chaque ligne de la matrice ; chaque chargeur du périmètre lit sa langue sans `settings.json` (réglage contraire au paramètre) ; `set_language` relit programme, cloud et libellés.
- [x] Commit 2, traductions : `content/i18n/{en,de}/` -- les fichiers du périmètre -- écrits par deux sous-agents (un par langue), avec la liste des libellés à citer.
- [x] `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- `common.language.help` -- commit 2.
- [x] `tests/test_i18n.py` -- commit 2 -- une branche de parité par fichier : mêmes clés, mêmes `id`, champs non textuels identiques (`bricks`, `tools`, `duration_min`, motifs des éditeurs, `test.tool.name`, `tool_reply`), même nombre de prompts, un nom de fichier de démonstration cité en `fr` l'est aussi dans la traduction ; `demo_files` : même ensemble de fichiers, même nombre de lignes pour les `.log`. `cloud.yaml` rejoint `LLM_DEFAULTS`.
- [x] `tests/test_content_language.py` -- commit 2 -- chaque libellé cité dans une consigne `en`/`de` existe dans un catalogue de sa langue ; le nom de brique cité par les skills égale `label_text` de `bricks/tools.yaml` de sa langue ; `test_program.py:216` rejoué en `en` et `de`.
- [x] `tools/e2e/run_e2e.py` -- commit 3 -- tranche `content_language` : en `en` puis `de`, lancer `native_tools`, comparer titre, consigne, prompts et aide de la brique Tools aux valeurs de sa langue (et à aucune valeur française qui en diffère) ; forcer `read_file` sur un préréglage et lire le contenu traduit dans Orchestration ; H1 refuse `confidentiel/` en `de` ; captures `de` à 1 280 et 1 600 px, normal et projection ; `finally` : repos puis `fr`.
- [x] `ARCHITECTURE-SPINE.md` (AD-19), `deferred-work.md` (fermer la part story 3 et le nom des briques des skills) -- commit 3.

**Acceptance Criteria:**
- Given la langue `fr`, when on joue ruff, pytest en quarts et l'E2E par tranches après chaque commit, then tout passe, et aucun fichier français de `content/` n'a changé.
- Given la langue `de`, when la tranche `content_language` joue, then la consigne, les prompts, l'aide de la brique et le fichier lu sont allemands, et aucune valeur française du périmètre n'est visible.
- Given une consigne `en` ou `de` qui cite un libellé, when le test des libellés joue, then ce libellé existe dans un catalogue de sa langue.

## Implementation Notes

- Commit 1 (`439711d`) : `lang` a pour défaut `fr` dans les chargeurs touchés (jamais `settings.json`). `read_file` est lié par `AppSession._read_file`, qui lit `_language` à chaque appel : rien à remplacer au changement de langue. `DiagnosticSession.language` (lié par `create_app` à `AppSession.language`) donne la langue aux textes du cloud du diagnostic. Une traduction invalide de `publishers.yaml` donne la table française, avec la raison qui nomme le fichier traduit (`load_publishers` ne lève jamais, il ne passe donc pas par `_localized`).
- Commit 2 (`ac0df1b`) : traductions écrites par deux sous-agents (un par langue) à partir d'une table des libellés français → `en`/`de`. Le test des libellés cités compte, par consigne, les citations qui sont des libellés d'un catalogue de la langue (valeur, texte avant la variable, début de valeur, ou « <Forcer l'appel> · <outil> ») : autant qu'en français, et autant de citations en tout.
- Constaté, hors périmètre : la carte Tools affiche encore « Bornes du tour : … » et la carte RAG la raison d'un modèle absent en français (textes produits par `app_session.py`, story 5). La consigne française de la brique Raisonnement cite « toujours active pour ce modèle », que l'interface ne montre plus (« Imposé par ce modèle ») : les traductions citent le libellé réel.

## Spec Change Log

## Review Triage Log

Revue 1 (2026-09-30, trois relecteurs : aveugle (B), cas limites (EC), trous de vérification (VG)).

| # | Constat | Verdict | Preuve | Suite |
|---|---------|---------|--------|-------|
| 1 | Langue des entrées locales du catalogue (`served_by_text`, `hosting_label_text`, groupe local) jamais testée hors `fr` (VG) | low | Les deux tests passent `[]` ou un diagnostic vide : aucune entrée locale | patch |
| 2 | Repli d'un `cloud.yaml` traduit invalide non testé (`active_model`, `DiagnosticSession._cloud_content`) ; test `active_model` en `en` qui ne vérifie que « non vide » (VG, B) | low | Aucun test n'écrit un `cloud.yaml` traduit invalide ; `test_the_active_model_of_a_cloud_choice_is_in_the_language` passerait si `lang` était ignoré | patch |
| 3 | Charge `model_load_*` d'un modèle cloud non testée en `en`/`de` (VG) | low | Code correct (`app_session.py:1701`) ; charge transitoire, relayée par `active_model()` testé | rejeté |
| 4 | `cloud.yaml` traduit invalide : un `harness_error` par appel de `_cloud_content`, soit 1 + N par `/api/diagnostic` (VG, EC, B) | low | Réel, même comportement que la branche française préexistante ; cas de développement ; correction = état de mémorisation | rejeté (improbable) |
| 5 | Fichier de démonstration traduit illisible (UTF-8) : erreur brute sans repli français (EC) | low | Fichiers livrés validés par la parité ; cas de développement ; correction = garde et trace | rejeté (improbable) |
| 6 | Ratio de longueur du test de parité : division par zéro sur un fichier français vide (EC) | low | Aucun fichier de démonstration vide | rejeté |
| 7 | E2E : `StopIteration` si un préréglage manque, clic d'étape qui expire et masque le vrai contrôle (EC) | low | Préréglages présents et figés par la parité ; robustesse du banc seulement | rejeté |
| 8 | E2E `content_language` : le `finally` ne rend ni la brique Hooks ni « Afficher les actions forcées » (EC, B) | low | `run_e2e.py`, `_content_language` : `/api/intentions/brick` hooks et `r.show_forced(True)` jamais défaits ; peut fuir vers la tranche suivante | patch |
| 9 | AD-19 (spine) : « défaut `fr` » faux pour `load_brick_content` et `load_compression_content` (`lang=None`) (EC, B) | low | `bricks/contract.py:60`, `compression/port.py:58` ; la session passe toujours la langue | patch (reformuler le spine) |
| 10 | Critère « aucun fichier français de `content/` n'a changé » contredit par `content/ui.yaml` (EC) | false | L'infobulle française est une tâche de la spec ; la commande de vérification exclut `content/ui.yaml` ; correction = éditer la spec | rejeté |
| 11 | Avertissement cloud en `en`/`de` : `hosting_text` et `notes_text` des déclarations de `wavestack.toml` restent français (B) | medium | `wavestack.toml:269-296` ; insérés par `cloud.fill()` dans les textes traduits ; préexistant, hors `content/` | defer |
| 12 | Légende des éditeurs traduite (« NETWORK », „NETZWERK“) mais préfixes `Local ·` / `RÉSEAU ·` écrits en dur par `catalog.py:490,561` (B) | low | Texte produit par le Python : story 5 | defer |
| 13 | `publishers.yaml` traduit invalide : pas de `harness_error` ; l'avertissement du journal Python affiche désormais le chemin absolu (B) | low | Pas de `harness_error` : même contrat que le français (raison affichée par la page) ; chemin absolu réel (`catalog.py:183`) | patch (chemin relatif) |
| 14 | Messages de `read_file` et refus de H1 français dans le contexte en `en`/`de`, absents de `deferred-work.md` (B) | false | Nommés par CAP-5 de `SPEC.md` (erreurs de `native.py`, refus de H1) | rejeté |
| 15 | Règles de `publishers.yaml` recopiées dans chaque traduction (B) | low | Choix de la spec (textes seuls traduits, champs figés par la parité) | rejeté |
| 16 | Allemand : « Kompression » (brique) et « Komprimierung » (étape, scénario, interface) ; « in Orchestrierung » sans article (11 fois) (B) | low | Nom de la brique figé par l'intention ; « in Orchestrierung » relu dans `scenarios.yaml`, `hooks.yaml`, `subagent.yaml` de `de` | patch (« im Bereich Orchestrierung ») ; Kompression/Komprimierung rejeté |
| 17 | `journal_serveur.log` : processus « sauvegarde » gardé en `de`, traduit en `en` (B) | low | Relu | patch |
| 18 | `test_every_default_sent_to_the_model_is_translated` exige aussi les contenus pédagogiques (B) | low | Nom trompeur | patch (test séparé) |
| 19 | `provider_text` anglais : « training no. » (B) | low | `content/i18n/en/cloud.yaml:11` | patch |
| 20 | Infobulle de langue incomplète (cloud, sélecteur, libellés) et « RAG » cité (B) | low | Ces textes relèvent de « l'interface » ; RAG y était avant la story | rejeté |

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

## Vérification finale (2026-09-30, après la revue 1)

- Rejouée par l'orchestrateur sur `ef9e7d6`, au premier plan, une suite à la fois.
- `ruff check` et `ruff format --check` : propres.
- `pytest` en quatre quarts des 54 `tests/test_*.py` triés : 386, 616, 275 et 302 réussis, 0 échec.
- E2E en huit tranches de 4 à 6 scénarios (les 43) : 80, 163, 41, 97, 98, 101, 88 et 155 vérifications réussies ; un seul échec, `gemini_shape` (« Empreinte estimée … dans le corps de l'appel »), intermittent et préexistant : il échoue aussi une fois sur deux sur `d7c87cf`, et passe au rejeu sur `ef9e7d6` (consigné dans `deferred-work.md`). `content_language`, `ui_language` et `language` passent.
- Aucun fichier français de `content/` changé hors `content/ui.yaml` depuis `d7c87cf`.
