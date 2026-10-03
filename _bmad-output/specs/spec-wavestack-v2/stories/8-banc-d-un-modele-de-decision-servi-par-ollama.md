---
title: 'V2 (8/8) : banc d''un modèle de décision servi par Ollama (tev1 0.8B)'
type: 'chore'
created: '2026-10-03'
status: 'done'
baseline_commit: 'b80097f8947edb4a25dbead3950a7f5f93972025'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/decision-model-candidates.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/stories/7-banc-des-nouveaux-candidats-de-decision.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** tev1 0.8B (Together AI), servi par Ollama 0.35 sur `/v1/systemone`, est le seul modèle de décision d'Ollama qui peut tenir les 4 096 Mo avec le SLM chargé ; il n'a jamais été mesuré, et le banc ne sait mesurer qu'un modèle chargé dans son propre processus enfant.

**Approach:** Étendre `tools/bench/v2s6_decision_bench.py` (sans le dupliquer) d'un candidat `tev1` servi par Ollama : mêmes critères, mêmes prompts et même relevé que les stories 6 et 7, la RAM comptant le processus enfant ET les processus Ollama qui servent tev1, le hors-ligne vérifié aussi côté serveur, la licence des poids établie ; puis consigner son verdict relevé sur le PC cible dans `decision-model-candidates.md` (CAP-6).

## Boundaries & Constraints

