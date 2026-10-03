---
title: 'V2 (9/9) : banc des modèles de décision servis par llama.cpp (Julia-1, Laya)'
type: 'chore'
created: '2026-10-03'
status: 'done'
baseline_commit: '598e44fcdc90f7a604fb3faac99137324d7f2584'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/decision-model-candidates.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/stories/8-banc-d-un-modele-de-decision-servi-par-ollama.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Depuis la PR #29818 (fusionnée le 2026-10-02), `llama-server` sert sur `/v1/systemone` des modèles de décision encodeurs, dont Julia-1 (144M, sur mmBERT-small, plus de 50 langues) : le premier candidat petit, non génératif et multilingue, alors que les prompts du banc sont en français. Ni lui ni Laya (421M, anglais) n'ont été mesurés.

**Approach:** Étendre le banc (`tools/bench/v2s6_decision_bench.py`) de deux candidats servis par un `llama-server` portable, en réutilisant le client `/v1/systemone` et la surveillance de processus serveur de la story 8 (généralisés au lieu d'être copiés) : mêmes critères, mêmes prompts, RAM enfant + `llama-server`, hors-ligne des deux côtés, licence établie ; consigner les verdicts relevés sur le PC cible dans `decision-model-candidates.md` (CAP-6).

## Boundaries & Constraints

**Always:**
- Banc hors produit : aucun changement sous `src/wavestack`, aucune dépendance ajoutée au projet.
- Binaire : `llama-b11378-bin-win-cpu-x64.zip` de la release `b11378` de `ggml-org/llama.cpp` (publiée le 2026-10-03, après la fusion de la PR #29818, commit `a4cb4c61fd9d9c2066c7c1747821d3d65b8943bd`), téléchargé une fois sur GitHub et décompressé hors du dépôt (`%LOCALAPPDATA%\WaveStack\bench\llama-b11378\`), sans droits administrateur ; sha256 de l'archive et version (`llama-server --version`) consignés. Le banc prend le chemin de `llama-server.exe` en option ou variable d'environnement, et refuse de télécharger le binaire lui-même.
- Modèles : `ggml-org/Julia-1-GGUF` fichier `Julia-1-Q8_0.gguf` (168 Mo) et `ggml-org/Laya-GGUF` fichier `Laya-Q8_0.gguf` (449 Mo), téléchargés une fois (option `--download`, révision du dépôt épinglée et consignée), puis servis par CHEMIN LOCAL (`-m`), jamais par `-hf` pendant la mesure. Licence : Apache-2.0 déclarée par les cartes GGUF (relu le 2026-10-03) ; relire aussi la carte des modèles sources (`SupersonicLabs/Julia-1`, `convaiinnovations/laya`) et consigner.
- Serveur lancé par le banc sur `127.0.0.1` et un port libre, arrêté à la fin quoi qu'il arrive (aucun `llama-server` restant) ; un seul modèle servi à la fois ; mesures l'une après l'autre.
- Format de requête : celui du billet ggml-org et de la PR #29818 (`state`, `questions` typées `choice`, critères ; probabilités par option), relu dans le code ou la doc de la release et cité dans le relevé ; mêmes tâches et même règle de label que la story 8.
- RAM : pic de RSS de l'enfant de mesure (SLM par défaut chargé) + pic de `llama-server`, les deux composantes et leur somme ; garde-fou de mémoire de l'enfant conservé comme en story 8.
- Hors ligne : garde d'AD-15 dans l'enfant, et aucune connexion sortante hors boucle locale de `llama-server` pendant la mesure (relevé par PID), consigné.
- Verdicts selon les critères habituels. Julia-1 et Laya sont des encodeurs (non génératifs) : la règle d'un seul modèle génératif ne les plafonne pas. Critère 1 (« sans exécutable à installer ») : un binaire portable décompressé n'est pas installé ; le consigner comme constat pour décision d'Anaël, sans en faire un échec.
- Relevé dans `tools/bench/results/2026-10-03-pc-cible-v2s9/` ; lignes de Julia-1 et Laya ajoutées avec leurs candidats (le test compte les lignes) ; Kev-4B consigné « écarté sans mesure » (`Kev-4B-Q4_K_M.gguf` = 3 034 Mo, plus le SLM ≈ 1 950 Mo > 4 096 Mo), lev 4B et OpenJev 27B aussi (taille ; OpenJev CC BY-NC 4.0, NFR-10) ; échelon 2 mis à jour ; section « Langue » complétée (Julia-1 multilingue).

**Never:**
- Pas de Kev-4B, lev, OpenJev mesurés ; pas de `llama-server` exposé hors de `127.0.0.1` ; pas de binaire ni de GGUF dans le dépôt.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Mesure | `measure julia1` (puis `laya`) avec binaire et GGUF présents | JSON : RAM (enfant, serveur, somme), latences, accords, hors-ligne, licence, verdict ; serveur arrêté | N/A |
| Binaire absent | Chemin de `llama-server.exe` absent ou faux | Message qui dit où le décompresser, aucun verdict | sortie non nulle |
| GGUF absent | Modèle non téléchargé, sans `--download` | Message qui dit la commande | sortie non nulle |
| Serveur qui ne démarre pas | `llama-server` sort en erreur | Sortie du serveur consignée, aucun verdict, aucun processus restant | sortie non nulle |

</frozen-after-approval>

## Code Map

- `tools/bench/v2s6_decision_bench.py` -- `SystemOneClient`, `OllamaWatch`, `OllamaOps`, candidat `tev1` (story 8) : généraliser la surveillance et les opérations à un serveur `llama-server` lancé par le banc ; `Candidate` (`server_url`, `server_model`, `generative`), `decision_verdict`, `choice_questions`.
- `tests/test_v2s6_decision_bench.py` -- tests de la story 8 comme modèle (faux transport, faux balayage de processus).
- `_bmad-output/specs/spec-wavestack-v2/decision-model-candidates.md` -- tableau, échelons, « Langue ».
- `tools/bench/results/2026-10-03-pc-cible-v2s8/` -- forme du relevé.

## Tasks & Acceptance

**Execution:**
- [x] Préparation (hors dépôt) -- télécharger et décompresser `llama-b11378-bin-win-cpu-x64.zip`, sha256 et version ; télécharger les deux GGUF.
- [x] `tools/bench/v2s6_decision_bench.py` -- candidats `julia1` et `laya`, lancement et arrêt de `llama-server`, surveillance généralisée.
- [x] Tests du banc -- lancement/arrêt simulés, binaire absent, serveur en échec, somme RAM, verdict non plafonné pour un encodeur.
- [x] Mesures sur le PC cible -- `tools/bench/results/2026-10-03-pc-cible-v2s9/`.
- [x] `decision-model-candidates.md` -- lignes, verdicts, écartés sans mesure, échelon 2, Langue.

**Acceptance Criteria:**
- Given le binaire et les GGUF présents, when on mesure Julia-1 puis Laya, then chaque JSON porte RAM (deux composantes), latences, accords, hors-ligne des deux côtés, licence et verdict, et aucun `llama-server` ne reste lancé.
- Given `pytest` des tests du banc, then vert.

## Implementation Notes

- PC partagé de 16 Go : une mesure à la fois, au premier plan ; pas de pytest ni de serveur WaveStack pendant une mesure ; aucun modèle Ollama chargé. Vider le dossier `pytest-of-anael.yahi` du Temp local à la fin.
- Anaël a validé le 2026-10-03 la story et le téléchargement du binaire de llama.cpp (points d'arrêt levés).
- `bench_sha256` = empreinte du fichier extrait en CRLF. La story 8 a mesuré avec la version du banc de son commit ; modifier le banc ici est normal, chaque relevé porte l'empreinte de sa version.
- 2026-10-03, agent :
  - **Préparation.** `llama-b11378-bin-win-cpu-x64.zip` téléchargé par `gh release download` et décompressé dans `%LOCALAPPDATA%\WaveStack\bench\llama-b11378\` ; sha256 `11bcb3ae…` (égal au digest GitHub) ; `llama-server --version` : `0.5.0-dev (build 11378, commit edd6e2bbd)` ; le tag `b11378` (`edd6e2bb…`) a 17 commits d'avance sur `a4cb4c61…` (API GitHub). GGUF téléchargés une fois au commit épinglé (Julia-1 `16fee179…`, Laya `da4b4753…`), sha256 égaux à ceux du dépôt. Format relu dans le README du serveur, `server-decision.cpp` et `test_systemone.py` au tag ; cartes GGUF et sources relues (Apache-2.0).
  - **Banc.** Candidats `julia1` et `laya` (backend `llama_systemone`, champs `server`, `gguf_sha256`). Généralisé, pas copié : `ServerWatch` (préfixe des champs, rôles additionnés, rôle du modèle), dont `OllamaWatch` et `LlamaServerWatch` ne sont que des réglages ; `_process_record` partagé par les deux balayages ; `_served_decisions` partagé par les deux chargeurs ; `decision_verdict` et `server_ram_total` lisent les champs par préfixe. `LlamaServerOps` (parent) : binaire présent (jamais téléchargé), version, sha256 du binaire, de `llama-server-impl.dll` et de l'archive voisine ; démarrage sur `127.0.0.1` et un port libre, GGUF par `-m`, `--offline --no-webui -np 1`, environnement sans proxy ni `LLAMA_ARG_*`, connexions relevées par PID pendant le démarrage, attente de `/health` ; arrêt dans un `finally`, puis recherche des llama-server restants de ce binaire. L'enfant reçoit `--server-url` et `--server-pid`. Sortie 2 si le binaire manque, si le GGUF manque sans `--download`, ou si le serveur ne démarre pas (extrait de sa sortie imprimé et consigné).
  - **Vérifié en vrai**, hors relevé : binaire absent, GGUF absent, serveur qui s'arrête au démarrage (chemin au-delà de MAX_PATH dans le dossier temporaire) : sortie 2, aucun llama-server restant.
  - **Relevés** (`bench_sha256` `89674b22…`, banc d'avant la revue ; Ollama sans modèle chargé, aucun pytest ni serveur WaveStack pendant les mesures) : Julia-1 2 330 Mo (1 950 + 380), 170 / 307 ms, 9/20 et 8/20, **retenu par le banc** ; Laya 2 441 Mo (1 950 + 491), 1 478 / 2 170 ms, 12/20 et 9/20, **écarté** (latence). Hors ligne vérifié des deux côtés pour les deux, serveur arrêté à chaque fois. Un premier relevé de Julia-1 (même résultat, médiane 117 ms) a été refait après une correction de libellé du banc, pour que les deux JSON portent la même empreinte.
  - **Constats pour Anaël.** Critère 1 de Julia-1 (binaire portable) ; accord faible et erreurs confiantes de Julia-1 ; ggml-org publie aussi Kev-0.8B (≈ 813 Mo, Apache-2.0), hors périmètre, non mesuré.
  - **Laissé** : le banc n'est pas commité ; statut de la story laissé à `in-progress` (revue à faire).
- 2026-10-03, corrections de la revue (sans nouvelle mesure ; verdicts recalculés à partir des JSON enregistrés, inchangés) :
  - critère « code relu et figé » : sha256 de `llama-server.exe` (`LLAMA_EXE_SHA256`) ou de l'archive voisine exigé, en plus du build ; un GGUF dont le sha256 diffère n'est plus servi (« non mesuré : GGUF non conforme », sortie 2) ;
  - hors-ligne non vérifiable si des connexions n'ont pu être lues au démarrage (`startup_errors`) ; second `TimeoutExpired` après `kill()` consigné (`kill_error`) ; sortie 2 si un llama-server reste lancé après la mesure ; libellé de serveur inconnu sans `KeyError` ; seuil d'arrêt écrit `RAM_BUDGET_MB + 2048` et justifié ;
  - tests ajoutés pour chaque correction, le plafond de RAM de llama-server de bout en bout, l'affichage d'un relevé mesuré, `LLAMA_CACHE`, `_llama_processes` et `_pid_connections` sur un psutil simulé ;
  - documents : rapport de Laya corrigé (8,7 fois la médiane de Julia-1), accord de coût de Julia-1 sous le taux de base, sha256 complets, écart de latence d'un relevé à l'autre, limite de 512 tokens par question, unités, « Langue » ; note « Version du banc (story 9) » du rapport ; `SPEC.md` ; quatre entrées dans `deferred-work.md`.

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-03) : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Source | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|---|
| 1 | BH, EC | « 13 fois celle de Julia-1 » : les médianes donnent 8,7 fois (12,5 seulement à l'échauffement) | medium | `laya.json` 1 477,5 ms, `julia1.json` 169,5 ms | patch |
| 2 | BH | Accord de coût de Julia-1 (9/20) sous le taux de base (10/20 en répondant toujours pareil), non dit | medium | Attendus : 10 « simple », 10 « complexe » | patch (document, rapport) |
| 3 | BH, EC | Critère « figé » : seul le numéro de build est vérifié, pas le sha256 du binaire ni de l'archive ; un GGUF au sha256 faux est lancé quand même | medium | `decision_verdict` l. ~1465 ; l. ~3024 | patch |
| 4 | BH, EC, VG | Erreurs de relevé au démarrage (`startup_errors`) ignorées par le critère hors ligne | low | l. ~1432, 2961 | patch |
| 5 | VG | Tests manquants : seuil de RAM de `llama-server` jusqu'à « écarté (RAM) », ligne RAM imprimée, `startup_errors`, `sha256_ok`, retrait de `LLAMA_CACHE`, balayage réel des processus | medium | Recherches de VG | patch |
| 6 | BH | Documents : empreintes complètes du candidat retenu (GGUF, exe), version du banc des JSON, écart de latence entre deux passages (117 contre 170 ms), limite de 512 tokens par question (`--ubatch-size`), unités Mo/Mio, faits de Laya, formulation de « Langue », SPEC.md l. 85, entrées différées (critère 1, Kev-0.8B, croissance de RAM) | low | Diff | patch |
| 7 | BH | Seuil d'abandon de 6 144 Mo appliqué au seul `llama-server` sans justification | low | Commentaire seul | patch (justifier ou rapporter au budget) |
| 8 | EC | `stop()` : second `TimeoutExpired` non rattrapé ; serveur restant sans effet sur le code de sortie ; `SERVER_LABELS[...]` en `KeyError` | low | l. ~2974, 3257, 1422 ; corrections directes | patch |
| 9 | EC | Port libéré repris par un autre serveur avant `llama-server` | low | Rare ; le PID est vérifié ensuite | rejeté |
| 10 | EC | `OSError` (fichier verrouillé) qui sort de `run_measure` | low | Rare ; garde nouvelle | rejeté |
| 11 | BH | `killed: false` trompeur sous Windows | low | Cosmétique | rejeté |

## Verification

**Commands:**
- `uv run ruff check tools/bench tests/test_v2s6_decision_bench.py ; uv run ruff format --check tools/bench tests/test_v2s6_decision_bench.py` -- expected: aucun écart
- `uv run pytest tests -k "bench" -q` -- expected: vert
- `Get-Process llama-server -ErrorAction SilentlyContinue` -- expected: rien à la fin
