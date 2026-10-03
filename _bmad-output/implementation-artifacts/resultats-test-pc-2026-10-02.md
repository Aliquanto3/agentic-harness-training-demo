# Résultats du test sur PC pro : story 1e et relecture de la nuit du 1er octobre (2026-10-02)

Poste : PC pro Windows 11 Enterprise 10.0.26200, `HTTPS_PROXY=http://127.0.0.1:9000` (proxy en
boucle locale), pas de proxy dans le registre. Branche `nuit/integration-2026-10-01`, commit
`e075ebe`, lancée par `uv run wavestack` depuis la racine du dépôt (`/api/health` : `"commit":
"e075ebe"`). Dossier de données réel (`%LOCALAPPDATA%\WaveStack`), `settings.json` sauvegardé
avant la séance. Pilotage par Claude in Chrome (extension reliée), sans Playwright. Aucun code
modifié.

Limite de la séance : l'écran disponible fait 1 280 × 672 px. À partir du test des clés cloud,
la fenêtre de Chrome est passée en arrière-plan (`document.visibilityState = "hidden"`) : les
captures sortaient blanches et les clics à la souris ne partaient plus. La suite a été jugée par
lecture du DOM, `element.click()` et les API du serveur (`/api/diagnostic`, flux
`/api/diagnostic/stream`). Les captures prises avant ce moment sont dans
`%TEMP%\claude-chrome-screenshots-sCuGBh\` (fichiers temporaires, non versionnés).

## Story 1e

| # | Geste | Attendu | Observé | Verdict |
|---|---|---|---|---|
| 1 | Scénario `network_tools`, prompt suggéré « What are the public holidays in France this year? », modèle cloud gemma | `public_holidays` contacté ; Orchestration montre les données sortantes | Tour en 7,9 s, 3 appels au modèle : `get_datetime`, puis `public_holidays(year=2026)`. Étape « Runs the tool outside the workstation · Public holidays », `🌐 NETWORK → calendrier.api.gouv.fr`, OK en 0,1 s. Bloc « NETWORK · Outbound data » : `GET https://calendrier.api.gouv.fr/jours-feries/metropole/2026.json`, en-têtes (User-Agent WaveStack), « No body: only the address leaves the workstation. » Résultat : 11 jours fériés. Schéma : nœud « Public holidays » `contacted`. Bandeau : « data left the workstation 4 times […] and to Public holidays (the requested year, 1 request) ». | OK |
| 2 | Atelier MCP (`/mcp`), Connect sur data.gouv.fr | Connexion et liste des outils | « data.gouv.fr: connection open in 530 ms · 10 tools listed ». `initialize` tracé comme « Outbound HTTP request (network guard) » `POST https://mcp.data.gouv.fr/mcp`. Outils : `search_datasets`, `search_organizations`, `search_dataservices`, `get_dataservice_info`, `get_dataservice_openapi_spec`, `query_resource_data`, `get_dataset_info`, `list_dataset_resources`, `get_resource_info`, `get_metrics` (préfixe `datagouv__`). | OK |
| 3a | Diagnostic, Test de Gemini (gemini-3.5-flash-lite) | Le test répond | « Test passed: Google AI Studio answers, 538 tokens/s. Tool call received: get_datetime. » | OK |
| 3b | Test de Gemma (gemma-4-26b-a4b-it) | Le test répond | « Test passed: Google AI Studio answers, 311 tokens/s. Tool call received: get_datetime. » | OK |
| 3c | Test de Groq (openai/gpt-oss-120b) | Le test répond | « Test passed: Groq answers, 682 tokens/s. Tool call received: get_datetime. » | OK |
| 3d | Test de Mistral (mistral-small-latest) | Message clair ; depuis D6, un 429 avec `x-ratelimit-limit-req-minute: 0` dit « aucun quota actif » | Message : « Test failed: Mistral AI refuses the call. No active quota on this account: check the plan in the provider's console. Provider's message: Rate limit exceeded ». Action : « Go back to the local model from the model selector in the top bar. » Journal : `outbound_request` (`POST https://api.mistral.ai/v1/chat/completions`, Authorization masqué), puis `model_call_ended` avec `stop_reason: "error"` en 288 ms, puis `diagnostic_check` `status: "fail"`. Le journal ne trace **ni le statut HTTP ni les en-têtes `x-ratelimit-*`**. Ce message ne peut sortir que d'un 429 dont `x-ratelimit-limit-req-minute` vaut `0` (`openai_chat.py:498`, `_no_quota`). | OK pour D6 ; voir R2 |
| 4 | Téléchargement Hugging Face (carte RAG) : démarrer, annuler, supprimer le partiel | La progression démarre, l'annulation ne laisse rien | Non fait. Le seul téléchargement de l'application concerne les modèles du RAG (`rag_embedding`, `rag_reranker`), et les deux fichiers sont déjà dans `%LOCALAPPDATA%\WaveStack\models` : rien à télécharger. Le renommage temporaire du reranker a été refusé par la garde de Claude Code (fichier de données réel). | Non testé |
| 5 | Second `uv run wavestack` pendant que le premier tourne | Message « déjà lancée » | « WaveStack is already running on port 8420, from C:\Users\anael.yahi\Documents\GitHub\agentic-harness-training-demo (e075ebe). Opening the browser. », code de sortie 0. | OK |

