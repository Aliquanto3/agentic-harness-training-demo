---
title: 'Lot I : guide de test du palier 2 et documentation'
type: 'chore'
created: '2026-09-27'
status: 'done'
baseline_revision: '2abad497ef6d742c82eea0165f2213dc7a3fe497'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/_bmad-output/implementation-artifacts/guide-test-pc-palier-2.md'
  - '{project-root}/CLAUDE.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Le guide `guide-test-pc-palier-2.md` contient des écarts relevés au test du 2026-09-27 (plan, lot I) : 3 072 tokens utilisables avec le raisonnement au lieu de 2 560 ; commande llama-server sans `-c 4096` ni RSS attendue ; Ollama `qwen3.5` présenté comme refusé alors qu'il est accepté par l'Ollama du poste ; résultat E2E d'un poste connecté ; 4B refusé par le budget de 4 Go et pourquoi (N5) ; conditions de mesure (fermer Edge, Outlook et Teams) ; Mistral : un 429 dès « Tester » signale un quota épuisé. Le nombre de tests attendu est périmé (G3). Et le guide doit servir à la prochaine séance, qui vérifie les corrections des lots A à G sur le PC cible.

**Approach:** Corriger chaque point du lot I dans le guide (et le README quand il porte le même écart), mettre le nombre de tests à jour, et ajouter une section de vérification des corrections A à G, point par point, avec la commande ou le geste, le résultat attendu et le critère d'acceptation du plan.

## Boundaries & Constraints

**Always:** textes en français, commandes PowerShell pour le PC Windows ; chaque attendu du guide correspond à ce que le code fait réellement aujourd'hui (vérifié dans le code ou les tests, pas supposé) ; les critères d'acceptation du plan repris tels quels (second tour de `native_tools` : `prompt_ms` sous 3 s ; quiz du sous-agent sous 15 s ; `mcp_lazy`, `data_flows`, `iam`, `sovereignty` sans débordement ; prompt du train avec une réponse en moins de 120 s) ; « Ce qui marche déjà » du plan n'est pas re-testé en détail, seulement parcouru.

**Never:** modifier le code (lot I est documentaire) ; traiter le lot H (scénarios et consignes, après le prochain test) ; inventer une mesure.

</intent-contract>

## Code Map

- `_bmad-output/implementation-artifacts/guide-test-pc-palier-2.md` -- sections 0 à 7 ; lignes à corriger (relevé du plan) : l.26 (Teams et Edge → ajouter Outlook), l.100 (« 770 réussis, 5 sautés »), l.121-123 (E2E : « 327 vérifications et 0 échec… jamais tourné sous Windows »), l.138 (Headroom « ≈ 130 Mo », « aucune tentative réseau »), l.140-142 (RSS ajoutée du banc), l.187-192 (`pytest -m model` du RAG), l.218 (« 3 072 avec le raisonnement »), l.224-226 (mesure NFR-2), l.312-332 (modèles : llama-server l.325 sans `-c`, RSS l.327-329, Ollama `qwen35` l.332), l.316-321 et l.356 (4B), l.336-341 (Groq/Mistral, « Tester »).
- `README.md` -- l.~174 et 185-203 (llama-server, `-c`, mémoire comptée ; en partie mis à jour au lot E), l.~154-155 et 193-195 (Ollama `qwen35` refusé), l.~370-374 (Mistral 429).
- Specs des lots A à G (`spec-lot-*.md`, sections « Auto Run Result » et frontmatter `deferred`) et `deferred-work.md` (entrées fermées le 2026-09-27, notes « À vérifier sur PC ») : la liste des vérifications de la prochaine séance.
- Faits utiles déjà établis : utilisables = fenêtre − réserve (4 096 − 1 536 = 2 560 avec le raisonnement, 3 584 sans) ; budget de raisonnement `[reasoning] budget_tokens` 1 024 ; borne des résultats d'outils `[tools] result_max_tokens` 1 200 ; `[net] contact` ; `[compression] cost_mb` 130 ; `WAVESTACK_TEST_MODELS_DIR` pour les tests `model` du RAG ; `WAVESTACK_TEST_GGUF` pour les tests `model` du moteur (cache entre les tours, sauvegarde et restauration) ; `WAVESTACK_TEST_WINDOWS_FILES=1` (garde facultative, sans effet sous Windows) ; E2E : réseau sortant coupé par le lanceur (même résultat sur un poste connecté), `stack.py --network` pour l'exploration manuelle ; sous Linux : 930 réussis, 7 sautés, 6 désélectionnés (`model`) sans l'extra `compression`.

