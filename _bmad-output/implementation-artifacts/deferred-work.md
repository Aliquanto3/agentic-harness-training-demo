- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/1-fondations-lancement-diagnostic-modele-local.md`
  summary: Aucun test n'exerce la branche « serveur déjà lancé » (`status: "server"`) de `DiagnosticSession.check_model()` — tous les tests forcent `discovery._server_candidates` à retourner une liste vide pour rester déterministes.
  evidence: Une régression qui exclurait `"server"` des candidats utilisables (ou casserait `_server_candidates`) empêcherait WaveStack de reconnaître un serveur Ollama/llama.cpp déjà lancé sans qu'aucun test n'échoue. Fermer l'écart demande un test de `_server_candidates` avec un transport httpx simulé ; raisonnable à ajouter lors du premier usage réel de la découverte serveur.
  closed: story 18 (2026-09-26) — `tests/test_model_servers.py::test_server_candidates_one_per_served_model` teste `_server_candidates` avec un transport `httpx.MockTransport` ; la branche serveur de `check_model` est couverte par `test_servers_only_block_with_a_choice` et `test_saved_server_choice_*`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/2-interface-a-volets-et-journal-devenements.md`
  summary: Le schéma d'architecture (`app.js::renderSchema`) ignore les champs `hosting`, `wanted`, `available`, `reason_fr` du payload `architecture_changed` : tout nœud est peint en violet « local » quel que soit son état réel.
  evidence: Invisible pour cette story (les deux nœuds fixes `core.harness`/`core.model` sont toujours locaux et disponibles), mais deviendra un vrai défaut dès qu'une story ultérieure (MCP, outils réseau) introduit un nœud réseau ou indisponible sans que personne n'ait branché ces styles.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/2-interface-a-volets-et-journal-devenements.md`
  summary: `streamEvents` (`app.js`) retente la connexion SSE indéfiniment toutes les 1 s sans indicateur « hors ligne » visible dans l'interface.
  evidence: Sans risque fonctionnel (la reprise par `Last-Event-ID` est correcte), mais si le serveur reste indisponible un moment, rien dans la barre haute ne distingue « application inactive » de « connexion perdue » pour l'utilisateur.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/2-interface-a-volets-et-journal-devenements.md`
  summary: `AppSession` (`session/app_session.py`) est instanciée à la volée, sans référence partagée/singleton nulle part dans l'application.
  evidence: Suffisant pour cette story (état fixe `idle`, aucune mutation), mais la story 3 devra probablement décider où vit « la » session applicative avant de faire évoluer son état au fil d'un tour.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/2-interface-a-volets-et-journal-devenements.md`
  summary: `ArchitectureEdge` ne valide pas que `from_`/`to` référencent des identifiants de nœuds présents dans la même liste `nodes`.
  evidence: Sans conséquence ici (cette story n'émet jamais d'arête, `edges: []`) ; à ajouter avec la première story qui construit de vraies arêtes (AD-12), pour éviter une arête fantôme rendue silencieusement sans rien dessiner.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/2-interface-a-volets-et-journal-devenements.md`
  summary: Le branchement diagnostic → `AppSession.emit_initial()` dans `cli.py` (`_run_diagnostic_then_boot`) n'est exercé par aucun test de bout en bout.
  evidence: `main()` bloque sur `uvicorn.run`, ce qui rend le test end-to-end malcommode tel qu'écrit ; chaque moitié (`DiagnosticSession.run().ready`, `AppSession.emit_initial()`) est testée isolément. Fermer l'écart demande d'extraire `_run_diagnostic_then_boot` en fonction injectable testable avec une session factice — refactor mineur, pas nécessaire pour livrer cette story (disposition déposée par la couche verification-gap elle-même).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/3-llm-nu-compteur-de-tokens-jauge.md`
  summary: Détail de la jauge (grille de cellules façon `/context`, composant DESIGN `context-gauge-detail`) dans le volet Contexte LLM, ouvert d'un clic sur la jauge.
  evidence: Différé sur décision d'Anaël (2026-09-24) : la jauge empilée de la barre haute, avec sa ventilation au survol, suffit à CAP-33 ; la grille alourdissait une story déjà au-dessus de la cible de taille.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/3-llm-nu-compteur-de-tokens-jauge.md`
  summary: `LlamaCppEngine.complete` (arrêt sur EOG, sortie coupée à `max_tokens`, séquence d'arrêt, annulation, décodage UTF-8 incrémental) n'est testé sur aucun vrai modèle : les tests du tour passent par le moteur factice, qui réimplémente cette logique.
  evidence: Un décalage d'un token sur `count >= max_tokens`, ou un préfixe d'arrêt émis après coup, passerait inaperçu. À ajouter au test opt-in marqué `model` (`tests/test_render_reference.py`, `WAVESTACK_TEST_GGUF`) avec un petit GGUF.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/5-outils-natifs.md`
  summary: Story 5b — outils réseau (`public_holidays` via calendrier.api.gouv.fr, `wikipedia_summary` via fr.wikipedia.org REST, `fetch_page` limité aux hôtes autorisés et coupé à `fetch_page_max_chars`), fabrique AD-15 complétée (`body` dans `outbound_request`, refus hors liste par `net`, redirections manuelles revérifiées, `preview_request`), `hosting-tag-network` et `outbound-payload` dans l'interface, état `not_contacted` puis `available`/`unavailable` du composant réseau selon le dernier appel.
  evidence: Scindée de la story 5 sur décision d'Anaël (2026-09-24), spec entière à ~3 800 tokens ; 5a livre l'exécuteur que 5b réutilise. Décisions déjà prises : `fetch_page` n'accepte que les hôtes des API (`fr.wikipedia.org`, `calendrier.api.gouv.fr`) ; outils réseau désactivés par défaut à l'activation de la brique ; à livrer avant la story 6 (MCP) pour éprouver la garde réseau.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/5b-outils-reseau.md`
  summary: Repli hors ligne de `fetch_page` (FR-13) — sans réseau, un long fichier de `content/demo_files/` remplace la page, avec la mention « contenu de remplacement ».
  evidence: Reporté sur décision d'Anaël (2026-09-24) : ce repli sert le résultat volumineux du sous-agent (UJ-6) et de la compression (UJ-7), qu'aucune story livrée n'utilise encore ; en 5b, `fetch_page` hors ligne échoue avec une erreur claire et le nœud passe indisponible.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/5b-outils-reseau.md`
  summary: Le rendu front de la story 5b (bloc `outbound-payload` rattaché à l'étape d'outil, nœud « non contacté », étiquette RÉSEAU) n'est vérifié par aucun test automatique.
  evidence: Le dépôt n'a aucun banc de test JS (`app.js` seulement passé à `node --check`) ; un réducteur qui rattacherait la requête à la mauvaise étape passerait inaperçu. Garde actuelle : la vérification manuelle de la spec ; à fermer si un banc de test front est introduit.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/1b-choix-du-modele-au-diagnostic.md`
  summary: Le démarrage CLI (`_run_diagnostic_then_boot` → `app_session.boot(result.model_path)`) n'est exercé par aucun test.
  evidence: Remplacer l'appel par `boot(None)` ne ferait échouer aucun test ; la fermeture vit dans `main()`, bloqué par `uvicorn.run`. Même écart que celui déjà consigné pour la story 2 ; se ferme en extrayant la fonction pour l'injecter.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/1c-correctif-garde-reseau.md`
  summary: La garde réseau ne filtre ni `socket.gethostbyname`/`gethostbyname_ex` ni `socket.sendto` : une résolution hors liste ou un envoi UDP vers une IP quelconque lui échappent.
  evidence: AD-15 ne filtre que `socket.getaddrinfo` et `socket.connect` ; relevé par la revue de la story 1c (préexistant). À traiter avant d'adopter une dépendance qui résout par `gethostbyname` ou parle UDP, en ajoutant ces événements au hook.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/1d-correctif-cache-navigateur-et-echecs-de-sonde.md`
  summary: Permettre de forcer une nouvelle sonde d'un fichier mémorisé en échec (par exemple, un choix explicite qui contourne `failed_probes`).
  evidence: Un `ok: false` transitoire (mémoire insuffisante au chargement) resterait mémorisé jusqu'à un changement du fichier ou de llama-cpp-python. Seule issue aujourd'hui : modifier settings.json à la main. Non vérifié : il faudrait constater un échec d'allocation de llama.cpp sur un poste CPU chargé.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6-mcp-local-et-public.md`
  summary: Story 6b — lazy loading MCP (CAP-22) : bascule documentation complète / lazy loading dans la carte MCP, méta-outil `load_tool_doc` (source `harness`) dont la description liste une ligne par outil MCP (un segment `tool_catalog` par outil, rendu étendu par un type `Joined` de plusieurs `Part`), réponse de type `tool_catalog`, effet `ToolDocLoaded` (`session/effects.py`, AD-23), outil appelable dans le même tour (`loaded_in_turn`) puis dans `tools` aux tours suivants, talon court dans l'historique, documentations déchargées par « Vider la conversation », appel d'un outil non documenté refusé et réinjecté ; la carte de dépassement propose alors le lazy loading.
  evidence: Scindée de la story 6 sur décision d'Anaël (2026-09-24), spec entière à ~4 100 tokens ; la story 6 livre serveurs, registre et documentation complète que 6b réutilise. Tant que 6b n'est pas livrée, data.gouv.fr en documentation complète ne sert qu'au dépassement volontaire (AD-9).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6-mcp-local-et-public.md`
  summary: Le rendu front de la story 6 (cartes de connexion MCP hors tour et leur appariement, `setOption` vers `/api/intentions/mcp_server`, badge « MCP », outils dans l'infobulle du nœud serveur) n'est vérifié par aucun test automatique.
  evidence: Même écart que pour la story 5b : le dépôt n'a aucun banc de test JS (`app.js` seulement passé à `node --check`) ; relevé par la couche verification-gap de la revue de la story 6.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6b-lazy-loading-mcp.md`
  summary: Le rendu front de la story 6b (interrupteur « Lazy loading », `setOption("mcp_mode")` vers `/api/intentions/mcp_mode`, carte d'étape « Chargement de la documentation » avec badge MCP) n'est vérifié par aucun test automatique.
  evidence: Même écart que pour les stories 5b et 6 : le dépôt n'a aucun banc de test JS (`app.js` seulement passé à `node --check`) ; relevé par la couche verification-gap de la revue de la story 6b.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6b-lazy-loading-mcp.md`
  summary: Au rejeu (story 9, `build_turn_state(origin_turn)`), les documentations MCP chargées (`_loaded_docs`) doivent suivre la branche rejouée et non la conversation entière.
  evidence: `_loaded_docs` est un ensemble au niveau de la session ; un rejeu depuis un tour antérieur proposerait des outils chargés après le point de branchement. AD-17 range les documentations chargées dans l'instantané conversationnel : à traiter avec l'instantané complet de la story 9.
  resolution: Planifié en story 9b (stories.yaml), sprint-change-proposal-2026-09-25-story-9b.md.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6c-refonte-visuelle-atelier-de-construction.md`
  summary: Dans le schéma, l'arête d'un nœud de la colonne 2 vers le cadre Harnais passe sous le nœud de la colonne 1 de la même ligne, ce qui se lit comme une chaîne (cadre → A → B).
  evidence: Visible dès 4 nœuds hors cadre (outils + serveurs MCP) ; à reprendre avec les zones Local / Réseau et la frontière de DESIGN.md, qui imposent de toute façon de refaire la disposition.
  resolution: Repris par la story 8e (tronc et rails, zones et frontière), sprint-change-proposal-2026-09-25.md.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6c-refonte-visuelle-atelier-de-construction.md`
  summary: `robotPose()` et la clé de mémorisation de `renderSchema()` (`app.js`) ne sont couverts par aucun test automatique.
  evidence: Le dépôt n'a aucun banc de test JS ; oublier `pose` dans la clé figerait le robot sans qu'un test échoue. Poses vérifiées à la main pendant un vrai tour (story 6c). Même écart que la story 5b ; à fermer si un banc de test front est introduit.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6c-refonte-visuelle-atelier-de-construction.md`
  summary: Sous le robot, un modèle chargé depuis un blob Ollama s'affiche `sha256-…` au lieu de son nom lisible.
  evidence: `boot(model_path)` ne reçoit que le chemin ; la découverte (`models/discovery.py`) connaît le nom affiché par le sélecteur du diagnostic. Transmettre ce nom demande de le faire passer par `boot` et `settings.json`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/7-skills-dont-caveman.md`
  summary: Aucun test ne vérifie que les vraies briques `skills`, `tools` et `mcp` sont indisponibles sur un modèle sans `tool_call_parser`.
  evidence: Supprimer `capabilities=["tool_call_parser"]` d'une déclaration de `bricks/registry.py` ne fait échouer aucun test ; seul le mécanisme générique est testé (`tests/test_bricks.py:371`).
- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/7-skills-dont-caveman.md`
  summary: Le basculement d'un skill dans l'interface (`setOption("skills", …)` vers `/api/intentions/skill`) et l'état « chargé » du schéma n'ont aucun test front.
  evidence: Le dépôt n'a aucun banc de test JS ; seul l'endpoint serveur est testé (`tests/test_skills.py`, `test_skill_intention_http`).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8-hooks-h1-h2-h3-h5.md`
  summary: Story 8b — hook H5, validation humaine avant tout outil réseau (outils réseau natifs et outils des serveurs MCP publics) : décision `ask_human` en `before_tool`, état `awaiting_human`, `approval_requested{approval_id, tool, destination, preview}` où `preview` est exactement ce qui sortirait (`preview_request`, ou corps JSON-RPC `tools/call` vers l'URL du serveur MCP), intention de classe (c) `approval {approval_id, approved, disable_hook}` (la première réponse l'emporte), `approval_resolved{decision: approved|refused|cancelled, hook_disabled}`, refus réinjecté et tour poursuivi, « Arrêter » pendant l'attente → `cancelled`, carte violette « En attente de votre validation » à trois boutons, indicateur « En attente de validation », `pending_approval` dans `/api/state`.
  evidence: Scindée de la story 8 sur décision d'Anaël (2026-09-24), spec entière à ~5 000 tokens. Décisions déjà prises : H5 désactivé à l'activation de la brique (Q1) ; trois boutons « Autoriser », « Refuser », « Autoriser et ne plus demander », ce dernier autorisant l'appel puis désactivant H5, y compris pour les appels réseau suivants du même tour (Q2). La story 8 livre les points d'accroche, `_run_tool` et la sous-option `h5` absente ; 8b ajoute le composant `hooks.h5` et `ask_human` à `ALLOWED`. Si l'aperçu est refusé (hôte hors liste), H5 ne demande rien.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8-hooks-h1-h2-h3-h5.md`
  summary: Aucun test ne vérifie que H2 reprend, à son déclenchement suivant dans le même tour, les lignes d'une écriture d'`audit.log` échouée (échec en `after_tool`, succès en `on_turn_end`).
  evidence: `test_h2_write_failure_is_traced_and_the_turn_goes_on` n'a qu'un déclenchement (`tools=False`) ; avancer le curseur de H2 même en cas d'échec perdrait des lignes sans qu'aucun test n'échoue. Il faut injecter un échec ponctuel (monkeypatch de `_apply_audit` ou de `config.audit_path`) ; chemin d'erreur secondaire, relevé par la couche verification-gap de la revue de la story 8.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8-hooks-h1-h2-h3-h5.md`
  summary: Les nœuds du schéma d'architecture (dont « Journal d'audit », seul accès au journal entier) ne sont atteignables qu'à la souris : pas de `tabindex` ni de gestion du clavier sur les `<g>` SVG.
  evidence: Préexistant pour tous les nœuds de `renderSchema` (`app.js`) ; la story 8 ajoute le clic sur `file.audit` qui ouvre le tiroir du journal. À traiter pour tout le schéma (accessibilité de base), avec la refonte de disposition déjà différée en story 6c.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8b-hook-h5-validation-humaine.md`
  summary: Aucun test ne vérifie qu'un hook `before_tool` qui modifie les arguments avant H5 fait porter à l'aperçu (`approval_requested.preview`) et à l'envoi (`outbound_request`) les mêmes arguments modifiés.
  evidence: `_hook` recopie les arguments modifiés dans le résultat `ask_human` ; retirer ce `replace` ferait approuver un aperçu et envoyer d'autres arguments sans qu'un test échoue. Inatteignable avec les hooks de démonstration (aucun ne modifie en `before_tool`) ; à ajouter avec le premier hook qui modifie, ou avec la story 9. Relevé par la couche verification-gap de la revue de la story 8b.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8b-hook-h5-validation-humaine.md`
  summary: Le rendu front de la story 8b (carte « En attente de votre validation », trois boutons actifs seulement en `awaiting_human`, décision affichée après résolution, « Arrêter » visible pendant l'attente, indicateur « En attente de validation ») n'est vérifié par aucun test automatique.
  evidence: Même écart que pour les stories 5b à 8 : le dépôt n'a aucun banc de test JS (`app.js` seulement passé à `node --check`) ; relevé par la couche verification-gap de la revue de la story 8b.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/1b-choix-du-modele-au-diagnostic.md`
  summary: Pendant la vérification du modèle, la page de diagnostic affiche « Modèles détectés : Aucun candidat trouvé. » sans aucun signe que la recherche et la sonde des modèles sont en cours ; l'utilisateur croit qu'aucun modèle n'a été trouvé.
  evidence: Constaté le 2026-09-25 lors du test manuel de la story 8b, avec 30 modèles Ollama à sonder : environ 1 min 30 de liste vide, pendant laquelle seuls les `harness_error` des fichiers incompatibles s'affichent, avant que le contrôle `model` n'arrive. `diagnostic.html` appelle `loadDiagnostic()` au chargement, et `/api/diagnostic` renvoie `candidates: []` tant que `check_model` n'a pas rendu son résultat ; `renderCandidates` confond alors « pas encore connu » et « aucun ». Piste : afficher « Recherche et test des modèles en cours… » tant que le contrôle `model` n'est pas émis, idéalement avec une progression (n sondés sur N), ce qui demande un événement de progression émis par `_discover`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8c-validation-h5-vue-humain-et-vider-la-conversation.md`
  summary: Le rendu front de la story 8c (carte H5 de la Vue humain gardée entre deux rendus, clic unique, focus, trace d'Orchestration sans bouton, libellé des outils, puce liée, masquage après `conversation_cleared` dans Contexte LLM, Orchestration, cartes MCP et schéma, réponse refusée en 409) n'est vérifié par aucun test automatique.
  evidence: Même écart que pour les stories 5b à 8b : aucun banc de test JS ; vérifié seulement à la main dans Chrome contre une API simulée hors dépôt, sans le cas 409 ni le filet rouge après vidage ; relevé par la couche verification-gap de la revue de la story 8c.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8d-orchestration-lisible-rail-par-tour.md`
  summary: Le rail d'Orchestration et le journal des événements de la story 8d (lignes qui restent dépliées, direct et vue figée, « Suivre le direct », repli du tour précédent, fusion des `model_delta` et compte du journal, correspondance de `KIND_LABELS` et `eventSummary` avec le catalogue) ne sont vérifiés par aucun test automatique.
  evidence: Même écart que pour les stories 5b à 8c : aucun banc de test JS, et la spec interdit toute nouvelle dépendance ; vérifié seulement dans Chrome contre un rejeu SSE scripté hors dépôt ; relevé par les couches verification-gap et blind-hunter de la revue de la story 8d. Piste sans dépendance : `node:test` avec `node:vm` pour exécuter `turnRows` et `syncLogGroups` sur des enveloppes conformes au catalogue.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8e-schema-par-categories-points-d-accroche-et-frontiere.md`
  summary: Le schéma de la story 8e (`schemaActivity` : halo, chemin, arrêt ✋ H5 et blocage ✖ ; `component` gardé sur les étapes `tool` et `hook` ; rangement en bacs par `kind` et `hosting` ; états « désactivé » et « ✖ a bloqué » de la bande des hooks) n'est vérifié par aucun test automatique, et aucun test pytest n'affirme que l'enveloppe `tool_started` d'un outil local porte `component == "tools.<nom>"`.
  evidence: Même écart que pour les stories 5b à 8d : aucun banc de test JS, et la spec interdit toute nouvelle dépendance ; vérifié seulement dans Chrome contre un rejeu SSE scripté hors dépôt ; relevé par les couches verification-gap et blind-hunter de la revue de la story 8e. Partie peu coûteuse à fermer : l'assertion pytest sur `tool_started.component` dans `tests/test_tools.py`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/8f-volets-redimensionnables.md`
  summary: Le redimensionnement des volets de la story 8f (`moveBoundary` : bornes minimales, poids des seuls voisins, sens de la hauteur du schéma ; `resetBoundary` ; `loadPaneLayout` et `savePaneLayout` : stockage corrompu, cinq volets masqués, persistance à chaque masquage) n'est vérifié par aucun test automatique.
  evidence: Même écart que pour les stories 5b à 8e : aucun banc de test JS, et la spec interdit toute nouvelle dépendance ; matrice vérifiée seulement à la main dans Chrome ; relevé par les couches verification-gap et blind-hunter de la revue de la story 8f. Piste sans dépendance : `node:test` avec `node:vm`, `handleNeighbours`, `moveBoundary` et `loadPaneLayout` ne dépendant que de `store` et d'un objet de mesure.

- source_spec: none
  summary: Rejeu du dernier prompt (CAP-7, FR-7, AD-17), prévu en story 9b : branche reconstruite depuis l'état antérieur au tour d'origine, nouveau groupe de tour avec badge « Rejeu » dans le rail (8d), tour rejoué lui-même rejouable, comparaison de deux tours côte à côte (« Comparer » dans Contexte LLM), action armée appliquée au tour rejoué.
  evidence: Scindé le 2026-09-25 de la story 9 « Déclenchement forcé et rejeu », qui réunissait deux livrables indépendants (déclenchement forcé CAP-8 d'une part, rejeu CAP-7 d'autre part) ; le déclenchement forcé est traité en premier. `build_turn_state(origin_turn)` et `turn_started.replay_of` existent déjà comme amorces.
  resolution: Planifié en story 9b (stories.yaml), sprint-change-proposal-2026-09-25-story-9b.md.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/9-declenchement-force.md`
  summary: Le rendu front du déclenchement forcé de la story 9 (interrupteur « Afficher les actions forcées » et sa mémorisation, bouton Forcer et formulaire à préréglages, puces « Armé : … » sur la carte et au-dessus du champ de saisie, badges « Forcé par l'utilisateur » / « Déclenché par le modèle » lus dans `envelope.trigger`, ligne « Action forcée abandonnée ») n'est vérifié par aucun test automatique.
  evidence: Même écart que pour les stories 5b à 8f : aucun banc de test JS, et aucune nouvelle dépendance permise ; les tests pytest vérifient l'enveloppe (`trigger`) et `/api/state`, pas le rendu ; vérifié seulement dans Chrome contre un serveur à faux modèle ; relevé par la couche verification-gap de la revue de la story 9. Piste sans dépendance : `node:test` avec `node:vm` sur `turnRows`, `armedChips` et `presetValues`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/1b-choix-du-modele-au-diagnostic.md`
  summary: Sur le PC portable cible, aucun Qwen d'Ollama ne se charge : `qwen3.5:0.8b`, `2b` et `4b` sont classés « incompatible » par le diagnostic, qui retient d'office `granite-4.0-h-1b` (famille sans parseur d'appels d'outils, AD-6), seul GGUF du cache Hugging Face.
  evidence: Constaté le 2026-09-25 au premier lancement sur le PC cible (CPU seul, 16 Go) pendant le test manuel de la story 9. Chargement verbeux : `error loading model hyperparameters: key qwen35.rope.dimension_sections has wrong array length; expected 4, got 3` avec llama-cpp-python 0.3.35 ; les GGUF `qwen35` produits par Ollama diffèrent du format amont. Contourné en téléchargeant `unsloth/Qwen3.5-2B-GGUF` (Q4_K_M, 1,28 Go) dans `%LOCALAPPDATA%\WaveStack\models`, qui se charge (parseur `qwen3_coder`). Pistes : message du diagnostic qui nomme la cause et propose le téléchargement d'un Qwen amont, ou montée de version de llama-cpp-python si elle accepte ces fichiers ; signaler aussi quand le modèle retenu d'office n'a pas de parseur d'appels d'outils.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/1-fondations-lancement-diagnostic-modele-local.md`
  summary: `uv run wavestack` peut se terminer sans rien écrire dans le terminal (code 0) : quand une instance saine occupe déjà le port, `cli.main` ouvre seulement le navigateur sur `/diagnostic`.
  evidence: Constaté le 2026-09-25 au premier lancement sur le PC cible : sortie immédiate, terminal vide, et plus rien n'écoutait sur 8420 quelques secondes après (cause exacte non confirmée ; le second lancement a fonctionné). Même hors de ce cas, un message « WaveStack tourne déjà sur le port … : ouverture du navigateur » éviterait de croire à un plantage silencieux.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/9-declenchement-force.md`
  summary: L'interrupteur « Afficher les actions forcées » et les boutons « Forcer l'appel » / « Déclencher le skill » sont difficiles à trouver : l'interrupteur ressemble aux interrupteurs des briques, et les boutons restent dans la liste repliée des options (« Outils : 3 activés sur 6 »).
  evidence: Test manuel du 2026-09-25 sur le PC cible : l'animateur n'a trouvé ni l'interrupteur ni les boutons sans aide (le comportement est conforme à la spec, vérifié dans un Edge headless : 12 boutons après activation). Pistes : distinguer visuellement l'interrupteur (titre de section, icône main), déplier la liste des options quand l'interrupteur est activé, ou afficher un indice sur la carte repliée.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/9-declenchement-force.md`
  summary: Caveman forcé : le skill est bien chargé avant le premier appel (`load_skill`, `trigger = user`, corps attribué à skills), mais Qwen3.5-2B ne suit pas la consigne (réponses longues ou hors style, et un appel spontané à `get_datetime`). La ligne « le modèle répond en Caveman dès ce tour » de la matrice n'est donc pas démontrable avec ce modèle.
  evidence: Test manuel du 2026-09-25, tours t2 à t4 (Qwen3.5-2B Q4_K_M, CPU) : t2 répond en 211 tokens de prose après un `get_datetime` non demandé ; t3 est télégraphique mais faux sur le fond ; t4 reste en prose. Le mécanisme de la story est conforme ; à revérifier avec un modèle plus gros (option LLM cloud du palier 2) pour trancher entre limite du SLM et consigne du skill trop faible.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/9-declenchement-force.md`
  summary: Documentation MCP forcée en lazy loading : `load_tool_doc` de `local__list_terms` est exécuté et son schéma réinjecté, mais Qwen3.5-2B n'appelle pas l'outil et répond « Je ne peux pas répondre à cette question… je n'ai pas accès … à la liste des termes du glossaire ».
  evidence: Test manuel du 2026-09-25, tour t5 (contexte de 560 tokens) : le harnais est conforme (appelabilité couverte par `tests/test_forced.py::test_forced_mcp_documentation_makes_the_tool_callable_in_the_same_turn`). Deux facteurs possibles : le SLM, et l'injection H3 « n'utilise que les fichiers du dossier de démonstration », qui peut pousser au refus. À revérifier avec un modèle plus gros, puis avec H3 décoché.

- source_spec: none
  summary: Temps de réponse sur le PC portable cible avec Qwen3.5-2B Q4_K_M (CPU seul, 16 Go, 3,3 à 4,3 Go libres au lancement) : 36 à 51 s avant le premier token pour un contexte de 1 100 à 1 400 tokens, 14 s pour 560 tokens ; tours de 20 à 84 s.
  evidence: Journal du test manuel de la story 9, 2026-09-25 : t1 649 tokens, tour arrêté par l'animateur après 22,9 s de lecture du contexte ; t2 1 392 tokens, 1er token à 51,4 s, tour de 83,5 s (dont 30 s pour générer 211 tokens) ; t3 1 104 tokens, 36,6 s / 40,2 s ; t4 1 104 tokens, 45,6 s / 54,6 s ; t5 560 tokens, 13,7 s / 19,8 s. La lecture du contexte (environ 21 à 30 tokens/s) domine. Teams, Edge et l'agent de sécurité occupent l'essentiel de la RAM. Pour la séance : fermer Teams et Edge, garder peu de briques actives, prévoir le rythme de la démonstration en conséquence.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/9b-rejeu-du-dernier-prompt.md`
  summary: Le badge « Rejeu », le choix par défaut de « Comparer » et les écarts de la comparaison de tours (app.js) n'ont aucun test automatique.
  evidence: Même écart que pour les stories 5b à 9 : aucun banc de test JS ; supprimer `replayOf: p.replay_of` ou inverser la paire par défaut passerait pytest et `node --check`. Relevé par la couche verification-gap de la revue de la story 9b. Piste sans dépendance : `node:test` avec `node:vm`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/10-scenarios-par-brique-programme-reinitialisation.md`
  summary: Le rendu front de la story 10 (sélecteur de scénario et option suivant `active`, consigne et puces de prompts suggérés, `harness_reset` : « Aucun tour », journal affiché depuis `logFrom`, préparation du harnais gardée, message de la barre haute) n'est vérifié par aucun test automatique.
  evidence: Même écart que pour les stories 5b à 9b : aucun banc de test JS ; rétablir l'ancien `cleared()` passerait pytest et `node --check`. Relevé par la couche verification-gap de la revue de la story 10. Piste sans dépendance : `node:test` avec `node:vm`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/10-scenarios-par-brique-programme-reinitialisation.md`
  summary: RÉSOLU (story 10b) — le scénario « MCP en documentation complète » (serveur local + data.gouv.fr) ne débordait pas la fenêtre de 4 096 tokens : `expects_overflow` a été retiré et la consigne reformulée autour d'une jauge presque pleine.
  evidence: Test manuel du 2026-09-25 sur le PC cible : jauge à 3 018 / 3 584 tokens utiles pour `mcp_full` (pas de dépassement), contre environ 1 040 tokens pour `mcp_lazy`. Voir aussi les deux entrées ci-dessous.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/10-scenarios-par-brique-programme-reinitialisation.md`
  summary: Le tour du scénario « MCP en documentation complète » dépasse largement le NFR-1 (temps de réponse) sur le PC cible.
  evidence: Test manuel du 2026-09-25, Qwen3.5-2B Q4_K_M (CPU) : contexte de 3 018 tokens, tour de 109,5 s pour 91 tokens de sortie. Bien au-delà des temps mesurés en story 9 pour des contextes de 560 à 1 400 tokens (voir entrée ci-dessus sur les temps de réponse). À surveiller en séance : prévenir l'auditoire, ou réduire les serveurs MCP actifs avant démonstration.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/10-scenarios-par-brique-programme-reinitialisation.md`
  summary: Risque BH1a (navigation clavier du sélecteur de scénario sous Windows) non vérifié au test manuel.
  evidence: Test manuel du 2026-09-25 : l'animateur a utilisé la souris pour choisir les scénarios, les flèches clavier sur le `<select>` n'ont pas été testées sur le PC cible (Windows). À revérifier au clavier avant une séance qui en dépendrait.

- source_spec: `_bmad-output/implementation-artifacts/spec-10b-corrections-test-manuel-story-10.md`
  summary: Le bouton d'aide « ? » et sa bulle (`popover` natif) des cartes de briques, ainsi que le vidage de `store.openExplanations` par « ⟲ Réinitialiser », n'ont aucun test automatique.
  evidence: Même écart que pour les stories 5b à 10 : aucun banc de test JS. Relevé par la couche verification-gap de la revue de la story 10b. Piste sans dépendance : `node:test` avec `node:vm`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/11-modeles-cloud-via-api-groq-mistral.md`
  summary: Non vérifié (medium si réel) — deux appels d'outils parallèles d'une même réponse seraient fusionnés si le fournisseur envoie le même `index` (ou aucun) pour chacun ; l'accumulation de `openai_chat._channels` se fait par `index`, puis `id`.
  evidence: Relevé par la revue de la story 11 (couche aveugle). À trancher au test manuel : demander à Groq puis à Mistral deux outils en un tour (ex. `get_datetime` et `calculator`) et lire `model_call_ended.tool_calls` ; si un seul appel aux noms collés apparaît, ouvrir un nouvel appel dès qu'un `id` différent arrive sur une clé déjà prise.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/11-modeles-cloud-via-api-groq-mistral.md`
  summary: Non vérifié (medium si réel) — en mode chat, un échange d'historique sans texte (réponse de raisonnement seul) part en message `assistant` au `content` vide et sans `tool_calls`, que Mistral pourrait refuser (400) aux tours suivants.
  evidence: Relevé par la revue de la story 11 (couche cas limites), `AppSession._messages`. À trancher : obtenir un tour terminé sans texte avec Mistral, puis envoyer un second message et lire la réponse du fournisseur ; si 400, omettre `content` vide ou sauter l'échange dans le corps chat.

- source_spec: `_bmad-output/implementation-artifacts/spec-11b-corrections-test-manuel-story-11.md`
  summary: Le front de la story 11b (entrée « Diagnostic » du menu « Volets ▾ », bloc `#next-launch` du diagnostic, ligne « Clé fournie par la variable X » et piste `key_env`) n'a aucun test automatique.
  evidence: Même écart que pour les stories 5b à 11 : aucun banc de test JS ; retirer le lien de `renderMenu` ou le remplissage de `#next-launch` dans `loadDiagnostic` passerait pytest et `node --check`. Relevé par la couche verification-gap de la revue de la story 11b. Piste sans dépendance : `node:test` avec `node:vm`.

- source_spec: `_bmad-output/implementation-artifacts/spec-11b-corrections-test-manuel-story-11.md`
  summary: Aucune attribution visible de la source dans les réponses : quand le modèle s'appuie sur un résultat d'outil (par exemple le glossaire du serveur MCP local), rien n'indique « d'après le glossaire ». Piste : consigne du prompt système ou mise en avant, dans la Vue humain, des résultats d'outil dont la réponse s'inspire.
  evidence: Test manuel de la story 11b, 2026-09-26, scénario « Lazy loading » avec Groq : la réponse à « Que veut dire MCP ? » paraphrase l'entrée `MCP` de `content/mcp_local/glossary.yaml` sans la nommer ; l'animateur a cru que le glossaire n'avait pas servi. « La réponse cite le glossaire » (spec 11b) voulait dire « reprend sa définition ».

- source_spec: `_bmad-output/implementation-artifacts/spec-11b-corrections-test-manuel-story-11.md`
  summary: Mistral répond 429 à tout appel quand l'espace de travail n'a aucun quota actif ; le texte affiché (« quota dépassé (par seconde, par minute ou par jour) » et la piste `min_interval_s`) oriente à tort vers l'espacement. Piste : reconnaître `x-ratelimit-limit-req-minute: 0` et afficher « aucun quota actif sur ce compte : vérifiez le plan dans la console du fournisseur ».
  evidence: Sonde directe du 2026-09-26 sur le PC cible : trois appels espacés de plus d'1 s, tous en 429, corps `{"message":"Rate limit exceeded","type":"rate_limited","code":"1300"}`, en-têtes `x-ratelimit-limit-req-minute: 0` et `x-ratelimit-remaining-req-minute: 0`. La spec 11b interdit de déduire quoi que ce soit des en-têtes `x-ratelimit-*` (Never) : lever cette interdiction pour un message d'explication seulement (ni attente ni nouvel essai) est une décision à prendre. À vérifier dans la console Mistral : plan « Experiment » activé et vérification par téléphone faite.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/13-raisonnement.md`
  summary: Le front de la story 13 (option « Afficher le raisonnement », reasoning-block de la Vue humain et de Contexte LLM, carte « toujours active pour ce modèle ») n'a aucun test automatique.
  evidence: Même écart que pour les stories 5b à 11b : aucun banc de test JS ; retirer le bloc de Contexte LLM ou ignorer l'option passerait pytest et `node --check`. À couvrir par le harnais E2E (tools/e2e/, faux serveur compatible OpenAI + Playwright) dès qu'il est disponible.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/13-raisonnement.md`
  summary: Non vérifié (medium si réel) — renvoi du raisonnement (`reasoning.resend = true`) au format `field` sous la clé `reasoning` du message assistant : aucun préréglage ne le déclare, forme jamais essayée contre un fournisseur réel.
  evidence: Forme tirée d'AD-4 (« dans la forme reçue ») ; tests avec MockTransport seulement. À trancher en déclarant `resend = true` dans settings.json pour une entrée `field` puis en menant un tour avec outil : si le fournisseur refuse (400), renvoyer sous le nom de champ reçu (`reasoning` ou `reasoning_content`).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/13-raisonnement.md`
  summary: Écart H6 de la story 13 — le préréglage Mistral garde `reasoning.resend = false`, alors qu'AD-20 et le Deferred du spine disent « vrai pour Mistral » (renvoi des blocs `thinking`).
  evidence: Laissé à faux faute de test réel : renvoyer un bloc `thinking` à mistral-small-latest n'a jamais été essayé et pourrait valoir un 400. À trancher sur le PC cible, brique Raisonnement active : déclarer `resend = true` pour `mistral` dans settings.json, mener un tour avec outil puis un second tour ; si Mistral accepte, passer le préréglage à vrai, sinon amender AD-20.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/13-raisonnement.md`
  summary: Critère d'acceptation 3 de la story 13 (brique Raisonnement voulue, indisponible avec un modèle qui ne raisonne pas, redevenue effective sans nouveau clic avec un modèle qui raisonne) non testé.
  evidence: Le changement de modèle à chaud n'existe pas encore (story 17) ; la disponibilité est bien calculée au point unique d'AD-12 et `wanted` n'est jamais modifié par un chargement. Écrire le test avec la story 17 (select_model hors diagnostic).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/13-raisonnement.md`
  summary: `_resend()` est lu dans la configuration courante à chaque rendu plutôt que figé dans le `TurnState`, et le raisonnement d'un tour passé repart (avec `resend = true`) même quand la brique Raisonnement est éteinte.
  evidence: Comportement non spécifié par AD-4 ni AD-17 ; sans effet tant qu'aucun préréglage ne déclare `resend` (la déclaration ne change pas pendant une session). À trancher si un préréglage passe `resend = true` : figer le format au début du tour, et décider si l'historique renvoie le raisonnement brique éteinte.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/13-raisonnement.md`
  summary: Contexte LLM ne montre que le raisonnement du dernier appel du tour affiché ; la Vue humain montre, elle, un bloc par appel.
  evidence: Même périmètre que la « Sortie brute du modèle » (dernier appel seulement) ; le raisonnement des appels précédents reste dans l'étape « Appel au modèle » d'Orchestration et dans le journal. À reprendre si Contexte LLM permet un jour de choisir l'appel affiché.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/14-memoire-globale.md`
  summary: Le scénario « Mémoire globale » ouvre un module en fin de programme (après « Raisonnement ») au lieu de suivre l'ordre de FR-38 (module 1, après « Prompt système »). À réordonner à la story 21 avec les autres modules du palier 2.
  evidence: Choix H11 de la story 14 : placé au module 1, il aurait dû rejoindre les premiers scénarios des modules 2 à 5 (convention cumulative de `content/scenarios.yaml`, CAP-40), ce que la section Never de la spec renvoie à la story 21. Même situation que le module « Raisonnement » de la story 13. Point confirmé par la revue indépendante de la story 14.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/14-memoire-globale.md`
  summary: Le tiroir de la mémoire globale n'affiche pas la date d'écriture (`created_at`) des entrées, seulement leur origine (démonstration, modèle, utilisateur).
  evidence: Revue indépendante de la story 14. `created_at` est écrit dans memory.json et porté par `memory_changed` ; EXPERIENCE.md ne demande que consulter, modifier, supprimer et tout effacer. À ajouter si la date aide la démonstration (format court, fuseau du poste).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/14-memoire-globale.md`
  summary: Aucun ajout d'entrée depuis le tiroir : l'utilisateur écrit par l'action forcée « Écrire en mémoire ».
  evidence: Exclu par la spec de la story 14 (Never, hypothèse H1) ; relevé par la revue indépendante. À rouvrir seulement si le test manuel montre que le forçage est trop détourné pour ajouter une information.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/14-memoire-globale.md`
  summary: Une mémoire globale pleine (20 entrées de 300 caractères) prend environ 1 550 tokens estimés, soit près de 60 % de l'espace utilisable d'une fenêtre de 4 096 tokens avec la réserve du raisonnement ; elle tient avec les briques du scénario (test), mais laisse peu de place au reste.
  evidence: Revue indépendante de la story 14 ; mesure de `test_a_full_memory_fits_the_smallest_window_with_the_scenario_bricks` (estimation à 4 caractères par token). La borne de 300 caractères est dans le contrat d'intention de la story (non modifiable par l'implémentation). À trancher au test manuel sur le PC cible avec Qwen : si une mémoire chargée fait déborder le scénario, abaisser `MAX_CHARS` (par exemple à 200) en amendant la spec.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/12-tests-prealables-headroom-embedding-et-reranking.md`
  summary: Le verdict embedding et reranking de la story 12 reste provisoire (granite-embedding-107m-multilingual Q8_0, bge-reranker-v2-m3 Q4_K_M) ; lancer sur le PC cible, avant la story 15, `uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download`, puis `uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom`, et reporter les deux sorties `--json` dans la story 12.
  evidence: Le conteneur de développement n'atteint pas huggingface.co (`ProxyError('403 Forbidden')` pour les 7 candidats) : aucune qualité, aucun RSS de modèle n'a été mesuré ; le code du banc est seulement validé sur des GGUF synthétiques. Les mesures Headroom (+130 Mo, aucune tentative réseau) viennent de Linux, pas du HP EliteBook sous Windows 11, où `strace` manque pour voir le code natif.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/17-changement-de-modele-a-chaud.md`
  summary: Le budget mémoire n'est pas contrôlé au chargement du lancement (hypothèse C2) : le coût du modèle est seulement enregistré dans le `LoadRegistry` ; seuls les changements à chaud sont refusés sur budget.
  evidence: Choix gardé par la revue indépendante de la story 17 : au lancement, aucun modèle actif n'est à protéger, et un refus bloquerait la séance sans autre recours que d'éditer `wavestack.toml`. À valider au test manuel sur le PC cible ; si un modèle trop gros au lancement fait échouer la séance, refuser avec le message chiffré et renvoyer au diagnostic.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/17-changement-de-modele-a-chaud.md`
  summary: L'estimation du cache KV (`kv_bytes_per_token`) n'est pas mesurée sur un vrai GGUF Qwen3.5 : surestimation possible (fenêtre glissante non prise en compte) au point de refuser un 4B sous le budget de 4 Go, ou cache inconnu (0) si llama-cpp-python ne rend le tableau des têtes KV qu'en texte.
  evidence: Revue de la story 17 (blind hunter, maybe-false). Aucun GGUF dans le conteneur de développement. À mesurer sur le PC cible : sonder Qwen3.5-2B et 4B, relire `rss_bytes` et `kv_bytes_per_token` dans `settings.json` (`probed_models`), puis tenter le changement 2B vers 4B.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/17-changement-de-modele-a-chaud.md`
  summary: Le critère d'acceptation 3 de la story 13 (brique Raisonnement redevenue effective sans nouveau clic avec un modèle qui raisonne) reste sans test dédié, bien que le changement à chaud existe maintenant.
  evidence: La story 17 teste la même règle pour la brique Outils (`test_lost_capability_leaves_wanted_and_comes_back`) : disponibilité au point unique `_availability`, `wanted` jamais modifié. Un test Raisonnement demande un faux moteur dont le gabarit porte `enable_thinking` ; à écrire avec la prochaine story qui touche au raisonnement.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/19-delegation-a-un-sous-agent.md`
  summary: Écart d'architecture (AD-11, AD-12) : `contributes_to` n'est lu que pour les outils du sous-agent (brique `tools`) et pour le raisonnement ; la composition du reste du contexte `sub{n}` (prompt du sous-agent, tâche, aucune autre brique) est écrite dans `_sub_messages`, pas dérivée des briques qui déclarent `sub`.
  evidence: Revue indépendante de la story 19. Aucune autre brique ne contribue au sous-agent aujourd'hui, le résultat est donc le même ; à généraliser quand une brique (RAG, mémoire globale…) devra y entrer : itérer sur les briques effectives qui déclarent `sub`.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/19-delegation-a-un-sous-agent.md`
  summary: Sur un SLM local réel (Qwen3.5 0.8B ou 2B), vérifier que le modèle délègue au lieu de lire guide_harnais.md lui-même, et que le contexte du sous-agent (guide ≈ 2 000 tokens) tient dans 4 096 − 512 tokens.
  evidence: Aucun GGUF dans le conteneur : le faux moteur compte un token par octet, le faux modèle cloud du parcours E2E donne 2 112 tokens de contexte au sous-agent. À régler au test manuel, scénario « Sous-agent ».

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/19-delegation-a-un-sous-agent.md`
  summary: Avec Qwen3.5, le gabarit peut réécrire l'appel d'outil du sous-agent (`prefix_not_reused` dans `sub{n}`).
  evidence: Même mécanisme qu'en contexte principal (AD-4) ; à observer sur le PC cible, sans effet sur le résultat de la délégation.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/15-corpus-de-demonstration-et-rag-simple.md`
  summary: AD-9, adéquation du scénario « RAG » : l'aperçu compte les 3 extraits les plus longs de l'index (leur maximum déclaré) ; vérifier sur le PC cible, avec Qwen3.5 et la fenêtre de 4 096 tokens, que le scénario cumulatif (modules 1 à 4, MCP en lazy loading, RAG) tient, et mesurer la latence de l'étape « Recherche RAG » (NFR-1).
  evidence: Revue indépendante de la story 15. Le faux moteur compte un token par octet et le faux modèle cloud estime à 4 caractères par token : aucune mesure réelle. À relever au test manuel (jauge avant envoi, durée de l'étape dans Orchestration).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/15-corpus-de-demonstration-et-rag-simple.md`
  summary: Intégrité du modèle d'embedding : l'URL de `[rag.embedding]` vise `resolve/main` et `sha256` est vide ; épingler l'URL sur un commit du dépôt bartowski et renseigner le sha256.
  evidence: Le connecteur Hugging Face de la session ne donne que la taille (121 020 096 octets, LFS), ni l'oid LFS ni le commit ; huggingface.co est bloqué dans le conteneur. Le premier téléchargement sur le PC cible trace le sha256 du fichier (effet `model_download` dans le journal) ; le recopier dans `files[].sha256`, et remplacer `main` par le commit affiché sur la page du fichier. Dès lors, `Télécharger`, le chargement et `scripts/build_rag_index.py --model` le vérifient.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/15-corpus-de-demonstration-et-rag-simple.md`
  summary: Sur le PC cible (Windows, Python de uv) : chargement de l'extension sqlite-vec, pooling CLS déclaré par le GGUF granite (sonde au chargement), et `uv lock` à confirmer (entrée sqlite-vec écrite à la main faute d'accès à l'index abetlen).
  evidence: Vérifiés ici seulement sous Linux, sans vrai modèle (GGUF BERT synthétique, faux embedder). À trancher : la carte RAG ne doit pas dire « sqlite-vec ne se charge pas » ; `uv run python -m pytest -m model tests/test_rag.py` doit passer, modèle en place ; `uv lock` ne doit rien changer.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/15-corpus-de-demonstration-et-rag-simple.md`
  summary: « Arrêter » un téléchargement pendant l'établissement de la connexion ne prend effet qu'au bout du délai de connexion (10 s au plus) ; pendant l'attente des données, il agit aussitôt (la réponse est fermée).
  evidence: Revue indépendante de la story 15 (edge cases). httpx ne permet pas d'interrompre proprement un `connect` depuis un autre fil ; le délai a été ramené de 30 à 10 s. À rouvrir si le test manuel montre une attente gênante sur le réseau du client.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/17-changement-de-modele-a-chaud.md`
  summary: Page de diagnostic, « Choisir » un modèle : quand `/api/diagnostic/stream` rejoue un long journal depuis le début, le repli de la page (« Le modèle choisi est actif. », après 3 s) s'affiche avant le `model_load_ended` et son texte « {modèle} est actif. ».
  evidence: Vu au parcours E2E complet après la revue de la story 15 (plus d'événements avant le scénario `model_switch`) ; le scénario seul passe. Les deux textes disent que le changement a réussi : le parcours accepte les deux. À corriger dans diagnostic.html (reprendre le flux au `seq` de `/api/state`, ou armer le repli seulement une fois le rejeu fini).
- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/18-serveur-local-deja-lance-ollama-llama-server.md`
  summary: Les champs réels de llama-server (`/props`, `with_pieces`, `stop_type`, `tokens_predicted`, `default_generation_settings.n_ctx` par emplacement) et d'Ollama (`raw`, `prompt_eval_count` avec cache, `done_reason`, `/api/ps`) ne sont vérifiés que sur des doublures.
  evidence: Aucun réseau ni serveur réel pendant la story. Un tour avec `get_datetime` sur chacun des deux serveurs, sur le PC cible, tranche ; noter toute alerte « transparence réduite » et les deux comptes qu'elle cite.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/18-serveur-local-deja-lance-ollama-llama-server.md`
  summary: Le tokenizer `vocab_only` des blobs `qwen35` d'Ollama avec llama-cpp-python 0.3.35 n'est pas vérifié sur un vrai blob.
  evidence: Un GGUF synthétique étiqueté `qwen35` s'ouvre en `vocab_only` (architecture et tokenizer seuls) ; l'échec connu de ces blobs (story 9) concerne le chargement complet. Sur le PC cible : choisir un modèle Qwen3.5 servi par Ollama ; s'il est refusé, la raison doit renvoyer vers llama-server et le modèle précédent rester actif.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/18-serveur-local-deja-lance-ollama-llama-server.md`
  summary: `keep_alive: 0` et le budget d'un modèle servi ne sont vérifiés qu'avec des doublures.
  evidence: Sur le PC cible, `ollama ps` doit être vide après un changement de modèle et après la fermeture de WaveStack, pour un modèle que WaveStack a fait charger ; un modèle déjà chargé par un autre programme doit y rester. La taille rapportée par `/api/ps` après le premier appel doit correspondre au coût compté.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/18-serveur-local-deja-lance-ollama-llama-server.md`
  summary: La coupure de la socket à l'annulation (`shutdown` depuis un fil de veille) n'est vérifiée que sous Linux, contre une socket de test.
  evidence: Sous Windows, face à un vrai Ollama qui charge un modèle, « Arrêter » et la fermeture de WaveStack doivent rendre la main en moins d'une seconde ; sinon, l'arrêt attend le premier token ou le délai de lecture (`[model_servers] read_timeout_s`).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/20-compression-du-contexte.md`
  summary: AD-13 : `transform_context` n'est pas un point d'accroche de hook. La compression agit sur les parties du tour avant l'assemblage (réponses d'outils, extraits RAG), à la place de l'étape d'AD-4, sans qu'un hook puisse l'observer ni la modifier.
  evidence: Revue indépendante de la story 20. Aucun hook de démonstration n'en a besoin en V1 ; à ouvrir si un hook doit voir le contexte compressé (ajouter le point au catalogue d'AD-13 et l'appeler depuis `_transform_context`).

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/20-compression-du-contexte.md`
  summary: H-1 de la story 20 : `transform_context` compresse chaque texte avant le premier appel qui le lit (et non seulement avant le premier appel du tour). Décision provisoire, ligne de règle d'AD-4 amendée et marquée « à valider ».
  evidence: Question posée à Anaël (memlog de la spec) ; décision attendue au test manuel. Défaut : garder H-1. Si la lecture stricte l'emporte, seuls les extraits RAG et les actions forcées seraient compressés.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/20-compression-du-contexte.md`
  summary: `compress()` de Headroom n'a pas de borne de temps : un texte pathologique pourrait retenir le tour ; « Arrêter » n'agit qu'entre deux textes.
  evidence: Headroom ne s'annule pas et n'est pas sûr entre fils : l'appeler dans un fil séparé abandonné laisserait un calcul concurrent. Mesuré : 2,2 s au pire (premier appel, JSON de 6 600 tokens), 0,02 s ensuite. À rouvrir si le PC cible montre une attente gênante.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/20-compression-du-contexte.md`
  summary: Sur le PC cible : mémoire ajoutée par Headroom, absence de sortie réseau, AppLocker et WDAC face à `_core.pyd` et `ast-grep` ; le scénario « Compression » doit tenir dans la fenêtre sans compression, avec un vrai SLM, et le modèle ne doit pas appeler un outil « Retrieve more » inexistant.
  evidence: Mesures hors PC cible seulement (story 12 : 130 Mo, aucune tentative réseau). Parcours E2E : 1 865 tokens sans compression, 1 437 envoyés, pour 3 584 utilisables.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/20-compression-du-contexte.md`
  summary: uv.lock : les entrées de headroom-ai 0.38.0 et de ses dépendances ont été écrites à la main, l'index abetlen étant injoignable.
  evidence: `uv lock --check --offline`, `uv sync --locked` et `uv sync --locked --extra compression` passent ; `uv lock` sur un poste qui joint l'index abetlen doit ne rien changer.
