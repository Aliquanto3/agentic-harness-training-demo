---
title: 'Interface à volets et journal d''événements'
type: 'feature'
created: '2026-09-23'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '02016def1a57d1c74ebb61a545645a19e3ee5a56'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** WaveStack n'a qu'une page de diagnostic minimale (story 1). Aucune des CAP-1 à CAP-4 (vue humain, contexte LLM, orchestration, schéma d'architecture, panneau des briques, synchronisation) n'existe, et le front n'a aucun magasin unique de projection du journal d'événements (AD-1).

**Approach:** Construire la grille à 5 volets masquables (AD-18, JS natif sans compilation) et le magasin client unique qui consomme tout le flux SSE existant pour projeter l'état — sans aucune brique active : LLM nu, historique vide, schéma limité aux deux nœuds fixes `core.harness`/`core.model`. Étendre `trace` du seul `kind` `architecture_changed` (AD-12) qu'il faut pour alimenter le schéma ; les autres volets restent à l'état vide, pédagogiquement explicite.

## Boundaries & Constraints

**Always:**
- AD-1 : un seul magasin de projection JS consomme tous les événements SSE, volets visibles ou masqués ; le front ne recalcule aucune donnée métier (tokens, disponibilité...), seulement mise en forme, écarts entre valeurs reçues, chronomètre local.
- AD-2 : ajouter uniquement le `kind` `architecture_changed` (et son modèle pydantic) au catalogue existant (`trace/catalog.py`) ; ne jamais modifier `Envelope`.
- AD-12 : `architecture_changed{nodes, edges}` n'est émis que par la session ; nœuds réservés `core.harness`, `core.model` seulement pour cette story (aucune brique).
- AD-18 : FastAPI sert API/SSE/statique sur `127.0.0.1` seul, pas de build ; `static/tokens.css` reprend sous les mêmes noms les jetons `colors`, `typography`, `rounded`, `spacing` du frontmatter de `DESIGN.md`, vérifié par un test pytest qui parse les deux.
- NFR-7 : tout texte affiché en français ; code, identifiants, docstrings en anglais.
- Grille et comportements de volet (masquer/réafficher via puce, menu « Volets ▾ », mode focus, au moins un volet visible) conformes à EXPERIENCE.md §Component Patterns et §Interaction Primitives.

**Never:**
- Pas de contenu de brique (panneau des briques reste vide, story 4), pas de génération de réponse ni de composer fonctionnel (LLM nu arrive en story 3), pas de segments de contexte réels, pas de scénario/modèle/taille de texte/réinitialisation dans la barre haute (stories 9, 10, 34).
- Aucune bibliothèque ou build JS ajoutée ; modules ES natifs recopiés seulement si besoin (AD-18).
- Ne pas modifier les routes et le comportement `/diagnostic` de la story 1 (gelés, `done`) au-delà d'un lien vers la nouvelle page une fois le diagnostic prêt.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Chargement initial | `GET /` après diagnostic prêt | `GET /api/state` peuple le magasin, puis le flux SSE reprend à `seq` suivant ; schéma affiche `core.harness`/`core.model` | N/A |
| Reconnexion SSE | Coupure réseau locale puis reprise | `Last-Event-ID` reprend sans doublon ni trou | Keep-alive déjà géré comme en story 1 |
| Masquer le dernier volet visible | Un seul volet visible, clic « — » | Bouton désactivé, infobulle FR | N/A |
| Volet masqué contient l'élément sélectionné | Sélection d'un nœud puis masquage de son volet | La puce du volet masqué porte la marque « lié » | N/A |
| `kind` inconnu du front reçu dans le journal | Événement futur non géré spécifiquement | Le journal (Orchestration) l'affiche en brut (`kind` + `payload`) sans casser le rendu | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/trace/catalog.py` -- ajouter `ArchitectureNode{id, kind, hosting, label_fr, wanted, available, reason_fr}`, `ArchitectureEdge{from_, to, crosses_boundary}`, `ArchitectureChangedPayload{nodes, edges}` ; enregistrer `"architecture_changed"` dans `PAYLOAD_MODELS`.
- `src/wavestack/session/app_session.py` (nouveau) -- `AppSession` minimal : état fixe `idle` (AD-3), `emit_initial()` qui pousse `session_state{state:"idle"}` puis `architecture_changed` avec les deux nœuds fixes `core.harness`/`core.model` (locaux, `wanted=available=True`), aucune arête.
- `src/wavestack/web/app.py` -- réutiliser `Journal`/`_format_sse` (déjà écrits story 1) : ajouter `GET /` (sert `static/index.html`), `GET /api/state` (dernier `session_state` + `architecture_changed` connus), `GET /api/stream` (SSE générique, même logique de reprise que `/api/diagnostic/stream`). Ne pas toucher aux routes `/diagnostic*` existantes.
- `src/wavestack/web/static/index.html`, `static/app.js`, `static/app.css`, `static/tokens.css` (nouveaux) -- grille 5 volets (barre haute minimale, panneau des briques vide, vue humain avec composer désactivé, Contexte LLM vide, Orchestration = journal brut des événements, bande basse = schéma SVG des 2 nœuds fixes), magasin de projection unique, masquage/puce/menu/mode focus, sélection synchronisée par `data-component`.
- `src/wavestack/web/static/diagnostic.html` -- une fois `ready`, afficher un lien « Ouvrir WaveStack » vers `/`.
- `src/wavestack/cli.py` -- après diagnostic prêt, construire `AppSession` et appeler `emit_initial()`.
- `tests/test_trace_architecture.py` (nouveau) -- validation payload `architecture_changed`.
- `tests/test_web_tokens.py` (nouveau) -- `static/tokens.css` reprend exactement les jetons `colors`/`typography`/`rounded`/`spacing` du frontmatter de `DESIGN.md`.
- `tests/test_web_app.py` (nouveau ou étendu) -- `GET /`, `GET /api/state`, reprise `/api/stream` par `Last-Event-ID`.

## Tasks & Acceptance

**Execution:**
- [x] `trace/catalog.py` -- ajouter `architecture_changed` et ses modèles -- AD-2, AD-12
- [x] `session/app_session.py` -- état `idle` + émission initiale des 2 nœuds fixes -- AD-3, AD-12
- [x] `web/app.py` -- routes `/`, `/api/state`, `/api/stream` -- AD-18, AD-1
- [x] `web/static/{index.html,app.js,app.css,tokens.css}` -- grille 5 volets, magasin de projection, masquage/focus/sync -- AD-1, AD-18, EXPERIENCE.md
- [x] `web/static/diagnostic.html` -- lien vers `/` une fois prêt
- [x] `cli.py` -- brancher `AppSession.emit_initial()` après diagnostic -- AD-3
- [x] `tests/*` -- payload, tokens.css vs DESIGN.md, routes/SSE -- non-régression AD-2/AD-12/AD-18

**Acceptance Criteria:**
- Given le diagnostic prêt, when l'utilisateur ouvre `/`, then les 5 volets s'affichent et le schéma montre `core.harness` et `core.model` sans aucune brique.
- Given un volet masqué contenant l'élément sélectionné, when la sélection change, then sa puce dans la barre haute porte la marque « lié ».
- Given une reconnexion SSE avec `Last-Event-ID`, when le flux reprend, then aucun événement n'est perdu ni dupliqué dans le journal.
- Given `static/tokens.css`, when comparé au frontmatter de `DESIGN.md`, then chaque jeton `colors`/`typography`/`rounded`/`spacing` a la même valeur sous le même nom.

## Implementation Notes

- Implémenté par un sous-agent d'implémentation (dispatch), puis vérifié dans cette session.
- Audit de la matrice I/O : les lignes « chargement initial » et « reconnexion SSE » ont un test automatisé (`tests/test_web_app.py`). Les lignes « masquer le dernier volet visible », « volet masqué lié à la sélection » et « `kind` inconnu affiché en brut » sont purement front (JS natif, aucun framework de test JS dans ce projet — `pyproject.toml` ne déclare que `pytest`/`ruff`, AD-18 ne prévoit aucune chaîne de build/test JS) : vérifiées manuellement dans Chrome via un serveur de prévisualisation (`AppSession().emit_initial()` + `uvicorn`) — bouton/case « — » désactivés avec l'infobulle « Au moins un volet reste visible. » sur le dernier volet visible, puce « ● + Schéma d'architecture » marquée liée après sélection d'un nœud puis masquage de son volet, aucune erreur console pendant tout le parcours.
- `ruff check`, `ruff format --check` et `pytest` (43 passed, 1 deselected -- test `model`, inchangé depuis la story 1) exécutés et verts.

## Spec Change Log

## Review Triage Log

Pass 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 layers, 15 findings) :

