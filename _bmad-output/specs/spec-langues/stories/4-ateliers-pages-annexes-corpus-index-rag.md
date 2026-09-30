---
title: 'Langues (4/5) : ateliers, pages annexes, corpus et index RAG par langue'
type: 'feature'
created: '2026-09-30'
status: 'in-progress'
baseline_commit: 'da6748d592bf34beeac61a570932e4633e56bfa7'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-langues/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Langue réglée sur `en` ou `de`, l'écran principal et les contenus pédagogiques sont traduits (stories 2 et 3). En revanche, « LLM nu », l'atelier RAG, le diagnostic et la page des modèles restent en français : leur HTML et leur JS n'utilisent pas `t()`, et `llm_lab.yaml` et `rag_lab.yaml` sont lus sans la langue de la session. Le RAG cherche aussi toujours dans le corpus et l'index français, titres compris.

**Approach:** CAP-3 et CAP-4 de `SPEC.md`, livrés en quatre commits :
1. La langue de la session est suivie par les ateliers, le corpus, le chemin de l'index, le script et la session. Rien n'est encore traduit : le français reste identique, octet pour octet pour `data/rag_index.sqlite`.
2. Les quatre pages passent par `t()`, avec les sections françaises de `ui.yaml`.
3. Les traductions `en` et `de` sont écrites, puis les deux index sont construits et versionnés.
4. La tranche E2E `annex_language` est ajoutée et la documentation mise à jour.

## Boundaries & Constraints

**Always:**
- **Catalogue.**
  - `content/ui.yaml` gagne les sections `llm`, `rag`, `diagnostic` et `models`, qui couvrent les textes du HTML et les littéraux des JS de ces pages.
  - La navigation et le thème, communs aux cinq pages, passent dans `common` : `main.theme.*` et `main.links.*` y déménagent, et `app.js` suit.
  - Les quatre pages attendent `ready` avant leur premier rendu. Le HTML garde son français et porte les attributs `data-i18n*`.
  - Tous les formats passent par `numberFormat` et `dateTimeFormat` de `i18n.js`. Plus aucun `"fr-FR"`, `toLocaleString` ni `.replace(".", ",")` dans les pages.
- **Ateliers.**
  - `llm_lab.yaml` et `rag_lab.yaml` sont traduits sous `content/i18n/{en,de}/`, avec les mêmes clés et les mêmes `id`, validés par `LabContent` et `RagLabContent`.
  - Leurs chargeurs prennent `lang` et passent par `AppSession._localized` : un fichier traduit invalide donne un `harness_error`, puis le français.
- **Corpus.**
  - Les huit fichiers sont traduits sous `content/i18n/{en,de}/corpus/`, sous les mêmes noms. Chaque fichier garde sa structure (titres, paragraphes) et à peu près sa longueur.
  - Les `documents` de `rag.yaml` en `en` et `de` gardent les mêmes `id` et le même `file`. Seuls les `title_text` sont traduits.
  - L'intro traduite ne dit plus « (in French) » ni « (auf Französisch) ».
  - `chunk_corpus` lit le corpus de la langue qu'on lui passe, fichier par fichier, avec repli sur le français.
- **Index.**
  - `config.rag_index_path(lang)` renvoie `rag.index_path` tel quel en `fr`. En `en` et `de`, il insère `.{lang}` avant l'extension.
  - `scripts/build_rag_index.py --lang {fr,en,de}` a pour défaut `fr` et ne relit plus la langue dans `settings.json`. Il écrit l'index de la langue demandée, titres de la langue compris.
  - La carte RAG, la recherche, le contrôle de fraîcheur (`_rag_index_mismatch`), la construction depuis la carte et l'atelier RAG (`brick_index`, repli de découpage) utilisent tous l'index et le corpus de la langue de la session.
  - `set_language` libère la connexion à l'index et l'embedder rattaché, puis réévalue la disponibilité du RAG. Si l'index de la nouvelle langue manque, la carte propose « Construire l'index », comme aujourd'hui.
  - `data/rag_index.en.sqlite` et `data/rag_index.de.sqlite` sont construits avec le vrai modèle d'embedding, un par un, puis versionnés.