### Diagnostic vide au premier chargement (observation du 02/10)

Reproduit au premier lancement de la séance. `/diagnostic` ouvert environ 1 s après la première
réponse de `/api/health` : « Checks », « Models detected » et « Cloud models » sont restés vides
pendant plus de 12 s, puis la page s'est remplie toute seule.

Mesure de la page (Resource Timing) : `GET /api/diagnostic` part à 282 ms, avec une **première
réponse à 10 170 ms (9,9 s)**. Au même moment, `/api/state` répond en 38 ms. Les appels suivants
de `/api/diagnostic` prennent 0,04 à 0,05 s.

- **La page n'attend pas le flux.** Elle attend la réponse de `fetch("/api/diagnostic")`
  (`diagnostic.html:679`) avant de rendre ses trois sections. Le flux `/api/diagnostic/stream`
  ne s'ouvre qu'après.
- **C'est le serveur qui a mis 9,9 s à répondre à cette première requête.** Après un second
  lancement (arrêt puis relance pour S2), le premier `/api/diagnostic`, envoyé dès que
  `/api/health` répondait, a pris 0,043 s. Le phénomène n'a donc pas été reproduit au second
  lancement.
- Cause non établie. Hypothèse la plus probable : un coût de démarrage à froid du premier
  lancement après le changement de commit (imports paresseux, analyse antivirus des DLL ou des
  `.pyc`, tâches de démarrage comme la recherche de modèles ou le chargement de gemma). Pour
  trancher, il faudrait tracer la durée de `diagnostic_state` et de ses appels (`active_choice`,
  `cloud_rows`, `_models`) au prochain premier lancement.

Verdict : ce n'est pas un défaut de la page (elle n'attend pas le flux). C'est un temps de
premier calcul côté serveur, réel mais non reproduit. Défaut d'ergonomie associé (R1) : pendant
cette attente, la page n'affiche aucun indicateur de chargement.

## Relecture visuelle (modèle gemma)

