---
title: 'Lot F : Headroom hors ligne et banc de la story 12'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '12faad6ce19aca068d944aa33f431b6175033a06'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/CLAUDE.md'
  - '{project-root}/tools/bench/README.md'
warnings: ['multiple-goals']
deferred:
  - summary: >-
      La mémoire ajoutée par Headroom avec le comptage `gpt-4` n'est pas mesurée sous Windows.
    evidence: |-
      Non vérifié : 107 Mo au pic sous Linux, 57 Mo sur le PC cible avec l'ancien comptage. Se tranche au banc `headroom` sur le PC, puis ajuster `[compression] cost_mb` (130 aujourd'hui).
    location: >-
      wavestack.toml:[compression]
    severity: medium (unverified)
  - summary: >-
      Les pics réels du banc embed sur le PC (granite ≈ +428 Mo, reranker ≈ +736 Mo) et les verdicts qui en découlent restent à relever.
    evidence: |-
      Non vérifié ici (aucun vrai GGUF) ; bge-m3 et Qwen3-Embedding dépasseront le budget de 600 Mo.
    location: >-
      tools/bench/story12_bench.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** (F1) Sur le PC cible, Headroom tente de joindre `openaipublic.blob.core.windows.net` : `COUNTING_MODEL = "gpt-4o"` demande la table `o200k_base`, que le cache tiktoken du poste n'a pas trouvée (seules `cl100k_base` et `p50k_base` y étaient) ; le banc, variante configurée comprise, a donné « ÉCARTÉ ». (F2) `[compression] cost_mb = 130` alors que Headroom ajoute 57 Mo sur le PC cible. (F3) Le banc mesure la RSS « ajoutée » après la libération du modèle (3 à 6 Mo affichés) au lieu du pic, modèle chargé (granite +428 Mo, reranker +736 Mo). (F4) Le candidat `e5small_q8` échoue (« Failed to load model ») avec llama-cpp-python 0.3.35.

**Approach:** (F1) compter avec `gpt-4` (`cl100k_base`, présente partout), commentaires corrigés, même modèle dans le banc (variante configurée), et un test hors ligne qui enregistre toute tentative réseau à l'import et à la compression. (F2) décision par défaut : `cost_mb = 80` (57 Mo mesurés sur le PC cible, plus une marge). (F3) RSS ajoutée = pic moins base, modèle chargé. (F4) retirer `e5small_q8` des candidats, avec la raison dans le README du banc.

## Boundaries & Constraints

**Always:** code en anglais, textes en français ; `uv`, `ruff`, `pytest` ; tests verts sous Linux et Windows, avec ou sans l'extra `compression` (un test qui demande Headroom est sauté proprement sans lui) ; AD-15 : aucune tentative réseau de Headroom ni de litellm à l'import ou à la compression ; les résultats du PC cible (`tools/bench/results/2026-09-27-pc-cible/`) restent tels quels.

**Never:** changer la version épinglée de `headroom-ai` ou de litellm ; ajouter une dépendance ; modifier les briques de compression au-delà du modèle de comptage et du coût mémoire.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Import hors ligne | Extra `compression`, variables hors ligne posées, garde réseau qui enregistre | Aucun `socket.getaddrinfo`/`connect` vers un hôte public à l'import de l'adaptateur | Tentative : le test échoue et la nomme |
| Compression hors ligne | `journal_serveur.log` compressé | Compression faite, aucune tentative réseau | — |
| Sans l'extra | Headroom absent | Tests Headroom sautés, les autres passent | — |
| Budget | Chargement de la compression | Coût contrôlé : 80 Mo par défaut | — |
| Banc, RSS ajoutée | Candidat embedding ou reranker | `rss_added_mb` = pic − RSS avant chargement ; verdict sur cette valeur | — |
| Banc, candidats | Liste des candidats | `e5small_q8` absent ; le test d'échec d'un candidat utilise un candidat factice | — |

</intent-contract>

## Code Map

