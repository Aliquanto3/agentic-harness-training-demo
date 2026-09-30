---
id: SPEC-langues
companions:
  - i18n-conventions.md
  - ../../implementation-artifacts/spec-i18n-1-socle-et-defauts-du-llm.md
  - ../../planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Langues : WaveStack en français, anglais et allemand (stories 2 à 5)

## Why

Anaël veut WaveStack en français, en anglais et en allemand (demande du 2026-09-29), pour former des publics non francophones avec le même démonstrateur. La story 1, fusionnée par la PR #7, pose le socle et traduit les défauts envoyés au LLM :
- le réglage `language` et le sélecteur ;
- la surcouche `content/i18n/{en,de}/` et la résolution `config.content_file`.

Reste environ 2 000 textes par langue, trop pour une seule story :
- l'interface principale ;
- les contenus pédagogiques ;
- les ateliers et les pages annexes ;
- les messages produits par le backend.

Un formateur qui choisit l'anglais voit aujourd'hui une interface presque entièrement française.

## Capabilities

- **CAP-1** Interface principale (story 2)
  - **intent:** Le formateur lit l'écran principal (`index.html`, `app.js`, environ 540 textes) dans la langue choisie, avec les nombres, les montants et les dates au format de cette langue.
  - **success:** En `en` et en `de`, la tranche E2E de la story ne trouve sur l'écran principal aucun texte du catalogue français, et la barre haute reste lisible à 1 280 et 1 600 px, en mode normal et en projection.
- **CAP-2** Contenus pédagogiques (story 3)
  - **intent:** Les explications des briques, les consignes et les prompts suggérés des scénarios, et les textes du cloud, de la compression, des types de segments et des éditeurs de modèles sont dans la langue choisie. Les fichiers de démonstration que lisent les outils sont traduits aussi.
  - **success:** Un scénario joué en `en` ou en `de` affiche l'explication de la brique, la consigne et les prompts traduits. L'outil `read_file` y lit le fichier de démonstration traduit.
- **CAP-3** Ateliers et pages annexes (story 4)
  - **intent:** L'écran « LLM nu », l'atelier RAG, le diagnostic et la page des modèles sont dans la langue choisie.
  - **success:** Chaque page s'ouvre en `en` et en `de` sans aucun texte du catalogue français, selon la tranche E2E de la story.
- **CAP-4** Corpus RAG par langue (story 4)
  - **intent:** La brique RAG et l'atelier RAG cherchent dans le corpus et l'index de la langue choisie.
  - **success:** En `de`, les extraits placés dans le contexte sont allemands, titres compris. En `fr`, les résultats d'une recherche sont identiques à ceux d'avant la story.
- **CAP-5** Messages produits par le backend (story 5)
  - **intent:** Les textes que produit le code (environ 950 lignes de Python) sont dans la langue de la session :
    - ceux que voit l'utilisateur : `harness_error`, raisons de disponibilité, diagnostic, catalogue des modèles ;
    - ceux que lit le LLM : erreurs d'outils de `tools/executor.py`, `native.py` et `network.py`, marque de troncature, refus de H1 et H5, erreurs de mémoire, jour de la semaine de `get_datetime`, « Terme inconnu du glossaire » du serveur MCP local.
  - **success:** Les tests paramétrés en `fr`, `en` et `de` couvrent chaque clé du catalogue des messages. Un tour joué en `de` avec une erreur d'outil ne place aucun message français dans le contexte.

## Constraints

- **Exécution sur le PC cible (16 Go).**
  - Jouer `pytest` en deux moitiés et l'E2E par tranches `--only`, toujours au premier plan.
  - Ne jamais lancer deux suites à la fois : Claude Code arrête les processus d'arrière-plan en manque de mémoire.
- **Hérité de la story 1.**
  - La surcouche `content/i18n/{lang}/` garde la même arborescence et les mêmes noms de fichiers. Tout passe par un seul point de résolution, `config.content_file`, avec repli sur le français, sans erreur.
  - La parité est validée par le même modèle pydantic : mêmes `id`, mêmes clés de gabarit.
  - La langue ne change que sur une conversation vide, suivie d'un rechargement de la page.
  - Pas de traduction automatique à l'exécution, pas de dépendance ajoutée.
