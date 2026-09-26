---
title: 'Correctif : courses du flux d''événements au rejeu (événements perdus, envoi silencieusement ignoré)'
type: 'bugfix'
created: '2026-09-26'
status: 'done'
baseline_revision: '0719050c74a252cd1a7bafdc76a3e1f392275730'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Une revue a relevé deux courses autour du rejeu du journal. (1) Serveur : `_sse_stream` envoie l'instantané `events_since(since_seq)` (chaque `yield` peut attendre la socket) puis seulement s'abonne ; un événement émis entre les deux est perdu pour cette connexion, et la fenêtre grandit avec le journal (la page principale, la page de diagnostic — qui peut rester sur « Chargement de … » jusqu'à 5 min si `model_load_ended` est perdu — et le parcours E2E en dépendent). (2) Page : `boot()` rejoue tout le journal et `applyEnvelope` réapplique chaque ancien `session_state` (et les autres états « dernier connu ») sans regarder `store.liveFrom` ; pendant le rejeu, le compositeur s'active et se désactive au gré des anciens états, et `sendMessage` ignore alors un envoi sans rien afficher. Le parcours E2E en souffre (envois perdus, échecs intermittents).

**Approach:** S'abonner avant de prendre l'instantané, puis ignorer dans la file les enveloppes déjà rejouées (`seq` ≤ dernier rejoué) : aucun événement perdu, aucun doublon, ordre conservé. Côté page, n'appliquer un état « dernier connu » rejoué que s'il est postérieur à l'instantané `/api/state` (`seq > store.liveFrom`), et ne jamais ignorer un envoi sans retour visible. Le parcours E2E attend `turn_started` après un envoi (sinon il dit l'état du compositeur et sa raison) et attend que la page ait rattrapé le rejeu après une navigation.

## Boundaries & Constraints

**Always:** code et identifiants en anglais, textes en français ; `uv`, `ruff`, `pytest` ; un seul flux SSE générique (AD-1) ; format des enveloppes inchangé ; modifications ciblées (les stories 16 et 21 modifient en parallèle `scenarios.yaml`, `fake_openai.py`, `run_e2e.py` pour `s_soc`/`s_programme`).

**Never:** retirer une vérification E2E ; toucher au contenu pédagogique (scénarios, textes des briques) ; nouvelle dépendance ; banc de test JS ; changer le format des événements ou de `/api/state`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Émission pendant le rejeu | Un `/api/stream` rejoue N enveloppes ; un événement est émis après la 1re | Il arrive une seule fois, après les N rejouées, `seq` strictement croissants | — |
| Émission entre abonnement et instantané | L'événement est à la fois dans la file et dans l'instantané | Envoyé une seule fois (le doublon de la file est ignoré) | — |
| Déconnexion pendant le rejeu | Le client part au milieu | Désabonnement garanti (`finally`) | — |
| Rechargement de la page principale | Journal long, dernier `session_state` = `idle` | Le compositeur reste dans l'état de `/api/state` pendant tout le rejeu | `/api/state` en échec : `liveFrom = 0`, tout s'applique comme avant |
| Envoi alors que l'entrée est désactivée | Entrée désactivée (tour en cours, modèle absent) | Message visible dans `#composer-reason` | — |
| Envoi d'un message vide | Entrée vide | Message visible (« Écrivez un message… ») | — |

</intent-contract>

## Code Map

- `src/wavestack/web/app.py` -- `_sse_stream` (~l. 590-622) : `yield` de `server_instance`, boucle sur `journal.events_since(since_seq)`, puis `journal.subscribe(_on_event)` ; `_on_event` pousse dans une `asyncio.Queue` via `loop.call_soon_threadsafe`.
- `src/wavestack/trace/journal.py` -- `Journal.subscribe/events_since/emit` : `emit` notifie hors verrou, dans l'ordre des `seq` (lecture seule ici).
- `tests/test_web_app.py` -- `_FakeRequest` et `test_stream_resumes_from_last_event_id_without_duplicates` : modèle de test direct de `_sse_stream` via `response.body_iterator`.
- `src/wavestack/web/static/app.js` -- `store.liveFrom` (l. 28, posé l. ~5105 depuis `/api/state.seq`) ; `applyEnvelope` (l. ~194) : `session_state` (l. ~207), `architecture_changed`, `context_preview`, `bricks_changed`, `memory_changed`, `armed_actions_changed`, `scenario_changed`, `harness_reset` (`topStatus`), `context_rendered`/`context_reconciled` (jauge) ; `model_load_ended` montre déjà le motif `envelope.seq > store.liveFrom` (l. ~271) ; `renderComposer` (l. ~2149) ; `sendMessage` (l. ~2302) ; `boot()` (fin de fichier) appelle `streamEvents(0, applyEnvelope)`. `app.js` est un module : `store` n'est pas visible depuis Playwright.
- `src/wavestack/web/static/diagnostic.html` -- `historyUpTo` (l. ~488) posé depuis `/api/diagnostic.seq` avant l'ouverture de `EventSource` ; le rejeu est déjà traité sans effets de bord ; seule la perte serveur pouvait bloquer « Chargement de … » (repli de 5 min).
- `tools/e2e/run_e2e.py` -- `Run.send` (l. ~160), `Run.replay`, `Run.wait_idle` (l. ~141), `s_local_server` (l. ~2236), `s_relaunch` (l. ~2388).

