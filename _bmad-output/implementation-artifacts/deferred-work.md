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
