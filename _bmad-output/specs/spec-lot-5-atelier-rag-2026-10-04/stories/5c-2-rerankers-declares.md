---
title: 'Lot 5c-2 : rerankers déclarés en plus du modèle de la brique (Qwen3-Reranker), formats de paire et refus dédiés'
type: 'feature'
created: '2026-10-05'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'def680ab0603643ee824caa32ce0b9a2ffbdb656'
context:
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/essai-modeles-5c.md'
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/stories/5c-1-embedding-au-choix.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'étape Reranking de l'Atelier RAG ne propose que BGE v2 M3, le reranker de la brique ; l'adaptateur traite tout GGUF comme un cross-encoder XLM-R (paire `[BOS] q [EOS] [SEP] d [EOS]`, sigmoïde), ce qui donne des scores sans signification pour un cross-encoder BERT (identifiants de segment non transmis par llama.cpp) et pour un reranker LLM comme Qwen3-Reranker (gabarit de rerank, sortie déjà en probabilité) ; la troncature des paires est silencieuse.

**Approach:** Déclarer Qwen3-Reranker-0.6B en `[[rag_lab.rerankers]]` (même mécanique que `[[rag_lab.embeddings]]` de 5c-1 : option = id déclaré, disponibilité et raison, emplacement mémoire propre, prêt ou chargement par `Loans`) ; l'adaptateur choisit le format de paire d'après l'en-tête GGUF et refuse, avec un message dédié en fr, en et de, ce qu'il ne sait pas noter.

**Décisions (2026-10-05, confirmées par l'essai et les en-têtes réels) :**
- « Reranker BERT refusé » vise les cross-encoders qui dépendent des identifiants de segment : `tokenizer.ggml.token_type_count` ≥ 2 (MiniLM : 2). BGE v2 M3, converti en `bert` avec `token_type_count = 1` et `bert.attention.causal = false`, reste accepté.
- Reranker LLM (architecture causale : `{arch}.attention.causal` absent ou vrai) : refusé sans `tokenizer.chat_template.rerank` ; avec ce gabarit, paire tokenisée en une séquence (`special=True`) et score lu tel quel comme une probabilité, sans sigmoïde.

## Boundaries & Constraints

**Always:**
- BGE (`[rag.reranker]`, option `declared`) inchangé dans ses scores ; préréglage « RAG + reranking » sur `declared`.
- `[[rag_lab.rerankers]]` : schéma `RerankerModel`, fichiers sous `reranker/`, mêmes règles d'id que 5c-1 (unique, ≤ 32 caractères, ni `declared` ni l'id de la brique), entrée invalide écartée avec message, toml seulement ; validation factorisée avec celle de 5c-1.
- Un emplacement `LoadRegistry` par modèle (`rag_lab.reranker.<id>`) ; la brique jamais déchargée par l'atelier ; sha256 vérifié par `rag_lab.file_digest`.
- Règles de format dans `models/reranker.py`, appliquées à tout reranker au chargement (brique comprise) et, pour les rerankers de l'atelier, dès le catalogue (en-tête lu, option indisponible avec la raison).
- Messages dédiés fr/en/de : fichier absent, cross-encoder à segments, LLM sans gabarit de rerank, troncature des paires (formes one/other).
- Le focus du Reranking dit comment le score est lu (sigmoïde du logit ou probabilité du modèle) ; l'explication de l'étape dit que les scores de deux rerankers ne se comparent pas, seul l'ordre compte.
- Troncature : nombre de candidats dont la paire a été coupée à `max_tokens`, en avertissement (`warning_text`) de l'étape.

**Never:** téléchargement depuis l'atelier (5c-4) ; MiniLM ou un autre cross-encoder BERT déclaré ; sigmoïde sur la sortie d'un reranker à gabarit ; nouvel endpoint.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Choix Qwen3-Reranker | fichier présent, chaîne livrée, Reranking = qwen3-reranker-0.6b | run `ok`, paire par le gabarit, scores = sortie brute, fait « probabilité » | N/A |
| Fichier absent | Qwen3-Reranker non téléchargé | option listée, indisponible, raison nommant `reranker/…` | refus `unavailable` sur la ligne |
| Cross-encoder à segments | GGUF `token_type_count = 2` déclaré | option indisponible, raison dédiée ; chargement refusé `models.reranker.segments` | refus |
| LLM sans gabarit | architecture causale, pas de `tokenizer.chat_template.rerank` | option indisponible, raison dédiée ; chargement refusé | refus |
| BGE | `bert`, `token_type_count = 1`, non causal | format paire, sigmoïde, scores inchangés | N/A |
| Troncature | paire plus longue que `max_tokens` | avertissement « N candidats sur M … coupés à X tokens » | avertissement |
| Slot | la brique tient BGE, run avec Qwen3 | slot `reranker` intact, `rag_lab.reranker.qwen3-reranker-0.6b` libéré en fin de run | N/A |