**Always:**
- Banc hors produit : aucun changement sous `src/wavestack`, aucune dépendance ajoutée au projet (`uv run --with` si besoin d'un paquet). Le client `/v1/systemone` passe par `httpx` sur `127.0.0.1` seulement ; il est écrit pour être réutilisé par la story 9 (llama-server, même point d'accès) : URL de base et nom du modèle en paramètres.
- Ollama 0.35.1 est installé (vérifié le 2026-10-03, `ollama --version`). Tirer `tev1:0.8b` une fois (`ollama pull`), consigner son empreinte (`ollama show --modelfile`, digest) et sa licence (`ollama show --license`, fiche ollama.com) ; la mesure elle-même ne télécharge rien.
- Format de requête de `/v1/systemone` : celui documenté par Ollama 0.35 (état + questions typées `choice`, `noul`, `score`, critères ; probabilités par option), relu avant d'écrire le client et cité dans le relevé. Les deux tâches du banc (coût, spécialité) deviennent chacune une question `choice` dont les options sont les étiquettes du banc ; le label retenu est l'option de plus forte probabilité.
- RAM : pic de RSS de l'enfant de mesure + pic des processus Ollama qui portent tev1 (serveur et processus de modèle, trouvés par leur ligne de commande / PID), SLM par défaut chargé dans l'enfant comme aux stories 6 et 7 ; consigner les deux composantes et leur somme ; garde-fou de mémoire du banc conservé (4 096 Mo).
- Hors ligne : garde d'AD-15 dans l'enfant comme avant, ET aucune connexion sortante hors boucle locale des processus Ollama pendant la mesure (relevé des connexions TCP par PID avant, pendant, après), consigné.
- Verdict : au mieux « à surveiller » (modèle causal, règle d'un seul modèle génératif ; décision d'Anaël du 2026-10-03), « écarté » si RAM, latence, hors-ligne ou licence interdite échouent. Critère 1 : Ollama est déjà installé sur le poste sans droits admin ; le dire tel quel, sans en faire un échec.
- Une mesure à la fois, au premier plan ; `ollama stop tev1:0.8b` et vérification par `ollama ps` à la fin ; aucun autre modèle Ollama chargé pendant la mesure (sinon le noter et le décharger seulement s'il appartient à WaveStack).
- Relevé dans `tools/bench/results/2026-10-03-pc-cible-v2s8/` (JSON du banc, `bench_sha256` comme avant) ; ligne de tev1 et candidat ajoutés ENSEMBLE dans `decision-model-candidates.md` (le test compte les lignes du tableau) ; échelon 2 du tableau des échelons mis à jour.

**Never:**
- Pas de tev1 4B ni d'autre modèle de décision d'Ollama (hors budget, déjà consigné).
- Pas d'exposition d'Ollama hors de `127.0.0.1`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Mesure | `measure tev1` avec Ollama lancé, modèle tiré | JSON : RAM (enfant, Ollama, somme), latences, accords, hors-ligne, licence, verdict | N/A |
| Ollama absent | Serveur Ollama non joignable | Message clair (« lancez Ollama »), aucun verdict | sortie non nulle |
| Modèle absent | `tev1:0.8b` non tiré, sans `--download` | Message qui dit la commande, aucun téléchargement implicite | sortie non nulle |
| Réponse inattendue | `/v1/systemone` renvoie une forme inconnue | Ligne en erreur consignée, pas de plantage du banc | consigné |

</frozen-after-approval>

## Code Map

- `tools/bench/v2s6_decision_bench.py` -- `Candidate` (l. ~299), `LOADERS` (l. ~1252), `_measure_child` (l. ~1320), garde-fou de mémoire `start_ram_watchdog` (l. ~1274), `decision_verdict` (l. ~827), `run_decisions`, `summarize_decisions`, prompts (`Prompt`, l. ~116).
- `tests/test_v2s6_decision_bench.py` (ou équivalent) -- tests du banc à étendre (pas de réseau : client `/v1/systemone` testé sur `httpx.MockTransport`).
- `_bmad-output/specs/spec-wavestack-v2/decision-model-candidates.md` -- tableau des candidats, paragraphe « À mesurer (story 8) », échelons.
- `tools/bench/results/2026-10-03-pc-cible-v2s7/` -- forme du relevé.

## Tasks & Acceptance

**Execution:**
- [x] `tools/bench/v2s6_decision_bench.py` -- candidat `tev1`, client `/v1/systemone` réutilisable, RAM des processus Ollama, hors-ligne côté serveur.
- [x] Tests du banc -- client sur faux transport (forme de requête, choix du label, réponse inconnue), somme RAM, verdict plafonné à « à surveiller ».
- [x] Mesure sur le PC cible -- `tools/bench/results/2026-10-03-pc-cible-v2s8/`.
- [x] `decision-model-candidates.md` -- ligne et verdict de tev1, échelon 2.

**Acceptance Criteria:**
- Given Ollama 0.35.1 lancé et `tev1:0.8b` tiré, when on lance la mesure, then le JSON porte RAM (deux composantes), latences, accords, hors-ligne des deux côtés, licence et verdict, et Ollama ne garde pas tev1 chargé après.
- Given `pytest` des tests du banc, then vert.

### Review Findings

Revue de la PR #20 du 2026-10-03, groupe 3 (`tools/bench/` hors `results/`, stories 8 et 9 ensemble ; voir aussi la story 9). Verdicts des trois JSON relus contre les critères : tev1 écarté (RAM 4 171 Mo, latence 2 655 ms), Julia-1 retenu, Laya écarté (latence 1 478 ms), conformes à `decision-model-candidates.md`. Aucun correctif ci-dessous ne change ces verdicts (critères tous à `True` ou `False`, aucune ligne en erreur).

- [x] [Review][Patch] Un critère bloquant non vérifiable compte comme réussi : `decision_verdict` ne déclasse que sur `ok is False`, donc un candidat servi dont la RAM du serveur ou le hors-ligne côté serveur n'a pu être lu (`None`) sort « retenu », contre « retenu s'il passe tous les critères ». Un `None` sur RAM, latence ou hors-ligne plafonne à « à surveiller », avec le critère dans la raison. [`tools/bench/v2s6_decision_bench.py:1568`]
- [x] [Review][Patch] Lignes en erreur partielles sans effet sur le verdict : avec 39 lignes sur 40 en erreur, la latence est jugée sur une décision et le candidat peut sortir « retenu ». Des lignes en erreur (sans qu'elles le soient toutes) plafonnent à « à surveiller », avec leur nombre dans la raison. [`tools/bench/v2s6_decision_bench.py:1321`]
- [x] [Review][Patch] `OllamaOps.preflight` arrête un tev1 déjà chargé sans attendre son déchargement (contrairement à `unload`) : la mesure peut démarrer sur l'ancien processus du modèle, même blob, dont le pic d'ensemble de travail (durée de vie) entre dans la RAM et dont le chargement n'est pas vu. Attendre `/api/ps` comme `unload`, erreur si le modèle reste chargé. [`tools/bench/v2s6_decision_bench.py:2267`]
- [x] [Review][Patch] Critère d'acceptation « Ollama ne garde pas tev1 chargé après » consigné mais sans effet : `main` rend 2 pour un llama-server restant, pas pour `ollama_unload.still_loaded` vrai. [`tools/bench/v2s6_decision_bench.py:3289`]
- [x] [Review][Patch] `_load_systemone` démarre la surveillance avant de construire le client : une exception du constructeur laisse le fil tourner (`_load_llama_server` le garde). Construire le client avant `watch.start()`. [`tools/bench/v2s6_decision_bench.py:2321`]
- [x] [Review][Patch] Test manquant : critère « figé » de tev1 sans version d'Ollama (`versions={"ollama": None}`), seul garde de `bool(versions.get("ollama"))`. [`tests/test_v2s6_decision_bench.py`]

**Rejetées (Ollama et commun) :**
- `low` : `other_models_loaded` n'apparaît ni dans le verdict ni dans l'affichage. La story demande de le noter, c'est fait dans le JSON ; WaveStack ne charge rien dans Ollama.
- `low` : un `ReadTimeout` sur une seule requête fait échouer toute la mesure, et 42 × 120 s dépasse le délai de l'enfant (1 800 s). Comportement documenté (`SystemOneClient`) ; une décision de 120 s est 120 fois au-delà du seuil.
- `maybe-false`, au mieux `low` : après `--download`, des connexions de `/api/pull` comptées dans le relevé « avant ». Non observé ; un faux échec serait bruyant (écarté hors ligne) et la story tire le modèle une fois, à part.
- `low` : blob vide dans le modelfile (le processus du modèle n'est jamais trouvé). Jamais vu sur un modèle tiré ; avec le premier correctif, le verdict devient « à surveiller ».
- `low` : licence de `/api/show` ni texte ni liste, entrée de `/api/tags` non objet. Spéculatif, garde nouvelle.

Revue de la PR #20 du 2026-10-03, groupe 4b (`tests/test_v2s6_decision_bench.py`, stories 8 et 9 ensemble ; voir aussi la story 9), quatre couches (BH, EC, VG, AA). Base : 195 tests verts, aucun appel réseau, aucun binaire local requis (faux transports, faux `run`/`popen`, faux psutil). Mutations du banc qui laissent les 195 tests verts : remplacement des conditions de sortie par `is not None`, valeurs du parent posées avant l'enfant, liste complète périodique coupée, `except psutil.Error` retiré de `_processes`, lecture limitée à la phase `during`, priorité « non vérifiable » sur une connexion sortante, premier franchissement du seuil écrasé.

- [x] [Review][Patch] (décision d'Anaël du 2026-10-03 : option 1) `/api/ps` illisible compté comme « déchargé » — `OllamaOps.loaded` rend `[]` pour un JSON non objet, donc `unload` et `preflight` concluent que tev1 n'est pas chargé ; `test_ollama_ops_show_failed_timeout_and_non_dict_json` l'épingle (`still_loaded is False` alors que la fausse réponse liste tev1 et que la CLI est introuvable). `main` rend 0 sur `still_loaded`/`still_running` à `None`, sans test. Options : (1) `/api/ps` illisible → `still_loaded: None`, et `main` rend 2 sur `None` comme sur `True` (critère d'acceptation « ne garde pas tev1 chargé » non vérifié = échec de sortie) ; (2) garder le comportement, retirer seulement l'assertion qui l'épingle ; (3) garder tel quel (spéculatif, Ollama 0.35 rend toujours un objet). [`tests/test_v2s6_decision_bench.py:1890`]
- [x] [Review][Patch] Raison des lignes en erreur partielles sans leur nombre, contre le correctif 2 de G3 (« avec leur nombre dans la raison ») : la raison reprend le libellé fixe « Décisions sans erreur », et `test_partial_error_rows_cap_an_encoder_under_watch` l'épingle. Mettre le nombre dans le libellé du critère et le vérifier dans la raison. [`tools/bench/v2s6_decision_bench.py:1439`]
- [x] [Review][Patch] Empreinte et version d'Ollama : le runner de `test_run_measure_served_model` rend déjà les `revisions`/`versions` du parent ; poser ces champs avant l'enfant ne fait échouer aucun test. Runner sans ces champs (comme celui de llama-server), puis vérifier le rapport et le critère `pinned`. [`tests/test_v2s6_decision_bench.py:1667`]
- [x] [Review][Patch] Liste complète des processus toutes les `OLLAMA_FULL_SCAN_EVERY` lectures jamais exercée (coupée : tests verts). Prendre une lecture à `_ticks == OLLAMA_FULL_SCAN_EVERY` et vérifier `scan(None)` et `full_scans`. [`tests/test_v2s6_decision_bench.py:1403`]
- [x] [Review][Patch] `_processes`, seule énumération psutil des deux surveillances, remplacé dans tous les tests ; retirer son `except psutil.Error` laisse tout vert. Tester `_processes(None)` et `_processes([disparu, présent])` sur `_fake_psutil` (`NoSuchProcess` sauté). [`tests/test_v2s6_decision_bench.py:1501`]
- [x] [Review][Patch] Sortie 0 d'une mesure servie propre jamais épinglée (Ollama et llama-server) : les quatre appels de `main` sur un candidat servi attendent 2. Ajouter les deux cas propres (`still_loaded`/`still_running` à `False` → 0). [`tests/test_v2s6_decision_bench.py:2862`]
- [x] [Review][Patch] Connexions sortantes « avant » et « après » jamais montrées écarter : les cas d'écart n'utilisent que `during` ; lire `during` seul laisse tout vert. Ajouter les deux phases aux cas paramétrés (Ollama et llama-server). [`tests/test_v2s6_decision_bench.py:1561`]
- [x] [Review][Patch] Une connexion sortante avec un relevé incomplet doit écarter (False avant None) ; inverser la priorité laisse tout vert. Cas `during` + `errors`. [`tests/test_v2s6_decision_bench.py:1561`]
- [x] [Review][Patch] Latence non vérifiable : seul `ok is None` est vérifié, pas le plafond « à surveiller » ni la raison (RAM et hors-ligne le sont). [`tests/test_v2s6_decision_bench.py:1617`]
- [x] [Review][Patch] « Réponse inattendue » (matrice) jamais jouée de bout en bout : aucun enfant ne reçoit une réponse mal formée en cours de mesure. Une réponse sans probabilités à la 5e décision : 40 décisions, la ligne en erreur, `error_rows == 1`. [`tests/test_v2s6_decision_bench.py:1953`]
- [x] [Review][Patch] Plafond « un seul génératif » jamais isolé : la licence de tev1 est déjà KO, donc « à surveiller » tient sans lui. Copie de tev1 à licence Apache-2.0 : toujours « à surveiller », raison = règle d'un seul génératif. [`tests/test_v2s6_decision_bench.py:1542`]
- [x] [Review][Patch] « Le premier franchissement est gardé » non prouvé : le second relevé rend la même valeur ; écraser `ceiling` à chaque franchissement laisse tout vert. Second relevé plus haut, en phase `after`. [`tests/test_v2s6_decision_bench.py:1453`]
- [x] [Review][Patch] Probabilités vides `{}` absentes des cas de `systemone_label` (sans la garde `not probs`, `max()` lèverait). [`tests/test_v2s6_decision_bench.py:1256`]
- [x] [Review][Patch] `ollama_role` : pas de cas `ollama.exe runner --model <blob>` → `runner`. [`tests/test_v2s6_decision_bench.py:1300`]
- [x] [Review][Patch] Licence non vérifiée dans le rapport final : `_PRE` n'a pas de `license_markers`, `test_run_measure_served_model` ne lit pas `report["ollama"]["model"]`. [`tests/test_v2s6_decision_bench.py:1654`]
- [x] [Review][Patch] Correctif 5 de G3 (client construit avant `watch.start()`) sans test de régression : `server_url` hors boucle locale → `ValueError`, aucune surveillance démarrée. [`tests/test_v2s6_decision_bench.py:1917`]
- [x] [Review][Patch] Message « (127.0.0.1 seulement) » alors que `localhost`, `127.0.0.0/8` et `::1` sont acceptés (et testés) : dire « boucle locale seulement ». [`tools/bench/v2s6_decision_bench.py:1872`]
- [x] [Review][Patch] Commentaire faux : « after ten answers » compte le sondage et l'échauffement, soit 7 décisions. [`tests/test_v2s6_decision_bench.py:1961`]

Appliqués le 2026-10-03 (tous les correctifs, choix d'Anaël) : 211 tests verts en ciblé ; les 14 mutations du banc qui passaient (ou auraient passé) sont désormais détectées. `_fail` consigne ses appels et une fixture automatique vérifie qu'aucun n'a été rattrapé par le banc. Verdicts des JSON inchangés (aucun relevé n'a de ligne en erreur).

**Rejetées (groupe 4b, Ollama et commun) :**
- `false` : les cas d'écart paramétrés passeraient par un autre critère. Chaque surcharge ne touche qu'un critère bloquant, les valeurs par défaut les passent tous ; casser la vérification visée rend « à surveiller » et le test échoue.
- `false` : URL pièges (`localhost.evil.com`, `127.0.0.1@evil.com`, `127.0.0.1.nip.io`). `urlparse(...).hostname` puis `ip_address` les refuse.
- `false` : `time.sleep` patché à mi-test laisserait dormir le scénario précédent. `_fake_cli` décharge aussitôt, la première lecture de `/api/ps` sort de la boucle.
- `low` : tests d'affichage qui injectent `ram_total_peak_mb`. `print_measure` reprend le champ calculé par l'enfant, et `test_measure_child_of_a_served_model` vérifie ce calcul.
- `low` : `test_tev1_unreadable_server_side_is_not_verifiable`, statut sans valeur probante (tev1 déjà plafonné). Le plafond sur `None` est prouvé pour Julia-1.
- `low` : sur un premier appel en échec, l'arrêt du fil de surveillance et les champs `ollama_*` ne sont pas vérifiés. L'enfant sort ensuite, et le verdict « non mesuré » ne lit pas ces champs.
- `low` : licence interdite jamais montrée écarter un candidat servi. Le chemin `license_class` est commun et testé.
- `low` : tests du document des candidats dans un seul sens. Test antérieur, seul le compte a changé.
- `low` : préparation dupliquée (`_served_child`, `_llama_child`, filtres des runners). Refactorisation sans défaut nommé.
- `low` : tests qui touchent l'état privé (`_ticks`, `_scan`, `start_timeout_s`). Fragilité sans défaut.
- `low` : nom `OLLAMA_ABORT_MB` qui gouverne aussi llama-server. Renommage de code relu en G3.
- `low` : `_EXE_SHA`/`_IMPL_SHA` en copie des constantes. Voulu : un réépinglage accidentel fait échouer le test.
- `low` : `main(seen["cmd"][2:])` fragile ; `--server-url` hors boucle locale de l'enfant. Le client le refuse déjà (testé).
- `low` : nom de `test_unreadable_peak_is_not_a_discard`. Il reste vrai (pas un écart).
- `low` : règles « Never » sans test de garde. Ce sont des mesures à ne pas faire, pas un comportement du banc.
- `low` : sortie 2 de `main` non vérifiée pour « modèle absent », « binaire absent », « GGUF absent ». `main` rend 2 sur tout `server_error`, vérifié par le cas « Ollama absent ».

## Implementation Notes

- PC partagé de 16 Go : une mesure à la fois, au premier plan ; pas de pytest ni de serveur WaveStack pendant la mesure. Vider le dossier `pytest-of-anael.yahi` du Temp local à la fin.
- `bench_sha256` = empreinte du fichier extrait en CRLF (`core.autocrlf=true`), pas celle du blob git.
- 2026-10-03, agent :
  - **Banc.** Candidat `tev1` (backend `ollama_systemone`, champs `server_url`, `server_model`, `generative`), sans `--with` : httpx et psutil sont déjà des dépendances du projet. Helpers purs : `systemone_label`, `choice_questions` (ancien `decision20_questions`, gardé en alias), `ollama_role`, `remote_endpoints`, `listening_endpoints`, `blob_sha_from_modelfile`, `ollama_model_record`, `server_ram_total`. Classes : `SystemOneClient` (URL de base et modèle en paramètres, boucle locale imposée, réutilisable par la story 9), `OllamaWatch` (RSS et connexions TCP du serveur et du processus du modèle, avant, pendant, après), `OllamaOps` (côté parent : serveur joignable, modèle tiré, `ollama pull` seulement avec `--download`, `ollama stop` puis `/api/ps` en fin de mesure, dans tous les cas). Critère `single_generative` non bloquant : plafond « à surveiller ». Sortie 2 si Ollama est injoignable ou le modèle absent.
  - **Format de `/v1/systemone`.** Relu sur docs.ollama.com le 2026-10-03, cité dans le JSON (`systemone_api`). Ollama 0.35.1 sert le modèle par un `lib/ollama/llama-server.exe --model <blob> --host 127.0.0.1 --offline`, enfant de `ollama.exe serve`.
  - **Garde-fou de mémoire.** Une première version comptait aussi les processus Ollama : elle a arrêté deux mesures vers 4 100 Mo, sans latence ni accord (JSON écrasés). Un diagnostic hors banc a montré que le processus du modèle grossit à chaque requête (≈ 950 Mo après chargement, ≈ 2 130 Mo après 42 requêtes). Le garde-fou est revenu à l'enfant seul, comme à la story 7 (« conservé »), pour que le JSON porte latences et accords comme l'exige le critère d'acceptation ; le dépassement est jugé par le critère RAM. La croissance est consignée (`ollama_rss.runner_series_mb`).
  - **Relevé** (17 h 37, `bench_sha256` `597a511b…`, celui du banc final) : RAM 1 951 + 2 220 = 4 171 Mo ; latence 2 655 / 3 926 ms ; accord 13/20 et 15/20 ; hors ligne des deux côtés ; aucun autre modèle Ollama chargé ; tev1 déchargé à la fin (`ollama ps` vide). Verdict du banc : **écarté** (RAM et latence).
  - **Laissé** : le banc n'est pas commité.
- 2026-10-03, corrections de la revue (sans nouvelle mesure, le verdict tient par la latence ; le JSON garde le `bench_sha256` de la version mesurée) :
  - lignes servies : probabilités et `choice` du serveur gardés (`systemone_row`) ; premier appel sans probabilités = échec du chargement ;
  - lignes en erreur exclues de la latence, « non mesuré » si toutes le sont ;
  - hors-ligne servi : non vérifiable sans processus du modèle ou avec des erreurs de relevé, échec si Ollama écoute hors boucle locale (serveur et processus du modèle) ;
  - `OllamaOps` : `pull_timeout`, `pull_failed`, `timeout` distincts, JSON non objet toléré, échec de `unload` consigné sans masquer le rapport ;
  - `OllamaWatch.report` idempotent, série sans doublon ; seuil d'arrêt à part sur les processus Ollama (`OLLAMA_ABORT_MB` = 6 144 Mo, `ollama_ceiling`, verdict « écarté (RAM) ») ;
  - documents : réserves sur l'accord et la RAM dans `decision-model-candidates.md`, « Suite » du rapport, entrée de nouvel essai dans `deferred-work.md`.

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-03) : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Source | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|---|
| 1 | BH | Accord de coût 13/20 présenté comme « le meilleur mesuré » alors qu'à partir de la 7e ligne tout est « complexe » (les attendus « complexe » sont groupés en fin de liste) pendant que le processus du modèle grossit : état gardé entre requêtes probable ; les lignes ne gardent pas les probabilités | medium | `tev1.json` ; `decision-model-candidates.md` | patch (réserve dans le document ; probabilités et `choice` gardés par ligne) |
| 2 | BH | RAM : dépassement de 75 Mo qui dépend du nombre de requêtes ; la latence (2,6 fois le seuil) suffit à écarter ; cause de la croissance non vérifiée | medium | `ollama_rss.runner_series_mb` | patch (document) |
| 3 | EC, VG | Critère hors ligne « ok » alors que le processus du modèle n'a pas été trouvé, que ses connexions n'ont pas pu être lues, ou qu'Ollama écoute hors boucle locale | medium | `decision_verdict` l. ~1140-1152 | patch (non vérifiable ou échec) |
| 4 | VG | Tests manquants : échec en cours de décisions (champs `ollama_*` gardés), `scan_ollama_processes` réel (psutil simulé), `show_failed`, lignes imprimées du modèle servi | medium | Recherches de VG | patch |
| 5 | BH, EC | `preflight` : délai dépassé ou `pull` en échec annoncés « lancez Ollama » ou « modèle absent » ; JSON non objet → `TypeError`/`AttributeError` ; `unload` qui lève dans `finally` masque le relevé | low | l. ~1762-1801, 2265 ; corrections directes | patch |
| 6 | EC | Lignes en erreur comptées dans la latence ; premier appel 200 sans probabilités accepté au chargement | low | l. ~965, 1128, 1858 | patch |
| 7 | BH | Aucune garde mémoire côté Ollama depuis que le garde-fou ne regarde que l'enfant | low | Croissance de 28 Mo par requête mesurée | patch (seuil d'abandon séparé, au-dessus du budget) |
| 8 | BH | `rapport-test-prealable-modeles-de-decision.md` dit encore la story 8 « à écrire » ; pas d'entrée différée pour tev1 | low | l. 203 du rapport | patch |
| 9 | BH, EC | `report()` non idempotent ; point final dupliqué dans la série | low | l. ~1708 | patch |
| 10 | BH | Empreinte : n'importe quel digest accepté ; libellés « commit » ; texte du critère 1 non vérifié | low | Relevé consigné ; cosmétique | rejeté |
| 11 | BH | Surcoût de la surveillance sur la latence non mesuré ; premier prompt en cache | low | Écart de latence (×2,6) bien au-delà ; à dire dans la réserve | rejeté (repris dans #2) |
| 12 | EC | Probabilités NaN ; déchargement par l'API (`keep_alive: 0`) | low | Spéculatif ; la CLI est présente et `ollama ps` vide vérifié | rejeté |

## Verification

**Commands:**
- `uv run ruff check tools/bench ; uv run ruff format --check tools/bench` -- expected: aucun écart
- `uv run pytest tests -k "bench" -q` -- expected: vert
- `ollama ps` -- expected: tev1 absent à la fin
