---
title: 'Tests préalables : Headroom, embedding et reranking'
type: 'chore'
created: '2026-09-26'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
baseline_revision: '81dba76e0b239a7c18d6ff0628b0223299434492'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
warnings: []
deferred:
  - summary: >-
      Les chemins fastembed du banc (_fastembed_scores, reranker ajouté par add_custom_model) n'ont jamais tourné sur un vrai modèle.
    evidence: |-
      Seules les signatures de l'API fastembed 0.8.1 ont été vérifiées, dans un environnement jetable ; aucun modèle n'était téléchargeable (huggingface.co bloqué). Pour trancher : lancer `embed --download` sur le PC cible et vérifier que fe_minilm_multi et fe_mmarco_rerank finissent « mesuré ». En cas d'échec, les autres candidats continuent et le candidat passe en « erreur ».
    location: >-
      tools/bench/story12_bench.py:_fastembed_scores
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Les stories 15 (RAG), 16 (reranking) et 20 (compression) dépendent de trois choix non tranchés du Deferred du spine : Headroom (headroom-ai 0.38.0) est-il adoptable hors ligne, sans torch, dans le budget d'AD-8 et sous licence compatible ; quels modèles d'embedding et de reranking, chargés par llama-cpp-python (repli fastembed), servent le français. Sans verdict chiffré, ces stories construiraient sur une hypothèse.

**Approach:** Story d'investigation, aucune brique livrée. Un script de mesure reproductible (`tools/bench/story12_bench.py`), lancé par `uv run --with …` sans toucher `pyproject.toml`, mesure Headroom sous la garde réseau et banc-teste les candidats d'embedding et de reranking sur un mini jeu français. On le lance ici à titre indicatif (conteneur Linux 4 CPU, 15 Go, sans accès à huggingface.co), puis Anaël le relance sur le PC cible. Le verdict, qui sépare le mesuré du provisoire, met à jour la Stack et le Deferred du spine.

## Boundaries & Constraints

