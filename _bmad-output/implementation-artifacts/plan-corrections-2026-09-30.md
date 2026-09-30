# Plan de corrections du 2026-09-30 (working tree `main`)

Retours d'Anaël du 2026-09-30 sur `main` (12112e5), après la fusion du lot de la nuit
(Gemini, FinOps, GreenOps, Langues 1/5). Un second working tree (`feat/i18n-2`, dossier
`agentic-harness-training-demo`) travaille en parallèle sur les Langues 2 à 5 ; la
réconciliation viendra après ce plan.

## 1. Constat : les quatre « erreurs critiques » ont une seule cause

Le serveur qui répond sur `http://127.0.0.1:8420` n'est pas celui de ce working tree.

| Fait | Preuve (relevée le 2026-09-30) |
| --- | --- |
| Processus périmé | PID 13156, lancé le 2026-09-29 à 20:20:27 par `agentic-harness-training-demo\.venv\Scripts\python.exe` sur un `launch.py` du scratchpad d'une autre session Claude |
| Python d'avant les fusions | `GET /rag` → 404 ; `/api/diagnostic` ne liste que `groq` et `mistral` (pas de `gemini`) |
| Fichiers statiques lus sur le disque de l'autre working tree | `app.js` servi : 0 occurrence de `label_fr` et `title_fr`, remplacés par `label_text` et `title_text` (renommage en cours de la story Langues 2) |
| `main` sain | `ruff` OK ; 270 tests (`test_web_app`, `test_cloud`, `test_scenarios`, `test_model_catalog`, `test_i18n`) passent ; en mémoire, `/rag` → 200 et le cloud liste `groq`, `mistral`, `gemini` |

Conséquences observées, toutes expliquées par ce décalage :
- « undefined » dans « Changer de modèle » : le JS récent lit `m.label_text`, l'ancien Python envoie `label_fr`.
- titres de scénarios invisibles : `s.title_text` vaut `undefined`, l'option est vide (ce n'est pas une couleur).
- `/rag` en « Not Found » : la route n'existe pas dans l'ancien processus.
- pas de Google AI Studio : l'ancien `wavestack.toml` chargé ne le déclarait pas.

Piège : `wavestack` (cli.py) ne relance rien si une instance saine occupe déjà le port ; il
ouvre le navigateur sur l'ancienne. Deux working trees doivent donc tourner sur deux ports.

## 2. Ce qui reste vrai après relance

- **Gemma sur Google AI Studio** : réellement absent. Seul `gemini-3.5-flash-lite` est déclaré.
  L'éditeur `gemma` existe déjà dans `content/models/publishers.yaml`.
- Toutes les demandes d'UX (barre de navigation commune, titres de volets, barre de l'atelier
  en bas, refonte Diagnostic et Modèles, tableau triable, LLM nu pédagogique).
- **Atelier MCP** : demande nouvelle. Le MCP n'a aujourd'hui que sa carte de brique et ses
  nœuds du schéma ; le protocole lui-même (poignée de main, `tools/list`, `tools/call`, JSON-RPC)
  n'est visible nulle part, alors que le LLM nu et le RAG ont chacun leur page.

## 3. Lots, dans l'ordre

