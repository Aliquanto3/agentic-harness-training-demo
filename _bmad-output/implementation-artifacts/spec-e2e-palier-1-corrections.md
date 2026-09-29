---
title: 'Corrections du test de bout en bout du palier 1 (anomalies A1 à A4)'
type: 'bugfix'
created: '2026-09-26'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
baseline_commit: '62f297a7c8e483a62c0f7d5e82eb8e0de99ba511'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/test-e2e-palier-1-cloud.md'
  - '{project-root}/tools/e2e/README.md'
warnings: []
deferred:
  - summary: >-
      Schéma très chargé à 1 366 px : la zone locale se resserre et déborde de 31 px sur la frontière.
    evidence: |-
      Outils réseau + Hooks (H5) + MCP à 1 366 × 768 : zone locale 546 px pour 577 px de contenu,
      noms de nœuds locaux abrégés (« H. », « C. »). Avant la correction A2, c'était la zone Réseau
      qui était coupée. Aucune vérification E2E n'échoue ; la zone Réseau reste entière.
    location: >-
      src/wavestack/web/static/app.css (.arch-zone-local, .arch-zone-network)
    severity: low
---

<intent-contract>

## Intent

**Problem:** Le test de bout en bout du palier 1 (`test-e2e-palier-1-cloud.md`) a relevé quatre anomalies. A1 : un onglet resté ouvert pendant une relance de WaveStack reprend le flux avec le `seq` de l'ancien processus et se bloque sur « Préparation du contexte… ». A2 : la zone Réseau du schéma est rognée de 60 px à 1 600 et 1 366 px. A3 : l'en-tête de Contexte LLM affiche « (somme des segments) (total renvoyé par le fournisseur) » et « Tour t1 ». A4 : « WaveStack réinitialisé : LLM nu. » comprime la barre haute.

**Approach:** A1 : le journal reçoit un identifiant d'instance tiré à chaque lancement du processus. `/api/state` le renvoie et chaque connexion au flux SSE commence par un événement `server_instance` qui le porte. Si le front voit un identifiant différent de celui qu'il connaît, il recharge la page, ce qui rejoue tout le journal du nouveau processus. A2 : la zone Réseau prend la largeur de son contenu, la zone locale cède la place libre. A3 : une seule précision de source et le nom de tour partagé (`turnName`). A4 : le message sort du flux de la barre haute (pastille superposée sous la barre, à droite) et s'efface seul après quelques secondes.

## Boundaries & Constraints

**Always:**
- L'enveloppe AD-2 ne change pas : l'identifiant d'instance voyage hors enveloppe (champ de `/api/state` et événement SSE sans `id:`).
- Les autres consommateurs du flux restent valides : la page de diagnostic (`EventSource` avec écouteurs nommés) ignore `server_instance` ; le lecteur du harnais E2E ne retient que les enveloppes.
- Modifications ciblées dans `app.js` et `app.css` (la story 14 touche les mêmes fichiers en parallèle).
- Textes d'interface en français, code en anglais ; `uv`, `ruff`, `pytest`.
- Les vérifications `KNOWN [A1]` à `[A4]` du harnais deviennent des vérifications normales.

**Never:**
- Remettre `seq` à zéro dans un processus, ou persister le journal (AD-2 : journal en mémoire).
- Une resynchronisation partielle du store en place : le rechargement est la resynchronisation complète.
- Réserver en permanence de la place au message dans la barre haute, ou tronquer le message.
- Toucher au comportement du futur `top-status` de la story 17 au-delà du style : seul le message de réinitialisation s'efface seul.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Même processus, reconnexion | Coupure réseau passagère, même instance | `server_instance` identique ; reprise au `Last-Event-ID`, sans rechargement | Aucune |
| Relance du processus | Onglet ouvert, nouveau processus (nouvelle instance, journal repart de 1) | Dès la reconnexion (≤ 1 s après le retour du serveur), la page se recharge ; un message envoyé ensuite affiche sa réponse | Aucune |
| Relance entre `/api/state` et le premier flux | `instance_id` de l'état ≠ celui du flux | Rechargement | Aucune |
| `/api/state` en échec au démarrage | Pas d'`instance_id` connu | Le premier `server_instance` du flux devient la référence | Aucune |
| En-tête cloud | `usage_source: "api"` | « Tour N · X tokens envoyés (total renvoyé par le fournisseur) · fenêtre … » | Aucune |
| En-tête local / estimé | `usage_source` autre | « Tour N · [≈ ]X tokens envoyés (somme des segments) · fenêtre … » | Aucune |
| Réinitialisation | Clic « ⟲ Réinitialiser » | Pastille « WaveStack réinitialisé : LLM nu. » sous la barre, voisins inchangés ; disparaît après 6 s ou au tour suivant | Aucune |

