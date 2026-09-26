---
title: 'Corpus de démonstration et RAG simple'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_revision: '7b8504e4635ea98c78e29af29018b35e294573e9'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
warnings: ['oversized']
deferred:
  - summary: >-
      Le chargement de l'extension sqlite-vec par le Python de uv sous Windows n'a pas été vérifié.
    evidence: |-
      Vérifié ici seulement (Linux, Python 3.13 système). À trancher sur le PC cible : la carte RAG ne doit pas dire « sqlite-vec ne se charge pas ».
    location: >-
      src/wavestack/rag/index.py:load_vec
    severity: medium (unverified)
  - summary: >-
      Le pooling CLS du GGUF granite n'est pas forcé par l'adaptateur : il doit venir des métadonnées du fichier ; une sonde au chargement refuse, en français, un modèle qui rend un vecteur par token.
    evidence: |-
      Aucun vrai modèle téléchargeable ici. À trancher par `uv run python -m pytest -m model tests/test_rag.py` sur le PC cible, modèle en place.
    location: >-
      src/wavestack/models/embedding.py:LlamaCppEmbedder
    severity: medium (unverified)
  - summary: >-
      L'entrée sqlite-vec de uv.lock a été écrite à la main, l'index abetlen étant injoignable.
    evidence: |-
      `uv lock --check --offline` et `uv sync --locked` passent. À confirmer par `uv lock` sur un poste qui joint l'index abetlen (aucun écart attendu).
    location: >-
      uv.lock
    severity: low
  - summary: >-
      La latence de la recherche RAG avec le vrai modèle sur CPU n'est pas mesurée (NFR-1).
    evidence: |-
      À mesurer au test manuel : durée de l'étape « Recherche RAG » dans Orchestration.
    location: >-
      src/wavestack/session/app_session.py:_rag_search
    severity: medium (unverified)
  - summary: >-
      L'URL du modèle d'embedding vise resolve/main et son sha256 n'est pas renseigné.
    evidence: |-
      Le connecteur Hugging Face ne donne ni l'oid LFS ni le commit. Le premier téléchargement sur le PC cible trace le sha256 (effet model_download) : le recopier dans files[].sha256 et épingler l'URL sur le commit (deferred-work.md).
    location: >-
      wavestack.toml:[rag.embedding]
    severity: medium
  - summary: >-
      « Arrêter » pendant l'établissement de la connexion d'un téléchargement n'agit qu'au bout du délai de connexion (10 s).
    evidence: |-
      httpx n'interrompt pas un connect depuis un autre fil ; pendant l'attente des données, la réponse est fermée et l'arrêt est immédiat (test).
    location: >-
      src/wavestack/models/download.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** Le palier 2 n'a ni corpus ni recherche : WaveStack ne peut pas montrer que « le RAG, ce n'est pas le modèle qui sait, c'est le harnais qui cherche » (UJ-5, CAP-17, CAP-18). Le type `rag_excerpt` existe dans `SegmentKind` sans producteur, `file.rag_index` est réservé sans nœud, et aucun composant lourd ne passe encore par un budget mémoire (AD-8).

**Approach:** Un corpus français fictif sous `content/corpus/`, découpé et indexé hors ligne par `scripts/build_rag_index.py` dans `data/rag_index.sqlite` (sqlite-vec), avec l'identifiant du modèle d'embedding retenu par la story 12. Une brique `rag` charge ce modèle par un `LoadRegistry` minimal, cherche à chaque tour avec le message de l'utilisateur par le port `Retriever.search` (AD-22), place les extraits en segments `rag_excerpt` du message de l'utilisateur (AD-4) et trace une étape « Recherche RAG » dépliable : requête, extraits, score, position. Sans ses fichiers, la brique est indisponible, avec la raison « modèle absent » et l'action « Télécharger » (AD-21).

## Boundaries & Constraints