## Tasks & Acceptance

**Execution:**
- `_bmad-output/implementation-artifacts/guide-test-pc-palier-2.md` -- (1) chaque point du lot I corrigé à sa place ; (2) G3 : nombre de tests attendu sous Windows avec l'extra `compression` (compté depuis la suite : tests collectés hors `model`, et les sauts attendus sous Windows, chacun avec sa raison) ; commande `-m model` avec `WAVESTACK_TEST_MODELS_DIR` et `WAVESTACK_TEST_GGUF` ; (3) section 1 : HEAD attendu = dernier commit de la branche (lot I) ; (4) nouvelle section « Vérifier les corrections du palier 2 (lots A à G) », placée avant le parcours fonctionnel, un sous-point par lot : geste, résultat attendu, critère du plan, ce qui est encore une hypothèse (décisions prises par défaut : `data_flows` en lazy loading, `cost_mb` 130, RAG hors de l'historique d'où des relectures signalées `history`, raisonnement gardé dans l'historique) ; (5) section 6 « Décisions à trancher » : N6 (moteur par défaut) après la mesure du lot A, D2, D3, D9, et ce que le lot H attend du test ; (6) section 7 : où consigner (plan, `deferred-work.md`).
- `README.md` -- mêmes corrections quand il porte l'écart (Ollama `qwen35` accepté par un Ollama récent, refus seulement si l'Ollama ne sert pas `qwen35` ; Mistral 429 dès « Tester » = quota épuisé, console Mistral).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer l'entrée du lot I (« Guide de test du palier 2 à corriger »).

