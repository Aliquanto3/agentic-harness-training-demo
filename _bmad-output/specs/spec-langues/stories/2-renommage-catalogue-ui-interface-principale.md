---
title: 'Langues (2/5) : renommage des champs *_fr, catalogue ui.yaml et t(), interface principale'
type: 'feature'
created: '2026-09-30'
status: 'in-progress'
baseline_commit: '740fa16ce1f5364ac33096aeae6a7a7241eb3645'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-langues/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Langue réglée sur `en` ou `de`, l'écran principal (`index.html`, `app.js`, environ 540 textes) reste en français, avec des nombres et des dates au format `fr-FR`. Les champs de données s'appellent `*_fr` alors qu'ils portent déjà de l'anglais ou de l'allemand. La barre haute sature à 1 600 px, et l'allemand l'allongera encore.

**Approach:** Trois commits, dans cet ordre (CAP-1 de `SPEC.md`, détail dans `i18n-conventions.md`) :
1. renommage pur des champs de données `*_fr` en `*_text` ;
2. le mécanisme : `content/ui.yaml` (sections `common` et `main`), une route, `i18n.js` et `t()`, les formats `Intl` ;
3. les traductions `en` et `de`, puis la barre haute qui tient en `de`.

## Boundaries & Constraints

**Always:**
- **Commit 1, renommage pur.**
  - Il couvre les clés d'événements, les réponses d'API, les modèles pydantic, les clés YAML de `content/` et `content/i18n/`, `wavestack.toml`, le JS, les tests, l'E2E, les variables de gabarit (`{title_fr}`) et les variables qui portent ces champs. Il couvre aussi les mentions dans `ARCHITECTURE-SPINE.md`, `EXPERIENCE.md` et `README.md`.
  - Aucune valeur ne change. `ruff`, `pytest` (deux moitiés) et l'E2E (tranches) passent avant et après.
- **Les fonctions `*_fr` gardent leur nom.** Ces 55 `def …_fr(` fabriquent du texte français (`kv_fr`, `date_fr`, `price_fr`…) ; la story 5 les reprend.
  - Un nom à la fois fonction et clé (`kv_fr`, `warning_fr`, `price_fr`, `count_fr`…) : seule la clé change, pas la définition, l'import ni l'appel.
  - Cela évite les deux collisions relevées : `kv_text` local à `app_session.py:2426`, et `date_text` qui existe déjà dans `hooks.py:263`.
- **Ce qui est déjà écrit se lit encore.**
  - La colonne SQL `title_fr` de `data/rag_index.sqlite` et de l'index de l'atelier garde son nom : l'index français ne change pas d'un octet. Le code la lit sous le nom `title_text`.
  - Les clés `*_fr` d'un `settings.json` existant (`hosting_fr`, `notes_fr`, `training_fr`, `note_fr`, `rag_lab.fastembed.label_fr`) sont encore acceptées à la lecture, en alias, et l'écriture se fait en `*_text`.
  - Une chaîne RAG sauvée dans le navigateur avec `label_fr` se relit aussi.
- **Catalogue.**
  - Les textes sont dans `content/ui.yaml` (`common`, `main`) et `content/i18n/{en,de}/ui.yaml`. Clés en anglais, `snake_case`, hiérarchiques.
  - Les variables s'écrivent `{name}`. Les pluriels ont une clé `.one` et une clé `.other`, choisies par `Intl.PluralRules`. `LANGUAGE_TEXTS` migre dans `common`.
  - `GET /api/ui_texts` rend `{language, texts}` dans la langue de la session, par `AppSession._localized`. Une clé absente de la traduction est comblée par le français côté serveur. Un fichier traduit invalide donne un `harness_error`, puis le français.
- **Front.**
  - `i18n.js` est un module chargé par les cinq pages. Il expose `t(key, vars)`, `locale()` et les formats `Intl` (`fr-FR`, `en-GB`, `de-DE`). Il pose `<html lang>` et remplace les attributs `data-i18n`, `data-i18n-title`, `data-i18n-aria-label` et `data-i18n-placeholder`.
  - `app.js` attend le catalogue avant son premier rendu. Le HTML garde son texte français.
  - Si une clé manque, `t()` rend la clé et le signale dans la console.