**Always:**
- **Précondition et point d'injection (story 12).** Avant toute ligne de code, lire le verdict de la story 12 (`stories/12-*.md`, et la Stack du spine qu'elle met à jour). Si la story 12 n'est pas `done`, ou si elle ne retient aucun modèle d'embedding, HALT `blocked` avec la condition `verdict de la story 12 absent`. Sinon, recopier ses valeurs dans la seule section `[rag.embedding]` de `wavestack.toml` (champs en Design Notes) ; aucun autre fichier ne nomme le modèle. N'écrire que l'adaptateur du `backend` retenu ; `fastembed` n'est ajouté (`uv add`, version du verdict) que si le verdict le retient.
- **Corpus** (NFR-10, NFR-11) : 8 documents Markdown en français, textes originaux et fictifs sur l'organisation fictive « Exemplia » : mots de passe, télétravail, classification de l'information, incidents de sécurité, conservation des données personnelles, usage de l'IA générative, déplacements et notes de frais, sauvegardes. Chacun compte de 250 à 450 mots et porte des faits précis (chiffres, délais) absents des autres. `content/rag.yaml` les déclare (`id`, `title_fr`, `file`) avec la mention « Textes fictifs rédigés pour WaveStack » et les textes de la brique (intro, format d'extrait, placement, libellé du fichier d'index).
- **Découpage**, une seule fonction pour le script et les tests : paragraphes séparés par une ligne vide, fusionnés tant qu'ils tiennent dans `[rag] chunk_max_chars` (700). Un paragraphe plus long est coupé en fin de phrase, sinon à la limite. Chaque extrait garde `doc_id`, `title_fr` et sa position dans le document.
- **Index** (`[rag] index_path`, par défaut `data/rag_index.sqlite`, relatif à la racine du dépôt) : table `meta` (`embedding_model_id`, `dims`, `chunk_max_chars`, nombre d'extraits, `built_at`), table `chunks` (`id`, `doc_id`, `title_fr`, `position`, `text`) et table virtuelle `vec0` (`float[dims] distance_metric=cosine`). Le script embarque les passages avec le même adaptateur et leur préfixe. Il écrit dans un fichier temporaire puis le remplace, refuse un corpus vide et installe la garde réseau limitée à la boucle locale.
- **Recherche.** `Retriever.search(query) → list[Excerpt{position, chunk_id, doc_id, title_fr, text, score}]` rend les `[rag] top_k` (3) plus proches, sans seuil. `score = 1 − distance cosinus`, arrondi à 3 décimales, par ordre décroissant ; `position` part de 1. La requête est le message de l'utilisateur du tour (celui du tour d'origine en rejeu), avec le préfixe de requête, tronquée au `max_tokens` de l'embedding.
- **Brique `rag`** (AD-12) : catégorie `context`, aucune capacité exigée, `network: false`, `contributes_to: [main]`. Elle a un composant `rag.retriever` (`local_process`, arêtes vers `core.harness` et `file.rag_index`). Le nœud `file.rag_index` est dessiné comme `file.demo_dir`, avec un libellé de `content/` et une infobulle qui donne le chemin, le nombre d'extraits et l'identifiant du modèle. La puce du harnais porte 📚, et son infobulle précise « modèle d'embedding {id}, processus local ».
- **Disponibilité**, au point unique `_availability`, dans cet ordre. Chaque raison dit en français quoi, pourquoi et quelle action :
  1. contenu ou `[rag.embedding]` invalide ;
  2. sqlite-vec non chargeable ;
  3. index absent (« lancez `uv run python scripts/build_rag_index.py` ») ;
  4. index d'un autre modèle ou d'autres dimensions (les deux identifiants nommés, « reconstruisez l'index ») ;
  5. fichiers du modèle absents : « modèle absent », `BrickState.download` proposé, chemin de copie manuelle dans `models_dir()` ;
  6. chargement en cours ;
  7. chargement refusé par le budget, ou en échec.

  Les métadonnées de l'index sont lues au démarrage et après un téléchargement, jamais à chaque émission.
- **Chargement** (AD-8). Le modèle d'embedding se charge sur le thread de travail à l'activation : `set_brick`, lancement d'un scénario, réinitialisation, fin d'un téléchargement avec la brique voulue. Il se libère (`close()`) à la désactivation et à `close()`. Il est chargé et compté même quand le modèle actif est cloud. L'état de session ne change pas : un tour lancé avant la fin du chargement tourne sans RAG.
- **`LoadRegistry` minimal** (`models/load_registry.py`) :
  - budget : `[memory] budget_mb` (4 096) ;
  - mesure : RSS psutil de WaveStack et de ses processus enfants ;
  - coût : `measured_rss_mb` du verdict s'il est présent, sinon la taille des fichiers plus `[memory] load_margin_mb` (128) ;
  - refus quand mesure + coût > budget, avec un message chiffré : « Mémoire insuffisante pour charger {composant} : WaveStack occupe {x} Mo, il en faut environ {y} de plus, au-delà du budget de {b} Mo. Désactivez une brique ou relevez `memory.budget_mb` dans settings.json. »

  Seul l'embedding y passe dans cette story.
- **Tour.** La recherche a lieu une fois par tour, dans le contexte `main` seul, après `on_user_message` et les actions armées, avant le premier appel. Son étape `{turn}.main.s{n}` porte la brique `rag`, le composant `rag.retriever`, et `actor` et `trigger` valent `harness`. Elle émet une paire (AD-2) :
  - `rag_search_started{query, top_k, phase_label: « Recherche dans le corpus… »}` ;
  - `rag_search_ended{status: ok|error, excerpts, placement_fr, error_fr, duration_ms}`.

  `placement_fr` vient de `content/rag.yaml` : « Dans le message de l'utilisateur de ce tour, avant la question ». Un dépassement causé surtout par les extraits a sa cause : « Cause : les extraits RAG … désactivez la brique RAG ou baissez `rag.top_k` ».
- **Contexte** (AD-4). Le message de l'utilisateur du tour contient, dans l'ordre : `hook_injection`, puis un `rag_excerpt` d'introduction (`intro_fr`), puis un `rag_excerpt` par extrait au format `excerpt_format_fr` (« Extrait {position} — {title_fr} :\n{text} »), puis `user_message`. Ces segments portent la brique `rag` et le composant `rag.retriever`. Les extraits n'entrent pas dans l'historique (`Exchange` inchangé), et chaque tour cherche à nouveau. En mode chat, les mêmes parties vont dans le corps JSON.
- **Aperçu** (AD-9). Brique effective, l'aperçu place les `top_k` extraits les plus longs de l'index (en caractères), au même format : ils sont comptés à leur maximum déclaré.
- **Téléchargement.** L'intention `download_model{target: "rag_embedding"}` est de classe (b) : 409 hors `idle`, avec la raison ; 404 pour une cible inconnue ; 409 « rien à télécharger » si les fichiers sont présents.
  - L'état `download` porte `reason_fr` : « Téléchargement du modèle d'embedding : {p} % ({x} / {y} Mo) », réémis une fois par seconde au plus. « Arrêter » l'annule : `stop` accepte l'état `download`.
  - `models/download.py` télécharge chaque fichier en flux, avec le client de `net` : `origin = download`, `turn_id = null`, redirections suivies saut par saut et revérifiées comme dans `tools/network.py`. Il écrit `*.part`, vérifie la taille, et le sha256 s'il est déclaré, puis renomme le fichier.
  - Tout échec supprime le `.part`, émet `harness_error` (cause, puis « copiez le fichier à la main dans {dossier} ») et rend l'état `idle`.
  - Un succès relit les métadonnées de l'index, charge le modèle si la brique est voulue, puis émet `bricks_changed`, `architecture_changed` et un aperçu.
- **Front** (AD-1 : mise en forme seule) :
  - **Rail d'étapes.** La ligne « 📚 Recherche RAG » a pour acteur le harnais. Son chiffre vaut « {n} extraits · {durée} », ou « erreur » (ligne gardée dépliée). Le détail montre la requête (`pre`), le placement, puis la liste rang / document / score (« 0,82 ») / texte repliable. Un clic sur un extrait sélectionne `rag.retriever` (CAP-4). L'indicateur de travail reprend `phase_label`.
  - **Carte de brique.** Le bouton « Télécharger le modèle d'embedding (≈ {taille} Mo) » apparaît avec `BrickState.download` ; il est désactivé hors `idle`, avec la raison. Pendant le téléchargement, la carte affiche `session_state.reason_fr` et « Arrêter le téléchargement ».
  - **Schéma.** `rag.retriever` s'allume, cible `file.rag_index`, pendant la recherche.
  - **Journal.** Les deux `kind` y ont un résumé d'une ligne.
- **Scénario** (AD-19, FR-38). Le module « RAG » (30 min) s'ajoute en fin de `program`, avec le scénario `rag` en tête.
  - Briques : celles des modules 1 à 4 (`short_memory, system_prompt, tools, mcp, skills, hooks`), plus `rag`, avec `mcp_lazy: true` et `hooks: [h1, h2]`.
  - Consigne : envoyer une question brique RAG éteinte, puis l'activer, rejouer et ouvrir « Comparer » ; regarder l'étape et le fichier d'index dans le schéma.
  - Prompts : « Combien de caractères doit compter au minimum un mot de passe chez Exemplia ? », plus un second prompt dont la réponse est dans un seul autre document.
- Tout texte affiché ou pédagogique est en français, sous `content/`, sauf les messages chiffrés composés en Python. Le code et les identifiants sont en anglais. Dépendance : `uv add "sqlite-vec==0.1.9"` (MIT/Apache-2.0). Outils : `ruff` et `pytest` ; aucun test ne touche au réseau.

**Never:**
- reranking (story 16), compression (story 20), RAG avancé ou indexation des documents de l'utilisateur (V2) ;
- seuil de score, reformulation de la requête par l'historique ;
- téléchargement du LLM au diagnostic, dépendance `huggingface_hub`, embedding dans la session de diagnostic ;
- LLM passé par le `LoadRegistry` (story 17) ;
- identifiant de modèle ailleurs que dans `[rag.embedding]` ;
- nouveau `SegmentKind` ;
- toute modification de `stories.yaml` ou d'une autre story.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu | Erreur |
|---|---|---|---|
| Question couverte | `rag` effective, « mot de passe » | Étape `ok`, 3 extraits triés par score, le premier du document « mots de passe » ; `context_rendered` : intro et 3 `rag_excerpt` entre `hook_injection` et `user_message` | — |
| Hors corpus | « Quelle est la capitale du Pérou ? » | 3 extraits aux scores faibles, envoyés quand même | — |
| Index absent | `rag` voulue | indisponible « index absent… », ni étape ni segment | — |
| Index d'un autre modèle | `meta.embedding_model_id` ≠ `[rag.embedding].id` | indisponible, les deux identifiants dans la raison | — |
| Modèle absent | fichiers manquants | indisponible « modèle absent », `download` proposé | — |
| Budget dépassé | mesure + coût > budget | indisponible, raison chiffrée ; rien de chargé | — |
| Recherche en échec | l'embedder lève | `harness_error`, `rag_search_ended{status: error}` ; le tour continue sans extraits | AD-16 |
| Désactivation | `rag` éteinte | `close()` de l'embedder ; tour suivant sans étape | — |
| Rejeu | t1 avec RAG, rejeu | nouvelle recherche ; t1 sans extrait dans l'historique | — |
| Modèle cloud | cloud actif + `rag` | embedding local chargé, extraits dans le corps JSON, nœud local | — |
| Téléchargement réussi | 302 vers `*.hf.co` puis 200 | `outbound_request{origin: download}` par saut, fichier renommé, brique chargée | — |
| Téléchargement en échec | hôte refusé, taille fausse, « Arrêter » | `.part` supprimé, `harness_error`, retour à `idle` | — |
| Hors `idle` | tour en cours | `download_model` renvoie 409 avec la raison | — |

</intent-contract>

## Code Map

- `src/wavestack/bricks/registry.py` : `RESERVED_NODES`, dont `file.rag_index` (L79) ; liste `BRICKS` (L96-209), où déclarer `rag` après `hooks`. Le contrat est dans `bricks/contract.py` (`BrickDeclaration`, `Component`) ; le contenu d'une carte suit le modèle de `content/bricks/skills.yaml`.
- `src/wavestack/context/segments.py:24` : `RAG_EXCERPT` existe déjà, avec son libellé dans `content/labels/segment_kinds.yaml`. `context/render.py:42` : `PART_SEPARATOR` joint les `Part` d'un même message, donc l'intro et chaque extrait sont des `Part` distinctes (aucun changement du rendu).
- `src/wavestack/session/app_session.py` :
  - `TurnState` L251-268 : ajouter `rag_excerpts: tuple[str, ...] = ()`, avec l'intro et les extraits déjà formatés ;
  - `__init__` L315-417 : injecter `embedder_factory` (tests), sur le modèle de `engine_factory` ; état RAG (métadonnées de l'index, embedder, raison de chargement) et registre ;
  - `_load_content` L943-1023 : bloc `try` pour `content/rag.yaml`, `[rag.embedding]` et les métadonnées de l'index, sur le modèle de L958-970 ;
  - `_emit_architecture` : dictionnaire `files` L547-558, où ajouter `file.rag_index` (brique `rag`) ; ajouter `detail_fr` à la puce `rag.retriever` ;
  - `_emit_bricks` L732-782 : champ `download` de `rag` ;
  - `_availability` L1031-1053 : raisons RAG, après `_content_errors` ;
  - `_OVERFLOW_CAUSES_FR` L138-157 : cause `RAG_EXCERPT`, après `USER_MESSAGE` (les égalités désignent le message) ;
  - `_messages` L1249-1252 : les parties RAG vont entre `hook_injection` et `user_message` ;
  - `_emit_preview` L1376-1391 : extraits de remplacement, comme `_preview_injection` L1393 ;
  - `set_brick` L1467-1486 et `_reconfigure` L1966-1992 : soumettre `_sync_rag` au thread de travail ;
  - `stop` L2001-2013 : accepter `download` ;
  - `close` L794-804 : libérer le registre ;
  - `_turn` : la recherche va juste après `_consume_armed` (L2111-2113), `step += 1`, et `state = replace(state, rag_excerpts=…)` comme l'injection de H3 (L2056-2057).
- `src/wavestack/trace/catalog.py` : `RagSearchStartedPayload`, `RagSearchEndedPayload` (avec `RagExcerpt`) et leurs entrées dans `PAYLOAD_MODELS` (L371-404) ; `DownloadOffer{target, label_fr}` et `BrickState.download` (L250-270). `ArchitectureNode.kind` suffit tel quel (`brick`, `file`).
- `src/wavestack/config.py` : sur le modèle de `CloudModel`/`_Strict` (L55-137), un modèle `EmbeddingModel` et ses accesseurs `rag_embedding()`, `rag_top_k`, `rag_chunk_max_chars`, `rag_index_path()` (chemin relatif résolu par `repo_root()`, L40), `memory_budget_mb`, `load_margin_mb`. `models_dir()` est en L385.
- `src/wavestack/net/factory.py:55-72` : `create_client(transport=…)`, avec `MockTransport` en test. Le suivi des redirections revérifiées saut par saut est à reprendre de `tools/network.py:25-45`.
- `src/wavestack/models/engine.py:94-98` : le style d'import paresseux de `llama_cpp`, que seul `models` importe. `session/diagnostic.py:26,51` : usage de psutil, inchangé.
- `src/wavestack/web/app.py` : route `POST /api/intentions/download_model`, sur le modèle de `clear_conversation` (L414-421 : `SendRefused` → 409) et de `scenario` (L423-430 : `KeyError` → 404).
- `src/wavestack/web/static/app.js` :
  - `applyEnvelope` L146-378 : cas `rag_search_*`, à côté de `tool_started` L267 ;
  - `turnRows` L1948-2124 : branche `rag` ;
  - `renderBricks` L491-603 : bouton sous `brick-reason` (L544) ;
  - `schemaActivity` L3133-3156 ;
  - `BRICK_ICONS` L3017 ;
  - `eventSummary` L2832.
- `content/scenarios.yaml` : `program` (L8-21) et le schéma `scenarios.py` (sans changement) ; `tests/test_scenarios.py` lance chaque scénario.
- Tests : `tests/fake_engine.py` (`booted_session` L85), `tests/conftest.py` (garde réseau L14, dossier de données isolé L28 : `settings.json` y surcharge `rag.index_path`).

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock`, `wavestack.toml` : vérifier la précondition (story 12), puis `uv add "sqlite-vec==0.1.9"`, et `fastembed` si le verdict le retient. Remplir `wavestack.toml` : `[rag]` (`index_path`, `top_k`, `chunk_max_chars`), `[rag.embedding]` (verdict) et `[memory]` (`budget_mb`, `load_margin_mb`).
- [x] `content/corpus/*.md` (8), `content/rag.yaml`, `content/bricks/rag.yaml` : corpus fictif et textes de la brique, en français.
- [x] `src/wavestack/config.py` : `EmbeddingModel` et accesseurs ; une section invalide rend la brique indisponible, sans plantage.
- [x] `src/wavestack/models/embedding.py` (nouveau) : port `Embedder{model_id, dims, embed_queries, embed_passages, close}`, vecteurs normalisés, et l'adaptateur du `backend` retenu.
- [x] `src/wavestack/models/load_registry.py` (nouveau) : `LoadRegistry`, avec une mesure injectable.
- [x] `src/wavestack/models/download.py` (nouveau) : `download_files(files, dest, cancel, on_progress)`.
- [x] `src/wavestack/rag/` (nouveau) :
  - `corpus.py` : chargement et découpage ;
  - `index.py` : écriture et lecture sqlite-vec, `meta` ;
  - `retriever.py` : `Retriever`, `SqliteVecRetriever`, `Excerpt`.
- [x] `scripts/build_rag_index.py` (nouveau) : `--model PATH` facultatif, sinon le chemin de `[rag.embedding]` ; garde réseau en boucle locale ; résumé en français (documents, extraits, dimensions, durée).
- [x] `src/wavestack/bricks/registry.py`, `trace/catalog.py`, `session/app_session.py`, `web/app.py` : brique, événements, disponibilité, chargement, recherche, contexte, aperçu, téléchargement, cause de dépassement.
- [x] `src/wavestack/web/static/app.js` et `app.css` : ligne et détail du rail, bouton et progression sur la carte, activité du schéma, icône, journal.
- [x] `content/scenarios.yaml` : module « RAG » et scénario `rag`.
- [x] `tests/fake_embedder.py` (nouveau) : sac de mots haché en 64 dimensions, normalisé, déterministe.
- [x] `tests/test_rag.py` (nouveau) : une ligne de la matrice par test, hors téléchargement, sur un index temporaire construit avec le vrai code de `rag/` et `FakeEmbedder` ; découpage ; refus chiffré du `LoadRegistry` (mesure injectée) ; libération à la désactivation ; aperçu ; mode chat (moteur cloud factice des tests de la story 11) ; schéma. Un test compare l'index livré aux extraits du corpus, et il est sauté si l'index est absent. Un test marqué `model` utilise le vrai modèle.
- [x] `tests/test_rag_download.py` (nouveau) : lignes « Téléchargement » et « Hors idle », avec `MockTransport` ; routes 404 et 409.
- [x] `data/rag_index.sqlite` : si les fichiers du modèle retenu sont sur le poste d'implémentation, construire et committer l'index. Sinon, le consigner sous Auto Run Result (index à construire sur le poste de référence) et laisser la brique « index absent ».

**Acceptance Criteria:**
- Given un tour avec la brique `rag` effective, when la page est rechargée, then le rail montre toujours l'étape « Recherche RAG », avec sa requête, ses extraits, leurs scores et leur placement (projection du journal, AD-1).
- Given la brique `rag` voulue mais indisponible, when on lit `/api/state`, then la carte `rag` porte `available: false` et la raison de la matrice, et `download` n'est présent que pour « modèle absent ».
- Given la brique activée puis désactivée, when le thread de travail a traité les deux intentions, then l'embedder a été chargé une fois puis fermé, et le `LoadRegistry` ne le compte plus.
- Given la brique effective et aucun tour, when l'aperçu est émis, then il contient l'intro et `top_k` segments `rag_excerpt`, qui sont les extraits les plus longs de l'index.
- Given le scénario `rag` lancé, when on lit `/api/state`, then les briques voulues sont celles des modules 1 à 4 plus `rag`, en lazy loading, avec les hooks H1 et H2.
- Given `uv run ruff check .`, `uv run ruff format --check .` et `uv run python -m pytest`, when ils s'exécutent sans réseau, then tout passe.

## Spec Change Log

## Review Triage Log

### 2026-09-26 — Review pass
Revue faite par l'agent d'implémentation lui-même, sans sous-agent (aucun outil de sous-agent dans cette exécution, sur instruction de l'appelant) ; une revue indépendante suivra.
- verdicts: 9 findings — high 0, medium 2, low 3, false 0, maybe-false 4
- findings:
  - `[medium]` `[patch]` Le GGUF d'embedding, rangé sous `models/embedding/`, était découvert comme modèle de conversation : sondé à chaque lancement, « Modèle incompatible » (vu au test de bout en bout, scénario de relance). — Corrigé : `discovery.discover` écarte les fichiers de `[rag.embedding]` ; test `test_the_embedding_model_is_never_offered_as_a_chat_model`.
  - `[medium]` `[patch]` `net/factory.py` levait `RequestNotRead` au traçage d'une redirection vers un hôte autorisé : le téléchargement (huggingface.co → *.hf.co) échouait, et les outils réseau auraient échoué de même. — Corrigé : `_body()` lit le flux d'une requête de redirection ; test de téléchargement avec 302.
  - `[low]` `[patch]` Un échec de téléchargement, hors tour, n'apparaissait que dans le journal des événements. — Corrigé : `harness_error` porté par la brique `rag`, affiché sur la carte.
  - `[low]` `[patch]` La synchronisation de l'embedding réémettait cartes, schéma et aperçu à chaque reconfiguration, contre la règle « un seul de chaque » de la story 10. — Corrigé : émission seulement si un modèle est chargé ou libéré.
  - `[low]` `[reject]` La progression affiche « 0 / 0 Mo » pour un fichier de moins d'un Mo. — Cosmétique, jamais vu avec le vrai fichier (115 Mo) ; corriger ajouterait une branche d'unité.
  - `[maybe-false]` `[defer]` Le Python de `uv` sous Windows charge-t-il l'extension sqlite-vec ? — À trancher sur le PC cible ; sinon la brique dit « sqlite-vec ne se charge pas ».
  - `[maybe-false]` `[defer]` Le GGUF bartowski de granite déclare-t-il le pooling CLS dans ses métadonnées ? L'adaptateur ne le force pas. — À trancher par le test marqué `model` sur le PC cible.
  - `[maybe-false]` `[defer]` L'entrée `sqlite-vec` de `uv.lock`, écrite à la main, est-elle identique à ce que produirait `uv lock` ? — `uv lock --check --offline` passe ; à confirmer par `uv lock` avec accès à l'index abetlen.
  - `[maybe-false]` `[defer]` La latence de la recherche (embedding de la question par le vrai modèle, CPU) reste-t-elle négligeable devant l'appel au modèle (NFR-1) ? — À mesurer au test manuel.

### 2026-09-26 — Revue indépendante (4 relecteurs séparés), triage du coordinateur
Tous les points ont été vérifiés dans le code puis appliqués ; aucun n'a été écarté comme faux. Deux sont appliqués en partie, pour une raison externe consignée dans deferred-work.md.
- `[medium]` `[patch]` Installation neuve sans chemin (index et modèle absents) — « Télécharger » dès que le modèle manque, puis « Construire l'index » (état `index_build`, progression, « Arrêter », effet `rag_index_write`) ; `--download` pour le script ; README et scénario à jour. Tests `test_fresh_install_*`, `test_build_*` ; parcours E2E installation neuve → téléchargement (échec expliqué puis réussite) → construction → recherche.
- `[medium]` `[patch]` Identité du modèle chargé — taille (fichier d'une autre taille = absent), sha256 déclaré vérifié au chargement, taille et sha256 du fichier dans `meta`, `load_path` ∈ `files`, `--model` contrôlé. Tests `test_another_file_*`, `test_an_index_built_from_another_file_*`, `test_a_declared_sha256_*`, `test_load_path_*`, `test_script_refuses_*`.
- `[medium]` `[patch]` Index périmé non détecté — empreinte du corpus et `chunk_max_chars` comparés. Test `test_stale_index_*`.
- `[medium]` `[patch]` Index remplacé pendant la séance — relu à la recherche (horodatage du fichier), brique indisponible s'il ne convient plus. Test `test_an_index_replaced_*`.
- `[medium]` `[patch]` Brique éteinte pendant le chargement — le modèle chargé est fermé et le registre libéré. Test `test_switching_the_brick_off_while_it_loads_*`.
- `[medium]` `[patch]` Refus de budget jamais retenté — retenté après un changement de modèle. Test `test_a_budget_refusal_is_retried_*`.
- `[medium]` `[patch]` Pooling absent non détecté — sonde au chargement, `ValueError` en français. Test `test_a_gguf_without_pooling_*`.
- `[medium]` `[patch]` « Arrêter » sans effet pendant l'attente des données — `StopToken` ferme la réponse ; cancel vérifié avant chaque fichier ; délai de connexion ramené à 10 s. Test `test_stop_acts_at_once_*`. Partiel : pendant la connexion elle-même, l'arrêt attend le délai (deferred-work.md).
- `[medium]` `[patch]` Chemins Windows (`\x`, `C:x`) acceptés — refusés sous les deux conventions. Test `test_paths_outside_*`.
- `[low]` `[patch]` Texte « Le score va de 0 à 1 » faux — score borné, NaN et vecteur nul gérés. Tests `test_score_*`, `test_a_question_without_any_vector_*` ; regex E2E `[01],\d\d`.
- `[low]` `[patch]` Avertissement fictif indexé, titre absent du passage — commentaire HTML ignoré au découpage, passage = titre + texte ; mots vides du faux embedder ajustés.
- `[low]` `[patch]` Découverte : tout `models/embedding/` exclu des modèles de conversation. Test `test_the_whole_embedding_folder_*`.
- `[low]` `[patch]` `.tmp` laissé si l'écriture de l'index échoue — supprimé ; `data/*.tmp` ignoré par git. Test `test_a_failed_write_*`.
- `[low]` `[patch]` Corps vide tracé pour une redirection asynchrone — marqueur « (corps non relu : redirection) » ; POST redirigé tracé avec son corps. Test `test_a_redirected_post_*`.
- `[low]` `[patch]` Script : erreurs non rattrapées, pas de test — messages français et codes de sortie ; tests `test_script_*` (FakeEmbedder).
- `[low]` `[patch]` Corpus : « au-delà de ce seuil » ambigu — « au-delà de 4 heures et demie de train ».
- `[low]` `[patch]` Tests figés (« 0 / 0 Mo », « 31 extraits ») — regex, et nombre lu par `read_meta` dans l'E2E.
- `[low]` `[patch]` Retriever : deux requêtes et extension rechargée à chaque recherche — une requête avec JOIN, connexion ouverte au chargement, fermée à la libération.
- `[low]` `[patch]` Backticks Markdown dans les textes d'interface — notation `[section] clé` sans backticks ; `chunk_max_chars` et la reconstruction cités.
- `[low]` `[patch]` Limite du RAG simple non dite — paragraphe dans content/bricks/rag.yaml (requête = message brut, relance sans contexte).
- `[low]` `[patch]` Notice d'échec restée affichée — la carte ne la montre plus quand elle est disponible ou n'offre plus d'action.
- `[low]` `[patch]` Faux serveur : extraits retirés par `rsplit` — retirés jusqu'à la fin du dernier extrait (textes du corpus découpé).
- `[low]` `[patch]` Unités : Mo décimaux pour les fichiers (README, carte, progression).
- `[medium]` `[defer]` Intégrité : URL épinglée sur un commit et sha256 — non lisibles par le connecteur Hugging Face ; le premier téléchargement trace le sha256 (effet `model_download`) pour le reporter (deferred-work.md).
- `[medium]` `[defer]` AD-9 : adéquation du scénario (extraits comptés au maximum déclaré) — au test manuel ; écart de l'aperçu documenté (hypothèse 35).
- `[low]` `[patch]` Tests ajoutés (verification-gap) : scénario `rag` puis `reset()` (modèle fermé, registre libéré) ; fabrique qui lève (carte indisponible, registre libre, un `harness_error`, chargement terminé) ; sqlite-vec qui ne se charge pas (session construite, raison « sqlite-vec ») ; index non SQLite (« illisible »).

Constat hors story pendant le parcours E2E complet : la page de diagnostic (story 17) affiche parfois son repli « Le modèle choisi est actif. » avant « {modèle} est actif. » quand le journal rejoué est long ; le parcours accepte les deux textes, le correctif est consigné dans deferred-work.md.

## Design Notes

**Point d'injection du verdict de la story 12**, unique, dans `wavestack.toml` (validé par `EmbeddingModel`, `extra = "forbid"`) :

```toml
[rag.embedding]
id = "<identifiant du verdict>"        # écrit dans meta.embedding_model_id
backend = "llama_cpp"                  # ou "fastembed", selon le verdict
label_fr = "<nom affiché>"
license = "<licence du verdict>"
dims = 0                               # dimensions du verdict
max_tokens = 0                         # longueur maximale d'entrée du verdict
query_prefix = ""                      # préfixes du verdict (ex. e5 : "query: ", "passage: ")
passage_prefix = ""
load_path = "embedding/<fichier ou dossier>"   # relatif à models_dir()
measured_rss_mb = 0                    # facultatif : RSS mesuré par la story 12, ligne omise sinon
files = [{ url = "https://huggingface.co/<dépôt>/resolve/<révision>/<fichier>", path = "embedding/<fichier>", size = 0, sha256 = "" }]  # sha256 vide = non vérifié
```

Les valeurs `0` et `<…>` ci-dessus ne sont pas des défauts : la tâche 1 les remplace toutes par celles du verdict, et `EmbeddingModel` refuse `dims`, `max_tokens` ou `size` nuls. Avec `llama_cpp`, l'adaptateur ouvre `Llama(model_path, embedding=True, n_ctx=max_tokens, verbose=False)` et normalise les vecteurs. Avec `fastembed`, il ouvre le dossier local (`cache_dir`, `local_files_only=True`), sans jamais télécharger lui-même (règle d'adoption d'AD-15) : `files` liste alors chacun des fichiers du dossier.

**Extraits hors de l'historique.** Garder 3 × ~200 tokens par tour saturerait une fenêtre de 4 096 tokens en quelques tours (NFR-1). Rechercher à chaque tour est aussi le comportement que l'on veut montrer.

**Échec de recherche.** Le tour continue sans extraits, sur le modèle d'un hook qui échoue (`_hook`, « Il laisse passer : le tour continue ») et de NFR-8. `harness_error` porte « Le tour continue sans extraits RAG. » dans `effect_fr`.

## Hypothèses à valider

1. **Verdict de la story 12.** La story 15 attend que la story 12 soit `done` (sinon HALT), et le modèle n'est nommé que dans `[rag.embedding]`. Seul l'adaptateur du `backend` retenu est écrit.
2. **Téléchargement.** « Télécharger » est livré ici, dans une forme minimale et pour la seule cible `rag_embedding`, avec le client de `net`, sans `huggingface_hub` : pas de nouvelle dépendance, et un code réutilisable pour le LLM plus tard. La progression passe par `session_state.reason_fr`, sans nouveau `kind`.
3. **`LoadRegistry`.** Il naît ici, réduit à l'embedding. Le LLM y passera avec la story 17, et le diagnostic mémoire ne change pas.
4. **Chargement.** Il n'occupe pas le verrou d'opération : un tour lancé pendant le chargement tourne sans RAG.
5. **Requête.** C'est le message brut de l'utilisateur, sans reformulation par l'historique (RAG simple).
6. **Historique.** Les extraits n'y entrent pas.
7. **Échec de recherche.** Le tour continue sans extraits, alors que la lettre d'AD-16 dit que le tour se termine en erreur.
8. **Seuil et scores.** Aucun seuil : les `top_k` extraits partent toujours, même avec des scores faibles, et c'est un matériau pédagogique. Le score n'entre pas dans le contexte, le titre du document si.
9. **Aperçu.** Le « maximum déclaré » d'AD-9 est lu comme les `top_k` extraits les plus longs de l'index.
10. **Corpus.** « Exemplia » est une organisation fictive, avec 8 documents originaux sous la licence du dépôt.
11. **Index livré.** Il n'est committé que si le modèle est présent à l'implémentation (huggingface.co est bloqué dans l'environnement actuel). Sinon, il se construit sur le poste de référence.
12. **sqlite-vec sous Windows.** Le chargement d'extensions sqlite par le Python de `uv` est à vérifier sur le poste de référence. En cas d'échec, la brique reste indisponible, avec la raison.
13. **Programme.** Le module « RAG » est ajouté en fin de programme ; la story 21 pourra le réordonner. Son premier scénario, cumulatif, est en lazy loading pour tenir dans la fenêtre, ce qui reste à vérifier au test manuel.
14. **Schéma.** Un seul composant, `rag.retriever` ; le modèle d'embedding est nommé dans son infobulle plutôt que dessiné comme un nœud à part.

Ajoutées pendant l'implémentation (exécution sans humain, 2026-09-26) :

15. **Précondition.** La story 12 est `done` avec un verdict provisoire (granite-embedding-107m-multilingual Q8_0, `llama_cpp`) : il suffit, sur instruction de l'appelant. `[rag.embedding]` en reprend les valeurs ; `measured_rss_mb` est omis (rien n'a été mesuré), donc le coût vaut la taille du fichier plus la marge. La config n'accepte que `backend = "llama_cpp"` ; `fastembed` n'est pas ajouté.
16. **Marge.** `[memory] load_margin_mb` reste à 256, la valeur posée par la story 17, au lieu des 128 cités ici : un seul réglage sert le LLM et l'embedding.
17. **Registre.** Celui de la story 17 existe déjà : il gagne un emplacement `embedding` et son refus chiffré en Mo, sans second registre.
18. ~~**« Télécharger » seulement pour « modèle absent ».**~~ Remplacée après la revue indépendante (hypothèse 28) : « Télécharger » est proposé dès que le modèle manque, même si l'index manque aussi, et « Construire l'index » ensuite.
19. **Fichiers relus aussi au clic.** Si « Télécharger » trouve les fichiers déjà là (copiés à la main), il répond 409 « Rien à télécharger », relit l'index et les fichiers, et la brique se charge : pas besoin de relancer WaveStack. Un téléchargement qui échoue relit aussi les fichiers.
20. **Fil du téléchargement.** Il tourne sur un fil à lui, pas sur le fil de travail : les aperçus et les bascules restent réactifs. L'état `download` refuse les intentions de classe (b) ; la raison d'`idle` d'avant (par exemple « aucun modèle chargé ») est rendue après.
21. **Échec de téléchargement affiché.** Hors tour, le `harness_error` du téléchargement porte la brique `rag` : la carte l'affiche (formatage seul, AD-1). Une URL `http` n'est acceptée que sur la boucle locale (comme `base_url` des modèles cloud), ce qui sert le test de bout en bout.
22. **Découverte des modèles.** Les fichiers déclarés par `[rag.embedding]` ne sont jamais proposés comme modèle de conversation au diagnostic ni dans « Changer de modèle » (sinon le GGUF d'embedding, rangé dans `models/embedding/`, était sondé et déclaré incompatible à chaque lancement).
23. **Traçage des redirections.** `net/factory.py` lisait `request.content`, qui lève sur une requête de redirection (corps en flux non lu) : toute redirection vers un hôte autorisé échouait, outils réseau compris. Corrigé ici, car le téléchargement suit la redirection de huggingface.co vers `*.hf.co`.
24. **Pooling.** L'adaptateur ne force pas `pooling_type` : il lit celui du GGUF (CLS attendu). Le test marqué `model` le vérifie sur le vrai fichier.
25. **`uv.lock` écrit à la main.** `uv add "sqlite-vec==0.1.9"` échoue ici : l'index abetlen de llama-cpp-python est injoignable. `pyproject.toml` a été modifié par `uv add --frozen`, et l'entrée de `uv.lock` recopiée d'une résolution PyPI isolée ; `uv lock --check --offline` et `uv sync --locked` passent. À confirmer par un `uv lock` sur un poste qui joint l'index.
26. **Consigne du scénario.** Le scénario `rag` veut la brique RAG (critère d'acceptation) : la consigne dit donc de l'éteindre d'abord, d'envoyer, puis de la rallumer et de rejouer. Second prompt : le plafond d'hôtel à Paris (document « Déplacements » seul).
27. **Test de bout en bout.** Un lanceur (`tools/e2e/wavestack_e2e.py`) remplace le modèle d'embedding par le faux des tests ; l'index est construit dans le dossier de données temporaire, et le faux serveur sert le fichier du modèle (503, puis 200).

Ajoutées après la revue indépendante (2026-09-26) :

28. **Installation neuve depuis l'interface.** La lettre du critère d'acceptation 2 (« `download` n'est présent que pour « modèle absent » ») est lue comme « seulement quand le modèle manque », quelle que soit la raison affichée en premier : sinon un clone neuf (index et modèle absents) n'avait aucun chemin. La carte propose donc « Télécharger » dès que le fichier manque, puis « Construire l'index » (même code que `scripts/build_rag_index.py`) une fois le modèle là et l'index absent, illisible, d'un autre modèle ou périmé. La construction tourne sur son propre fil, dans un nouvel état de session `index_build`, avec progression et « Arrêter », et trace l'effet `rag_index_write` ; son modèle d'embedding passe par le registre (AD-8) et se ferme ensuite.
29. **Identité du modèle.** Le fichier chargé doit avoir la taille déclarée (sinon il compte comme absent : « Télécharger » le remplace) et le sha256 déclaré quand il l'est ; `load_path` doit être l'un des `files`. L'index garde la taille et le sha256 du fichier qui l'a construit : un index d'un autre fichier est refusé comme « d'un autre modèle ». `scripts/build_rag_index.py --model` refuse un autre fichier que celui déclaré.
30. **Index périmé.** L'index garde une empreinte du corpus découpé ; un corpus modifié, un autre `[rag] chunk_max_chars` ou un index sans empreinte rendent la brique indisponible (« index périmé »), avec « Construire l'index ». Un index remplacé pendant la séance (script) est relu à la recherche suivante : s'il ne convient plus, la recherche échoue avec la raison et la brique devient indisponible.
31. **Texte indexé.** L'avertissement « Texte fictif… » reste dans chaque document, en commentaire HTML jamais indexé (il est aussi dans `notice_fr`) ; chaque passage est embarqué avec le titre de son document. Le corpus découpé compte 29 extraits.
32. **Score.** `1 − distance cosinus` peut sortir de [0, 1] : il est borné à [0, 1] (NaN vaut 0), ce qui rend exact le texte de la carte ; une question sans aucun vecteur (vecteur nul) fait échouer la recherche, pas le tour.
33. **Unités.** Tailles de fichiers en Mo décimaux (README, carte, progression). Les messages de budget mémoire gardent les Mo du budget (`[memory] budget_mb`, en Mio), comme la story 17.
34. **Budget refusé.** Après un changement de modèle (la mémoire change), un modèle d'embedding refusé par le budget est rechargé de lui-même ; désactiver puis réactiver la brique le retente aussi.
35. **Aperçu (écart C1).** AD-9 dit à la fois « aperçu calculé sans message ni extraits RAG » et « extraits RAG comptés à leur maximum déclaré ». L'aperçu suit la seconde règle (hypothèse 9) : il place les 3 extraits les plus longs de l'index, pour que la jauge « prochain tour » ne sous-estime pas le tour. L'adéquation du scénario à la fenêtre reste à vérifier au test manuel (deferred-work.md).
36. **Téléchargement par le script.** `scripts/build_rag_index.py --download` ouvre la garde réseau aux seuls hôtes de `[net] allowed_hosts` ; sans l'option, boucle locale seulement.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` : aucune erreur attendue.
- `uv run python -m pytest` : tout doit passer, sans réseau.
- `node --check src/wavestack/web/static/app.js` : aucune erreur attendue.
- `uv run python scripts/build_rag_index.py`, quand le modèle est présent : il affiche le résumé et écrit `data/rag_index.sqlite`.

**Manual checks:**
- `uv run wavestack`, scénario « RAG » :
  - sans la brique, le modèle invente la longueur du mot de passe ;
  - avec la brique, l'étape montre 3 extraits et leurs scores, et la réponse cite le bon document ;
  - « Comparer » montre les segments « Extraits RAG » ;
  - le schéma montre `file.rag_index` en fichier local ;
  - on vérifie la jauge et la latence (NFR-1).

## Auto Run Result

Status: done
Blocking condition: aucune.

(Planification : arrêt après planification à la demande de l'appelant, puis reprise le 2026-09-26 une fois la story 12 `done` avec un verdict provisoire.)

**Résumé.** Brique `rag` complète : corpus fictif « Exemplia » (8 textes, 310 à 345 mots), découpage unique, index sqlite-vec écrit hors ligne par `scripts/build_rag_index.py`, adaptateur llama.cpp derrière `[rag.embedding]`, chargement par le registre de la story 17 (emplacement `embedding`, refus chiffré), recherche à chaque tour (étape « Recherche RAG », paire d'événements), extraits en segments `rag_excerpt` avant le message, aperçu aux extraits les plus longs, cause de dépassement, « Télécharger » avec progression et « Arrêter », front (rail, carte, schéma, journal), module « RAG » du programme.

**Fichiers.**
- `pyproject.toml`, `uv.lock` : `sqlite-vec==0.1.9` (entrée du lock écrite à la main, hypothèse 25).
- `wavestack.toml` : `[rag]`, `[rag.embedding]` (verdict provisoire de la story 12), commentaires `[memory]`.
- `content/corpus/*.md` (8), `content/rag.yaml`, `content/bricks/rag.yaml`, `content/scenarios.yaml` : corpus, textes de la brique, module et scénario `rag`.
- `src/wavestack/config.py` : `EmbeddingFile`, `EmbeddingModel`, `rag_embedding`, `rag_top_k`, `rag_chunk_max_chars`, `rag_index_path()`.
- `src/wavestack/models/embedding.py` : port `Embedder`, `LlamaCppEmbedder`, `open_embedder`.
- `src/wavestack/models/load_registry.py` : emplacement `embedding`, `embedding_cost`, `check_component`.
- `src/wavestack/models/download.py` : `download_files`, `missing_files`, `DownloadError`.
- `src/wavestack/models/discovery.py` : le modèle d'embedding n'est jamais un candidat LLM.
- `src/wavestack/net/factory.py` : traçage d'une redirection (corps en flux).
- `src/wavestack/rag/` : `corpus.py`, `index.py`, `retriever.py`.
- `scripts/build_rag_index.py` : construction de l'index, garde réseau en boucle locale.
- `src/wavestack/bricks/registry.py`, `trace/catalog.py`, `session/app_session.py`, `web/app.py` : brique, événements, disponibilité, chargement, recherche, contexte, aperçu, téléchargement, route `download_model`.
- `src/wavestack/web/static/app.js`, `app.css` : étape du rail, carte (bouton, progression, échec), schéma, journal.
- `tests/fake_embedder.py`, `tests/test_rag.py`, `tests/test_rag_download.py` ; `tests/test_bricks.py`, `tests/test_scenarios.py` ajustés à la nouvelle brique.
- `tools/e2e/` : lanceur `wavestack_e2e.py`, index et faux modèle dans `stack.py`, fichier et réponses « mot de passe » dans `fake_openai.py`, scénario `rag` dans `run_e2e.py`, README, capture `22-rag-recherche-et-extraits.jpg`.
- `README.md` : section « RAG : corpus de démonstration et index ».

**Revue.** 4 corrections (2 medium, 2 low), 4 points différés (non vérifiables ici), 1 rejeté (« 0 / 0 Mo » sur un fichier minuscule, cosmétique). Relecture de suivi recommandée : **oui** (2 corrections medium) ; risque non vérifié : le vrai modèle d'embedding sur le PC Windows (chargement de sqlite-vec par le Python de `uv`, pooling du GGUF, latence).

**Vérifications.**
- `uv run ruff check .`, `uv run ruff format --check .` : OK.
- `uv run python -m pytest` : 540 réussis, 4 sautés (dont l'index livré, absent), 3 désélectionnés (`model`).
- `node --check src/wavestack/web/static/app.js` : OK.
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` : 197 vérifications réussies, 0 échec (29 pour le scénario `rag` : modèle absent, téléchargement en échec expliqué puis réussi, tour sans puis avec RAG, étape, extraits dans Contexte LLM, schéma, « Comparer », rechargement).
- Adaptateur llama.cpp exercé sur un GGUF BERT synthétique (poids aléatoires) : vecteurs normalisés, troncature d'un texte long, contrôle des dimensions, construction de l'index, `close()`.
- `scripts/build_rag_index.py` sans modèle : message et code 2 ; avec un modèle aux mauvaises dimensions : message et code 2, aucun index écrit.

**Index livré.** Non construit : huggingface.co est bloqué ici, le modèle d'embedding est absent. `data/rag_index.sqlite` est à construire sur le poste de référence (`uv run python scripts/build_rag_index.py`) puis à committer ; d'ici là, la brique dit « index absent ».

**Revue indépendante (2026-09-26).** Tous les points appliqués (voir « Review Triage Log ») ; deux reports (intégrité du modèle, adéquation AD-9). Vérifications après correctifs : `uv lock --check --offline`, ruff, `ruff format --check`, `node --check` : OK ; pytest : 629 réussis, 4 sautés ; E2E complet : 251 vérifications réussies, 0 échec (32 pour le scénario `rag`, parcours d'installation neuve compris). Relecture de suivi recommandée : oui ; risque non vérifié : la construction de l'index depuis la carte avec le vrai modèle sous Windows (durée, mémoire, verrouillage du fichier d'index).

**Risques résiduels.** Voir les points différés : sqlite-vec sous Windows, pooling du GGUF, `uv.lock` à confirmer, latence. La consigne du scénario (éteindre, envoyer, rallumer, rejouer) et la tenue du scénario cumulatif dans 4 096 tokens restent à vérifier au test manuel.
