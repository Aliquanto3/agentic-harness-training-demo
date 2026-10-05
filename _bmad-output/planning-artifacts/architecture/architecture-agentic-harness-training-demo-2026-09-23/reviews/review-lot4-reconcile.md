# Réconciliation lot 4 : EXPERIENCE.md « Atelier MCP en séquence » ↔ AD-27 / AD-28

Date : 2026-10-05. Entrées : EXPERIENCE.md, section « Atelier MCP en séquence (lot 4 du 2026-10-04) » (l. 320-610) ; plan de corrections du 2026-10-04, lot 4. Spine : AD-27, AD-28 et les paragraphes « Lot 4 du 2026-10-04 » d'AD-2, AD-3, AD-18, AD-19 (et AD-26).

Méthode : chaque fait que la page doit recevoir de la session (AD-1 : la page met en forme, elle ne calcule rien) est cherché dans un champ nommé d'un événement ou de `GET /api/mcp_lab`. Quand la spine ne le nomme pas mais que le code actuel le fournit déjà, la ligne le dit (« existant »). Le code a été lu pour vérifier trois points : `describe_error` (`mcp/connection.py:44`), `_mcp_lab_servers` et `mcp_lab_state` (`session/app_session.py:9424-9468`), l'arrêt d'une connexion (`_run_mcp_lab_connect`).

## Bilan

| Statut | Nombre |
|---|---|
| couvert | 75 |
| manquant | 13 |
| contradiction | 6 (+ 2 points non comptés : ambiguïté de `tools/list`, questions ouvertes devenues caduques) |
| **Total** | **94** |

## Tableau

### A. Volet Serveurs et commandes

| # | Besoin | Source EXPERIENCE | Couvert par | Statut |
|---|---|---|---|---|
| 1 | Liste des serveurs : nom, `Local` / `🌐 RÉSEAU`, transport, adresse ou commande de lancement, ce qui sort du poste (« ⓘ ») | Serveurs et commandes, « Serveurs » | AD-18 `GET /api/mcp_lab.servers` (`label_text`, `transport`, `url`, `command`, `network`, `sends_text`) | couvert |
| 2 | Serveur connecté marqué « connecté » | idem | `open_server` ; `mcp_lab_connect_ended.status = ok` | couvert |
| 3 | Échec : carte « injoignable » et raison sous les cartes | idem | `mcp_lab_connect_ended{status: error, error_text}` | couvert |
| 4 | Commandes indisponibles hors `idle`, raison dans un bandeau ; « Arrêter » actif seulement en `mcp_lab` | « Boutons » | AD-3 `session_state{state, reason_text}` | couvert |
| 5 | Comptes des onglets « 🔧 Outils n », « 📄 Ressources n », « 💬 Prompts n » tirés des listes reçues | « Onglets des primitives » | AD-27 `connect_ended.tools`, `.resources`, `.prompts` | couvert |
| 6 | Capacités lues dans la réponse à `initialize`, jamais en dur | idem | AD-27 `connect_ended.capabilities` (+ `server_info`, `protocol_version`) | couvert |
| 7 | Onglet barré « ⊘ » (capacité non annoncée) contre onglet actif « Aucune ressource » (annoncée, vide) | idem | AD-27 `resources` / `prompts` : `null` = non annoncée, `[]` = annoncée et vide | couvert |
| 8 | Liste facultative annoncée mais en échec (`resources/list` en erreur) | (absent) | AD-27 : la liste vaut `null` comme une capacité non annoncée, l'erreur va dans `list_errors[{method, error_text}]`, la connexion reste `ok`. EXPERIENCE n'a aucun texte pour ce cas : appliquée telle quelle, sa règle « null → barré, Ce serveur n'annonce pas de ressources » serait fausse. | contradiction |
| 9 | Préréglages, un champ par paramètre (texte, nombre, case, JSON) | « Outils », à la main | `call_presets` ; `connect_ended.tools[].schema` | couvert |
| 10 | Disponibilité du mode « Par le modèle » et ses trois raisons (pas d'appel d'outils, aucun modèle, pas `idle`) | « Outils », par le modèle | AD-18/AD-27 `ask{available, reason_text, tools, model}`, relu après `model_load_ended` ; `session_state` | couvert |
| 11 | « Envoyer au modèle » (ressource, prompt) : « mêmes conditions de disponibilité que le mode Par le modèle » | « Envoyer au modèle » | AD-27 : avec `of`, il suffit qu'un modèle soit chargé (`doc_mode = none` sans appel d'outils). EXPERIENCE se contredit d'ailleurs elle-même (« un modèle qui n'appelle pas d'outils reçoit la ressource… sans ce bloc »). | contradiction |
| 12 | Disponibilité distincte des deux usages d'`ask` (sans `of` : appel d'outils requis ; avec `of` : un modèle suffit), chacun avec sa raison | « Outils », « Envoyer au modèle » | `ask.available` et `ask.reason_text` sont uniques : la page devrait recombiner `tools`, `model` et l'état pour savoir si « Envoyer au modèle » est permis | manquant |
| 13 | Ligne « {modèle} · 🌐 RÉSEAU · {fournisseur} » sous le bouton | « Envoyer au modèle » | `ask.model: ActiveModel{label, hosting, provider}` | couvert |
| 14 | Ressources : URI, titre, type | « Ressources » | `connect_ended.resources[{uri, name, title, mime_type, description}]` | couvert |
| 15 | Prompts : arguments, requis marqués | « Prompts » | `connect_ended.prompts[].arguments[{name, description, required}]` | couvert |
| 16 | Envoi d'une ressource lue ou d'un prompt obtenu, sans renvoyer le contenu depuis la page | « Ressources », « Prompts » | AD-27 `mcp_lab_ask{of}` = `step_id` de la lecture ou du prompt ; contenu gardé par la session | couvert |