- [VG1] `select_model` (`web/app.py:93-96`) ne branche jamais `AppSession().emit_initial()` : un utilisateur sans modèle auto-détecté qui en choisit un manuellement via `/diagnostic` obtient `ready=True` mais `/api/state` reste `null`/`null` à jamais, le schéma ne s'affiche jamais sur `/` — viole directement le critère d'acceptation « le schéma montre core.harness et core.model ». `high`, confirmé (grep : aucun appel à `emit_initial`/`AppSession` dans `web/app.py`). → groupe G1, `patch`.
- [BH8/EC1-doublon] Même chemin que VG1 décrit sous l'angle « pas de signal distinctif quand le diagnostic ne devient jamais prêt » — fusionné dans G1 pour la partie réelle (select_model) ; la partie « diagnostic jamais prêt » est traitée séparément ci-dessous (EC1).
- [BH3] `tests/test_web_tokens.py` code en dur le nom daté du dossier UX (`ux-agentic-harness-training-demo-2026-09-22`) : cassera par un `FileNotFoundError` non lié si ce dossier est régénéré/renommé — `low`, confirmé, correction triviale (glob `ux-designs/*/DESIGN.md`). → groupe G2, `patch`.
- [BH4] Le menu « Volets ▾ » ne se ferme jamais au clic extérieur ni à `Échap` (seul le mode focus écoute `Échap`) — `low`, confirmé (grep : aucun listener `click`/`keydown` visant la fermeture du menu), rencontré à chaque utilisation normale du menu, correction contenue (un listener). → groupe G3, `patch`.
- [BH5] Les boutons d'icône seule ⛶/— n'ont qu'un `title`, jamais annoncé de façon fiable par les lecteurs d'écran — `low`, confirmé (grep sur `index.html`), correction triviale (`aria-label` reprenant le `title`). → groupe G4, `patch`.
- [BH1/BH2] `renderSchema`/`app.css` ignorent `hosting`, `wanted`, `available`, `reason_fr` du payload (toujours peint en violet « local ») — réel mais invisible tant que les deux nœuds fixes de cette story sont locaux et toujours disponibles ; l'intent gèle explicitement le schéma à ces deux nœuds pour cette story. Hors périmètre par l'intent lui-même (pas par la seule section Boundaries), pas une régression. → `defer`.
- [BH6] `streamEvents` retente indéfiniment toutes les 1 s sans indicateur « hors ligne » visible — réel mais aucun critère d'acceptation ni ligne de la matrice n'exige un indicateur de connexion, et la barre haute est volontairement réduite au strict nécessaire pour cette story (Design Notes). → `defer`.
- [BH7] `AppSession` est une instance jetable, jamais un singleton référencé ailleurs — question d'architecture pour la story 3 (mutation de l'état de session), pas un défaut de cette story (`état fixe idle`). → `defer`.
- [EC2] Aucun `try/except` autour de la cible du thread diagnostic (`cli.py`) — préexistant : `session.run()` tournait déjà seul, sans protection, dans ce même thread avant cette story ; cette story ajoute seulement un appel supplémentaire au même risque déjà présent. → `defer`.
- [EC5] `ArchitectureEdge` ne valide pas que `from_`/`to` référencent des nœuds existants — cette story n'émet jamais d'arête (`edges: []`) ; à traiter avec la story qui introduira de vraies arêtes. → `defer`.
- [VG2] Le branchement `cli.py` diagnostic → `AppSession` n'est exercé par aucun test de bout en bout (`main()` bloque sur `uvicorn.run`, chaque moitié est testée isolément) — disposition déposée par la couche verification-gap elle-même : `defer`, refactor (extraire `_run_diagnostic_then_boot` en fonction injectable) non nécessaire pour livrer cette story.
- [EC1] « Pas de signal distinctif si le diagnostic ne devient jamais prêt » — `false`, réfuté : `/diagnostic` et `/api/diagnostic` portent déjà ce signal (`blocking_checks`), et l'UI ne route jamais vers `/` avant `ready` (le lien « Ouvrir WaveStack » n'apparaît que si `ready`).
- [EC3] `parseSseEvent` ne validerait pas la présence de `seq`, risquant `Last-Event-ID: undefined` puis rejeu/doublons — `false`, réfuté : `Envelope.seq` est un champ pydantic requis (`envelope.py`), le serveur ne peut jamais sérialiser un événement sans lui.
- [EC4] Croissance non bornée de `store.journal` (et du journal serveur) sur une session longue — `low`, rejeté : même raisonnement déjà tenu et accepté en story 1 (BH2 de son propre triage) pour le journal serveur, applicable ici au journal front ; session de démo pédagogique courte, correction (virtualisation de liste) non triviale pour un bénéfice marginal.

Groupes routés en `patch` (G1-G4, détail dans les instructions de correction envoyées au sous-agent) ; aucun `intent_gap` ni `bad_spec` — pas de loopback, `review_loop_iteration` reste à 0.

## Design Notes

Pas de bibliothèque JS (décision AD-18 différée jusqu'à cette story) : le schéma à 2 nœuds fixes ne justifie pas une dépendance de diagramme, du SVG écrit à la main suffit ; les stories suivantes (MCP, outils, skills) réévalueront si le graphe grossit. Barre haute réduite au strict nécessaire à cette story (titre, menu Volets, puces) ; scénario/modèle/taille de texte/réinitialisation sont des contrôles sans effet avant leurs stories propriétaires et seraient de la façade trompeuse.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent

**Manual checks (if no CLI):**
- `uv run wavestack`, attendre le diagnostic prêt, ouvrir `/` : les 5 volets sont visibles, masquer/réafficher chacun via « — » et via le menu « Volets ▾ », vérifier qu'au moins un volet reste toujours visible, cliquer un nœud du schéma et vérifier la surbrillance.
