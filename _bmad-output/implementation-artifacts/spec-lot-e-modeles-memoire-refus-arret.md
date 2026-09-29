---
title: 'Lot E : modèles, mémoire estimée, refus, arrêt du chargement'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '8afb1d59ec48ac421cbf3736498d0d58f116ce8d'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/CLAUDE.md'
warnings: ['multiple-goals', 'oversized']
deferred:
  - summary: >-
      L'encadré des briques du scénario indisponibles avec le modèle actif n'est vérifié par aucun test d'interface.
    evidence: |-
      Les faux modèles du parcours E2E savent tous appeler des outils ; à voir sur le PC avec `llama3.2:3b` via Ollama.
    location: >-
      src/wavestack/web/static/app.js:renderScenarioUnavailable
    severity: low
  - summary: >-
      L'estimation du 4B après la nouvelle sonde n'est vérifiée qu'avec une RSS injectée.
    evidence: |-
      Non vérifié : le test injecte 4,05 Gio ; se tranche en sondant le 4B sur le PC cible (refus attendu pour un budget de 4 096 Mo, N5).
    location: >-
      src/wavestack/models/probe.py:probe_file
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Six écarts du test sur PC autour des modèles. (E1) llama-server lancé sans `-c` occupe 5 137 Mo (contexte par défaut immense) alors que WaveStack compte la taille du fichier (1,28 Go). (E2) L'estimation mémoire d'un fichier ignore les tampons de calcul : 4B estimé 3,4 Go, 4,27 Go mesurés après 3 000 tokens ; le 2B, sondé avant la story 17, n'a ni `rss_bytes` ni `kv_bytes_per_token` et n'est jamais resondé. (E3) Le refus par le budget affiche « WaveStack occupe 0,0 Go sans le modèle actif » alors que le processus pèse ≈ 200 Mo. (E4) « Arrêter » pendant un chargement de modèle : l'intention `stop` répond `stopping: false` en `model_load`. (E5) Avec `llama3.2:3b` via Ollama, `native_tools` montre une jauge de 141 tokens et aucun outil, sans explication. (E6) La raison d'un fichier incompatible est le message anglais brut de llama.cpp.

**Approach:** Décision N5 : le budget reste 4 096 Mo ; c'est l'estimation qui devient réaliste. (E1) lire `n_ctx` de llama-server, compter sa mémoire avec le KV de tout son contexte, et le dire au diagnostic (« relancez llama-server avec `-c 4096` ») ; README avec `-c 4096`. (E2) la sonde mesure la RSS après une vraie évaluation au contexte et au lot réels, les entrées d'une ancienne sonde ou incomplètes sont resondées. (E3) la vraie mémoire de WaveStack sans le modèle, en Mo sous 1 Go. (E4) le chargement devient annulable : « Arrêter » visible en `model_load`, le modèle précédent revient. (E5) une brique voulue par le scénario mais indisponible avec le modèle actif est signalée au lancement du scénario, avec sa raison. (E6) raison en français, message brut gardé comme détail technique.

## Boundaries & Constraints

**Always:** code en anglais, textes en français ; `uv`, `ruff`, `pytest` ; tests verts sous Linux et Windows ; tout ce qui demande un vrai GGUF, Ollama ou llama-server se code et se teste avec les doublures existantes (faux serveurs, `tests/fixtures/tiny-llama.gguf`) et se note « à vérifier sur PC » ; jamais deux modèles chargés (AD-8) ; un arrêt pendant un chargement laisse toujours un état cohérent (modèle précédent actif, ou aucun s'il n'y en avait pas), jamais un tour ni un chargement bloqué.