- **Infobulle.** `common.language.help` (en `fr`, `en` et `de`) ne cite plus que les messages du harnais comme restant en français.
- **Exécution.**
  - `pytest` en quarts et l'E2E par tranches `--only`, au premier plan, une suite à la fois.
  - Les sous-agents de traduction reçoivent la table des libellés `ui.yaml` déjà traduits, pour citer l'interface réelle.

**Never:**
- Reconstruire ou modifier `data/rag_index.sqlite`, ou changer un fichier français de `content/` hors `ui.yaml`.
- Renommer la colonne SQL `title_fr`, un `id`, un nom de fichier du corpus ou une clé de gabarit.
- Traduire ce que produit le Python : raisons et chiffres de `lab_state`, `rag_lab_state`, `lab.py` et `catalog.py`, ainsi que les messages du diagnostic et du script. C'est la story 5.
- Rendre `fake_openai.py` ou `FakeEmbedder` sensibles à l'anglais ou à l'allemand.
- Changer un test existant, sauf :
  - les assertions de la story 1 sur les ateliers et le corpus restés français (`test_i18n.py:210-213`, `:279-280`) ;
  - `test_ui_texts.py:63` (liste des sections) ;
  - les tests d'un chargeur dont la signature gagne `lang` ;
  - les clés `main.theme` et `main.links` déménagées.
- Ajouter une dépendance, ou traduire à l'exécution.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Tour RAG en allemand | `de`, index `de` présent, brique RAG | Extraits allemands « Auszug 1 — <titre allemand>: » ; aucun titre français | — |
| Français inchangé | `fr`, même question qu'avant la story | Mêmes extraits, même ordre, même texte ; `data/rag_index.sqlite` intact | — |
| Index absent | `en`, `rag_index.en.sqlite` absent | Carte RAG indisponible, « Construire l'index » proposé ; la construction écrit `rag_index.en.sqlite` | raison existante |
| Changement de langue | `fr` → `de`, RAG prêt | Connexion `fr` fermée ; la recherche suivante lit l'index `de` | — |
| Index d'une autre langue | `rag_index.de.sqlite` copié depuis le français | Signalé périmé (empreinte du corpus), reconstruction proposée | `stale` existant |
| Atelier RAG | `de`, lancer une chaîne | Textes de `rag_lab.yaml` `de` ; extraits et titres allemands | — |
| Atelier traduit invalide | `i18n/en/llm_lab.yaml` casse le schéma | `harness_error`, puis la page en français | `_localized` |
| Pages annexes | `en`/`de`, ouvrir `/llm`, `/rag`, `/diagnostic`, `/models` | Aucun texte du catalogue français (`ui.yaml` et ateliers) ; `<html lang>` juste | — |
| Clé manquante | clé absente de `i18n/de/ui.yaml` | Texte français et avertissement dans la console | repli `t()` |
| Script | `build_rag_index.py --lang de` | Écrit `data/rag_index.de.sqlite` ; rien d'autre | sortie 1 si l'index est ouvert (`IndexInUse`) |

</frozen-after-approval>

## Code Map

- **i18n front** : `static/i18n.js` (`t` L70, `section` L85, `applyTexts` L110, `ready` L122, `numberFormat` L53, `dateTimeFormat` L55). Modèle d'usage : `app.js` L7 et `await textsReady` L7183. Route `/api/ui_texts` (`web/app.py:306`) → `ui_texts.load_ui_texts` (`ui_texts.py:63`, `_filled` L36).
- **Pages** :
  - `llm.html` : environ 30 textes ; les `data-text` sont lus par `text()` de `llm.js` L38 (atelier) et restent tels quels.
  - `llm.js` :
    - environ 22 littéraux : L77, L93, L96, L101, L113, L118-121, L211, L214, L527, `STEP_NAMES` L599-605, L617, L925 ;
    - formats et guillemets figés : `Intl` `fr-FR` L332 et L712, « » L214, L240, L527, L763.
  - `rag.html` : environ 28 textes.
  - `rag.js` :
    - littéraux : L76, L90, L170, L189, L269-270, L289, L393-394, L602, L608, L689, L777 ;
    - formats figés : L41-45 (`fr-FR`, virgule, ordinaux).
  - `diagnostic.html` : environ 17 textes, plus un script en ligne L106-605 (environ 45 littéraux, format « Go » L284-290).
  - `models.html` : environ 25 textes, plus un script en ligne L150-238 (statuts L181-184, erreurs L207 et L212, pluriel fait main L232, état vide L233).
  - Navigation et thème identiques sur les quatre pages (`nav.page-tabs`, `#theme-picker`). Pas de mode projection hors `/`.
