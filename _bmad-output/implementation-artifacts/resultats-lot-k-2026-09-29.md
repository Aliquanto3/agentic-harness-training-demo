# Résultats de la recette du lot K sur PC cible (2026-09-29)

Poste : Windows 11 Enterprise 10.0.26200, PowerShell 5.1, sans droits d'administrateur, CPU
seul, 16 Go. Tête testée : `1eae76c` (`origin/claude/lot-k-recette-pc`, tête détachée).
Consigné au fil de l'eau par Claude Code ; aucun fichier du dépôt modifié (hors ce fichier,
non commité). Prompt suivi : `prompt-recette-lot-k-2026-09-29.md`.

Préparation : l'instance WaveStack de test laissée par la séance du matin (run6, `launch.py`,
dossier jetable) a été arrêtée pour libérer le port 8420 et le venv. Dossier réel avant la
séance : `settings.json` 9 272 octets, empreinte `FA634B52…` (inchangée depuis le matin).
Processus au début : Edge ouvert (23 processus), Outlook et Teams fermés, Ollama lancé.

## Étape 1 : tests automatiques

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| tête | `git fetch`, `git checkout --detach origin/claude/lot-k-recette-pc` | tête de la branche | `1eae76c` (poussée juste avant), arbre propre | OK | PowerShell |
| sync | `uv sync --extra compression` | sans erreur | 91 paquets résolus, 90 vérifiés, rien à installer | OK | uv |
| lint | `uv run ruff check .` | propre | « All checks passed! » | OK | ruff |
| format | `uv run ruff format --check .` | propre | « 148 files already formatted » | OK | ruff |
| pytest | `uv run pytest -q` (16:17 à 16:26) | vert | **1 253 passed, 3 skipped, 7 deselected in 529.54s**, code 0 | OK | pytest |
| `fits` exact | `WAVESTACK_TEST_GGUF` = 2B ; `uv run pytest -s -rA tests/test_program.py -k fits` | réussi, marges positives | **1 passed** en 19 s. Plus petite marge d'aperçu : **`mcp_full` p1, 3 204 / 3 584, marge 380** (328 après son résultat de 52). Une fois l'historique simulé et la place du résultat retirés : `network_tools` p2 388 (2 553 − 1 765 − 400), `compression` p1 465 (2 470 − 2 005), `mcp_lazy` p2 630, `compression` p2 685 ; `subagent` p2 1 150, p3 et p4 ≈ 1 686 (historique d'un seul échange, voir point 3) ; `iam` et `sovereignty` comptés sans historique (1 322 et 1 707) | OK | pytest |
| E2E | `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` (16:27 à 16:36) | 0 FAIL, `[linked_view]` aux quatre largeurs | **654 réussies, 0 en échec**, code 0. `[linked_view]` : « barre sur une ligne, « Réinitialiser » entier, légende de la jauge dégagée, « · lié » entier sur la puce (10 px de marge) » **PASS à 1 280, 1 366, 1 440, 1 600, projection et normal**. 5 `harness_error` voulus (429, 500, flux cassé, 401, embedding). Console : 2 × `ERR_FAILED`, 1 × `ERR_CONNECTION_RESET` et **1 × `ERR_CONNECTION_REFUSED`** (une de plus que les 3 notées sur le poste de développement ; aucune vérification ne la juge, réseau coupé du parcours) | OK | E2E |
| arbre | `git restore tools/e2e/screenshots` | arbre propre | captures restaurées ; seul ce fichier de résultats est nouveau | OK | PowerShell |

## Dossier de données jetable

`<scratchpad>\wsdata` (scratchpad de cette séance, hors dépôt) : copie de `settings.json`,
`api_keys.json`, `memory.json`, `audit.log` du dossier réel ; `models` = vrai dossier avec des
**liens physiques** (`mklink /H`) vers le 2B, le 4B, l'embedding et le reranker. Tous les
lancements passent par `WAVESTACK_DATA_DIR` vers ce dossier (`launch.py` et `ws.py` de la séance
du matin, copiés). Outils de la séance : `repath.py` (chemins et empreinte), `pw_k.py`
(Playwright, points 2, 5 et 6).

Dans le `settings.json` jetable seulement, les **clés** de `probed_models` du 2B et du 4B et le
`ref` de `selected_model` ont été réécrits du vrai dossier des modèles vers le dossier de liens
(3 occurrences, remplacement d'octets : aucune valeur touchée). Vérifié avant tout lancement :
entrée du 2B `kv_bytes_per_token` **49 152**, 4B **131 072** (sondes d'avant le lot), taille et
date des liens = celles des entrées. Empreinte du `settings.json` jetable avant le lancement :
`10C7B88A…` (9 662 octets, 18 caractères « Ã/Â » des 6 anciennes raisons abîmées).

## Étape 2 : point 1 (A2), coût du cache des modèles hybrides

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 1 | lancement (run1, 16:37), 2B choisi repris ; panneau « Fenêtre ▾ » (`context_window_state.choices`) | 4 096 « 48 Mo », 8 192 « 96 Mo », 16 384 « 192 Mo » | « Cache de contexte : **48 Mo** » (50 331 648 o), « **96 Mo** » (100 663 296), « **192 Mo** » (201 326 592), tous « tient » : 12 288 octets par token, recalculés depuis l'en-tête. **Aucune sonde** relancée (0 `probe_started`) | OK | script |
| 1 | empreinte du `settings.json` jetable après lancement, chargement, lectures du panneau, choix du scénario « Outils natifs » et trois tours | inchangée | `10C7B88A…`, 9 662 octets : **identique** ; l'entrée du 2B garde 49 152 dans le fichier | OK | script |
| 1 | mémoire, 2B, scénario « Skills », même conversation, un tour après chaque réglage ; Edge ouvert (23 processus, 1 450 Mo), **Outlook et Teams fermés** (Teams, ouvert en début de séance, fermé par Anaël à 17:02) ; `mem.py` (RSS et mémoire privée du processus) | 4 096 → 8 192 : ≈ + 48 Mio | t5 à 4 096 : RSS 2 062, privé 2 422 Mo ; t6 à 8 192 (rechargement 3,0 s, conversation gardée) : 2 135 / 2 494 → **+73 Mo RSS, +72 Mo privé** ; t7 à 8 192 : 2 138 / 2 497 ; t8 revenu à 4 096 : 2 036 / 2 424 (−102 / −73) ; t9 à 8 192 : 2 094 / 2 496 (**+58 / +72**). La mémoire privée monte de **72 Mo** à chaque passage (trois mesures concordantes) pour **48 Mio annoncés** : 1,5 fois l'annonce, contre 4 fois avant le lot (ce matin : +61 Mo privé pour 192 annoncés). L'écart restant (≈ 24 Mo) croît avec la fenêtre sans être du cache d'attention (tampons de calcul de llama.cpp, probablement) | OK (ordre de grandeur) ; écart de 1,5 noté | script |
| 1 | `settings.json` jetable après ces réglages | seuls les réglages posés le changent | 9 704 octets, `A9A02302…` : clé `context` `{'window': 8192}` ajoutée ; entrées `probed_models` inchangées (2B **49 152**, 4B **131 072** dans le fichier) | OK | script |
| 1 | WaveStack arrêté, fenêtre remise à 4 096 ; `config.save_setting('memory', {'budget_mode': 'fixed', 'budget_mb': 6144})` sur le jetable ; relance (run2, 17:07) | « valeur fixe », 6 144 Mo | « RAM du poste : 16 064 Mo, dont 7 355 Mo disponibles au lancement. Budget mémoire de WaveStack : **6 144 Mo (valeur fixe [memory] budget_mb de 6 144 Mo (budget_mode = « fixed »))**. » | OK | script |
| 1 | `select_model` du 4B (7,8 s) ; panneau « Fenêtre ▾ » | 16 384 tient | 4 096 « **128 Mo** », 8 192 « **256 Mo** », 16 384 « **512 Mo** » (32 768 octets par token), **tous `fits` true** (le matin : 512 Mo / 1,0 Go / 2,0 Go, 16 384 refusé). `settings.json` : seul `selected_model` change (4B choisi), sondes inchangées | OK | script |
| 1 | 4B, un tour à 4 096 (« Bonjour. ») ; `context_window` 16 384 ; un tour (« Merci. ») | accepté, rechargement ; hausse ≈ 384 Mio (± 30 %) | **accepté** : « Fenêtre de contexte : 16 384 tokens (conversation gardée). », rechargement **5,4 s**. Mémoire : 4 096 → RSS 4 317, privé 3 330 Mo ; 16 384 → RSS 4 708, privé 3 821 Mo : **+391 Mo RSS (+2 %)**, **+491 Mo privé (+28 %)** pour **384 Mio annoncés** : dans ± 30 % pour les deux | OK | script |

## Étape 3 : point 2 (A1), barre haute et puce « · lié »

Playwright 1.56 sur la vraie application (run1, 2B) : **Chromium 141** (`chromium-1194`) puis
**Edge 154** installé (`channel="msedge"`, même profil vierge à chaque contexte). Geste de
l'E2E : scénario « Outils natifs », un tour qui appelle la Calculatrice (le 2B répond de tête
aux prompts 1 et 2 ; appel forcé `calculator` « 1234*5678 » puis rejeu, t3), clic sur le nœud
`#schema .arch-node` « Calculatrice », « — » de Contexte LLM. Mesure : `scrollWidth −
clientWidth` de la puce telle quelle puis élargie de 10 px (contrôle de l'E2E), enfants de la
barre hors de la barre, « Réinitialiser », recouvrement de la légende par « 4096 ▾ ». Zoom
**émulé** : viewport 1 280 × 650 divisé par le zoom, `deviceScaleFactor` = zoom (1 024 × 520 à
125 %, 853 × 433 à 150 %). Captures `<scratchpad>\run1\pw\{chromium,edge}-bar-*.png`,
`*-zoom*.png`.

Sans tour, la puce reste « + Contexte LLM » (rien de lié dans le volet masqué) et cède comme
prévu (73 à 106 px coupés) : le geste demande un tour avec appel de la Calculatrice.

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 2 | Chromium, 1 280 × 720, 1 366 × 768, 1 440 × 900, 1 600 × 1 000, normal puis projection | puce « · lié » entière, `scrollWidth − clientWidth` ≤ 1, barre sur une ligne | puce « **● + Contexte LLM · lié** » : manque **0 px** aux 8 mesures, **0 px avec 10 px de marge** ; barre de 56 px (normal) et 72 px (projection), **aucun enfant hors de la barre**, pas de défilement horizontal, « Réinitialiser » entier ; légende dégagée (24 à 232 px d'écart) | OK | Playwright |
| 2 | Edge 154, mêmes 8 mesures | idem | **mesures identiques au pixel près** à Chromium : manque 0 px (et 0 avec 10 px), barre sur une ligne, « Réinitialiser » entier | OK | Playwright (Edge) |
| 2, remarque | mêmes captures | chiffres de la jauge visibles quand la place le permet | chiffres **coupés** (ellipse, texte en infobulle) à 1 280 et 1 600 normal (104 et 8 px), 1 366 normal (18 px), projection 1 280 à 1 440 ; **masqués** à 1 440 normal (0 px de large, comme prévu dans les notes) ; entiers seulement en projection 1 600. En projection à 1 280, le sélecteur de scénario et le sélecteur de modèle sont réduits à leur chevron, l'indicateur à « L G » (ordre de repli voulu par la spec) | conforme aux notes | Playwright |
| 2 | 1 280 × 650 à **125 %** (émulé, 1 024 × 520), normal et projection, Chromium et Edge | légende non recouverte | légende dégagée de **53 px** (normal) et **59 px** (projection) ; barre sur une ligne, « Réinitialiser » entier | OK | Playwright |
| 2 | 1 280 × 650 à **150 %** (émulé, 853 × 433), normal et projection, Chromium et Edge | légende non recouverte | légende dégagée de **20 px** : critère tenu. **Mais « Réinitialiser » sort de la barre** : bord droit à 967 px pour une barre qui finit à 845 (**122 px**, normal ; le sélecteur de thème sort aussi) et 961 px (**116 px**, projection) ; défilement horizontal de la page ; le panneau Fenêtre ouvert est alors coupé à droite (capture `edge-window-150.png`). Le matin, avec le code d'avant le lot et la même émulation, la barre tenait à 853 px (« Réinitialiser » visible, capture `run6\pw\n26-8-fenetre-150.png` de la séance du matin) : **régression du lot K** hors du critère du point 2 (qui ne porte que sur la légende), voir anomalie K1 | OK (critère) ; **KO** (régression) | Playwright |

## Étape 6 : point 5 (A4), sélecteur de thème après « Précédent »

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 5 | Chromium : atelier, « Sombre », clic sur l'indicateur du modèle (lien vers `/diagnostic`, vraie navigation), « Clair », `page.go_back()` | atelier clair, sélecteur « ☀ Clair » | après retour (`navigation.type` **back_forward**) : `data-theme` light, `localStorage` light, sélecteur **light**, face **☀** | OK | Playwright |
| 5 | Chromium, même suite, retour par `history.back()` | idem | idem : sélecteur **light**, face ☀, thème light | OK | Playwright |
| 5 | Edge 154, les deux retours | idem | idem dans les deux cas : sélecteur **light**, face ☀, thème light | OK | Playwright (Edge) |
| 5 | vrai bouton « Précédent » du navigateur (Alt+← dans Edge et Chromium en fenêtre) | idem | **non fait** : Playwright envoie la touche dans la page, pas à l'interface du navigateur (aucune navigation). Le type de navigation de `go_back` et `history.back()` est le même (`back_forward`) | non fait (à la main) | — |

## Étape 7 : point 6 (A8), `aria-expanded` et pied du panneau Fenêtre

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 6 | Edge 154 : scénario « Sous-agent », « Afficher les actions forcées », « Déléguer au sous-agent » ; « Annuler » ; rouvrir ; re-cliquer | `aria-expanded` `true` ouvert, `false` fermé, dans l'arbre d'accessibilité | attribut et **arbre d'accessibilité** d'Edge (CDP `Accessibility.getFullAXTree`, nœud bouton « Déléguer au sous-agent », propriété `expanded`) : repos **false/False** ; ouvert **true/True** (formulaire et « Armer » visibles) ; « Annuler » **false/False** ; rouvert **true/True** ; re-clic **false/False** | OK | Playwright (Edge), DevTools par CDP |
| 6 | Chromium, même suite | idem | identique | OK | Playwright |
| 6 | 1 280 × 650 à 100, 125 et 150 % (émulé), « Fenêtre ▾ », Edge et Chromium | « Appliquer » et « Fermer » visibles en pied sans défiler | les deux boutons **dans la fenêtre et au premier plan** (`elementFromPoint`) aux trois zooms : haut à 577, 447 et 360 px pour 650, 520 et 433 px de haut ; la zone des choix défile au-dessus (570 px de contenu pour 495, 365, 278 px visibles). À 150 %, le panneau est coupé à droite (anomalie K1) | OK | Playwright (Edge et Chromium) |
| remarque | chargement d'une page neuve dans Edge | aucune erreur de console | `404` sur **`/favicon.ico`** à chaque profil neuf d'Edge (Chromium ne le demande pas) : sans effet, message rouge dans la console | remarque | Playwright (Edge) |

## Étape 9 : point 8 (A6), installation de llama-server

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 8 | bloc « Installation » de P5 (`cmd-llama-install` du cahier, tête `1eae76c`) extrait tel quel, seule modification `$dest` suffixé `-lotk` ; exécuté dans un `powershell.exe` 5.1 neuf (`-NoProfile`, version **5.1.26100.8875**), sans droits d'administrateur | `$asset.name` = `llama-bNNNNN-bin-win-cpu-x64.zip`, version affichée, code 0 | `$asset.name` **`llama-b11256-bin-win-cpu-x64.zip`** (première des dix dernières releases qui porte l'archive) ; `version: 0.5.0-dev (build 11256, commit c85b92c69)`, « built with Clang 20.1.8 for Windows x86_64 » ; **`$LASTEXITCODE` 0** ; 66 s ; décompressé dans `%LOCALAPPDATA%\llama.cpp\b11256-lotk` ; aucune élévation, ni AppLocker ni SmartScreen | OK | PowerShell 5.1 |

## Étape 4 : point 3 (A5), scénarios avec le 2B

2B intégré, fenêtre 4 096, run2 (budget fixe 6 144 Mo resté dans le jetable, sans effet sur le
2B), Outlook et Teams fermés, Edge ouvert. Journal : `<scratchpad>\run2\events.jsonl`.

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 3a | « Lazy loading », prompt 1 (t3) | appel de `local__define_term`, « Model Context Protocol » | `load_tool_doc(local__define_term)` trigger model, puis **aucun appel de `local__define_term`** ; réponse « MCP signifie **Model Context Protocol**. … » (de tête, après la documentation) ; 49 s | secours nécessaire | script |
| 3a | secours : `arm` kind `tool` `local__define_term` `{"term": "MCP"}` (préréglage « MCP »), « Rejouer le dernier prompt » (t4) | appel `trigger user`, « Model Context Protocol » | `tool_started` **`local__define_term` trigger user** `{"term": "MCP"}`, ok ; réponse « MCP signifie **Model Context Protocol** (Protocole de contexte du modèle). … » ; 47 s ; aucune requête sortante (serveur local) | OK | script |
| 3b | « Métier SOC », prompt 1 (t5) puis 2 (t6), sans secours | tour 1 `completed` ; `h1 block` au tour 2 | t5 : **aucun appel** (« Je ne peux pas lire directement le fichier `alertes_siem.log` … Pourriez-vous copier-coller le contenu ») alors que `read_file` est décrit (83 tokens) ; t6 : aucun appel, pas de H1 | secours nécessaire | script |
| 3b | scénario relancé ; `arm` `read_file` `alertes_siem.log` (préréglage « Alertes SIEM (SOC) »), prompt 1 (t7) ; prompt 2 (t8) ; `arm` `read_file` `confidentiel/comptes_privilegies.txt` (préréglage « Comptes à privilèges »), rejeu (t9) | tour 1 `completed` ; `h1 block` au tour 2 ; escalade | t7 : h1 allow, `read_file` trigger user ; réponse de **285 tokens, `stop_reason` stop, tour `completed`** (plus de coupure à 512) : chronologie en 6 étapes (02:03 à 02:40, adm.leroy, groupe Admins du domaine, antivirus, 2,3 Go sortants) mais « aucun incident critique » et **aucune tactique MITRE** ; t8 : aucun appel, noms de fichiers inventés (`notes_reseaux.txt`…), pas de H1 ; t9 : **`hook_decided h1 block`** « … dans le dossier confidentiel, dont la lecture est interdite », tour `completed` ; réponse « La lecture est interdite par un hook. … je dois vous transmettre ce fichier directement » : **ni analyste ni habilité** | OK (critères, par les deux secours) ; escalade absente | script |
| 3b | « Métier IAM », prompt 1 (t10) | ≥ 1 appel, deux liens learn.microsoft.com, pas de débordement | `mslearn__microsoft_docs_search` trigger model, 1 `outbound_request` POST `https://learn.microsoft.com/api/mcp`, résultat 1 153 tokens gardés sur 5 275 ; jauge 2 357 / 3 584 ; **2 liens** (`…/entra/fundamentals/security-defaults#enforced-security-policies`, `…/entra/identity/authentication/concept-mfa-licensing`) ; `completed`, 118 s | OK | script |
| 3b | « Vider la conversation », prompt 2 (t11) | idem | 1 appel `mslearn__microsoft_docs_search`, 1 153 / 5 222 tokens ; jauge 2 367 / 3 584, **aucun `context_overflow`** (le matin : 3 967 / 3 584) ; mais réponse coupée par la réserve (**512 tokens, `stop_reason` length, tour `limit`**) avant tout lien : **0 lien** (longue explication de PIM, exemple inventé d'« étudiant ») ; 142 s | **KO** (liens) | script |
| 3b | « Métier Souveraineté », prompt 1 (t12) | appel de `datagouv__search_datasets`, requête vers mcp.data.gouv.fr | `load_tool_doc(datagouv__search_datasets)` trigger model, puis **aucun appel** ni requête sortante pendant le tour ; réponse de méthode (« Commence par l'outil `datagouv__search_datasets` » suivi d'une longue liste de mots-clés) ; `completed`, 88 s | secours nécessaire (suite après la pause) | script |

**Pause de 17:22 à 17:44** (appel Teams d'Anaël) : aucun tour en cours, WaveStack (run2) resté
lancé et inactif. Reprise Teams et Outlook refermés (Edge : 22 processus, 1 346 Mo ; 5 249 Mo
libres).

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 3b | Souveraineté, secours du prompt 1 : `arm` `datagouv__search_datasets` `{"query": "cybersécurité"}` (préréglage « cybersécurité », `page` et `page_size` vides non envoyés), rejeu (t13) | une `outbound_request` vers mcp.data.gouv.fr ; vrais jeux cités | `tool_started` **trigger user**, ok ; **1 `outbound_request` POST `https://mcp.data.gouv.fr/mcp`** ; résultat : 7 jeux (« Recensement de l'offre en cybersécurité », « Tableau de suivi ANSM », « Challenge Cyber "Passe ton hack d'abord" »…) ; réponse : **titres, identifiants, organisations et liens repris du résultat** (4 jeux), mais descriptions en partie brodées (« Tableau de suivi ANSM : un suivi des indicateurs de cybersécurité ») ; réponse coupée par la réserve (**512 tokens, tour `limit`**) ; jauge 1 887 / 3 584 ; 136 s | OK (critère) ; remarques | script |
| 3b | « Vider la conversation », prompt 2 (t14) | appel de `mslearn__microsoft_docs_search` | le 2B **appelle `mslearn__microsoft_docs_search` sans avoir chargé sa documentation** : `tool_call_malformed` « La documentation de « mslearn__microsoft_docs_search » n'est pas chargée : appelle d'abord load_tool_doc … » (lazy loading) ; au lieu de `load_tool_doc`, il répond de tête (généralités) ; **0 requête sortante** ; `completed`, 61 s | secours nécessaire | script |
| 3b | secours : `arm` `mslearn__microsoft_docs_search`, préréglage « Journalisation des connexions admin (Souveraineté) », rejeu (t15) | une `outbound_request` vers learn.microsoft.com ; aucune réponse inventée | `tool_started` **trigger user**, 1 153 tokens gardés sur 5 676 ; **1 `outbound_request` POST `https://learn.microsoft.com/api/mcp`** ; réponse tirée du résultat (journaux de connexion dans Monitoring & health, filtres « Agent type », `auditLogs/signIns` de Graph, Entra Connect 2.4.129.0 et source « Entra Connect Admin Actions ») ; `completed`, 320 tokens, 103 s ; jauge 2 152 / 3 584 | OK | script |
| 3b | bilan Souveraineté | une `outbound_request` par serveur, aucune réponse inventée | data.gouv.fr 1 (t13), learn.microsoft.com 1 (t15), **toutes deux par les secours** ; sans secours (t12, t14) aucune requête et des réponses de tête | OK (par les secours) | script |
| sous-agent | « Sous-agent », prompts 1 à 3 (t16 à t18) ; jauge avant l'envoi du prompt 4 ; prompt 4 (t19) | noter la jauge du prompt 4 (constat reporté de la revue, modèle d'historique du test `fits`) | t16 : `delegate` **trigger model**, sous-agent `read_file(guide_harnais.md)`, `subagent_ended` completed, réponse de 470 tokens, 225 s ; quiz t17, t18 : 29,7 et 27,2 s, `prompt_ms` 2 969 et 3 234, aucun `prefix_not_reused`, aucune redélégation. **Jauge avant le prompt 4 : 2 675 / 3 584 (74,6 %)** (dernier contexte rendu, t18) ; aperçu sans historique : 1 326 (= la valeur du test `fits`). **Prompt 4 (t19) : 2 997 / 3 584 (83,6 %, « ⚠ … Contexte plein à 83,6 % » dans Edge)**, marge 587, pas de débordement, 28,6 s. Historique réel des trois échanges ≈ **1 650 tokens** (2 997 − 1 326 − ≈ 20 de prompt), contre **570** simulés par le test (un seul échange) et **2 267** au pire cumulé (réponses à la réserve) : le modèle d'un seul échange sous-estime d'environ 1 080 tokens, le pire cumulé surestime d'environ 620. Un décompte cumulé avec des réponses de 250 tokens (réponses mesurées : 470, 245, 223, 213) tiendrait | constat noté | script, Playwright (Edge) |

## Étape 5 : point 4 (A3), llama-server borné sous la fenêtre choisie

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 4 | 2B intégré, `context_window` 8 192 (enregistré : `settings.json` jetable `{'window': 8192}`) ; WaveStack arrêté ; `llama-server.exe` b11239 `-m <jetable>\models\Qwen3.5-2B-Q4_K_M.gguf --port 8080 -np 1 -c 4096` (« listening » en 3 s, `n_slots = 1, n_ctx_slot = 4096`) ; relance (run3), choix de « Local · llama-server · Qwen3.5-2B-Q4_K_M.gguf · 2B » ; relance (run4) | llama-server repris, 8 192 configuré, 4 096 effectif | run4 : modèle actif `kind` server repris ; `configured` **8 192**, `window` **4 096**, `window_source` server, `bound_fr` « bornée à 4 096 par llama-server (-c) » | OK | script |
| 4 | bouton et infobulle au premier affichage (Edge 154, 1 600 × 1 000) | « Fenêtre 4 096 ▾ », infobulle « …, 8 192 choisi. » | bouton « **Fenêtre 4 096 ▾** » ; infobulle « **Fenêtre de contexte : 4 096 tokens, bornée à 4 096 par llama-server (-c), 8 192 choisi.** » (capture `run4\edge-bouton-fenetre.png`) | OK | Playwright (Edge) |
| 4 | `/api/diagnostic` et page `/diagnostic` (Edge) | conseil « relancez-le avec `-np 1 -c 8192` » | API et page : « Modèle retenu : Qwen3.5-2B-Q4_K_M.gguf, servi par llama-server (http://127.0.0.1:8080) (choisi lors d'un lancement précédent). **llama-server a été lancé avec un contexte de 4 096 tokens par emplacement, sous la fenêtre choisie de 8 192 : la fenêtre effective reste de 4 096 tokens. Arrêtez-le et relancez-le avec `-np 1 -c 8192`.** » (ligne `model` en `warn` ; le conseil paraît déjà au choix du modèle en run3, « changé sans relance ») (capture `run4\edge-diagnostic.png`) | OK | script, Playwright (Edge) |
| 4 | llama-server arrêté ; 2B intégré choisi ; `context_window` 4 096 | retour à l'état de départ | 2B intégré actif, 4 096 appliqué (rechargement 4,2 s), `window_source` configured ; plus aucun processus `llama-server` | OK | script |

## Étape 8 : point 7 (A7), compte rendu du skill

| Point | Geste | Attendu | Obtenu | Statut | Moyen |
|---|---|---|---|---|---|
| 7 | « Skills », prompt suggéré (run1, t4, 16:58 ; Teams encore ouvert : pas une mesure de temps) | `load_skill`, aucun `read_file`, compte rendu de la réunion du prompt (Paul, Julie, lundi 10 h), ni Alice ni Bruno | appel 1 : **`load_skill({"skill": "meeting_minutes"})` trigger model** ; appel 2 : réponse directe, **aucun `read_file`** (aucun autre `tool_started`) ; « Voici le compte rendu de la réunion : **Présents** : Paul, Julie ; **Décisions** : Budget présenté par Paul, Planning validé par Julie ; **Actions** : Aucune action spécifique à définir ; **Prochaine réunion** : Lundi à 10 h » ; **ni Alice ni Bruno** ; tour `completed`, 194 s (lecture lente, 10,9 tokens/s, poste chargé par Teams à ce moment) | OK | script |

## Anomalies et constats

| # | Point | Anomalie | Cause probable | Criticité | Correction proposée (non appliquée) |
|---|---|---|---|---|---|
| K1 | 2 (et 6) | À 1 280 × 650 zoomé à **150 %** (853 px CSS, émulé ; Chromium et Edge), « **Réinitialiser** » sort de la barre de **122 px** (normal ; le sélecteur de thème aussi) et **116 px** (projection), la page défile horizontalement et le panneau Fenêtre ouvert est coupé à droite. Avant le lot, à la même largeur, la barre tenait (seule la légende était recouverte) | Lot K : les éléments de la barre ne cèdent plus assez sous 1 024 px (les replis décrits s'arrêtent là : « sous 1 100 px, le titre disparaît et la puce peut céder ») ; aucun contrôle E2E sous 1 024 px. Le critère du point 2 à 150 % ne portait que sur la légende | Moyenne : 150 % est un zoom courant sur un portable de 1 280 px ; « Réinitialiser » hors de vue en formation | Palier `@media (max-width: 900px)` : légende de la jauge réduite à ses pastilles (texte en infobulle), mots de « Projection » et « LLM » retirés, sélecteurs de scénario et de modèle à leur chevron ; contrôle E2E à 853 × 433 (« Réinitialiser » entier, pas de défilement horizontal, légende dégagée), normal et projection |
| K2 | 3 (IAM p2, Souveraineté p1) | La réponse atteint la réserve de sortie (**512 tokens, tour `limit`**) : IAM p2 sans aucun des deux liens demandés (longue explication de PIM, exemple inventé) ; Souveraineté p1 (avec secours) coupée après 4 jeux | Le 2B développe au-delà du nécessaire ; les liens viennent en fin de réponse | Moyenne (IAM : critère « deux liens » non tenu) | Prompts : « en 6 lignes au plus, puis les deux liens » (comme SOC) ou « commence par les deux liens » ; Souveraineté p1 : « liste 3 jeux au plus, avec leur lien » |
| K3 | 3 (Lazy, SOC, Souveraineté) | Sans secours, le 2B n'appelle pas l'outil : Lazy p1 répond après `load_tool_doc` ; SOC p1 et p2 répondent « je n'ai pas accès aux fichiers » (`read_file` pourtant décrit) ou inventent des noms de fichiers ; Souveraineté p1 répond après `load_tool_doc`, p2 appelle l'outil MCP sans documentation (`tool_call_malformed`, lazy loading) puis répond de tête. Avec les secours « Forcer l'appel », tous les critères sont tenus | Comportement du 2B (non déterministe : le matin, SOC p1 appelait `read_file`) ; le lot corrige par les secours, comme le prévoit la décision | Faible (les consignes décrivent les secours) ; à connaître pour l'animation | Rien au code ; dans la consigne SOC, présenter le secours comme probable avec le 2B. À trancher : en lazy loading, quand le modèle appelle un outil MCP connu non chargé, charger sa documentation d'office et exécuter l'appel |
| K4 | 3 (SOC p2) | Après le blocage H1, la réponse ne nomme ni analyste ni personne habilitée (« je dois vous transmettre ce fichier directement ») | Petit modèle | Faible (la consigne prévoit que le formateur conclue) | Ajouter au prompt 2 « en 3 lignes, en nommant qui est habilité » |
| K5 | 1 | Hausse mesurée de mémoire privée **72 Mo** (trois fois) pour **48 Mio** annoncés à 4 096 → 8 192 (2B) ; 4B 4 096 → 16 384 : +491 Mo privés, +391 RSS pour 384 (dans ± 30 %) | Mémoire qui croît avec la fenêtre hors cache d'attention (tampons de calcul), plus visible sur le petit écart du 2B | Faible (ordre de grandeur juste ; l'écart × 4 est corrigé) | Aucune ; éventuellement un terme par token mesuré par la sonde |
| K6 | 3 (test `fits`, constat reporté) | Sous-agent p4 : historique réel des trois échanges ≈ 1 650 tokens (jauge 2 675 avant l'envoi, 2 997 / 3 584 au prompt 4), contre 570 simulés (un seul échange) et 2 267 au pire cumulé | Modèle d'historique du test | Faible | Historique cumulé avec des réponses de ≈ 250 tokens (mesurées : 470, 245, 223, 213) plutôt que la réserve entière : le scénario tiendrait (≈ 3 000 / 3 584) |
| K7 | 5, 6 | Edge demande `/favicon.ico` : 404 en console à chaque profil neuf | Pas d'icône servie à cette adresse | Très faible | Servir l'icône à `/favicon.ico` ou un `<link rel="icon">` sur chaque page |
| K8 | 1 (E2E) | Une erreur de console de plus que sur le poste de développement : `ERR_CONNECTION_REFUSED` (4 au lieu de 3) | Réseau coupé du parcours ; dépend de l'ordre des requêtes | Très faible | Aucune |

## Synthèse

| Point | Anomalie | Statut | Mesures clés |
|---|---|---|---|
| 1 | A2 · coût du cache hybride | **OK** | Panneau 2B : 48 / 96 / 192 Mo (avant : 192 / 384 / 768), sans nouvelle sonde ni réécriture (empreinte du jetable identique, 49 152 gardé dans le fichier). 2B 4 096 → 8 192 : +72 Mo privés pour 48 annoncés (K5). 4B à 16 384 sous budget fixe 6 144 Mo : **accepté** (avant : refusé), rechargement 5,4 s, +391 Mo RSS / +491 Mo privés pour 384 annoncés |
| 2 | A1 · puce « · lié » | **OK** (critère) ; **régression K1** | Puce entière (0 px, et 0 px avec 10 px de marge) à 1 280, 1 366, 1 440, 1 600, normal et projection, Chromium et Edge ; barre sur une ligne ; légende dégagée à 125 % (53 px) et 150 % (20 px). À 150 %, « Réinitialiser » sort de la barre (116 à 122 px) |
| 3 | A5 · scénarios avec le 2B | **OK par les secours** ; **KO partiel** (IAM p2) | Lazy : `local__define_term` trigger user, « Model Context Protocol ». SOC : tour 1 `completed` (285 tokens), `h1 block` au tour 2 (les deux par lecture forcée). IAM : p1 deux liens ; p2 sans débordement (2 367 / 3 584) mais coupé à 512 sans lien (K2). Souveraineté : 1 requête data.gouv.fr et 1 learn.microsoft.com, vrais jeux cités (par les secours). Sous-agent : jauge 2 675 avant le prompt 4, 2 997 au prompt 4 (K6) |
| 4 | A3 · llama-server borné | **OK** | Bouton « Fenêtre 4 096 ▾ », infobulle « …, 8 192 choisi. » ; conseil « relancez-le avec `-np 1 -c 8192` » dans l'API et la page |
| 5 | A4 · thème après « Précédent » | **OK** (vrai bouton : à la main) | Sélecteur « ☀ Clair » après `go_back` et `history.back()`, Chromium et Edge |
| 6 | A8 · `aria-expanded`, pied du panneau | **OK** | `expanded` True / False juste dans l'arbre d'accessibilité d'Edge ; « Appliquer » et « Fermer » visibles à 100, 125 et 150 % |
| 7 | A7 · compte rendu du skill | **OK** | `load_skill`, aucun `read_file`, Paul, Julie, lundi 10 h, ni Alice ni Bruno |
| 8 | A6 · installation de llama-server | **OK** | `llama-b11256-bin-win-cpu-x64.zip`, build 11256, `$LASTEXITCODE` 0, PowerShell 5.1 |

Tests automatiques : ruff propre, pytest 1 253 réussis, `fits` réussi (marge `mcp_full` 380), E2E
654 réussies et 0 échec.

## Reste à la main pour Anaël

- Point 2 : **vrai zoom d'Edge** à 125 et 150 % sur 1 280 × 650 (ici émulé par le viewport) :
  confirmer K1 (« Réinitialiser » hors de la barre à 150 %) et la légende dégagée ; lisibilité
  des sélecteurs réduits à leur chevron en projection à 1 280.
- Point 5 : vrai bouton « Précédent » du navigateur (Chrome et Edge) : « Sombre », `/diagnostic`,
  « Clair », « Précédent » → sélecteur « ☀ Clair ».
- Point 6 : **lecteur d'écran** (Narrateur) sur « Déléguer au sous-agent » : « développé » /
  « réduit » annoncés.
- Point 3 : **avis sur les réponses du 2B** (chronologie SOC sans MITRE et « aucun incident
  critique », escalade absente, descriptions brodées des jeux data.gouv.fr, IAM p2 sans liens) ;
  décider des suites de K2 et K3, et de la question AD-17 (toujours ouverte).

## Nettoyage

Fait : llama-server arrêté ; 2B intégré et fenêtre 4 096 remis dans WaveStack (run4) ; captures
E2E restaurées ; dossier réel vérifié à 17:59 (`settings.json` 9 272 octets `FA634B52…`,
`api_keys.json`, `memory.json`, `audit.log` inchangés). Laissé en place : WaveStack run4 lancé
sur le dossier jetable (budget fixe 6 144 Mo dans le jetable) pour vos gestes ;
`<scratchpad>\wsdata` (copie et liens physiques : les supprimer n'efface pas les originaux) ;
`%LOCALAPPDATA%\llama.cpp\b11256-lotk` (installation du point 8, sans effet sur WaveStack, à
supprimer à volonté). Dépôt en tête détachée sur `1eae76c` ; `git status` : seul ce fichier est
nouveau. Pour arrêter WaveStack :
`Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object CommandLine -match "launch.py" | ForEach-Object { Stop-Process -Id $_.ProcessId }`.
﻿﻿
## Contre-vérification indépendante (autre session Claude Code, 2026-09-29, 18:05 à 18:30)

Tête détachée `1eae76c` (`origin/claude/lot-k-recette-pc`), dossier de données jetable, 2B
intégré, fenêtre 4 096. Edge ouvert (onglet de l'extension), Teams fermé.

| Contrôle | Obtenu | Statut |
|---|---|---|
| ruff, format | « All checks passed! », « 148 files already formatted » | OK |
| pytest | **1253 passed, 3 skipped, 7 deselected** (14 min 50 s) | OK |
| fits (vrai tokenizer) | `test_every_scenario_fits_the_default_window_with_every_prompt` passed | OK |
| E2E | **654 réussies, 0 en échec** ; captures restaurées | OK |
| Point 1 | panneau Fenêtre du 2B : 48 / 96 / 192 Mo | OK |
| Point 2 | après un tour (« Combien font 12*37 ? ») : puce « ● + Contexte LLM · lié » entière (manque 0 px) à 1 280, 1 366, 1 440, 1 600, normal et projection ; barre sur une ligne, « Réinitialiser » visible. Les chiffres de la jauge cèdent désormais à toutes les largeurs sauf 1 600 en projection. Sans tour à l'écran, la puce non liée cède (voulu, commit `05e83d8`) | OK |
| K1 | zoom 150 % émulé : 1 280 de large (853 px CSS) → « Réinitialiser » à 967 px, **114 px hors de la fenêtre**, défilement horizontal de 114 px ; 1 366 (911 px CSS) → 56 px ; 125 % (1 024 px) → tient | **KO (régression confirmée)** |
| Point 5 | Chromium (`go_back`) et Edge (`history.back()`) : atelier clair, sélecteur « ☀ Clair » ; aucune erreur de console. Dans Edge, la page est revenue sans navigation `back_forward` (cache de retour), donc le cas exact du matin n'est pas rejoué | OK |
| Point 6 | panneau Fenêtre à 100, 125, 150 % : « Appliquer » visible (plus de défilement interne) | OK |
| Point 3, sans secours | Lazy p1 : `load_tool_doc` puis réponse inventée « Machine Learning Contextual Prompting ». Souveraineté p1 : `load_tool_doc`, aucune recherche, mais la réponse affirme « J'ai effectué une recherche sur data.gouv.fr » et invente des jeux. SOC p1 : 8 lignes, `completed` (entre dans l'historique) ; SOC p2 : `read_file` notes_reunion.txt, « . », puis **h1 block** sur `confidentiel/comptes_privilegies.txt`, réponse « Transmettez ce fichier au **Démonstrateur** » (ni « analyste » ni « habilité »). IAM p1 et p2 : 1 appel chacun, réponses **coupées à 512 tokens** (`limit`), sans lien ; p2 ne déborde plus parce que p1, `limit`, est hors de l'historique | Lazy KO, Souveraineté KO, SOC partiel, IAM KO |
| Point 7 | Skills p1 : `load_skill(meeting_minutes)`, aucun fichier lu, compte rendu Paul, Julie, lundi 10 h | OK |
| Branches | `origin/claude/lucid-cori-1rkbjf` (PR #2) a reçu depuis `a2722ce`, `4b830b0` (story 28 : guide et cahier), story 30 ; le lot K ne les contient pas (`merge-base --is-ancestor` faux) : rebase nécessaire avant fusion, conflit probable sur le cahier (point 8) | à faire |
