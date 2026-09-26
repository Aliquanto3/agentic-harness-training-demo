---
title: 'Compression du contexte'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_revision: 'c53a60cd7b34b755384aefeddbc21b0fbc157951'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
warnings: ['oversized']
deferred:
  - summary: >-
      Les entrées de headroom-ai 0.38.0 et de ses 39 dépendances ont été ajoutées à uv.lock à la
      main, l'index abetlen étant injoignable.
    evidence: |-
      Résolution faite par `uv add --optional compression headroom-ai==0.38.0` sur une copie du
      projet sans llama-cpp-python (aucune version existante modifiée, 40 paquets ajoutés), puis
      fusion. `uv lock --check --offline`, `uv sync --locked` et `uv sync --locked --extra
      compression` passent. À confirmer par `uv lock` sur un poste qui joint l'index abetlen.
    location: >-
      uv.lock
    severity: low
  - summary: >-
      Sur un SLM local réel, vérifier que le scénario « Compression » tient dans la fenêtre sans
      compression (journal de 50 lignes plus extraits RAG) et mesurer le gain de latence.
    evidence: |-
      Non mesurable ici (aucun GGUF). Parcours E2E (faux modèle cloud) : 1 865 tokens sans
      compression, 1 437 envoyés, pour 3 584 utilisables. Headroom : 647 → 219 tokens estimés
      sur le journal.
    location: >-
      content/scenarios.yaml (scénario compression), content/demo_files/journal_serveur.log
    severity: medium (unverified)
  - summary: >-
      Relever sous Windows, sur le PC cible, la mémoire ajoutée par Headroom et l'absence de
      sortie réseau (AppLocker et WDAC face à `_core.pyd` et `ast-grep`).
    evidence: |-
      130 Mo et zéro tentative réseau mesurés hors PC cible par la story 12 ; `tools/bench/
      story12_bench.py headroom` à relancer sur le poste de référence.
    location: >-
      src/wavestack/compression/headroom_adapter.py, wavestack.toml [compression] cost_mb
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Rien ne montre encore qu'un harnais peut réduire ce qui entre dans le contexte : un gros résultat d'outil ou des extraits RAG passent tels quels, et la symétrie « la compression réduit ce qui entre, Caveman ce qui sort » (UJ-7, CAP-32, FR-31) reste invisible.

**Approach:** Une brique `compression` (context engineering) passe les `tool_result` et `rag_excerpt` par un port `Compressor` à l'étape `transform_context` (AD-4, AD-22). L'adaptateur est Headroom (`headroom-ai==0.38.0`, retenu par la story 12), dépendance optionnelle (extra uv `compression`), chargé par le `LoadRegistry` (AD-8). Chaque compression est une étape du harnais tracée avec l'avant, l'après et les tokens des deux versions ; les segments remplacés portent `compressed_from`, et Contexte LLM montre le texte d'avant et le total sans compression.

## Boundaries & Constraints