</intent-contract>

## Code Map

- `src/wavestack/trace/journal.py` -- `Journal.__init__` : ajouter `instance_id` (uuid4 hex), identité du journal de ce processus.
- `src/wavestack/web/app.py` -- `api_state` (~l. 187) : ajouter `instance_id` ; `_sse_stream._generate` (~l. 468) : émettre d'abord `event: server_instance` + `data: {"instance_id": …}`, sans `id:`.
- `src/wavestack/web/static/app.js` -- `streamEvents`/`parseSseEvent` (l. 102-145) : lire le nom d'événement, traiter `server_instance` ; `applyEnvelope` case `harness_reset` (~l. 187) : minuterie d'effacement ; `boot` (~l. 3656) : retenir `instance_id` ; `renderContext` (l. 1492-1499) : en-tête ; `turnName` (l. 1537) à réutiliser.
- `src/wavestack/web/static/app.css` -- `.arch-zone-network` (l. 2050) ; `.top-bar` (l. 80) ; `.top-status` (~l. 2591).
- `tools/e2e/run_e2e.py` -- `Events._run` (l. 47) : ignorer les événements non-enveloppes ; vérifications `known=` l. 295 (A3), 796 (A2), 883 (A4), 954 (A1) ; `s_network_tools` (l. 476) ; sélecteur du raisonnement l. 301 (`bubble-reasoning` renommé `reasoning-block` par la story 13).
- `tests/test_web_app.py` -- `_FakeRequest`, `test_stream_resumes_from_last_event_id_without_duplicates` (l. 123-150) : modèle pour les tests du flux.
- `_bmad-output/implementation-artifacts/test-e2e-palier-1-cloud.md`, `tools/e2e/README.md` -- rapport et documentation à mettre à jour.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/trace/journal.py` -- attribut `instance_id` tiré au constructeur -- identité de lancement.
- `src/wavestack/web/app.py` -- `instance_id` dans `/api/state` ; événement `server_instance` en tête de chaque flux SSE -- détection immédiate à la reconnexion.
- `src/wavestack/web/static/app.js` -- `store.serverInstance` ; `streamEvents` compare et recharge (`location.reload()`) puis cesse de lire ; `boot` initialise depuis `/api/state` ; en-tête de `renderContext` ; effacement du message de réinitialisation après 6 s -- A1, A3, A4.
- `src/wavestack/web/static/app.css` -- `.arch-zone-network { flex: 0 0 auto; min-width: 230px }` ; `.top-bar { position: relative }` ; `.top-status` en pastille absolue sous la barre, `pointer-events: none`, sans boîte quand vide -- A2, A4.
- `tests/test_web_app.py` -- tests : `/api/state` renvoie `instance_id` ; le flux commence par `server_instance` avec le même identifiant, sans `id:`, avant les enveloppes rejouées.
- `tools/e2e/run_e2e.py` -- lecteur d'enveloppes robuste ; retirer `known=` des quatre vérifications ; A1 : prouver le rechargement (marqueur `window` absent après relance) ; A2 : même contrôle de largeur dans `s_network_tools` ; A3 : vérifier aussi « Tour N » et la précision fournisseur ; sélecteur `details.reasoning-block`.
- `tools/e2e/README.md`, `_bmad-output/implementation-artifacts/test-e2e-palier-1-cloud.md` -- anomalies marquées corrigées, résultat de la nouvelle séance.

**Acceptance Criteria:**
- Given un onglet ouvert et WaveStack relancé, when l'animateur envoie un message depuis cet onglet, then la page s'est rechargée d'elle-même et la réponse s'affiche dans la Vue humain.
- Given le scénario « Où vont mes données ? » ou « Outils réseau » à 1 600 × 1 000 et 1 366 × 768, when le schéma s'affiche, then `.pane-body-schema` ne défile pas horizontalement (écart ≤ 2 px) et le nœud data.gouv.fr est entier.
- Given un tour sur le modèle cloud avec `usage`, when Contexte LLM s'affiche, then l'en-tête commence par « Tour N » et ne porte que « (total renvoyé par le fournisseur) ».
- Given la barre haute à 1 600 px, when on clique « Réinitialiser », then « Réinitialiser », « Volets » et la jauge gardent leurs dimensions et le message est lisible dans `#top-status`.
- Given la séance E2E complète, when elle se termine, then 0 échec et 0 anomalie connue.