</frozen-after-approval>

## Code Map

- `wavestack.toml` -- après `[[rag_lab.embeddings]]` : `[[rag_lab.rerankers]]` Qwen3-Reranker-0.6B : `https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/resolve/a02f48bb4f057028298c21fa033da2b30d7742d5/qwen3-reranker-0.6b-q8_0.gguf`, path `reranker/qwen3-reranker-0.6b-q8_0.gguf`, size 639153184, sha256 `22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48`, Apache-2.0, `max_tokens = 1024`, RSS 937 (PC de développement).
- `src/wavestack/config.py` -- `Config.rag_lab_embeddings` / `rag_lab_embedding` / `RAG_LAB_RESERVED_IDS` (5c-1) : factoriser pour `rag_lab_rerankers` / `rag_lab_reranker` (réservés : `declared` + id de la brique, dossier `reranker/`) ; `load_config` ignore aussi `rag_lab.rerankers` de settings.json ; messages `config.rag_lab_rerankers.*`.
- `src/wavestack/models/reranker.py` -- `pair_tokens` l. 67 (format paire, gardé pour BGE) ; `LlamaCppReranker.__init__` l. 118 (contrôle de pooling après chargement via `llm.metadata`) ; `_logit` (lecture `llama_get_embeddings_seq[0]`) ; `score` (sigmoïde) : ajouter le classement de l'en-tête (`segments` / `no_rerank_template` / format paire / format gabarit), la paire par gabarit (`{query}`, `{document}` ; lire le gabarit réel dans l'en-tête du GGUF, requête HTTP Range sur le dépôt si besoin, et traiter tout autre champ qu'il contient), coupe du document seul pour tenir dans `max_tokens`, score brut pour le gabarit, attribut disant comment le score est lu.
- `src/wavestack/models/gguf_meta.py`, `models/catalog.py` -- `catalog.header_metadata` (en-tête complet en cache : `tokenizer.chat_template.rerank` est après les tableaux du vocabulaire, `stop_at` ne suffit pas).
- `src/wavestack/models/load_registry.py` -- constante `RAG_LAB_RERANKER = "rag_lab.reranker"`.
- `src/wavestack/models/discovery.py` -- `_rag_model_files` : inclure `[[rag_lab.rerankers]]`.
- `src/wavestack/session/app_session.py` -- `_rag_lab_catalog` (options rerank déclarées : fichier puis en-tête), `_rag_lab_reranker` l. 9608 (sur le modèle de `_rag_lab_declared_lent` de 5c-1 : slot propre, `soft=True`), `_rag_lab_absent` à généraliser.
- `src/wavestack/rag/lab.py` -- `_rerank` (l. ~1890-1977) : lit `item.truncated` pour l'avertissement, fait sur la lecture du score ; `OPTIONS["rerank"] = ("declared",)` inchangé.
- `content/messages.yaml`, `content/rag_lab.yaml` et copies en/de -- refus `models.reranker.segments`, `models.reranker.no_rerank_template`, raison de fichier absent, `rag_lab.rerank.truncated` (one/other), faits de lecture du score, explication de l'étape Reranking.
- `tests/fixtures/make_tiny_rerank_gguf.py` + `tiny-bert-rank.gguf` -- déclare aujourd'hui `token_type_count = 2` (l. 51) : régénérer à 1 (comme BGE) et produire la variante à 2 pour le test de refus ; seul `tests/test_rag_rerank.py:808` charge ce fichier en reranker, `test_model_servers.py:1365` le lit.
- Tests -- `tests/test_rag_lab_embeddings.py` (modèle à suivre), `tests/test_rag_rerank.py`, `tests/test_rag_lab.py`, `tools/e2e/run_e2e.py` (`_rag_lab` : select du Reranking).
- Docs -- `docs/guide.md` (puce Reranking au choix), `docs/installation.md` (tableau « Modèles du RAG », chiffre disque).

## Tasks & Acceptance

**Execution:**
- [x] `wavestack.toml`, `config.py` -- déclarer et valider `[[rag_lab.rerankers]]` (validation commune avec 5c-1).
- [x] `models/reranker.py`, fixtures -- classement de l'en-tête, format gabarit, score brut, refus dédiés, compte des paires coupées.
- [x] `app_session.py`, `load_registry.py`, `discovery.py` -- options, disponibilité par fichier et en-tête, slot par modèle.
- [x] `rag/lab.py`, contenus ×3 -- avertissement, fait de lecture du score, explication.
- [x] tests pytest (matrice entière, adaptateur sur fixtures réelles et faux `Llama`) et E2E (Qwen3-Reranker dans le select, indisponible sans fichier) ; docs.

