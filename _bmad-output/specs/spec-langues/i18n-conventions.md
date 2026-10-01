# Conventions de l'epic Langues

Règles communes aux stories 2 à 5. `SPEC.md` en porte les décisions ; ce fichier en porte le détail.

## Renommage des champs `*_fr` (story 2, premier commit)

- Chaque champ de données `X_fr` devient `X_text` : clés d'événements, réponses d'API, modèles pydantic, clés YAML de `content/` et de `content/i18n/`. Sur `main` à `12112e5`, cela fait 251 noms.
- Les variables de gabarit suivent (`{title_fr}` devient `{title_text}` dans `excerpt_format_fr`, qui devient `excerpt_format_text`), de même que les variables locales qui portent un de ces champs.
- Si `X_text` existe déjà dans le même modèle, on s'arrête et on le signale. Aucune collision n'a été trouvée au découpage.
- Le commit est un renommage pur : aucune valeur ni aucun texte ne change. `ruff`, `pytest` (deux moitiés) et l'E2E (tranches) passent avant et après.
- Les mentions de ces champs dans `ARCHITECTURE-SPINE.md` et `EXPERIENCE.md` sont mises à jour dans le même commit.

## Catalogue d'interface et `t()` (stories 2 et 4)

- **Fichiers.**
  - `content/ui.yaml` porte le français, avec une section par page : `main`, `llm`, `rag`, `diagnostic`, `models`, plus `common` pour les textes partagés.
  - `content/i18n/{en,de}/ui.yaml` ont les mêmes clés.
  - La story 2 crée le fichier avec `common` et `main`, la story 4 ajoute les autres sections.
  - `LANGUAGE_TEXTS` (`app.js`, story 1) migre dans `common`.
- **Clés** : en anglais, `snake_case`, hiérarchiques (`main.top_bar.scenario_label`).
- **Variables** : `{name}`, la même syntaxe que les gabarits Python ; la parité impose le même jeu de variables par clé.
- **Pluriels** : une clé `.one` et une clé `.other`, choisies par `Intl.PluralRules(locale)` quand `vars.count` est donné.
- **Service.**
  - Une route `GET` renvoie `{language, texts}` pour la langue de la session, lu par `config.content_file("ui.yaml", lang)`.
  - Elle a un repli par fichier, comme la story 1 : un fichier traduit invalide donne un `harness_error` et le français.
- **Front.**
  - Un module `i18n.js`, chargé par toutes les pages comme `theme.js`, expose `t(key, vars)`, `locale()` et les formats `Intl` de la langue.
  - Chaque page attend le catalogue avant son premier rendu.
  - Le HTML garde son texte français et porte les attributs `data-i18n`, `data-i18n-title`, `data-i18n-aria-label` et `data-i18n-placeholder`, que le module remplace.
  - Si une clé manque, `t()` rend le texte français et le signale dans la console.
- **Formats** : `fr-FR`, `en-GB`, `de-DE`, pour tous les `Intl.NumberFormat` et `Intl.DateTimeFormat` des pages (ceux de `app.js` sont figés en `fr-FR` aujourd'hui).
- `<html lang>` suit la langue, sur toutes les pages.

## Contenus pédagogiques (story 3)

- Surcouche habituelle : mêmes noms, mêmes `id`, validés par le modèle du français.
- Les fichiers `demo_files/` sont traduits sous les mêmes noms.
- Les noms des briques que citent les skills traduits de la story 1 (« Tools brick », « Baustein Tools ») sont alignés sur les noms de `bricks/*.yaml` traduits.

## Corpus et index RAG (story 4)

- Le corpus traduit est dans `content/i18n/{en,de}/corpus/`, sous les mêmes noms de fichiers. Les documents gardent leur `id`, et leurs titres (`title_text`) sont traduits dans `content/i18n/{en,de}/rag.yaml`.
- **Index.**
  - Le français garde `data/rag_index.sqlite`.
  - L'anglais et l'allemand ont `data/rag_index.en.sqlite` et `data/rag_index.de.sqlite`. Leur chemin se déduit de `rag.index_path` (`wavestack.toml`) en insérant `.{lang}` avant l'extension.
- `scripts/build_rag_index.py --lang {fr,en,de}` construit l'index d'une langue. Les trois index sont versionnés.
- La brique RAG et l'atelier RAG ouvrent l'index de la langue de la session. S'il est absent, la carte propose de le construire, comme aujourd'hui.

## Messages du backend (story 5)

- `content/messages.yaml` porte le français, avec les surcouches `en` et `de` ; clés et variables comme pour `ui.yaml`.
- `msg(key, lang, **kw)` : la langue est toujours un argument, jamais relue de `settings.json`.
- Les messages que lit le LLM (erreurs d'outils, troncature, refus H1 et H5, mémoire, `get_datetime`, glossaire du serveur MCP local) passent par le même catalogue.
- Le serveur MCP local reçoit déjà la langue en argument (story 1).
- Parité stricte (story 7 du 2026-09-30) : les surcouches ont toutes les clés du français, mêmes variables ; une clé nouvelle s'ajoute dans les trois langues dans le même commit.
- Allemand : « Sie » pour l'utilisateur ; les messages lus par le modèle suivent le registre du prompt système traduit (« du »). Ordinaux : `1st`, `2nd`… en anglais, `{n}.` en allemand.
- Terminal : toujours en anglais (`msg(key, "en")`).

## Tests et exécution

- **Parité**, étendue à chaque nouveau fichier traduit : `ui.yaml`, `messages.yaml`, contenus, corpus (mêmes fichiers).
- **Tests paramétrés** en `fr`, `en` et `de` sur le périmètre de la story. La suite existante reste en français.
- **Une tranche E2E par story**, jouée en `en` et en `de` :
  - elle compare les textes visibles aux valeurs du catalogue français de son périmètre ;
  - elle prend des captures en `de` à 1 280 et 1 600 px, en mode normal et en projection ;
  - elle revient en `fr` à la fin, après une attente de repos.
- **Sur le PC cible (16 Go)**, une seule suite à la fois, au premier plan :
  - `pytest` en deux moitiés : les 51 fichiers `tests/test_*.py` triés par nom, la première moitié puis la seconde ;
  - l'E2E par tranches, `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only …`, avec `$env:PYTHONUTF8=1`.
