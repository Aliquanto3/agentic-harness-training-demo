# Résultats du test sur PC cible : stories 22 à 27 et 31 à 34 (2026-09-29)

Poste : Windows 11 Enterprise 10.0.26200, PowerShell 5.1, sans droits d'administrateur, CPU
seul, 16 Go. Commit testé `3ed8482` (code de `175eb5a` et cahier de recette), tête détachée,
arbre propre. Consigné au fil de l'eau par Claude Code ; aucun code du dépôt modifié.

Dossier de données jetable : `<scratchpad>\wsdata` (copie de `settings.json`, `api_keys.json`,
`memory.json`, `audit.log` ; `models` en jonction vers `%LOCALAPPDATA%\WaveStack\models`).
Tous les lancements de WaveStack de cette séance passent par `WAVESTACK_DATA_DIR` vers ce
dossier : le dossier réel n'est pas touché.

État du dossier réel avant la séance (lecture seule) : `settings.json` 9 272 octets, empreinte
`FA634B52…`, **6 « Ã/Â »** (six raisons de `failed_probes` écrites en double encodage
`ab\xc3\xaem\xc3\xa9`, soit « abÃ®mÃ© »). Fenêtre, budget et modèle non réglés (`context`,
`memory` absents). Modèles : Qwen3.5-2B (1 280 835 840 o), Qwen3.5-4B (2 740 937 888 o),
embedding et reranker. Ollama lancé (processus `ollama`). llama-server absent du PATH.
Processus au début : Edge ouvert, Outlook et Teams fermés.

## Plan de vérification

Chaque test du cahier est rangé selon le moyen qui le juge le mieux. « Edge » veut dire que la
partie Edge du test reste à la main : Claude in Chrome et Playwright passent par Chrome ou
Chromium.