| Point | Geste | Attendu | Observé | Verdict |
|---|---|---|---|---|
| D3 | Panneau des briques, interrupteur « Show the forced actions » | Section « Actions forcées » avec ✋ ; l'interrupteur déplie les listes qui ont un bouton Forcer | Section « FORCED ACTIONS » avec ✋ et le libellé « Show the forced actions ». Après activation : « Tools: 6 of 6 enabled » et « Skills: 6 of 6 enabled » dépliées (6 « Force the call », 6 « Trigger the skill ») ; « Servers » (MCP non lazy, sans appel) et « Hooks » restent repliées. Aussi « Write to memory » et « Delegate to the sub-agent » sur les cartes. Interrupteur remis à faux ensuite. | OK |
| D5 | Sous la réponse du tour 1 (outils utilisés), clic sur « Public holidays » | Ligne « Outils consultés pendant ce tour » ; le clic sélectionne l'étape dans Orchestration | « Tools consulted during this turn: Time and date, Public holidays ». Le clic sélectionne l'étape « Runs the tool outside the workstation · Public holidays » (`turn-step is-selected is-selection-linked`) et y fait défiler Orchestration. | OK |
| D7 | Tiroir de la mémoire globale (« Edit the memory ») | Date et heure d'écriture | « Entry 1 demonstration · 01/10/2026, 19:57 » (idem pour les entrées 2 et 3). | OK |
| S2/E003 | Arrêt du serveur (taskkill) puis relance | « Connexion perdue » dans la barre haute, puis effacé au retour | « Connection to the server lost, trying again… » dans le statut de la barre haute, environ 4 s après l'arrêt. À la relance, la page se recharge d'elle-même (nouvelle instance du serveur : `sameServerInstance`, `app.js:273`) et l'indicateur disparaît. Constat par lecture du DOM (fenêtre en arrière-plan). | OK |
| Singulier `/llm` | Découper « a » en tokens, en fr, en et de | « 1 token » au singulier | en : « ≈ 1 token (1 character, at 4 characters per token) » ; fr : « ≈ 1 token (1 caractère, à raison de 4 caractères par token) » ; de : « ≈ 1 Token (1 Zeichen, bei 4 Zeichen pro Token) ». Estimation du harnais (tokenizer de gemma distant). La langue ne change qu'avec une conversation vide (comportement voulu) : la conversation a été vidée pour ce test. | OK |
| Journal | Journal des événements après network_tools, atelier MCP, LLM nu, atelier RAG (« Kette starten »), changements de langue | Aucun nom technique brut | 190 lignes, 36 types, tous avec un libellé traduit : `consumption_updated` « Verbrauch aktualisiert », `context_window_state` « Kontextfenster », `rag_lab_run_started` « RAG-Werkstatt: Durchlauf begonnen », `rag_lab_stage_progress` « RAG-Werkstatt: Schritt läuft », `mcp_lab_message`, `llm_tokenized`, `effect_applied`, `language_changed`… Le type brut reste affiché en petit, en police à chasse fixe, après le libellé (« raw » assumé par le titre du journal). | OK |

## Défauts et remarques

- **R1 (ergonomie, mineur) : diagnostic sans indicateur de chargement.** Pendant les 9,9 s de
  la première réponse de `/api/diagnostic`, les sections « Checks », « Models detected » et
  « Cloud models » restent vides, sans texte d'attente. Preuve : relevé Resource Timing
  ci-dessus. Piste : un texte « Diagnostic en cours… » tant que la réponse n'est pas arrivée,
  et une trace de la durée de `diagnostic_state` pour trouver la cause.
- **R2 (pédagogie, mineur) : le refus de Mistral ne laisse pas sa preuve dans le journal.** Le
  message D6 est juste, mais ni le statut HTTP (429) ni les en-têtes `x-ratelimit-*` ne sont
  tracés : `model_call_ended` ne porte que `stop_reason: "error"`. Pour un démonstrateur qui
  montre ce qui sort du poste, une réponse d'erreur (statut et en-têtes de quota) aurait sa
  place à côté de `outbound_request`.
- **Demande d'Anaël (02/10, pendant la séance) : interpréter le Markdown de la réponse dans la
  Vue humain**, et seulement là (les autres vues gardent le texte brut). Aujourd'hui, la réponse
  s'affiche telle que le modèle l'écrit : « *   **January 1st:** New Year's Day… ». Aucun
  rendu Markdown n'existe dans `app.js`.
