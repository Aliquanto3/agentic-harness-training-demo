---
title: 'B2 (plan du 2026-10-05) : Atelier RAG, composant « Index lexical (BM25) » construit au BUILD'
type: 'feature'
created: '2026-10-05'
status: 'done'
baseline_commit: '7dcb248723585e62281632107c18fbaff8bf8d4e'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/vues-atelier-rag.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** En RAG hybride, la colonne ARCHITECTURE ne montre aucun composant pour BM25 : la formule (k1 = 1,5, b = 0,75) est recalculée sur les Chunks à chaque question (`bm25()` dans `_lexical_search`), sans index construit au BUILD, alors qu'un vrai RAG hybride (Elasticsearch…) construit un index inversé à l'indexation.

**Approach (option (b) choisie par Anaël) :** un composant « Index lexical (BM25) » dans le groupe Données, écrit par une nouvelle étape BUILD qui lit les Chunks, présente seulement quand la chaîne a `lexical_search` ; l'étape BM25 (RUN) lit alors l'index lexical et la Question. Le calcul est découpé : construction de l'index au BUILD (termes par chunk, fréquences documentaires, longueurs, longueur moyenne, termes distincts), avec ses chiffres et sa durée propres dans le focus, puis score à la requête qui lit cet index (mêmes scores qu'avant). Le focus de BM25 dit que c'est un algorithme statistique, sans modèle appris. Mise à jour de `vues-atelier-rag.md` §2 et §4, `rag_lab.yaml` fr/en/de, mode Dérouler, préréglage « RAG hybride », tests pytest et E2E RAG.

**Décisions prises par Claude (Anaël injoignable, option recommandée) :**
- La nouvelle étape n'est pas une étape de la chaîne (pas de nouveau `kind`, chaînes sauvegardées et validation inchangées) : c'est la première partie de l'étape `lexical_search`, exécutée par la session à la fin du BUILD (après le vector store, avant le segment de récupération). Ses événements `rag_lab_stage_started/ended` portent le `stage_id` de l'étape BM25, `kind: "lexical_index"`, `part: "index"`, composant `rag_lab.lexical_index`.
- Nom technique de la ligne : « Lexical indexing » (noms techniques en anglais, mêmes en fr/en/de, comme « Indexing ») ; action fr « Construire l'index lexical (BM25) des chunks ». Composant : « Index lexical (BM25) », en « Lexical index (BM25) », de « Lexikalischer Index (BM25) ».
- L'atelier reconstruit l'index à chaque exécution (rapide, pas de cache) ; le focus le dit, un moteur de recherche le garde sur disque.
- Le détail replié (« Toutes les étapes en détail ») garde une carte par étape de la chaîne : les chiffres de l'index sont dans le focus de sa ligne.

## Boundaries & Constraints

**Always:** AD-1 (chiffres, statuts, table étape → composants de la session) ; scores BM25 identiques à l'arrondi près (`bm25()` reste, devenu index + score) ; textes fr/en/de ; la chaîne livrée (« RAG + reranking ») ne change pas (10 lignes, 9 tuiles).

**Never:** nouveau kind de chaîne ou nouveau champ de chaîne ; toucher `app_session.py` hors partie rag_lab ; cache disque de l'index lexical.

## I/O & Edge-Case Matrix