- `src/wavestack/compression/headroom_adapter.py:33-36` -- `HEADROOM_VERSION`, commentaire (« `o200k_base`, shipped by litellm ») et `COUNTING_MODEL = "gpt-4o"`, utilisé l.~121.
- `src/wavestack/compression/env.py` -- `OFFLINE_ENV` (l.15-21), `tiktoken_cache_dir` (commentaire « `cl100k_base`, `o200k_base` »), `apply_offline_env`.
- `wavestack.toml:113-120` -- `[compression] min_chars`, `cost_mb = 130` et son commentaire ; `src/wavestack/config.py:~426` -- `compression_cost_bytes` (défaut 130).
- `tools/bench/story12_bench.py` -- `HEADROOM_OFFLINE_ENV` (l.44-55), candidats embedding (l.~230-241 `e5small_q8`), `_passes` (l.465-475), `_record_and_guard` (l.526-562 : garde qui enregistre les tentatives, modèle pour le test), `_peak_rss_mb` (l.571-586), variante Headroom (l.701 `kompress_model`, l.718 et 736 `model="gpt-4o"`, l.743-744 RSS), mesure embedding/reranker (l.~1000, 1078 : RSS après `llm.close()` ; l.1135-1138 `rss_added_mb = rss_after_run − rss_before_load`), sortie (l.1265).
- `tools/bench/README.md` -- description du banc et des candidats.
- `tests/test_story12_bench.py:280,292` -- `e5small_q8` comme candidat qui échoue.
- `tests/test_compression.py` -- `test_offline_variables_are_set…` (l.~686), `test_headroom_adapter_compresses_the_demo_log_offline` (l.~717 : passe même avec une tentative, Headroom se repliant en silence) ; `tests/conftest.py:13-24` : garde de session qui bloque sans enregistrer.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- quatre entrées du 2026-09-27 du lot F, à fermer.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/compression/headroom_adapter.py`, `src/wavestack/compression/env.py` -- `COUNTING_MODEL = "gpt-4"` (table `cl100k_base`, livrée par litellm et présente sur le PC cible) ; commentaires justes.
- `wavestack.toml`, `src/wavestack/config.py` -- `cost_mb = 80`, commentaire : 57 Mo mesurés sur le PC cible le 2026-09-27, marge comprise.
- `tools/bench/story12_bench.py` -- même modèle de comptage que l'adaptateur (importé ou constante partagée) dans les deux variantes ; `rss_added_mb` = pic − RSS avant chargement, mesurés modèle chargé (le pic lu avant `close()`), pour l'embedding et le reranker ; `e5small_q8` retiré.
- `tools/bench/README.md` -- RSS ajoutée au pic ; `e5small_q8` retiré (échec de chargement avec llama-cpp-python 0.3.35) ; modèle de comptage `gpt-4`.
- `tests/test_story12_bench.py` -- le test du candidat qui échoue utilise un candidat factice ; test : `rss_added_mb` vient du pic.
- `tests/test_compression.py` -- test hors ligne (Headroom requis, sinon sauté) dans un sous-processus avec les variables hors ligne et une garde qui enregistre (`sys.addaudithook` sur `socket.getaddrinfo`/`socket.connect`, comme `_record_and_guard`) : import de l'adaptateur puis compression du journal de démonstration ; aucune tentative vers un hôte hors de la boucle locale ; le modèle de comptage est `gpt-4` ; `compression_cost_bytes` vaut 80 Mo par défaut.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer les quatre entrées du lot F.

**Acceptance Criteria:**
- Given l'extra `compression` et aucun réseau, when l'adaptateur est importé puis compresse `journal_serveur.log`, then aucune tentative réseau n'est enregistrée.
- Given le banc sur un candidat d'embedding, when il rend son résultat, then la RSS ajoutée est celle du pic, modèle chargé.

## Spec Change Log

- 2026-09-27 — Constat de l'implémentation (banc réel, conteneur Linux) : avec le comptage `gpt-4` de F1, Headroom ajoute 99 Mo, au-dessus des 80 Mo retenus pour F2. Le plan liait F2 à F1 (« garder 130 par prudence ou passer à 80, à trancher avec F1 ») : F2 est tranché à 130 (valeur gardée) ; les 57 Mo du PC cible avaient été mesurés avec `gpt-4o` et une table absente. Modifié : `wavestack.toml`, `config.compression_cost_bytes`, README, test du défaut. État évité : un coût sous-estimé qui laisserait passer un chargement au-delà du budget (AD-8). KEEP : F1, F3, F4 et le test hors ligne tels quels. Le tableau de l'`intent-contract` (« 80 Mo par défaut ») est dépassé par cette entrée.

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 17 findings (constats des quatre couches, doublons regroupés avec leurs sources) — high 0, medium 4, low 8, false 2, maybe-false 3
- findings:
  - `[medium]` `[patch]` Câblage de `_embed_child` vers `measured_result` non testé : l'ancienne formule revient sans qu'un test échoue (verification-gap, blind) — test de `_embed_child`, runners reranker et fastembed couverts.
  - `[medium]` `[patch]` Changement de sens de `rss_added_mb` : bge-m3 et Qwen3-Embedding échouent désormais au budget de 600 Mo, sans que ce soit dit ni testé (blind, intent) — README, test des verdicts sur des pics réalistes, champ `rss_added_method`.
  - `[medium]` `[patch]` Banc Headroom encore mesuré après compression, pas au pic (blind, intent) — même définition partout.
  - `[medium]` `[patch]` Pic Linux (`ru_maxrss`) qui garde le maximum du parent à travers `exec`, et pic atteint avant la base (edge) — `VmHWM`, pic de la base retranché.
  - `[low]` `[patch]` « Lu avant la libération » : les compteurs de pic ne baissent jamais, le vrai correctif est la formule (blind) — textes corrigés, test factice retiré.
  - `[low]` `[patch]` `embed --only` avec un identifiant inconnu ou retiré : résultat vide et verdict muet (edge) — message et erreur.
  - `[low]` `[patch]` Test hors ligne : échec au lieu d'un saut sans litellm, dernière ligne JSON, adresses locales non spécifiées, variable masquée, pas de contrôle négatif (blind, edge) — corrigé, contrôle `gpt-4o` ajouté.
  - `[low]` `[patch]` Test « table toujours livrée » qui ne compare qu'une constante (blind) — encodage résolu et fichier vérifié.
  - `[low]` `[patch]` Test du banc fondé sur le texte source (blind, verification-gap) — faux `headroom` qui enregistre `model=`.
  - `[low]` `[patch]` README « 57 à 99 Mo selon le poste » trompeur, ligne trop courte (blind) — reformulé.
  - `[low]` `[reject]` Suivis « à vérifier sur PC » dans des entrées fermées (blind) — consigne de l'utilisateur ; repris dans le rapport de fin et le guide de test.
  - `[low]` `[reject]` Portée « les deux variantes » non notée comme décision par défaut (intent) — consignée dans le README du banc ; la variante naïve n'est qu'informative.
  - `[maybe-false]` `[reject]` `gpt-4` change aussi la fenêtre ou le coût vus par Headroom (blind) — banc réel « RETENU », compression du journal avec l'erreur gardée ; si vrai : low.
  - `[maybe-false]` `[defer]` 99 Mo sous Linux contre 57 sur le PC : la valeur Windows avec `gpt-4` reste à mesurer (intent) — si vrai : medium ; se tranche au banc `headroom` sur le PC.
  - `[maybe-false]` `[defer]` Vraies valeurs du pic sur le PC (granite ≈ +428, reranker ≈ +736) (intent) — si vrai : low ; se tranche au banc `embed` sur le PC.
  - `[false]` `[reject]` La spec annonce 80 Mo alors que le code garde 130 (blind, edge) — le journal des changements de la spec consigne la décision et la remplace ; corriger la spec n'est pas un correctif de code.
  - `[false]` `[reject]` Absence de résultat de référence pour la variante configurée sous Windows (intent) — hors du diff : c'est la vérification sur PC, notée.

## Design Notes

- F2, décision prise par défaut (le plan laissait « 130 ou 80 ») : 80 Mo, soit la mesure du PC cible (57) plus ≈ 40 % de marge ; la mesure Linux de la story 12 (130) incluait le repli réseau raté et un autre modèle de comptage.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert
- `uv run --extra compression pytest -q tests/test_compression.py` -- expected: tout vert, test hors ligne exécuté (non sauté)

## Auto Run Result

Status: done

**Résumé.** (F1) Headroom compte avec `gpt-4` (`cl100k_base`, présente dans le cache de litellm du PC cible) au lieu de `gpt-4o` (`o200k_base`, absente sur le PC, d'où la tentative vers `openaipublic.blob.core.windows.net`) ; le banc utilise le même modèle ; un test en sous-processus, avec les variables hors ligne, un cache réduit à `cl100k_base` et une garde qui enregistre, vérifie qu'aucune tentative réseau n'a lieu à l'import ni à la compression, avec un contrôle négatif (`gpt-4o` tente le réseau). (F2, décision prise par défaut) `cost_mb` gardé à 130 : avec `gpt-4`, Headroom ajoute 107 Mo au pic sous Linux, au-dessus des 80 envisagés. (F3) Le banc mesure la RSS ajoutée au pic (`VmHWM` sous Linux, `peak_wset` sous Windows) moins la base, pour l'embedding, le reranker, fastembed et Headroom ; les rapports portent `rss_added_method: "pic"` ; le README prévient que les verdicts d'embedding changeront sur le PC. (F4) `e5small_q8` retiré, avec sa raison ; `--only` d'un identifiant inconnu ou retiré le dit.

**Fichiers.** `src/wavestack/compression/headroom_adapter.py`, `env.py`, `wavestack.toml`, `src/wavestack/config.py`, `README.md`, `tools/bench/story12_bench.py`, `tools/bench/README.md`, `tests/test_compression.py`, `tests/test_story12_bench.py`, `deferred-work.md` (quatre entrées fermées).

**Revue.** 10 patchs (4 medium, 6 low), 2 différés (mesures sur PC), 5 rejetés. `followup_review_recommended: false`. Écart à la spec consigné dans son journal des changements (F2 : 130 au lieu de 80).

**Vérification.** `ruff check`, `ruff format --check` : OK ; `pytest -q` : 922 réussis, 7 sautés (sans l'extra) ; `uv run --extra compression pytest tests/test_compression.py tests/test_story12_bench.py` : tout vert, tests Headroom exécutés ; banc `headroom` réel : « RETENU » en variante configurée, sans tentative réseau.

**Risques résiduels (à vérifier sur PC).** Banc `headroom` sous Windows (« RETENU », mémoire ajoutée) ; banc `embed` au pic (verdicts de bge-m3 et Qwen3-Embedding) ; `cost_mb` à ajuster ensuite.