- **Remarque (non confirmée) : barre basse mal placée quand un volet est agrandi.** Orchestration
  agrandie, après un défilement vers le bloc des données sortantes, la barre basse (scénario,
  jauge, modèle) est apparue au milieu de la fenêtre, puis plus du tout après un nouveau
  défilement. Vu une fois, avec une fenêtre de 624 px de haut. À revoir sur un écran normal
  avant de conclure.
- **Vérification 4 à refaire.** Moyen sans toucher au dossier réel : lancer WaveStack avec
  `WAVESTACK_DATA_DIR` vers un dossier jetable dont `models\reranker` est vide (comme la séance
  du 29/09), puis lancer et annuler le téléchargement depuis la carte « RAG with reranking ».

## Suites (02/10, `spec-recette-2026-10-02-markdown-diagnostic-quota.md`)

- **R1, fermé.** `diagnostic.html` affiche « Diagnostic en cours… » (`diagnostic.loading`, fr,
  en, de) dans Contrôles, Modèles détectés et Modèles cloud jusqu'au premier rendu de chaque
  liste ; dans Contrôles, le texte part à la première ligne reçue par le flux. Côté serveur,
  chaque `GET /api/diagnostic` écrit une ligne de log : numéro de l'appel, total, attente avant
  le gestionnaire (middleware limité à la route), durée d'`active_choice`, `cloud_rows`,
  `_models` et `shown` en ms, temps écoulé depuis la création de l'application. En `debug`
  sous `SLOW_DIAGNOSTIC_S = 1.0`, en `warning` au-delà, donc visible dans la console de
  `uv run wavestack`. Aucun événement de journal. La cause des 9,9 s reste à lire dans cette
  ligne au prochain premier lancement lent.
