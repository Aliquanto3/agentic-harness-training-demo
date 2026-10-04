# Plan de corrections du 2026-10-04 (working tree `main`)

Retours d'Anaël du 2026-10-04 sur `main` (64c660d), onglet par onglet : Diagnostic, Modèles,
Atelier MCP, Atelier RAG, Atelier (harnais), LLM nu. Le plan se lit lot par lot, chaque lot
dans une nouvelle session (`/clear`), en plan mode pour les modifications multi-fichiers.

## 1. Explication demandée : « Préfixe non réutilisé » (volet Orchestration)

Le moteur local garde en cache (KV cache) les tokens du dernier contexte lu. Si le nouveau
contexte commence exactement par les mêmes tokens, il ne relit que la suite. Le harnais
compare les deux suites à chaque tour (`_check_prefix`, `_check_reuse`, `_diverging_cause`,
`app_session.py:7521-7614` ; charge `trace/catalog.py:662`). En cas de divergence, il émet
cette ligne :
- tokens communs, tokens à relire ;
- cause : prompt système modifié, historique réécrit ou gabarit, conversation vidée, rejeu,
  tour abandonné, cache occupé par le sous-agent ou par « LLM nu ».

Ce n'est pas une erreur : c'est une information de coût et de latence. Sur un modèle hybride
(Qwen3.5), qui ne sait pas tronquer son cache, tout le contexte est relu.

Libellés : `content/ui.yaml:581` (`main.orch.rows.prefix`), `:688`, causes `:484-492` ;
messages `content/messages.yaml:105-122` (`session.prefix.*`) ; rendu `app.js:5473-5484`.

## 2. Décisions

**Validées par Anaël le 2026-10-04 : les cinq recommandations ci-dessous sont retenues telles
quelles.** D5 reste en attente des captures de schémas d'Anaël, à fournir avant le lot 4.

| # | Question | Décision (recommandation retenue) |
| --- | --- | --- |
| D1 | Fusionner Diagnostic et Modèles ? | **Oui.** Même source (`/api/diagnostic`). Modèles n'ajoute que capacités (fenêtre, outils, raisonnement, prix), tri et filtres : ils passent dans la carte dépliée et dans des filtres en tête. `/models` redirige vers `/diagnostic`. |
| D2 | Nommage des onglets | **Court dans la barre, complet en titre.** Barre : `Harnais · LLM · RAG · MCP · 🛠️ Diagnostic`. `h1` et `<title>` : « Atelier Harnais », « Atelier LLM », « Atelier RAG », « Atelier MCP », « Diagnostic et modèles ». |
| D3 | Logos des éditeurs | Aucun logo dans le dépôt (seul `favicon.svg`). SVG embarqués dans `static/logos/` (appli hors ligne, garde réseau, pas de CDN). Vérifier d'abord le skill `banque-visuels`. Marques : acceptable en formation interne, à vérifier avant tout usage client. |
| D4 | Portée du schéma de l'Atelier LLM | Détailler le **transformeur décodeur dense** (Qwen3, Llama, Gemma). Pas de restriction des modèles : bandeau « schéma simplifié, inexact pour cette architecture » pour les hybrides et MoE. |
| D5 | Inspiration MCP | Cours Anthropic Academy « Introduction to Model Context Protocol » et « MCP: Advanced Topics » non consultés. **Captures de schémas d'Anaël à fournir avant le lot 4.** |

## 3. Lots, dans l'ordre

Ordre : Lot 1 → Lot 2 → Lot 3 → Lot 4 → Lot 5a/5b → Lot 6 → Lot 5c.
Les lots 1 et 3 n'attendent rien ; le lot 4 attend D5 ; 5c attend la validation de 5a/5b.

### Lot 1 — Quick wins (un seul passage de build)

