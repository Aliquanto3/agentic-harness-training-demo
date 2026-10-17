# Existant à réutiliser (relevé du 2026-10-17, `main` à `0274806`)

## Atelier RAG du lot 5

| Élément | Où | Remarque |
|---|---|---|
| Registres | `src/wavestack/rag/lab.py` : `KINDS` :44 (9 types), `RETRIEVAL`, `FIXED_HEAD` et `FIXED_TAIL` :57-60, `OPTIONS` :65, `PARAMS` :78, `BOUNDS` :84, `PHASES` :99, `GROUPS` :102, `COMPONENTS` :103, `STEPS` :137, `PRESETS` :176, `default_pipeline` :411 | Seul le segment `RETRIEVAL` se réordonne ; un préréglage ne remplace que ce segment. |
| Exécution | `Pipeline` :401 (12 `Stage` au plus), `LabRun.run` :1463, `_run_chain` :1519, `_run_stage` :1694-1716 | Le dispatch se fait par une suite de `if stage.kind == …` ; un type inconnu lève `StageFailed`. Les événements sont `rag_lab_run_started`, `stage_started`, `stage_ended` et `rag_lab_run_ended`, avec le step_id `{run_id}.s{i}` (à plat). |
| Textes | `content/rag_lab.yaml` et `content/i18n/{en,de}/rag_lab.yaml` | `RagLabContent._every_kind_option_and_setting` (:339-366) exige exactement les clés des registres. |
| Page | `src/wavestack/web/static/rag.js` (1 762 lignes), `rag.css`, `rag.html` | La page est pilotée par `Catalog.payload()`. Seuls `generation`, `context`, `embedding` et `rerank` sont codés en dur (rag.js:187, 285, 1014-1018). |
| Payloads | `trace/catalog.py:1347-1446` (`RagLab*`) | `kind` est un `str` libre ; `RagLabStageEndedPayload` (:1415) ne porte que `duration_ms`, `rss_bytes` et les tokens de la génération. |
| Lignes du lot 5 | `_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/` | `vues-atelier-rag.md` et la maquette v2 font référence. |

**Pour ajouter un type, une option ou un préréglage**, on touche :
- le registre concerné ;
- une méthode `_xxx` et sa branche dans `_run_stage` ;
- les textes, dans les trois langues ;
- le cas échéant, la page.

## Comparaison A/B retirée

- **Ce que c'était** : une case « Comparer », une chaîne B, des colonnes A/B et une synthèse.
- **Retrait côté page** : décision d'Anaël du 2026-10-05 (`.memlog.md:48-50` du lot 5).
- **Retrait côté backend** en 5c-1 : `LANES_MAX`, `compare()`, `RagLabCompared` et les clés `rag.comparison.*`.
- **En V1.2**, CAP-9 compare une exécution courante et une exécution épinglée (deux runs successifs). Ce n'est pas un retour de la voie B.

## Coûts aujourd'hui

- **FinOps** (`[finops]`, wavestack.toml:276) et **GreenOps** (`[greenops]` :298, `greenops.py`, 301 lignes) ne comptent que le modèle génératif :
  - EcoLogits pour le cloud ;
  - CodeCarbon hors ligne pour le local.
- **Atelier RAG** : seule la génération entre dans la dépense de session (décision 5c-3).
- **Limite écrite dans `docs/guide.md:750`** : « L'embedding et le reranker du RAG ne sont pas comptés ». Rien n'est dit sur l'indexation.

## Traces

- **`Envelope`** (`trace/envelope.py`) porte `step_id` et `parent_step`, ce qui permet de reconstruire un arbre.
- **Il manque** un modèle de span (début et fin) et toute brique OpenTelemetry.
- **Ce que CAP-12 ajoute** : l'arbre de l'Atelier, avec un `parent_step` renseigné pour les sous-étapes et les appels de modèle.

## Cache de prompt (pour CAG)

- **llama-server** : `cache_prompt: True` (`models/servers.py:508`, `_last_cache_n` :542).
- **Moteur intégré** : `snapshot()`/`restore()` via `llama_state_get/set_data` (`models/engine.py:340-368`), utilisés par `app_session.py:5424` pour le préfixe de conversation.
- **Non utilisés à ce jour** : `/slots` save/restore et tout usage CAG.

## Briques transverses

- **Garde-fous** (`src/wavestack/guardrails/`) :
  - `toxicity.py` : distilbert ONNX ;
  - `pii.py` : Presidio et spaCy FR ;
  - `injection.py` : Prompt Guard 2 22M, ONNX ;
  - `manager.py` : modes block, flag et off.
- **Matrice des risques** :
  - données : `mcp/policy.py` (`RISKS` :16) ;
  - assemblage : `app_session.security_state()` :10956 ;
  - API : `GET /api/security` (`web/app.py:1151`) ;
  - rendu : `security.js:75-78, 318` ;
  - libellés : `ui.yaml` `security.matrix` :1567.
- **Outils et MCP** : `src/wavestack/mcp/`, réutilisés par la recherche agentique (CAP-7).
- **Modèles cloud** : `content/cloud.yaml`.
- **Fenêtre de contexte** : `config.WINDOW_CHOICES = (4096, 8192, 16384)`, 4 096 par défaut.

## Modèles de décision (banc CAP-6 de la V2)

`decision-model-candidates.md` ne couvre que le routage par spécialité :
- `deberta_xsmall` ONNX (87 Mo, MIT, 107 ms) est retenu par défaut ;
- le SLM juge (Qwen3.5-2B + GBNF) sert de repli ;
- aucun candidat n'y figure pour le filtre de passages ni pour le contrôle d'ancrage, d'où la story de banc préalable ;
- « Jev » n'y apparaît pas comme modèle par API.

## Extras et dépendances

| Extra existant | Contenu |
|---|---|
| `compression` | headroom-ai==0.38.0 |
| `guardrails` | onnxruntime==1.23.2, tokenizers==0.22.1, presidio ==2.2.360, spacy==3.8.7, fr-core-news-sm |
| `rag-alt` | faiss-cpu==1.15.1, lancedb==0.39.0 |
| `greenops` | codecarbon==3.3.1 |

Base : llama-cpp-python>=0.3.35,<0.4, sqlite-vec==0.1.9, ecologits>=0.11.2,<0.12.

**Extras prévus par la V1.2** (versions à épingler à la story qui les introduit) :

| Extra | Contenu | Justification |
|---|---|---|
| `otel` | opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http | CAP-12, pur Python, aucun service |
| `eval-adapters` | ragas, deepeval | CAP-11, optionnel ; à écarter s'ils tirent torch ou un service |
| (aucun) | networkx ou union-find maison pour les communautés de GraphRAG | À trancher dans la story GraphRAG ; préférer le code maison s'il reste court |

## Travail reporté qui touche le RAG (`deferred-work.md`)

- 979, 982, 985, 988, 1003, 1006, 1013, 1016 et 1019 : vocabulaire, E2E de disponibilité et de troncature, focus clavier, téléchargements.
- 904 et 912 : Kev-0.8B et critères de Julia-1, utiles au banc System One.