**Always:**
- **Dépendance optionnelle (story 12).** `headroom-ai==0.38.0` épinglé exactement, dans l'extra `compression` (`uv sync --extra compression`). Absent ou d'une autre version : brique indisponible, raison en français avec la commande à lancer. Aucun test pytest n'exige headroom : les tests injectent un faux compresseur.
- **Hors ligne (AD-15, story 12).** `cli` pose avant tout import tiers `LITELLM_LOCAL_MODEL_COST_MAP=True`, `HEADROOM_OFFLINE=1`, `HEADROOM_BEACON=off`, `HEADROOM_UPDATE_CHECK=off`, `DO_NOT_TRACK=1` et `TIKTOKEN_CACHE_DIR` (cache fourni par litellm, trouvé sans l'importer) ; l'adaptateur les repose avant `import headroom`. Appel avec `kompress_model="disabled"` et `protect_recent=0`.
- **Chargement (AD-8).** À l'activation de la brique (`set_brick`, scénario, réinitialisation), sur le thread de travail : contrôle du budget avec `[compression] cost_mb` (130), import et un appel de chauffe, puis `grant` dans le slot `compressor`. Libéré à la désactivation et à `close()`. Pendant le chargement : indisponible « Chargement de Headroom… » ; refus du budget ou échec : indisponible avec la raison, jamais de plantage.
- **Portée (AD-22).** Seuls les `tool_result` d'un outil exécuté (natif, réseau, MCP) et les `rag_excerpt` sont candidats, dans le contexte `main` seul. Jamais : réponses des méta-outils (`source = harness`), `subagent_result`, `skill_body`, `history`, refus d'un hook, erreur réinjectée d'un appel mal formé, contexte `sub{n}`. Un texte de moins de `[compression] min_chars` (300) caractères n'est pas candidat.
- **Moment (AD-4, ajout seul).** Avant le premier appel du tour : les extraits RAG et les réponses des actions forcées. Avant chaque appel suivant : les réponses d'outils arrivées depuis l'appel précédent, une seule fois. Un texte déjà envoyé au modèle n'est jamais réécrit. Aucun candidat : aucune étape, aucun événement.
- **Étape tracée (AD-2).** `{turn}.main.s{n}`, brique `compression`, composant `compression.compressor`, `actor` et `trigger` = `harness`. Paire `compression_started{phase_label, items, compressor_fr}` / `compression_ended{status: ok|error, compressor_fr, items[{source_fr, kind, brick, component, tokens_before, tokens_after, text_before, text_after, changed, transforms}], tokens_before, tokens_after, saved_tokens, estimated, error_fr, duration_ms}`. Tokens comptés par WaveStack (`_count_tokens` : tokenizer en local, estimation en mode chat), jamais ceux de Headroom. Un résultat vide ou pas plus court en tokens garde le texte d'origine (`changed = false`).
- **Segments (AD-4).** Le remplaçant garde `kind`, `brick` et `component` d'origine et porte `compressed_from{tokens_before, text_before}`. `context_rendered` porte `uncompressed_used` (le total si ces segments n'étaient pas compressés), calculé par la session. En mode chat, le corps JSON envoyé contient le texte compressé.
- **Historique.** Un tour terminé garde dans l'historique le texte que le modèle a lu (compressé), en `history`, sans `compressed_from` ; il n'est jamais recompressé.
- **Échec (AD-16).** Une exception de Headroom sur un candidat : texte d'origine gardé, `harness_error`, `compression_ended{status: error, error_fr}` ; le tour continue.
- **Front (AD-1, mise en forme seule).** Orchestration : ligne « 🗜️ Compression (Headroom) », acteur harnais, chiffre « {avant} → {après} tokens (−{x} %) » ; détail : une entrée par candidat (source, tokens avant → après, textes avant/après repliables), événement du harnais violet. Contexte LLM : un segment compressé affiche « compressé, {avant} tokens avant » et un repli « Texte avant compression » ; en tête, « Sans compression : ≈ {uncompressed_used} tokens ». Schéma : puce 🗜️ sur le harnais, allumée pendant l'étape ; journal : résumés d'une ligne.
- **Scénario (CAP-40).** Module « Compression » (30 min) en fin de programme, après RAG : briques du scénario `rag` plus `compression` (`mcp_lazy`, hooks `h1`, `h2`), outil `read_file`, fichier de démonstration `journal_serveur.log` (journal fictif, une erreur grave parmi des lignes répétitives).
- Textes en français sous `content/` ; code en anglais ; aucun nouveau `SegmentKind` ; `uv`, `ruff`, `pytest`.

**Never:** compression ML (Kompress, torch, onnxruntime), téléchargement de modèle, outil de récupération du texte coupé (le « Retrieve more: hash » de Headroom reste un texte inerte), compresseur maison en plus de Headroom, compression dans le sous-agent ou de l'historique, compression dans l'aperçu de la jauge (AD-9), nouvelle dépendance hors de l'extra, modification de `stories.yaml` ou d'une autre story, réécriture de la story 15 hors des points d'accroche nommés.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu | Erreur |
|---|---|---|---|
| Gros résultat d'outil | brique active ; le modèle appelle `read_file` sur `journal_serveur.log` | Après l'outil, étape compression (1 candidat) avant l'appel suivant ; ce dernier contient le texte compressé en `tool_result` avec `compressed_from` ; `uncompressed_used > used` | — |
| Action forcée | `read_file` forcé | Compressé avant le premier appel | — |
| Extraits RAG | `rag` + `compression` | Extraits ≥ 300 caractères candidats avant le premier appel ; prose inchangée (`changed = false`), intro non candidate | — |
| Petit résultat | `get_datetime` | Aucune étape, aucun événement | — |
| Méta-outil / hook / sous-agent | `load_skill`, refus H1, `delegate` | Jamais candidat | — |
| headroom-ai absent | extra non installé | Brique indisponible : « … `uv sync --extra compression` … » | — |
| Budget dépassé | RSS + 130 Mo > budget | Indisponible, raison chiffrée, rien d'importé | — |
| Headroom lève | exception sur un candidat | Texte d'origine, `harness_error`, `status: error`, tour terminé | pas de plantage |
| Toutes briques éteintes | LLM nu | Contexte octet pour octet inchangé | — |