- **Renommage des champs `*_fr` en `*_text`.**
  - Il se fait en un seul commit de renommage pur, au début de la story 2.
  - Il s'applique partout : contrat d'événements, API, modèles pydantic, clés YAML de `content/` et de `content/i18n/`, JS, tests, E2E, `ARCHITECTURE-SPINE.md`.
  - Aucun texte ne change, et la suite est verte avant et après.
  - Il lève deux interdits de la story 1 : « ne pas renommer les champs `*_fr` » et « fichiers français octet pour octet ». Les clés changent, les valeurs restent.
- **Textes de l'interface.**
  - Le français est dans `content/ui.yaml`, l'anglais et l'allemand dans `content/i18n/{en,de}/ui.yaml`.
  - Une route sert le catalogue de la langue de la session, et `t(key, vars)` est partagé par toutes les pages.
  - Le HTML garde son texte français, pour que la page reste lisible si la route échoue. Détail dans `i18n-conventions.md`.
- **Messages du backend.**
  - Le français est dans `content/messages.yaml`, avec les surcouches `en` et `de`, et `msg(key, lang, **kw)` les produit.
  - La langue de la session est passée explicitement, jamais relue de `settings.json` (constat 1 de la revue de la story 1).
- **Index RAG.**
  - Le corpus traduit est dans `content/i18n/{en,de}/corpus/`, sous les mêmes noms de fichiers.
  - `data/rag_index.sqlite` ne change pas pour le français. `data/rag_index.en.sqlite` et `data/rag_index.de.sqlite` sont construits par `scripts/build_rag_index.py --lang` et versionnés.
  - Si l'index d'une langue manque, la carte RAG propose de le construire, comme aujourd'hui.
- **Tests.**
  - La suite existante reste en français et ne change que par le renommage.
  - Chaque story ajoute :
    - la parité de ses fichiers ;
    - des tests paramétrés en `fr`, `en` et `de` sur son périmètre ;
    - une tranche E2E dédiée, jouée en `en` et en `de`.
  - Pas d'E2E complet par langue.
- **L'allemand est la langue la plus longue.** Toute mise en page traduite doit tenir en `de` à 1 280 et 1 600 px, en mode normal et en projection.
  - La story 2 règle au passage la saturation de la barre haute à 1 600 px, déjà visible en français avec la dépense et la langue : sélecteurs réduits à « Mé… », « Cl… », « L… ».
- **Reprises de la story 1.**
  - Story 2 : les textes du code de langue restés français côté front (repli « Disponible hors d'un tour. », « Changement de langue refusé. », refus d'enregistrement).
  - Story 3 : les noms des briques que citent les skills.
  - Story 4 : les titres des documents dans les extraits RAG.
  - Story 5 : le texte du `harness_error` de `_localized`, le jour de `get_datetime` et « Terme inconnu du glossaire ».

## Non-goals

- D'autres langues que `fr`, `en` et `de`.
- Changer de langue pendant une conversation, ou retraduire la page sans la recharger.
- Traduire la documentation (README, guides, cahiers de recette), les artefacts BMAD ou les commentaires du code.
- Traduire ce que l'utilisateur écrit : prompt système modifié, mémoire écrite par l'utilisateur ou le modèle.
- Rejouer tout l'E2E dans les trois langues.

## Success signal

- Langue réglée sur `de`, un formateur joue un scénario de bout en bout : écran principal, briques, consignes, « LLM nu », atelier RAG, diagnostic, page des modèles, puis une erreur d'outil lue par le modèle. Il ne voit aucun texte français, hormis les noms propres et ce qu'il a saisi. De même en `en`.
- En `fr`, la suite existante passe et le seul changement de ses tests est le renommage des champs.

## Assumptions

- Les fichiers de `demo_files/` sont traduits sous les mêmes noms : les prompts des scénarios qui nomment un fichier restent valides dans les trois langues.
- Formats `Intl` : `fr-FR`, `en-GB` et `de-DE`. `en-GB` est retenu pour les dates au format jour-mois et l'heure sur 24 h, adaptées à un public européen.
- Le contrôle « aucun texte français » compare les textes visibles aux valeurs du catalogue français du périmètre de la story. Il exclut les noms propres, les noms de modèles et ce que l'utilisateur a saisi.
- Les pluriels passent par `Intl.PluralRules`, avec des clés `.one` et `.other` (proposé dans `i18n-conventions.md`).