## Tasks & Acceptance

**Execution:**
- `src/wavestack/web/app.py` -- dans `_sse_stream`, s'abonner avant `events_since`, retenir le `seq` du dernier envoyé et ignorer dans la file toute enveloppe de `seq` ≤ ce repère ; abonnement et désabonnement dans le même `try/finally` -- plus aucune fenêtre de perte.
- `tests/test_web_app.py` -- deux tests : émission pendant le rejeu (arrive une fois, dans l'ordre) ; émission entre abonnement et instantané (pas de doublon) -- couvre la matrice serveur.
- `src/wavestack/web/static/app.js` -- n'appliquer les états « dernier connu » rejoués que si `envelope.seq > store.liveFrom` (`session_state` et `activeModel`, `architecture_changed`, `bricks_changed`, `armed_actions_changed` (les libellés restent tous retenus), `scenario_changed`, `memory_changed`, jauge de `context_preview/rendered/reconciled`, message de `harness_reset`) sans toucher aux projections des tours ; marquer `document.body.dataset.journalReplayed` quand le rejeu atteint `liveFrom` ; `sendMessage` affiche une raison au lieu d'ignorer (entrée désactivée ou vide).
- `tools/e2e/run_e2e.py` -- `send`/`replay` attendent `turn_started` (5 s) et, sinon, lèvent une erreur qui dit l'état du compositeur et `#composer-reason` ; barrière « rejeu rattrapé » (`body[data-journal-replayed]`) dans `wait_idle` et après les `goto`/`reload` de la page principale de `s_local_server` et `s_relaunch`.

**Acceptance Criteria:**
- Given un `/api/stream` en cours de rejeu, when un événement est émis, then le client le reçoit une seule fois, après les enveloppes rejouées, `seq` croissants.
- Given la page principale rechargée sur un journal qui contient des `session_state` passés non `idle`, when le rejeu se déroule, then le compositeur garde l'état donné par `/api/state` et un envoi n'est jamais ignoré sans message visible.
- Given la page de diagnostic ouverte pendant un changement de modèle, when `model_load_ended` est émis pendant le rejeu, then il est reçu (plus d'attente de 5 min).
- Given le parcours E2E complet, when il est lancé 3 fois de suite, then il est vert à chaque fois.

## Spec Change Log

## Review Triage Log

### 2026-09-26 — Review pass
Revue brève menée par l'agent lui-même (exécution sans outil de sous-agent, à la demande de l'appelant) : couches « chasseur aveugle », « cas limites », « écart de vérification » et « alignement sur l'intention » appliquées en une passe.
- verdicts: 6 findings — high 0, medium 2, low 2, false 2, maybe-false 0
- findings:
  - `[medium]` `[patch]` Serveur : `last_sent` initialisé à `since_seq` écarte les événements en direct d'un nouveau journal quand le client envoie le `Last-Event-ID` d'une autre instance (relance, onglet resté ouvert) — corrigé : `last_sent = 0` (seul ce qui a été rejoué est dédoublonné) ; test `test_stream_with_an_id_of_another_instance_still_sends_live_events`.
  - `[low]` `[patch]` Écart de vérification : le test de dédoublonnage se terminait avant de vider la file (la boucle s'arrête sur `is_disconnected`), un doublon serait passé inaperçu — corrigé : sentinelle émise après la cible, lecture jusqu'à elle ; mutation (filtre retiré) → le test échoue.
  - `[low]` `[reject]` `composerError` « Écrivez un message avant d'envoyer. » reste affiché jusqu'au prochain envoi ou état `idle` en direct — comportement voulu (retour visible), rien de trompeur ; le corriger ajouterait un minuteur.
  - `[false]` `[reject]` La vérification E2E « le rejeu ne désactive jamais le champ » serait sans pouvoir (rendu groupé par trame) — réfuté : parcours complet avec `isLive` forcé à `true` → FAIL `[True, True, True, False]` ; avec le correctif → PASS `[]`. Seule, sur un journal court, elle ne détecte pas la régression (noté).
  - `[false]` `[reject]` `diagnostic.html` devrait aussi ignorer le rejeu — réfuté : il le fait déjà (`historyUpTo`, `live=false`) ; la perte de `model_load_ended` venait du serveur, corrigée par la tâche 1.
  - `[medium]` `[patch]` Alignement sur l'intention : « ne jamais ignorer un envoi » n'était couvert par aucune vérification — ajouté dans `s_busy_and_stop` : envoi pendant un tour (« Message non envoyé : … ») et message vide (« Écrivez un message… »).

## Design Notes

S'abonner d'abord crée un recouvrement volontaire (un événement peut être dans l'instantané et dans la file) ; le filtre `seq > last_sent` le résout, car `emit` attribue les `seq` sous verrou et notifie dans l'ordre. Le filtre sert aussi de garde si la file reçoit une enveloppe antérieure au `Last-Event-ID` du client.

Côté page, `/api/state` donne déjà le dernier de chaque état ; une enveloppe de `seq` ≤ `liveFrom` est au plus aussi récente que lui : la réappliquer ne peut que faire reculer l'état affiché.

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q` -- expected: tout vert
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` (×3) -- expected: code 0 à chaque passage

## Auto Run Result

Status: done

**Résumé.** Serveur : `_sse_stream` s'abonne avant tout (y compris avant l'événement `server_instance`), rejoue l'instantané, puis écarte de la file ce qui a déjà été rejoué (`seq` ≤ dernier rejoué, repère initial 0 pour ne pas écarter les événements en direct d'un nouveau journal quand le client envoie le `Last-Event-ID` d'une autre instance). Page : `isLive(envelope)` (`seq > store.liveFrom`) protège les états « dernier connu » rejoués (`session_state` et modèle actif, architecture, briques, actions armées — libellés toujours retenus —, scénario, mémoire, jauge, message de réinitialisation) ; `sendMessage` n'ignore plus rien sans message ; `body[data-journal-replayed]` signale la fin du rejeu. `diagnostic.html` inchangé : il traitait déjà le rejeu sans effets de bord, seule la perte serveur pouvait le bloquer sur « Chargement de … ».

**Intégration.** Pendant le travail, l'intégration a reçu un correctif serveur parallèle (story 16, 2974307). À la fusion, une seule implémentation est gardée : celle-ci (abonnement avant `server_instance`, repère initial 0, désabonnement garanti) ; le test de la story 16 (`test_an_event_emitted_during_the_replay_is_never_lost_nor_repeated`) est retiré car couvert par `test_stream_keeps_an_event_emitted_during_the_replay` et `test_stream_drops_the_overlap_between_subscription_and_snapshot`.

**Fichiers.**
- `src/wavestack/web/app.py` — abonnement avant l'instantané, dédoublonnage par `seq`.
- `tests/test_web_app.py` — 4 tests : émission pendant le rejeu, recouvrement abonnement/instantané, `Last-Event-ID` d'une autre instance, désabonnement au départ du client.
- `src/wavestack/web/static/app.js` — `isLive`, refus visible dans `sendMessage`, marqueur de fin de rejeu.
- `tools/e2e/run_e2e.py` — `wait_turn_started` (5 s, puis état du champ, du bouton et de `#composer-reason`) dans `send` et `replay` ; `wait_replayed`, `goto_app`, `reload_app` ; barrière dans `wait_idle`, `s_local_server`, `s_relaunch` ; vérifications ajoutées (champ jamais désactivé au rejeu, envoi pendant un tour, message vide). Aucune vérification retirée.

**Revue.** Revue brève par l'agent lui-même (pas d'outil de sous-agent ; voir le journal de tri) : 3 correctifs appliqués (2 medium, 1 low), 0 différé, 3 rejetés (1 low jugé voulu, 2 réfutés).

**Recommandation de revue complémentaire :** `false` (aucun `high` corrigé ; 2 `medium` corrigés, mais chacun vérifié par un test ou une vérification E2E qui échoue sans le correctif).

**Vérifications.** Sur la base fusionnée (2974307 + ce correctif) : `ruff check` et `ruff format --check` OK ; `pytest -q` : 770 réussis, 5 ignorés ; `node --check app.js` OK ; parcours E2E complet ×3 de suite : 327/327, 327/327, 327/327 (0 échec, 0 anomalie connue). Mutations : sans le filtre de `seq`, le test de recouvrement échoue ; avec l'ancien serveur, le test d'émission pendant le rejeu échoue ; avec `isLive` forcé à `true`, le parcours complet échoue sur « le rejeu ne désactive jamais le champ » (`[True, True, True, False]`).

**Risques résiduels.** La vérification E2E du champ au rejeu ne détecte la régression que sur un journal long (parcours complet), pas avec `--only reload_and_reset` seul. Le message « Écrivez un message avant d'envoyer. » reste affiché jusqu'au prochain envoi ou état `idle`.