### Lot 0 — Relancer le bon serveur (5 min, sans code)
1. `taskkill /PID 13156 /F` (processus périmé de l'autre working tree).
2. Depuis ce working tree : `uv run wavestack`.
3. Convention : l'autre working tree se lance avec `uv run wavestack --port 8421`.
4. Recette : `/rag` s'ouvre, « Changer de modèle » nomme les modèles, les scénarios ont leur
   titre, Google AI Studio apparaît dans les modèles réseau.
5. Quick win facultatif (R0) : `GET /api/health` renvoie aussi le dossier du projet et le
   commit ; le CLI l'affiche quand il réutilise une instance (« déjà lancée depuis … »).

### Lot 1 — Gemma via Google AI Studio (critique)
- Relevé : `GET https://generativelanguage.googleapis.com/v1beta/openai/models` avec la clé,
  pour le nom exact du modèle Gemma servi, sa fenêtre, l'appel d'outils (à tester avec
  « Tester »), le raisonnement.
- Décision à prendre : Gemma n'est servi que sur l'offre gratuite, or la note du projet dit
  l'offre payante obligatoire (clause EEE). Proposition : déclarer l'entrée avec
  `training = "yes"` (ou `opt_out`), `trial = true` et un `notes_fr` explicite, pour que
  l'avertissement « Ce modèle tourne hors de votre poste » dise la vérité ; c'est la
  pédagogie recherchée.
- Changements : `[[cloud.models]] id = "gemma"` dans `wavestack.toml` (`base_url` identique
  à Gemini, `key_env = "GEMINI_API_KEY"`, `pricing` à 0 ou absent, `impacts` si EcoLogits
  connaît le modèle, sinon pas d'empreinte) ; README « Modèle cloud » ; `tests/test_cloud.py`.
- Recette réelle avec la clé (budget déjà fixé : 3 € au plus).

### Lot 2 — Navigation commune et barre de l'atelier
- Une barre de navigation identique en tête des cinq pages : logo WaveStack, Atelier, LLM nu,
  Atelier RAG, Diagnostic, Modèles, thème, langue. Elle remplace `.page-tabs` des pages
  annexes et absorbe `#llm-link`, `#rag-link` et le titre de la barre de l'atelier.
- Atelier : barre actuelle déplacée en bas (`.top-bar` → barre basse), titres de volets
  (« Vue humain »…) réduits d'un cran typographique.
- Risques : les règles de projection et les paliers 1 000 / 1 100 / 1 280 / 1 400 / 1 500 /
  1 600 px de `app.css` visent `.top-bar` ; la vérification E2E de la barre (« la barre
  tient ») et le panneau « Fenêtre » calé sous la barre doivent suivre. Traite au passage le
  constat différé « barre saturée à 1 600 px ».
- Méthode : mise à jour de DESIGN.md / EXPERIENCE.md (`/bmad-ux`), puis `/bmad-build`.

### Lot 3 — Pages Diagnostic et Modèles
- Refonte visuelle des deux pages avec les tokens de `tokens.css` (skills `artifact-design`
  pour les principes, `dataviz` pour le tableau et les jauges, `/bmad-ux` pour la spec).
- Tableau des modèles : tri par colonne (`aria-sort`), filtres (hébergement, éditeur, outils,
  raisonnement, texte libre), sans dépendance JS ; les données viennent déjà de
  `/api/diagnostic.models`.
- Diagnostic : état « Recherche et test des modèles en cours… » avec progression (constat
  différé de la story 8b), hiérarchie visuelle des contrôles, bloc cloud plus lisible.

### Lot 4 — LLM nu pédagogique
- Démarche : pour chaque section, lister les questions qu'un stagiaire se pose, puis y
  répondre par une manipulation visible.
- Section 2 : distribution de probabilités vivante (barres des candidats, déjà calculés par
  `candidates_from_logits`) recalculée à chaque réglage : top-k, top-p, min-p, température ;
  comparaison A/B : la même invite générée avec deux réglages, affichée côte à côte.
  Contrainte : un seul modèle local sur CPU et une session `llm_lab` exclusive ; le « en
  parallèle » sera séquentiel en local (deux générations enchaînées, rendu côte à côte),
  réellement parallèle seulement pour un modèle cloud.
- Autres sections : frise du chargement, chronomètre lecture/génération déjà présents à
  enrichir de schémas (table d'embedding, fenêtre glissante, réflexion/réponse).

### Lot 5 — Atelier MCP : le protocole à manipuler
- But : une troisième page de focus, `/mcp`, sur le modèle de `/llm` (LLM nu) et `/rag`
  (Atelier RAG) : ce que fait *le protocole* entre le harnais et un serveur, sans l'atelier
  ni le modèle. Le stagiaire doit voir qu'un serveur MCP est un processus séparé, que le
  harnais lui parle en JSON-RPC, et ce que sa documentation pèse dans le contexte.
- Démarche (comme le lot 4) : lister les questions du stagiaire, y répondre par une
  manipulation visible. Sections proposées, dans l'ordre d'un échange réel :
  1. **Les serveurs** : les trois de `content/mcp.yaml` (glossaire local en stdio, data.gouv.fr
     et Microsoft Learn en Streamable HTTP), avec transport, adresse ou commande de lancement,
     et ce qui sort du poste (`sends_fr`). Bouton « Se connecter » par serveur.
  2. **La poignée de main** : `initialize` → réponse du serveur (nom, version, capacités) →
     `tools/list`, chaque message JSON-RPC affiché tel quel, sens harnais → serveur / serveur →
     harnais, avec sa durée. Un serveur public montre aussi l'`outbound_request` (adresse,
     en-têtes, corps), comme le volet Orchestration.
  3. **La documentation des outils** : pour chaque outil listé, son nom `{serveur}__{outil}`,
     sa description et son schéma d'arguments ; à côté, ce que cela pèse en tokens dans le
     contexte, serveur par serveur, en documentation complète et en lazy loading
     (`load_tool_doc`, une ligne par outil). C'est la jauge de la brique, sortie de l'atelier.
  4. **L'appel** : formulaire d'appel d'un outil (un champ par paramètre du schéma, préréglages
     `call_presets` de `content/mcp.yaml`), requête `tools/call` et résultat JSON-RPC bruts,
     puis le texte tel que le harnais le réinjecterait (`result_text`, bornage du lot B).
     Cas d'erreur à montrer : argument invalide (le serveur répond, `is_error`), serveur
     injoignable (`describe_error`), délai dépassé.
  5. **Ce que le modèle voit** : le bloc « outils » du contexte tel qu'il partirait au modèle
     avec les serveurs cochés, sans génération (comme la « Génération » non exécutée de
     l'Atelier RAG).
- Architecture, calquée sur les stories 29 et 30 (ARCHITECTURE-SPINE, AD-19, AD-24) :
  - `GET /mcp` sert `static/mcp.html` (+ `mcp.css`, `mcp.js`, `theme.js` en tête,
    `tokens.css` seulement) ; `GET /api/mcp_lab` donne `{servers, content, content_error_fr,
    last_session, session_state, seq}` ; la page lit `/api/stream` à partir de `seq` et ne
    garde que le contexte `mcp_lab` et `session_state`.
  - Intentions de classe (b), acceptées en `idle` seulement, nouvel état de session `mcp_lab`
    (« Atelier MCP : échange en cours ; attendez sa fin ou arrêtez-le. ») : `mcp_lab_connect
    {server}`, `mcp_lab_call{server, tool, args}` ; `stop` (classe c) ferme la connexion.
  - Bac à sable : l'atelier ouvre **ses propres** `McpConnection` (jamais celles de la brique,
    `_mcp_conns`), fermées à la fin de la page ou au `stop` ; il ne change ni `_mcp_enabled`
    ni `_mcp_lazy`. Le serveur local est relancé en processus enfant pour l'atelier (deuxième
    processus, coût nul en RAM notable). Les serveurs publics passent par `create_async_client`
    et la garde réseau (AD-15) ; hors ligne, la section 2 montre l'erreur, c'est aussi
    pédagogique.
  - Événements, contexte `mcp_lab` (`turn_id` nul, `step_id` `mcp{n}`, `brick = mcp`,
    `component = mcp_lab.{server}`) : `mcp_lab_message{direction: to_server|from_server,
    method, jsonrpc: str, elapsed_ms}`, `mcp_lab_connect_ended{server, status, tools:
    [{name, description, schema, doc_tokens}], full_tokens, lazy_tokens, error_fr}`,
    `mcp_lab_call_ended{server, tool, status, raw, text, truncated, error_fr, duration_ms}`.
    Point dur : le SDK `mcp` n'expose pas les messages JSON-RPC bruts ; à relever à
    l'implémentation (hook de transport, ou reconstruction depuis les objets `mcp_types`,
    dite « reconstitué » dans la page si c'est le cas).
  - Textes dans `content/mcp_lab.yaml` (pydantic, `extra = "forbid"`), déclinés dans
    `content/i18n/{en,de}/mcp_lab.yaml`. Les descriptions des outils viennent du serveur,
    dans la langue du serveur local.