</intent-contract>

## Code Map

- `pyproject.toml`, `uv.lock` -- extra `compression = ["headroom-ai==0.38.0"]` ; 40 paquets ajoutés au verrou (résolution pypi faite sans llama-cpp-python, index abetlen injoignable, fusionnée à la main comme sqlite-vec en story 15).
- `src/wavestack/compression/` (nouveau, AD-22) : `__init__.py` (vide de dépendances) ; `env.py` (`OFFLINE_ENV`, `apply_offline_env()`, stdlib seule, appelée par `cli`) ; `port.py` (`Compressed{text, transforms}`, protocole `Compressor{label_fr, compress(text), close()}`, `CompressionContent` + `load_compression_content()` de `content/compression.yaml`) ; `headroom_adapter.py` (`HEADROOM_VERSION`, `missing_fr()`, `HeadroomCompressor`, imports lourds dans le constructeur).
- `src/wavestack/cli.py` L21-31 -- `apply_offline_env()` juste après la garde réseau.
- `src/wavestack/config.py` L347 (modèle `rag_top_k`) + `wavestack.toml` -- `[compression] min_chars = 300`, `cost_mb = 130` ; propriétés `compression_min_chars`, `compression_cost_bytes`.
- `src/wavestack/models/load_registry.py` -- slot `COMPRESSOR = "compressor"` (réutilise `check_component`, `grant`, `release`).
- `src/wavestack/context/segments.py` -- `CompressedFrom{tokens_before, text_before}` ; `Part.compressed_from` et `Segment.compressed_from` (défaut `None`). `context/render.py` `_attribute` L306 : recopie `compressed_from` de la part. `context/window.py` `gauge` : `uncompressed_used` quand un segment est compressé.
- `src/wavestack/trace/catalog.py` -- `SegmentPayload.compressed_from`, `ContextWindowPayload.uncompressed_used`, `CompressionItem`, `CompressionStartedPayload`, `CompressionEndedPayload` dans `PAYLOAD_MODELS` (L589).
- `src/wavestack/bricks/registry.py` -- brique `compression` (`category="context"`), composant `compression.compressor` (`kind="compressor"`, `local_process`, `edges_to=["core.harness"]`).
- `src/wavestack/session/app_session.py` :
  - `__init__` (L405) : `compressor_factory` injectable ; `_compression_missing` (seulement avec la fabrique par défaut), `_compressor`, `_compression_loading`, `_compression_load_error`, `_compression_content`.
  - `_load_content` (L1325) : `content/compression.yaml`, sinon `_content_errors["compression"]`.
  - Modèle RAG L1600-1690 : `_request_compression_sync`, `_sync_compression`, `_load_compressor`, `_release_compressor`, `_compression_unavailable` ; appelés où `_request_rag_sync` l'est (`set_brick` L2384, `_reconfigure` L3417) et à `close()` (L995). `_availability` (L1714).
  - `TurnState` (L299) + `rag_compressed: tuple[CompressedFrom | None, ...]` ; `_messages` (L2050) : les parts RAG la portent ; `_step_messages` (L1906) : `compressed_from` d'une étape `tool` hors historique.
  - `_turn` (L3640) : `sent` = nombre d'étapes déjà rendues ; avant `before_model_call`, `_transform_context(turn_id, step, state, steps, sent, first=n == 1)` si la brique est effective et le compresseur chargé ; contrôle d'arrêt après.
  - `_emit_architecture` (L781) : infobulle de la puce `compression.compressor`.
