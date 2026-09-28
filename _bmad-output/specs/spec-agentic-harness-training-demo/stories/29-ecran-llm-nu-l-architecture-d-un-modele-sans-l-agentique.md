---
title: 'Écran « LLM nu » : l''architecture d''un modèle, sans l''agentique'
type: 'feature'
created: '2026-09-28'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/31-mode-sombre.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/25-selecteur-de-modeles-regroupe-et-tableau-des-capacites.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/26-fenetre-de-contexte-reglable-4-096-8-192-16-384.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/24-modeles-memoire-comptee-juste-budget-dynamique-sonde-interruptible.md'
  - '{project-root}/tools/e2e/README.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Demande du 2026-09-28. L'atelier montre ce que le harnais ajoute à un LLM, mais rien ne montre ce qui se passe *dans* le modèle. Le texte découpé en tokens, les vecteurs d'embedding et les réglages d'échantillonnage restent invisibles. On ne voit pas non plus le chargement en mémoire vive, la lecture du prompt, la génération token par token ni les probabilités des candidats. Aujourd'hui, l'échantillonnage est figé : `TEMPERATURE`, `TOP_P` et `TOP_K` dans `models/engine.py`, `min_p` à 0 en dur, rien pour un modèle cloud, et rien n'est tracé.

**Approach:** Une page à part, `/llm` (« LLM nu »), en HTML, CSS et JS natifs (AD-18), atteinte depuis la barre haute. Elle travaille sur le modèle actif, avec un prompt libre, sans aucune brique. La session porte tout (AD-1) :
- une intention de tokenisation ;
- une intention de génération, de classe (b), dans un nouvel état `llm_lab` ;
- des événements dédiés dans le contexte `llm` ;
- une lecture `GET /api/llm_lab`.

L'échantillonnage devient un paramètre de chaque appel des trois moteurs locaux, et des modèles cloud qui le déclarent. Il est tracé dans `model_call_started`. La story se livre en **quatre incréments**, chacun utilisable seul (section « Incréments »).

## Boundaries & Constraints

**Always:**
- Conventions de `CLAUDE.md` : `uv` (jamais pip), `ruff`, `pytest`. Code et identifiants en anglais ; textes d'interface et contenus pédagogiques en français.
- AD-1 et AD-2 : tout ce que la page affiche vient d'un événement du journal ou de `GET /api/llm_lab`, construit par la session.
  - La page ne compte aucun token et ne calcule ni débit, ni probabilité, ni dimension.
  - Elle a droit à la mise en forme et au chronomètre local ancré sur un `ts` de `*_started`, remplacé ensuite par le `*_ended`.
  - Elle a droit au rendu visible des blancs (`␣`, `↵`).
- Les textes pédagogiques vivent dans `content/llm_lab.yaml` (AD-19). Ce fichier est validé par pydantic. S'il est invalide, la session émet `harness_error`, la page reste servie et affiche la raison.
- Aucune brique n'intervient : pas de prompt système, d'historique, d'outil, de mémoire, de hook, de RAG ni de compression. Le prompt est un seul message utilisateur, rendu par le gabarit du modèle (AD-4). La conversation de l'atelier (`_history`, `_last`, jauge, aperçu) n'est jamais modifiée.
- Contexte de trace `llm` : `context_id="llm"`, `turn_id=None`, `step_id` et `call_id` en `llm{n}`. La page `/` ignore ces événements, sauf pour son journal replié. Aucun `context_rendered`, `context_preview` ni `context_reconciled` n'est émis dans ce contexte.
- Génération de classe (b) : acceptée en `idle` seulement, sinon 409 avec la raison. Elle passe en `llm_lab` sous le verrou, dans l'appel qui l'accepte, puis tourne sur le worker unique (`_executor`). « Arrêter » l'interrompt (classe c). La tokenisation est acceptée en `idle` et tourne aussi sur le worker, sans changer d'état.
- Moteur en processus : l'état du contexte principal est sauvegardé puis restauré autour d'un appel de l'écran (`_save_main_state` et `_restore_main_state`, comme pour le sous-agent). À défaut, le tour suivant de l'atelier trace `prefix_not_reused` avec la nouvelle cause `llm`.
- Appels de l'atelier : ils gardent exactement leur requête. Ce sont les mêmes valeurs par défaut, et le corps cloud ne change pas. Seul le payload de `model_call_started` gagne le champ `sampling`.
- Pages statiques :
  - jetons de `tokens.css` seulement, aucune couleur en dur, aucun nouveau jeton de couleur ;
  - `theme.js` en tête et un sélecteur `select[data-theme-picker]` (story 31) ;
  - lisible dans les deux thèmes.
- Aucune dépendance nouvelle. `numpy` est déjà installé avec llama-cpp-python ; il est importé seulement dans le chemin du moteur en processus.
- Aucun vrai modèle dans le conteneur. On utilise les doublures du dépôt :
  - `tests/fake_engine.py` ;
  - `tests/gguf_writer.py` ;
  - le transport simulé de `tests/test_model_servers.py` ;
  - `tools/e2e/fake_local_server.py` et `tools/e2e/fake_openai.py`.
- Documentation et parcours E2E :
  - `uv run pytest -q` reste entièrement vert : aucune story livrée ne casse ;
  - mettre à jour EXPERIENCE.md, DESIGN.md (composants), SPEC.md (nouvel écran), README, `wavestack.toml` et le spine (AD-2, AD-3, AD-5, AD-18, AD-19) ;
  - ajouter les vérifications d'interface au parcours `tools/e2e/run_e2e.py`.
- Chaque incrément livré est commité seul, avec la documentation et l'E2E de son périmètre. Un incrément non livré est noté comme tel dans cette spec et dans le rapport, sans rien casser des précédents.