### B. Volet Séquence

| # | Besoin | Source EXPERIENCE | Couvert par | Statut |
|---|---|---|---|---|
| 17 | Nom du modèle dans la colonne SLM ; « Modèle · 🌐 RÉSEAU · {fournisseur} » pour un cloud | « Colonnes » | `ask.model` (avant tout envoi) ; `mcp_lab_model_started.model` | couvert |
| 18 | Nom de la source de données par serveur (`glossary.yaml`, « API data.gouv.fr », « Docs Microsoft ») et libellé de la flèche Serveur → Source (« lit glossary.yaml ») | « Colonnes », table des flèches, lignes de phase | Rien : ni `servers` (AD-18, code `_mcp_lab_servers`), ni AD-19, ni la liste « Textes et aides » ne portent un texte de source par serveur | manquant |
| 19 | Flèche JSON-RPC : puce de méthode, durée | Table des flèches | `mcp_lab_message.method`, `elapsed_ms` | couvert |
| 20 | Résumé de chaque réponse, en direct (« 2 outils », « 1 bloc texte », « capacités : tools · resources · prompts ») | Table des flèches ; ligne 3 de la poignée de main | `mcp_lab_message` n'a pas de résumé. `connect_ended` n'arrive qu'à la fin. La page devrait compter dans `jsonrpc`, ce que le *Prevents* d'AD-27 interdit (« deviner une capacité depuis le JSON capturé ») | manquant |
| 21 | Sorte du message : requête, réponse, notification « sans réponse », réponse `error` JSON-RPC (flèche rouge) | « Une notification porte… », état « Erreur JSON-RPC », nom accessible | Seulement implicite dans `jsonrpc` (présence de `id`, `result`, `error`) ; aucun champ nommé | manquant |
| 22 | Échec du transport : quelle requête porte ✖ et la raison (« Service injoignable (ConnectError) ») ; requête bloquée par la garde | « Une erreur porte… », états « Serveur injoignable », « Délai dépassé » ; Architecture, cas limites | `*_ended.error_text` donne la raison, mais rien ne désigne la requête restée sans réponse : la page devrait apparier les `id` JSON-RPC | manquant |
| 23 | Origine affichée par sorte de flèche (« capturé sur le transport », « dans l'hôte · déduit »…) | Table des flèches ; Voix | Rendu par type d'événement ; textes dans `McpLabContent` (AD-19) | couvert |
| 24 | Hôte → Client : « lance le serveur : python -m … » (stdio) ou « ouvre une session HTTP avec … » | Lignes, poignée de main, 1 | AD-27 `exchange_started.transport`, `launch_text` | couvert |
| 25 | Hôte → Client : « exécute {outil}(…) » | Lignes, appel d'outil, 4 | `exchange_started.tool`, `args` (à la main) ; `model_ended.tool_call{name, tool, arguments}` (par le modèle) | couvert |
| 26 | Puce modèle « question + 2 outils », « question + ressource + 2 outils », « prompt + 2 outils », avec les tokens | Table des flèches ; appel, 2 ; envoi, 2 | `mcp_lab_model_started.sends[{part, label_text, tokens}]`, `prompt_tokens`, `exact` | couvert |
| 27 | SLM → Hôte : « appel : define_term », durée de génération | Appel, 3 | `model_ended{outcome: tool_call, tool_call, duration_ms}` ; `model_call_ended.gen_ms` | couvert |
| 28 | Client → Hôte : texte du résultat, tokens ; Hôte → SLM : résultat d'outil | Appel, 9 et 10 | `call_ended{by: model, text, tokens, estimated}` ; `sends.part = tool_result` | couvert |
| 29 | Réponse finale et sa durée ; Hôte → Utilisateur : début de la réponse | Appel, 11 et 12 | `model_ended{outcome: answer, answer_text, duration_ms}` ; `ask_ended.answer_text` | couvert |
| 30 | Lazy loading : aller-retour `load_tool_doc` entre le SLM et l'hôte, sans message MCP | Appel, note lazy | `model_ended.outcome = meta_call` ; `sends.part = tool_doc` dans l'appel suivant | couvert |
| 31 | Appel à la main : « formulaire : define_term(…) », « à la place du modèle », fantômes 2, 3, 10, 11, 12 | Appel à la main | `exchange_started{exchange: call, by: hand, tool, args}` | couvert |
| 32 | Lecture : « choisit glossary://terms » ; « contenu · 64 tokens » | Lecture de ressource | `exchange_started.uri` ; `read_ended{tokens, estimated, text}` | couvert |
| 33 | Prompt : « choisit le prompt explain_term(term = « hook ») » ; « 1 message · 52 tokens » | Prompt | `exchange_started.prompt`, `args` ; `prompt_ended{messages, tokens}` | couvert |
| 34 | Titre « Envoi au modèle · {uri} » ou « · {prompt} » ; étape 1 : la question ou « envoie le prompt explain_term » | Phases ; envoi au modèle | `exchange_started.of`, `question` ; l'URI ou le nom se lisent dans le `read_ended` / `prompt_ended` du même `last_session` (jointure sur `step_id`) ; `phase_label` | couvert |
| 35 | Titres de phase (« Poignée de main · {serveur} », « Appel d'outil · à la main / par le modèle »…) | Phases | `exchange_started{exchange, server, by, phase_label}` | couvert |
| 36 | Synthèse de la poignée de main : « ouverte en 1 371 ms · 2 outils, 1 ressource, 1 prompt » ou « échec : {raison} » | Phases | `connect_ended{duration_ms, tools, resources, prompts, error_text}` | couvert |
| 37 | Synthèse d'un appel par le modèle ou d'un envoi : « part de la génération » | Phases | `ask_ended.model_ms` et `duration_ms` sont donnés, mais la part (rapport) serait calculée par la page | manquant |
| 38 | « Arrêter » pendant une poignée de main ou une requête : dernière requête marquée « arrêté », synthèse « arrêtée par l'utilisateur », clients non connectés (et non « injoignable ») | États, « Arrêté » | `connect_ended`, `call_ended`, `read_ended`, `prompt_ended` n'ont que `ok|error`. Aujourd'hui l'arrêt rend `status: error` avec `session.mcp_lab.stopped` : la page marquerait la carte « injoignable » et le fil en rouge, sauf à comparer des textes. Seul `ask_ended` a `cancelled` | manquant |
| 39 | Note « pas de resources/list ni de prompts/list : le serveur ne les annonce pas » | Poignée de main, 6 | `connect_ended.capabilities` (posée à la fin de l'échange) | couvert |
| 40 | Client → Hôte : « 2 outils · 1 ressource · 1 prompt » | Poignée de main, 7 | `connect_ended` | couvert |
| 41 | Encart : sens, légende, origine ; explication de la méthode (`methods.*`, huit méthodes) | « Déplier un message » | AD-19 lot 4 (`METHODS` à huit, validateur) | couvert |
| 42 | Encart d'une flèche vers un serveur public : sa requête HTTP sortante (`outbound-payload`) | idem ; Flow MCP-2, 1 | Les `outbound_request` sont sur `mcp{n}`, sans lien avec le `mcp_lab_message` qu'ils transportent ; un échange HTTP en compte plusieurs (POST par message, GET du flux, DELETE de fin). La page devrait apparier par le corps | manquant |
| 43 | Encart Hôte → modèle cloud : données sortantes | Colonnes ; état « Modèle cloud » | `outbound_request{origin: model}` sur `mcp{n}.c{k}` (AD-27, AD-26) | couvert |
| 44 | JSON indenté du message ; code et message d'une réponse `error` | « Déplier » ; état « Erreur JSON-RPC » | `mcp_lab_message.jsonrpc` | couvert |
| 45 | Stepper : une étape par flèche, ◀ ▶ quittent le direct, « Suivre le direct », suspension du défilement et puce « ↓ {n} nouveaux messages » | « Stepper du lot 2 » | AD-28 (trames opaques, la page décide), option `onLive(live)` | couvert |
| 46 | Annonce hors direct « Étape 4 sur 12 : Client MCP vers Serveur MCP, tools/call » | Accessibilité, « Flèche courante » | AD-28 : le module remplit le nœud `status` hors du direct, mais aucune option ne lui passe le nom de l'étape, que seule la page connaît | manquant |
| 47 | Restitution : dernière connexion et ses échanges reconstruits, en direct | « Restitution » ; « Données attendues » | AD-27 `last_session` (neuf `mcp_lab_*`, `model_call_started/ended`, `outbound_request`), `mcp/lab.KINDS` | couvert |
| 48 | Chronomètre de la flèche Hôte → SLM en attente, hors du nom accessible | États, « Échange en cours » | `ts` de `mcp_lab_model_started` (affichage seul) | couvert |

### C. Volet Ce que le modèle voit

| # | Besoin | Source EXPERIENCE | Couvert par | Statut |
|---|---|---|---|---|
| 49 | Total full / lazy, « compté par le modèle chargé » ou « estimé » | « Bloc outils » | `connect_ended.full_tokens`, `lazy_tokens`, `estimated` (AD-18 : moteur chargé, sinon `_count_tokens`) | couvert |
| 50 | Poids juste après un changement de modèle (connexion faite avec un autre modèle ou sans modèle) | « Bloc outils » ; « pendant le comptage, calcul… » | Le compte est figé à `connect_ended`. Aucun recomptage, et le modèle qui a compté n'est pas nommé : après `model_load_ended`, « compté par le modèle chargé » devient faux, comme la promesse d'AD-27 « le poids affiché est le poids envoyé » | manquant |
| 51 | État « calcul… » du total | États du volet | Entre la réponse à `tools/list` et `connect_ended` (`exchange_started` posé, pas de `*_ended`) | couvert |
| 52 | Tableau par outil : nom vu par le modèle `{serveur}__{outil}`, tokens ; en lazy loading, ligne du catalogue et `load_tool_doc` | « Bloc outils » | `tools[{name, tool, doc_tokens, line_text, line_tokens}]`, `load_tool_doc_tokens` | couvert |
| 53 | « Voir le JSON envoyé au modèle » | idem | `tools[].definition_text`, `lazy_definition_text` | couvert |
| 54 | Sélecteur « Documentation complète \| Lazy loading » : c'est le mode envoyé en « par le modèle » | idem | `mcp_lab_ask.doc_mode`, `model_started.doc_mode` | couvert |
| 55 | Envoi sans bloc « outils » (`doc_mode: none`, modèle sans appel d'outils) | (absent) | AD-27 ajoute `none`. EXPERIENCE ne prévoit que deux segments, sans texte pour un envoi qui part sans outils | contradiction |
| 56 | Bloc « Envoyé au modèle » : tokens à chaque appel, ce qu'ils contiennent, durée | « Après un échange » | `model_started{index, sends, prompt_tokens, exact}`, `model_ended.duration_ms` | couvert |
| 57 | Cloud : « 🌐 RÉSEAU · parti chez {fournisseur} » | idem | `model_started.model.provider` / `hosting` ; `outbound_request` sur `mcp{n}.c{k}` | couvert |
| 58 | Résultat réinjecté : texte, tokens, troncature au plafond, étiquette `isError` | idem | `call_ended{text, tokens, estimated, truncated, is_error}` (`truncated` porte déjà `{tokens, total_tokens, estimated}`, `_bound_result`) | couvert |
| 59 | Contenu de la ressource ; messages du prompt | idem | `read_ended{text, contents, tokens}` ; `prompt_ended{messages, text, tokens}` | couvert |
| 60 | Après l'envoi : « Envoyé au modèle avec votre question » / « Envoyés au modèle comme votre message » | idem | un `ask` dont `of` vise cette lecture ou ce prompt | couvert |
| 61 | États : avant connexion, « Liste des outils en cours… », échec « aucun outil listé » | « États » du volet | `exchange_started{exchange: connect}` puis `connect_ended` | couvert |
| 62 | Annonce du nouveau total au changement de mode | Accessibilité, « Annonces » | `full_tokens` / `lazy_tokens` déjà reçus | couvert |

### D. Volet Architecture

| # | Besoin | Source EXPERIENCE | Couvert par | Statut |
|---|---|---|---|---|
| 63 | Zones Poste et Réseau, un client par serveur, transport sur le fil (stdio, HTTP) | Poste, Réseau, Fils | `servers[].transport`, `network` | couvert |
| 64 | « 🔧 2 · 📄 1 · 💬 1 » sous le serveur connecté | « Après la poignée de main » | `connect_ended` | couvert |
| 65 | Clients et serveurs non connectés estompés, « non connecté » dans leur nom | idem | `open_server` | couvert |
| 66 | Robot : antenne clignotante seulement en direct, pendant une génération du mode « par le modèle » | « Robot » | `mcp_lab_model_started` sans son `*_ended`. Mais AD-27 traite de la même façon un envoi de ressource ou de prompt, qui génère aussi : la formule d'EXPERIENCE est trop étroite | contradiction |
| 67 | Échec de connexion : fil client → serveur rouge ✖ | « Échec de connexion » | `connect_ended.status = error` (voir #38 pour l'arrêt, confondu aujourd'hui avec un échec) | couvert |
| 68 | Dernier échec gardé par serveur jusqu'à une nouvelle tentative, perdu au rechargement `[ASSUMPTION]` | idem | Projection de la page. `last_session` part de la dernière connexion : les échecs antérieurs sont perdus au rechargement, comme le veut l'hypothèse. Nuance : si la dernière tentative a échoué, son ✖ revient, lui, après un rechargement | couvert |
| 69 | Serveur public indisponible au démarrage : `arch-node-unavailable` | « Cas limites » | `servers` ne porte ni état ni raison (code `_mcp_lab_servers`), et la page ne garde pas `architecture_changed` (AD-18). Rien ne fournit ce cas | manquant |
| 70 | Requête bloquée par la garde réseau : ✖ et raison de la garde | idem | `error_text` (`tools.network.blocked`, via `describe_error`) ; flèche fautive : voir #22 | couvert |
| 71 | Modèle cloud : robot en zone Réseau, fil en tirets à travers la frontière | idem | `ActiveModel.hosting` (`ask.model`, `model_started.model`) | couvert |
| 72 | Clic sur un bloc : explication et analogie du restaurant | « Clic sur un bloc » | AD-19 lot 4 (textes de `McpLabContent`) | couvert |
| 73 | Vue « Avant MCP \| Avec MCP » : textes, mémorisée avec la disposition | « Avant MCP \| Avec MCP » | AD-19 (contenu) ; AD-18, « État du navigateur » | couvert |
| 74 | Fermeture de la connexion hors « Arrêter » (connexion suivante, changement de langue, fermeture de session, mort du processus stdio) : clients revenus à « non connecté » | États ; AD-3 (fermetures) | Aucun événement : la page afficherait « connecté » jusqu'au rechargement (`open_server`) | manquant |

### E. États

| # | Besoin | Source EXPERIENCE | Couvert par | Statut |
|---|---|---|---|---|
| 75 | « Service injoignable (ConnectError) : le poste n'a pas accès à {hôte}. » | « Serveur injoignable » | `error_text` (existant : `tools.network.unreachable{kind, host}`) | couvert |
| 76 | « Le serveur n'a pas répondu dans le délai ({délai} s). », délai de connexion ou d'appel de `wavestack.toml` | « Délai dépassé » | `error_text` (existant : `mcp.error.timeout{timeout}`, `mcp_connect_timeout_s` / `mcp_call_timeout_s`). AD-27 ne l'écrit pas | couvert |
| 77 | `isError` : le protocole a fonctionné, l'outil non | « isError » | `call_ended.is_error` | couvert |
| 78 | Méthode capturée sans explication (`ping`, `list_changed`, `logging/*`) | idem | `mcp_lab_message.method` absent de `methods.*` | couvert |
| 79 | Modèle sans appel d'outils | idem | `ask.tools = false`, `reason_text` | couvert |
| 80 | Le modèle répond sans outil : note dédiée | idem | `ask_ended.outcome = no_tool` | couvert |
| 81 | Outil inconnu ou arguments invalides : flèche rouge, raison du harnais, rien vers le serveur | idem | `model_ended{outcome: refused, refusal_text}`, `ask_ended.outcome = refused` (`ToolExecutor.check`) | couvert |
| 82 | Second appel d'outil montré, puis arrêt avec le texte dédié | idem | `ask_ended{status: limit, outcome: second_tool}` ; `model_ended.tool_call` | couvert |
| 83 | Sortie coupée (`cut`), borne `tools.max_calls`, dépassement de fenêtre refusé avant envoi | (absent) | AD-27 les crée. EXPERIENCE n'a aucun état pour eux, et `ask_ended.outcome` n'a pas de valeur `cut` alors qu'AD-27 dit qu'une sortie coupée « clôt l'échange aussi » | contradiction |
| 84 | Modèle cloud : clé refusée ou quota dépassé, raison du fournisseur | « Modèle cloud » | `mcp_lab_model_ended{status: error, error_text}` (+ `harness_error` au journal) | couvert |
| 85 | Retour à l'Atelier Harnais : état moteur restauré, sinon la ligne de cache dit la cause « Atelier MCP » (`prefix_causes`) | « Retour à l'Atelier Harnais » | AD-2 `prefix_not_reused.cause` gagne `mcp_lab` ; AD-27 « Cache du moteur » (`_lab_restore`) | couvert |
| 86 | Nom de cette ligne : EXPERIENCE dit « Préfixe non réutilisé » | idem | Le lot 1 l'a renommée « Cache non réutilisé » (`ui.yaml:593`, `:702`) | contradiction |
| 87 | « Arrêter » pendant une génération : seule la génération s'arrête, la connexion reste `[ASSUMPTION]` | « Arrêté » | AD-27 « Déroulé et bornes » ; `model_ended` / `ask_ended.status = cancelled` | couvert |

### F. Accessibilité, module commun

| # | Besoin | Source EXPERIENCE | Couvert par | Statut |
|---|---|---|---|---|
| 88 | Nom accessible d'une flèche, fragment par fragment (résumé, réseau, sorte, origine, erreur, fantôme, durée) | « Nom d'une flèche » | Réseau, origine, fantôme, durée : couverts. Résumé, sorte et erreur par flèche manquent (#20, #21, #22) | manquant |
| 89 | Annonces : synthèse de chaque phase, échecs en `alert`, fin d'un appel par le modèle avec sa durée | « Annonces » | `*_ended`, `ask_ended.duration_ms` | couvert |
| 90 | Nom d'un serveur : « …, sur le poste, stdio, connecté, 2 outils, 1 ressource, 1 prompt » | « Architecture » | `servers`, `open_server`, `connect_ended` | couvert |
| 91 | Retouche 1 : anneau d'encre sous le halo de `diagram-block.is-active` | « Retouches du module commun » | AD-28 | couvert |
| 92 | Retouche 2 : cœur du fil parcouru à 3 px | idem | AD-28 (`.diagram-path-core` ; `.diagram-wire` inchangé) | couvert |
| 93 | Retouche 3 : « Suivre le direct » pressé en fond plein, précédé de « ● » | idem | AD-28 (« ● » en `aria-hidden`) | couvert |
| 94 | Retouches 4 et 5 : position du stepper dans un nœud `status` poli, hors du direct seulement ; `explain()` fermé à la sortie du focus | idem | AD-28 (la position visible perd `aria-live` ; `focusout`) | couvert |

### G. Données attendues et contenus (hors tableaux ci-dessus)

Ces besoins sont tous couverts, sauf un, mineur. Ils ne sont pas comptés dans le bilan pour éviter les doublons.

- Ressource `glossary://terms` et prompt `explain_term(term)` dans les trois langues : AD-19 lot 4 (`content/mcp_local/` et ses surcouches). Couvert.
- Gabarit qui réunit une ressource et sa question en un seul message utilisateur : AD-19, AD-27. Couvert.
- Raisonnement coupé `[ASSUMPTION]` : `model_ended.reasoning_cut`. Couvert, mais EXPERIENCE ne dit pas où l'afficher.
- Reformulation de `mcp.to_server`, `mcp.from_server`, `methods.*`, `transports.*.explain_text` et passage de `session.mcp_lab.is_error` à `isError` : la spine ne les reprend pas. C'est un détail de contenu qui relève du build ; il reste à le mettre dans la story.

## Contradictions (détail)

1. **#11 Disponibilité de « Envoyer au modèle ».** EXPERIENCE dit « mêmes conditions que le mode Par le modèle » (appel d'outils requis) et, deux phrases plus loin, qu'un modèle sans appel d'outils reçoit la ressource sans le bloc. AD-27 tranche pour la seconde lecture. → Corriger EXPERIENCE : un modèle chargé suffit avec `of`.
2. **#8 Liste facultative en échec.** AD-27 met la liste à `null`, comme pour une capacité non annoncée. EXPERIENCE associe `null` à « ⊘, Ce serveur n'annonce pas… ». → Ajouter un état à EXPERIENCE (onglet actif ou barré avec « La liste des ressources a échoué : {raison} », lu dans `list_errors`), ou, mieux, garder `null` pour « non annoncée » seulement et donner un autre marqueur à l'échec.
3. **#55 `doc_mode: none`.** Le sélecteur d'EXPERIENCE n'a que deux segments. → Ajouter à EXPERIENCE l'affichage d'un envoi sans bloc « outils » (« Aucun outil envoyé : le modèle actif n'appelle pas d'outils »).
4. **#66 Antenne du robot.** EXPERIENCE la limite au mode « par le modèle » ; AD-27 fait générer aussi les envois de ressource et de prompt. → Écrire dans EXPERIENCE « pendant toute génération d'un envoi au modèle ».
5. **#83 Sortie coupée, borne d'appels, fenêtre dépassée.** Trois issues d'AD-27 sans état dans EXPERIENCE. De plus, la spine n'est pas cohérente avec elle-même : `ask_ended.outcome` n'a pas de valeur `cut`. → Ajouter `cut` (et un `outcome` pour `max_calls`) à `ask_ended`, puis trois lignes dans le tableau des États d'EXPERIENCE.
6. **#86 Libellé de la ligne de cache.** Le lot 1 a renommé « Préfixe non réutilisé » en « Cache non réutilisé ». → Mettre à jour EXPERIENCE.
7. **Ambiguïté de `tools/list` (non comptée).** AD-27 écrit « `tools/list`, puis `resources/list` et `prompts/list` dans cet ordre, chacune seulement si la capacité est annoncée », ce qui peut rendre `tools/list` conditionnel. EXPERIENCE (ligne 5 de la poignée de main) le rend inconditionnel. → Préciser dans AD-27 (`tools/list` aussi conditionnel à `capabilities.tools`, ce que veut la spécification MCP) et dans EXPERIENCE.
8. **Questions ouvertes devenues caduques (non comptées).** « Données attendues par la page » (« Aujourd'hui, la fin de connexion ne porte ni capacités… », « Le contrat d'événements est à fixer ») et la question ouverte « Contrat d'événements (bloquant) » sont réglées par AD-27. → Les clore dans EXPERIENCE avec un renvoi à AD-27.

## `[ASSUMPTION]` d'EXPERIENCE et leur sort dans la spine

| `[ASSUMPTION]` d'EXPERIENCE | Spine | Action sur EXPERIENCE |
|---|---|---|
| Textes du glossaire (ressource, prompt) dans les trois langues | Confirmée (AD-19) | Retirer la balise |
| Un modèle sans appel d'outils reçoit la ressource ou le prompt sans le bloc « outils » | Confirmée, mais la spine la balise de nouveau `[ASSUMPTION]` (`doc_mode = none`) et ajoute la valeur `none` | Retirer « mêmes conditions » ; ajouter l'affichage de `none` |
| Lazy loading : `load_tool_doc` sans message MCP | Confirmée (`meta_call`) | Retirer la balise |
| « Arrêter » pendant une génération garde la connexion | Confirmée | Retirer la balise |
| Second appel d'outil : l'atelier s'arrête | Confirmée (`status: limit`, `outcome: second_tool`) | Retirer la balise |
| Raisonnement coupé | Confirmée par `reasoning_cut`. La spine ajoute deux hypothèses à elle : raisonnement éteint par défaut, et contexte minimal sans prompt système | Dire où s'affiche `reasoning_cut` et, peut-être, mentionner « sans prompt système » dans le bloc « Envoyé au modèle » |
| Dernier échec par serveur gardé par la page, perdu au rechargement | Cohérente (`last_session` part de la dernière connexion) | Préciser que l'échec de la *dernière* tentative revient après un rechargement |
| Phases repliées, retour au direct à chaque nouvel échange, mémorisation à part de l'atelier, pas de défilement automatique | Hors spine (interface) ; `onLive` le permet (AD-28) | Aucune |

## Correctifs proposés (manquants)

| # | Correctif |
|---|---|
| 38 | Ajouter `status: cancelled` à `connect_ended`, `call_ended`, `read_ended`, `prompt_ended` (et à `call_ended{by: model}` d'un `ask` arrêté pendant `tools/call`), et cesser de rendre l'arrêt en `error`. |
| 20, 21, 88 | Ajouter à `mcp_lab_message` : `summary_text` (« 2 outils », « 1 bloc texte », « capacités : tools · resources · prompts », calculé par `mcp/lab.py`) et `message_kind: request|response|notification|error`. |
| 22 | Ajouter à chaque `*_ended` en échec `failed_method` et `failed_seq` (le `seq` du `mcp_lab_message` resté sans réponse), ou un `mcp_lab_message_failed{seq, error_text}`. |
| 42 | Relier chaque `outbound_request` d'un serveur public à son message : `mcp_lab_message.outbound_seq`, ou une règle d'ordre écrite (l'`outbound_request` précède immédiatement son `mcp_lab_message` `to_server`), plus un libellé pour les GET et DELETE de session. |
| 12 | Scinder la disponibilité : `ask{tools: {available, reason_text}, send: {available, reason_text}, model}`. |
| 18 | `servers[].source_text` et `source_read_text` (« glossary.yaml », « lit glossary.yaml »), dans `content/mcp.yaml` ou `mcp_lab.yaml`, avec leurs surcouches. |
| 50 | `connect_ended.counted_by` (libellé du modèle, ou `null` pour une estimation), et un `mcp_lab_weights{…}` réémis après `model_load_ended` quand une connexion est ouverte. À défaut, EXPERIENCE marque le poids « compté par {modèle} ». |
| 74 | `mcp_lab_closed{server, cause: next|language|stop|session|process, reason_text}`, que `last_session` garde. |
| 69 | `servers[].state{not_contacted|available|unavailable, reason_text}` dans `GET /api/mcp_lab`, ou retirer le cas `arch-node-unavailable` d'EXPERIENCE (l'atelier est un bac à sable et ne contacte rien au démarrage). |
| 37 | `ask_ended.model_share_text`, ou une synthèse reformulée dans EXPERIENCE : « dont {model_ms} ms de génération ». |
| 46 | Option `describe(step)` de `createStepper` pour le texte du nœud `status` (AD-28, option facultative). |
| G | Reformulations de `ui.yaml` / `messages.yaml` (`isError`) : à mettre dans la story du lot 4. |