- **Le français ne bouge pas à l'écran.** En `fr`, chaque texte, chaque nombre et chaque date rendus sont identiques à ceux d'avant la story. Exemples : « 1 234 », « 0,02 $ », « < 0,0001 $ », les pluriels et les listes « a, b et c ».
- **Périmètre traduit** : tous les littéraux d'interface de `index.html` et `app.js`, dont :
  - les tables de libellés (`PANE_LABELS`, `TURN_STATUS`, `SESSION_STATES`…) ;
  - les messages de repli (« Disponible hors d'un tour. », « Changement de langue refusé. », « Enregistrement refusé : … », « Action refusée. »…) ;
  - l'infobulle du sélecteur de langue, qui dit désormais que les briques, les scénarios et les messages du harnais restent en français jusqu'aux stories 3 à 5.
- **Registre** : l'allemand vouvoie (« Sie »), comme la story 1. Les termes suivent les traductions de la story 1 (Harness, Baustein/brick, Gedächtnis/memory).
- **Barre haute** : elle tient en `de` à 1 280 et 1 600 px, en mode normal et en projection : tous ses contrôles sont entièrement visibles (`_bar_fits`), aucun sélecteur n'est réduit à deux lettres suivies de « … ».
  - Décision (Anaël, 2026-09-30) : un menu « Affichage ▾ », sur le modèle de « Volets », regroupe le thème, la langue et la projection.
  - Les identifiants `#theme-picker`, `#language-picker` et `#projection-toggle` sont conservés dans le menu. Le verrou et l'infobulle du sélecteur de langue restent les mêmes.

**Never:**
- Traduire les textes que le backend envoie dans les champs `*_text` (stories 3 et 5), ni les pages « LLM nu », RAG, diagnostic et modèles (story 4). Ces pages chargent seulement `i18n.js` pour `<html lang>`.
- Changer une valeur de texte dans le commit 1, ou un test existant autrement que par le renommage. Il y a deux exceptions :
  - les assertions de la story 1 sur l'interface restée française (`test_i18n.py`, `s_language`), qui suivent la migration de `LANGUAGE_TEXTS` ;
  - les étapes E2E qui touchent au thème, à la langue ou à la projection : elles ouvrent d'abord le menu « Affichage ».
- Ajouter une dépendance, ou faire une traduction automatique à l'exécution.
- Jouer deux suites à la fois, ou une suite en arrière-plan.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Écran en allemand | `de`, un tour joué | Aucun texte visible, ni `title`, `aria-label` ou `placeholder`, n'est une valeur française de `common` ou `main` dont la valeur allemande diffère. `<html lang="de">`, « 1.234 » | — |
| Français inchangé | `fr` | Rendu identique à avant la story ; E2E existant vert | — |
| Traduction invalide | `content/i18n/de/ui.yaml` casse le schéma | `harness_error`, puis le catalogue français | repli par fichier |
| Clé absente de la traduction | `de` sans `main.x` | La valeur française de `main.x` | comblée côté serveur |
| Route injoignable | `/api/ui_texts` échoue | Le HTML reste lisible en français ; `t()` rend les clés | console |
| Ancien `settings.json` | `hosting_fr` dans un modèle cloud | Lu comme `hosting_text`, sans erreur | alias |
| Pluriel | `count` = 1 ou 2 | `.one` ou `.other` selon `Intl.PluralRules(locale)` | — |

</frozen-after-approval>

## Code Map

- **Renommage** : 251 noms `\b\w+_fr\b` hors `_bmad-output/`. La substitution se fait par un script jetable dans le scratchpad, non versionné, sur la liste des noms moins les usages de fonctions (`def`, `import`, `nom(`) des 55 `def …_fr(`.
  - Le script saute `data/rag_index.sqlite`, le seul binaire concerné.
  - Accès littéraux à vérifier : `getattr` sur `"warning_fr"` (`session/diagnostic.py:793`) et `"label_fr"` (`app_session.py:3200,3214`) ; `.format(title_fr=…)` (`rag/corpus.py:56,72`) et `{title_fr}` dans les trois `rag.yaml` ; la liste `["sent_fr","provider_fr","unseen_fr"]` (`app.js:2824`, `cloud.py:169`) ; `text(path)` de `llm.js:38` et `rag.js:33` ; `vectorization.steps.${key}` (`llm.js:238`).
  - Noms étranges après renommage, acceptés : `text_fr` → `text_text`, `default_text_fr` → `default_text_text` (`llm_lab`).
  - `README.md` (379, 769-771) et `config.py:769` citent des clés de `settings.json`.
- **SQL** : `rag/index.py:197,205,238,250` et `rag/retriever.py:64` gardent `title_fr` en colonne ; alias `AS title_text` dans les `SELECT`.
- **Alias de `settings.json`** : `config.py:65-66` (`extra="forbid"`), 137, 188, 191, 329. Utiliser `validation_alias=AliasChoices("x_text", "x_fr")`. `rag.js:125-126` (`only(p, ["label_fr","stages"])`).
- **Chargeur** : un nouveau `src/wavestack/ui_texts.py`, `load_ui_texts(lang=None)` sur le modèle de `tools/registry.py:104`, avec `config.content_file`, `@cache` ajouté à `clear_content_caches` (`config.py:1050`). Validation : arbre de `str`, à feuilles non vides.
- **Session** : `_localized` (`app_session.py:1545`) ; un `ui_texts()` à côté de `language_state()` (≈ :5166), relu par `_reload_texts` (≈ :5221).
- **Route** : `web/app.py`, à côté de `/api/llm_lab` (:304).
- **Front** :
  - `index.html:267` charge `app.js` en module. `theme.js` est chargé ligne 5 de `<head>` sur les cinq pages, et `i18n.js` s'y ajoute (`llm.html:150`, `rag.html:78`, `diagnostic.html:105`, `models.html:149`).
  - `boot()` est à `app.js:7291`. Le premier `fetch("/api/state")` est à :7427, et `<html lang>` est posé à :7440.
  - Formats (sept `"fr-FR"`) :
    - `numberFormat` 173, `fmt`, `seconds`, `moneyFormat` 177, `usd`, `eur`, `footprintFormat` 184, `rangeText` 187 ;
    - `shortMoneyFormat` 2306 (« < 0,0001 $ » en dur), `scoreFormat` 4591 ;
    - `toLocaleString` 5342, `toLocaleTimeString` 6478.
  - Texte composé :
    - `plural(count, word)` 4969 (33 appels) et 21 ternaires `> 1 ?`, dont 1330, 1336, 1490, 2034, 2334, 2345, 3806, 3829, 4012, 4167, 4634, 4709, 5774, 6887 ;
    - `joinFr` 6851, à remplacer par `Intl.ListFormat` ;
    - les phrases montées par `parts.push` et `sentences.push` (4167, 2334) deviennent des gabarits à variables.
  - `LANGUAGE_TEXTS` 3258-3301.
  - Tables de libellés : 6, 1294, 1544, 1985, 3387, 4778-4958, 5312, 6197-6273, 6580. Constantes `*_FR` : 154, 155, 264, 1080, 1082, 1295, 2857, 4527-4530.
- **Barre haute** :
  - HTML : `index.html:14-81`.
  - CSS `app.css` :
    - la barre :173-190 et :561 ;
    - les priorités de réduction :4797-4828 et les `min-width` :568-588 ;
    - les media queries 1600 (:4766, :4858), 1500 (:4933), 1400, 1300 (:5046) ;
    - la projection :4629-4657 ; les sélecteurs thème et langue :4150-4245 ;
    - le menu « Volets » (`.pane-menu`, `index.html:51-56`) est le modèle d'un menu.
- **Tests** :
  - `tests/test_i18n.py` : `_translations()` :82 et la branche de parité par fichier :111-163 (ajouter `ui.yaml`, sinon `pytest.fail` :163) ; `test_every_per_language_table_has_exactly_the_languages` :198 (`LANGUAGE_TEXTS` quitte `app.js`) ; le modèle du test de traduction invalide :333.
  - E2E : registre `run_e2e.py:7153-7196`, `s_language` :4690, `_pick_language` :4664, `_bar_fits` :1590, `_fully_visible` :1154, projection `#projection-toggle` :1782, `r.shot` :132, `page.inner_text("body")` comme modèle de lecture des textes.

## Tasks & Acceptance

**Execution:**
- [ ] Commit 1, renommage : tout le dépôt, hors `_bmad-output/` sauf `ARCHITECTURE-SPINE.md` et `EXPERIENCE.md`. Il comprend l'alias de colonne SQL, les alias de `settings.json` et la relecture de `label_fr` dans `rag.js` — pour que le renommage n'efface rien de ce qui est déjà écrit.
- [ ] `content/ui.yaml`, `src/wavestack/ui_texts.py`, `config.py`, `app_session.py`, `web/app.py` -- catalogue `common` et `main`, chargeur, route -- commit 2.
- [ ] `src/wavestack/web/static/i18n.js` et les cinq HTML -- `t()`, `locale()`, formats, `data-i18n*`, `<html lang>` -- commit 2.
- [ ] `index.html`, `app.js` -- tous les littéraux via `t()`, formats par `i18n.js`, pluriels, listes -- commit 2, rendu français identique.
- [ ] `content/i18n/{en,de}/ui.yaml` -- traductions -- commit 3.
- [ ] `index.html`, `app.css`, `app.js` -- menu « Affichage ▾ » (thème, langue, projection), avec les contrôles E2E qui les ouvrent (`_themes`, `_pick_language`, projection) -- commit 3.
- [ ] `tests/test_ui_texts.py` (nouveau), `tests/test_i18n.py` -- commits 2 et 3 :
  - la parité de `ui.yaml` : mêmes clés, mêmes variables par clé, paires `.one` et `.other` ;
  - chaque clé `data-i18n*` de `index.html` et chaque `t("…")` littéral de `app.js` existe en français, et le texte HTML égale sa valeur française ;
  - la route en `fr`, `en` et `de` ;
  - la traduction invalide et la clé absente.
- [ ] `tools/e2e/run_e2e.py` -- scénario `ui_language` (commit 3) :
  - en `en` puis en `de`, après un tour, il compare les textes visibles et les attributs aux valeurs de `common` et `main` qui diffèrent entre les deux langues ;
  - il prend des captures `de` à 1 280 et 1 600 px, en mode normal et en projection, avec `_bar_fits` ;
  - dans son `finally`, il attend le repos puis revient en `fr`.
- [ ] `ARCHITECTURE-SPINE.md` (AD-19, « Langue »), `deferred-work.md` (fermer « Barre haute saturée » et la part front des textes de la story 1) -- commit 3.

**Acceptance Criteria:**
- Given la langue `fr`, when on joue ruff, pytest en deux moitiés et l'E2E par tranches après chaque commit, then tout passe, et le diff du commit 1 ne contient que des renommages.
- Given `data/rag_index.sqlite`, when le commit 1 est appliqué, then le fichier est inchangé et une recherche RAG en `fr` rend les mêmes extraits.
- Given la langue `de`, when la tranche `ui_language` joue, then elle ne trouve aucun texte français du périmètre, et la barre haute passe `_bar_fits` aux quatre combinaisons (1 280 et 1 600 px, normal et projection).

## Implementation Notes

- **Commit 1 (`5dbcc86`), renommage.** Script jetable sur les 251 noms ; les 55 `def …_fr(` gardent leur nom (définitions, imports, appels, docstrings). Lecture de l'existant : `title_fr AS title_text` dans les `SELECT` ; alias `AliasChoices` et `_legacy_text_keys` pour les clés `*_fr` de `settings.json` (le renommage avant la fusion garde la priorité d'une ancienne clé sur `wavestack.toml`) ; `label_fr` d'une chaîne sauvée relu par `rag.js`. `tests/test_text_fields.py` couvre les trois cas.
- **Commit 2 (`390e486`), mécanisme.** `content/ui.yaml` (720 feuilles), `ui_texts.py`, `AppSession.ui_texts()`, `GET /api/ui_texts`, `i18n.js` (`t()`, `section()` pour les tables de libellés, `locale()`, formats `Intl`, `ListFormat`, `PluralRules`, `data-i18n*`). `app.js` n'a plus de littéral français ni de format `fr-FR`. `common.language` porte l'ancien `LANGUAGE_TEXTS`, avec ses valeurs `en` et `de` dès ce commit (sinon `s_language` régressait) ; la parité stricte n'est vérifiée qu'au commit 3.
- **Commit 3 (`e20119a`), traductions et barre.** `en` et `de` écrits par deux sous-agents, contrôlés par la machine (clés, variables, vouvoiement), sans relecture humaine. Menu « Affichage ▾ » : face = symbole du thème et code de langue ; les faces compactes du thème et de la langue et le « Aa » de la projection disparaissent, d'où le remplacement de `_compact_picker` par `_display_menu_picker` et de `#theme-picker-box` par `#display-menu` dans `_bar_fits` (au-delà de « ouvrir le menu »). `main.outbound_summary.left` devient une paire `.one` / `.other`. Le contrôle « aucun texte français » ignore les textes (ou citations de textes) envoyés par la session, encore français jusqu'aux stories 3 et 5.
- **Commit 4, reprises de la vérification.** Barre haute lisible en `fr`, `en` et `de` (CSS seul) : au-dessus de 1 000 px, le scénario, l'hébergement et le nom du modèle et le sélecteur de modèle gardent environ six caractères et « … » ; sous 1 700 px, le titre part, les liens disent « LLM » et « RAG », et la puce du modèle garde son hébergement (le fournisseur reste dans l'infobulle, `app.js` le met dans son propre `span`) ; sous 1 400 px, « Affichage ▾ » garde symbole et code. La tranche `ui_language` mesure ces quatre noms (les six premiers caractères et « … » dans leur propre police) en `fr`, `en` et `de`, à 1 280 et 1 600 px, normal et projection, et couvre les lignes « Route injoignable » et « Pluriel » de la matrice. `<html lang>` n'est plus posé par `app.js` mais par `i18n.js` seul (français quand la route échoue). Citations de l'utilisateur par `common.format.quote` (« … », “…”, „…“).
  - Écarts du commit 4 : ces minimums ne s'appliquent qu'à partir de 1 200 px et tant qu'aucune puce ne dit « · lié » (lot K : cette puce ne cède jamais, les noms cèdent pour elle, comme avant) ; en projection jusqu'à 1 600 px, avec la dépense ou l'empreinte dans la barre, « Réinitialiser » garde son seul « ⟲ » (nom accessible et infobulle entiers ; `main.top_bar.reset` porte désormais le mot sans le symbole). Deux contrôles E2E existants suivent le titre et les liens compacts sous 1 700 px (survol de « Réinitialiser » au lieu du titre ; « LLM » / « RAG » acceptés, nom accessible vérifié). `rag_lab` dépend des modèles téléchargés par `rag` et `rag_rerank` : à jouer dans la même tranche.

## Spec Change Log

## Review Triage Log

## Design Notes

- Le serveur comble les clés manquantes : `t()` n'a jamais besoin du français à part, et la parité rend ce cas exceptionnel.
- Les montants gardent le motif de la langue par une clé, par exemple `common.format.usd: "{amount} $"` en `fr` et `de` et `"${amount}"` en `en`. `Intl.NumberFormat` en `currency` écrirait « $US » en français.
- Le contrôle E2E compare des nœuds de texte entiers, pas des sous-chaînes, et ignore les clés dont la valeur traduite égale la française (« Tokens », « RAG »…).

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` sur les 26 premiers `tests/test_*.py` triés, puis sur les suivants, au premier plan -- expected: tout vert
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only …` par tranches, dont `ui_language` et `language` -- expected: 0 FAIL
- `git diff --stat HEAD~… -- data/rag_index.sqlite` après le commit 1 -- expected: vide