- **Clés à déménager** : `main.theme.*` (`ui.yaml:756-760`) et `main.links.*` (:751-755) vers `common`. `common.format.quote` sert aux guillemets.
- **Ateliers** :
  - `session/llm_lab.py:206` `load_lab_content()` (`LabContent` L182) ; `rag/lab.py:199` `load_lab_content()` (`RagLabContent` L133).
  - Appels : `app_session.lab_state` :7531, `rag_lab_state` :8184 et :8113, catalogue :8136.
  - Vidage des caches : `config.py:1090-1091`.
- **RAG** :
  - `config.rag_index_path` (`config.py:830`), appelé à `app_session` 2732, 2748, 2882, 2990, 5699, 6214 et 8308.
  - `rag/corpus.py:129-138` `chunk_corpus` (langue figée `DEFAULT_LANGUAGE` L134, commentaire L133) et `load_rag_content` L84.
  - `rag/index.py` : `build_index`, `chunks.title_fr` L196-206, empreinte du corpus L75-80, `IndexInUse` L162-181. `retriever.py:63-69` lit `title_fr AS title_text`.
  - Session :
    - `_load_rag` :2697 ; `_rag_refresh` :2722 ; `_rag_index_state` :2741 ; `_rag_index_mismatch` :2804 ;
    - `_rag_offers` :2860 ; `_load_embedder` :2990 ; `build_rag_index` :5649 et `_run_build` :5690 ;
    - `_rag_current_retriever` :6206 ; `set_language` :5234 ; `_reload_texts` :5306 ;
    - `_run_rag_lab` :8281 (`LabDeps` :8303-8309), `lab.py` `_chunking` :1239-1250.
  - Script `scripts/build_rag_index.py` : arguments L57-69, `load_rag_content()` L75, cible L108, `BUILD_FROM_THE_CARD_FR` L39.
- **Contenus** : `content/i18n/{en,de}/rag.yaml` (en-tête L1-3, intro L10, `documents` recopiés du français), `index_label_text` qui nomme le fichier.
- **Tests** :
  - `test_i18n.py` : branche de parité par fichier L159-270, `PEDAGOGICAL` L80, assertions françaises L210-213 et L279-280.
  - `test_ui_texts.py` : sections L63, parité L83, contrôle des clés de `app.js` et `index.html` L116 (à étendre aux quatre pages), absence de `fr-FR` L156.
  - `test_content_language.py` : modèle des tests paramétrés.
  - `test_rag.py:89-106`, `test_rag_lab.py:35-37` : index minuscule construit avec `FakeEmbedder`.
  - `test_rag_review.py:601-666` : le script, avec `embedder_factory`.
  - `test_text_fields.py:101-112` ouvre le vrai `data/rag_index.sqlite`.
- **E2E** (`tools/e2e/run_e2e.py`) :
  - `_french_patterns` :4855, `_backend_strings` :4872, `_french_left` :4910, `_switch_language` :4931 ;
  - `s_content_language` :5165 (captures, `finally`), `_goto_lab` :6842 (`body[data-lab-ready]`), `_goto_rag_lab` :7215 (`body[data-rag-ready]`), `_rag_lab_run` :7220 ;
  - `s_rag` :3867 (construction depuis la carte :3940-3964, corps envoyé au modèle `r.fake_calls()` :4017), registre `SCENARIOS` :7757.
  - Serveur E2E : `stack.py:112`, avec `index_path` = `data_dir/rag_index.sqlite`, donc l'index `de` = `data_dir/rag_index.de.sqlite`, à construire depuis la carte avec le faux embedder.

## Tasks & Acceptance