**Always:**
- Aucune dépendance ajoutée au projet : `pyproject.toml` et `uv.lock` restent inchangés, les paquets de mesure arrivent par `uv run --with` ou dans un environnement jetable du scratchpad.
- Chaque mesure tourne dans un processus enfant neuf, pour un RSS propre : la garde réseau du projet (`wavestack.net.guard.install`) est installée avant tout import tiers, les variables de proxy sont retirées comme dans `tests/conftest.py`, et un hook d'audit consigne chaque `socket.getaddrinfo` et `socket.connect` tentés.
- Sous Linux, si `strace` est présent, la variante configurée de Headroom tourne aussi sous `strace -f -e trace=connect`, pour voir les sockets du code natif qui échappent à la garde (plafond d'AD-15). Sans `strace`, le script le dit.
- Le verdict indique pour chaque chiffre s'il est mesuré (ici ou sur le PC cible) ou provisoire (carte de modèle, raisonnement).
- Les textes affichés par le script, le README et la story sont en français ; code et identifiants en anglais.
- Le jeu de mesure est court, non confidentiel et en français (NFR-11).

**Never:**
- Aucun `uv add`, aucune modification de `pyproject.toml` ou `uv.lock`, aucun code sous `src/`.
- Aucun test pytest qui importe headroom, llama-cpp, fastembed ou huggingface_hub, ni qui sorte sur le réseau : les tests ne couvrent que la logique pure du script.
- Aucun candidat sous licence non commerciale ou restrictive retenu (NFR-10) : jina-reranker-v2 (CC-BY-NC-4.0) et embeddinggemma (licence Gemma) sont écartés d'office.
- Pas de brique RAG, reranking ou compression : ce sont les stories 15, 16 et 20.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Headroom configuré | `headroom`, variables posées avant l'import, `kompress_model="disabled"` | Import et `compress()` sans tentative réseau ; RSS, temps et tokens avant/après par échantillon ; verdict « retenu » si les 5 critères passent | Une exception de `compress()` est consignée, le critère échoue |
| Headroom naïf | Aucune variable posée | Tentatives réseau listées (hôte, événement), bloquées par la garde | `NetworkBlocked` trouvé par `find_blocked` et consigné, pas de plantage |
| headroom-ai absent | `headroom` lancé sans `--with headroom-ai` | Message français « lancez avec `uv run --with headroom-ai==0.38.0` », code de sortie 2 | N/A |
| Embedding, modèles absents, sans réseau | `embed` sans `--download`, dossier vide | Chaque candidat marqué « absent », verdict « provisoire, mesure à faire » | N/A |
| Embedding, téléchargement | `embed --download` sur un poste avec réseau | Téléchargement des GGUF dans `--models-dir`, mesures RSS, temps et qualité par candidat, verdict | Échec d'un candidat consigné, les autres continuent |
| fastembed absent | `embed` sans `--with fastembed` | Repli marqué « non mesuré (fastembed absent) » | N/A |

</intent-contract>

## Code Map

- `src/wavestack/net/guard.py` -- `install(allowed_hosts)` et `find_blocked(exc)` : garde réutilisée telle quelle par le script ; la garde accepte l'hôte du proxy, d'où le retrait des variables de proxy (story 1e).
- `tests/conftest.py` -- modèle du retrait des variables de proxy et de la garde limitée à la boucle locale.
- `pyproject.toml` -- lecture seule ; ruff inclut `tools/` (seuls `.claude`, `_bmad`, `_bmad-output` sont exclus), pytest ne collecte que `tests/`.
- `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md` -- AD-8 (budget 4 Go, `LoadRegistry`), AD-15 (garde, règle d'adoption, variables HF), AD-22 (embedding et reranking par llama-cpp-python), `## Stack` (ligne headroom-ai), `## Deferred` (deux entrées à mettre à jour).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- reçoit la mesure sur PC cible restant à faire.
- Faits établis pendant la planification (environnement jetable du scratchpad) : headroom-ai 0.38.0 est une roue maturin (`_core.abi3.so`), Apache-2.0, sans torch ni onnxruntime en installation de base ; il tire litellm (MIT, sans dossier `enterprise/` dans la roue), tiktoken, tokenizers, huggingface-hub 1.33.0, boto3 et `ast-grep-cli` (exécutable natif de 50 Mo). litellm embarque les caches tiktoken `cl100k_base` et `o200k_base` dans `litellm/litellm_core_utils/tokenizers`. Balise télémétrie active par défaut (`HEADROOM_BEACON`), vérification de mise à jour vers PyPI, interrupteur global `HEADROOM_OFFLINE`. `CompressConfig.kompress_model="disabled"` coupe la compression ML (modèle HF).
- llama-cpp-python 0.3.35 (projet) expose `LLAMA_POOLING_TYPE_RANK`, mais `Llama.embed()` lit `n_embd` flottants par séquence, alors qu'un reranker n'en produit qu'un (`n_cls_out`) : le script lit le score par `llama_get_embeddings_seq(ctx, 0)[0]` après un `decode` de la paire.

## Tasks & Acceptance

**Execution:**
- `tools/bench/story12_bench.py` -- créer le script, avec les sous-commandes `headroom` et `embed`, `--json` pour une sortie machine, et des fonctions pures testables (jeu français, métriques recall@1 et MRR, classement des tentatives réseau, règles de verdict). Imports lourds seulement dans les fonctions -- reproductible sur le PC cible, testable sans dépendance.
- `tools/bench/README.md` -- README court en français : but, commandes exactes (`uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom`, `uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download`), lecture du verdict, limites (strace Linux seulement, mesure indicative hors PC cible).
- `tests/test_story12_bench.py` -- tester la logique pure : intégrité du jeu, métriques, verdicts Headroom et embedding sur des mesures fabriquées, classement des tentatives réseau, message quand headroom-ai manque.
- `_bmad-output/specs/spec-agentic-harness-training-demo/stories/12-tests-prealables-headroom-embedding-et-reranking.md` -- consigner le verdict chiffré (mesuré ici ou provisoire), le candidat recommandé et les « Hypothèses à valider ».
- `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md` -- mettre à jour la Stack (headroom-ai, embedding, reranker, fastembed en repli) et les deux entrées du Deferred, en marquant le mesuré et le provisoire.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- ajouter la mesure sur PC cible à faire avant la story 15.

**Acceptance Criteria:**
- Given headroom-ai 0.38.0 fourni par `uv run --with`, when on lance `story12_bench.py headroom` dans ce conteneur, then la sortie donne pour les variantes naïve et configurée : tentatives réseau (Python et, si `strace`, natives), présence de torch, onnxruntime et transformers, RSS en Mo (avant import, après import, après compression), temps, tokens avant/après par échantillon, licences de la fermeture des dépendances, puis un verdict chiffré.
- Given un poste sans modèles ni réseau, when on lance `story12_bench.py embed`, then le script finit sans erreur et imprime un verdict « provisoire, mesure sur PC cible à faire » avec la liste courte des candidats (licence, taille, dimension, français).
- Given la story terminée, when on lit la story 12 et le spine, then la Stack et le Deferred portent le verdict Headroom mesuré et le candidat d'embedding et de reranking recommandé, marqué provisoire, et `git diff` ne touche ni `pyproject.toml` ni `uv.lock`.

## Spec Change Log

## Review Triage Log

### 2026-09-26 — Review pass

Sans outil de sous-agent, l'agent principal a appliqué lui-même, sur le diff, les grilles des quatre relecteurs : chasseur à l'aveugle, cas limites, écarts de vérification, alignement sur l'intention. Ce n'est pas une revue indépendante.

- verdicts: 10 findings — high 0, medium 2, low 5, false 2, maybe-false 1
- findings:
  - `[medium]` `[patch]` L'échantillon JSON de Headroom était sérialisé avec `ensure_ascii` : chaque accent devenait `é`. Le nombre de tokens avant compression était gonflé, et le gain mesuré biaisé (−63 % au lieu de −57 %). — Corrigé : `json.dumps(..., ensure_ascii=False)`, banc relancé, chiffres mis à jour dans la story et le spine. Un test vérifie que chaque échantillon contient son repère.
  - `[medium]` `[patch]` Le point d'injection de la story 15 (`[rag.embedding]`) attend des valeurs précises, et un pooling lu dans le GGUF. Le banc imposait le pooling et ne pouvait donc pas confirmer les métadonnées. — Corrigé : le banc affiche `pooling_gguf`, et la story donne le bloc `[rag.embedding]` et les réglages du reranker pour la story 16.
  - `[low]` `[patch]` Le hook d'enregistrement notait `getaddrinfo(None)`, une résolution passive, comme l'hôte « None » : une fausse tentative réseau. — Corrigé : ces appels sont ignorés.
  - `[low]` `[patch]` Le second appel à `compress()`, qui mesure le temps à chaud, n'était pas protégé : une exception aurait fait planter l'enfant. — Corrigé : l'exception est consignée comme une erreur d'échantillon.
  - `[low]` `[patch]` Écart de vérification : la ligne « Headroom naïf » de la matrice (`NetworkBlocked` retrouvé derrière l'exception d'une bibliothèque) et `dependency_closure` n'avaient aucun test. — Corrigé : `test_blocked_attempt_is_found_behind_the_library_exception` et `test_dependency_closure_reads_installed_licences`.
  - `[low]` `[reject]` `_run_child` n'attrape pas `OSError` si `strace` ou `unshare` disparaît entre la vérification et le lancement. — Très improbable, et la correction ajouterait une branche.
  - `[low]` `[reject]` Le test de headroom-ai absent remplace `importlib.util.find_spec` pour tout le processus. — `monkeypatch` le rétablit à la fin du test ; aucun autre code ne tourne pendant ce test.
  - `[false]` `[reject]` « Une licence LGPL serait classée interdite par le mot GPL. » — Réfuté : `classify_license` teste d'abord LGPL et « Lesser » et renvoie « unknown » ; le test paramétré `LGPL-3.0-or-later` le couvre.
  - `[false]` `[reject]` « La résolution des dépendances avec le projet n'est pas dans le script. » — Réfuté comme défaut : l'intention demande un script de mesure du poste cible. La résolution a été vérifiée une fois, par `uv add` sur une copie du projet dans le scratchpad, et elle est consignée au verdict ; le projet ne doit pas être modifié.
  - `[maybe-false]` `[defer]` Les chemins fastembed du banc n'ont jamais tourné sur un vrai modèle. — Ce qui tranche : `embed --download` sur le PC cible. Entrée ajoutée au `deferred` du frontmatter.

## Design Notes

Critères de verdict Headroom, tous requis :
1. Réseau : aucune tentative, Python ou native, pendant l'import et `compress()` dans la variante configurée (`LITELLM_LOCAL_MODEL_COST_MAP=True`, `TIKTOKEN_CACHE_DIR` = cache fourni par litellm, `HEADROOM_OFFLINE=1`, `HEADROOM_BEACON=off`, `HEADROOM_UPDATE_CHECK=off`, `DO_NOT_TRACK=1`, `HF_HUB_OFFLINE=1`).
2. Sans torch : ni `torch`, ni `transformers`, ni `onnxruntime` chargés, ni installés par headroom-ai de base.
3. Budget : RSS ajouté par l'import et la compression ≤ 300 Mo, une part du budget de 4 Go d'AD-8 (seuil à valider).
4. Licence : toute la fermeture des dépendances est sous licence permissive ou copyleft faible par fichier (MIT, BSD, Apache, PSF, MPL-2.0) ; rien sous GPL, AGPL, NC ni BSL.
5. Règle d'adoption d'AD-15 : fonctionne hors ligne (vérifié aussi sous `unshare -rn` quand c'est possible).

Choix d'embedding : le plus petit GGUF qui se charge dans llama-cpp-python, avec recall@1 ≥ 0,75 sur le mini jeu et un RSS ajouté ≤ 600 Mo. Pour le reranker : la paire se charge avec `pooling_type=RANK`, garde ou améliore le MRR de l'embedding seul, avec un RSS ajouté ≤ 800 Mo. Sinon, repli fastembed.

## Verification

**Commands:**
- `uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom` -- expected: verdict chiffré imprimé, code 0
- `uv run python tools/bench/story12_bench.py embed` -- expected: verdict provisoire, code 0, sans réseau
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q` -- expected: tout vert
- `git diff --stat HEAD -- pyproject.toml uv.lock` -- expected: vide

## Verdict

Mesures du 2026-09-26, dans le conteneur de développement : Linux x86_64, 4 CPU, 15 Go, Python 3.13.12, sans accès à huggingface.co. Elles sont **indicatives** : le PC cible (HP EliteBook i5, 16 Go, Windows 11) reste à mesurer avec [le banc](../../../../tools/bench/README.md). Chaque chiffre porte sa source :

- **mesuré ici** : relevé par le banc dans ce conteneur ;
- **carte HF** : lu sur la carte du modèle le 2026-09-26, par le connecteur Hugging Face ;
- **provisoire** : raisonnement, rien n'a été mesuré.

### Headroom (headroom-ai 0.38.0) : RETENU, sous conditions

Les cinq critères passent. Commande : `uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom`.

| Critère | Résultat | Source |
| --- | --- | --- |
| Hors ligne sous la garde | Variante configurée : aucune tentative réseau, ni Python ni native (`strace -f -e trace=connect`), à l'import comme pendant `compress()`. Variante naïve : une seule tentative, le téléchargement de `o200k_base` vers `openaipublic.blob.core.windows.net`, bloqué par la garde, puis repli sur une estimation des tokens. Aucune balise ni vérification de mise à jour observée en mode bibliothèque (seul `MainThread` actif 2 s après la compression). | mesuré ici |
| Sans aucun réseau | Variante configurée sous `unshare -rn` : les 3 échantillons sont compressés. | mesuré ici |
| Sans torch | Ni torch, ni transformers, ni onnxruntime, chargés ou installés. Le routeur de contenu passe en « détection pure Python ». | mesuré ici |
| Budget AD-8 | RSS de 24 Mo avant l'import, 28 Mo après l'import, 154 Mo après la compression : **+130 Mo**, pic à 154 Mo. Variante naïve : +67 Mo, sans la table `o200k_base` de tiktoken. | mesuré ici |
| Licences (NFR-10) | 63 paquets dans la fermeture des dépendances, tous sous licence permissive : MIT, BSD, Apache-2.0, PSF, MPL-2.0 pour certifi et tqdm. headroom-ai est sous Apache-2.0. litellm est sous MIT : sa roue ne contient pas le dossier `enterprise/`. | mesuré ici |
| Résolution avec le projet | `uv add --optional compression headroom-ai==0.38.0`, essayé sur une copie du projet dans le scratchpad (sans llama-cpp-python, dont l'index abetlen est injoignable ici) : aucune version épinglée ne change, 40 paquets s'ajoutent (litellm, openai, boto3, botocore, aiohttp, tiktoken, tokenizers, huggingface-hub 1.33.0, hf-xet, ast-grep-cli…). L'environnement jetable complet pèse 285 Mo sur disque, dont litellm 91 Mo, l'exécutable `ast-grep` 50 Mo, headroom 32 Mo et botocore 29 Mo. | mesuré ici |

Compression, variante configurée (`kompress_model="disabled"`, tokens `o200k_base`) :

| Échantillon | Tokens avant → après | 1er appel | Appel suivant | Repère conservé |
| --- | --- | --- | --- | --- |
| `tool_result` JSON (120 enregistrements, une erreur) | 6 601 → 2 825 (−57 %) | 2,21 s | 0,018 s | oui |
| `tool_result` journal (150 lignes, un FATAL) | 3 940 → 218 (−94 %) | 0,035 s | 0,012 s | oui |
| Prose française (façon `rag_excerpt`) | 624 → 624 (0 %) | 0,004 s | 0,003 s | oui |

Le premier appel paie les imports paresseux et l'initialisation, une fois par processus.

**Conditions d'adoption pour la story 20 :**

1. Épingler exactement `headroom-ai==0.38.0`, en dépendance optionnelle. Le projet évolue vite et sa balise est active par défaut.
2. Poser avant tout import, dans `cli` comme le veut AD-15, les variables `LITELLM_LOCAL_MODEL_COST_MAP=True`, `HEADROOM_OFFLINE=1`, `HEADROOM_BEACON=off`, `HEADROOM_UPDATE_CHECK=off` et `DO_NOT_TRACK=1`, plus `TIKTOKEN_CACHE_DIR`, qui pointe vers le cache fourni par litellm (`litellm/litellm_core_utils/tokenizers`, qui contient `cl100k_base` et `o200k_base`).
3. Appeler avec `kompress_model="disabled"` : pas de modèle ML, pas de téléchargement, pas de torch.
4. Charger par le `LoadRegistry` en comptant environ 130 Mo.

**Conséquence pédagogique.** Sans Kompress, Headroom ne compresse que le structuré (JSON, journaux). La prose d'un `rag_excerpt` passe telle quelle. La brique de compression montrera donc son gain sur les `tool_result`.

### Embedding et reranking : verdict provisoire, mesure sur PC cible à faire

Aucun modèle n'a pu être téléchargé ici : le proxy refuse huggingface.co (`ProxyError('403 Forbidden')` pour les 7 candidats, message consigné par le banc). Le banc a quand même tourné de bout en bout sur deux GGUF BERT synthétiques, minuscules et aléatoires, créés dans le scratchpad avec le paquet `gguf`. Avec llama-cpp-python 0.3.35, le chargement en `pooling_type=CLS` et en `pooling_type=RANK` fonctionne, et la lecture du score par `llama_get_embeddings_seq` aussi. La qualité de ce test ne veut rien dire : il valide le code, pas le modèle.

| Candidat | Rôle | Licence | Taille | Dim. | Français | État llama.cpp | Statut |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **granite-embedding-107m-multilingual Q8_0** (bartowski, modèle IBM) | embedding | Apache-2.0 | 121 Mo | 384 | oui, dans les 12 langues de la carte | XLM-RoBERTa, quantifié avec llama.cpp principal | **recommandé** (provisoire) |
| multilingual-e5-small Q8_0 (cstr) | embedding | MIT | 132 Mo | 384 | oui | conversion faite pour CrispEmbed, compatibilité à vérifier | à mesurer |
| bge-m3 Q4_K_M (gpustack) | embedding | MIT | 438 Mo | 1024 | oui | pris en charge | alternative si la qualité manque |
| Qwen3-Embedding-0.6B Q8_0 (GGUF officiel) | embedding | Apache-2.0 | 639 Mo | 1024 | oui | pris en charge, pooling `last` | le plus lourd |
| **bge-reranker-v2-m3 Q4_K_M** (gpustack) | reranker | Apache-2.0 | 438 Mo | - | oui | pooling `RANK` ; code du banc validé sur GGUF synthétique | **recommandé** (provisoire) |
| fastembed + paraphrase-multilingual-MiniLM-L12-v2 | embedding (repli) | Apache-2.0 | 220 Mo | 384 | oui | ONNX | repli |
| fastembed + mmarco-mMiniLMv2-L12-H384-v1 (`add_custom_model`) | reranker (repli) | Apache-2.0 | 118 Mo | - | oui (mMARCO) | ONNX quint8 | repli |

Licences, tailles, dimensions et langues : carte HF. Le catalogue fastembed 0.8.1 a été lu dans un environnement jetable : mesuré ici.

Écartés d'office :

- **jina-reranker-v2-base-multilingual** : CC-BY-NC-4.0, non commercial. C'est pourtant le seul reranker multilingue du catalogue fastembed.
- **embeddinggemma-300m** : licence Gemma.
- **gte-multilingual-reranker-base** : son GGUF ne se lit qu'avec llama-box.
- **Qwen3-Reranker-0.6B** : son gabarit de reranking serait à reproduire à la main.

Faits établis pour les stories 15 et 16 :

- `Llama.embed()` ne convient pas à un reranker : il lit `n_embd` flottants par séquence, alors qu'un modèle en pooling `RANK` n'en écrit qu'un. Le banc lit le score par `llama_get_embeddings_seq(ctx, 0)[0]`, après un `decode` de la paire au format `[BOS] q [EOS] [SEP] d [EOS]`, celui de `format_rerank` de llama-server (mesuré ici, sur GGUF synthétique).
- fastembed 0.8.1 est sous Apache-2.0. Il tire onnxruntime 1.30, numpy, tokenizers et huggingface-hub, sans torch : 178 Mo d'environnement. Il charge hors ligne par `local_files_only` ou `HF_HUB_OFFLINE`, ce qui respecte la règle d'adoption d'AD-15 si `models/download.py` télécharge d'abord (mesuré ici).
- Budget provisoire, selon la formule d'AD-8 (taille du fichier plus une marge) : LLM 2B Q4_K_M ≈ 1,3 Go, embedding 121 Mo, reranker 438 Mo, Headroom 130 Mo. Le total reste sous 2,2 Go hors cache KV, dans les 4 Go.

**Valeurs pour `[rag.embedding]` (point d'injection de la story 15), provisoires :**

```toml
[rag.embedding]
id = "granite-embedding-107m-multilingual-q8_0"
backend = "llama_cpp"
label_fr = "Granite Embedding 107M multilingue (IBM, GGUF Q8_0)"
license = "Apache-2.0"
dims = 384                 # carte HF : hidden_size 384, 1_Pooling/config.json en CLS
max_tokens = 512           # carte HF : max_position_embeddings 514 (XLM-RoBERTa)
query_prefix = ""          # aucun préfixe sur la carte IBM
passage_prefix = ""
load_path = "embedding/granite-embedding-107m-multilingual-Q8_0.gguf"
files = [{ url = "https://huggingface.co/bartowski/granite-embedding-107m-multilingual-GGUF/resolve/main/granite-embedding-107m-multilingual-Q8_0.gguf", path = "embedding/granite-embedding-107m-multilingual-Q8_0.gguf", size = 121020096, sha256 = "" }]
```

Taille lue par le connecteur HF (`stat`). Le sha256 et la révision épinglée restent à relever au premier téléchargement sur le PC cible. `measured_rss_mb` est omis : rien n'a été mesuré. Le pooling CLS doit venir des métadonnées du GGUF, puisque l'adaptateur de la story 15 ne le passe pas. Le banc affiche la valeur déclarée dans le GGUF (`pooling_gguf`, 2 = cls) ; si elle manque, l'adaptateur devra passer `pooling_type` lui-même.

Pour la story 16, le reranker : `gpustack/bge-reranker-v2-m3-GGUF`, fichier `bge-reranker-v2-m3-Q4_K_M.gguf`, 438 376 864 octets, Apache-2.0, `pooling_type=LLAMA_POOLING_TYPE_RANK`, paire au format `[BOS] q [EOS] [SEP] d [EOS]`, score lu par `llama_get_embeddings_seq(ctx, 0)[0]`.

**Statut de la story.** `done`, avec la mention « verdict provisoire, mesure sur PC cible à faire » pour l'embedding et le reranking. Les stories 15, 16 et 20 s'appuient sur les candidats recommandés. Headroom n'est pas rédhibitoire.

## Hypothèses à valider

1. **Seuils de verdict.** Ils ont été choisis ici, faute de valeur dans le spine : Headroom ≤ 300 Mo ajoutés, embedding ≤ 600 Mo, reranker ≤ 800 Mo, recall@1 ≥ 0,75 sur le mini jeu. Anaël peut les resserrer.
2. **Mesures hors du PC cible.** Toutes les mesures sont indicatives. Sous Windows, le RSS peut différer. `strace` et `unshare` n'existent pas, donc le banc n'y voit que la garde Python, pas le code natif (plafond d'AD-15).
3. **Modèle d'embedding recommandé.** granite-107m multilingue suppose un GGUF communautaire (bartowski) fidèle au modèle IBM. Le pooling CLS est confirmé par `1_Pooling/config.json` du modèle IBM (carte HF), mais il n'est pas vérifié dans les métadonnées du GGUF. Le banc affiche `pooling_gguf` pour le confirmer.
4. **multilingual-e5-small.** Le GGUF de cstr vise CrispEmbed : llama.cpp pourrait refuser de le charger. Le banc le dira.
5. **Format de paire du reranker.** Il reproduit celui de llama-server. Idéalement, comparer une fois l'ordre obtenu avec `llama-server --rerank` sur le PC cible.
6. **Tokens de Headroom.** Ses comptes ne servent qu'à ses propres décisions : WaveStack compte les tokens lui-même. La table `o200k_base` coûte environ 60 Mo, soit l'écart de RSS entre la variante naïve et la variante configurée. La story 20 peut enregistrer un compteur par estimation pour économiser cette mémoire, si l'écart se confirme sur le PC cible.
7. **Prose non compressée.** Sans Kompress, Headroom laisse la prose telle quelle (0 % sur l'échantillon). La story 20 décide si le libellé de la brique le dit, ou si un compresseur maison minimal complète Headroom pour les `rag_excerpt`.
8. **AppLocker et WDAC.** headroom-ai ajoute deux binaires natifs non vérifiés : la bibliothèque Rust `_core` (`.pyd` sous Windows) et l'exécutable `ast-grep` (50 Mo). Ce dernier n'est pas lancé pendant une compression JSON : `strace -e trace=execve` ne montre aucun processus enfant (mesuré ici). Même risque que les DLL de llama.cpp : à vérifier en session pilote (Deferred du spine).
9. **Résolution des dépendances.** La compatibilité de headroom-ai avec le projet a été résolue sans llama-cpp-python (index abetlen injoignable ici). Les dépendances de llama-cpp-python (numpy, diskcache, jinja2, typing-extensions) ne recoupent celles de headroom que sur jinja2 et typing-extensions, déjà présents dans le projet. À confirmer par un `uv lock` réel au moment de la story 20.
10. **Déroulé du palier.** Le spine plaçait ce test en première story du palier 2 ; il arrive après la story 11, ce qui ne change rien au verdict.
11. **Écarts de processus.** Cette exécution sans humain n'avait pas d'outil de sous-agent. Le plan, l'implémentation et la revue ont été faits par l'agent principal, sans relecteurs indépendants ; la revue a appliqué les grilles des quatre relecteurs du workflow.

## Auto Run Result

Status: done — verdict provisoire, mesure sur PC cible à faire (embedding et reranking)

**Résumé.** Story d'investigation, sans brique livrée. Headroom est **retenu** sur mesures, prises dans le conteneur de développement :

- aucune tentative réseau, Python ou native ;
- fonctionne sans aucun réseau ;
- pas de torch ;
- +130 Mo de RSS ;
- 63 paquets sous licence permissive.

Embedding et reranking : **verdict provisoire**. granite-embedding-107m-multilingual Q8_0 et bge-reranker-v2-m3 Q4_K_M sont recommandés, avec fastembed en repli. Faute d'accès à huggingface.co, aucun vrai modèle n'a été mesuré ; le code llama.cpp du banc est validé sur des GGUF synthétiques.

**Fichiers modifiés :**

- `tools/bench/story12_bench.py` : banc reproductible, sous-commandes `headroom` et `embed`, lancé par `uv run --with`, processus enfants sous la garde réseau.
- `tools/bench/README.md` : mode d'emploi en français.
- `tests/test_story12_bench.py` : 35 tests de la logique pure (jeu, métriques, licences, tentatives réseau, strace, verdicts, lignes de la matrice).
- `_bmad-output/specs/spec-agentic-harness-training-demo/stories/12-tests-prealables-headroom-embedding-et-reranking.md` : spec, verdict chiffré, hypothèses à valider.
- `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md` : Stack (headroom-ai, embedding, reranker, repli fastembed) et Deferred (deux entrées tranchées ou marquées provisoires).
- `_bmad-output/implementation-artifacts/deferred-work.md` : mesure sur PC cible à faire avant la story 15.

**Revue.** 5 corrections appliquées (2 medium, 3 low), 1 point différé (fastembed jamais exécuté sur un vrai modèle, gravité medium non vérifiée). Points rejetés :

- `OSError` de `_run_child` : improbable, et la correction ajouterait une branche ;
- `monkeypatch` global dans un test : rétabli à la fin du test ;
- LGPL classée interdite : réfuté par le code et par un test ;
- résolution des dépendances absente du script : faite hors du script, volontairement.

**Relecture de suivi recommandée : oui.** Deux corrections de gravité medium ont été appliquées. Risque non vérifié : les chemins du banc sur de vrais modèles (fastembed, e5-small, bge-m3, Qwen3 et le reranker sur de vrais poids) n'ont jamais tourné. Le premier `embed --download` sur le PC cible sert de vérification, et ses chiffres doivent remplacer le verdict provisoire.

**Vérification :**

- `uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom` : verdict RETENU, code 0 ; JSON conservé dans le scratchpad de la session.
- `uv run python tools/bench/story12_bench.py embed` : verdict provisoire, code 0, aucun réseau.
- `embed --download` : les 7 échecs `ProxyError('403 Forbidden')` sont consignés, et le verdict reste provisoire.
- `embed` sur GGUF synthétiques : pooling CLS et RANK exécutés, et le pooling du GGUF lu.
- `uv run ruff check .` et `uv run ruff format --check .` : aucun écart.
- `uv run pytest -q` : 418 tests passés, 3 sautés, 2 désélectionnés (avant la fusion de la branche d'intégration).
- `git diff --stat HEAD -- pyproject.toml uv.lock` : vide.

**Risques résiduels :**

- mesures hors du PC cible ;
- seuils de verdict posés par la story ;
- binaires natifs de headroom-ai face à AppLocker ;
- prose non compressée par Headroom sans Kompress ;
- résolution des dépendances vérifiée sans llama-cpp-python.