- **R2, fermé.** Nouvel événement `outbound_response` (« Réponse d'erreur reçue »), émis par
  la fabrique HTTP (crochet `response` des clients synchrone et asynchrone) pour tout statut
  ≥ 400 d'un hôte hors de la boucle locale : `origin`, `method`, `url`, `status`, en-têtes dans
  l'ordre reçu. Seuls `content-type`, `content-length`, `date`, `retry-after` et les préfixes
  `x-ratelimit-` et `ratelimit-` restent en clair (`config.PUBLIC_RESPONSE_HEADERS`) ; le reste
  est masqué. Dans un tour Mistral : `outbound_request`, `outbound_response` (429, quota en
  clair), `model_call_ended` en erreur, puis le message D6, inchangé. Résumé du journal :
  `429 · POST url · x-ratelimit-limit-req-minute: 0, …`. Rien dans Orchestration.
- **Markdown dans la Vue humain, fait.** `static/markdown.js`, rendu maison construit nœud par
  nœud (jamais d'`innerHTML`), appliqué à la seule réponse finale : paragraphes, gras,
  italique, listes imbriquées, titres (h3 à h6), code en ligne et blocs de code, liens
  `http(s)` seulement. Le HTML du modèle, `javascript:`, les liens relatifs et les images
  restent du texte. Contexte LLM, Orchestration, le journal, la comparaison et l'annonce
  d'accessibilité gardent le texte brut.
- **Barre basse en mode focus, confirmé puis corrigé.** Reproduit par Playwright à 1280×672,
  1440×900 et 1280×624 : `.right`, en colonne sans `min-height: 0`, débordait du `body`.
  Correctif :
  `body.focus-mode .right:has(> .pane.is-focused, > .top-row > .pane.is-focused) { min-height: 0; }`.
  La règle ne s'applique que si le volet agrandi est dans `.right` : appliquée sans condition,
  elle faisait défiler la page de 108 px quand on agrandissait Briques (`.right`, de base 0,
  tombait à zéro et ses en-têtes repliés débordaient). Contrôle E2E dans `panes` : chaque volet
  agrandi, à 1280×672 et 1440×900 ; il échoue sans la règle (Vue humain, Contexte LLM et
  Orchestration).

## État en fin de séance

- `settings.json` identique à la sauvegarde : `language: "en"`, `selected_model: {kind: "cloud",
  ref: "gemma"}`.
- Serveur arrêté, port 8420 libre, onglet de test fermé.
- L'interrupteur des actions forcées est remis à faux (stockage local du navigateur).
- La conversation du scénario network_tools a été vidée pour pouvoir changer de langue. La
  mémoire globale n'a pas changé.

## Recette des suites sur le PC pro (02/10 au soir, commit `31ec98f`)

Pilotage par Claude in Chrome (extension reliée, fenêtre visible, 1 696 × 675 px de page),
`uv run wavestack` lancé depuis la racine du dépôt, console capturée dans un fichier. Dossier de
données réel ; `settings.json` sauvegardé avant et identique après (`en`, cloud `gemma`).

| Point | Geste | Observé | Verdict |
|---|---|---|---|
| R1, attente | `/diagnostic` ouvert dès la réponse de `/api/health` | À 1,3 s : « Diagnostic en cours… » dans les trois listes, aucun `/api/*` encore répondu. Puis `/api/ui_texts` en 515 ms, `/api/diagnostic` en 252 ms ; les listes se remplissent. | OK |
| R1, mesure | Console du serveur | Une seule ligne : `/api/diagnostic n° 2 : 14719 ms au total (attente avant le gestionnaire 3 ms ; active_choice 0 ms, cloud_rows 13 ms, _models 14700 ms, shown 2 ms), 27.3 s après la création de l'application`. Les appels suivants : 75 à 88 ms. | OK, cause localisée |
| R2 | Diagnostic, « Test » de Mistral | Message D6 inchangé (« No active quota on this account… Rate limit exceeded »). Journal : `outbound_request` (Authorization masqué), `outbound_response` 429 avec `x-ratelimit-limit-req-minute: 0` et `x-ratelimit-remaining-req-minute: 0` en clair, 15 autres en-têtes masqués (`set-cookie`, `mistral-correlation-id`, `CF-RAY`…), puis `model_call_ended` en erreur. Journal de la page : « Error response received » · `429 · POST https://api.mistral.ai/v1/chat/completions · x-ratelimit-limit-req-minute: 0, x-ratelimit-remaining-req-minute: 0`. | OK |
| Markdown | `network_tools`, « What are the public holidays in France this year? » (gemma) | `p` puis `ul` de 11 `li`, dates en `strong` : plus aucun `*   **…**` brut. | OK |
| Markdown | Deux questions sans outil (titre, liste numérotée, code) | `h3`, `ol` de 4 étapes, `code` en ligne, `pre > code` ; le Contexte LLM garde `**` et les clôtures de code. Pendant le flux, la `.bubble-text` du tour ne disparaît jamais (21 lots de mutations) et le rendu progresse (liste, puis code, puis bloc). | OK |
| Mode focus | Orchestration agrandie, défilement vers le bloc « Données sortantes » (lien « Public holidays » du tour 1), molette (10 crans), Fin | Seul Orchestration défile (jusqu'à 1 043 px) ; `scrollTop` de la page à 0, hauteur du document égale à la fenêtre, barre basse à 612 px (bas de la fenêtre). Briques, Vue humain et Contexte LLM agrandis : idem. | OK |

**Cause de R1, localisée par la mesure.** Le temps se passe dans `_models`
(`catalog.models_payload`), au premier appel qui suit la fin de la recherche des modèles
(appel n° 2, après le contrôle `model`), puis plus jamais. Ni l'attente d'un thread, ni
`active_choice`, ni `cloud_rows`. Le 02/10 au matin, la page s'était ouverte après la fin de la
recherche : c'est sans doute pourquoi le premier appel portait les 9,9 s. Prochaine étape :
mesurer l'intérieur de `models_payload` (par candidat : lecture des métadonnées GGUF, éditeurs,
fenêtres) avant tout correctif.

Reste à faire : la vérification 4 (téléchargement HF avec un `WAVESTACK_DATA_DIR` jetable).

## Cause de R1 mesurée et corrigée, vérification 4 (02/10, nuit, commit `a263d30`)

**R1.** Spec `spec-r1-lenteur-models-payload.md` (`done`). La ligne de log R1 détaille désormais
`_models` : `load_publishers`, `local_entries` (avec `headers` et chaque candidat d'au moins
1 ms : lecture d'en-tête + reste), `cloud_entries`, `group_models`. Reproduit sur ce PC avec le
vrai serveur (`uv run wavestack` sans navigateur, dossier de données réel, 39 candidats dont
21 fichiers GGUF distincts, Ollama compris) :

| Premier `/api/diagnostic` après la recherche | Total | `_models` | dont en-têtes GGUF | Appel suivant |
|---|---|---|---|---|
| Avant (`d1ea42b` + instrumentation) | 21 009 ms | 20 988 ms | 20 893 ms (0,3 à 2,2 s par fichier) | — |
| Après (`a263d30`) | 1 753 ms | 1 368 ms | 1 186 ms (attente du préchauffage) | 54 ms |

Cause : `gguf_meta.read_metadata` sautait le vocabulaire et les fusions du tokenizer chaîne
par chaîne (environ 500 000 lectures par fichier), une fois par lancement (cache en mémoire).
Deux requêtes concurrentes (dont un onglet Edge resté ouvert sur 8420) relisaient chacune tous
les en-têtes : d'où 21 s ici et 14,7 s pendant la recette. Correctif : saut par blocs (3 fois
plus rapide), préchauffage des en-têtes en arrière-plan dès que la recherche connaît ses
candidats, lectures sérialisées (une requête attend le fichier en cours au lieu de le relire).
Le reste (1,2 s) n'apparaît que si toutes les sondes sont en cache : la recherche finit alors
juste après la découverte, avant la fin du préchauffage. Un cache des en-têtes sur disque le
supprimerait (non fait).

**Vérification 4 (téléchargement Hugging Face).** `WAVESTACK_DATA_DIR` vers un dossier jetable
du scratchpad (`settings.json` et modèle d'embedding copiés, `models\reranker` vide, sans clés),
serveur sur le port 8421. Le cloud gemma n'ayant pas de clé, le modèle choisi a été
`granite4:350m` (Ollama) pour atteindre l'état `idle`. Pilotage par Claude in Chrome ; la
fenêtre est passée en arrière-plan, donc clics par `element.click()`.

| Geste | Observé | Verdict |
|---|---|---|
| Carte RAG, « Download the reranking model (≈ 438 MB) » | Le chemin indiqué est celui du dossier jetable. État `download`, « Downloading the reranking model: 4% (21 / 438 MB) » à 5 s, puis 22 % (101 / 438 MB) ; `bge-reranker-v2-m3-Q4_K_M.gguf.part` de 73 Mo sur le disque ; bouton Stop actif. | OK |
| Stop | État `idle` ; `models\reranker` vide (le `.part` est supprimé) ; le bouton de téléchargement revient. Message de la carte : « Download of the reranking model stopped. Cause: download stopped. Nothing is installed. To continue, copy the file by hand into … then click “Download” again. » | OK |

- Onglet masqué : la carte est restée sur « 22 % » et « Stop the download » jusqu'à ce que
  l'onglet redevienne visible. Le rendu passe par `requestAnimationFrame`, suspendu dans un
  onglet masqué. Ce n'est pas un défaut de l'application.
- **R3 (ergonomie, mineur).** Un arrêt volontaire s'affiche en rouge, comme un échec
  (« Cause: download stopped »), avec la consigne de copier le fichier à la main. Un arrêt
  demandé pourrait dire seulement « Téléchargement arrêté, rien n'est installé ».
- Dossier de données réel non touché (`settings.json` du 02/10 à 07:43, reranker présent).
