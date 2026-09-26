---
title: 'Corpus de démonstration et RAG simple'
type: 'feature'
created: '2026-09-26'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
warnings: ['oversized']
deferred: []
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
- [ ] `pyproject.toml`, `uv.lock`, `wavestack.toml` : vérifier la précondition (story 12), puis `uv add "sqlite-vec==0.1.9"`, et `fastembed` si le verdict le retient. Remplir `wavestack.toml` : `[rag]` (`index_path`, `top_k`, `chunk_max_chars`), `[rag.embedding]` (verdict) et `[memory]` (`budget_mb`, `load_margin_mb`).
- [ ] `content/corpus/*.md` (8), `content/rag.yaml`, `content/bricks/rag.yaml` : corpus fictif et textes de la brique, en français.
- [ ] `src/wavestack/config.py` : `EmbeddingModel` et accesseurs ; une section invalide rend la brique indisponible, sans plantage.
- [ ] `src/wavestack/models/embedding.py` (nouveau) : port `Embedder{model_id, dims, embed_queries, embed_passages, close}`, vecteurs normalisés, et l'adaptateur du `backend` retenu.
- [ ] `src/wavestack/models/load_registry.py` (nouveau) : `LoadRegistry`, avec une mesure injectable.
- [ ] `src/wavestack/models/download.py` (nouveau) : `download_files(files, dest, cancel, on_progress)`.
- [ ] `src/wavestack/rag/` (nouveau) :
  - `corpus.py` : chargement et découpage ;
  - `index.py` : écriture et lecture sqlite-vec, `meta` ;
  - `retriever.py` : `Retriever`, `SqliteVecRetriever`, `Excerpt`.
- [ ] `scripts/build_rag_index.py` (nouveau) : `--model PATH` facultatif, sinon le chemin de `[rag.embedding]` ; garde réseau en boucle locale ; résumé en français (documents, extraits, dimensions, durée).
- [ ] `src/wavestack/bricks/registry.py`, `trace/catalog.py`, `session/app_session.py`, `web/app.py` : brique, événements, disponibilité, chargement, recherche, contexte, aperçu, téléchargement, cause de dépassement.
- [ ] `src/wavestack/web/static/app.js` et `app.css` : ligne et détail du rail, bouton et progression sur la carte, activité du schéma, icône, journal.
- [ ] `content/scenarios.yaml` : module « RAG » et scénario `rag`.
- [ ] `tests/fake_embedder.py` (nouveau) : sac de mots haché en 64 dimensions, normalisé, déterministe.
- [ ] `tests/test_rag.py` (nouveau) : une ligne de la matrice par test, hors téléchargement, sur un index temporaire construit avec le vrai code de `rag/` et `FakeEmbedder` ; découpage ; refus chiffré du `LoadRegistry` (mesure injectée) ; libération à la désactivation ; aperçu ; mode chat (moteur cloud factice des tests de la story 11) ; schéma. Un test compare l'index livré aux extraits du corpus, et il est sauté si l'index est absent. Un test marqué `model` utilise le vrai modèle.
- [ ] `tests/test_rag_download.py` (nouveau) : lignes « Téléchargement » et « Hors idle », avec `MockTransport` ; routes 404 et 409.
- [ ] `data/rag_index.sqlite` : si les fichiers du modèle retenu sont sur le poste d'implémentation, construire et committer l'index. Sinon, le consigner sous Auto Run Result (index à construire sur le poste de référence) et laisser la brique « index absent ».

**Acceptance Criteria:**
- Given un tour avec la brique `rag` effective, when la page est rechargée, then le rail montre toujours l'étape « Recherche RAG », avec sa requête, ses extraits, leurs scores et leur placement (projection du journal, AD-1).
- Given la brique `rag` voulue mais indisponible, when on lit `/api/state`, then la carte `rag` porte `available: false` et la raison de la matrice, et `download` n'est présent que pour « modèle absent ».
- Given la brique activée puis désactivée, when le thread de travail a traité les deux intentions, then l'embedder a été chargé une fois puis fermé, et le `LoadRegistry` ne le compte plus.
- Given la brique effective et aucun tour, when l'aperçu est émis, then il contient l'intro et `top_k` segments `rag_excerpt`, qui sont les extraits les plus longs de l'index.
- Given le scénario `rag` lancé, when on lit `/api/state`, then les briques voulues sont celles des modules 1 à 4 plus `rag`, en lazy loading, avec les hooks H1 et H2.
- Given `uv run ruff check .`, `uv run ruff format --check .` et `uv run python -m pytest`, when ils s'exécutent sans réseau, then tout passe.

## Spec Change Log

## Review Triage Log

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

Status: ready-for-dev
Blocking condition: aucune. Arrêt après planification, à la demande de l'appelant. L'implémentation attend la story 12 (précondition du premier point d'Always) ; les hypothèses sont dans « Hypothèses à valider ».
