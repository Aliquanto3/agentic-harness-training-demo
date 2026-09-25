- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/1-fondations-lancement-diagnostic-modele-local.md`
  summary: Aucun test n'exerce la branche « serveur déjà lancé » (`status: "server"`) de `DiagnosticSession.check_model()` — tous les tests forcent `discovery._server_candidates` à retourner une liste vide pour rester déterministes.
  evidence: Une régression qui exclurait `"server"` des candidats utilisables (ou casserait `_server_candidates`) empêcherait WaveStack de reconnaître un serveur Ollama/llama.cpp déjà lancé sans qu'aucun test n'échoue. Fermer l'écart demande un test de `_server_candidates` avec un transport httpx simulé ; raisonnable à ajouter lors du premier usage réel de la découverte serveur.

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
