---
title: 'Modèles : mémoire comptée juste, budget dynamique, sonde interruptible'
type: 'bugfix'
created: '2026-09-28'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-lot-e-modeles-memoire-refus-arret.md'
  - '{project-root}/_bmad-output/implementation-artifacts/retours-recette-palier-2-2026-09-28.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
warnings: ['oversized', 'multiple-goals']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Recette du 2026-09-28 (C4, C5, C6). Le refus par le budget affiche « WaveStack occupe 0 Mo sans le modèle actif » : la mémoire de base est déduite en retranchant de la RSS une part estimée (mesure de la sonde) plus grande que ce que les poids en mmap occupent vraiment. « Arrêter » pendant la sonde d'un GGUF attend la fin du processus enfant (≈ 25 s, jusqu'à 300 s). `llama3.2:3b` servi par Ollama est estimé à ≈ 4,0 Go (RSS de la sonde en processus du blob, KV et tampons compris, plus la marge) et refusé alors qu'il tournait la veille. Les raisons de la sonde arrivent mal décodées (« abÃ®mÃ© ») et restent ainsi dans `settings.json`. Enfin, décision du 2026-09-28 : le budget fixe de 4 096 Mo devient dynamique et plafonné.

**Approach:** (1) La mémoire de base est mesurée juste avant la création du moteur (après la libération) et gardée dans la réservation ; le refus retranche au plus jusqu'à cette base. (2) Budget calculé une fois au lancement : `min(plafond budget_mb, budget_ram_ratio × RAM disponible)` en mode `dynamic` (défaut), `budget_mb` en mode `fixed` ; le diagnostic et chaque refus affichent le budget et son calcul. (3) La sonde tourne en `Popen` avec une attente par tranches qui lit le jeton d'arrêt et termine l'enfant ; un arrêt n'enregistre rien. (4) Un modèle Ollama non résident coûte fichier + KV à la fenêtre + marge, jamais la RSS de la sonde en processus ; règle écrite dans AD-8. (5) Sortie de la sonde en JSON ASCII, lecture en UTF-8, réparation à la lecture des raisons déjà abîmées.

## Boundaries & Constraints