**Never:** changer `[memory] budget_mb` (N5) ; changer le moteur par défaut (N6) ; écrire un analyseur d'appels d'outils pour la famille Llama (hors lot : la carte doit dire pourquoi les briques ne s'appliquent pas) ; relancer ou piloter llama-server ou Ollama depuis WaveStack.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| llama-server à grand contexte | `/props` : `n_ctx` 262 144, fenêtre 4 096 | Mémoire comptée = fichier + KV × `n_ctx` (KV lu dans le GGUF de `model_path`) ; diagnostic : avertissement « lancé avec un contexte de 262 144 tokens … relancez-le avec `-c 4096` » | KV illisible : taille du fichier, avertissement gardé |
| llama-server à `-c 4096` | `n_ctx` 4 096 | Mémoire = fichier + KV × 4 096, aucun avertissement | — |
| Sonde d'un GGUF | Fichier jamais sondé | RSS mesurée après l'évaluation d'un prompt d'un lot complet, au contexte de la fenêtre ; entrée avec `probe_version = 2` et le nombre de tokens évalués ; estimation = max(RSS, fichier) + KV × (fenêtre − tokens évalués) + marge | Échec : raison en français (E6) |
| Entrée ancienne ou incomplète | `probed_models` sans `probe_version = 2`, ou sans `rss_bytes`/`kv_bytes_per_token` | Resondée au diagnostic et avant un changement à chaud | — |
| Refus par le budget | WaveStack pèse 210 Mo sans le modèle | « WaveStack occupe 210 Mo sans le modèle actif » ; Go au-delà de 1 Go ; un modèle servi (hors processus) n'est pas retranché de la RSS | — |
| Arrêter pendant un chargement | `model_load` en cours (fichier, serveur ou cloud) | `stop` répond `stopping: true` ; au premier point d'arrêt, le chargement s'arrête, le modèle précédent est rechargé, `model_load_ended{status: "cancelled"}` avec la raison « Chargement arrêté : {précédent} est de nouveau actif. » ; « Arrêter » visible pendant le chargement | Pas de modèle précédent : aucun modèle actif, raison dite |
| Brique indisponible au lancement | Scénario `native_tools` avec un modèle sans format d'appel d'outils | Avertissement visible au lancement du scénario : briques voulues mais indisponibles, chacune avec sa raison | — |
| Fichier incompatible | llama.cpp : « Failed to load model from file: … » | Raison : « llama-cpp-python {version} ne sait pas charger ce fichier (architecture non prise en charge, fichier incomplet ou abîmé). Choisissez un autre modèle, ou servez-le avec Ollama ou llama-server. » ; message brut en détail technique (cause) | — |

</intent-contract>

## Code Map

- `src/wavestack/models/servers.py` -- `LlamaServerEngine._read_metadata` (l.~271 : `server_context` = `default_generation_settings.n_ctx` ou `n_ctx` de `/props`) ; `_served_by` (l.~594, lit `/health`, `/props` pour `model_path`) ; `ServedModel` ; `served_bytes` (l.~703 : Ollama `/api/ps`, sinon taille du fichier) ; `_open_tokenizer` (l.~526 : raison qui embarque l'exception brute).
- `src/wavestack/models/discovery.py` -- `_server_candidates` (l.~160-200 : `served_bytes`, `resident`).
- `src/wavestack/session/diagnostic.py` -- `_hand_out_server` (l.~485 : ligne « Modèle retenu : … servi par … ») ; `_probe_candidate` (l.~191 : `harness_error` « Modèle incompatible : {reason} », `record_failure`) ; `_discover` (saute les fichiers déjà sondés).
- `src/wavestack/web/static/diagnostic.html` -- ligne de candidat (l.~245 : mémoire `≈ X Go` depuis `served_bytes`).
- `src/wavestack/models/probe.py` -- `ProbeResult`, `kv_bytes_per_token`, `probe_file` (charge `Llama(n_ctx=16, n_batch=16)`, RSS après chargement seulement, « Chargement impossible : {exc} »), `record_success`, `measured(path)` (ne regarde que `rss_bytes`), `probed_entry`.
- `src/wavestack/models/load_registry.py` -- `file_cost` (l.~116 : `max(rss, fichier) + kv × fenêtre + marge`), `check` (l.~130-145 : texte du refus, `without = max(0, rss − held.cost)`), `_go`, `_mo`.
- `src/wavestack/session/app_session.py` -- `switch_model` (l.~1395), `_load` (l.~1422 : libère, sonde, contrôle, `_install`, `_load_failed`), `_load_failed`, `_release`, `_install`, `_cost` (l.~1182), `stop` (l.~4333 : n'agit qu'en `download`/`index_build`/`turn`/`awaiting_human`), `launch_scenario` (l.~4262), `_reconfigure`, `_emit_scenario`, `_availability` (raisons `_CAPABILITIES_FR`), `_effective`.
- `src/wavestack/models/capabilities.py` -- `capabilities_for` : seule la famille `qwen3` a un `tool_call_parser` ; la famille `llama` n'en a pas, d'où `tools`, `mcp`, `skills`, `subagent` indisponibles (cause probable de E5).
- `src/wavestack/trace/catalog.py` -- `ModelLoadEndedPayload` (`status: ok|restored|error`), `ScenarioChangedPayload` (l.~797).
- `src/wavestack/web/static/app.js` -- bouton « Arrêter » (l.~2186 : caché hors `turn`/`awaiting_human`), affichage de `scenario_changed`, fin de chargement.
- `tools/e2e/launch_app.py` -- ralentit `_install` du modèle `fake_b` (`WAVESTACK_E2E_LOAD_DELAY_S`, 2 s) : chargement lent pour le parcours ; `tools/e2e/run_e2e.py` `s_model_switch` (l.~2205), `tools/e2e/fake_local_server.py` (faux llama-server : `props()` avec `n_ctx` 8 192, faux Ollama).
- `README.md` -- l.174 (`llama-server -m … --port 8080 -np 1`), l.185-189, l.202-203 (mémoire d'un modèle servi).
- Tests : `tests/test_model_servers.py` (faux serveurs, `test_vocab_only_failure_keeps_the_previous_model` l.~501 qui attend le message brut), `tests/test_model_switch.py` (l.~567 attend « 1,0 Go sans le modèle actif »), `tests/test_probe.py`, `tests/test_discovery.py`, `tests/test_cli_diagnostic.py`, `tests/test_scenarios.py`.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- six entrées du 2026-09-27 du lot E, à fermer.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/models/servers.py`, `src/wavestack/models/discovery.py` -- (E1) `ServedModel`/candidat llama-server portent `n_ctx` ; mémoire servie = fichier + `kv_bytes_per_token` (métadonnées du GGUF de `model_path`, lu sans poids) × `n_ctx` ; avertissement français quand `n_ctx` dépasse nettement la fenêtre (plus de 1,5 fois). (E6) `_open_tokenizer` : raison française, brut en cause.
- `src/wavestack/session/diagnostic.py`, `src/wavestack/web/static/diagnostic.html` -- (E1) avertissement dans la ligne du serveur retenu et sur la ligne du candidat. (E2) `_discover` resonde les entrées anciennes ou incomplètes. (E6) `harness_error` avec la raison française et le brut en cause.
- `src/wavestack/models/probe.py` -- (E2) sonde au contexte de la fenêtre (passée à l'enfant) et au lot du moteur, évaluation d'un prompt neutre d'un lot complet, RSS de pointe après l'évaluation ; `probe_version = 2`, `rss_eval_tokens` ; `measured()` exige la version 2 et une entrée complète. (E6) raison française pour tout échec de chargement, brut dans un champ `detail`.
- `src/wavestack/models/load_registry.py` -- (E2) `file_cost` : KV pour la fenêtre moins les tokens déjà évalués par la sonde. (E3) `without` = RSS moins le coût du modèle seulement s'il est dans le processus ; texte en Mo sous 1 Go (`_mo`), en Go au-delà.
- `src/wavestack/session/app_session.py` -- (E4) `stop` en `model_load` : événement d'annulation lu par `_load` après la libération, après la sonde et après `_install` ; annulé → libérer ce qui a été chargé, recharger le précédent, `model_load_ended{status: "cancelled", reason_fr}` ; `stop` répond `True`. (E5) au lancement d'un scénario (et à un changement de modèle quand un scénario est actif), liste des briques du scénario indisponibles avec leur raison, dans `scenario_changed` (champ `unavailable: [{brick, label_fr, reason_fr}]`).
- `src/wavestack/trace/catalog.py` -- `model_load_ended.status` accepte `cancelled` ; `ScenarioChangedPayload.unavailable`.
- `src/wavestack/web/static/app.js` -- « Arrêter » visible en `model_load` (et l'issue « Chargement arrêté » affichée) ; avertissement des briques indisponibles dans le volet du scénario.
- `README.md` -- commande llama-server avec `-c 4096`, explication (mémoire réservée pour tout le contexte), mémoire comptée par WaveStack.
- `tools/e2e/run_e2e.py` -- scénario : pendant le chargement lent de `fake_b`, « Arrêter » ; le modèle précédent revient, issue « Chargement arrêté ».
- Tests -- `tests/test_model_servers.py` (E1 : faux `/props` à grand `n_ctx` → mémoire et avertissement ; E6 : raison française), `tests/test_probe.py` (E2 : sonde de `tiny-llama.gguf` avec `probe_version`, `rss_eval_tokens` ; entrée ancienne ou incomplète resondée ; E6), `tests/test_model_switch.py` (E3 : texte en Mo ; modèle servi non retranché ; E4 : arrêt pendant un chargement lent → précédent rétabli, `cancelled`, arrêt sans modèle précédent), `tests/test_scenarios.py` ou `tests/test_bricks.py` (E5 : scénario avec un modèle sans analyseur d'outils → `unavailable` avec la raison).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer les six entrées du lot E, avec ce qui reste à vérifier sur PC.

**Acceptance Criteria:**
- Given llama-server lancé sans `-c`, when le diagnostic le découvre, then il affiche une mémoire proche de la réalité et conseille `-c 4096`.
- Given un chargement lent en cours, when l'utilisateur clique « Arrêter », then le modèle précédent redevient actif et l'issue dit « Chargement arrêté ».
- Given le 4B et un budget de 4 096 Mo, when l'estimation est calculée après la nouvelle sonde, then elle dépasse le budget (≈ 4,3 Go mesurés) et le refus donne la vraie mémoire de WaveStack.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 27 findings (constats des quatre couches, doublons regroupés avec leurs sources) — high 1, medium 11, low 10, false 0, maybe-false 5
- findings:
  - `[high]` `[patch]` KV illisible pour Qwen3.5 : llama-cpp-python montre `head_count_kv` par couche comme texte, `kv_bytes_per_token` rend `None` ; E1 et E2 ne marchent pas pour le modèle qui les motive (blind) — lecteur d'en-tête GGUF en Python pur, tableaux compris, test d'un GGUF hybride synthétique.
  - `[medium]` `[patch]` Fichier GGUF de llama-server ouvert par llama.cpp dans le processus principal, contre AD-16 (blind, edge) — même lecteur Python pur.
  - `[medium]` `[patch]` KV compté deux fois : la RSS de la sonde contient déjà le KV de toute la fenêtre (llama.cpp efface tout le tampon à la création) (blind) — `probe_window` enregistré, KV compté au-delà seulement.
  - `[medium]` `[patch]` Échec passager (mémoire, évaluation, temps) enregistré comme fichier incompatible pour toujours (blind, edge) — seuls les échecs de chargement du fichier sont gardés.
  - `[medium]` `[patch]` Échecs d'avant le lot E gardés avec la raison anglaise (blind) — ignorés et resondés.
  - `[medium]` `[patch]` Délai de la sonde (120 s) trop court pour la nouvelle sonde (blind, edge) — 300 s.
  - `[medium]` `[patch]` Premier lancement : toutes les anciennes entrées resondées l'une après l'autre (intent) — au lancement, seul le modèle enregistré ; les autres au moment du choix.
  - `[medium]` `[patch]` « Arrêter » accepté après le dernier point d'arrêt puis ignoré (blind, edge) — jeton fermé après le dernier point, test.
  - `[medium]` `[patch]` Chargement de lancement arrêté sans modèle : le diagnostic reste prêt (edge, verification-gap) — même traitement que `_switched`.
  - `[medium]` `[patch]` E3 : un modèle local actif peut encore donner « 0 Mo » (coût estimé retranché) (edge) — part de RSS mesurée retranchée.
  - `[medium]` `[patch]` Conseil `-c 4096` faux avec `-np N` (blind, edge) — contexte par emplacement comparé, conseil `-np 1 -c 4096`.
  - `[medium]` `[patch]` `_emit_scenario` dans le `finally` de `_load` peut bloquer en `model_load` (edge) — protégé.
  - `[low]` `[patch]` Repli du KV silencieux, chemin relatif de `model_path` lu localement (blind, edge) — la ligne dit que le cache du contexte manque ; chemin relatif ignoré.
  - `[low]` `[patch]` Changement à chaud vers llama-server : l'avertissement disparaît de la ligne du modèle (edge) — gardé.
  - `[low]` `[patch]` Autre exception de llama.cpp au chargement en processus : raison anglaise (edge, blind) — raison française pour toute exception.
  - `[low]` `[patch]` Rafraîchissement du scénario après un chargement lu comme une relance (blind) — `refresh: true`, pas de ligne de journal.
  - `[low]` `[patch]` Style `warn` écrasé sur la page de diagnostic (blind) — spécificité relevée.
  - `[low]` `[patch]` README : chiffres non mesurés avec la nouvelle sonde présentés comme acquis (blind) — « à vérifier sur PC ».
  - `[low]` `[patch]` E2E : vérification toujours vraie ; avertissement `-c` du diagnostic non vérifié (blind, verification-gap) — vérifications réelles.
  - `[low]` `[patch]` Contexte total plus grand que celui d'un emplacement jamais testé ; arrêt sans modèle et diagnostic ; réinstallation du précédent en échec ; conversion de la RSS de pointe POSIX (verification-gap, blind) — tests ajoutés.
  - `[low]` `[defer]` Encadré des briques indisponibles du scénario non vérifié dans l'interface (verification-gap) — les faux modèles E2E savent tous appeler des outils ; à voir sur PC avec `llama3.2:3b`.
  - `[low]` `[reject]` Correspondance sur le texte anglais « Failed to load model » (blind) — remplacé par la raison française pour toute exception.
  - `[maybe-false]` `[reject]` RSS d'une sonde faite à une autre fenêtre (edge) — le KV est compté par différence de fenêtre (`probe_window`) ; les tampons de calcul dépendent du lot, pas de la fenêtre ; si vrai : low.
  - `[maybe-false]` `[reject]` Surface de E4 : faux fournisseur cloud lent au lieu du faux Ollama lent (intent) — le mécanisme est commun à tous les chargements ; le faux Ollama du parcours sert un modèle incompatible ; à vérifier sur PC avec Ollama.
  - `[maybe-false]` `[reject]` Surface de E5 : encadré du scénario plutôt que la carte (intent) — les cartes disaient déjà la raison ; le constat du PC était qu'on ne les voyait pas au lancement ; si vrai : low.
  - `[maybe-false]` `[defer]` Estimation du 4B au-dessus du budget par construction du test (intent) — si vrai : medium ; se tranche en sondant le 4B sur le PC.
  - `[maybe-false]` `[reject]` Arrêt qui n'agit qu'aux points d'étape (intent) — limite de llama.cpp, dite dans la barre haute.

## Design Notes

- E2 : l'évaluation d'un lot complet touche les tampons de calcul que llama.cpp réserve pour un lot ; la première sonde d'un modèle prend donc quelques dizaines de secondes de plus (≈ 512 tokens à 35 tokens/s sur le PC cible), une seule fois par fichier.
- E4 : llama.cpp ne sait pas interrompre un chargement en cours ; l'arrêt agit au point suivant (après la libération, la sonde ou l'installation), ce qui suffit pour qu'un clic ne soit jamais perdu.
- E5 : diagnostic d'après le code (non vérifié sur PC) : Llama 3.2 est de la famille `llama`, sans format d'appel d'outils connu ; les briques qui en ont besoin sont indisponibles et le prompt ne garde que le message.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert
- `node --check src/wavestack/web/static/app.js` -- expected: pas d'erreur
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only model_switch` -- expected: 0 échec (captures restaurées ensuite par `git restore tools/e2e/screenshots`)

## Auto Run Result

Status: done

**Résumé.** (E1) La mémoire d'un modèle servi par llama-server compte le KV de tout son contexte (`n_ctx` de `/props`, KV lu dans l'en-tête du GGUF par un lecteur Python pur, tableaux par couche compris, sans llama.cpp dans le processus principal) ; le diagnostic avertit quand le contexte par emplacement dépasse 1,5 fois la fenêtre et conseille `-np 1 -c 4096` ; il dit quand le cache ne peut pas être compté ; README à jour. (E2) La sonde charge au contexte de la fenêtre, évalue un lot complet et mesure la RSS de pointe (`probe_version` 2, `probe_window`) ; l'estimation n'ajoute que le KV au-delà de la fenêtre sondée ; les entrées anciennes ou incomplètes sont resondées (au lancement pour le modèle enregistré, les autres au moment du choix) ; un échec passager (mémoire, temps) n'est plus enregistré comme incompatibilité ; délai porté à 300 s. (E3) Le refus retranche la part mesurée du modèle local seulement, en Mo sous 1 Go. (E4) « Arrêter » agit pendant un chargement (points d'étape), le modèle précédent revient (`cancelled`), le diagnostic se rebloque s'il ne reste aucun modèle. (E5) Le lancement d'un scénario signale les briques voulues mais indisponibles avec le modèle actif, avec leur raison. (E6) Raisons françaises pour un fichier ou un tokenizer refusé, message brut en cause technique. N5 respectée (budget inchangé).

**Fichiers.** `src/wavestack/models/gguf_meta.py` (nouveau), `probe.py`, `load_registry.py`, `servers.py`, `discovery.py`, `src/wavestack/session/app_session.py`, `diagnostic.py`, `src/wavestack/trace/catalog.py`, `src/wavestack/web/static/app.js`, `app.css`, `index.html`, `diagnostic.html`, `README.md`, `tools/e2e/run_e2e.py`, `tests/gguf_writer.py` (nouveau), `tests/test_probe.py`, `tests/test_model_switch.py`, `tests/test_model_servers.py`, `tests/test_cli_diagnostic.py`, `tests/test_scenarios.py`, `deferred-work.md` (six entrées fermées).

**Revue.** 20 patchs (1 high, 11 medium, 8 low), 2 différés (encadré E5 non testé dans l'interface ; estimation du 4B, medium si vrai), 5 rejetés. `followup_review_recommended: true` : un high corrigé (lecture du KV des modèles hybrides) ; risque non vérifié : le lecteur GGUF sur le vrai fichier Qwen3.5 (clés `qwen35.*`, tableau `head_count_kv`) et la RSS de la nouvelle sonde sur le PC.

**Vérification.** `ruff check`, `ruff format --check`, `node --check app.js` : OK ; `pytest -q` : 911 réussis, 4 sautés ; E2E `--only model_switch local_server` : 55 réussies, 0 échec (captures restaurées).

**Risques résiduels (à vérifier sur PC).** RSS de la sonde pour le 2B et le 4B (refus du 4B attendu) ; llama-server avec et sans `-c` (≈ 5 Go comptés sans `-c`) ; « Arrêter » pendant un chargement Ollama ou GGUF ; `llama3.2:3b` dans `native_tools` (encadré) ; raison française du blob Ollama refusé ; première sonde plus longue (≈ 15 à 30 s par modèle).