**Never:**
- `Llama(logits_all=True)`, qui réserverait n_ctx × vocabulaire en float32 (≈ 2,5 Go à 4 096 × 151 936) ; les probabilités se lisent sur la dernière position seulement.
- Recalculer dans le navigateur ce qu'un événement porte ; un état métier dans `localStorage` (seul le brouillon du prompt et les curseurs peuvent y être gardés, sous `try/catch`).
- Changer le modèle depuis la page (lien vers l'atelier seulement), régler la fenêtre ou la réserve de sortie (AD-9 : réserve 512, ou 1 536 avec raisonnement), régler `max_tokens`.
- Envoyer à un fournisseur cloud un paramètre qu'il n'a pas déclaré ; demander des probabilités à llama-server, Ollama ou un fournisseur cloud (incrément 4 : moteur en processus seulement).
- Modifier les scénarios, les briques, la story 30 (atelier RAG) ou le contenu d'une autre page que l'ajout du lien.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Tokenisation locale | Faux llama-server actif, « Bonjour <\|im_end\|> 🙂 » | `llm_tokenized` : `exact=true`, un token par octet, `<\|im_end\|>` = un token `special` (id 1002), `token_count` = nombre d'ids | — |
| Tokenisation cloud | Faux cloud A actif | `exact=false`, `tokens=[]`, `estimate` = `estimate_tokens(text)`, `unavailable_fr` : le tokenizer est chez le fournisseur | — |
| Texte long | 2 000 caractères | 512 tokens au plus dans `tokens`, `more` = le reste | > 2 000 caractères ou vide : 422 |
| Dimensions | GGUF avec `qwen35.embedding_length=2048`, `block_count=24`, `head_count` en tableau | `embedding_length 2048`, `layer_count 24`, `head_count` = max du tableau, `vocab_size` du tokenizer, `embedding_params` = vocab × dim | Clé absente : `null` et `source_fr` le dit |
| Génération locale | T 0,2 · top-k 5 · top-p 0,9 · min-p 0,05 | Valeurs envoyées au moteur (corps `/completion`, `options` d'Ollama, `generate` en processus) et tracées dans `model_call_started.sampling` (`source: screen`) | Hors bornes : 422 |
| Cloud qui déclare `sampling=["temperature","top_p"]` | T 0,2, top-k 5 | Corps : `temperature` et `top_p` seulement ; trace : `top_k`/`min_p` à `null`, `note_fr` « non réglables chez {fournisseur} » | — |
| Cloud sans déclaration | — | Aucun champ d'échantillonnage envoyé ; trace `source: provider` | — |
| Pas `idle` | Tour de l'atelier en cours | 409 « Refusé pour l'instant : … » | — |
| Arrêter | « Arrêter » pendant la génération | `llm_generation_ended{status: cancelled}`, retour en `idle`, conversation de l'atelier intacte | — |
| Raisonnement indisponible | `reasoning=true`, modèle sans raisonnement | 409 avec la raison de `reasoning_fr` | — |
| Probabilités | Moteur en processus, `candidates=true` | Chaque `llm_token` porte 5 candidats `{token_id, text, p, kept, p_sampled}` ; le token tiré est marqué, même hors des 5 | Serveur ou cloud : `candidates_available=false` avec la raison ; `candidates=true` → 409 |

</intent-contract>

## Code Map

Les stories 33, 23, 34, 32, 24, 25, 26, 27 et 31 modifient plusieurs de ces fichiers avant celle-ci. On se repère aux **symboles**, jamais aux numéros de ligne.

- `src/wavestack/models/engine.py`
  - `TEMPERATURE`, `TOP_P`, `TOP_K` : constantes à remplacer par `Sampling`.
  - `Fragment(text, output_tokens, stop_reason)`, `EngineMetadata`, `Engine` (Protocol, `complete(prompt_ids, stop, max_tokens, cancel)`).
  - `VocabTokenizer` : `_lib`, `_model`, `_vocab`, `tokenize` (`special=True`), `token_pieces`, `is_eog`, `_read_metadata`. Avec `vocab_only`, les hyperparamètres ne sont pas chargés (`n_ctx_train()` = 0).
  - `LlamaCppEngine.complete` : `self._llm.generate(prompt_ids, temp=…, top_p=…, top_k=…, min_p=0.0)`, un `Fragment` par token.
- llama-cpp-python 0.3.35 (`llama_cpp/llama.py`), lu dans le cache `uv` :
  - `Llama.eval` ne recopie plus les logits sans `logits_all`.
  - `Llama._init_sampler` enchaîne `top_k`, `typical`, `top_p`, `min_p`, `temp`, `dist` : la température vient *après* le tri.
  - Quand `generate` rend un token, `llama_cpp.llama_get_logits_ith(ctx, -1)` pointe sur les logits dont il a été tiré (`n_vocab()` flottants).
  - Dimensions : `llama_model_n_embd`, `llama_model_n_layer`, `llama_model_n_head`, `llama_vocab_n_tokens`.
- `src/wavestack/models/servers.py`
  - Importe `TEMPERATURE`, `TOP_K`, `TOP_P`.
  - `_sampling()` : dict envoyé, pénalités neutres comprises.
  - `LlamaServerEngine._read_metadata` : `/v1/models`, `meta` (`n_ctx_train`) ; le vrai serveur y donne aussi `n_vocab` et `n_embd`.
  - `LlamaServerEngine.complete` : corps `/completion`, `**_sampling()`.
  - `OllamaRawEngine.complete` : `options`, `**_sampling()`. `_open_tokenizer`.
- `src/wavestack/cloud.py` -- `chat_fields(entry, max_tokens, reasoning)` : champs du corps chat, dans leur ordre.
- `src/wavestack/config.py`
  - `CloudModel` (strict), `output_reserve`, `OUTPUT_RESERVE`, `MAX_RESERVE`, `MIN_REASONING_BUDGET`.
  - `Config.reasoning_budget_tokens`, `estimate_tokens`, `Config.chars_per_token`, `content_dir()`.
- `src/wavestack/models/gguf_meta.py` -- `try_read_metadata` : clés de l'en-tête. Les tableaux longs (le vocabulaire) valent `None`, d'où un vocabulaire lu au tokenizer.
- `src/wavestack/models/capabilities.py` -- `Capabilities` (`reasoning_variable`, `reasoning`, `reasoning_always`, `reasoning_tags`, `stop_sequences`) ; `ChannelSplitter`. La story 25 y ajoute `reasoning_mode`, à réutiliser si elle est livrée.
- `src/wavestack/models/openai_chat.py` -- `run_call(engine, body, cancel, *, phase_label, …)` : `model_call_started`, puis `model_delta` groupé par `DELTA_INTERVAL_S`, puis `model_call_ended`.
- `src/wavestack/models/load_registry.py` -- `process_rss()`, `LoadRegistry.grant`, `_size`. La story 24 y ajoute `baseline()` et `grant(…, base=)`.
- `src/wavestack/context/render.py` -- `render_context(engine, template, messages, *, call_id, special_tokens, **template_vars)`, `render_chat_body`.
- `src/wavestack/session/app_session.py`
  - Génération :
    - `_call_model` : fonctions internes `generate`, `take`, `flush`, `end` ; `reasoning_cut` ; `output_truncated`.
    - `_call_model_chat` : émet `context_reconciled` et modifie `self._ratio`. **À ne pas utiliser pour l'écran.**
    - `_render` : `template_vars[reasoning_variable]`.
  - États et arrêt :
    - `_start` : passage en `turn` sous `_memory_lock` et `_lock`, puis `self._executor.submit`.
    - `_refusal_reason`, `stop` (arme les jetons selon l'état), `_emit_state`, `_set_state`, `_error`.
  - Cache du moteur : `_save_main_state`, `_restore_main_state`, `_check_reuse`, `_PREFIX_CAUSES_FR`, `_SUBAGENT_EVICTED_FR`, `_cache_cause`, `_cache_evicted`.
  - Chargement :
    - `_load` : `off_turn`, `model_load_started`, `_release`, `_checkpoint`, sonde, `_install`, `model_load_ended` dans le `finally`.
    - `_install` : `_engine_factory` ou `_server_factory`, puis `capabilities_for`.
  - Aides : `active_model()`, `_engine`, `_caps`, `_cloud`, `_fr`, `_ms`.
- `src/wavestack/trace/catalog.py` -- `SessionState` (Literal), `ModelCallStartedPayload`, `ModelLoadEndedPayload`, `PAYLOAD_MODELS`. `trace/scope.py` : `scoped`.
- `src/wavestack/web/app.py`
  - Modèles d'intention.
  - Route `send`, modèle du 409 sur `SendRefused` ; `stop` ; `index_page` et `diagnostic_page` (`FileResponse`).
  - `api_state` : `main` n'exclut que `sub*`.
  - `_sse_stream`.
- `src/wavestack/web/static/`
  - `index.html` : `header.top-bar` ; la story 26 y met `#window-toggle`, la story 31 `#theme-picker` avant `#reset-button`.
  - `app.js` :
    - `applyEnvelope`, dont le garde `SUB_KINDS` pour les sous-agents ;
    - `SESSION_STATES`, `eventSummary` (cas `model_call_started`, `model_load_ended`), `fmt` ;
    - gestion de `server_instance`.
  - Stories 25 et 31 : `models.html` et `nav.page-tabs` ; `theme.js` et `[data-theme-picker]`.
- `tools/e2e/`
  - `fake_local_server.py` :
    - `models` (`meta`) ;
    - `completion` : morceaux de 4 caractères, raisonnement « Je réfléchis. » quand le prompt finit par `<think>\n` ;
    - `/_e2e/requests`.
  - `fake_openai.py` : `/_e2e/requests`. `stack.py` : `_entry`, entrées A, B et R.
  - `run_e2e.py` :
    - `s_local_server` : bascule vers le faux llama-server par `#model-picker` et `#model-picker-apply`, puis retour au cloud A ;
    - `LLAMA_OPTION`, `_pick_model`, `_fully_visible`, `Run.shot`, `Run.fake_calls`, `r.ev.wait`, `SCENARIOS`.
- Tests :
  - `tests/fake_engine.py` : `FakeEngine`, `booted_session`.
  - `tests/gguf_writer.py` : `write_gguf`.
  - `tests/test_model_servers.py` : transports simulés ; assertion `temperature`, `top_p`, `top_k`, `min_p`.
  - `tests/test_web_app.py` (pages servies) ; `tests/test_web_tokens.py`, avec les règles de la story 31 sur toutes les pages.
  - Moteurs de test à quatre arguments, **laissés intacts** : `tests/test_reasoning.py`, `tests/test_turn_cache.py`, `tests/test_reasoning_budget.py`.

## Tasks & Acceptance

**Execution:**
- Les tâches, avec leur chemin, leur action et leur raison, sont réparties dans la section « Incréments » ci-dessous. Elles s'exécutent dans l'ordre : incrément 1, puis 2, 3 et 4.
- Chaque incrément se termine ainsi :
  - ses critères `[In]` sont verts ;
  - ses tests pytest et son E2E passent ;
  - sa documentation est à jour ;
  - il est commité (message conventionnel en français, co-auteur Claude).
- Si le temps manque, on s'arrête à la fin d'un incrément livré, et l'incrément suivant est noté « non livré » dans cette spec et dans le rapport de la nuit.

**Acceptance Criteria:**
- [I1] Given l'atelier ouvert sur la pile E2E, when on clique « LLM nu » dans la barre haute, then `/llm` s'affiche avec le sélecteur de thème. Le thème choisi dans l'atelier s'applique, et toutes les commandes de la barre haute de l'atelier restent entièrement visibles sur une ligne à 1600 × 1000.
- [I1] Given le faux llama-server actif, when on découpe « Bonjour <|im_end|> 🙂 », then chaque token s'affiche avec son identifiant. `<|im_end|>` est un seul token marqué spécial, le total est égal au `token_count` de `llm_tokenized`, et le schéma montre « 2 048 » dimensions et « 1 004 » tokens de vocabulaire.
- [I1] Given le faux cloud A actif, when on découpe un texte, then la page dit que le tokenizer est chez le fournisseur et montre l'estimation, sans aucune puce.
- [I2] Given des réglages modifiés sur `/llm`, when on génère, then :
  - les valeurs arrivent au moteur ;
  - `model_call_started` du contexte `llm` les porte avec `source: screen` ;
  - les puces apparaissent une à une ;
  - le temps jusqu'au premier token puis le débit s'affichent ;
  - en fin de génération, la session est revenue en `idle`.
- [I2] Given une génération de l'écran, when on revient à l'atelier et qu'on envoie un message, then l'historique, la jauge et la Vue humain n'ont rien reçu de l'écran. Le tour a le même contexte que sans l'écran.
- [I2] Given un tour de l'atelier en cours, when on clique « Générer » sur `/llm`, then le bouton est désactivé avec la raison, et un appel direct reçoit 409.
- [I3] Given un changement de modèle fait dans l'atelier, when on ouvre `/llm`, then la section Chargement montre les étapes, leur durée et la mémoire, avec « RAM » pour un modèle local et « aucune mémoire sur ce poste » pour un modèle cloud.
- [I4] Given le moteur en processus, when on génère avec « Montrer les tokens candidats », then chaque puce ouvre cinq candidats avec leur probabilité, et le token tiré est marqué. Sur llama-server, Ollama ou le cloud, la case est grisée avec sa raison.

## Incréments

**Incrément 1 — Écran, tokenisation et vectorisation.** Petit et sûr, il ne touche pas à la génération. Critères : les trois `[I1]`.
- `content/llm_lab.yaml` (nouveau) et `src/wavestack/session/llm_lab.py` (nouveau, fonctions pures) --
  - `load_lab_content()` : `@cache`, pydantic, sur le modèle de `cloud.load_cloud_content`. Il porte le titre, les intertitres des six sections, les textes de la tokenisation, de la vectorisation et des légendes du schéma. Les incréments suivants y ajoutent les leurs.
  - `dimensions_from_header(meta) -> dict` : `{arch}.embedding_length`, `block_count`, `attention.head_count` (le maximum si c'est un tableau), `context_length`.
  - `token_rows(ids, pieces, specials, limit=512)` : `[{id, text, special}]` et `more`.
  - Tout en français, testable sans moteur.
- `src/wavestack/models/engine.py`, `servers.py` -- Méthode facultative `dimensions() -> dict | None`, que la session tolère absente, comme `snapshot` :
  - `LlamaCppEngine` : API llama.cpp ;
  - `OllamaRawEngine` : `llama_vocab_n_tokens` du `VocabTokenizer`, plus l'en-tête du blob ;
  - `LlamaServerEngine` : `n_vocab` et `n_embd` de `/v1/models`, gardés par `_read_metadata`, plus l'en-tête de `model_path` s'il est lisible.
- `src/wavestack/trace/catalog.py` -- `LlmTokenizedPayload` : `request_id`, `text`, `model_label`, `hosting`, `exact`, `tokenizer_fr`, `tokens`, `token_count`, `more`, `estimate | None`, `unavailable_fr | None`, `dimensions | None`, `dimensions_fr`. Ajouter `"llm_tokenized"` à `PAYLOAD_MODELS`.
- `src/wavestack/session/app_session.py` --
  - `llm_tokenize(text) -> str` : `SendRefused` hors `idle` ; soumis au worker ; émet `llm_tokenized` dans `scoped(context_id="llm", turn_id=None, step_id=f"llm{n}")`.
  - `lab_state() -> dict` pour `GET /api/llm_lab` : `content`, `content_error_fr`, `active_model`, `tokenizer {exact, reason_fr}` et `seq`.
  - Tokenise le texte brut, sans gabarit (`tokenize`, puis `token_pieces`).
- `src/wavestack/web/app.py` --
  - `GET /llm` (`FileResponse` de `llm.html`) et `GET /api/llm_lab`.
  - `LlmTokenizeIntention(text: str, min 1, max 2000)` sur `POST /api/intentions/llm_tokenize` : 409 sur `SendRefused`, réponse `{request_id}`.
- `src/wavestack/web/static/llm.html`, `llm.css`, `llm.js` (nouveaux) --
  - En tête, `theme.js` puis `fonts.css`, `tokens.css` et `llm.css`.
  - En-tête de page :
    - titre « LLM nu : l'intérieur du modèle » ;
    - modèle actif (« Local · … » ou « 🌐 RÉSEAU · … ») ;
    - lien « ← Atelier » (`/`) ;
    - `nav.page-tabs` si la story 25 est livrée ;
    - sélecteur de thème.
  - Section 1 « Tokenisation et vectorisation » :
    - zone de prompt, bouton « Découper en tokens » ;
    - des puces de tokens qui alternent deux fonds, id au-dessous, les tokens spéciaux marqués ;
    - le nombre de tokens et de caractères ;
    - un schéma en HTML et CSS : texte → tokens → identifiants → ligne de la table d'embedding (vocabulaire × dimension) → vecteur de *d* nombres → *L* couches, avec les dimensions réelles, ou « inconnue » et sa raison ;
    - pour un modèle cloud, `unavailable_fr` et l'estimation.
  - `llm.js` (module) : `GET /api/llm_lab`, puis `EventSource("/api/stream")` à partir de `seq`. La page filtre `context_id === "llm"` et `session_state`, et recharge sur un nouveau `server_instance`.
- `src/wavestack/web/static/index.html`, `app.js`, `app.css` --
  - Lien `<a id="llm-link" class="screen-link" href="/llm">LLM nu</a>` dans `.top-bar`, avant le sélecteur de thème, ou avant `#reset-button`.
  - Dans `applyEnvelope`, les événements `context_id === "llm"` ne vont qu'au journal (`store.journal`), avant tout `switch`.
  - Onglet « LLM nu » ajouté à `nav.page-tabs` de `diagnostic.html` et `models.html` s'ils existent.
- Tests : `tests/test_llm_lab.py` (nouveau), `tests/test_web_app.py`, `tests/test_web_tokens.py` --
  - tokenisation avec `FakeEngine` et un moteur sans `dimensions` ;
  - cloud sans tokenizer ;
  - plafond de 512 et `more` ;
  - dimensions sur un GGUF synthétique (`write_gguf`) ;
  - 409 hors `idle`, 422 vide ou trop long ;
  - YAML invalide : `harness_error`, 200 sur `/api/llm_lab` avec `content_error_fr` ;
  - `/llm`, `/static/llm.js` et `/static/llm.css` en 200 ;
  - les pages `llm.*` couvertes par la règle « jetons seulement » et la présence de `theme.js`.
- `tools/e2e/fake_local_server.py` -- `meta` : `n_vocab: 1004`, `n_embd: 2048`.
- `tools/e2e/run_e2e.py`, `README.md` -- Nouveau scénario `s_llm_screen`, placé après `context_window` s'il existe, sinon après `local_server`, et avant `relaunch`. Il vérifie :
  - le lien, visible et entièrement visible (`_fully_visible`) ;
  - la tokenisation sur le faux cloud A (raison), puis sur le faux llama-server, choisi dans le sélecteur de l'atelier comme dans `s_local_server` ;
  - le retour au faux cloud A en fin de scénario.
  Capture `NN-llm-nu-tokenisation`, au prochain numéro libre.
- Docs -- EXPERIENCE.md :
  - ligne « Écran LLM nu » de la table Surfaces ;
  - le lien dans la ligne Barre haute ;
  - patrons `llm-screen` et `token-chip`.
  DESIGN.md : composants `token-chip` et `embedding-diagram`, faits de jetons existants. SPEC.md : nouvelle capacité « Écran LLM nu », au numéro CAP suivant, partie 1. README : section « Écran LLM nu ». Spine : AD-2 (`llm_tokenized`, contexte `llm`), AD-18 (`/llm`), AD-19 (`llm_lab.yaml`).

**Incrément 2 — Réglages d'échantillonnage, lecture du prompt, génération token par token.** Critères : les trois `[I2]`.
- `src/wavestack/models/engine.py` -- `Sampling`, dataclass figée : `temperature`, `top_k`, `top_p`, `min_p`.
  - `DEFAULT_SAMPLING = Sampling(0.7, 20, 0.8, 0.0)`.
  - Bornes `SAMPLING_BOUNDS` : température 0 à 2, top-k 1 à 100, top-p 0,05 à 1, min-p 0 à 0,5.
  - `Fragment` gagne `token_id: int | None = None` et `piece: bytes | None = None`.
  - `LlamaCppEngine.complete(..., *, sampling=None)` : `None` vaut `DEFAULT_SAMPLING`. Il remplit `token_id` et `piece`.
  - Les constantes sont supprimées et leurs imports suivent.
- `src/wavestack/models/servers.py` -- `_sampling(sampling)` ; `complete(..., *, sampling=None)` sur les deux adaptateurs, qui mettent le morceau reçu dans `piece`.
- `src/wavestack/config.py`, `wavestack.toml`, `tools/e2e/stack.py` --
  - `CloudModel.sampling: list[Literal["temperature", "top_p"]] = []` ;
  - préréglages Groq et Mistral à `["temperature", "top_p"]`, avec un commentaire ;
  - entrées A, B et R de la pile E2E identiques.
- `src/wavestack/cloud.py` -- `chat_fields(..., sampling: Sampling | None = None)` : les champs déclarés, après la limite de sortie, **seulement si `sampling` est donné**. Les corps de l'atelier restent donc identiques.
- `src/wavestack/models/openai_chat.py` -- `run_call(..., sampling_trace=None)`, qui le met dans `model_call_started`.
- `src/wavestack/trace/catalog.py` --
  - `SamplingTrace` : `temperature`, `top_k`, `top_p`, `min_p`, chacun `None` s'il n'est pas envoyé ; `source: harness|screen|provider` ; `note_fr`.
  - `ModelCallStartedPayload.sampling: SamplingTrace | None = None`.
  - Nouveaux payloads :
    - `llm_generation_started` : `request_id`, `prompt`, `rendered`, `prompt_tokens`, `exact`, `sampling`, `reserve`, `reasoning`, `phase_label` ;
    - `llm_token` : `request_id`, `index`, `token_id | None`, `text`, `channel`, `elapsed_ms` ;
    - `llm_generation_ended` : `request_id`, `status: completed|cancelled|limit|error`, `duration_ms`, `read_tps | None`, `reasoning_tokens`, `answer_tokens`, `message_fr | None`.
  - `SessionState` gagne `llm_lab`.
- `src/wavestack/session/app_session.py` --
  - `_call_model(..., sampling=None, on_token=None)` :
    - les paramètres ne sont passés au moteur (`**extra`) que s'ils sont donnés, si bien que les moteurs de test à quatre arguments restent valides ;
    - `on_token(fragment, channel)` est appelé pour chaque fragment dont la pièce ou le texte n'est pas vide ;
    - la trace vaut `DEFAULT_SAMPLING` en `source: harness` pour l'atelier.
  - Les appels cloud de l'atelier tracent `source: provider`.
  - `llm_generate(prompt, sampling, reasoning=False) -> str` : comme `_start`, sous les verrous, `idle` requis, puis `self.state, self.reason_fr = "llm_lab", _LAB_FR`, `self._cancel = CancelToken()` et `submit(self._run_lab, …)`.
  - `_run_lab`, en portée `llm{n}` avec `origin="model"` :
    - sauvegarde de l'état principal ;
    - rendu d'un seul message, par `render_context` ou par `render_chat_body` avec `chat_fields(entry, reserve, reasoning, sampling)` ;
    - `llm_generation_started` ;
    - appel local : `_call_model(rendered, cancel, (), reserve, reasons=reasoning, sampling=…, on_token=…)`, qui émet un `llm_token` par fragment ;
    - appel cloud : `run_call` **directement** (ni `context_reconciled` ni `_ratio`), avec les `model_delta` comme fragments ;
    - `llm_generation_ended`, avec `read_tps = evaluated_tokens / prompt_ms` quand `prompt_ms > 0` ;
    - restauration de l'état principal, sinon `_cache_cause = "llm"` ;
    - `idle` dans le `finally`.
  - `stop()` couvre `llm_lab`.
  - `_PREFIX_CAUSES_FR["llm"]` : « L'écran « LLM nu » a occupé le cache du moteur{why}. »
  - `_LAB_FR` : « L'écran « LLM nu » génère une réponse : attendez sa fin ou arrêtez-la. »
  - `lab_state()` ajoute `sampling {defaults, bounds, supported: {nom: raison_fr | null}, source_fr}`.
- `src/wavestack/web/app.py` -- `LlmGenerateIntention` : `prompt` (1 à 2 000) et `sampling` (4 champs bornés par `Field`), sur `POST /api/intentions/llm_generate`. Le champ `reasoning` n'arrive qu'à l'incrément 3 ; d'ici là, un modèle qui raisonne toujours suit sa déclaration (`chat_fields`, réserve `reserve_for`). Réponse `{request_id}`, 409 ou 422.
- `llm.html`, `llm.css`, `llm.js` --
  - Section 2 « Réglages d'échantillonnage » : un curseur et un champ numérique par réglage, l'explication tirée du YAML, « Valeurs du harnais : … », et « Revenir aux valeurs du harnais ». Un réglage non supporté est désactivé, sa raison visible.
  - Section 4 « Lecture du prompt » :
    - prompt rendu avec le gabarit visible et son nombre de tokens ;
    - chronomètre du premier token, ancré sur `model_call_started.ts` puis remplacé par `model_call_ended.prompt_ms` ;
    - débit de lecture `read_tps`.
  - Section 5 « Génération » : une puce par `llm_token`, au fil de l'eau ; compteur ; débit final (`output_tps`) ; bouton « Arrêter » (`/api/intentions/stop`). Pour un modèle cloud, le texte « fragments reçus du fournisseur, pas des tokens un par un ».
  - « Générer » est désactivé hors `idle`, avec `reason_fr`.
- `src/wavestack/web/static/app.js` -- `SESSION_STATES.llm_lab = "écran LLM nu"`. Dans `eventSummary`, `model_call_started` affiche `phase_label · T 0,7 · top-k 20 · top-p 0,8 · min-p 0` quand `sampling` est là.
- Tests : `tests/fake_engine.py`, `tests/test_llm_lab.py`, `tests/test_model_servers.py`, `tests/test_cloud.py` --
  - `FakeEngine.complete(..., *, sampling=None)` note `self.samplings`.
  - Paramètres transmis :
    - `FakeEngine` ;
    - corps `/completion` et `options` d'Ollama, sur le transport simulé ;
    - corps chat avec la déclaration (seulement les champs déclarés) et sans elle (aucun).
  - Trace de `model_call_started.sampling` : atelier en `harness`, écran en `screen`, cloud de l'atelier en `provider`.
  - Suite des événements de l'écran :
    - `session_state` `llm_lab`, `llm_generation_started`, puis `model_call_started` avec `context_id="llm"` ;
    - autant de `llm_token` que de tokens produits par `FakeEngine` ;
    - `model_call_ended`, `llm_generation_ended`, puis `idle`.
  - Aucun `context_*` dans `llm`.
  - `_history` inchangé, et le tour suivant de l'atelier donne le même rendu.
  - État restauré (`FakeEngine` avec état) ; cause `llm` sans état (`stateful=False`).
  - Arrêt ; 409 et 422.
- `tools/e2e/run_e2e.py` -- Compléter `s_llm_screen` :
  - sur le faux llama-server, régler T 0,2, top-k 5, top-p 0,9 et min-p 0,05, puis générer ;
  - le dernier corps `/completion` de `/_e2e/requests` porte ces valeurs, et `model_call_started` (contexte `llm`) aussi ;
  - le nombre de puces croît entre deux relevés ;
  - « Premier token après … ms » et le débit sont affichés ;
  - la Vue humain de l'atelier est inchangée (même nombre de bulles) ;
  - sur le faux cloud A, le dernier corps porte `temperature` et `top_p`, et top-k est désactivé avec sa raison.
  Capture `NN-llm-nu-generation`.
- Docs -- EXPERIENCE.md :
  - patrons `sampling-controls` et `token-stream` ;
  - état `llm_lab` dans les State Patterns.
  README : l'échantillonnage devient un paramètre de chaque appel, réglable dans l'écran ; ajouter la clé `sampling` des modèles cloud. Spine : AD-2 (kinds, `sampling`), AD-3 (état `llm_lab`, intentions de classe b), AD-5 (`complete(..., sampling)`), AD-20 (`sampling` déclaré). SPEC : partie 2 de la capacité.

**Incrément 3 — Chargement du modèle et raisonnement.** Critères : `[I3]`, plus les critères de raisonnement ci-dessous (tests et E2E).
- `src/wavestack/trace/catalog.py` -- `ModelLoadStepPayload` : `model`, `step: release|probe|check|engine|ready`, `label_fr`, `elapsed_ms`, `rss_bytes | None`. `ModelLoadEndedPayload.memory: LoadMemory | None = None`, avec `rss_before`, `rss_after`, `cost_bytes`, `where_fr`.
- `src/wavestack/session/app_session.py` --
  - Dans `_load`, en portée `off_turn`, émettre `model_load_step` à chaque étape franchie, avec `process_rss()` :
    - libération ;
    - sonde, si elle a lieu ;
    - contrôle du budget ;
    - création du moteur dans `_install` : « Lecture du fichier et copie des poids en mémoire vive », ou « Connexion à {serveur} », ou « Préparation, sans chargement (modèle cloud) » ;
    - prêt.
  - `memory` dans `model_load_ended{ok}`, dont `where_fr` :
    - fichier : « Mémoire vive (RAM) du processeur, pas de carte graphique : … » ;
    - modèle servi : « chargé par {serveur}, dans son propre processus, en RAM de ce poste » ;
    - cloud : « aucune mémoire sur ce poste : le modèle tourne chez {fournisseur} ».
  - `lab_state()` ajoute :
    - `last_load` : les enveloppes du dernier chargement, lues dans le journal ;
    - `reasoning {mode: never|toggle|always|unknown, reason_fr, budget, reserve}`, par `reasoning_mode` (story 25) ou, à défaut, par `Capabilities` avec les mêmes règles.
  - `LlmGenerateIntention.reasoning: bool = False`, puis `llm_generate(reasoning=True)` :
    - mode `never` ou `unknown` : 409 ;
    - `always` : il est forcé ;
    - réserve de 1 536 et budget `cfg.reasoning_budget_tokens` : `_call_model` émet `reasoning_cut` dans `llm` ;
    - `llm_generation_ended` compte `reasoning_tokens` et `answer_tokens`.
- `llm.html`, `llm.css`, `llm.js` --
  - Section 3 « Chargement du modèle » :
    - frise des étapes avec leur durée, chronomètre en direct pendant un chargement ;
    - mémoire (`_size`, mis en forme côté session dans `label_fr` et `where_fr`), avec la mention « en local : RAM du CPU, pas de GPU » ;
    - lien « Changer de modèle dans l'atelier ».
    La page relit `/api/llm_lab` sur `model_load_ended`.
  - Section 6 « Raisonnement » :
    - interrupteur, grisé avec sa raison, ou verrouillé « toujours » ;
    - deux couloirs, « Réflexion » puis « Réponse » ;
    - compteurs, budget, marque de coupe avec `reasoning_cut.message_fr`.
- `src/wavestack/web/static/app.js` -- Dans `eventSummary`, `model_load_step` rend `label_fr · durée`.
- Tests : `tests/test_llm_lab.py`, `tests/test_model_switch.py` --
  - étapes et ordre pour un fichier (`FakeEngine`), un modèle servi et un cloud ;
  - `memory` avec `rss_fn` injecté ;
  - raisonnement : variable de gabarit posée, `reasoning_cut` dans `llm` avec un budget bas (modèle de `tests/test_reasoning_budget.py`), cloud « toujours », 409 sans raisonnement ;
  - les tests existants de chargement restent verts, puisque le nouvel événement est additif.
- `tools/e2e/run_e2e.py` -- `s_llm_screen` :
  - après le passage au faux llama-server, `/llm` montre les étapes, dont « Connexion », et « dans son propre processus » ;
  - après le retour au cloud A : « aucune mémoire sur ce poste » ;
  - raisonnement sur le faux llama-server : le couloir « Réflexion » contient « Je réfléchis. » et la réponse suit.
  Capture `NN-llm-nu-chargement-raisonnement`.
- Docs -- EXPERIENCE, SPEC (partie 3), README, spine AD-2 (`model_load_step`, `memory`) et AD-8 (mémoire affichée).

**Incrément 4 — Probabilités des tokens candidats.** Critères : `[I4]`.
- `src/wavestack/session/llm_lab.py` (ou `models/candidates.py`) -- `candidates_from_logits(logits, sampling, chosen_id, n=5)`, avec numpy importé dans la fonction. Il calcule :
  - `p` : softmax à température 1 ;
  - `kept` : dans top-k, puis top-p cumulé sur les probabilités renormalisées, puis min-p, soit l'ordre de llama.cpp ;
  - `p_sampled` : softmax de `logits / T` restreint aux gardés ; T = 0 donne 1 pour le plus probable.
  Il renvoie les n premiers, plus le token tiré s'il n'en fait pas partie.
- `src/wavestack/models/engine.py` -- `Fragment.candidates: tuple | None = None`. `LlamaCppEngine.complete(..., candidates: int = 0)` lit, à chaque token rendu par `generate`, `llama_get_logits_ith(self._llm.ctx, -1)` sur `n_vocab()` flottants, puis `candidates_from_logits`. Le texte d'un candidat vient de `token_pieces`.
- `src/wavestack/trace/catalog.py`, `app_session.py`, `web/app.py` --
  - `llm_token.candidates: list[{token_id, text, p, kept, p_sampled, chosen}] | None`.
  - `lab_state().candidates {available, reason_fr, n}` : disponible pour un fichier seulement, avec la raison pour llama-server, Ollama et le cloud.
  - `LlmGenerateIntention.candidates: bool = False`, avec 409 si indisponible.
  - `_call_model` passe `candidates` au moteur seulement s'il est non nul.
- `llm.js`, `llm.css` -- Case « Montrer les tokens candidats », grisée avec sa raison. Au survol, au focus ou au clic d'une puce, un encart avec cinq barres en % (`p`), la marque « écarté par top-k/top-p/min-p » et la « chance d'être tiré » (`p_sampled`), le token tiré mis en avant. Explications en YAML.
- Tests : `tests/test_llm_lab.py`, `tests/fake_engine.py` --
  - fonction pure sur des logits synthétiques : température, glouton, top-k, top-p, min-p, token tiré hors des cinq ;
  - `FakeEngine(candidates_script=…)` jusqu'à `llm_token.candidates` ;
  - raisons d'indisponibilité ;
  - un test `model` (sauté sans `WAVESTACK_TEST_GGUF`) sur le vrai moteur : somme des `p` ≤ 1, et le token tiré est parmi les gardés.
- `tools/e2e/run_e2e.py` -- Sur le faux llama-server, la case est grisée et sa raison contient « llama-server ». Même contrôle sur le cloud A.
- Docs -- EXPERIENCE (patron `candidates-popover`), SPEC (partie 4), README, spine AD-5 (`candidates`, lecture de la dernière position).

## Spec Change Log

## Review Triage Log

## Design Notes

- **Pourquoi une page et non un volet.** L'écran n'a pas de briques et ne partage ni la jauge ni l'historique. Une page, sur le modèle de `/models` (story 25), ne touche pas à la disposition des cinq volets. Le journal reste unique : la page lit le même flux SSE et filtre le contexte `llm`.
- **Échantillonnage de llama.cpp.** La chaîne applique top-k, top-p et min-p sur les logits bruts, puis la température sur les tokens gardés. D'où les trois nombres d'un candidat : `p` (probabilité du modèle), `kept` et `p_sampled` (chance réelle d'être tiré). À température 0, le tirage est glouton (`add_greedy`).
- **Probabilités sans `logits_all`.** `generate` rend chaque token juste après l'avoir tiré, alors que le contexte llama.cpp tient encore les logits de cette position. Les lire à cet instant coûte n_vocab flottants par token, soit ≈ 0,6 Mo et environ 1 ms pour 151 936 tokens, contre environ 2,5 Go pour `logits_all`.
- **Pièces et fragments.** Le moteur en processus donne l'id et la pièce de chaque token. llama-server et Ollama rendent un morceau de flux, en général un token. Le cloud rend des deltas regroupés : la page les appelle « fragments », sans les présenter comme des tokens.
- Exemple de `llm_token` (incrément 4) :

```json
{"request_id": "llm3", "index": 7, "token_id": 12095, "text": " Paris", "channel": "text", "elapsed_ms": 812,
 "candidates": [{"token_id": 12095, "text": " Paris", "p": 0.61, "kept": true, "p_sampled": 0.83, "chosen": true},
                {"token_id": 30421, "text": " Lyon", "p": 0.12, "kept": true, "p_sampled": 0.11, "chosen": false}]}
```

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, `tests/test_llm_lab.py` compris ; aucun test existant supprimé
- `node --check src/wavestack/web/static/llm.js && node --check src/wavestack/web/static/app.js` -- expected: pas d'erreur (si `node` est présent)
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; scénario `llm_screen` passé pour les incréments livrés ; captures `NN-llm-nu-*` écrites dans `tools/e2e/screenshots/` et listées dans `tools/e2e/README.md`

**Manual checks (if no CLI):**
- Relire les captures : les puces sont lisibles dans les deux thèmes, le schéma de vectorisation est compréhensible sans légende orale, « RÉSEAU » est présent pour le cloud et aucune couleur ne sort des jetons.

## Décisions prises par défaut

- **Quatre incréments au lieu de trois.** La tokenisation et la vectorisation ne demandent aucun changement du moteur. Elles forment un premier incrément petit et sûr, puis viennent les réglages et la génération. L'ordre du contexte (tokenisation, réglages et génération, puis chargement et raisonnement, puis probabilités) est gardé.
- **Page `/llm`, lien « LLM nu » dans la barre haute**, et onglet dans `nav.page-tabs` si la story 25 est livrée. La story 30 ajoutera son propre lien ; un menu « Écrans » pourra les réunir plus tard. Le nom « LLM nu » reprend la demande, bien que le module 1 de l'atelier porte le même nom.
- **Un nouvel état `llm_lab`** plutôt que `turn` (même principe que `rag_lab` de la story 30). L'atelier affiche une raison juste, `stop` sait quoi arrêter, et `turns`, les numéros `t{n}` et `turn_ended` restent propres à l'atelier.
- **Contexte de trace `llm`, `turn_id` nul.** L'atelier ignore ces événements sans rien casser : ses réducteurs cherchent un tour. Un garde explicite est ajouté.
- **L'écran n'appelle pas `_call_model_chat`**, qui réconcilie la jauge principale et apprend le ratio d'estimation : il appelle `run_call` directement.
- **Échantillonnage passé en mot-clé seulement quand l'écran le demande.** Les requêtes de l'atelier restent octet pour octet identiques, et les moteurs de test à quatre arguments restent valides sans modification.
- **Cloud : `sampling` déclaré par modèle**, vide par défaut, soit « réglé par le fournisseur ». Groq et Mistral déclarent `temperature` et `top_p`, les deux champs de l'API compatible OpenAI. Top-k et min-p ne sont jamais envoyés à un fournisseur.
- **Pas de `max_tokens` réglable** : la réserve d'AD-9 (512, ou 1 536 avec raisonnement) s'applique, comme dans l'atelier.
- **Probabilités : moteur en processus seulement**, comme le demande le contexte. Le `n_probs` de llama-server et les `logprobs` d'Ollama ou des fournisseurs sont écartés : leur format varie selon la version, et ils ne peuvent pas être vérifiés ici. Leur indisponibilité est expliquée. En E2E, on ne vérifie que la raison ; l'affichage des candidats passe par pytest et par le PC.
- **Candidats : 5**, plus le token tiré s'il n'en fait pas partie.
- **Tokenisation sans gabarit** : on découpe le texte saisi. Le prompt rendu avec le gabarit apparaît à la section « Lecture du prompt ».
- **Plafonds** : 2 000 caractères de prompt et 512 puces affichées, pour garder la page fluide en projection.
- **Dimensions** : le moteur en processus d'abord, puis l'en-tête GGUF, puis `/v1/models` pour llama-server. Le vocabulaire vient toujours du tokenizer, car `gguf_meta` saute les tableaux longs. Pour un cloud, elles sont « inconnues ». Les chiffres sont mis en forme par la session.
- **Chargement non déclenché depuis la page** : un lien renvoie au sélecteur de l'atelier, et la page montre le dernier chargement, relu dans le journal, ou le chargement en cours, en direct. On évite ainsi de dupliquer l'avertissement cloud et le budget.
- **Mémoire au chargement** : la RSS avant et après, plus le coût compté par le budget. Le texte prévient que les poids en mmap montent en RAM au premier appel.
- **Pas de restitution de la dernière génération après un rechargement de la page** : seuls le dernier chargement et l'état de la session sont relus. On s'épargne une projection lourde pour un gain faible.
- **Aucun nouveau jeton de couleur** : les puces alternent des fonds existants, sans jumeau `-dark` à dessiner (story 31).
- **SPEC.md** : une seule capacité nouvelle, au numéro CAP libre suivant, complétée à chaque incrément.

## À vérifier sur PC

- **Vitesse token par token**
  - **Geste** : PowerShell, `uv run wavestack`, Qwen3.5-2B GGUF actif. Dans Chrome, cliquer « LLM nu », saisir « Explique en deux phrases ce qu'est un token. », puis « Générer ».
  - **Attendu** : les puces arrivent une à une ; premier token, puis débit.
  - **Critère** : premier token en moins de 10 s (NFR-1, LLM nu), débit affiché ≥ 8 tokens/s, pas de saccade de plus de 1 s entre deux puces.
  - **Moyen** : Claude in Chrome ; mesure croisée par script AppSession.
- **Réglages réellement appliqués**
  - **Geste** : même prompt, T 0 deux fois de suite, puis T 1,5 deux fois.
  - **Attendu** : à T 0, deux réponses identiques ; à T 1,5, des réponses différentes.
  - **Critère** : identité exacte à T 0 ; au moins un token différent à T 1,5.
  - **Moyen** : script AppSession ou Playwright.
- **Probabilités sur le vrai moteur**
  - **Geste** : Qwen3.5-2B, « Montrer les tokens candidats » coché, prompt « La capitale de la France est ». Survoler la première puce.
  - **Attendu** : cinq candidats, « Paris » en tête.
  - **Critère** : somme des `p` affichés ≤ 100 %. Le token tiré est marqué, et le débit baisse de moins de 20 % par rapport à la case décochée.
  - **Moyen** : Claude in Chrome, puis `pytest -m model` avec `WAVESTACK_TEST_GGUF`.
- **Dimensions réelles**
  - **Geste** : découper un texte avec Qwen3.5-2B, puis 4B.
  - **Attendu** : dimension d'embedding, couches, têtes et vocabulaire conformes à la fiche du modèle.
  - **Critère** : égalité avec l'en-tête GGUF (`gguf_meta`).
  - **Moyen** : script.
- **Chargement en RAM**
  - **Geste** : Edge, Outlook et Teams fermés. Dans l'atelier, passer du 2B au 4B, puis ouvrir `/llm`.
  - **Attendu** : les étapes et leur durée s'affichent, avec la mémoire et « RAM du CPU, pas de GPU ».
  - **Critère** : durée totale égale à celle de `model_load_ended` à 100 ms près. RSS après chargement à ±15 % du Gestionnaire des tâches (« Mémoire », processus python), mesuré après un premier appel.
  - **Moyen** : Claude in Chrome et Gestionnaire des tâches à la main.
- **Raisonnement et coupe**
  - **Geste** : 4B, raisonnement activé, prompt « Combien font 17 × 23 ? Détaille. ».
  - **Attendu** : le couloir « Réflexion » se remplit, puis « Réponse ». Si le budget est atteint, la marque de coupe apparaît avec son message.
  - **Critère** : compteurs Réflexion + Réponse égaux aux tokens de sortie. Coupe au budget configuré ±1 token.
  - **Moyen** : Claude in Chrome.
- **Ollama et llama-server**
  - **Geste** : dans l'atelier, choisir un modèle Qwen servi par Ollama, puis llama-server lancé avec `-c 4096`. Sur `/llm`, générer avec T 0,2 et top-k 5.
  - **Attendu** : la génération marche ; les candidats sont grisés avec leur raison.
  - **Critère** : le journal d'Ollama ou de llama-server montre les options reçues, et `model_call_started.sampling` du contexte `llm` a les mêmes valeurs.
  - **Moyen** : à la main (journal du serveur) et Playwright.
- **Cloud**
  - **Geste** : Groq gpt-oss-120b, clé saisie, puis `/llm` avec T 0,2.
  - **Attendu** : réponse en fragments, top-k et min-p grisés « non réglables chez Groq », raisonnement « toujours ».
  - **Critère** : aucun 400 du fournisseur, et le corps tracé (`outbound_request`) contient `temperature: 0.2`.
  - **Moyen** : Claude in Chrome.
- **Lisibilité en salle**
  - **Geste** : projeter `/llm` en thème clair puis sombre, zoom 125 %, dans Chrome puis Edge.
  - **Attendu** : puces, identifiants, schéma et encart des candidats lisibles.
  - **Critère** : Anaël lit un identifiant de token à 3 m. Aucune section coupée à 1600 × 1000.
  - **Moyen** : à la main (œil humain).
- **Atelier intact**
  - **Geste** : dans l'atelier, envoyer deux messages, faire une génération sur `/llm`, puis envoyer un troisième message dans l'atelier.
  - **Attendu** : le troisième tour ne reprend rien de l'écran. Avec le moteur en processus, aucun `prefix_not_reused` à cause `llm`.
  - **Critère** : pas de relecture complète du contexte, temps du troisième tour comparable au deuxième (±20 %).
  - **Moyen** : script AppSession.