**Acceptance Criteria:**
- Given la chaîne livrée et BGE, when on lance la chaîne, then les scores sont identiques à ceux d'avant ce lot.
- Given la langue en ou de, when on lit refus, raisons et avertissement, then ils sont traduits.
- Given `uv run pytest`, `ruff check` et les E2E RAG, when on les lance, then tout est vert (hors `test_readme_is_a_short_onboarding_page`, rouge sur main).

## Implementation Notes

- En-tête réel de Qwen3-Reranker relu le 2026-10-05 (fichier de l'essai, dossier temporaire) : `tokenizer.chat_template.rerank` ne porte que `{query}` et `{document}` (instruction en dur dans le gabarit), pas de `qwen3.attention.causal`, `qwen3.pooling_type = 4`. Le gabarit est découpé à ses deux champs (dans n'importe quel ordre, chacun une fois ; sinon refus `no_rerank_template`) : un nom de champ dans la question reste du texte.
- `rerank_format(meta)` (`models/reranker.py`) : pooling déclaré ≠ RANK → `embedding_pooling` ; `token_type_count` ≥ 2 → `segments` ; causal (clé vraie, ou absente hors architectures d'encodeur connues de llama.cpp : `ENCODERS`, bert, nomic-bert, jina-bert-v2…) sans gabarit utilisable → `no_rerank_template` ; sinon paire (non causal) ou gabarit. Accepte l'en-tête typé (lecteur Python) et les textes de `llm.metadata`. Sans `general.architecture` (en-tête illisible), la paire, comme avant : la sonde du chargement juge.
- Adaptateur : l'en-tête est lu en Python avant `Llama(...)` (refus sans rien charger) ; illisible, `llm.metadata` décide après chargement. Contrôle de pooling après chargement gardé. Paire par gabarit : remplie puis tokenisée d'un bloc (`add_bos=False`, `special=True`, comme llama-server) ; trop longue, parties fixes gardées entières, question et extrait coupés par `fit` (règle de `pair_tokens` : l'extrait d'abord). Score du gabarit lu tel quel, borné à [0, 1] (NaN → 0). Attributs `format`, `score_reading` (`sigmoid` / `probability`), `max_tokens`.
- BGE inchangé : `pair_tokens` et la sigmoïde intacts ; vérifié sur le vrai GGUF (scores identiques à 10⁻⁶ avant/après sur 4 paires dont une coupée) et Qwen3-Reranker réel 0,996 / 0,002 / 0,057 (essai : 1,0 / 0,0 / 0,06). MiniLM L6 réel refusé `segments`, Granite et Qwen3-Embedding refusés `embedding_pooling`.
- Catalogue : `catalog.header_metadata` (cache par taille et mtime) puis `rerank_format` ; option indisponible « Indisponible : {raison} ». Un fichier absent passe avant l'en-tête.
- Config : `_rag_lab_models` factorise la validation de 5c-1 (messages `config.rag_lab_<section>.*`) ; `RAG_LAB_RERANKER_RESERVED_IDS = ("declared",)` (test d'égalité avec `OPTIONS["rerank"]`).
- Fait « Lecture du score » ajouté seulement quand le reranker dit `score_reading` (le faux des tests n'en dit rien ; celui des E2E dit `sigmoid`, il tient le rôle de BGE). Avertissement de troncature seulement si le reranker dit `max_tokens`.
- Revue 1 : l'étape Reranking trie sur le score borné non arrondi (arrondi à l'affichage seulement : les probabilités saturées de Qwen3 ne s'égalisent plus à 1,000) ; `pair_tokens` passe par `fit` ; le gabarit rend le drapeau de coupe de `fit` ; refus sha256 des modèles de l'atelier nommés `[[rag_lab.embeddings]]` / `[[rag_lab.rerankers]]`.
- Fixtures : `tiny-bert-rank.gguf` régénéré à `token_type_count = 1` ; `tiny-bert-rank-segments.gguf` ajouté (et dé-ignoré dans `.gitignore`) ; `tiny-bert-cls.gguf` inchangé à l'octet.

## Spec Change Log

## Review Triage Log

Passe 1, 2026-10-05.

| # | Source | Constat | Verdict | Preuve | Suite |
| --- | --- | --- | --- | --- | --- |
| 1 | blind | tri du Reranking sur des scores arrondis à 3 décimales : les probabilités saturées de Qwen3 (1,000 / 0,000) tombent à égalité et retombent sur le rang de la recherche | medium | `lab.py:1926-1929` | patch (tri sur la valeur brute, arrondi à l'affichage) |
| 2 | verif | le test « pas d'avertissement » ne tient aucun de ses deux gardes (`truncate_over` posé sur la fabrique, jamais lu) | medium | `test_rag_lab_rerankers.py` ~470 ; `Rerankers.__call__` | patch |
| 3 | verif | `fit` jamais exercé sur une question longue | medium | seul test : question de 2 tokens | patch (test unitaire) |
| 4 | verif | trace d'une entrée rejetée : ni `cause` ni `effect_text` vérifiés | low | `test_an_invalid_entry_is_traced_once` | patch |
| 5 | edge | chemin coupé : `cut=True` rendu même quand `fit` ne coupe rien | low | `_pair`, branche gabarit | patch (rendre le `cut` de `fit`) |
| 6 | blind | `fit` recopie la règle de `pair_tokens` | low | deux copies de la même formule | patch (`pair_tokens` appelle `fit`) |
| 7 | blind | « causal si la clé est absente » refuserait un encodeur (`bert`, `nomic-bert`…) converti sans `attention.causal`, brique comprise | low | `_causal` ; le test fige `{"general.architecture": "bert"}` → refus | patch (encodeurs connus non causaux par défaut) |
| 8 | blind | explication : la raison donnée (logit contre probabilité) est fausse, c'est la calibration de chaque modèle ; anglais peu idiomatique | low | `rag_lab.yaml` ×3 | patch |
| 9 | blind | l'avertissement ne dit pas que la question peut aussi être coupée | low | `fit`, `pair_tokens` coupent la question | patch (texte) |
| 10 | blind | fait « Lecture du score » testé en français seulement | low | — | patch |
| 11 | blind | refus sha256 : `[rag_lab.rerankers]` au lieu de `[[rag_lab.rerankers]]` (de même pour les embeddings, 5c-1) | low | `section=` des deux `open_model` | patch |
| 12 | blind | docs : ligne non rebouclée, paragraphe « Hors ligne » et RAM sans les modèles de l'atelier | low | `installation.md`, `guide.md` | patch |
| 13 | edge, blind, verif | gabarit dont la partie fixe dépasse `max_tokens` : débordement, refus générique `no_score` | low | n'arrive qu'avec un `max_tokens` déclaré minuscule ; Qwen3 : ~60 tokens fixes pour 1 024 | rejeté |
| 14 | edge, blind | chemin coupé tokenisé autrement que le chemin entier (fusions BPE, `special`) | low | chunk ≤ 1 500 caractères + question ≤ 500 + gabarit tiennent sous 1 024 tokens : chemin coupé quasi inatteignable dans l'atelier | rejeté |
| 15 | edge, blind | jetons spéciaux d'une question tapée parsés dans le chemin entier | low | même lecture que llama-server ; corpus maîtrisé, question du formateur | rejeté |
| 16 | edge | reranker à gabarit dont la sortie serait un logit, borné à [0, 1] | maybe-false | Qwen3 vérifié sur le vrai GGUF (0,996 / 0,002 / 0,057) ; trancherait : un autre reranker à gabarit | rejeté (low si vrai) |
| 17 | edge | `reranker/../x.gguf` passe le contrôle du dossier | false | `_relative_path` refuse « .. » partout | rejeté |
| 18 | edge | refus au chargement rendu en français en en/de (`cause=str(exc)`) | low | `Loans.lend`, antérieur à 5c ; le refus d'en-tête est déjà traduit au catalogue | defer |
| 19 | blind | `_rag_lab_declared_reranker_lent` recopie celui de 5c-1 | low | duplication sans dérive démontrée | rejeté |
| 20 | blind | « scores BGE inchangés » sans test automatique | low | `pair_tokens` et sigmoïde inchangés, figés par `test_rag_rerank.py` ; vérifié sur le vrai GGUF | rejeté |

## Design Notes

- En-têtes réels relevés le 2026-10-05 (lecture partielle sur Hugging Face) : BGE v2 M3 (gpustack) `general.architecture = bert`, `tokenizer.ggml.token_type_count = 1`, `bert.attention.causal = false`, pas de `pooling_type` ; ms-marco-MiniLM `token_type_count = 2`. Qwen3-Reranker : `qwen3.pooling_type = 4` (RANK), gabarit `tokenizer.chat_template.rerank` (essai §1).
- Un GGUF Qwen3-Reranker hors de `reranker/` est déjà écarté des modèles de conversation par 5c-1 (`pooling_type` > 0).

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q` -- expected: vert hors `test_readme_is_a_short_onboarding_page`
- `PYTHONIOENCODING=utf-8 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only rag rag_rerank rag_lab` -- expected: aucun FAIL
