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

## État en fin de séance

- `settings.json` identique à la sauvegarde : `language: "en"`, `selected_model: {kind: "cloud",
  ref: "gemma"}`.
- Serveur arrêté, port 8420 libre, onglet de test fermé.
- L'interrupteur des actions forcées est remis à faux (stockage local du navigateur).
- La conversation du scénario network_tools a été vidée pour pouvoir changer de langue. La
  mémoire globale n'a pas changé.