1. **Renommages (D2).**
   - Barre en HTML statique dans les 6 pages : `index.html:21-22`, `llm.html:21-22`,
     `rag.html:21-22`, `mcp.html:21-22`, `diagnostic.html:143-147`, `models.html:80-84` ;
     réécrite par `i18n.js:108-121` depuis `common.links.*`.
   - Clés : `content/ui.yaml:76-80`, `:900` (`llm.page_title`), `content/i18n/{en,de}/ui.yaml:67-70`,
     `content/llm_lab.yaml:5` ; `llm.html` : `<title>` l.8, `h1` l.55, lien l.60.
   - Tests : `tests/test_ui_texts.py:228-235`, `tests/test_llm_lab.py:100,284,818`,
     `tools/e2e/run_e2e.py` (l.377-393, 7253, 9311, 9388-9391, 9510, 10450, 10473-10476).
   - Doc : `README.md:20,69-70`, `docs/installation.md:163`, `docs/guide.md:13,29,213-215,410,462,528`,
     `docs/modeles.md:425,448,514-517`.
   - **Piège** : « LLM nu » désigne aussi le *concept* (aucune brique active) : ne pas renommer
     `scenarios.yaml:38,61`, `ui.yaml:112-113,873`, `messages.yaml:114` et semblables.
2. **Camille → Pascal** : 42 occurrences dans 14 fichiers (contenus fr/en/de, mémoire, tests,
   e2e). Accorder au masculin : « consultante » → « consultant », « Beraterin » → « Berater ».
   Fichiers : `content/scenarios.yaml:97`, `content/memory/memory.yaml:37-39`, leurs copies
   `content/i18n/{en,de}/`, `tests/test_subagent.py`, `tests/test_i18n.py`,
   `tests/test_global_memory.py`, `tests/test_e2e_fake_openai.py`, `tools/e2e/run_e2e.py`.
3. **Barre de dépense sur 3 lignes** : libellé / `💰 coût` / `🍃 CO₂e`.
   - `index.html:233-235` (`#consumption`), `app.js:2400-2453` (`renderConsumption`),
     `app.css:4833-4858`, clés `main.consumption.*` (`ui.yaml:646-656`).
   - `fitFootprint` (`app.js:2455-2477`) masquait le CO₂ faute de place : probablement à retirer.
   - Vérifier la hauteur de la barre aux paliers de `app.css` et en projection, et l'E2E
     « la barre tient ».
4. **« ? » à côté d'« Actions forcées »** : `forcedToggle` (`app.js:1628-1659`, clé
   `main.force.section_title`, `ui.yaml:172`). Réutiliser `.brick-help` + `div.brick-explanation[popover]`
   (`app.js:1292-1318`, `app.css:2305-2340`). Texte proposé : « Le harnais déclenche lui-même
   l'outil, sans laisser le modèle décider. » (fr/en/de).
5. **JSON repliés par défaut (Contexte LLM)** : `jsonNode` ouvre tout
   (`node.open = !store.jsonClosed.has(path)`, `app.js:4222-4227`). Inverser en `store.jsonOpened`
   (déclaré `app.js:103`, remis à zéro `app.js:3590`) ; seule la racine reste ouverte.
6. **« Préfixe non réutilisé »** : d'après le code, la ligne est déjà repliée (non `sticky`,
   `app.js:5473`). Reproduire le cas où elle paraît dépliée (résumé trop long ?), puis
   reformuler, par exemple « Cache non réutilisé : 1 240 tokens relus ».
7. **Diagnostic** : « 💻 Modèles locaux détectés » (`diagnostic.html:184`,
   `diagnostic.candidates_title`, `ui.yaml:1021`), « ☁️ Modèles cloud » (`diagnostic.html:204`,
   `diagnostic.cloud_title`, `ui.yaml:1022`), 🛠️ devant l'onglet ; en/de l.1010-1011.
