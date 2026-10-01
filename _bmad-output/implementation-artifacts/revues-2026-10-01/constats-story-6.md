# Constats de revue, story 6 (atelier MCP) — à trier

Working tree : `C:\Users\anael.yahi\Documents\GitHub\wt-story6`, commit 0601e89, baseline 1bc25bf.
« patch L… » = lignes du diff `git -C ..\wt-story6 diff 1bc25bf 0601e89 -- . ':!_bmad-output/specs'` (à régénérer, non commité).
Les quatre relecteurs ont rendu (Intent Alignment, Verification Gap, Blind Hunter, Edge Case Hunter).

## Intent Alignment (IA)
- IA1. Les cinq sections sont faites (lecture « tout, avec repli 1 à 3 »), capture JSON-RPC réelle sur le transport (`reconstructed` toujours faux, noté dans la SPINE).
- IA2. Écart principal : section 5 et poids montrés et comptés sur le JSON des définitions (`json.dumps(registry.definition(name))`), pas sur le contexte rendu (gabarit local `render_context`, corps cloud `render_chat_body`) que compte la jauge. Pour un gabarit qui enveloppe les outils, texte et tokens diffèrent de la jauge. Les tests ne vérifient que la cohérence au niveau JSON.
- IA3. Lignes de la matrice énoncées côté page mais testées côté session/API : « hors ligne, page lisible », « Occupé » (forcé par `_set_state("turn")`, pas un vrai tour), « arrêt, aucun processus enfant » (arrêts testés sur le serveur HTTP en processus, pas sur le glossaire stdio ; bouton Arrêter de la page jamais pressé).
- IA4. Fonctions de page jamais exercées : préréglages, champs JSON des paramètres non scalaires, avis de troncature, requêtes sortantes des serveurs publics, rejeu de `last_session` après rechargement, bandeau occupé, note « servi non traduit ».
- IA5. Garde réseau : `outbound_request` tracé, mais aucun refus par la garde n'est exercé.

## Verification Gap (VG)
- VG1. [patch] `content/mcp_lab.yaml` invalide jamais testé (`_mcp_lab_content`, app_session.py ~8657-8673) : ajouter `test_invalid_content_is_said_and_refuses_the_connection` sur le modèle de `test_rag_lab.py:861` (`content` None et raison, `mcp_lab_connect` lève `SendRefused` sans événement, un seul `harness_error` `mcp_lab` sur deux lectures).
- VG2. [patch] `last_session(envelopes, first)` non vérifié contre `_mcp_lab_first` ; le test nommé pour le filtre ne l'appelle pas. Ajouter `test_last_session_is_the_last_connection_and_its_calls` (connexion, appel, reconnexion → seule la 2e ; connexion puis appel → `last_session[0]` est `initialize`) ; renommer `test_catalog_line_and_last_session_filter`.
- VG3. [patch] Fermeture par le lifespan avec une connexion d'atelier ouverte jamais exercée (`aclose_mcp` ~5168-5175) : `test_lifespan_closes_the_workshops_connection` copié de `test_mcp.py:524` (TestClient, connexion `local`, sortie, `no_local_server_left()`). **Lance un serveur MCP local : à faire seulement avec l'accord d'Anaël.**
- VG4. [patch] Connexion perdue pendant un appel (`ConnectionError` sans annulation, `not conn.alive`, ~8931-8944) non testée : tuer l'enfant puis appeler ; `status == "error"`, texte de connexion perdue, `open_server is None`, appel suivant refusé. **Lance un serveur local : accord requis.**
- VG5. [defer] Poids sans moteur jamais marqués estimés (`estimated = estimated or rough`, ~8842).
- VG6. Un `MCPError(CONNECTION_CLOSED)` passe par `describe_error` qui teste `MCPError` avant `ConnectionError` → « refused_exchange » au lieu de `session.mcp_lab.closed` (spec l.113). À vérifier dans le SDK.