**Always:** code et identifiants en anglais, textes en français ; `uv`, `ruff`, `pytest` ; aucune dépendance nouvelle (psutil est déjà là) ; aucun vrai modèle dans le conteneur : faux moteur, faux serveurs (`tests/test_model_servers.py`, `tools/e2e/fake_local_server.py`), GGUF synthétiques (`tests/gguf_writer.py`), faux fournisseurs, enfant de sonde simulé ; jamais deux modèles génératifs (AD-8) ; un arrêt laisse toujours un état cohérent (modèle précédent actif, ou aucun) ; les tests existants restent verts (ceux qui figent l'ancien texte du refus ou `subprocess.run` de la sonde sont adaptés, pas supprimés) ; un budget identique pour le diagnostic et la session (même objet `Config`, calcul mis en cache) ; EXPERIENCE.md, SPEC.md (NFR-2), README, `wavestack.toml` et le spine (AD-7, AD-8) mis à jour ; parcours E2E complété.

**Never:** recalculer le budget pendant la session (seulement au lancement) ; dépasser le plafond en mode `dynamic` (NFR-2 : 4 Go au plus par défaut) ; lancer, arrêter ou reconfigurer Ollama ou llama-server ; rendre interruptible la sonde du diagnostic de lancement (aucun « Arrêter » sur cette page) ; interrompre un chargement llama.cpp en processus (inchangé : point d'arrêt après l'étape) ; réécrire `settings.json` à la simple lecture d'une raison abîmée ; changer `PROBE_VERSION` (forcerait la resonde de tous les fichiers).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Refus, poids en mmap peu résidents | Base mesurée 150 Mo avant le moteur ; RSS 900 Mo ; part de la sonde 2,5 Go | « WaveStack occupe 150 Mo sans le modèle actif » | `without = max(base, rss − part)`, jamais 0 quand une base existe |
| Budget dynamique, plafond atteint | RAM 16 Go, dispo 9 600 Mo, ratio 0,6, plafond 4 096 | Budget 4 096 Mo ; calcul « plafond … plus petit que 60 % des 9 600 Mo disponibles » | — |
| Budget dynamique, RAM limitante | Dispo 5 000 Mo | Budget 3 000 Mo ; diagnostic `warn` « fermez des applications puis relancez WaveStack » ; refus qui donne le calcul | — |
| Budget fixe | `budget_mode = "fixed"`, `budget_mb = 6144` | Budget 6 144 Mo, « valeur fixe » | — |
| Réglages invalides | ratio 3 ou « abc », mode inconnu | ratio borné [0,1 ; 0,9] ou 0,6 par défaut ; mode `dynamic` | — |
| RAM illisible | `virtual_memory()` lève | Budget = plafond, « RAM du poste non mesurée » dans le calcul | contrôle « memory » du diagnostic en `warn`, jamais bloquant |
| Arrêter pendant la sonde | Enfant lent, clic « Arrêter » | Enfant terminé en moins de 1 s, `model_load_ended{cancelled}`, précédent rétabli ; rien dans `failed_probes`, aucun `harness_error` « incompatible » | — |
| Sonde qui dépasse 300 s | Enfant bloqué | Enfant tué, échec passager (inchangé) | — |
| Ollama non résident | Blob 2,0 Go, KV 112 Kio/token, fenêtre 4 096, marge 256 Mo, entrée de sonde à 3,6 Go | Coût ≈ 2,6 Go (fichier + 448 Mo + marge), `rss_bytes` ignoré ; ligne du diagnostic ≈ 2,3 Go | KV illisible : fichier + marge |
| Raison accentuée | Enfant : « abîmé » | Lue « abîmé » (Windows cp1252 compris) | Octets invalides : remplacés, jamais d'exception |
| Raison déjà abîmée | `failed_probes[…].reason` = « abÃ®mÃ© » | Diagnostic et sélecteur affichent « abîmé » | Réparation impossible : texte gardé tel quel |

</intent-contract>

## Code Map

Numéros de ligne indicatifs (`app_session.py` bouge avec les stories 33, 23, 34, 32) : se repérer aux symboles.

- `src/wavestack/models/load_registry.py` -- `_Grant` (l.~109 : `cost`, `in_process`, `share`) ; `file_cost` (l.~133) ; `file_share` (l.~147) ; `check` (l.~154, texte du refus) ; `_without` (l.~170, `max(0, rss − share)` : cause du « 0 Mo ») ; `check_component` (l.~185, texte « relevez [memory] budget_mb ») ; `grant` (l.~199) ; `process_rss`, `_size`, `_mo`, `_go`.
- `src/wavestack/config.py` -- `memory_budget_bytes` (l.~369), `load_margin_bytes`, `_int`, `_float` (l.~330) ; `Config` a déjà des `cached_property`.
- `src/wavestack/session/app_session.py` -- `AppSession.__init__` (`LoadRegistry(self.cfg.memory_budget_bytes, …, rss_fn or process_rss)`) ; `_cost` (l.~1350 : serveur non résident → `file_cost(served.gguf_path, …)`, d'où les 4,0 Go) ; `switch_model` (signature `probe: Callable[[str], str | None]`) ; `_load` (sonde `why = probe(choice.ref)` puis `_checkpoint(cancel)`) ; `_checkpoint`, `_LoadCancelled`, `_load_cancelled`, `_last_checkpoint` ; `_install` (création du moteur par `_engine_factory`, `grant(…, in_process, share)` à la fin) ; `stop` (arme `_load_cancel` en `model_load`).
- `src/wavestack/session/diagnostic.py` -- `PROBE_TIMEOUT_S` (l.~58), `MEMORY_WARN_MB` ; `check_memory` (l.~152) ; `_probe_candidate` (l.~191 : `subprocess.run(…, capture_output=True, text=True)` sans `encoding`, `record_failure` sur plantage natif et sur échec) ; `_discover` (l.~323 : `failed_entry(path).get("reason")`) ; `switch` (passe `probe=self.probe_path`) ; `probe_path` (l.~722).
- `src/wavestack/models/probe.py` -- `ProbeResult`, `record_failure`, `failed_entry` (l.~289, seul lecteur de `failed_probes`), `gguf_kv_bytes_per_token` (lecteur Python pur), `main` (l.~356 : `print(result.model_dump_json())`, non ASCII).
- `src/wavestack/models/servers.py` -- `ServedModel`, `served_bytes(model, path)` (l.~741 : Ollama non résident = taille du blob seule), `served_kv` (llama-server seulement).
- `src/wavestack/models/discovery.py` -- `_server_candidates` (l.~164 : `candidate.served_bytes = servers.served_bytes(model, candidate.gguf_path)`, `cfg` disponible).
- `src/wavestack/web/static/app.js` -- `modelLoadText` (« Arrêt demandé, effectif à la fin de l'étape en cours · »).
- `src/wavestack/web/static/diagnostic.html` -- ligne de candidat servi (`c.served_bytes` en Go) ; contrôles rendus depuis `diagnostic_check` (aucun code propre à `memory`).
- `tools/e2e/launch_app.py` -- ralentit `_install` de `fake_b` ; point d'accroche des doublures du lanceur. `tools/e2e/run_e2e.py` -- `s_model_switch` (« Arrêter » pendant le chargement lent de `fake_b`, vérifie « Arrêt demandé »), `r.stack.data_dir`.
- Tests à adapter : `tests/test_cli_diagnostic.py` et `tests/test_model_switch.py` (`_probe_child`) remplacent `diagnostic_module.subprocess.run` et bouchent `_probe_candidate` par `lambda candidate: None` ; `tests/test_model_switch.py` (texte du refus « … sans le modèle actif »), `tests/test_rag.py` (l.~308, texte de `check_component`), `tests/test_model_servers.py` (budget, Ollama) ; `tests/conftest.py` (fixtures `autouse`).
- Docs : `README.md` (l.~138-165 « Budget mémoire », l.~285), `wavestack.toml` (`[memory]`, l.~42-52), SPEC.md NFR-2, EXPERIENCE.md (ligne `model-picker`), spine AD-7 (« Sonde ») et AD-8 (« Refus », « Estimation du coût », « Mode serveur »).

## Tasks & Acceptance

**Execution:**
- `src/wavestack/config.py` -- ajouter `system_memory() -> tuple[int, int]` (totale, disponible, via `psutil.virtual_memory()`), un `MemoryBudget` figé (`bytes`, `mode`, `cap_bytes`, `ratio`, `total_bytes`, `available_bytes`, `ram_limited`, `measured`) avec `calc_fr()` (le calcul, en Mo) ; `Config.memory_budget` en `cached_property` lisant `[memory] budget_mode` (`dynamic` défaut | `fixed`), `budget_mb` (plafond ou valeur fixe, 4 096), `budget_ram_ratio` (0,6, borné [0,1 ; 0,9]) ; `memory_budget_bytes` renvoie `memory_budget.bytes` -- un seul calcul au lancement, partagé par diagnostic et session (même `_cfg` dans `cli.py`).
- `src/wavestack/models/load_registry.py` -- `LoadRegistry` reçoit le `MemoryBudget` (ou ses octets et `calc_fr`) ; `_Grant.base` ; `grant(…, base=)` ; `baseline()` = `self._rss()` ; `_without` = `max(base, rss − part)` quand le détenteur est en processus ; textes de `check` et `check_component` avec le calcul, et « fermez des applications puis relancez WaveStack » quand la RAM limite -- (1), (2).
- `src/wavestack/session/app_session.py` -- `_install` : mesurer `baseline()` juste avant `_engine_factory` (fichier seulement) et le passer à `grant` ; `_cost` : serveur non résident → `served_bytes(…, window)` + marge, jamais `file_cost` du blob ; `switch_model`/`_load` : `probe(path, cancel)` avec le jeton de chargement -- (1), (3), (4).
- `src/wavestack/session/diagnostic.py` -- seam `_probe_argv(path, window)` et `_run_probe(argv, cancel, timeout)` : `Popen(stdout/stderr=PIPE, text=True, encoding="utf-8", errors="replace")`, `communicate(timeout≈0,2)` en boucle qui teste `cancel` et l'échéance, `kill()` puis `communicate()` pour récolter l'enfant ; sur arrêt, `_probe_candidate(candidate, cancel=None)` ne touche ni au candidat, ni à `failed_probes`, ni au journal ; `probe_path(path, cancel=None)` renvoie `None` (le `_checkpoint` de `_load` lève) ; `check_memory` : disponible, totale, budget et calcul, `warn` si la RAM limite -- (2), (3), (5).
- `src/wavestack/models/probe.py` -- `main` : `sys.stdout.reconfigure(encoding="utf-8")` et JSON en ASCII (`json.dumps(result.model_dump(mode="json"))`) ; `repair_mojibake(text)` (cp1252 → UTF-8 si « Ã », « Â » ou « â€ » présent, inchangé si impossible) appliqué par `failed_entry` à `reason` (copie, sans écriture) -- (5).
- `src/wavestack/models/servers.py`, `src/wavestack/models/discovery.py` -- `served_bytes(model, path, window=None)` : Ollama non résident = blob + `gguf_kv_bytes_per_token(blob)` × fenêtre configurée ; `_server_candidates` passe `cfg.context_window` -- même chiffre au diagnostic et au contrôle (marge en plus au contrôle).
- `src/wavestack/web/static/app.js` -- `modelLoadText` : « Arrêt demandé · » (sans « effectif à la fin de l'étape », faux pendant la sonde) -- texte juste.
- `tools/e2e/launch_app.py` -- pour un fichier nommé `sonde-lente-e2e.gguf`, `_probe_argv` renvoie un enfant qui dort 120 s (chemin gardé en dernier argument pour le retrouver) -- sonde lente sans vrai modèle.
- `tools/e2e/run_e2e.py` -- dans `s_model_switch` (ou un scénario voisin) : diagnostic « Budget mémoire » avec « % » et « Mo » ; après le lancement, écrire `sonde-lente-e2e.gguf` (octets quelconques, hors dossier scanné au lancement), le saisir dans `#model-path`, revenir à la page principale, cliquer « Arrêter » ; vérifier `model_load_ended{cancelled}` en moins de 3 s, le modèle précédent actif, plus aucun processus dont la ligne de commande contient `sonde-lente-e2e` (psutil), aucune entrée dans `failed_probes` de `settings.json`, aucun `harness_error` « incompatible ».
- `tests/conftest.py` -- fixture `autouse` qui fixe `config.system_memory` à 16 Gio / 12 Gio : les tests existants gardent un budget de 4 096 Mo quelle que soit la machine.
- `tests/test_memory_budget.py` (nouveau), `tests/test_model_switch.py`, `tests/test_cli_diagnostic.py`, `tests/test_probe.py`, `tests/test_model_servers.py`, `tests/test_rag.py` -- matrice I/O : budget (RAM injectée, modes, bornes, RAM illisible), base mesurée (RSS injectée qui change avant/après le moteur), arrêt pendant une sonde lente simulée (vrai enfant `sys.executable -c "sleep"` par `_probe_argv`, jeton armé depuis un thread : retour en moins de 2 s, `psutil.pid_exists` faux, rien enregistré), `main` ASCII, décodage UTF-8, réparation, coût Ollama non résident ; adapter les tests qui remplacent `subprocess.run` (vers `_run_probe`) et les bouchons `_probe_candidate`/`probe_fn` à un argument.
- `README.md`, `wavestack.toml`, SPEC.md (NFR-2), EXPERIENCE.md, spine AD-7 et AD-8 -- budget dynamique et son calcul, nouvelles clés commentées, base mesurée, « Arrêter » immédiat pendant la sonde, règle du coût Ollama ; dans AD-8 une ligne *Décision provisoire, à valider (story 24)*.

**Acceptance Criteria:**
- Given un modèle local actif dont les poids sont peu résidents, when un modèle plus gros est refusé, then le refus nomme la base mesurée avant le chargement (jamais 0 Mo) et le budget avec son calcul.
- Given WaveStack lancé, when la page de diagnostic s'affiche, then le contrôle « memory » donne RAM totale, disponible, part, plafond et budget retenu, identique au budget des refus de la session.
- Given la sonde lente d'un fichier choisi à chaud, when l'utilisateur clique « Arrêter », then l'enfant est terminé, le modèle précédent revient (« Chargement arrêté : … est de nouveau actif. ») en moins de 3 s, et le fichier n'est pas marqué incompatible.
- Given un modèle Ollama non résident dont le blob a une entrée de sonde, when on le choisit, then son coût est fichier + KV à la fenêtre + marge, et `llama3.2:3b` passe sous un budget de 4 096 Mo avec ≈ 150 Mo de base.
- Given une raison abîmée dans `settings.json`, when le diagnostic liste le fichier, then la raison s'affiche correctement accentuée sans nouvelle sonde.

## Spec Change Log

## Review Triage Log

## Design Notes

- Base : `max(base, rss − part)` et non `base` seule, pour compter aussi ce qui s'est chargé après le modèle (embedding, reranker, caches) quand les poids sont résidents ; `base` seule garantit le plancher.
- Budget « au lancement » : RAM disponible lue une fois ; WaveStack pèse alors ≈ 100 Mo, négligeable. La story 26 (fenêtre réglable) réutilisera `MemoryBudget` et `LoadRegistry.check`.
- Coût Ollama : la sonde du blob mesure llama-cpp-python dans l'enfant de WaveStack (tampons de calcul, KV à `probe_window`) ; Ollama a son propre moteur et sa mémoire n'est pas dans la RSS de WaveStack. Compter fichier + KV (f16) à la fenêtre + marge l'estime une seule fois ; la marge couvre le tokenizer `vocab_only` ouvert dans WaveStack.
- Exemple de calcul (`calc_fr`, mode dynamique, plafond atteint) : « plafond [memory] budget_mb de 4 096 Mo, plus petit que 60 % des 9 600 Mo de RAM disponibles au lancement (5 760 Mo), sur 16 071 Mo ».

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert (tests Windows compris)
- `node --check src/wavestack/web/static/app.js` -- expected: pas d'erreur
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; captures de `tools/e2e/screenshots` mises à jour et commitées

## Décisions prises par défaut

- Budget calculé une fois par processus (cache sur `Config`), au premier accès pendant le lancement : l'intention dit « au lancement » ; un recalcul en cours de session rendrait les refus imprévisibles.
- `budget_mb` garde son nom et devient le plafond en mode `dynamic` : aucune configuration existante ne casse ; en mode `fixed` il garde son sens actuel.
- Ratio borné à [0,1 ; 0,9], mode inconnu lu comme `dynamic` : valeurs sûres, sans bloquer le lancement.
- Diagnostic en `warn` (non bloquant) quand la RAM disponible limite le budget sous le plafond : pédagogique, sans empêcher la démo.
- `without = max(base, rss − part)` plutôt que la base seule : ne sous-estime jamais, compte les composants chargés après le modèle.
- Sonde du diagnostic de lancement non interruptible (pas de bouton « Arrêter » sur cette page) ; seule la sonde d'un changement à chaud l'est.
- Arrêt de l'enfant par `kill()` (TerminateProcess sous Windows) : immédiat ; la sonde n'écrit rien, rien à nettoyer.
- Coût Ollama non résident au KV f16 de la fenêtre configurée : borne haute cohérente avec `_cost` ; le KV quantifié ou `OLLAMA_NUM_PARALLEL` > 1 d'Ollama restent à vérifier sur PC.
- Raisons abîmées réparées à la lecture sans réécrire `settings.json` : lecture sans effet de bord ; la prochaine sonde réécrit l'entrée proprement.
- Texte de la barre haute réduit à « Arrêt demandé · » : le front ne sait pas si l'étape est une sonde (interruptible) ou un chargement ; pas de nouvel événement.
- Seam `_probe_argv`/`_run_probe` plutôt qu'un patch de `subprocess.Popen` dans les tests et le lanceur E2E : un seul point d'accroche.

## À vérifier sur PC

- **Geste** : Edge, Outlook et Teams fermés ; lancer WaveStack, lire la ligne « Mémoire » du diagnostic ; dans PowerShell, `uv run python -c "import psutil; v=psutil.virtual_memory(); print(v.total//2**20, v.available//2**20)"`. — **Attendu** : RAM totale, disponible, 60 %, plafond et budget retenu. — **Critère** : budget = min(4 096, 0,6 × disponible) à 5 % près de la mesure PowerShell. — **Moyen** : script AppSession ou Claude in Chrome.
- **Geste** : rouvrir Edge et Teams, relancer WaveStack. — **Attendu** : budget plus petit si la RAM disponible chute sous 6,8 Go, contrôle en `warn` avec le conseil. — **Critère** : chiffres cohérents avec PowerShell. — **Moyen** : à la main.
- **Geste** : mettre `budget_mode = "fixed"` et `budget_mb = 6144` dans `[memory]` de `wavestack.toml`, relancer. — **Attendu** : « valeur fixe », 6 144 Mo. — **Critère** : texte exact du budget. — **Moyen** : Playwright ou à la main.
- **Geste** : 2B actif, choisir le 4B dans « Changer de modèle ». — **Attendu** : refus chiffré. — **Critère** : « WaveStack occupe N Mo sans le modèle actif » avec 80 ≤ N ≤ 400, jamais 0, proche (±100 Mo) de la RSS mesurée par script après libération. — **Moyen** : script AppSession.
- **Geste** : copier le 2B sous un autre nom dans `models\` (jamais sondé), le choisir à chaud, cliquer « Arrêter » dans les 5 s. — **Attendu** : « Chargement arrêté : … est de nouveau actif. ». — **Critère** : `Get-Process python` ne montre plus l'enfant de sonde 1 s après le clic ; aucune entrée pour ce fichier dans `failed_probes` ; fin d'arrêt ≤ 3 s plus le rechargement du 2B. — **Moyen** : Claude in Chrome et PowerShell.
- **Geste** : Ollama lancé, `llama3.2:3b` non chargé (`ollama ps` vide), le choisir. — **Attendu** : accepté ; ligne du diagnostic ≈ 2,3 Go. — **Critère** : pas de refus ; après un message, `ollama ps` (SIZE) à ±30 % de l'estimation ; noter `OLLAMA_NUM_PARALLEL` et le type de KV d'Ollama. — **Moyen** : script AppSession et PowerShell.
- **Geste** : reprendre le fichier incompatible de C6 (même fichier que la recette), le choisir. — **Attendu** : raison accentuée juste dans le diagnostic et le journal. — **Critère** : aucun « Ã » ni « Â » dans la page ni dans les nouvelles entrées de `settings.json`. — **Moyen** : Claude in Chrome.
- **Geste** : avant la mise à jour, garder le `settings.json` du PC (entrée C6 abîmée) ; après, ouvrir le diagnostic. — **Attendu** : raison réparée sans nouvelle sonde. — **Critère** : « abîmé » et « modèle » corrects ; `settings.json` inchangé tant qu'aucune sonde ne réécrit l'entrée. — **Moyen** : à la main.