- Navigation : la barre commune du lot 2 gagne « Atelier MCP » entre « Atelier RAG » et
  « Diagnostic » ; la carte de la brique MCP de l'atelier y renvoie (comme le bouton
  « Changer de modèle dans l'atelier » fait le chemin inverse pour le LLM nu).
- Tests : `tests/test_mcp_lab.py` (doublure de serveur en stdio, comme `test_mcp.py`), E2E
  `s_mcp_lab` avec captures 59+ (`59-atelier-mcp-poignee-de-main`, `60-atelier-mcp-appel`),
  `test_web_tokens`, `test_i18n` (nouveau fichier de contenu dans les trois langues).
- README : section « Atelier MCP » après « Atelier RAG ».
- Méthode : `/bmad-spec` pour la story (elle est de la taille de la 30), puis `/bmad-ux`
  pour DESIGN.md / EXPERIENCE.md, puis `/bmad-build`. Dépend du lot 2 (barre commune) ;
  indépendant des lots 3 et 4.

## 4. Réconciliation avec `feat/i18n-2`
La story Langues 2 renomme les champs `*_fr` dans le JS (déjà visible : `label_text`,
`title_text`). Les lots 2 à 4 touchent `app.js`, `llm.js`, `rag.js`, `models.html`,
`diagnostic.html`, exactement les fichiers des Langues 2 et 4. Ordre conseillé : lots 0 et 1
sur `main` tout de suite ; fusionner Langues 2 (renommage) avant d'ouvrir les lots 2 à 5,
ou les développer sur une branche rebasée sur `feat/i18n-2`. Sinon, conflits sur des milliers
de lignes. Le lot 5 crée surtout de nouveaux fichiers (`mcp.html`, `mcp.js`, `mcp.css`,
`content/mcp_lab.yaml`) : il doit naître directement avec les champs `*_text` et les trois
langues, jamais en `*_fr` à traduire ensuite.

## 5. Vérification de chaque lot
`uv run ruff check .`, `uv run pytest` en deux moitiés (PC à 16 Go), E2E par tranches
`--only`, puis recette à la main sur le PC, sur le bon port.