## Spec Change Log

## Review Triage Log

### 2026-09-26 — Review pass

Revue faite par l'agent lui-même (pas d'outil de sous-agent dans cette exécution, consigne de
l'appelant) : lectures adversariale, cas limites, trous de vérification et alignement sur
l'intention, appliquées au diff `62f297a..` (code, tests, harnais).

- verdicts: 7 findings — high 0, medium 0, low 4, false 3, maybe-false 0
- findings:
  - `[low]` `[defer]` Zone locale resserrée (31 px de débordement) quand Hooks, MCP et outils réseau sont actifs à 1 366 px — mesuré ; la zone Réseau, but de A2, reste entière ; différé (frontmatter `deferred`).
  - `[low]` `[reject]` Après un rechargement, un `harness_reset` rejoué sans tour ultérieur réaffiche le message 6 s — comportement antérieur pire (message affiché indéfiniment) ; corriger demanderait de distinguer rejeu et direct.
  - `[low]` `[reject]` La pastille de réinitialisation recouvre 6 s les boutons d'en-tête du volet de droite — `pointer-events: none`, les clics passent ; transitoire ; la barre n'a pas la place d'un message en flux (~40 px libres).
  - `[low]` `[reject]` Le rechargement A1 perd un brouillon du champ de saisie ou du tiroir du prompt système — la reconnexion suit le retour du serveur à 1 s près ; le serveur a redémarré de toute façon ; garder le brouillon ajouterait un stockage.
  - `[false]` Boucle de rechargement si `/api/state` et le flux divergent — les deux lisent le même `Journal` du processus ; un nouveau rechargement n'a lieu que si l'instance change réellement (vérifié : « un seul rechargement »).
  - `[false]` Les autres consommateurs du flux cassent sur `server_instance` — `diagnostic.html` n'écoute que des événements nommés (`EventSource`) ; le lecteur E2E filtre sur `seq` ; `models/openai_chat.py` lit le flux du fournisseur, pas celui-ci.
  - `[false]` La reconnexion dans le même processus n'est pas couverte — le chemin « même instance, pas de rechargement » est celui de chaque chargement de page (état et flux de la même instance), vérifié par `stream_resync` ; une coupure réelle du flux en boucle locale ne se provoque pas depuis Playwright (`set_offline` ne coupe pas la boucle locale).

## Design Notes