## Blind Hunter (BH)
- BH1. Résultat `is_error` : la page montre sous « Texte réinjecté au modèle » le texte brut, alors que la brique réinjecte `msg("tools.error", text=…)` (et « pas de détail » quand vide). Le point pédagogique est faux pour le cas démontré (terme inconnu).
- BH2. Arrêt pendant un appel stdio : `except MCPError` ne regarde pas `cancel.cancelled` → « Le serveur a refusé l'échange MCP » au lieu de `session.mcp_lab.stopped` (= VG6 côté arrêt).
- BH3. Les textes `mcp.error.closed` (fr, en, de) conseillent « décochez puis recochez », sans objet dans l'atelier.
- BH4. Course arrêt/démarrage de connexion : `cancel.cancelled` vérifié une seule fois avant `conn.start()`, pas après `future.result(...)` → `connect_ended{ok}` avec une connexion vivante après un arrêt.
- BH5. Aucun moyen de fermer une connexion ouverte (« Arrêter » actif en `mcp_lab` seulement) ; l'enfant stdio vit jusqu'à la connexion suivante ; README dit « Arrêter ferme la connexion ». Ajouter « Se déconnecter » ou corriger le README.
- BH6. Réponses du serveur jamais expliquées (seules les requêtes ont un texte) : `initialize` (nom, version, capacités), résultat de `tools/list`, erreur JSON-RPC.
- BH7. Le validateur exige `methods == METHODS` exactement : `ping`, `notifications/cancelled`, `notifications/message` ne peuvent jamais avoir de texte ; préférer « au moins celles-ci ».
- BH8. Libellé de durée selon la direction, pas selon le type de message (notification serveur étiquetée « aller-retour ») ; le payload n'a pas de champ requête/réponse/notification/erreur.
- BH9. Ordre des requêtes sortantes deviné alors que `envelope.seq` est disponible (mal placé pour les GET SSE / DELETE du Streamable HTTP).
- BH10. JSON-RPC brut non borné et dupliqué (`mcp_lab_message.jsonrpc` puis `mcp_lab_call_ended.raw`) dans le journal, le flux SSE et chaque instantané ; ni plafond ni indicateur de troncature.
- BH11. `launch_command` affiche `python -m wavestack.mcp.local_server {lang}` en dur alors que le lancement réel utilise `sys.executable` ; dériver de `StdioServerParameters`.
- BH12. Clés réutilisées absentes en en/de : `session.mcp.no_loop`, `session.llm_lab.back_to_idle` (ce dernier hors de l'espace de noms) ; créer `session.mcp_lab.back_to_idle` en trois langues.
- BH13. Libellé « Atelier MCP : connexion terminée » trompeur (fin de la tentative, connexion souvent ouverte) ; préférer « poignée de main terminée ».
- BH14. `intro_text` : « la brique MCP de l'atelier » confond atelier MCP et écran principal (fr, en, de) ; dire « l'écran principal ».
- BH15. Formulaire : booléens optionnels envoyés à `false` sans avoir été touchés ; un champ `integer` accepte 1.5.
- BH16. Tests manquants : YAML invalide (= VG1), refus des intentions de classe (b) de l'écran principal pendant un échange, arrêt pendant un appel stdio.
- BH17. DESIGN.md et EXPERIENCE.md affirment que la barre à six liens tient en `de` à 1 280 px en projection, alors que les notes de la story disent que ce n'est pas mesuré (`_bar_fits`).
- BH18. Virgule perdue dans la liste « Verrou d'opération » d'ARCHITECTURE-SPINE (après « génère) »).
- BH19. `eventSummary` de `mcp_lab_call_ended` met `p.status` brut (« ok »/« error ») dans le journal ; passer par `t()`.

## Edge Case Hunter (EC)
- EC1. (= BH4) Arrêt entre la vérification `cancel.cancelled` et `conn.start()` (~8781-8785) : `aclose` ne fait rien (tâche absente), `start` connecte, statut ok, l'enfant survit à « Arrêter » ou à la fermeture. Garde : après `future.result(...)`, si `cancel.cancelled`, lever `ConnectionError` pour passer par le `except` qui ferme.
- EC2. Si `_mcp_lab_weights` ou l'émission de `connect_ended` lève après la liste des outils (~8805-8820) : pas de `connect_ended`, connexion et `_mcp_lab_tools` restent posés, page bloquée sur « connexion ». Garde : `except` qui ferme et émet `connect_ended{status: error}`.
- EC3. Exception dans `_run_mcp_lab_call` hors du `try` interne (~8948-8955) : pas de `mcp_lab_call_ended`, page bloquée sur « appel en cours ». Garde : émettre `call_ended{error}` dans le `except` externe avant `_error`.
- EC4. Serveur qui liste deux outils de même nom (~8836) : `harness_error` émis dans le contexte principal, en français ; doublon compté deux fois dans `full_tokens`.
- EC5. Requête initiée par le serveur (ping) qui réutilise un id en attente côté client (`lab.py` ~171-181) : réponse attribuée à la mauvaise méthode. Garde : clé `(direction, id)`.
- EC6. Réponse tardive d'un appel expiré pendant un échange suivant (`lab.py` ~154-158) : émise sous le `step_id` suivant, `_received['tools/call']` écrasé. Garde : vider `_pending` à `begin()` ou ignorer les réponses d'une autre étape.
- EC7. (= VG6) `MCPError CONNECTION_CLOSED` (~8924-8946) : `alive` reste vrai, connexion morte gardée, `open_server` encore affiché.
- EC8. `open_server` lu pendant la poignée de main (`lab.py` ~300-302) : la page rechargée dit « Connexion ouverte » avant toute liste d'outils.
- EC9. (= BH9) `mcp.js` ~268-277 : appariement par position des requêtes sortantes (GET SSE, DELETE) ; trier par `seq`.
- EC10. (= BH8) `mcp.js` ~231-234 : « aller-retour » pour tout message serveur.
- EC11. `mcp.js` ~150 : connexion fermée hors état `mcp_lab` (changement de langue depuis un autre onglet) → pastille « connecté » périmée, chaque appel reçoit 409. Garde : `refreshOpenServer()` sur `language_changed` ou sur un 409 `not_connected`.
- EC12. (= BH15) Booléen optionnel non touché envoyé à `false`.
- EC13. `mcp.js` ~481-490 : texte non numérique dans un champ nombre (valeur vide) → argument optionnel ignoré en silence, obligatoire dit « manquant » au lieu d'« invalide ». Garde : `input.validity.badInput`.
- EC14. (faible, = EC1) Processus local qui peut survivre à un arrêt ou à la fermeture dans la fenêtre de course.