- `content/bricks/compression.yaml`, `content/compression.yaml`, `content/demo_files/journal_serveur.log`, `content/scenarios.yaml`.
- `src/wavestack/web/static/app.js` : `applyEnvelope` (modèle `rag_search_*` L370) ; `turnRows` (L3024) ; `compressionBody` (modèle `ragBody` L2688) ; `appendSegments` (L2305) et en-tête de `renderContextBody` ; `schemaActivity` (L4280) ; `JOURNAL_LABELS` (L3929) et résumés (L4008) ; `BRICK_ICONS` (L4159). `app.css` : `.compression-items`, `.ctx-compressed`.
- `README.md` -- installation de l'extra et commande de lancement.
- E2E : `tools/e2e/fake_openai.py` (`_plan` L140 : « journal_serveur » → `read_file`), `tools/e2e/run_e2e.py` (scénario `compression` après `rag`), `tools/e2e/README.md`.
- Tests : `tests/test_rag.py` (`rag_session`, `Embedders`), `tests/test_tools.py`, `tests/fake_engine.py`, `tests/test_cloud.py` (session cloud factice).

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock` -- extra `compression`, verrou fusionné ; `uv lock --check --offline`, `uv sync --locked --extra compression`.
- [x] `src/wavestack/compression/*`, `src/wavestack/cli.py`, `src/wavestack/config.py`, `wavestack.toml`, `src/wavestack/models/load_registry.py` -- port, adaptateur, variables hors ligne, réglages, slot.
- [x] `src/wavestack/context/segments.py`, `render.py`, `window.py`, `src/wavestack/trace/catalog.py` -- `compressed_from`, `uncompressed_used`, deux événements.
- [x] `src/wavestack/bricks/registry.py`, `content/bricks/compression.yaml`, `content/compression.yaml` -- brique et textes.
- [x] `src/wavestack/session/app_session.py` -- chargement, disponibilité, `_transform_context`, parts et étapes compressées, schéma.
- [x] `src/wavestack/web/static/app.js`, `app.css` -- étape, contexte avant/après, puce, journal.
- [x] `content/demo_files/journal_serveur.log`, `content/scenarios.yaml` -- module et scénario `compression`.
- [x] `tests/test_compression.py` (nouveau) -- une ligne de la matrice par test, plus : variables hors ligne, adaptateur Headroom réel (sauté si absent), mode chat (corps compressé, estimation).
- [x] `tools/e2e/*`, `README.md` -- parcours `compression` visible, documentation.

**Acceptance Criteria:**
- Given la brique activée et un gros résultat d'outil, when on déplie « Compression (Headroom) » dans Orchestration, then on lit pour chaque candidat sa source, ses tokens avant → après et les deux textes, et la ligne porte le total avant → après avec le pourcentage.
- Given le même tour, when on ouvre Contexte LLM, then le segment « Résultat d'outil » est marqué compressé avec ses tokens d'avant, son texte d'avant se déplie, et l'en-tête donne le total sans compression à côté du total envoyé.
- Given la brique éteinte, when on rejoue le prompt et qu'on ouvre « Comparer », then le résultat d'outil y pèse ses tokens d'origine.
- Given headroom-ai absent, when on ouvre le panneau des briques, then la carte « Compression » est indisponible avec la commande d'installation, et le reste de WaveStack fonctionne.

## Spec Change Log

## Review Triage Log

### 2026-09-26 — Revue de l'agent principal (brève ; une revue indépendante suivra)
- Verdicts : 0 high, 1 medium, 4 low, 0 false, 1 maybe-false.
  - `[medium]` `[defer]` Fenêtre du scénario sur un vrai SLM (journal + extraits RAG sans compression) non mesurée. — Ce qui tranche : le scénario joué sur le PC cible ; entrée `deferred`.
  - `[low]` `[patch]` Le titre de l'étape recopiait « Headroom 0.38.0 » et se tronquait dans Orchestration. — Corrigé : `title_fr` (« Compression (Headroom) ») vient de `content/compression.yaml` par `compression_started`.
  - `[low]` `[patch]` Un candidat inchangé n'expliquait pas pourquoi (0 % sur la prose). — Corrigé : `compression_ended.unchanged_fr`, affiché sous chaque texte inchangé.
  - `[low]` `[accept]` `uncompressed_used` additionne des tokens comptés à part (tokenizer seul sur le texte d'avant) et des tokens attribués dans le rendu : écart d'un ou deux tokens en local, estimation en mode chat. Affiché avec « ≈ ».
  - `[low]` `[accept]` Les extraits RAG, toujours inchangés sans Kompress, ajoutent une étape à 0 % avant le premier appel. Gardé : c'est la limite de Headroom que la carte annonce (Design Notes).
  - `[maybe-false]` `[defer]` Headroom écrit « Retrieve more: hash=… » : un SLM pourrait tenter un outil inexistant. — Ce qui tranche : le scénario sur le PC cible ; un appel inconnu suit déjà la voie de l'appel mal formé (AD-10), sans plantage.

## Design Notes

**Pourquoi compresser dans le tour.** AD-4 place `transform_context` « seulement avant le premier appel d'un tour ». Lu à la lettre, un résultat d'outil demandé par le modèle, arrivé après ce premier appel, ne serait jamais compressé, alors que CAP-32 et UJ-7 visent précisément ce cas. La règle protège l'ajout seul (le préfixe déjà lu n'est pas réécrit). La compression d'une réponse d'outil nouvelle, une seule fois, avant le premier appel qui la contient, la respecte : rien de déjà envoyé ne change (H-1). Le spine reçoit cette précision.

**Headroom seul.** Sans Kompress, Headroom ne compresse que le structuré (JSON en tableau, journaux) ; la prose passe telle quelle. Les extraits RAG restent candidats, et leur 0 % s'affiche : c'est une limite de l'outil, dite par la carte (story 12, hypothèse 7), plutôt qu'un second compresseur.

## Hypothèses à valider

- **H-1 Compression dans le tour** (voir Design Notes) : réponses d'outils compressées avant le premier appel qui les contient, pas seulement avant le premier appel du tour. Lecture stricte d'AD-4 possible, mais elle viderait la brique de son cas principal.
- **H-2 Historique** : on garde le texte compressé (ce que le modèle a lu), pas l'original. Désactiver la brique ne regonfle pas les tours passés.
- **H-3 Seuil** : `min_chars = 300` évite une étape pour chaque petit résultat ; à ajuster après la séance pilote.
- **H-4 Coût mémoire** : 130 Mo, mesuré hors PC cible par la story 12 ; relevé à refaire sur le PC cible.
- **H-5 Installation** : l'extra n'est pas installé par `uv run wavestack` seul ; la séance doit lancer `uv sync --extra compression` une fois (documenté au README).
- **H-6 `model="gpt-4o"`** : Headroom l'utilise pour son propre compte (tiktoken `o200k_base`) ; WaveStack compte ses tokens lui-même.
- **H-7 Libération** : désactiver la brique rend sa part du budget (`LoadRegistry.release`), mais le module Python reste importé jusqu'à l'arrêt de WaveStack ; la mesure RSS réelle le compte toujours, donc un chargement suivant reste contrôlé honnêtement.
- **H-8 Journal de démonstration** : `journal_serveur.log` a 50 lignes, niveaux `INFO`/`WARN`/`ERROR` en anglais. Mesuré ici : Headroom 0.38.0 ne reconnaît pas un journal de moins de ~50 lignes ni les niveaux français (`ERREUR`, `ALERTE`) ; à 50 lignes, il garde `WARN` et `ERROR` (2 585 → 876 caractères).
- **H-9 Verrou écrit à la main** (voir `deferred`) : même procédé que sqlite-vec en story 15.
- **H-10 Écart de processus** : exécution sans humain et sans outil de sous-agent ; plan, implémentation et revue faits par l'agent principal (revue brève, une revue indépendante suivra). Le spine reçoit une précision sous AD-4 (H-1), marquée « hypothèse à valider ».
- **H-11 Scénario** : briques du module RAG (convention cumulative de la story 15) plus `compression` ; le second prompt montre la perte d'information (le lot 12 est coupé par Headroom).

## Verification

**Commands:**
- `uv lock --check --offline` -- expected: verrou à jour
- `uv sync --locked --extra compression` -- expected: headroom-ai 0.38.0 installé
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q` -- expected: tout vert
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 échec

## Auto Run Result

Status: done

- `uv lock --check --offline` : à jour (91 paquets) ; `uv sync --locked --extra compression` : OK.
- `ruff check` et `ruff format --check` : aucun écart ; `node --check` : OK.
- `pytest -q` : 618 réussis, 4 sautés (dont aucun de `tests/test_compression.py`, qui a joué le vrai Headroom), 3 désélectionnés (`model`).
- E2E complet : 267 vérifications réussies, 0 échec, 0 anomalie connue ; scénario `compression` : 25 vérifications, capture `24-compression-avant-apres.jpg`.
- Audit de la matrice : chaque ligne a son test dans `tests/test_compression.py`, joué et vert.
