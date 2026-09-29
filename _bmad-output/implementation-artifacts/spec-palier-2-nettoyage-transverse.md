---
title: 'Nettoyage transverse du palier 2 : points relevés pendant les fusions'
type: 'bugfix'
created: '2026-09-26'
status: 'done'
baseline_revision: 'a314a62b199902874a8a47e399f8dcc1399d18bb'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['multiple-goals']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Pendant les fusions du palier 2, quatre défauts transverses ont été relevés : (1) sur la page de diagnostic, un clic sur « Choisir » peut être perdu, car la page rejoue tout le journal au chargement et, à chaque contrôle `model` ou `model_load_ended` rejoué, refait `/api/diagnostic` et reconstruit les listes (bouton remplacé sous le pointeur) ; le parcours E2E le contourne en recliquant en boucle ; (2) des textes « relancez WaveStack » de la story 15 ne disent pas le vrai comportement (le modèle d'embedding se relit sans relance), et le scénario E2E `model_switch` lancé seul échoue dès qu'une carte dit « relancez WaveStack » pour une raison légitime (Headroom absent) ; (3) le repli « … est actif. » de la page de diagnostic peut précéder le texte du flux sur un journal long, et le parcours tolère deux textes ; (4) certains scénarios E2E dépendent de l'ordre du parcours complet.

**Approach:** Page de diagnostic : l'API donne le `seq` du journal, la page ouvre le flux après l'avoir lu, traite le rejeu (`seq` ≤ ce repère) sans effets de bord (ni rechargement de `/api/diagnostic`, ni issue de changement), coalesce les rechargements et ne remplace une ligne de liste que si son rendu a changé. Textes de la story 15 reformulés selon le vrai comportement (et la réactivation de la brique RAG relit les fichiers du modèle). Parcours E2E : contournement et tolérance retirés, vérification « relancez » ramenée au texte de la story 11b, dépendances d'ordre corrigées.

## Boundaries & Constraints

**Always:** code et identifiants en anglais, textes en français ; `uv`, `ruff`, `pytest` ; textes vrais (une relance n'est demandée que quand elle est réellement nécessaire) ; le parcours E2E complet et chaque scénario lancé seul (`--only <nom>`) passent ; modifications ciblées (les stories 16 et 20 avancent en parallèle).

**Never:** nouvelle dépendance ou banc de test JS ; toucher aux textes de la story 20 (Headroom) ou aux textes « relancez » des stories 4 à 14 et 19 (ils disent vrai : fichiers lus au lancement) ; relire la configuration à chaud ; changer le format des événements du journal.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Journal long | `/diagnostic` ouvert après des centaines d'événements, clic sur « Choisir » pendant le rejeu | Le clic part du premier coup ; les lignes inchangées gardent leurs boutons | — |
| Changement depuis le diagnostic | « Choisir » un modèle déjà chargé plus tôt dans le journal | Issue exacte « {modèle} est actif. », jamais l'issue rejouée d'un ancien chargement | Flux perdu : repli après 3 s, même texte |
| Modèle d'embedding qui ne se charge pas | Fichier corrompu ; l'utilisateur le supprime, désactive puis réactive la brique RAG | La carte relit les fichiers : « modèle absent » et « Télécharger » | — |
| Section `[rag.embedding]` absente ou invalide | Lancement | Raison qui dit que la configuration n'est lue qu'au lancement | Brique indisponible, pas de plantage |

</intent-contract>

## Code Map

- `src/wavestack/web/static/diagnostic.html` -- script de la page : `loadDiagnostic` (fetch puis `renderCloud` + `renderCandidates`, repli 3 s « `${body.loaded.label} est actif.` »), `renderCandidates` (`innerHTML = ""`), `renderCloud` (`replaceChildren()`), `renderCheck` (contrôle `model` → `loadDiagnostic`), écouteur `model_load_ended` (issue du changement + `loadDiagnostic`), `setBusy` (réactive aussi les boutons bloqués par `disabled_fr`), `EventSource("/api/diagnostic/stream")` ouvert sans attendre.
- `src/wavestack/web/app.py` -- `diagnostic_state` (`GET /api/diagnostic`) : ajouter `seq` (`get_journal().last_seq()`) ; `_sse_stream` rejoue depuis `Last-Event-ID` (0 à l'ouverture).
- `src/wavestack/models/load_registry.py:55` -- `ModelChoice.label` = `entry.model` (cloud), nom ou radical du fichier : même libellé que `model_load_ended.model.label` (`cloud.active_model`, `AppSession._model_payload`) ; c'est le correctif de la story 18 qui rend le repli identique au texte du flux.
- `src/wavestack/config.py:346-366` -- `rag_embedding` : textes « Rétablissez-la, puis relancez » / « Corrigez …, puis relancez » ; `Config` est lu une fois (`AppSession.cfg`), la relance est donc réelle : dire pourquoi.
- `src/wavestack/session/app_session.py` -- `_load_embedder` (~l.1890, « supprimez-le et relancez WaveStack pour le télécharger à nouveau ») ; `_sync_rag` (~l.1826) charge sans relire les fichiers ; `_rag_refresh` relit index et fichiers ; `_rag_static_reason`, `_rag_offers`. `_load_rag` (l.1618, `content/rag.yaml`) garde le même texte que les autres fichiers de contenu (lus au lancement).
- `src/wavestack/compression/headroom_adapter.py`, `app_session._compression_missing` -- story 20, lu au lancement : texte vrai, hors périmètre.
- `tools/e2e/run_e2e.py` -- `s_model_switch` (vérification « relancez WaveStack » sur tout le `body`, tolérance `^(wavestack-fake|Le modèle choisi) est actif\.$`), `s_local_server` (boucle de re-clic sur « Choisir »), `SCENARIOS`, `main` (`--only`, diagnostic toujours joué).
- `tools/e2e/README.md` -- décrit l'ordre des scénarios (« joué avant `relaunch` », « joué après `model_switch` »).
- `tests/test_rag_review.py:222` -- `test_a_failing_factory_leaves_the_brick_unavailable_and_the_registry_free` : modèle pour le nouveau test. `tests/test_cli_diagnostic.py`, `tests/test_cloud.py` : tests de `/api/diagnostic`.
- `_bmad-output/implementation-artifacts/deferred-work.md:296` -- entrée story 17 (repli « Le modèle choisi est actif. ») à fermer (`closed:`).

## Tasks & Acceptance

**Execution:**
- `src/wavestack/web/app.py` -- `seq` (dernier `seq` du journal) dans la réponse de `GET /api/diagnostic` -- repère du rejeu pour la page.
- `src/wavestack/web/static/diagnostic.html` -- ouvrir le flux après la première réponse de `/api/diagnostic` ; événements de `seq` ≤ repère : lignes de contrôle et résultats de test affichés, sans `loadDiagnostic` ni issue de changement ; `loadDiagnostic` coalescé (une requête à la fois, une seule relance) ; listes `#candidates` et `#cloud-models` mises à jour ligne par ligne (une ligne dont le rendu est identique est gardée, avec ses boutons, sa saisie et son focus) ; `setBusy(false)` laisse désactivés les boutons bloqués par `disabled_fr` ; repli de 3 s gardé (même texte que le flux) -- clic jamais perdu, issue exacte.
- `src/wavestack/session/app_session.py` -- `_sync_rag` relit les fichiers et l'index (`_rag_refresh`) avant de charger le modèle d'embedding ; texte d'échec de chargement : supprimer le fichier puis désactiver et réactiver la brique RAG, qui proposera « Télécharger » -- texte vrai sans relance.
- `src/wavestack/config.py` -- textes de `rag_embedding` : relance gardée, avec sa raison (configuration lue au lancement seulement) -- texte vrai.
- `tests/test_rag_review.py` -- test : échec de chargement, fichier supprimé, brique désactivée puis réactivée → raison « modèle absent », `download` proposé ; texte d'échec sans « relancez ».
- `src/wavestack/session/diagnostic.py` -- `cloud_rows` : `last_test`, le dernier résultat de « Tester » de chaque modèle (gardé par `_emit_test`) -- la page ouverte après un test l'affiche sans attendre le rejeu, donc sans reconstruire la ligne pendant le rejeu.
- `tests/test_cli_diagnostic.py`, `tests/test_cloud.py` -- tests : `/api/diagnostic` renvoie `seq` égal au dernier `seq` du journal ; `last_test` après « Tester ».
- `tools/e2e/run_e2e.py` -- retirer la boucle de re-clic (`s_local_server`) et la tolérance (`s_model_switch` exige « wavestack-fake est actif. ») ; ramener la vérification « relancez » au texte de la story 11b (« relancez WaveStack pour l'utiliser ») ; corriger les dépendances d'ordre trouvées en lançant les scénarios seuls.
- `tools/e2e/README.md` -- dire que chaque scénario se lance seul ; retirer les mentions d'ordre obligatoire.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- `closed:` sur l'entrée story 17 du repli.

**Acceptance Criteria:**
- Given un journal long, when j'ouvre `/diagnostic` et clique une fois sur « Choisir » (modèle servi ou cloud), then le changement démarre au premier clic (parcours E2E sans re-clic).
- Given un retour au premier modèle depuis le diagnostic après un journal long, when le changement aboutit, then la ligne affiche exactement « wavestack-fake est actif. ».
- Given l'environnement sans l'extra `compression`, when je lance `run_e2e.py --only model_switch`, then le scénario passe.
- Given chaque scénario de `SCENARIOS`, when je le lance seul avec `--only <nom>`, then il passe.
- Given le parcours complet, when je le lance, then toutes les vérifications passent.

## Spec Change Log

## Review Triage Log

### 2026-09-26 — Review pass
- Revue brève faite par l'agent lui-même (aucun outil de sous-agent dans cette exécution : couches blind-hunter, edge-case, verification-gap et intent-alignment non lancées séparément).
- verdicts: 4 findings — high 0, medium 1, low 1, false 2, maybe-false 0
- findings:
  - `[medium]` `[patch]` `/api/diagnostic` lisait le `seq` du journal après les listes : un événement émis entre les deux lectures (contrôle `model`, `model_load_ended`) passait pour de l'historique, sans rechargement, et la page restait sur une liste périmée. — Corrigé : `seq` lu avant toute lecture (`tip` en tête de `diagnostic_state`).
  - `[low]` `[reject]` Pendant un « Tester », une relecture de `/api/diagnostic` pourrait réafficher l'ancien `last_test`. — Rejeté après correction directe : `testCloud` pose `null` dans `testResults`, qui l'emporte sur `last_test` ; le résultat en direct le remplace.
  - `[false]` `[reject]` Une ligne gardée par `patchList` garde des écouteurs liés à un ancien objet modèle. — Les écouteurs lisent le modèle courant par son id (`currentModel`) ; les boutons de fichier et de serveur ne portent que `{kind, ref}`, visibles dans le HTML comparé.
  - `[false]` `[reject]` `setBusy(false)` réactive un bouton bloqué par `disabled_fr` quand la ligne n'est plus reconstruite. — `data-blocked` est posé sur ces boutons et `setBusy` le respecte.

## Design Notes

Le rejeu est la cause commune des points 1 et 3 : chaque `diagnostic_check{check: model}` et chaque `model_load_ended` rejoués relançaient `/api/diagnostic` et reconstruisaient les deux listes, et un ancien `model_load_ended` du même modèle pouvait être pris pour l'issue du changement en cours. Le repère `seq` sépare l'historique du direct sans changer le flux. La délégation d'événements seule ne suffit pas : si le bouton est remplacé entre `mousedown` et `mouseup`, aucun `click` n'est émis sur le nouveau ; il faut ne pas remplacer ce qui n'a pas changé. Comparaison de lignes par `outerHTML` (les listeners et la valeur saisie ne font pas partie du HTML, donc une ligne inchangée garde sa saisie).

Point 2 : seul le texte d'échec de chargement du modèle d'embedding pouvait devenir « sans relance » ; les autres « relancez » disent vrai (configuration et fichiers de contenu lus au lancement ; Headroom vérifié au lancement, story 20). L'échec de `model_switch` seul venait de la vérification trop large : sans l'extra `compression`, la carte Compression dit à raison « relancez WaveStack ».

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` -- expected: tout vert
- `node --check src/wavestack/web/static/app.js` et le script extrait de `diagnostic.html` -- expected: OK
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 en échec
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only <nom>` pour chaque scénario -- expected: 0 en échec

## Auto Run Result

Status: done

**Résumé.** Page de diagnostic : `/api/diagnostic` donne le `seq` du journal (lu avant tout le reste) et le dernier résultat de « Tester » par modèle cloud (`last_test`) ; la page ouvre son flux après cette lecture et traite le rejeu comme de l'historique (lignes de contrôle affichées, sans rechargement des listes ni issue de changement), coalesce ses rechargements et ne remplace une ligne des listes que si son rendu a changé : un clic sur « Choisir » n'est plus perdu, l'issue exacte « {modèle} est actif. » s'affiche. Story 15 : l'échec de chargement du modèle d'embedding dit la voie sans relance (supprimer le fichier, désactiver puis réactiver la brique RAG, qui relit ses fichiers) ; `[rag.embedding]` absente ou invalide garde la relance, avec sa raison (configuration lue au lancement). Parcours E2E : boucle de re-clic et tolérance retirées, vérification « relancez » ramenée au texte de la story 11b, README sans ordre obligatoire.

**Hypothèses tranchées.** (1) Les « relancez WaveStack » des fichiers de contenu (stories 4 à 19, dont `content/rag.yaml`) et de Headroom (story 20) disent vrai : ces fichiers et la présence de Headroom ne sont lus qu'au lancement ; ils sont gardés. (2) L'échec de `model_switch` seul venait de la carte Compression sans l'extra `compression` (« …puis relancez WaveStack », légitime), pas d'un texte de la story 15. (3) Aucune dépendance d'ordre restante : les 25 scénarios passent seuls.

**Fichiers.**
- `src/wavestack/web/static/diagnostic.html` -- rejeu sans effets, `patchList`, rechargements coalescés, `data-blocked`, `last_test`.
- `src/wavestack/web/app.py` -- `seq` dans `/api/diagnostic`.
- `src/wavestack/session/diagnostic.py` -- `last_test` par modèle cloud.
- `src/wavestack/session/app_session.py` -- `_sync_rag` relit les fichiers avant de charger ; texte d'échec du modèle d'embedding.
- `src/wavestack/config.py` -- textes de `[rag.embedding]`.
- `tests/test_cli_diagnostic.py`, `tests/test_cloud.py`, `tests/test_rag_review.py` -- `seq`, `last_test`, réactivation de la brique RAG.
- `tools/e2e/run_e2e.py`, `tools/e2e/README.md` -- contournement et tolérance retirés, scénarios indépendants.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- entrée story 17 fermée.

**Revue.** 1 patch (medium : `seq` lu avant les listes), 3 rejetés (voir le journal de triage), 0 différé. Revue brève sans sous-agents (outil absent dans cette exécution). `followup_review_recommended: false` (un seul medium corrigé).

**Vérification.** `ruff check` et `ruff format --check` : OK ; `pytest -q` : 705 réussis, 4 ignorés ; `node --check` app.js et script de diagnostic.html : OK ; E2E complet : 289 réussies, 0 en échec ; chaque scénario seul (`--only <nom>`, 25 scénarios) : 0 en échec ; `--only model_switch` sans l'extra `compression` : 27/27.

**Risques résiduels.** Aucun banc de test JS : `patchList` et le traitement du rejeu ne sont vérifiés que par le parcours E2E. Une ligne dont le contenu change vraiment au moment du clic (résultat de test en direct) est encore reconstruite.
