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

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6c-refonte-visuelle-atelier-de-construction.md`
  summary: Dans le schéma, l'arête d'un nœud de la colonne 2 vers le cadre Harnais passe sous le nœud de la colonne 1 de la même ligne, ce qui se lit comme une chaîne (cadre → A → B).
  evidence: Visible dès 4 nœuds hors cadre (outils + serveurs MCP) ; à reprendre avec les zones Local / Réseau et la frontière de DESIGN.md, qui imposent de toute façon de refaire la disposition.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6c-refonte-visuelle-atelier-de-construction.md`
  summary: `robotPose()` et la clé de mémorisation de `renderSchema()` (`app.js`) ne sont couverts par aucun test automatique.
  evidence: Le dépôt n'a aucun banc de test JS ; oublier `pose` dans la clé figerait le robot sans qu'un test échoue. Poses vérifiées à la main pendant un vrai tour (story 6c). Même écart que la story 5b ; à fermer si un banc de test front est introduit.

- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/6c-refonte-visuelle-atelier-de-construction.md`
  summary: Sous le robot, un modèle chargé depuis un blob Ollama s'affiche `sha256-…` au lieu de son nom lisible.
  evidence: `boot(model_path)` ne reçoit que le chemin ; la découverte (`models/discovery.py`) connaît le nom affiché par le sélecteur du diagnostic. Transmettre ce nom demande de le faire passer par `boot` et `settings.json`.