8. **Guide d'installation des modèles du RAG** (aujourd'hui seul `docs/guide.md:115-158` en parle) :
   - nouvelle section « Modèles du RAG » dans `docs/installation.md` : embedding
     `granite-embedding-107m-multilingual-Q8_0.gguf` (121 Mo, `[rag.embedding]` de
     `wavestack.toml`), reranker `bge-reranker-v2-m3-Q4_K_M.gguf` (438 Mo, `[rag.reranker]`),
     index `data/rag_index{,.en,.de}.sqlite` (livrés, reconstructibles par
     `scripts/build_rag_index.py --download`), FAISS et LanceDB (`uv sync --extra rag-alt`),
     fastembed (facultatif) ;
   - lien depuis le README (« Installation sous Windows », l.25) et depuis le message
     `session.rag_lab.embedding_absent` (`messages.yaml:507`) et `reranker_absent` (l.513).

Modèle : Opus 5.5, effort low à medium.

### Lot 2 — Composant de schéma commun (préalable aux lots 4 à 6)

- Extraire du harnais (`app.js:6783-7434` : `svgEl`, `schemaActivity`, `renderSchema`,
  `buildSchema`, `schemaNode`, `scheduleWires`, `drawSchemaWires` ; CSS `app.css:3172`,
  `:3679-3740`) un module `static/diagram.js` + règles dans `pages.css`.