**Acceptance Criteria:**
- Given le guide mis à jour, when un testeur suit la nouvelle section de vérification, then chaque correction A à G a un geste, un attendu et un critère mesurable, et aucun attendu ne contredit le code.
- Given les points du lot I, when on relit le guide, then aucun des sept écarts n'y reste.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 21 findings (constats des quatre couches, doublons regroupés avec leurs sources) — high 0, medium 7, low 10, false 0, maybe-false 4
- findings:
  - `[medium]` `[patch]` Critère « quiz du sous-agent sous 15 s » déplacé sans le dire (RAG éteint) (blind) — deux mesures consignées ; acceptation RAG éteint, décision par défaut à confirmer (D5 → lot H).
  - `[medium]` `[patch]` Lot C : tour suivant sans « Préfixe non réutilisé » non vérifié (blind) — ajouté.
  - `[medium]` `[patch]` Resonde du 2B (E2) invisible où le guide la place (blind, edge) — observée au premier lancement, nouvelle étape de lancement.
  - `[medium]` `[patch]` Bancs lancés en `--json` : ni « RETENU » ni `e5small_q8` à lire (edge) — lecture du JSON en PowerShell, `embed --only e5small_q8`.
  - `[medium]` `[patch]` 4B : refus possible sur l'ancienne estimation avant toute sonde, RAG compté (edge) — RAG éteint d'abord, refus anticipé dit.
  - `[medium]` `[patch]` Texte de code contradictoire (tokenizer refusé « comme Qwen3.5 ») (blind, edge) — corrigé dans le code par un commit séparé.
  - `[medium]` `[patch]` Ollama trop ancien présenté comme un refus alors que le premier tour échoue en « HTTP 500 » brut (blind) — décrit tel quel ; entrée ouverte dans `deferred-work.md` pour le code.
  - `[low]` `[patch]` llama-server : arrêts et relances non dits, risque de RAM (blind) — ajoutés.
  - `[low]` `[patch]` « Arrêter » sur un choix Ollama trop rapide pour cliquer (edge) — test sur un chargement GGUF.
  - `[low]` `[patch]` `budget_mb` en syntaxe TOML pour un fichier JSON (blind) — forme JSON, N5 rompue le temps de la mesure.
  - `[low]` `[patch]` Mistral 429 : seulement au premier appel de « Tester », lire le message du fournisseur (edge) — guide et README.
  - `[low]` `[patch]` Nombre de tests `model` sautés selon la variable absente (edge) — 4 et 2.
  - `[low]` `[patch]` D2 et D3 sans procédure ni retour arrière (blind, edge) — procédures avec restauration.
  - `[low]` `[patch]` D5 à D18 disparus du tableau (blind) — ligne ajoutée.
  - `[low]` `[patch]` Tableau des résultats sans lignes N6, D2, D3, D9, F2, budget (blind) — ajoutées ; fusion après le lot H.
  - `[low]` `[patch]` Vérification des captures après `git pull` (blind) — avant.
  - `[low]` `[patch]` Sauvegarde de retour arrière prise après les données du palier 2 (blind) — `sauvegarde-palier-1` gardée comme source, commande de restauration.
  - `[maybe-false]` `[patch]` « Nettement » non chiffré (blind) — 20 % ou 50 Mo, mesure + 30 %.
  - `[maybe-false]` `[reject]` Chiffres Windows prédits (934/3) et non mesurés (intent) — seul le PC peut les mesurer ; le guide donne la référence Linux vérifiée.
  - `[maybe-false]` `[reject]` Portée « réécriture » au-delà des sept points (intent) — demandée par l'utilisateur (« pour la prochaine séance de test »).
  - `[maybe-false]` `[reject]` Aucune vérification automatique d'un document (verification-gap : aucun écart) — sans objet pour un document.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème (aucun code touché)
- `uv run pytest -q --co -q | tail -1` -- expected: le nombre collecté cité par le guide

**Manual checks (if no CLI):**
- Relire le guide : les sept points du lot I corrigés, la section de vérification A à G complète, les commandes PowerShell cohérentes entre elles.

## Auto Run Result

Status: done

**Résumé.** Guide de test du palier 2 réécrit pour la prochaine séance : les sept écarts du lot I corrigés (2 560 utilisables avec le raisonnement, llama-server avec `-c 4096` et RSS attendue, Ollama `qwen3.5:2b` accepté, E2E sans échec sur un poste connecté, 4B refusé par le budget de 4 096 Mo et pourquoi, Edge, Outlook et Teams fermés, Mistral 429 au premier appel de « Tester ») ; G3 : 937 tests collectés hors `model`, 934 réussis et 3 sautés attendus sous Windows avec l'extra (raison de chaque saut), commandes `-m model` avec `WAVESTACK_TEST_GGUF` et `WAVESTACK_TEST_MODELS_DIR` ; nouvelle section « Vérifier les corrections du palier 2 (lots A à G) » (geste, attendu, critère du plan, hypothèses) ; décisions N6, D2, D3, D9, F2 et attentes du lot H ; tableau des résultats ; fusion après le lot H. README aligné (Ollama, Mistral 429).

**Fichiers.** `guide-test-pc-palier-2.md`, `README.md`, `deferred-work.md` (entrée du lot I fermée ; entrée ouverte : Ollama trop ancien → « HTTP 500 » brut au premier tour).

**Revue.** 18 patchs (7 medium, 11 low ou maybe-false), 0 différé, 3 rejetés. Deux textes de code relevés par la revue (raison du tokenizer refusé, phrase « modèle hybride » en double) corrigés dans un commit séparé, le lot I restant documentaire.

**Vérification.** `ruff check` : OK ; `pytest --co` : 937/943 collectés (6 désélectionnés) ; parcours E2E complet : 336 vérifications sans l'extra, 356 avec, 0 échec ; `embed --only e5small_q8` : message français, code 2.