**Execution:**
- [x] Commit 1, la langue suit :
  - fichiers : `config.py`, `rag/corpus.py`, `rag/lab.py`, `session/llm_lab.py`, `session/app_session.py`, `scripts/build_rag_index.py` ;
  - changements : `rag_index_path(lang)`, `chunk_corpus(..., lang)`, chargeurs d'ateliers à `lang` via `_localized`, `--lang`, `set_language` qui libère et réévalue le RAG ;
  - aucun fichier de `content/` ni de `data/` ne change, suite verte.
- [x] `tests/test_annex_language.py` (nouveau), commits 1 puis 3, paramétré `fr`, `en` et `de` :
  - chaque ligne de la matrice côté Python, avec des index minuscules construits par `FakeEmbedder` ;
  - chaque chargeur lit sa langue sans `settings.json` (réglage contraire au paramètre) ;
  - `--lang` écrit le bon fichier et laisse les autres intacts.
- [x] Commit 2, les pages passent par `t()` :
  - fichiers : `static/{llm,rag}.{html,js}`, `diagnostic.html`, `models.html`, `app.js`, `content/ui.yaml` ;
  - `llm.js` et `rag.js` importent `i18n.js` ; formats `Intl` de la langue ; rendu français identique.
- [x] `tests/test_ui_texts.py`, commit 2 :
  - sections attendues ;
  - le contrôle des clés `t()` et `section()` et du français de `data-i18n*` s'étend aux quatre pages et à leurs scripts en ligne ;
  - plus aucun `fr-FR` ni `toLocaleString` dans les cinq pages.
- [x] Commit 3, traductions :
  - `content/i18n/{en,de}/` : `ui.yaml` (quatre sections et `common`), `llm_lab.yaml`, `rag_lab.yaml`, `rag.yaml`, `corpus/*.md` ;
  - écrites par deux sous-agents, un par langue.
- [x] `data/rag_index.en.sqlite`, `data/rag_index.de.sqlite`, commit 3 : `uv run python scripts/build_rag_index.py --lang en`, puis `--lang de`.
- [x] `tests/test_i18n.py`, commit 3 : branches de parité pour `llm_lab.yaml`, `rag_lab.yaml` et `corpus/*.md` (même ensemble de fichiers, mêmes titres de section `#` en nombre, longueur à ±40 %) ; `rag.yaml` avec les mêmes `id` et `file` mais des titres différents du français ; assertions françaises de la story 1 retirées.
- [x] `tests/test_annex_language.py`, commit 3 :
  - les index versionnés `en` et `de` ont les titres de leur langue et l'empreinte de leur corpus, sans modèle réel (lecture de la table `meta`) ;
  - `data/rag_index.sqlite` a le même `sha256` qu'à la base.
- [x] `tools/e2e/run_e2e.py`, commit 4, tranche `annex_language`, en `en` puis `de` :
  - ouvrir `/llm`, `/rag`, `/diagnostic` et `/models` ;
  - aucun texte du catalogue français du périmètre (sections de `ui.yaml`, `llm_lab.yaml`, `rag_lab.yaml`) ; `<html lang>` juste ;
  - en `de` : construire l'index depuis la carte ; un tour RAG dont le corps envoyé contient « Auszug 1 — » suivi d'un titre allemand et aucun titre français ; une chaîne de l'atelier RAG ;
  - captures `de` à 1 280 et 1 600 px ;
  - `finally` : repos, brique RAG rendue, `fr`.