| Scénario | État | Attendu |
|---|---|---|
| Préréglage hybride | chaîne avec `lexical_search` | BUILD : 5 lignes, « Lexical indexing » après « Indexing » ; tuile « Index lexical (BM25) » dans Données ; BM25 lit Index lexical et Question |
| Chaîne sans BM25 | dense, livrée | ni ligne ni tuile d'index lexical |
| Run hybride | `ok` | une paire d'événements `lexical_index` (statut, durée, chiffres : chunks, termes distincts, occurrences, longueur moyenne, aucun modèle) avant ceux du segment ; BM25 rend les mêmes scores qu'avant |
| Étape précédente en échec / arrêt | `stopped` | partie index `skipped` (ou `cancelled`), BM25 `skipped` |
| Dérouler pendant un run | événements en direct | la ligne et sa tuile arrivent dans le pas-à-pas avant Dense retrieval, pastille avec sa durée |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `COMPONENTS` (l.103) : `lexical_index` (`data`, icône, `None`) après `vector_store`. `SequenceStep` (l.117) : champ `part: str | None` (la partie de l'étape dont la ligne montre les événements) ; `STEPS` (l.133) : `lexical_index` après `vector_store` = `SequenceStep("build", "lexical_search", own=False, part="index", reads=("chunks",), writes=("lexical_index",))` ; `lexical_search` lit `("lexical_index", "question")`. `_views()` (l.565) : `"part"` dans chaque step. `bm25()` (l.2355) découpé en `LexicalIndex` (dataclass : comptes par chunk, longueurs, df, moyenne, `n`, `vocabulary`, `occurrences`), `lexical_index(documents, lang)` et `bm25_scores(index, query, lang)` ; `bm25()` = les deux. `_Chain` (l.1377) : `lexical: LexicalIndex | None`. `_run_chain` (l.1502) : avant la première étape hors `FIXED_HEAD`, si la chaîne a `lexical_search`, `_lexical_index_part` (événements via `_emit` / `_ended`, step_id `{run}.s{i}.index`, annulation, `stopped`). `_lexical_search` (l.2089) lit `chain.lexical` (construit à la volée s'il manque).
- `content/messages.yaml` ×3 (`rag_lab.lexical_index.*` : `input`, `output`, faits ; `lexical_search.input` : « dans l'index lexical »).
- `content/rag_lab.yaml` ×3 : `steps.lexical_index` (label, action, explication : algorithme statistique, index inversé, reconstruit à chaque exécution), `components.lexical_index`, `stages.lexical_search.explain_text` (+ « sans modèle appris »).
- `src/wavestack/web/static/rag.js` -- `applyEnvelope` (l.1301-1318) : événement à `part` rangé dans `stage.parts[part]` sans toucher le statut de l'étape ; `rag_lab_run_started` : `parts: {}`. `runStage` (l.883) : pour `step.part`, la partie. `stepStatus`, `focusRun` (avertissement, pied durée/mémoire), `playFrames`, `landing` : `step.own || step.part`.
- `_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/vues-atelier-rag.md` §2, §4.
- `tests/test_rag_lab.py` -- l.960-1031 (catalogue : 5 lignes BUILD possibles, `not own`, composants) ; nouveaux tests : `bm25()` = `bm25_scores(lexical_index())` (mêmes valeurs), chiffres de l'index, événements `lexical_index` d'un run hybride (ordre, `part`, statut skipped après arrêt), absent d'une chaîne sans BM25.
- `tools/e2e/run_e2e.py` -- `_rag_lab_presets` (~l.14395) : après « RAG hybride », ligne `lexical_index` dans `#rag-seq-build`, tuile `lexical_index` dans Données ; après le run, focus de la ligne en Dérouler : termes distincts, durée.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/rag/lab.py` -- composant, étape, `part`, index + score, partie au BUILD.
- [x] `content/rag_lab.yaml`, `content/messages.yaml` ×3 -- textes.
- [x] `src/wavestack/web/static/rag.js` -- parties, pastille, focus, Dérouler.
- [x] `tests/test_rag_lab.py` -- catalogue mis à jour, nouveaux tests.
- [x] `vues-atelier-rag.md` §2 et §4 ; `docs/guide.md` (Atelier RAG, BM25).
- [x] `tools/e2e/run_e2e.py` -- préréglage hybride.

**Acceptance Criteria:**
- Given `/rag` sur « RAG hybride » après un run, when on clique « Lexical indexing » en Dérouler, then le focus montre les chunks indexés, les termes distincts, la longueur moyenne, « aucun modèle » et la durée de l'étape.
- Given la langue en ou de, when on lit la ligne, la tuile et le focus, then ils sont traduits.
- Given ruff et les tests concernés, when on les lance, then tout est vert ; l'E2E `rag rag_rerank rag_lab` passe.

## Implementation Notes

- Mode autonome (Anaël injoignable) : CHECKPOINT 1 « Approve and continue » pris à sa place ; implémentation directe dans la session (machine partagée), revue à trois relecteurs en sous-agents.
- `lab.py` : `LexicalIndex` (`counts`, `lengths`, `df`, `mean` ; `n`, `vocabulary`, `occurrences`), `lexical_index()`, `bm25_scores()`, `bm25()` = les deux ; `COMPONENTS["lexical_index"]` (📇, Données) ; `SequenceStep.part` ; `STEPS["lexical_index"]` ; `_Chain.lexical` ; `_run_chain` → `_lexical_index_part` avant la première étape hors `FIXED_HEAD` ; `_lexical_index` (chiffres : chunks, termes distincts, occurrences, longueur moyenne à une décimale, k1/b, « aucun modèle ») ; `_lexical_search` lit l'index.
- Surprise : les charges utiles passent par les modèles de `trace/catalog.py` (`model_validate` puis `model_dump`) ; `part` ajouté (optionnel, `None`) à `RagLabStageStartedPayload`, `…ProgressPayload`, `…EndedPayload`, sinon il était retiré.
- `rag.js` : `partOf` (événement à `part` rangé dans `stage.parts`), `runStage` (partie, « skipped » si le run est fini sans elle), `ownFigures`, `playFrames`, `landing`, `closeStaleRun` (parties).
- Textes : `rag_lab.yaml` ×3 (étape, composant, explication BM25), `messages.yaml` ×3 (`rag_lab.lexical_index.*`). Docs : `guide.md`, `vues-atelier-rag.md` §2-§4, `SPEC.md` (10 à 13 étapes).
- Vérifié : `pytest tests/test_rag_lab.py tests/test_rag_lab_download.py tests/test_ui_texts.py tests/test_i18n.py tests/test_annex_language.py` 318 passés ; `tests/test_backend_messages.py tests/test_content_language.py` 3 549 passés ; E2E `--only rag rag_rerank rag_lab --channel msedge` : 147 vérifications, 0 échec. Captures régénérées : 56 à 59 (atelier RAG).

## Spec Change Log

## Review Triage Log

Passe 1, 2026-10-05.

| # | Source | Constat | Verdict | Preuve | Suite |
| --- | --- | --- | --- | --- | --- |
| 1 | verif, blind | `part` du `rag_lab_stage_started` jamais vérifié | medium | seul l'ended était lu ; sans lui la page mettrait BM25 « en cours » au BUILD | patch (assertion `part` des deux started) |
| 2 | verif, blind | chemin d'erreur de la partie index jamais joué | medium | aucun test ne fait lever `lexical_index` | patch (`test_the_lexical_index_failing_stops_the_chain`) |
| 3 | edge, blind | `closeStaleRun` ne ferme pas les parties | low | pastille « en cours » sans fin si la session repasse au repos sans fin de run | patch |
| 4 | edge | run d'avant B2 relu : ligne « En attente » | low | `runStage` rendait `waiting` | patch (« skipped » si le run est fini) |
| 5 | edge | échec de l'index non dit dans les cartes du détail | low | le focus de la ligne le dit ; décision : cartes par étape de chaîne | rejeté |
| 6 | edge, verif, blind | journal et `phase_label` disent « BM25 » pour l'index | low | `phase_label` avec le libellé de BM25 ; `ragLabStage` par `stage_id` | patch (`phase_label` « Lexical indexing ») ; `app.js` : defer (fichier modifié en parallèle) |
| 7 | edge | une erreur d'index arrête aussi la recherche dense | low | même règle qu'un échec du BUILD ; calcul en Python pur, échec improbable | rejeté |
| 8 | edge, blind | longueur moyenne arrondie à l'entier (« 0 terme ») | low | `round(built.mean)` | patch (une décimale, `number`) |
| 9 | blind | « minuscules ignorées », « petits mots », « sa longueur » | low | textes ×3 | patch (casse, mots vides, sigles gardés, longueur du chunk) |
| 10 | blind | « Index lexical (BM25) » traduit, contre la règle des noms anglais | false | nom demandé par Anaël ; « Réponse » déjà traduit ; décision du bloc figé | rejeté |
| 11 | blind | partie copiée de `_run_chain` sans `LabCancelled`, `StageSkipped`, `soft` | low | aucun de ces cas n'est levé par l'index ; aide commune = restructuration | rejeté |
| 12 | blind | annulation avant le début de la partie non testée | low | course étroite ; l'étape suivante annule de même | rejeté |
| 13 | blind | `SPEC.md` : « 10 à 12 étapes » | low | hybride + Reranking = 13 lignes | patch |
| 14 | blind | `guide.md` « Trois vues » sans la nouvelle ligne | low | l.276 | patch |
| 15 | blind | docstring de `LabRun` périmée | low | « une paire par étape » | patch |
| 16 | blind | k1, b écrits en dur dans les textes | low | trois chaînes | patch (`{k1}`, `{b}` formatés) |
| 17 | blind | `LexicalIndex` gelé mais mutable, `__hash__` | low | `frozen=True` sur listes et dict | patch (`eq=False`) |
| 18 | blind | reconstruction de secours dans `_lexical_search` masque une régression | low | documentée, la partie est testée | rejeté |

## Verification

**Commands:**
- `uv run ruff check src tests tools && uv run ruff format --check src tests tools` -- expected: aucun écart
- `uv run pytest -q tests/test_rag_lab.py tests/test_rag_lab_download.py tests/test_ui_texts.py tests/test_i18n.py` -- expected: vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only rag rag_rerank rag_lab --channel msedge` -- expected: aucun FAIL