- Fonctions : blocs qui apparaissent ou s'allument étape par étape, fils animés, boutons
  ◀ ▶ et mode « suivre le direct » piloté par les événements réels, clic sur un bloc pour
  son explication (c'est ce qui retire le texte des ateliers).
- Le harnais est rebranché sur le module sans changement visible (E2E schéma et rail).

Modèle : Opus 5.5, effort high.

### Lot 3 — « 🛠️ Diagnostic et modèles » (fusion, D1)

- Grille de cartes multi-colonnes, groupée Locaux puis Cloud, puis par éditeur
  (`group_models`, `catalog.py:745-768`, éditeurs `content/models/publishers.yaml`).
- Carte : logo (D3), nom, éditeur, taille (`size_bytes`, déjà dans le payload), état en
  couleur (chargé / disponible / incompatible / erreur).
- Clic : carte dépliée avec les messages complets, chemin, capacités, prix, actions
  (Choisir, clé, Tester, avertissement cloud).
- En tête : filtres de la page Modèles (`models.html:116-148`). Contrôles dans une section
  repliable.
- Rendu actuel : JS inline de `diagnostic.html` (`renderCandidates` l.365, `servedRow` l.431,
  `renderCloud` l.512). Textes : `content/ui.yaml:1018-1079`, `content/cloud.yaml`,
  `content/messages.yaml` (sections `diagnostic`, `models`).
- Tests touchés : `run_e2e.py` (`s_diagnostic` l.353, `s_local_server` l.8667,
  `_models_sort_and_filters` l.8993, `_models_window_then_network` l.9121,
  `_diagnostic_search_shown` l.9149, `s_model_catalog` l.9222, `#cloud-cap` l.10060) ;
  `tests/test_web_app.py:45-124,468,496`, `tests/test_ui_texts.py:30-35,201-239`,
  `tests/test_web_tokens.py`, `tests/test_cli_launch.py` (route `/diagnostic` conservée).
- Méthode : `bmad-ux` (DESIGN.md, EXPERIENCE.md, maquette HTML) puis `bmad-build` ; principes
  d'`artifact-design` pour l'esthétique.

### Lot 4 — Atelier MCP en séquence (attend D5)

- Socle existant : chaque message JSON-RPC est capturé avec sens et durée
  (`Capture.record`, `mcp/lab.py:164`), événements `mcp_lab_message`,
  `mcp_lab_connect_ended`, `mcp_lab_call_ended` (`mcp.js:144-180`).
- Trois vues :
  1. architecture : Hôte (WaveStack) ⊃ Client ↔ Serveur ↔ source de données, transport
     stdio ou Streamable HTTP ;
  2. poignée de main en diagramme de séquence : `initialize` → capacités →
     `notifications/initialized` → `tools/list` → outils et leur poids en tokens ;
  3. un appel : le modèle choisit l'outil → `tools/call` → résultat → réinjection dans le contexte.
- Légendes courtes : `content/mcp_lab.yaml` (`methods.*`, `transports`) ; les aides longues
  (`*_help_text`) passent dans le clic sur un bloc. Modèle pydantic `McpLabContent`
  (`mcp/lab.py:54`) à adapter.

### Lot 5 — Atelier RAG en deux pipelines

Aujourd'hui : une seule chaîne linéaire de cartes CSS (`rag.css:102-138`), seul le segment
`RETRIEVAL` est modifiable, la génération ne s'exécute jamais (`OPTIONS`, `rag/lab.py:65`).

- **5a. Indexation, puis requête** : deux schémas progressifs branchés sur
  `rag_lab_stage_started/progress/ended` (`rag/lab.py:1131-1292`) ; garder l'ajout/retrait
  d'étapes de recherche et la comparaison A/B. Explications `stages.*.explain_text`
  (`content/rag_lab.yaml`) au clic sur un bloc.
- **5b. Architectures toutes faites** : RAG dense simple, hybride (BM25 + dense + fusion),
  avec reranking. Ce sont des préréglages de la chaîne.
- **5c. Choix du modèle par composant** : embedding (Granite, fastembed), reranker (en
  déclarer d'autres), LLM (exécuter la génération, lente sur CPU) ; bouton de téléchargement
  dans l'Atelier RAG (`download_model`, `app_session.py:6105`) au lieu de renvoyer vers la
  carte de l'atelier principal. Touche backend, téléchargements et disque.

### Lot 6 — Atelier LLM, schéma inspiré de 3Blue1Brown

- Boucle : texte → tokens → ids → embeddings → N blocs (attention + MLP) → logits →
  température / top-p → token tiré → retour à l'entrée.
- Réel aux deux bouts : tokenisation exacte en local, 5 candidats et top 100 des
  probabilités par token (`models/candidates.py`, `POST /api/llm_lab/distribution`).
- Illustratif au milieu, avec les vraies dimensions du GGUF (`llm_lab.py:31,334-377`) :
  le moteur n'expose ni poids d'attention ni états cachés ; le schéma le dit.
- Base existante : `#embedding-diagram` (`llm.js:270-385`, `DiagramSteps`, `llm_lab.py:84`)
  et la figure de distribution, à migrer sur le module du lot 2. Portée selon D4.

## 4. Prompts de démarrage (une session par lot)

| Lot | Skill | Modèle / effort | Prompt |
| --- | --- | --- | --- |
| 1 | `bmad-build` | Opus 5.5 / medium | « Implémente le lot 1 de `_bmad-output/implementation-artifacts/plan-corrections-2026-10-04.md`. Mets à jour les tests pytest et E2E concernés. » |
| 2 | `bmad-build` | Opus 5.5 / high | « Implémente le lot 2 du plan de corrections du 2026-10-04 : extraire le schéma du harnais dans `static/diagram.js`, sans changement visible sur l'atelier. » |
| 3 | `bmad-ux` puis `bmad-build` | Opus 5.5 / medium | « Lot 3 du plan de corrections du 2026-10-04 : maquette et spécification de la page fusionnée "Diagnostic et modèles" (grille de cartes par éditeur, logos, détail au clic). » |
| 4 | `bmad-ux` puis `bmad-build` | Opus 5.5 / medium | « Lot 4 du plan de corrections du 2026-10-04 : Atelier MCP en séquence, à partir des captures jointes. » |
| 5 | `bmad-spec` puis `bmad-build` | Opus 5.5 / high | « Lot 5 du plan de corrections du 2026-10-04 : découper 5a, 5b, 5c en stories, puis implémenter 5a. » |
| 6 | `bmad-ux` puis `bmad-build` | Opus 5.5 / medium | « Lot 6 du plan de corrections du 2026-10-04 : schéma séquentiel de l'Atelier LLM, portée D4. » |
