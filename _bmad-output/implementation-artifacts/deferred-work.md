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