- [x] `README.md` (RAG L613-642), `ARCHITECTURE-SPINE.md` (L520-521, L605, L773-775 et AD-19), `deferred-work.md` (fermer l'entrée L545 et la part « titres RAG » de L551), en-têtes de `content/i18n/{en,de}/rag.yaml`, commit 4.

**Acceptance Criteria:**
- Given la langue `fr`, when on joue ruff, pytest en quarts et l'E2E par tranches après chaque commit, then tout passe, et ni `data/rag_index.sqlite` ni un fichier français de `content/` hors `ui.yaml` n'a changé.
- Given la langue `de`, when la tranche `annex_language` joue, then les quatre pages n'affichent aucun texte du catalogue français du périmètre, et les extraits envoyés au modèle sont allemands, titres compris.
- Given `rag_index.de.sqlite` versionné, when le formateur passe en `de` sur une installation neuve où le modèle d'embedding est présent, then la brique RAG est disponible sans reconstruction.

## Implementation Notes

- Commit 1 (509c516) : `rag_index_path(lang)`, `chunk_corpus(…, lang)`, `build_index(…, lang=)`, chargeurs d'ateliers à `lang` (défaut `fr`, comme ceux de la story 3), `LabDeps.lang`. `set_language` rafraîchit l'état du RAG tout de suite, puis `_rag_follow_language` libère l'embedder et sa connexion sur le worker (après un chargement en cours, avant tout tour) et `_request_rag_sync` le recharge si la brique est voulue et l'index là. La raison « index absent » cite `--lang {lang}` hors du français. `test_rag_review.py` : le faux `load_rag_content` du test du script reçoit `lang` (le script le passe désormais) — seule retouche d'un test existant hors de la liste, de la nature « chargeur dont la signature gagne `lang` ».
- Commit 2 (5a67133) : deux écarts au plan, imposés par les tests existants.
  - Les sections traduites de `content/i18n/{en,de}/ui.yaml` entrent dans ce commit (et non au commit 3) : la parité clé par clé et l'absence de « » de `test_ui_texts` rendraient la suite rouge sinon.
  - `test_web_app.py` lit le HTML exact des liens de navigation (`<a href="/models" aria-current="page">Modèles</a>`, `open-link`) et de `<th scope="col">Prix</th>` : ces balises gardent leur HTML. Les liens sont traduits par `applyTexts` d'après leur adresse (`nav[data-i18n-links]`), les en-têtes du tableau des modèles par leur ordre (`COLUMN_ORDER`, `section("models.columns")`) ; `test_ui_texts` vérifie que leur français est celui du catalogue.
  - `test_ui_texts.py` : la liste des sections change aussi dans `test_the_route_serves_the_sessions_language` (même nature que L63).
- Commit 3 (beaa49d) : traductions écrites par deux sous-agents (un par langue), relues par échantillons ; index construits avec Granite (`--lang en` : 26 extraits, `--lang de` : 30), `data/rag_index.sqlite` inchangé (sha256 vérifié par test). Les sous-agents ont relevé que BM25 de l'atelier n'ignore que des mots vides français : noté dans `deferred-work.md`, les explications traduites le disent.
- Commit 4 : tranche `annex_language` (après `content_language` dans `SCENARIOS`) ; le contrôle « aucun texte français » compare les textes visibles aux valeurs françaises de `common`, `llm`, `rag`, `diagnostic`, `models` et des deux ateliers, hors ce que rendent l'état, les événements et les routes `/api/llm_lab`, `/api/rag_lab`, `/api/diagnostic` (messages du Python, story 5). Captures `de` des quatre pages à 1 280 et 1 600 px.

## Spec Change Log

## Review Triage Log

## Design Notes

- Le chemin de l'index se déduit de la langue, et non d'une entrée de `wavestack.toml` par langue : un seul réglage, et le français reste identique.
- L'index porte les titres (`title_fr`, lus comme `title_text`). Un index par langue suffit donc à traduire les titres des extraits, sans toucher à `retriever.py`.
- Le contrôle de fraîcheur compare l'empreinte du corpus de la langue. Un index `fr` copié sous le nom `de` est donc vu comme périmé.
- Pas de mode projection sur les pages annexes : les captures se font en mode normal seulement.
- Ordinal du rang (`rag.js` L45) : une clé à pluriel `.one` et `.other` (« 1er » et « {count}ᵉ », « No. {count} », « Nr. {count} »). Aucune règle ordinale propre à l'anglais.
- La tranche E2E construit l'index `de` depuis la carte, avec le faux embedder : l'index versionné, construit avec Granite, y serait refusé (autre modèle).

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` en quatre quarts des `tests/test_*.py` triés, au premier plan -- expected: tout vert
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only …` par tranches de 4 à 6, dont `annex_language`, `content_language`, `ui_language`, `rag`, `rag_lab` et `llm_screen` -- expected: 0 FAIL
- `git diff --stat da6748d592bf34beeac61a570932e4633e56bfa7 -- data/rag_index.sqlite content/ ':!content/i18n' ':!content/ui.yaml'` -- expected: vide