| Moyen | Tests |
|---|---|
| **Script** (`AppSession` hors dépôt, vrai Qwen3.5-2B, journal, RSS) | N22-6 (turn_id) ; N23-1 (vrai appel Wikipédia, User-Agent), N23-2 (clé Groq), N23-3 (en-têtes data.gouv.fr) ; N24-1, N24-3, N24-4, N24-5, N24-6, N24-7, N24-8 ; N25-2 (capacités face aux cartes), N25-3, N25-4, N25-5, N25-6 ; N26-1 à N26-7 ; N27-1 à N27-9 ; N32-2, N32-4 (octet pour octet) ; N33-4 (lignes d'état face aux sections) ; N34-2, N34-3 (bilan face au journal) |
| **pytest / E2E** | étape 1 ; N27-9 (`-k fits`) |
| **Playwright** (vraie application, Chromium) | mises en page 1 280, 1 366, 1 440, 1 600 px, normal et projection (N26-8, N34-4 partie « une ligne », N32-6 partie 1 366) ; balayage des contrastes axe-core, la règle même de Lighthouse, clair et sombre (N33-5, N31-7 hors Edge) ; captures de chaque volet dans les deux thèmes ; N31-8 (mémorisation, console) ; N34-5 approché (`prefers-reduced-motion`) ; N31-2 approché (bascule `prefers-color-scheme` émulée) ; N31-4 approché (première image après F5) ; N32-5 approché (tâches longues pendant le flux) |
| **Claude in Chrome** (écran réel de Chrome) | N22-1 (Chrome), N22-3, N22-5 ; N33-0, N33-3 ; N23-1 (Chrome) ; N34-0, N34-1 (éclairage, sans le CPU humain) ; N32-0, N32-3, N32-6 ; N25-1 (Chrome), N25-7 ; N26-1 (panneau), N26-8 (Chrome) ; N31-0, N31-1 (Chrome), N31-3, N31-5 |
| **Humain seulement** | P7 (Windows) ; N22-2 (zoom et place réelle à l'écran, préparé) ; N22-4 et N34-6 (Narrateur) ; N33-1, N34-4, N31-6 (3 m, projecteur, Teams) ; N33-2, N23-4, N27-10 (novice ou autre personne) ; N33-6 (thème de contraste Windows) ; N34-5, N31-2 (réglages Windows réels) ; N32-1 (chronomètre et avis) ; N24-2 (Edge et Teams ouverts exprès) ; toutes les parties Edge ; N32-5 et N31-4 dans les DevTools d'Edge |

Ordre d'exécution : tests automatiques (étape 1) ; script sur les vrais modèles (mesures, après
fermeture d'Edge, Outlook et Teams) ; Playwright ; Claude in Chrome ; préparation des gestes
humains.

**Correctif du plan (réponse d'Anaël, 2026-09-29)** : l'extension Claude in Chrome de ce poste
pilote **Edge 154** (`navigator.userAgent` … `Edg/154.0.0.0`, échelle 150 %, onglet de
871 × 506 px CSS), et non Chrome. Les gestes faits par Claude in Chrome valent donc pour les
parties **Edge** du cahier ; les parties « Chrome » passent par le Chromium de Playwright
(`chromium-1194`), qui n'est pas Google Chrome. Mesures : Edge reste ouvert sur l'onglet de
l'extension (accord d'Anaël), Outlook et Teams fermés ; chaque mesure le rappelle. Anaël accepte
le téléchargement de llama-server (P5) et les appels à Groq et Mistral pour les tests qui les
demandent. WaveStack est lancé sans ouvrir de navigateur (`webbrowser.open` neutralisé), avec
le dossier de données jetable.

## Préparation

| Test | Commande ou geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| P1 | `git status`, `git log -1` | commit à tester | tête détachée sur `3ed8482` (au lieu de `175eb5a` du cahier : même code, plus le cahier), arbre propre | OK | PowerShell |
| P2 | copie du dossier de données | sauvegarde avant tout lancement | dossier réel **non utilisé** : copie jetable `<scratchpad>\wsdata` (4 fichiers et jonction `models`). Compte « Ã/Â » du réel : **6**, empreinte `FA634B52…` | OK (équivalent) | PowerShell |
| P5 | bloc « Installation » du cahier | `llama-bNNNNN-bin-win-cpu-x64.zip` | **échec du bloc** : `releases/latest` pointe sur `v0.5.0` (2026-09-23), dont le seul fichier est `nightly-tag.txt` ; `$asset` vide. Les builds `bNNNNN` restent publiées à côté (dernière : `b11243`, 2026-09-29) | KO (cahier) | PowerShell |
| P5 | bloc « Repli » (`b11239`) | version affichée, sans élévation | 19 160 190 octets, décompressé dans `%LOCALAPPDATA%\llama.cpp\b11239`, `version: 0.5.0-dev (build 11239, commit 66e665c42)`, code 0, aucune élévation, ni AppLocker ni SmartScreen, pas d'erreur de DLL | OK | PowerShell |

## Étape 1 : tests automatiques (en cours)

| Test | Commande | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| lint | `uv run ruff check .` | propre | « All checks passed! » | OK | PowerShell |
| format | `uv run ruff format --check .` | propre | « 143 files already formatted » | OK | PowerShell |
| pytest | `uv run pytest -q` (07:26 à 07:39) | 1 194 passés | **1 194 passed, 3 skipped, 6 deselected in 819.92s (0:13:39)**, code 0 | OK | pytest |
| pytest `-m model` | `WAVESTACK_TEST_GGUF` = 2B, `WAVESTACK_TEST_MODELS_DIR` = dossier des modèles ; `uv run pytest -q -m model -rA --durations=0` | 6 réussis | **6 passed, 1197 deselected in 74.12s**. Durées : cache entre deux tours 35,8 s ; sonde réelle 18,4 s ; embedding 7,1 s ; état restauré 4,5 s ; reranker 3,4 s ; contrôles 4 et 6 2,6 s | OK | pytest |
| pytest Windows | `WAVESTACK_TEST_WINDOWS_FILES=1 uv run pytest -q -rs` | vert | **1194 passed, 3 skipped, 6 deselected in 465.16s** ; sauts : `test_rag_rerank.py:579` et `test_rag_review.py:340` (« Windows refuse de remplacer un fichier qu'une connexion tient ouvert »), `test_rag_review.py:503` (« simulation sans /proc ») : les mêmes que le 27/09 | OK | pytest |
| E2E | `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` (318 s) | 0 FAIL (609 PASS dans le conteneur) | **609 réussies, 1 en échec**, code 1. FAIL `[linked_view]` « 1280 × 720 en mode projection : barre sur une ligne, « Réinitialiser » entier, « · lié » lisible sur la puce » : Réinitialiser visible, rien ne déborde, mais **puce « ● + Contexte LLM · lié » coupée de 8 px**. Les autres contrôles de largeur passent (barre sur une ligne à 1 280, 1 440 et 1 600, sélecteur compact). 5 `harness_error` voulus (429, 500, flux cassé, 401, téléchargement d'embedding) ; console : 2 × `ERR_FAILED`, 1 × `ERR_CONNECTION_RESET`, attendus avec le réseau coupé du parcours | **KO (Windows)** | E2E |
| E2E, arbre | `git restore tools/e2e/screenshots` | arbre propre | 51 captures réécrites par le parcours, restaurées ; captures 35, 36, 39 copiées dans `<scratchpad>\e2e-shots` | OK | PowerShell |

**Point d'arrêt (07:36)** : Anaël doit éteindre le poste. Rien d'autre ne tourne (ni WaveStack,
ni llama-server). pytest a fini à 07:39. Reprise à 07:55 (poste resté allumé) : étape 1 terminée à 08:10. llama-server `b11239` reste installé dans `%LOCALAPPDATA%\llama.cpp`, et le dossier
jetable `<scratchpad>\wsdata` a une jonction `models` (à retirer par `cmd /c rmdir`, jamais par
une suppression récursive).

## Étape 3 : vraie application et vrais modèles, pilotées par script

Outils (tous dans `<scratchpad>`, hors dépôt) : `launch.py` lance `wavestack.cli.main` sans
navigateur, consigne chaque événement du journal dans `runN\events.jsonl` et chaque prompt
réellement passé à un moteur (`LlamaCppEngine`, `OllamaRawEngine`, `LlamaServerEngine`,
`OpenAIChatEngine`) dans `runN\prompts.jsonl`. `ws.py` pilote l'application par son API HTTP
(`/api/intentions/*`, `Origin` posé), attend l'état `idle` et résume chaque tour ; `n32.py`
compare « Texte exact » au prompt envoyé.

**Incident de préparation** : la jonction `wsdata\models` a disparu entre 07:55 et 08:11
(pendant les tests automatiques ; aucune ligne du dépôt ne retire de jonction, cause non
trouvée). Le vrai dossier des modèles est intact (4 fichiers, tailles et dates inchangées).
Conséquence du premier lancement (run1, 08:11) : la découverte n'a pas vu le dossier des
modèles (38 candidats, pas de `Qwen3.5-4B-Q4_K_M.gguf` ; le 2B venait du choix enregistré).
Remplacée à 08:22 par un vrai dossier de **liens physiques** (`mklink /H`, sans droits
d'administrateur ; supprimer un lien n'efface jamais l'original) ; chemins de `probed_models`
et `selected_model` du `settings.json` jetable réécrits vers ce dossier. Run2 : 39 candidats,
4B présent, aucun doublon du 2B.

Conditions des mesures : Edge ouvert (27 processus, 2 074 Mo à 08:11, onglet de
l'extension seul), Outlook et Teams fermés, Ollama lancé sans modèle chargé.

| Test | Commande ou geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| N24-1 | lancement ; ligne `memory` du diagnostic ; `psutil.virtual_memory()` juste avant | budget = min(4 096 ; 0,6 × disponible) à 5 % près | run1 : « RAM du poste : 16 064 Mo, dont 6 250 Mo disponibles au lancement. Budget mémoire de WaveStack : 3 750 Mo (60 % des 6 250 Mo … sous le plafond [memory] budget_mb de 4 096 Mo) » ; PowerShell 6 342 Mo → 3 805 Mo (écart 1,5 %). Run2 : 6 324 Mo → **3 794 Mo** ; PowerShell 6 434 → 3 860 (écart 1,7 %) | OK | script |
| N24-2 | même ligne, RAM disponible sous 6 827 Mo (Edge ouvert) | budget sous 4 096, avertissement | statut `warn`, « La RAM disponible limite le budget sous son plafond : fermez des applications puis relancez WaveStack. » (Edge ouvert, pas Teams) | OK (partiel : Teams fermé) | script |
| N24-4 | `select_model` du 4B, 2B actif | refus chiffré, 80 ≤ N ≤ 400, proche (± 100 Mo) de la RSS après libération | 409 « Changement refusé : Qwen3.5-4B-Q4_K_M demande environ 4,4 Go ; WaveStack occupe **119 Mo** sans le modèle actif, pour un budget de 3,7 Go (= 60 % des 6,2 Go de RAM disponibles au lancement). Qwen3.5-2B-Q4_K_M reste actif. … » ; `harness_error` « Rien n'est libéré ni écrit. » ; 2B toujours actif. RSS mesurée par script (`AppSession` dans le processus : 2B chargé, un tour, puis `_release()`) : **109 Mo** après libération (2 042 Mo avant), écart 10 Mo | OK | script |
| N25-4 | `Measure-Command` sur `/api/diagnostic`, 3 fois | < 2 s au 1er, < 200 ms au 2e | run2 : serveur prêt 2,3 s après le lancement ; les appels avant la fin du diagnostic répondent en 27, 4, 19 ms (ils rendent le résultat précédent, vide) ; résultat complet (39 candidats) 4,5 s plus tard ; ensuite **17, 16, 18 ms**. Run1 : 128 ms puis 26 et 24 ms. La lecture des en-têtes se fait dans le fil du diagnostic, pas dans la requête : le critère « 1er appel < 2 s » est tenu, et la lecture complète de 39 GGUF prend moins de 7 s lancement compris | OK | script |
| N22-6 | Réinitialiser ; « Bonjour », « Merci », « Au revoir » ; Réinitialiser ; « Bonjour » ; Vider la conversation ; « Bonjour » | `turn_id` uniques, t4 puis t5 | `turn_started` : t1 Bonjour, t2 Merci, t3 Au revoir, **t4** Bonjour, **t5** Bonjour ; jamais deux fois le même. Affichage « Tour 1 » et infobulles : à l'écran (étape 5) | OK (journal) | script |
| N32-2 (2B) | « Outils natifs », « Quelle heure est-il ? » (t6) ; `n32.py` compare la jointure des segments de `context_rendered` aux octets de `token_pieces(prompt_ids)` passés à `LlamaCppEngine.complete` | égalité octet pour octet ; Σ sections = lus | appel 1 : 3 075 octets, sha256 `55789a3f0769…` des deux côtés, **IDENTIQUE**, 729 ids ; Σ sections 729 = lus 729 (`usage_source` engine), écart 0. Appel 2 : 3 279 octets **IDENTIQUE**, 788 = 788, écart 0. Début `<\|im_start\|>system\n# Too…`, fin `…assistant\n<think>\n\n</think>\n\n` | OK | script |
| N26-1 | après t6 (appel 1 : 729 tokens évalués en 19 548 ms), `context_window_state` | cache = `kv_bytes_per_token` × fenêtre ; temps à ± 20 % | débit affiché 37,3 tokens/s = 729 / 19,548 s. Choix : 4 096 « Cache de contexte : 192 Mo », 109,8 s ; 8 192 « 384 Mo », 219,7 s ; 16 384 « 768 Mo », 439,3 s ; tous « tient ». Calcul : 49 152 × fenêtre = 192 / 384 / 768 Mio ; fenêtre / 37,3 = 109,8 / 219,7 / 439,3 s : **égalité exacte**. Texte : « Temps de lecture : au moins ≈ 1 min 50 s, au-delà des 30 s visées au premier token (NFR-1) » | OK | script |
| N26-2 | `context_window` 8 192, puis un tour | rechargement ≤ 30 s ; conversation gardée ; `{'window': 8192}` ; hausse de RSS à ± 30 % de l'écart annoncé (192 Mo) | rechargement **2,2 s** (puis 2,1 et 3,0 s), `model_load_ended` « Fenêtre de contexte : 8 192 tokens (conversation gardée). » ; le tour suivant relit l'échange précédent (829 tokens, réponse juste) ; `settings.json` jetable : `{'window': 8192}`. Mémoire, même conversation, après un tour : 4 096 → RSS 2 074 Mo, privé 2 418 Mo ; 8 192 → RSS 2 122 Mo, privé 2 479 Mo : **+48 Mo (RSS), +61 Mo (privé)** pour **192 Mo annoncés** | **KO** (coût surestimé × 4) | script |
| N26-2, cause | métadonnées GGUF (`VocabTokenizer`) et `probe.kv_bytes_per_token` | — | 2B : `block_count` 24, `head_count_kv` **2 (un seul entier)**, `key_length` = `value_length` = 256, **`full_attention_interval` 4**. La formule compte 2 × 24 × 2 × 512 = 49 152 octets par token ; seules 6 couches sur 24 (une sur quatre) ont un cache d'attention : **12 288 octets par token**, soit 48 Mo à 4 096 et 96 Mo à 8 192, ce qui cadre avec la mesure. 4B : 32 couches, `head_count_kv` 4, même intervalle : 131 072 annoncés, 32 768 réels | anomalie A2 | script |
| N26-3 | `context_window` 16 384 (rechargement 2,2 s) ; « MCP en documentation complète » + `mcp_server` mslearn (trois serveurs `ok` : datagouv, local, mslearn) ; prompt suggéré (t10) | pas de débordement ; premier token face au temps annoncé ; noter > 30 s | `context_rendered` **4 042 / 15 872**, `overflow` False (à 4 096, 4 042 > 3 584 utilisables : débordement). Appel 1 : **`prompt_ms` 117 241** (4 042 tokens évalués, soit 34,5 tokens/s), appel de `local__define_term({"term": "MCP"})` ; appel 2 : 2 132 ms (70 évalués). Réponse : « **MCP** signifie **Model Context Protocol**. … ». Temps annoncé pour 16 384 : 439,3 s (« au moins ≈ 7 min 19 s ») ; pour 4 042 tokens au débit mesuré : 108 s, mesuré 117 s. **Premier token à 120 s, au-delà des 30 s de NFR-1** (attendu, et annoncé par le panneau) | OK (NFR-1 dépassé, annoncé) | script |
| N25-2 (tableau) | `/api/diagnostic` → `models.groups` | 2B et 4B : outils oui, raisonnement activable ; llama3.2:3b : outils non avec raison, jamais ; Groq : toujours, 120B ; Mistral : activable | Qwen3.5-2B : « oui (qwen3_coder) », « activable » (« variable enable_thinking du gabarit ») ; Qwen3.5-4B (run2) : présent dans le groupe Qwen ; llama3.2:3b (fichier et Ollama) : « non », « aucun format d'appel connu pour cette famille de modèle », « jamais » ; Groq gpt-oss-120b : « toujours », « 120B », fenêtre 4 000 (« moitié du quota de tokens par minute ») ; Mistral small : « oui (déclaré) », « activable ». Comparaison avec les cartes après chargement : plus bas (Ollama, Groq, Mistral) | OK (tableau) | script |
| N25-1 (ordre, données) | `models.groups` | Qwen puis Llama ; 2B avant 4B ; légende ; rien de Qwen, Llama, Gemma dans « Autres éditeurs » | 12 groupes : Qwen, Llama, Gemma, Granite, Phi, Mistral, LFM, Nemotron, MiniCPM, Autres éditeurs, puis Réseau · Mistral, Réseau · gpt-oss. Qwen : 0,8B, 2B (fichier WaveStack), 2B (blob), 2B Ollama, 4B (fichier WaveStack), 4B (blob), 4,7B Ollama, bonsai 8,2B. « Autres éditeurs » : olmo-3 seul. Légende : « Légende : « Local » ou « RÉSEAU » dit où tourne le modèle, puis vient qui le sert (fichier, Ollama, llama-server ou fournisseur cloud). » Rendu dans les navigateurs : étape 5 | OK (données) | script |
| N25-5 | lignes « inconnu » du tableau | raison compréhensible, aucune ligne vide, aucun Traceback | 13 lignes « inconnu » : « Ce fichier GGUF ne contient pas de gabarit de conversation (tokenizer.chat_template) : WaveStack ne peut pas construire le prompt. Choisissez un autre modèle. » (blobs Ollama de ministral-3, lfm2.5-thinking, nemotron-3-nano, olmo-3) ou « llama-cpp-python 0.3.35 ne sait pas charger ce fichier (architecture non prise en charge, fichier incomplet ou abîmé). … » ; aucune raison vide ; aucun `Traceback` dans `run1-server.log` ni `run2-server.log` | OK | script |
| N24-8 | raisons des 6 `failed_probes` abîmées (« abÃ®mÃ© » dans `settings.json`), lues par l'API | accents justes à l'affichage, `settings.json` non réécrit | `tools_reason_fr` et `reason_fr` : « … fichier incomplet ou **abîmé** … » ; `settings.json` jetable : toujours **6** « Ã/Â » après deux lancements (entrées non réécrites) | OK (API ; affichage à l'écran à l'étape 5) | script |
| N27-4 (complet) | « MCP en documentation complète », fenêtre 4 096, prompt suggéré (t11) | `local__define_term` appelé ; « Model Context Protocol » dans la réponse | jauge 3 227 / 3 584 ; `local__define_term({"term": "MCP"})` trigger model ; réponse « MCP signifie **Model Context Protocol** (Protocole de contexte du modèle). … » ; tour 127,6 s (`prompt_ms` 108 485) | OK | script |
| N27-4 (lazy) | « Lazy loading », prompt 1 (t12) | `load_tool_doc` puis `local__define_term` ; « Model Context Protocol » | `load_tool_doc({"tool": "local__define_term"})` puis **aucun appel de `local__define_term`** : réponse de tête « MCP est une abréviation pour **Machine Learning** ou **Machine Control** … » ; tour 47,1 s | **KO** | script |
| N27-3 | « Skills », prompt suggéré (t13), Edge ouvert | `load_skill` au premier tour, jamais `load_tool_doc` | appel 1 : `load_skill({"skill": "meeting_minutes"})` trigger model ; aucun `load_tool_doc` ; tour **61,1 s**. Puis le modèle lit `notes_reunion.txt` (non demandé) et rédige le compte rendu **de ce fichier** (Alice, Bruno, Chloé, salle Rivoli) au lieu de la réunion du prompt (Paul, Julie, lundi 10 h) | OK (critère) ; remarque sur le contenu | script |
| N27-8 | « Compression du contexte », brique Compression éteinte, prompt 1 (t14) | `read_file(journal_serveur.log)` trigger model au premier essai ; jauge < 3 584 | `read_file({"path": "journal_serveur.log"})` trigger model, h1 allow ; jauge après lecture **3 206 / 3 584** ; réponse « La sauvegarde a échoué car le disque `/srv/archives` était plein, ce qui a empêché le copie du lot 58. … » ; tour 101,2 s ; secours non utilisé | OK | script |
| N27-7 | « Métier SOC », prompts 1 et 2 (t15, t16) | prompt 1 : `alertes_siem.log` ; prompt 2 : `hook_decided h1 block`, réponse avec « analyste » ou « habilité » | prompt 1 : `read_file({"path": "alertes_siem.log"})`, nom exact, h1 allow ; mais la réponse atteint la réserve de sortie (**512 tokens, `stop_reason` length, tour `limit`**, 80,9 s). Prompt 2 : `prefix_not_reused` cause **abandoned** ; le contexte (396 tokens) ne contient plus le premier échange ; **aucun appel d'outil, aucun h1** ; réponse « … Pourriez-vous me fournir le contenu de ce fichier ou le nom de votre fichier contenant les informations sur les comptes ? » ; ni « analyste » ni « habilité » | **KO** | script |
| N27-2 | « Où vont mes données ? » sans rien cocher, prompt (t17) | MCP actif (local, data.gouv.fr, lazy) ; `load_tool_doc` puis `datagouv__search_datasets` ok, ≤ 1 200 tokens | connexions `datagouv` et `local` ok ; `load_tool_doc({"tool": "datagouv__search_datasets"})`, puis `datagouv__search_datasets({"query": "qualité de l'air"})` **ok**, `truncated` **1 140** tokens gardés sur 2 526 ; `outbound_request` POST `https://mcp.data.gouv.fr/mcp` avec User-Agent WaveStack ; réponse (vrais jeux, avec leurs identifiants) coupée par la réserve de 512 tokens (tour `limit`) ; 145 s. Affichage du flux dans le schéma et Edge : étape 5 | OK (critère) | script |
| N27-5 | « Métier IAM », prompts 1 et 2 (t18, t19) | ≥ 1 appel par prompt ; ≤ 1 200 tokens ; aucun « Contexte dépassé » ; liens cités | prompt 1 : 1 appel `mslearn__microsoft_docs_search`, 1 153 tokens gardés sur 5 383, réponse sans **aucun lien** `learn.microsoft.com` ; prompt 2 : 1 appel, 1 153 sur 5 222, puis **`context_overflow` 3 967 / 3 584** (« Cause : l'historique de la conversation occupe la plus grande part du contexte »), tour `overflow` | **KO** | script |
| N27-6 | « Métier Souveraineté », prompt 1 (t20, t26), puis secours (armer `tool_doc` datagouv__search_datasets et rejouer, t27) | `datagouv__search_datasets` ok au prompt 1 | trois essais : chaque fois `load_tool_doc` (ou armé), **jamais `datagouv__search_datasets`** ; réponses inventées (« CyberArk », « INSECURE », « Cybersecurity France »…) ; aucune requête sortante vers data.gouv.fr pendant le tour | **KO** | script |
| N27-1 | « Sous-agent » (RAG et Raisonnement éteints), 4 prompts (t21 à t24) | délégation au prompt 1 ; quiz sans redélégation ; `prompt_ms` du 1er appel de chaque quiz < 15 000 ; pas de cause history | t21 : `delegate` trigger model, sous-agent `read_file(guide_harnais.md)`, résumé en cinq points, tour 174,8 s ; **un seul `subagent_started`** (t21). Quiz : `prompt_ms` **2 873 / 3 130 / 2 640** (101, 99, 98 tokens évalués), tours 14,2 / 11,2 / 14,6 s ; **aucun `prefix_not_reused`** après t21 ; réponses plausibles (bornes : durée, hooks) | OK | script |
| N27-9 | `WAVESTACK_TEST_GGUF` = 2B ; `uv run pytest -s -rA tests/test_program.py -k fits` | réussi ; `mcp_full` tient ; marges positives | **1 passed** en 13,6 s. Tableau (utilisés / utilisables, marge) : `mcp_full` **3 204 / 3 584, marge 380** (la plus petite), `network_tools` 1 031 (marge 2 553), `subagent` 1 334 (2 250), `skills` 1 311 (2 273), `iam` 1 062 (2 522), `soc` 345 (3 239), `reasoning` 10 / 2 560. Cohérent avec la jauge réelle de t11 (3 227 avec le prompt). Le test ne couvre que le premier prompt : le second prompt d'IAM déborde (N27-5) | OK | pytest |
| N24-6 | `ollama ps` vide ; `OLLAMA_NUM_PARALLEL` et `OLLAMA_KV_CACHE_TYPE` vides (défauts) ; `select_model` « Local · Ollama · llama3.2:3b » ; « Bonjour » (t28) | pas de refus ; SIZE à ± 30 % de l'estimation | candidat `served_bytes` **2 489 139 424** (≈ 2,3 Go) ; chargé en 3,1 s, aucun refus ; `ollama ps` : **2.6 GB**, 100 % CPU, contexte 4096 : écart ≈ + 4 % | OK | script |
| N26-5 | llama3.2:3b, panneau Fenêtre, `context_window` 8 192, « Bonjour » (t30) | hausse de SIZE ≈ hausse de cache annoncée (± 30 %) | annoncé : 4 096 « 448 Mo », 8 192 « 896 Mo », soit + 448 Mio (≈ 470 Mo) ; rechargement 1,8 s ; `ollama ps` **2.6 GB → 3.1 GB**, contexte 8192 : + 0,5 GB (arrondi d'Ollama à 0,1 GB) ; revenu à 4 096 | OK | script |
| N34-3 (journal) | llama3.2:3b (Ollama), Réinitialiser, « Bonjour » (t29) | aucune requête sortante dans le tour | **0** `outbound_request` au tour t29. Phrase du bilan : calculée par le front, lue à l'étape 5 | OK (journal) | script |
| N32-2 (Ollama) | qwen3.5:2b servi par Ollama, « Outils natifs », « Quelle heure est-il ? » (t31) ; prompt brut passé à `OllamaRawEngine.complete` | égalité octet pour octet ; écart de tokens nul | appel 1 : 3 075 octets **IDENTIQUE** (même empreinte `55789a3f0769` que le 2B intégré), 729 = 729 ; appel 2 : 3 279 octets **IDENTIQUE**, 788 = 788. Aussi llama3.2:3b (t29) : 240 octets IDENTIQUE, 36 = 36 | OK | script |
| N25-2 (cartes, local) | cartes Raisonnement et Outils après chargement (`bricks_changed`) | = tableau | 2B intégré et qwen3.5:2b Ollama : Raisonnement disponible (budget de réflexion 768), Outils disponibles = « activable », « oui » ; llama3.2:3b : Raisonnement indisponible « le modèle actif ne sait pas raisonner. Son gabarit de conversation n'a pas de variable de raisonnement », Outils indisponibles « aucun format d'appel connu pour cette famille de modèle » = « jamais », « non » avec la même raison | OK | script |
| N33-3 | `select_model` Groq gpt-oss-120b, avertissement confirmé ; carte Raisonnement dans Edge (Claude in Chrome), clic sur son interrupteur | coché, verrouillé, 🔒 ; « Imposé par ce modèle » ; ne bouge pas | carte : 🔒, « Imposé par ce modèle », « Toujours active pour ce modèle : openai/gpt-oss-120b raisonne à chaque réponse ; ce modèle ne permet pas de l'éteindre. La réserve de sortie reste de 1 536 tokens. » ; `<input … role="switch" disabled …>` coché avant et après le clic. Retour au 2B sans 🔒 : à vérifier à l'étape 5 | OK | Claude in Chrome (Edge) |
| N32-4 | Groq, « Outils natifs », « Quelle heure est-il ? » (t32) ; corps passé à `OpenAIChatEngine.complete` ; « Corps JSON » dans Edge ; recherche de la clé dans la page | `json.loads(texte exact)` = `body` ; arbre lisible, arguments décodés ; aucune clé dans la page | appel 1 : 2 239 octets, sha256 `422367e105ad…` des deux côtés, **IDENTIQUE** ; appel 2 : 2 451 octets **IDENTIQUE** (donc égalité JSON). Dans Edge (tour t33) : « Corps JSON envoyé » en arbre repliable (`model`, `messages`, `tools`, `stream_options`, `reasoning_effort`), bloc « Produit par le modèle · Appel d'outil » avec `"arguments": { "title": "Mont-Saint-Michel" }` décodé ; dans le corps, `arguments` reste la chaîne envoyée à Groq ; **0** « gsk_ » dans le HTML de la page. Σ des sections estimées 342 et 470 contre 454 et 493 lus (`usage_source` api) : écart attendu en mode chat (estimations) | OK | script, Claude in Chrome (Edge) |
| N23-2 | Groq, t32 et t33 ; en-têtes de `outbound_request{origin: model}` ; recherche de la clé entière et de fragments de 8 caractères pris dans la clé | `Authorization: [masqué]`, masked True ; 0 occurrence | `Authorization` « [masqué] » masked True, `Content-Type` « application/json » en clair ; `Cookie` (posé par Groq) masqué aussi. Clé Groq (9 fragments + clé entière) et clé Mistral (7 + entière) : **0 occurrence** dans `run1\events.jsonl`, `run2\events.jsonl`, `run2\prompts.jsonl`, `run1-server.log`, `run2-server.log`, `wsdata\audit.log`, `batch27.log` | OK | script |
| N34-2 | Groq, « Outils réseau », « Résume l'article Wikipédia sur le Mont-Saint-Michel. » (t33) ; phrase sous le schéma dans Edge | K = lignes du journal ; aucun « en échec » | journal : **3** `outbound_request` (Groq, Wikipédia, Groq). Phrase : « Au tour 1, les données ont quitté le poste **3 fois** : vers le modèle chez Groq (contexte complet, 2 appels) et vers Résumé Wikipédia (le titre de l'article, 1 requête). » ; nœuds : Résumé Wikipédia « contacté », Jours fériés et Lecture de page web « non contacté » | OK | script, Claude in Chrome (Edge) |
| N23-1 (journal) | même tour (t33) | GET summary, User-Agent et Accept ; pas de 403 ; résultat non vide | `GET https://fr.wikipedia.org/api/rest_v1/page/summary/Mont-Saint-Michel`, en-têtes `Host`, `Accept: */*`, `Accept-Encoding`, `Connection`, `User-Agent: WaveStack/0.1 (demonstrateur pedagogique; https://github.com/Aliquanto3/agentic-harness-training-demo)`, aucun corps ; `tool_ended` ok ; résumé fidèle (îlot, abbaye, baie) | OK (journal ; mise en page à 1 366 à l'étape 4) | script |
| N25-2 (cartes, cloud) | Groq puis Mistral chargés (`bricks_changed`) | Groq « toujours » ; Mistral « activable » | Groq : `always_fr` renseigné, interrupteur verrouillé = « toujours » ; Mistral : Raisonnement disponible, sans `always_fr` ni verrou = « activable » ; Outils disponibles pour les deux = « oui (déclaré) ». Aucun appel réseau au chargement de Mistral. Avec N25-2 (cartes, local) : **5 modèles comparés, 0 écart** (le 4B n'est pas chargeable au budget) | OK | script |
| N25-6 | `llama-server.exe` (b11239) `-m Qwen3.5-2B-Q4_K_M.gguf --port 8080 -np 1 -c 4096` (« server is listening » en 3 s, `n_ctx_slot = 4096`, RSS 1 896 Mo) ; WaveStack relancé (run3) | éditeur Qwen (Alibaba), 2B, fenêtre 4 096 | candidat `server` `llama_server/Qwen3.5-2B-Q4_K_M.gguf`, `n_ctx` 4096, `gguf_path` lisible ; ligne « **Local · llama-server · Qwen3.5-2B-Q4_K_M.gguf · 2B** » dans « Sur ce poste · Qwen (Alibaba) », « Qwen (Alibaba) », « 2B », « 2 B · 1,2 Go », fenêtre « 4 096 tokens » (« contexte d'un emplacement du serveur »), outils « oui (qwen3_coder) », raisonnement « activable » | OK | script |
| N26-6 | modèle llama-server chargé (1,4 s) ; panneau Fenêtre ; `context_window` 8 192 ; bouton et jauge dans Edge | « bornée à 4 096 par llama-server (-c) » ; enregistré sans rechargement ; bouton et jauge à 4 096 | choix 8 192 : `bound_fr` « **bornée à 4 096 par llama-server (-c)** », « Cache de contexte : réservé par llama-server (-c 4 096), inchangé » ; réponse « Fenêtre de 8 192 tokens enregistrée ; la fenêtre effective de Qwen3.5-2B-Q4_K_M reste de 4 096 tokens (bornée à 4 096 par llama-server (-c)), sans rechargement. », `switching` False ; `settings.json` `{'window': 8192}` ; Edge : bouton « **Fenêtre 4 096 ▾** », jauge « 13 / 3 584 tokens », infobulle « Fenêtre de 4 096 tokens, dont 512 réservés à la réponse : 3 584 utilisables. » | OK | script, Claude in Chrome (Edge) |
| N26-7 | relance de WaveStack (run4), llama-server toujours à `-c 4096` ; bouton au premier affichage ; `/diagnostic` ; arrêt de llama-server, 2B intégré, 4 096 | « Fenêtre 8 192 ▾ » au premier affichage ; le diagnostic conseille `-c 8192` ; retour à 4 096 | llama-server repris comme modèle choisi ; `configured` **8 192** repris (effectif 4 096, `window_source` server). Bouton au premier affichage : « **Fenêtre 4 096 ▾** » (la fenêtre effective, comme en N26-6). **Aucun conseil `-c 8192`** : ni dans `/api/diagnostic` (`warning_fr` du candidat vide), ni sur la page `/diagnostic` (« Local llama-server · Qwen3.5-2B-Q4_K_M.gguf — serveur local déjà lancé, chargé, choix enregistré »). Le code ne conseille une relance que si le contexte du serveur dépasse 1,5 × la fenêtre (`servers.context_warning_fr`), jamais s'il est plus petit. Retour : llama-server arrêté, 2B intégré (3,6 s), 4 096 appliqué (2,1 s) | **KO** (conseil absent ; attendu du bouton contradictoire avec N26-6) | script, Claude in Chrome (Edge) |
| N24-5 | copie `Qwen3.5-2B-copie-test.gguf` (jamais sondée) dans le dossier de modèles jetable ; `select_model` à chaud ; « Arrêter » (`/api/intentions/stop`) 2 s après ; relevé des processus `probe` toutes les 50 ms (`n245.py`) | sonde tuée ≤ 1 s après le clic ; fin d'arrêt ≤ 3 s + rechargement ; rien d'enregistré | sonde vue à 1,89 s (pid 26080) ; clic à 2,04 s ; **sonde terminée à 2,11 s, soit 0,06 s après le clic** ; `idle` **1,90 s** après le clic ; `model_load_ended` `cancelled` « **Chargement arrêté : Qwen3.5-2B-Q4_K_M est de nouveau actif.** » ; 2B toujours actif (jamais libéré) ; aucune entrée pour la copie dans `failed_probes` ni `probed_models`. Copie supprimée ensuite. « Arrêt demandé · » dans la barre haute : non observé (piloté par l'API) | OK | script |
| N24-7 | copie d'un blob refusé le 28/09 (lfm2.5-thinking, 731 Mo) en `incompat-lfm-test.gguf` hors du dossier des modèles ; `select_model` par chemin | raison bien accentuée ; modèle précédent actif ; nouvelle entrée propre | 4,0 s : `harness_error` « Modèle incompatible : llama-cpp-python 0.3.35 ne sait pas charger ce fichier (architecture non prise en charge, fichier incomplet ou **abîmé**). Choisissez un autre **modèle**, ou servez-le avec Ollama ou llama-server. », puis « Le fichier incompat-lfm-test.gguf est incompatible. » / « Retour au modèle précédent : Qwen3.5-2B-Q4_K_M. » ; `model_load_ended` `restored`. Nouvelle entrée `failed_probes` : `ab\xeem\xe9`, `mod\xe8le` (propre). `settings.json` : toujours **6 lignes** avec « Ã/Â » (les 6 anciennes, 3 caractères chacune : 18 caractères, inchangés) | OK | script |
| N33-4 | 2B, « Mémoire globale », deux prompts (t1, t2 de run4) ; cartes et marges du Contexte LLM dans Edge ; interrupteur Prompt système éteint puis rallumé | tokens sans « ≈ » ; carte = tokens de sa section ; « Éteinte » puis des tokens | cartes : Prompt système « **33** tokens dans le contexte », Mémoire globale « 4 entrées · **194** tokens », Mémoire courte « **85** tokens dans le contexte », sans « ≈ ». Marges (dernier appel) : « Prompt système · **33** tokens » ; « Mémoire globale · 64 tokens **dont 3 de gabarit** · 7 segments », « Descriptions d'outils · Mémoire globale · 111 tokens », « Résultats d'outils · Mémoire globale · 22 tokens » : 61 + 111 + 22 = **194** ; « Historique · Mémoire courte · 127 tokens dont 42 de gabarit » : **85**. `by_brick` identique. Interrupteur : « 33 tokens dans le contexte » → « **Éteinte** » → « 33 tokens dans le contexte ». La carte compte tous les segments de sa brique, gabarit exclu : l'égalité se lit en retirant « dont N de gabarit » et en ajoutant les autres sections de la brique | OK | script, Claude in Chrome (Edge) |
| N24-3 / P6 | WaveStack arrêté ; `config.save_setting('memory', {'budget_mode': 'fixed', 'budget_mb': 6144})` dans le `settings.json` **jetable** ; relance (run5) | « valeur fixe », 6 144 Mo | « RAM du poste : 16 064 Mo, dont 7 257 Mo disponibles au lancement. **Budget mémoire de WaveStack : 6 144 Mo (valeur fixe [memory] budget_mb de 6 144 Mo (budget_mode = « fixed »)).** » statut `ok` (6 144 < 7 257 disponibles : pas d'avertissement « Le budget fixe dépasse … ») ; le 4B se charge (6,4 s, RSS 3 003 Mo) | OK | script |
| N26-4 | budget fixe 6 144 Mo, 4B chargé ; panneau Fenêtre ; `context_window` 16 384 | refus chiffré, ou « ✓ Tient » et rechargement | panneau : 4 096 « 512 Mo », 8 192 « 1,0 Go » (tient), 16 384 « 2,0 Go », `fits` False. Intention : 409 « **Fenêtre de 16 384 tokens refusée : Qwen3.5-4B-Q4_K_M demanderait environ 5,9 Go ; WaveStack occupe 128 Mo sans le modèle actif, pour un budget de 6,0 Go (= valeur fixe [memory] budget_mb). Qwen3.5-4B-Q4_K_M reste actif avec 4 096 tokens. Choisissez une fenêtre plus petite.** », « Rien n'est libéré, écrit ni rechargé. » ; 4B resté à 4 096. Ce refus découle de l'anomalie A2 : cache réel à 16 384 ≈ 512 Mo (32 768 octets par token), pas 2 Go ; le 4B tiendrait (≈ 4,4 Go) | OK (critère) ; refus dû à A2 | script |
| N23-3 | « Où vont mes données ? », « Métier IAM », « Métier Souveraineté », MCP complet (run2 à run4) ; en-têtes des `outbound_request{origin: brick}` | chaque requête montre ses en-têtes ; `Mcp-Session-Id` et tout en-tête non public à « [masqué] » | **34** requêtes des briques (13 `https://mcp.data.gouv.fr/mcp`, 20 `https://learn.microsoft.com/api/mcp`, 1 Wikipédia), toutes avec leurs en-têtes (Host, User-Agent, Accept-Encoding, Connection, accept, content-type, mcp-protocol-version…). **`mcp-session-id` masqué 17 fois sur 17, `Cookie` 17 sur 17** ; aucun en-tête d'authentification, de session, de jeton ni de proxy en clair. Poste derrière le proxy : `Proxy-Authorization` non tracé (limite connue). Bloc dans Orchestration : étape 5 | OK (journal) | script |
| N25-3 | tableau (`window` du 2B) ; jauge après chargement | égalité exacte | tableau : 2B `window` **4 096** (« fenêtre configurée ») ; après chargement : `context_window_state.window` **4 096**, jauge « … / 3 584 », infobulle « Fenêtre de 4 096 tokens, dont 512 réservés à la réponse » ; llama-server : 4 096 des deux côtés | OK | script, Claude in Chrome (Edge) |


## Étape 4 : Playwright (Chromium `chromium-1194`) sur la vraie application

Application run6 (2B, fenêtre 4 096, budget par défaut 4 096 Mo), après un tour « Outils réseau »
Wikipédia sur le 2B (t1, 43 s, `wikipedia_summary` ok). Scripts `pw.py` et `pw2.py` ;
captures dans `<scratchpad>\run6\pw\` (noms cités). axe-core 4.x (`axe-playwright-python`, règle
`color-contrast`, celle qu'emploie Lighthouse).

| Test | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| Barre haute, 4 largeurs | 1 280 × 720, 1 280 × 650, 1 366 × 768, 1 440 × 900, 1 600 × 1 000, normal et projection, thème clair ; clic sur le nœud « Calculatrice » puis « — » de Contexte LLM (geste de l'E2E) | barre sur une ligne, « Réinitialiser » visible, puce « · lié » lisible | **barre sur une ligne partout** (56 px en normal, 72 px en projection ; aucun enfant ne déborde, pas de défilement horizontal) ; **« Réinitialiser » entier partout**. Puce « ● + Contexte LLM · lié » (`aria-label` avec « lié » partout) : **entière seulement en projection à 1 366 et 1 600**. Il manque : projection 1 280 **7 px** (l'échec de l'E2E), projection 1 440 **129 px** (réduite à « ● + ( ») ; normal 1 280, 1 440 : 116 px (26 px de large, illisible), normal 1 366 et 1 600 : 60 et 62 px (« + Conte… », « + Contexte L »). Aussi tronqués : indicateur du modèle (« L… Qwen3.… »), chiffres de la jauge à 1 280 et 1 440, et en projection partout (masqués). Captures `layout-*.png` | **KO** (puce) | Playwright |
| N33-5, N31-7 (hors Edge) | balayage axe `color-contrast`, 1 600 × 1 000, thèmes clair et sombre : atelier, atelier avec panneau Fenêtre, liste Volets, tiroir de la mémoire, tiroir du prompt ouverts ; `/diagnostic` ; `/models` | 0 élément signalé | **0 violation** sur les 14 vues (7 en clair, 7 en sombre). « À revoir » (non jugés par axe : dégradés, superpositions) : 63 à 94 sur l'atelier, 0 sur `/diagnostic` et `/models`. Lighthouse d'Edge reste à la main (même moteur axe) | OK (Chromium) | Playwright |
| Captures | chaque volet et chaque page, clair et sombre | — | `light-` et `dark-` : `atelier`, `volet-bricks`, `volet-human`, `volet-ctx`, `volet-orch`, `volet-schema`, `diagnostic`, `models`, `panneau-Fenêtre`, `liste-Volets`, `tiroir-mémoire`, `tiroir-prompt` (24 fichiers). Aucune erreur de console | fait | Playwright |
| N22-3 (1 600 × 1 000) | tiroir de la mémoire ouvert (4 entrées), sombre | croix, pied fixe « Tout effacer » (rouge) et « Fermer » | croix en haut à droite, « Tout effacer » bordé de rouge et « Fermer » visibles en bas sans défiler (`dark-tiroir-mémoire.png`) ; avec 8 entrées et zoom 150 % : à l'écran | OK (partiel) | Playwright |
| N34-0 (frise) | Orchestration du tour Wikipédia | titres et pastilles H, M, M, R, H, M | « Décrit les outils » H, « Appelle le modèle » M, « Demande un outil » M, « Exécute l'outil hors du poste · Résumé Wikipédia » R, « Réinjecte le résultat » H, « Répond » M ; nœud Résumé Wikipédia « contacté », Jours fériés et Lecture de page web « non contacté » (`light-atelier.png`) | OK | Playwright |
| N31-2 (émulé) | thème « Système », `emulate_media(color_scheme)` clair → sombre → clair, sans rechargement | bascule sans rechargement | fond `rgb(246, 245, 250)` → `rgb(18, 18, 28)` → `rgb(246, 245, 250)`, `data-theme` absent, sélecteur « system ». Réglage réel de Windows dans Chrome et Edge : à la main | OK (émulé) | Playwright |
| N31-3 | deux onglets du même profil ; « Sombre » dans A ; puis dans B `/diagnostic`, « Clair », « Précédent » | B suit sans rechargement ; après « Précédent », atelier clair **et sélecteur sur « ☀ Clair »** | B passe en sombre sans rechargement (`data-theme` dark, sélecteur dark). Après « Précédent » : atelier **clair** mais **sélecteur sur « Sombre »** (`value` dark). Reproduit dans **Edge** avec un vrai retour (`history.back()`, navigation `back_forward`) : `data-theme` light, `localStorage` light, sélecteur « **☾ Sombre** » (capture `claude-chrome-screenshots-SdaTjq\screenshot-1790665845385-0.png`) | **KO** (sélecteur) | Playwright, Claude in Chrome (Edge) |
| N31-8 | profil gardé : « Sombre », page fermée, nouvelle page ; profil vierge (équivalent InPrivate) : « Sombre » | repris ; aucune erreur de console | même profil : sombre repris ; profil vierge : « Système », puis « Sombre » appliqué ; **aucune erreur de console** sur toute la séance Playwright. Chrome fermé puis relancé, et vraie fenêtre InPrivate d'Edge : à la main | OK (émulé) | Playwright |
| N31-1 (Chromium) | 1 366 × 768 : faces du sélecteur ; focus clavier ; flèche bas | « ◐▾ », « ☀▾ », « ☾▾ » ; focus visible ; flèches changent le thème | faces « ◐ ▾ », « ☾ ▾ », « ☀ ▾ » ; focus : `:focus-visible`, contour blanc plein de 2 px ; flèche bas : « Système » → « Clair », appliqué (`n31-1-compact-focus-1366.png`) | OK | Playwright |
| N34-5 (émulé) | `reduced_motion` reduce contre no-preference, survol du nœud Calculatrice | estompage instantané, même éclairage | no-preference : 50 éléments avec transition (`opacity, outline-color 0.15s`), 42 estompés ; **reduce : 0 transition**, 42 estompés (même éclairage). Réglage réel de Windows : à la main | OK (émulé) | Playwright |


## Étape 5 : Claude in Chrome, écran réel d'**Edge 154**

Edge suit un Windows en **mode sombre** (`prefers-color-scheme: dark`) : « ◐ Système » donne donc
l'atelier sombre ; les tests qui demandent un Windows clair (N31-0, N31-2, N31-3) sont décrits en
conséquence. Onglet de 1 413 puis 1 696 px CSS de large (fenêtre agrandie pendant la séance).
Captures dans `%TEMP%\claude-chrome-screenshots-SdaTjq\`.

| Test | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| N22-1 (Edge) | Réinitialiser ; première carte ; « RAG avec reranking » ; RAG éteint ; survol de « Reranking » ; Réinitialiser, options MCP, « Lazy loading » | Raisonnement en tête ; option cochée grise, sans réaction, infobulle ; « · brique éteinte » | première carte **Raisonnement** (puis Prompt système, Mémoire courte). RAG éteint : « Reranking » **coché, `disabled`, gris** (interrupteur gris, pas violet), `title` et `aria-description` « **Activez la brique RAG pour régler cette option.** ». MCP éteint : résumé « Serveurs : 1 activé sur 3 **· brique éteinte** », « Lazy loading » désactivé, `title` « **Activez la brique MCP pour régler cette option.** ». RAG rallumé : « Reranking » reste coché, grisé le temps du chargement du modèle d'embedding. L'infobulle est l'infobulle native du navigateur (`title`) : elle ne paraît pas dans les captures, son délai (< 2 s) reste à voir à l'œil | OK (texte) ; délai à l'œil | Claude in Chrome (Edge) |
| N22-6 (affichage) | Réinitialiser, puis tour Wikipédia (t2 du journal) | « Tour 1 », infobulle avec l'identifiant | Orchestration « **Tour 1** », `title` « **Identifiant du tour dans le journal : t2** » | OK | Claude in Chrome (Edge) |
| N25-1 (Edge) | liste « Changer de modèle… » ouverte | légende entière en tête ; groupes et ordre | liste native ouverte : « Changer de modèle… », puis la légende **entière** sur une ligne, puis « Sur ce poste · Qwen (Alibaba) » (0,8B, 2B, 2B, 2B Ollama, 4B…), Llama, Gemma, Granite, Phi, Mistral, LFM, Nemotron, MiniCPM, « Autres éditeurs » (olmo-3 seul), « Réseau · Mistral », « Réseau · gpt-oss », « Tableau des modèles et de leurs capacités… », « Autre fichier ou clé API… ». Incompatibles et modèle actif grisés (capture `screenshot-1790665962150-2.jpg`) | OK | Claude in Chrome (Edge) |
| N34-0 (Edge) | tour Wikipédia ; sous-titres ; survol de la carte Outils ; clic sur « Calculatrice » ; « — » de Contexte LLM ; Échap ; clic sur la puce ; bilan | voir cahier | sous-titres 1 « Ce que voit l'utilisateur », 2 « Ce que le modèle lit, dans l'ordre », 3 « Ce que fait le harnais, pas à pas », 4 « Où tourne chaque pièce » ; aide « Survolez une brique : elle s'éclaire dans le contexte, l'orchestration et le schéma. » ; survol : le reste s'estompe, outils et outils réseau éclairés (`screenshot-1790666044667-3.jpg`) ; clic Calculatrice : carte Outils, 2 sections et 1 étape cerclées ; puce « **● + Contexte LLM · lié** » entière (1 696 px), `aria-label` avec « lié » ; Échap : puce « + Contexte LLM », 0 élément lié ; puce cliquée : volet revenu. Bilan : « Au tour 1, les données ont quitté le poste 1 fois : vers Résumé Wikipédia (le titre de l'article, 1 requête). » | OK | Claude in Chrome (Edge) |
| N33-0 (Edge, partiel) | même tour | carte Outils : puce RÉSEAU, « N déclarés · 1 contacté » ; légende ; disciplines | carte Outils rose (harness engineering), puces « harness engineering », « Local », « 🌐 RÉSEAU », « **6 déclarés · 1 contacté** » ; légende du panneau : Prompt engineering, Context engineering, Harness engineering, Sort du poste de travail ; cartes éteintes grisées « Éteinte » ; jaune seulement sur la zone Réseau et les nœuds 🌐. « Tout se voit sans chercher » : avis d'Anaël | OK (constat) ; avis à la main | Claude in Chrome (Edge) |
| N23-1 (Edge) | clic sur le nœud 🌐 « Résumé Wikipédia » | étape dépliée, bloc Données sortantes ouvert ; User-Agent lisible sans défilement horizontal | bloc « 🌐 RÉSEAU · Données sortantes » **ouvert** sur l'étape : Requête « GET https://fr.wikipedia.org/api/rest_v1/page/summary/Mont-Saint-Michel », En-têtes (Host, Accept: */*, Accept-Encoding, Connection, **User-Agent: WaveStack/0.1 (demonstrateur pedagogique; https://github.com/Aliquanto3/agentic-harness-training-demo)**), Corps « Aucun corps : seule l'adresse sort du poste. » ; texte en `pre-wrap`, débordement horizontal 0 (le User-Agent passe à la ligne dans la colonne) ; résultat non vide (`screenshot-1790666089002-4.jpg`). Chrome à 1 366 × 768 : par Playwright, pas de défilement horizontal | OK | Claude in Chrome (Edge) |
| N32-0 (Edge) | « Outils natifs », « Quelle heure est-il ? » (t3), Contexte LLM en « Lecture groupée » | appels numérotés avec Lu, évalués, produits ; déjà-lu replié, « Nouveau » ; blocs « Produit par le modèle » ; ligne du harnais entre les appels | « **Appel 1 sur 2** · Lu : 729 tokens · évalués : 729 · produits : 13 », « **Appel 2 sur 2** · Lu : 788 tokens · évalués : 46 · produits : 32 » ; « **Déjà lu à l'appel précédent · 6 sections · 720 tokens** » replié ; 5 marques « **Nouveau** » à l'appel 2 ; blocs « Produit par le modèle » ; « ⚙ Le harnais exécute Heure et date ; le résultat est lu à l'appel 2. ». « Texte exact » : voir N32-2 (égalité octet pour octet) | OK ; avis de lecture à la main | Claude in Chrome (Edge) |
| N32-3 (Edge) | même tour, appel 1 | un arbre par outil activé ; marge qui nomme gabarit et descriptions | appel 1 : **4 arbres JSON** repliables (3 outils de la carte Outils, « Outils : 3 activés sur 6 », et l'outil `remember` décrit dans la section « Descriptions d'outils · Mémoire globale ») ; marge « Descriptions d'outils · 271 tokens dont 30 de gabarit · 5 segments » ; appel 2 : les mêmes 4 arbres dans le déjà-lu | OK (3 + 1 de la mémoire) | Claude in Chrome (Edge) |
| N22-5 (formulaire) | « Sous-agent », « Afficher les actions forcées », « Déléguer au sous-agent », « Annuler » ; rouvrir ; re-cliquer « Déléguer » | fermeture < 0,5 s | « Annuler » : fermé à l'image suivante, **19 ms** ; re-clic sur « Déléguer au sous-agent » : **20 ms**. Préréglages : « Résumer le guide du harnais », « Bornes de la boucle », « Notes de réunion », « Saisie libre ». Remarque : le bouton garde `aria-expanded="false"` formulaire ouvert | OK | Claude in Chrome (Edge) |
| N22-5 (onglets) | préréglage « Résumer le guide du harnais », « Armer », premier prompt suggéré, « Envoyer » depuis l'interface (t4, **170,3 s**) ; onglets de Contexte LLM ; « Merci » | onglets « Agent principal » (sélectionné) et « Sous-agent sub1 » ; principal au tour suivant | puce « 👆 Armé : Délégation : « Lis le fichier guide_harnais.md et résum… » » ; `delegate` trigger user, `subagent_started` sub1. Onglets : « **Agent principal** » `aria-selected` true, « Sous-agent sub1 » false ; clic : sub1 sélectionné, contexte du sous-agent (« Appel 1 sur 2 · Lu : 418 tokens … », `read_file` guide_harnais.md) (`screenshot-1790666396561-5.jpg`). Tour « Merci » sans sous-agent : plus d'onglets, contexte principal affiché | OK | Claude in Chrome (Edge) |
| N32-6 (Edge) | « Raisonnement », prompt suggéré (t6, 99,5 s) ; Contexte LLM ; « Mode projection » | un appel : réflexion, note, réponse ; en projection, rien de coupé, pas de défilement horizontal | `reasoning_cut` à 768 tokens (réserve 765) ; « **Appel 1 sur 1** » ; ordre : « Produit par le modèle · Réflexion », « ⚙ Le harnais : **Raisonnement coupé par le harnais à 768 tokens** : … garde 765 tokens pour la réponse. », « Produit par le modèle · Réponse » (17 h 50, juste). Projection (1 696 px) : 0 défilement horizontal dans la page et dans Contexte LLM, 0 texte coupé dans le volet (`screenshot-1790666534043-6.jpg`). À 1 366 × 768 : par Playwright, voir la ligne barre haute (Contexte LLM non mesuré à cette largeur) | OK | Claude in Chrome (Edge) |
| N34-3 (variante intégrée) | bilan du tour t6 (2B intégré, aucune brique réseau) | phrase sans sortie | « Au tour 1, aucune donnée n'a quitté le poste : le modèle tourne sur ce poste et aucun service réseau n'a été contacté. » (la variante Ollama « servi sur ce poste (Ollama) » n'a pas été lue à l'écran) | OK (variante) | Claude in Chrome (Edge) |
| N34-1 | « Outils natifs », « Combien font 12*37 ? » sans survol (CPU échantillonné toutes les 0,5 s) ; « Rejouer le dernier prompt » dans Edge avec 120 survols simulés (`pointerover`, l'événement qu'écoute l'application) alternés carte Outils / nœud Calculatrice toutes les 250 ms | éclairage < 100 ms, sans clignotement ; CPU avec survol ≤ sans + 5 points | délai jusqu'à l'image suivante : **médiane 2 ms, 95e centile 15 ms, max 21 ms** ; 0 image sans éclairage ; 1 tâche longue de 84 ms pendant le flux. CPU du poste : **97,4 % sans survol** (20,4 s), **89,0 % avec survol** (18,3 s) ; les deux sont saturés par llama.cpp (tous les cœurs), la comparaison est donc peu parlante. Le vrai pointeur et le Gestionnaire des tâches : à la main | OK (simulé) | script, Claude in Chrome (Edge) |
| N26-8 (Chromium, zoom émulé) | fenêtre 1 280 × 650 ; zoom 100, 125, 150 % émulés (viewport 1 280 × 650, 1 024 × 520, 853 × 433, `deviceScaleFactor` égal au zoom) ; « Fenêtre ▾ » ouvert | aucune commande de la barre sur deux lignes ; panneau lisible, non coupé | barre de 56 px, **aucun enfant hors de la barre** aux trois zooms. Panneau : dans la fenêtre, lisible, mais **défilant** : 626 px de contenu pour 560 (100 %), 430 (125 %), 343 px (150 %) visibles ; « **Appliquer** » hors de vue sans défiler le panneau, **même à 100 %**. À 125 % et 150 %, le bouton « 4096 ▾ » **recouvre la légende de la jauge** (« Context engine… ») (`n26-8-fenetre-100/125/150.png`). Edge et vrai zoom : à la main | OK (critère) ; remarques | Playwright |
| N25-7 (Chromium) | `/models`, 1 600 × 1 000 à 125 % émulé | aucune colonne coupée ; onglets ; RÉSEAU | tableau de 1 232 px dans 1 280, **0 cellule coupée**, pas de défilement horizontal ; colonnes Modèle, Éditeur, Taille, Hébergement, Fenêtre, Appel d'outils, Raisonnement, État ; onglets « Diagnostic », « Modèles », « Ouvrir WaveStack » ; « RÉSEAU » sur les 2 lignes cloud (`n25-7-models-125.png`). Lecture du fond de la salle : à la main | OK (mesure) | Playwright |
| N22-3 (Chromium) | « Modifier la mémoire » (3 entrées de démonstration dans cette session), 1 600 × 1 000 à 100 % et 150 % émulés | croix ; « Tout effacer » et « Fermer » visibles sans défiler | 100 % : croix, « Tout effacer » (bord `rgb(255, 42, 73)`) et « Fermer » visibles ; 150 % : les trois visibles, **la liste seule défile** (`n22-3-tiroir-100/150.png`). Avec 8 entrées : non fait (commande « 8 entrées de test » non lancée) ; distinction évidente : avis d'Anaël | OK (partiel) | Playwright |
| N32-5 (Edge, approché) | « RAG », premier prompt suggéré envoyé depuis l'interface (t9, 34 s) ; `PerformanceObserver('longtask')` ; défilement du volet toutes les 0,7 s et dépliage des blocs pendant le flux | aucune tâche longue > 200 ms due au rendu ; déplié et défilement gardés | **0 tâche longue** pendant le tour ; 21 blocs dépliés restés ouverts ; réponse « au minimum **14 caractères** ». Réserve : le 2B a répondu en **un seul appel de 1 157 tokens**, pas les ≈ 3 500 tokens et trois appels de la spec ; l'onglet Performance des DevTools d'Edge reste à la main. N34-1 a relevé une tâche longue de 84 ms pendant un autre flux | OK (approché) | Claude in Chrome (Edge) |
| N31-5 (captures) | `/diagnostic` et `/models`, clair et sombre (`light-diagnostic.png`, `dark-diagnostic.png`, `light-models.png`, `dark-models.png`) | fonds doux, état lisible sans la couleur seule ; RÉSEAU jaune, Local neutre | clair : lignes de vérification et modèles sur fonds doux (vert pour ok et disponible, rose pour incompatible, avec le mot « incompatible » dans la raison) ; modèles cloud sur fond jaune doux, puce « 🌐 RÉSEAU » jaune, « Local » en neutre. Sombre : pages sombres lisibles, sélecteur « ☾ Sombre ». axe : 0 défaut sur ces pages (étape 4). Jugement fin de l'aspect : Anaël | OK (constat) | Playwright |


## Étape 6 : terrain préparé pour les gestes à la main (09:30)

- WaveStack tourne sur http://127.0.0.1:8420/ (processus `launch.py`, **dossier de données
  jetable**, 2B intégré, fenêtre 4 096, budget par défaut), le tour Wikipédia de N33-0 à l'écran
  (« Outils réseau », t10 du journal run6), thème « ◐ Système », Mode projection relâché. Il
  sert aux gestes humains sans toucher au dossier réel ; pour les tests qui demandent un
  lancement neuf (N24-2, N31-8 dans Chrome), utilisez `uv run wavestack` après l'avoir arrêté.
- Edge : l'onglet de l'extension est sur l'atelier. Windows est en **mode sombre** : les tests
  qui partent d'un Windows clair (N31-0, N31-2, N31-3) demandent de passer d'abord en clair.
- Dossier réel vérifié à 09:29 : `settings.json` inchangé (9 272 octets, empreinte `FA634B52…`,
  6 lignes « Ã/Â »), `api_keys.json`, `memory.json`, `audit.log` inchangés.

## Synthèse par story

| Story | Statut | Mesures face aux critères |
|---|---|---|
| 22 · briques, volets, tiroirs | OK sur ce qui est vérifié ; reste humain | N22-1 : textes d'infobulle et états justes dans Edge, délai à l'œil. N22-3 : pied visible à 100 et 150 % (3 entrées). N22-5 : fermeture en 19 et 20 ms (< 500) ; onglets conformes. N22-6 : t1 à t5 uniques, « Tour 1 » avec « t2 » |
| 33 · contrastes et code couleur | OK sur ce qui est vérifié | N33-3 : verrou, « Imposé par ce modèle », clic sans effet. N33-4 : 33 = 33, 194 = 61 + 111 + 22, 85 = 127 − 42. N33-5 : 0 défaut axe en clair (Chromium) |
| 23 · données sortantes | OK | N23-1 : User-Agent exact, pas de 403, bloc ouvert dans Edge, sans défilement horizontal. N23-2 : 0 occurrence de la clé (16 fragments et 2 clés entières, 7 fichiers). N23-3 : 17/17 `mcp-session-id` et 17/17 `Cookie` masqués |
| 34 · vue liée et lecture guidée | **KO partiel** (puce « · lié ») | N34-0, N34-2 (K = 3 = journal), N34-3 (0 requête), N34-1 (éclairage ≤ 21 ms), N34-5 (0 transition en mouvement réduit) : OK. **Puce « · lié » tronquée** : 7 px en projection à 1 280 (échec E2E), 129 px à 1 440, 60 à 116 px en mode normal à toutes les largeurs |
| 32 · contexte LLM lisible | OK | N32-2 : égalité octet pour octet et 0 token d'écart (2B intégré, Ollama qwen3.5:2b et llama3.2:3b). N32-4 : corps Groq identique octet pour octet, 0 « gsk_ ». N32-0, N32-3, N32-6 : OK dans Edge. N32-5 : 0 tâche longue (flux court) |
| 24 · mémoire comptée juste, budget, sonde | OK | N24-1 : 3 750 et 3 794 Mo à 1,5 et 1,7 % de PowerShell. N24-4 : N = 119 Mo, RSS après libération 109 Mo. N24-5 : sonde tuée en 0,06 s, `idle` en 1,9 s, rien d'enregistré. N24-6 : 2,49 Go estimés contre 2,6 GB. N24-7, N24-8 : accents justes, 6 lignes abîmées non réécrites |
| 25 · sélecteur regroupé, tableau | OK | N25-1 : ordre, groupes, légende entière dans Edge. N25-2 : 5 modèles, 0 écart. N25-3 : 4 096 = 4 096. N25-4 : 17 ms, 39 GGUF lus en moins de 7 s. N25-5 : 13 « inconnu » avec raison, 0 Traceback. N25-6 : Qwen, 2B, 4 096. N25-7 : 0 colonne coupée à 125 % |
| 26 · fenêtre réglable | **KO** (N26-2, N26-7) | N26-1 : cache et temps exacts. N26-2 : rechargement 2,2 s, conversation gardée, mais **+ 61 Mo mesurés pour 192 annoncés** (coût × 4). N26-3 : 4 042 tokens sans débordement, premier token 120 s (NFR-1 dépassé, annoncé). N26-4 : refus chiffré (dû au coût × 4). N26-5 : + 0,5 GB pour + 470 Mo. N26-6 : « bornée à 4 096 par llama-server (-c) ». **N26-7 : conseil `-c 8192` absent**. N26-8 : barre sur une ligne à 100, 125 et 150 % émulés |
| 27 · scénarios et consignes (lot H) | **KO** (4 scénarios sur 9) | OK : MCP complet, Skills (61 s), Compression (3 206 < 3 584), Où vont mes données ? (1 140 ≤ 1 200), Sous-agent (quiz 2 873 / 3 130 / 2 640 ms < 15 000), `fits` (marge mcp_full 380). **KO : Lazy loading** (réponse inventée), **SOC** (prompt 1 coupé à 512 tokens, prompt 2 sans contexte ni h1), **IAM** (aucun lien, prompt 2 déborde à 3 967 / 3 584), **Souveraineté** (jamais d'appel de recherche, même avec le secours) |
| 31 · mode sombre | **KO partiel** (N31-3) | N31-1 : ◐▾ ☾▾ ☀▾, focus 2 px, flèches. N31-2 et N31-8 : OK en émulation. N31-5 : fonds doux, RÉSEAU jaune. N31-7 : 0 défaut axe en sombre (7 vues). **N31-3 : après « Précédent », thème juste mais sélecteur sur l'ancien choix** (Chromium et Edge) |

## Identifiants vérifiés par Claude Code (ordre du cahier)

Statut, puis valeur à reporter. « (Edge) » : vérifié dans Edge ; la partie Chrome reste à faire
si le test la demande.

- P1 OK : commit `3ed8482` (tête détachée), branche d'origine : aucune (tête détachée)
- P2 OK (équivalent) : dossier réel non utilisé ; « Ã/Â » : 6 lignes ; hash `FA63`
- P3 OK : Qwen3.5-2B-Q4_K_M actif ; sélecteur de thème présent
- P4 OK (équivalent) : journal complet par le lanceur (`events.jsonl`)
- P5 OK : version b11239 ; chemin : repli (le bloc « Installation » échoue : `releases/latest` = v0.5.0 sans archive)
- P6 OK : budget fixe dans le `settings.json` jetable ; 4B utilisé pour N24-3 et N26-4
- N22-1 OK (Edge, texte) : infobulles « Activez la brique RAG / MCP pour régler cette option. » ; délai non mesuré
- N22-3 OK partiel : pied visible à 100 % et 150 % (3 entrées, zoom émulé)
- N22-5 OK (Edge) : fermeture 19 ms et 20 ms ; onglets conformes ; tour de délégation 170,3 s
- N22-6 OK : infobulle « Identifiant du tour dans le journal : t2 » après Réinitialiser (session run6) ; journal t1 à t5 uniques (run2)
- N33-0 OK (Edge, constat) : « 6 déclarés · 1 contacté », légende et disciplines ; avis à donner
- N33-3 OK (Edge) : verrouillé (`disabled`, coché, 🔒)
- N33-4 OK : Prompt système 33 / 33 ; Mémoire globale 194 / 194 (sections 61 + 111 + 22)
- N33-5 OK (Chromium, axe) : 0 élément ; score Lighthouse non mesuré
- N23-1 OK (Edge et journal) : conforme ; résultat non vide
- N23-2 OK : Authorization « [masqué] » ; 0 occurrence
- N23-3 OK (journal) : `mcp-session-id` masqué ; aucun secret en clair
- N34-0 OK (Edge) : bilan « Au tour 1, les données ont quitté le poste 1 fois : vers Résumé Wikipédia (le titre de l'article, 1 requête). »
- N34-1 OK (simulé) : éclairage ≤ 21 ms, sans clignotement ; CPU 97,4 % sans survol, 89,0 % avec (saturé)
- N34-2 OK : K = 3 ; lignes du journal = 3
- N34-3 OK (journal) : 0 requête ; phrase Ollama non lue à l'écran (variante intégrée lue)
- N34-5 OK (émulé) : estompage instantané (0 transition)
- N32-0 OK (Edge)
- N32-2 OK : 2B 729 / 729 et 788 / 788 ; Ollama 729 / 729 et 788 / 788 ; 4B non fait
- N32-3 OK (Edge) : 4 arbres ; 3 outils activés + `remember` de la mémoire globale
- N32-4 OK : arbre lisible ; clé non trouvée dans la page
- N32-5 OK (approché, Edge) : tâche la plus longue 0 ms pendant le tour RAG (84 ms sur un autre flux) ; déplié gardé
- N32-6 OK (Edge) : note entre les blocs ; aucun texte coupé (1 696 px)
- N24-1 OK : total 16 064 ; disponible 6 324 ; budget 3 794 ; PowerShell 6 434
- N24-2 OK partiel : disponible 6 250 ; budget 3 750 ; avertissement affiché (Edge ouvert, Teams fermé)
- N24-3 OK : « Budget mémoire de WaveStack : 6 144 Mo (valeur fixe [memory] budget_mb de 6 144 Mo (budget_mode = « fixed »)). »
- N24-4 OK : N = 119 Mo ; message chiffré (voir tableau)
- N24-5 OK : clic → sonde terminée 0,06 s ; clic → 2B actif 1,9 s ; aucune entrée
- N24-6 OK : estimation 2,3 Go ; SIZE 2,6 GB ; NUM_PARALLEL et KV_CACHE_TYPE vides
- N24-7 OK : « … fichier incomplet ou abîmé … » ; 6 lignes « Ã/Â »
- N24-8 OK (API) : « abîmé » juste ; 6 lignes
- N25-1 OK (Edge)
- N25-2 OK : 5 modèles ; 0 écart
- N25-3 OK : 4 096 / 4 096
- N25-4 OK : 1er appel (après diagnostic) 17 ms ; 2e 16 ms ; 39 GGUF (40 candidats avec llama-server)
- N25-5 OK : 13 modèles « inconnu » (ministral-3, lfm2.5-thinking, nemotron-3-nano, olmo-3…), raisons renseignées, 0 Traceback
- N25-6 OK : Qwen (Alibaba) / 2B / 4 096
- N25-7 OK (mesure) : 0 colonne coupée à 125 % émulé
- N26-1 OK : 4 096 192 Mo / 110 s ; 8 192 384 Mo / 220 s ; 16 384 768 Mo / 439 s ; débit 37,3 tok/s
- N26-2 **KO** : durée 2,2 s ; RSS 2 074 → 2 122 Mo (privé 2 418 → 2 479) pour 192 Mo annoncés
- N26-3 OK : prompt_ms 117 241 ; temps annoncé 439 s (108 s pour 4 042 tokens) ; pas de débordement
- N26-4 OK (critère) : « Fenêtre de 16 384 tokens refusée : Qwen3.5-4B-Q4_K_M demanderait environ 5,9 Go … »
- N26-5 OK : SIZE 2,6 GB → 3,1 GB ; cache annoncé 896 Mo
- N26-6 OK : « bornée à 4 096 par llama-server (-c) »
- N26-7 **KO** : 8 192 repris (configuré) mais bouton « Fenêtre 4 096 ▾ » ; conseil absent ; retour à 4 096 fait
- N26-8 OK (Chromium émulé) : barre sur une ligne ; Edge non fait
- N27-1 OK : prompt_ms 2 873 / 3 130 / 2 640 ; pas de redélégation ; pas de cause history
- N27-2 OK : load_tool_doc, datagouv__search_datasets ; 1 140 tokens gardés
- N27-3 OK : load_skill ; 61,1 s ; secours non utilisé
- N27-4 **KO** : complet conforme ; lazy non conforme
- N27-5 **KO** : 1 appel au prompt 1, 1 au prompt 2, puis débordement
- N27-6 **KO** : recherche jamais faite ; secours utilisé, sans effet
- N27-7 **KO** : fichier lu `alertes_siem.log` ; pas d'escalade (et pas de h1)
- N27-8 OK : trigger model ; jauge 3 206
- N27-9 OK : marge mcp_full 380 ; plus petite marge : mcp_full (380)
- N31-1 OK (Chromium) : faces et clavier ; Edge non fait
- N31-2 OK (émulé)
- N31-3 **KO** : autre onglet suit ; après « Précédent », sélecteur sur l'ancien choix (Edge et Chromium)
- N31-5 OK (constat sur captures)
- N31-7 OK (Chromium, axe) : 0 / 0 / 0 ; Lighthouse d'Edge non fait
- N31-8 OK (émulé) : repris ; aucune erreur de console

## Identifiants qui restent à faire à la main (ordre du cahier)

- P7 : retour à l'état initial (voir « Nettoyage » ci-dessous ; rien à restaurer dans le dossier réel)
- N22-1 : délai de l'infobulle (< 2 s) dans Edge et dans Chrome
- N22-2 : consigne SOC repliée, bulles visibles à 125 % et 150 % (vrai zoom)
- N22-3 : 8 entrées (commande « 8 entrées de test »), vrai zoom 150 %, avis sur la distinction
- N22-4 : Narrateur
- N33-0 : votre avis (« tout se voit sans chercher »)
- N33-1 : lecture à 3 m
- N33-2 : 4 éléments sans la légende (autre personne)
- N33-5 : Lighthouse dans Edge (score)
- N33-6 : thème de contraste « Désert »
- N23-1 : partie Chrome à 1 366 × 768 (facultatif : Edge conforme, Chromium sans défilement horizontal)
- N23-3 : bloc de la connexion data.gouv.fr dans « Préparation du harnais », à l'écran
- N23-4 : novice
- N34-1 : vrai pointeur et Gestionnaire des tâches (facultatif, CPU saturé par llama.cpp)
- N34-3 : lire la phrase avec un modèle Ollama à l'écran
- N34-4 : salle et Teams
- N34-5 : réglage Windows réel « Effets d'animation »
- N34-6 : Narrateur et clavier
- N32-1 : chronomètre et avis
- N32-2 : 4B (budget fixe), facultatif
- N32-5 : onglet Performance des DevTools avec un tour plus long (4B ou RAG à trois appels)
- N25-1 : Chrome (facultatif)
- N25-7 : lecture du fond de la salle
- N26-8 : Edge, vrai zoom 125 % et 150 %
- N27-10 : formateur novice
- N31-0 : Windows clair, « ☾ Sombre », bords et filets (captures sombres de Playwright disponibles)
- N31-1 : Edge au clavier
- N31-2 : vrai mode de Windows, Chrome et Edge
- N31-4 : éclair blanc au rechargement (Edge)
- N31-6 : projection et Teams, choix clair ou sombre
- N31-7 : Lighthouse d'Edge en sombre sur les trois pages
- N31-8 : Chrome fermé puis relancé ; vraie fenêtre InPrivate d'Edge

## Anomalies

| # | Test | Anomalie | Cause probable | Criticité | Correction proposée (non appliquée) |
|---|---|---|---|---|---|
| A1 | E2E `linked_view`, N34-4, N34-0 (largeurs) | La puce « ● + Contexte LLM · lié » est tronquée : 7 px en projection à 1 280 (échec E2E), 129 px en projection à 1 440, 60 à 116 px en mode normal à toutes les largeurs. Aussi : chiffres de la jauge masqués en projection à toutes les largeurs (même 1 696 px), nom du modèle tronqué, légende de la jauge recouverte par « 4096 ▾ » à 1 024 px | La puce rétrécit la première dans la barre flexible ; au-delà de 1 400 px le sélecteur de thème reprend sa forme longue (« ☀ Clair ») et prend la place ; les polices de Windows sont plus larges que celles du conteneur (l'E2E passe sous Linux) | Moyenne : la puce est le repère de la vue liée quand un volet est masqué ; lecteur d'écran correct (`aria-label`) | `#pane-chips .pane-chip { flex-shrink: 0 }` (ou `min-width: max-content`), et faire céder d'abord le nom du modèle et la légende ; en projection, garder le sélecteur de thème compact jusqu'à 1 600 px ; étendre le contrôle E2E aux 4 largeurs, normal et projection, avec une marge de 10 px pour les polices de Windows |
| A2 | N26-2, N26-4, N26-1 | Coût du cache annoncé **4 fois trop haut** pour Qwen3.5 (2B : 49 152 octets par token annoncés, 12 288 réels ; 4B : 131 072 contre 32 768). Mesure 4 096 → 8 192 : + 61 Mo privés pour 192 annoncés. Le 4B à 16 384 est refusé (5,9 Go) alors qu'il tiendrait (≈ 4,4 Go) | `probe.kv_bytes_per_token` compte `block_count × head_count_kv` ; le GGUF de Qwen3.5 donne `head_count_kv` en un seul entier (2) et `full_attention_interval` = 4 : les 18 couches à attention linéaire n'ont pas de cache | Moyenne : chiffres faux affichés à des formateurs ; refus trop prudents | Si `{arch}.full_attention_interval` = n > 1 et `head_count_kv` scalaire : couches avec cache = `block_count // n` ; test sur les métadonnées de Qwen3.5 (2B, 4B) ; incrémenter `probe_version` (ou recalculer à la lecture) pour corriger les entrées sondées |
| A3 | N26-7 | Relancé avec 8 192 choisi et llama-server à `-c 4096` : aucun conseil « relancez-le avec `-c 8192` » ; bouton « Fenêtre 4 096 ▾ » au premier affichage (le cahier attend « 8 192 ») | `servers.context_warning_fr` ne conseille que si le contexte du serveur dépasse 1,5 × la fenêtre, jamais s'il est plus petit ; le bouton montre la fenêtre effective | Faible | Ajouter le cas inverse au diagnostic (« llama-server a été lancé avec -c 4 096 ; pour la fenêtre choisie de 8 192, relancez-le avec `-np 1 -c 8192` ») ; trancher l'attendu du bouton (effective, avec « 8 192 choisi » dans l'infobulle) et aligner N26-6 et N26-7 du cahier |
| A4 | N31-3 | Après « Précédent », l'atelier applique le bon thème mais le sélecteur affiche l'ancien choix (Edge : `data-theme` light, `localStorage` light, sélecteur « ☾ Sombre ») | Restauration de l'état des formulaires par le navigateur sur une navigation `back_forward` hors bfcache (la page garde un flux SSE ouvert) : elle réécrit la valeur du `<select>` après `theme.js` | Faible | `autocomplete="off"` sur `select[data-theme-picker]` et relecture de `wavestack.theme` au `pageshow` et au `load` ; contrôle E2E par `page.go_back()` |
| A5 | N27-4 lazy, N27-5, N27-6, N27-7 | Avec le 2B à 4 096 : lazy loading répond de tête après `load_tool_doc` ; Souveraineté n'appelle jamais `datagouv__search_datasets` (3 essais, secours compris) ; SOC : prompt 1 coupé à 512 tokens (tour `limit`), donc absent de l'historique, et prompt 2 sans contexte, sans h1 ni escalade ; IAM : aucun lien cité, prompt 2 déborde (3 967 / 3 584) | Comportement du 2B après un chargement de documentation (il tient l'étape pour faite) ; réserve de sortie de 512 tokens trop courte pour une chronologie ou une liste de jeux de données ; un tour `limit` sort de l'historique (`abandoned`) ; résultats MCP de 1 153 tokens gardés dans l'historique ; le test `fits` ne vérifie que le premier prompt | **Élevée** pour la démo : 4 scénarios sur 9 du lot H ne montrent pas leur leçon | Secours de Lazy et Souveraineté : « Forcer l'appel » de l'outil lui-même (armer `tool` avec ses arguments) plutôt que `tool_doc` ; reformuler les prompts sans « Charge la documentation » ; SOC : demander une sortie courte (« en 8 lignes au plus ») ou relever la réserve pour ce scénario, et décider si un tour `limit` garde sa réponse tronquée dans l'historique ; IAM : « Vider la conversation » entre les deux prompts dans la consigne, ou plafond de 700 tokens pour mslearn, et demander les liens explicitement ; étendre `fits` à tous les prompts, historique compris |
| A6 | P5 | Le bloc « Installation » du cahier ne trouve pas d'archive | `releases/latest` de ggml-org/llama.cpp pointe désormais sur `v0.5.0` (seul fichier `nightly-tag.txt`) ; les builds `bNNNNN` restent publiées | Faible (le repli marche) | Lire `/releases?per_page=10` et prendre la première qui a `llama-b*-bin-win-cpu-x64.zip`, ou garder le repli en premier |
| A7 | N27-3 | Le compte rendu porte sur `notes_reunion.txt` (lu de lui-même) et non sur la réunion décrite dans le prompt | Le skill `meeting_minutes` ou le 2B pousse à lire un fichier de notes | Faible | Relire le texte du skill ; préciser dans le prompt « à partir des éléments ci-dessous, sans lire de fichier » |
| A8 | N22-5, N26-8 | `aria-expanded="false"` sur « Déléguer au sous-agent » formulaire ouvert ; « Appliquer » du panneau Fenêtre hors de vue sans défiler dès 1 280 × 650 à 100 % | Attribut non mis à jour ; panneau de 626 px de haut | Faible | Mettre à jour `aria-expanded` ; épingler « Appliquer » et « Fermer » en pied du panneau (comme le tiroir de la mémoire) |

## Nettoyage

Fait : copies de test supprimées (`Qwen3.5-2B-copie-test.gguf`, `incompat-lfm-test.gguf`),
llama-server arrêté, captures E2E restaurées (`git status` : seul ce fichier de résultats est
nouveau). Laissé en place : WaveStack (run6) pour vos gestes ; `<scratchpad>\wsdata` (copie et
**liens physiques** vers les modèles : les supprimer n'efface pas les originaux) ;
`%LOCALAPPDATA%\llama.cpp\b11239` (sans effet sur WaveStack) ; dans Edge, le thème de
127.0.0.1:8420 remis sur « Système ». Pour arrêter WaveStack :
`Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object CommandLine -match "launch.py" | ForEach-Object { Stop-Process -Id $_.ProcessId }`.

## Report dans le cahier en ligne (accord d'Anaël, 09:40)

67 tests écrits dans la base de l'artifact (collection `results-nuit`, vide avant) par
`ArtifactData` : statut posé seulement quand la vérification couvre tout le critère (43 OK, 8 KO),
sinon valeurs et note « Claude Code (29/09) : … RESTE : … » avec le statut laissé « à faire ».
Vérifié dans Edge après rechargement : « 43 OK · 8 KO · 0 non fait · 0 bloqué · 29 à faire ».