Hypothèses (exécution sans humain) :
- Rechargement plutôt que remise à zéro du store en place : le store a beaucoup d'état dérivé (tours, journal, comparaisons) ; le rechargement rejoue le journal du nouveau processus (AD-1) et garde les préférences du navigateur (volets, raisonnement). Un brouillon dans le champ de saisie est perdu : la reconnexion a lieu dans la seconde qui suit le retour du serveur, avant que l'animateur ne tape.
- Événement SSE hors enveloppe plutôt que champ d'enveloppe : l'enveloppe AD-2 est figée, et un champ d'enveloppe ne serait vu qu'au prochain événement (rien n'est rejoué quand le `Last-Event-ID` périmé dépasse la pointe du nouveau journal).
- Message de réinitialisation : la barre haute n'a que ~40 px libres à 1 600 px ; la pastille superposée n'intercepte aucun clic et s'efface après 6 s.

```text
id absent        event: server_instance
                 data: {"instance_id": "3f2c…"}

id: 1            event: session_state
                 data: {…enveloppe…}
```

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q` -- expected: tout vert.
- `node --check src/wavestack/web/static/app.js` -- expected: syntaxe valide.
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 échec, 0 `KNOWN`.

## Auto Run Result

Status: done

**Résumé.** A1 : identifiant d'instance du journal (`Journal.instance_id`), renvoyé par `/api/state` et annoncé en tête de chaque flux SSE (`event: server_instance`, hors enveloppe, sans `id:`) ; le front recharge la page quand il change. A2 : zone Réseau à la largeur de son contenu. A3 : une seule précision de source et « Tour N » dans l'en-tête de Contexte LLM. A4 : message de réinitialisation en pastille hors du flux de la barre haute, effacé après 6 s.

**Fichiers modifiés.**
- `src/wavestack/trace/journal.py` : `instance_id` tiré au lancement.
- `src/wavestack/web/app.py` : `instance_id` dans `/api/state` ; événement `server_instance` en tête de flux.
- `src/wavestack/web/static/app.js` : `sameServerInstance`, `parseSseEvent` lit le nom d'événement, en-tête de `renderContext`, minuterie du message de réinitialisation.
- `src/wavestack/web/static/app.css` : `.arch-zone-network`, `.top-bar`, `.top-status`.
- `tests/test_web_app.py` : flux qui commence par l'instance, `/api/state` qui la renvoie.
- `tools/e2e/fake_openai.py`, `tests/test_e2e_fake_openai.py`, `tools/e2e/README.md` : déclencheur `[sans-usage]`.
- `tools/e2e/run_e2e.py` : `KNOWN` retirés, vérifications A1 à A4 renforcées, scénario `stream_resync`, `schema_fits`, lecteur d'enveloppes, sélecteur `reasoning-block` (story 13).
- `_bmad-output/implementation-artifacts/test-e2e-palier-1-cloud.md` : anomalies marquées corrigées ; `tools/e2e/screenshots/` régénérées.

**Revue.** 7 constats : 0 correctif appliqué, 1 différé (zone locale resserrée à 1 366 px dans le cas le plus chargé), 3 rejetés `low` (message rejoué 6 s après rechargement, pastille qui recouvre 6 s des boutons sans bloquer les clics, brouillon perdu au rechargement), 3 `false`. Recommandation de revue complémentaire : `false` (aucun correctif `high` ou `medium`).

**Vérification.** `ruff check` et `ruff format --check` : OK. `pytest -q` : 422 réussis, 3 ignorés. `node --check app.js` : OK. E2E complet : 152 vérifications réussies, 0 échec, 0 anomalie connue (les 4 `harness_error` affichés sont ceux attendus du scénario des refus du fournisseur).

**Hypothèses.** Rechargement complet plutôt que resynchronisation en place du store ; identifiant hors enveloppe pour garder l'enveloppe AD-2 figée ; revue faite sans sous-agent, sur consigne de l'appelant. La branche du worktree partait de `81dba76` : avance rapide sur `claude/dreamy-cerf-gdjtee` (`62f297a`) avant tout changement.

**Risques résiduels.** Une vraie coupure du flux dans le même processus n'est pas provoquée par l'E2E (le chemin de comparaison est le même que celui de chaque chargement). Story 14 en parallèle sur `app.js`/`app.css` : changements ciblés, conflits possibles mais locaux (`streamEvents`, `harness_reset`, `renderContext`, `.top-status`, `.arch-zone-network`).
