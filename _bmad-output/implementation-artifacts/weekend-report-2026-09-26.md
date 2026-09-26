# Rapport du week-end : palier 2 (stories 12 à 21), 26 septembre 2026

Branche `claude/dreamy-cerf-gdjtee`, 57 commits d'avance sur `origin/main`.

## 1. Résumé

- Les dix stories du palier 2 (12 à 21) sont livrées (`done`), ainsi que quatre correctifs transverses : harnais E2E, anomalies A1 à A4, nettoyage des fusions et courses du flux SSE.
- Le programme compte maintenant six modules (5 h 15) et trois scénarios métier : SOC, IAM et Souveraineté.
- Aucun vrai modèle n'a tourné : embedding, reranker, Qwen3.5, Ollama et llama-server n'ont été testés qu'avec des doublures. Le verdict embedding et reranking reste **provisoire**.
- Six décisions d'architecture ou de comportement ont été prises par défaut et attendent ta validation (section 3). Deux amendements du spine sont marqués « à valider » : AD-4 et AD-21.
- État final : pytest 770 réussis (5 sautés) ; E2E 327 vérifications, vertes sur 3 parcours complets de suite ; ruff propre. Tout ce qui dépend du PC cible reste à faire (section 4).

**Méthode.** Le travail a été fait dans un conteneur cloud sans réseau externe : huggingface.co, les API cloud et les sites web étaient bloqués, seul PyPI répondait. Les tests ont donc utilisé des doublures (faux moteur, faux embedder, faux reranker, GGUF synthétiques) et un faux serveur compatible OpenAI, joués par des parcours Playwright (`tools/e2e/`). Chaque story a été implémentée par `bmad-build-auto`, puis relue par 4 relecteurs indépendants (aveugle, cas limites, lacunes de vérification, alignement d'intention) et corrigée. Deux exceptions : la story 21 n'a eu que trois relecteurs, et la story 12 comme les correctifs transverses n'ont eu qu'une auto-revue. `uv.lock` a été complété à la main pour sqlite-vec et headroom-ai (plus 39 dépendances), car l'index abetlen de llama-cpp-python était injoignable.

## 2. Livrables

| Story | Livré | Statut |
|---|---|---|
| 12 Tests préalables | Banc `tools/bench/story12_bench.py`. Headroom **retenu** : hors ligne, sans torch, +130 Mo, licences OK. Embedding granite-107m Q8_0 et reranker bge-v2-m3 Q4_K_M recommandés, **provisoires** | done, verdict provisoire ; suivi conseillé |
| 13 Raisonnement | Brique `reasoning` : `enable_thinking` en local, `reasoning.on/off` en cloud, réserve de sortie 1 536. Option « Afficher le raisonnement » et bloc dans Contexte LLM | done |
| 14 Mémoire globale | Brique `global_memory` (`memory.json`), méta-outil `remember`, action forcée « Écrire en mémoire », tiroir d'édition, restauration de la démo | done |
| 15 RAG simple | Corpus fictif « Exemplia » (8 docs, 29 extraits), index sqlite-vec, « Télécharger » et « Construire l'index » depuis la carte, `scripts/build_rag_index.py`, `LoadRegistry` étendu | done ; suivi conseillé |
| 16 Reranking | Sous-option de la carte RAG : 8 candidats, 3 gardés, étape « Reranking » (ordre avant et après), téléchargement du reranker | done |
| 17 Modèle à chaud | Sélecteur `model-picker` + « Charger », contrôle du budget avant libération, retour arrière si échec, chronomètre, « Modèle : … » et « Comparer » par modèle | done |
| 18 Serveur local | Ollama (`raw`) et llama-server (`/completion`, `/tokenize`) choisissables ; « transparence réduite » ; `keep_alive: 0` ; mémoire servie comptée | done ; suivi conseillé |
| 19 Sous-agent | Brique `subagent` et méta-outil `delegate` : contexte `sub{n}`, 4 appels au plus, hooks, économie de tokens affichée, second robot dans le schéma | done |
| 20 Compression | Brique Headroom (extra `compression`) sur `tool_result` et `rag_excerpt`, étape tracée avant/après, journal de démonstration | done ; suivi conseillé |
| 21 Programme palier 2 | Six modules dans l'ordre de FR-38, cumul avec deux exceptions, `restore_memory`, scénarios `soc`, `iam`, `sovereignty`, `scripts/snapshot_mcp.py`, `tests/test_program.py` | done |
| Harnais E2E | `tools/e2e/` : faux OpenAI, faux llama-server et faux Ollama, Playwright, captures | done |
| Anomalies A1 à A4 | Relance détectée (`instance_id` et rechargement), zone Réseau du schéma, en-tête de Contexte LLM, pastille de réinitialisation | done |
| Nettoyage transverse | Diagnostic : rejeu sans effets de bord, clics « Choisir » plus perdus. Textes « relancez » rendus exacts. Les 25 scénarios E2E passent seuls | done |
| Courses du flux SSE | Abonnement avant l'instantané et dédoublonnage par `seq` ; `isLive` côté page ; un envoi n'est plus jamais ignoré en silence | done |

**Documents de planification modifiés.**
- Spine : AD-2 (`model_load_*`, `active_model`), AD-3 (changement à chaud), AD-8 (coût et budget), Stack et Deferred (verdicts de la story 12).
- Deux amendements marqués « à valider » : AD-4 (`transform_context`) et AD-21 (reranker).
- EXPERIENCE.md : `model-picker`, changement en cours, avertissement cloud dans la barre haute.
- SPEC.md : une ligne sur le changement de modèle sans relance.

## 3. Décisions à prendre

Chaque décision donne le défaut appliqué, l'alternative et l'endroit où changer. Les six premières touchent à l'architecture ou au comportement visible en séance.

### Priorité 1 : architecture et comportement en séance

**D1. AD-4 et AD-22 : quand compresser** (story 20, H-1)
- Par défaut : chaque texte passe une seule fois, avant le premier appel qui le lit. Les réponses d'outils arrivées en cours de tour sont donc compressées, et l'historique garde le texte compressé (H-2).
- Alternative : lecture stricte, compression seulement avant le premier appel du tour. Seuls les extraits RAG et les actions forcées seraient compressés, et la brique perdrait son cas principal (UJ-7).
- Où changer : spine AD-4 (ligne « à valider ») ; `AppSession._transform_context` dans `src/wavestack/session/app_session.py` ; `.memlog.md`.

**D2. AD-21 : reranker absent** (story 16, hypothèse 1)
- Par défaut : seule la sous-option « Reranking » devient indisponible. Le RAG simple continue, et l'étape « Recherche RAG » dit que le reranking n'est pas appliqué.
- Alternative : lettre initiale d'AD-21, toute la brique RAG indisponible sans le reranker.
- Où changer : spine AD-21 ; `_load_rag` et `_rerank_refresh` dans `app_session.py`.

**D3. Disparition de « prêt sans modèle »** (story 18, hypothèse 2)
- Par défaut : quand seuls des serveurs (Ollama, llama-server) sont trouvés, le contrôle `model` bloque avec « Choisissez un modèle servi ». Un modèle servi n'est jamais choisi d'office ; un choix mémorisé est repris s'il est encore servi.
- Alternative : revenir à « prêt sans modèle », ou choisir d'office quand un seul modèle est servi (Ollama chargerait alors un modèle sans ton accord).
- Où changer : `src/wavestack/session/diagnostic.py` (`_check_model_locked`) ; `tests/test_cli_diagnostic.py`.

**D4. Budget mémoire de 4 096 Mo** (story 17, repris par les stories 15, 16, 18 et 20)
- Par défaut : `[memory] budget_mb = 4096` (en Mio, soit le plafond de NFR-2 et non la cible de 2 à 3 Go), marge `load_margin_mb = 256`. Le budget est contrôlé à chaque changement à chaud et à chaque chargement de composant, **pas au lancement** (C2) : le coût y est seulement enregistré.
- Alternative : budget à 3 072 (la cible), ou refus chiffré au lancement avec renvoi au diagnostic.
- Où changer : `wavestack.toml [memory]` ou `settings.json` ; chemin de démarrage dans `app_session.py` et `models/load_registry.py`.

**D5. Exceptions au cumul du programme** (story 21, H2 et H5)
- Par défaut : le raisonnement n'est reconduit dans aucun module après le module 1 ; le RAG est éteint dans `mcp_full` et rallumé par `mcp_lazy`. Le premier scénario de chaque module restaure la mémoire globale de démonstration (`restore_memory`), alors qu'EXPERIENCE.md la supposait intouchée.
- Alternative : cumul strict (risque de déborder la fenêtre de 4 096 tokens), ou aucune restauration de la mémoire.
- Où changer : en-tête et champs de `content/scenarios.yaml` ; `tests/test_program.py` ; consignes des scénarios.

**D6. SOC : H5 réservé aux outils réseau** (story 21, H6)
- Par défaut : le garde-fou sur l'inventaire des comptes à privilèges reste un blocage H1. La leçon « escalader vers un humain » passe par la consigne.
- Alternative (V2) : H1 en validation humaine, avec un nouveau hook ou une option de H1 et une carte de validation pour un fichier local. Cela change le contrat de FR-27.
- Où changer : scénario `soc` de `content/scenarios.yaml` ; hooks.

### Priorité 2 : réglages et écarts mineurs, à confirmer au test manuel

| # | Sujet | Défaut appliqué | Alternative | Où changer |
|---|---|---|---|---|
| D7 | Échec de la recherche RAG (story 15, hyp. 7) | Le tour continue sans extraits | Lettre d'AD-16 : le tour se termine en erreur | `app_session.py` (recherche RAG) |
| D8 | Aperçu de la jauge avec RAG (story 15, hyp. 9 et 35) | Compte les 3 extraits les plus longs de l'index | Aperçu sans extraits (l'autre phrase d'AD-9) | `app_session.py` (aperçu) ; spine AD-9 |
| D9 | Renvoi du raisonnement à Mistral (story 13, H6) | `resend = false`, ce qui s'écarte d'AD-20 (« vrai pour Mistral ») | `resend = true` si Mistral accepte les blocs `thinking` renvoyés ; sinon amender AD-20 | Préréglage `mistral` de `wavestack.toml`, ou `settings.json` |
| D10 | Brique voulue mais indisponible (story 13, H4) | Dessinée en style indisponible dans le schéma | « Absente du schéma », comme le dit EXPERIENCE.md | `renderSchema` dans `app.js` |
| D11 | Taille de la mémoire globale (story 14, H3) | 20 entrées de 300 caractères, soit environ 1 550 tokens (≈ 60 % de l'espace utile avec le raisonnement) | Descendre `MAX_CHARS` à 200 | `src/wavestack/memory.py` (`MAX_CHARS`, `MAX_ENTRIES`) |
| D12 | Tiroir de la mémoire (story 14, H1 et H7) | Aucun ajout depuis le tiroir ; « Tout effacer » sans confirmation | Ajout direct depuis le tiroir ; confirmation avant d'effacer | `app.js` ; `POST /api/intentions/memory` |
| D13 | Nombre de candidats reranqués (story 16, hyp. 3) | 8 candidats, 3 gardés | Moins de candidats si l'étape dépasse NFR-1 | `wavestack.toml [rag] rerank_candidates`, `top_k` |
| D14 | Seuil et prose en compression (story 20, H-3 ; story 12, hyp. 7) | `min_chars = 300`, `cost_mb = 130`. La prose passe telle quelle (0 %), et la carte le dit | Compresseur maison minimal pour les `rag_excerpt` | `wavestack.toml [compression]` |
| D15 | Outils et état du sous-agent (story 19, H-1, H-5, H-22) | `tools = ["read_file", "fetch_page"]`, limités aux outils actifs ; pas de préservation d'état ; pas de raisonnement dans le sous-agent | Autre liste d'outils ; `save_state` après mesure | `wavestack.toml [subagent]` ; `contributes_to` de la brique Raisonnement |
| D16 | Seuils du banc (story 12, hyp. 1) | Headroom ≤ 300 Mo, embedding ≤ 600 Mo, reranker ≤ 800 Mo, recall@1 ≥ 0,75 | Des seuils plus serrés | `tools/bench/story12_bench.py` |
| D17 | Place des scénarios métier (story 21, H1) | Dans `transverse`, groupe « Transverses et métier », hors cumul | Un champ `business` dédié | `content/scenarios.yaml` |
| D18 | Budget exprimé en Go dans les refus (story 18, hyp. 10) | Un seul format pour tous les refus : « environ 5,0 Go ; budget de 4,0 Go » | Mo, comme le prévoyait la matrice de la story 18 | Message du `LoadRegistry` |

## 4. Checklist de test sur le PC cible

Prérequis : le réseau ouvert vers PyPI, `abetlen.github.io`, `huggingface.co`, `*.hf.co`, `learn.microsoft.com` et `mcp.data.gouv.fr`, et le fichier Qwen3.5-2B Q4_K_M amont en place.

### A. Installation et verrou
- [ ] `git pull`, puis `uv lock` : `git diff uv.lock` doit être vide (il valide les entrées écrites à la main pour sqlite-vec et headroom-ai). Si le verrou change, committer la version produite par `uv lock`.
- [ ] `uv lock --check`, puis `uv sync --extra compression`.
- [ ] `uv run pytest -q` : tout doit être vert (les tests `model` sont sautés).
- [ ] AppLocker et WDAC : vérifier que `headroom\_core*.pyd` et `ast-grep.exe` ne sont pas bloqués. Au lancement, la carte Compression doit être disponible.

### B. Bancs et instantanés (avant de lancer WaveStack)
- [ ] `uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom --json` : reporter la sortie dans la story 12, avec le RSS ajouté sous Windows (≈ 130 Mo attendus) et l'absence de tentative réseau.
- [ ] `uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download --json` (≈ 2,1 Go) : recall@1, MRR, RSS et `pooling_gguf` (2 = CLS) par candidat. Confirmer ou remplacer granite-107m et bge-reranker-v2-m3, et vérifier que les replis fastembed finissent « mesuré ».
- [ ] `uv run python scripts/snapshot_mcp.py` : versionner `content/mcp_snapshots/`, puis `uv run pytest -s tests/test_program.py -k fits`.

### C. Modèles RAG (dans WaveStack)
- [ ] `uv run wavestack` avec Qwen3.5-2B. Sur la carte RAG, la raison affichée ne doit pas être « sqlite-vec ne se charge pas » : c'est le test de sqlite-vec sous Windows.
- [ ] « Télécharger le modèle d'embedding », puis relever le sha256 dans l'effet `model_download` du journal. Le reporter dans `[rag.embedding] files[].sha256`, et remplacer `resolve/main` par le commit du dépôt bartowski.
- [ ] « Construire l'index » : noter la durée, la mémoire, et qu'aucun verrou de fichier ne gêne. Puis `uv run python -m pytest -m model tests/test_rag.py`.
- [ ] Cocher « Reranking », puis « Télécharger le modèle de reranking » : reporter le sha256 et le commit dans `[rag.reranker]`. Mesurer le RSS ajouté (≤ 800 Mo) et le reporter dans `measured_rss_mb`. Puis `uv run python -m pytest -m model tests/test_rag_rerank.py`.

### D. Modèle à chaud et serveurs locaux
- [ ] Sonder Qwen3.5-2B et 4B, puis relire `rss_bytes` et `kv_bytes_per_token` dans `settings.json` (`probed_models`). Tenter le passage de 2B à 4B : il ne doit pas être refusé à tort (surestimation du cache KV d'un modèle hybride).
- [ ] Lancer `llama-server -m …\Qwen3.5-2B-Q4_K_M.gguf --port 8080 -np 1` : le choisir, faire un tour avec `get_datetime`, vérifier que les ids reçus correspondent au texte rendu et que le robot est dessiné hors du cadre Harnais.
- [ ] Lancer `ollama serve` : choisir un modèle, faire un tour, puis noter toute alerte « transparence réduite » avec les deux comptes qu'elle cite. Essayer un blob `qwen35` : s'il est refusé, la raison doit renvoyer vers llama-server et le modèle précédent doit rester actif.
- [ ] `ollama ps` doit être vide après un changement de modèle et après la fermeture de WaveStack. Un modèle déjà chargé par un autre programme doit rester chargé.
- [ ] « Arrêter » pendant qu'Ollama charge un gros modèle : la main doit revenir en moins d'une seconde.
- [ ] Facultatif, pour D9 : déclarer `resend = true` pour `mistral`, puis jouer un tour avec outil et un second tour. Un code 400 signifie que Mistral refuse.

### E. Programme, module par module
Pour chaque scénario, relever trois mesures :
- **jauge** : la jauge avant envoi, sur 3 584 tokens utiles (3 072 avec le raisonnement) ;
- **NFR-1** : le premier token de chaque appel (< 10 s en LLM nu, < 30 s pour la configuration la plus chargée) ;
- **NFR-2** : le RSS de WaveStack dans le Gestionnaire des tâches (≤ 4 Go, cible 2 à 3 Go).

- [ ] **Module 1** : LLM nu (NFR-1 < 10 s) ; `reasoning` (repli dans la Vue humain, réserve de 1 536 tokens, longueur du raisonnement face à cette réserve) ; `short_memory` ; `system_prompt` ; `global_memory` (tiroir, « Écrire en mémoire », mémoire pleine face à la fenêtre, pour D11).
- [ ] **Module 2** : `native_tools`, `network_tools`.
- [ ] **Module 3** : `rag` (consigne « éteindre, envoyer, rallumer, rejouer » ; durée de l'étape « Recherche RAG ») ; `rag_rerank` (durée des 8 passes ; au moins un extrait doit changer de rang sur le prompt de l'hôtel à Paris, sinon choisir un autre prompt).
- [ ] **Module 4** : `mcp_full` : c'est le point critique. Il mesurait 3 018 / 3 584 sans la mémoire globale à la story 10b, avec un tour de 109 s. S'il déborde, deux choix : `expects_overflow` et une nouvelle consigne, ou la mémoire globale éteinte dans ce scénario. `mcp_lazy` (RAG rallumé) : s'il déborde, y éteindre le RAG.
- [ ] **Module 5** : `skills`, `caveman`, `hooks`, avec la jauge et NFR-1.
- [ ] **Module 6** : `subagent` (le modèle délègue-t-il au lieu de lire le guide lui-même ? le contexte `sub{n}` tient-il dans 4 096 − 512 ? y a-t-il un `prefix_not_reused` ?) ; `compression` (tient-il sans compression ? gain affiché ; aucun appel à un outil « Retrieve more » inexistant).
- [ ] **Transverses et métier** : `soc` (H1 bloque l'inventaire, pour D6) ; `iam` (taille des résultats de `microsoft_docs_search` face à la fenêtre : si le débordement est systématique, passer en lazy loading ou ajouter la compression) ; `sovereignty` (données sortantes de chaque appel dans Orchestration).
- [ ] **NFR-2** : toutes briques actives (LLM, embedding, reranker, Headroom), noter le RSS maximal. L'estimation est de moins de 2,2 Go hors cache KV.
- [ ] Trancher les décisions D1 à D6 et reporter les choix dans les stories et le spine (retirer les mentions « à valider »).

## 5. Points de vigilance et risques restants

Sélection dans `deferred-work.md`, par gravité.

**Pourraient bloquer une séance**
1. **sqlite-vec sous Windows** : il n'a été vérifié que sous Linux. S'il ne se charge pas, toute la brique RAG est indisponible (modules 3, 4 à 6 et scénarios métier).
2. **AppLocker et WDAC** : `_core.pyd` et `ast-grep` de headroom-ai sont des binaires non signés, tout comme les DLL de llama.cpp.
3. **`uv.lock` écrit à la main** (sqlite-vec, headroom-ai et 39 dépendances) : il reste à confirmer par un `uv lock` réel.
4. **Fenêtre et latence réelles** : `mcp_full` avec la mémoire globale, IAM avec jusqu'à dix extraits Microsoft Learn, NFR-1 jamais mesurée pour le programme réordonné. Les chiffres actuels sont des estimations (4 caractères par token, facteur 1,3), et les fixtures MCP ne sont que plausibles.

**Moyens**
5. Aucun vrai modèle d'embedding ni de reranking n'a tourné : le pooling CLS du GGUF granite, la latence, la pertinence et les chemins fastembed du banc restent inconnus.
6. Intégrité des modèles : URL sur `resolve/main` et sha256 vides pour l'embedding comme pour le reranker.
7. L'estimation du cache KV peut refuser à tort un Qwen3.5 hybride, et le budget n'est pas contrôlé au lancement (C2).
8. Les champs réels de llama-server et d'Ollama ne sont vérifiés que sur des doublures : `/props`, `with_pieces`, `prompt_eval_count` avec le cache, `vocab_only` sur `qwen35`, coupure de la socket sous Windows.
9. Comportement d'un SLM réel : délégation spontanée, taille du contexte du sous-agent, raisonnement plus long que la réserve de 1 536 tokens.
10. Le renvoi du raisonnement (`resend = true`) n'a jamais été essayé contre un vrai fournisseur (format `field`, Mistral).
11. Le front n'a pas de banc de test JS. Le parcours E2E couvre l'essentiel, mais la vérification du champ désactivé au rejeu ne voit la régression que sur un journal long.

**Faibles, ou reportés en V2**
12. « Arrêter » pendant l'établissement de la connexion d'un téléchargement attend jusqu'à 10 s ; `compress()` n'a pas de borne de temps (2,2 s mesurées au pire).
13. AD-9 : l'avertissement en direct quand `tools/list` s'écarte de l'instantané n'est pas réalisé. IAM et Souveraineté n'ont pas de repli hors ligne, seulement l'échec expliqué.
14. Écarts d'architecture documentés : `transform_context` n'est pas un point d'accroche de hook (AD-13) ; `contributes_to` n'est pas généralisé au contexte `sub{n}` (AD-11 et AD-12).
15. Critère 3 de la story 13 (Raisonnement redevenu effectif après un changement de modèle) sans test dédié ; `created_at` absent du tiroir ; zone locale du schéma serrée à 1 366 px dans le cas le plus chargé.
16. Reste du palier 1 : le message des 429 de Mistral quand le compte n'a aucun quota actif. Il faut décider si on lève l'interdiction de lire les en-têtes `x-ratelimit-*`.

## 6. Relancer les vérifications

```bash
uv lock --check --offline                # verrou cohérent
uv sync --extra compression              # l'extra couvre les tests Headroom
uv run ruff check . && uv run ruff format --check .
uv run pytest -q                          # attendu : 770 réussis, 5 sautés
uv run python -m pytest -m model tests/test_rag.py tests/test_rag_rerank.py   # PC cible, modèles en place

# Parcours de bout en bout (faux modèle, Chromium sans affichage)
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py                  # attendu : 327 vérifications, 0 échec
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only rag rag_rerank --keep
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only compression --no-headroom

# Bancs (PC cible)
uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom --json
uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download --json
uv run python scripts/snapshot_mcp.py && uv run pytest -s tests/test_program.py -k fits
```

Le parcours E2E a besoin d'un Chromium de la révision de Playwright 1.56 (`PLAYWRIGHT_BROWSERS_PATH`). Chaque scénario se lance seul avec `--only <nom>`.

## Fichiers clés

- Stories : `_bmad-output/specs/spec-agentic-harness-training-demo/stories/12-…` à `21-…` (sections « Hypothèses à valider », Review Triage Log, Auto Run Result)
- Correctifs : `_bmad-output/implementation-artifacts/spec-e2e-palier-1-corrections.md`, `spec-palier-2-nettoyage-transverse.md`, `spec-correctif-courses-flux-evenements.md`, `test-e2e-palier-1-cloud.md`
- Reports : `_bmad-output/implementation-artifacts/deferred-work.md`
- Architecture : `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md` (AD-4 et AD-21 « à valider »)
- UX et spec : `_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md`, `_bmad-output/specs/spec-agentic-harness-training-demo/SPEC.md`, `.memlog.md`
- Réglages : `wavestack.toml` (`[memory]`, `[rag]`, `[rag.embedding]`, `[rag.reranker]`, `[compression]`, `[subagent]`, `[model_servers]`, préréglage `mistral`)
- Programme : `content/scenarios.yaml`, `tests/test_program.py`, `scripts/snapshot_mcp.py`, `scripts/build_rag_index.py`
- Outillage : `tools/bench/story12_bench.py` et `README.md`, `tools/e2e/run_e2e.py` et `README.md`
- Code central : `src/wavestack/session/app_session.py`, `src/wavestack/session/diagnostic.py`, `src/wavestack/models/load_registry.py`, `src/wavestack/models/servers.py`, `src/wavestack/memory.py`
- Documentation utilisateur : `README.md` (programme, changer de modèle, serveurs locaux, RAG, reranking, compression)
