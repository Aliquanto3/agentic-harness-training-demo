---
title: 'Lot 5c-3 : génération exécutée par le modèle actif dans l''Atelier RAG'
type: 'feature'
created: '2026-10-05'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '8a0cad07447fad62c1bf331d0aed681723a5cc9d'
context:
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/stories/5c-2-rerankers-declares.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'étape Generation de l'Atelier RAG n'est jamais exécutée : elle dit « non exécutée » et montre ce que le modèle recevrait ; la tuile Réponse reste vide, et l'option de la ligne (« Modèle actif de l'atelier ») annonce une génération qui n'a pas lieu.

**Approach:** La ligne Generation propose deux options, « Modèle actif de l'atelier » (par défaut, exécutée) et « Ne pas générer » (le comportement d'avant). Exécutée, l'étape envoie au modèle actif le prompt système effectif de l'atelier principal, puis le contexte construit par la chaîne (son introduction et ses extraits) et la question, en streaming, avec la progression en tokens et « Arrêter » ; le focus montre le prompt envoyé et la réponse, la tuile Réponse montre la réponse.

**Décisions (Anaël, 2026-10-05, SPEC.md « Décisions de 5c ») :**
- Dépense comptée dans celle de la session (FinOps/GreenOps, `consumption_updated`), comme l'Atelier LLM ; jamais dans la jauge d'un tour (aucun tour).
- Prompt système : celui de l'atelier principal tel qu'un tour l'enverrait (personnalisé ou par défaut), rien si la brique « prompt système » est éteinte.
- Bornes de l'atelier principal : réserve de sortie d'un tour (`_reserve_of`) et budget de raisonnement (`_reasoning_on`, `[reasoning] budget_tokens`).
- Sans modèle chargé, l'étape est sautée avec sa raison et le reste de la chaîne se termine.
- Le cache de préfixe de la conversation de l'atelier est écrasé (local) : accepté, avec une cause « atelier RAG » à la ligne « Cache non réutilisé ».

## Boundaries & Constraints

**Always:**
- AD-1 : statut, chiffres, prompt, réponse, progression viennent de la session (événements `rag_lab_*`, `model_delta` du contexte `rag_lab`) ; la page ne calcule que la mise en page.
- Appel local par `_call_model` (événements `model_*`, CodeCarbon, `_count_impact`) entre `_save_main_state` et `_lab_restore(saved, "rag_lab")` ; appel cloud par `_lab_cloud_call` (`run_call` direct : `record_spend`, ni `context_reconciled` ni ratio). Portée `rag_lab` (pas de `turn_id`).
- Prompt plus long que la place utile (`fenêtre − réserve`) : rien n'est envoyé, l'étape en erreur avec les chiffres (comme `session.llm_lab.too_long`).
- Fin `limit` : étape `ok` avec avertissement « réponse coupée à N tokens » ; `cancelled` : étape et run arrêtés ; erreur du modèle ou du fournisseur : étape en erreur, la session revient à `idle`.
- `rag_lab_stage_progress` pendant la génération : `done` = tokens produits, `total` = réserve, au plus dix par seconde ; la page dit « n / N tokens ».
- Textes nouveaux en fr, en, de (`rag_lab.yaml`, `messages.yaml`, `ui.yaml` pour la cause), validés par `RagLabContent` ; carrefours en ajouts seulement.
- Ajouts de champs aux payloads `RagLab*` optionnels (valeur par défaut) : les journaux anciens se relisent.

**Never:** toucher la jauge, l'historique ou la conversation de l'atelier principal ; outils, mémoire globale ou skills dans le prompt envoyé ; nouvel endpoint ; modifier `app.js` (les `model_*` sans tour y sont déjà ignorés) ; changer les autres étapes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Chaîne livrée, modèle local | modèle chargé, option `active` | `rag_lab_stage_started` puis progressions, `model_delta`, `stage_ended` `ok` : `output_text` = réponse, `prompt_text` = prompt rendu, faits (modèle, tokens du prompt, tokens produits / réserve) ; run `ok` ; `consumption_updated` émis | N/A |
| Brique prompt système éteinte | `system_prompt` hors `effective` | aucun message système dans le prompt | N/A |
| Ne pas générer | option `not_run` | statut `not_run`, texte « vous avez choisi de ne pas générer », comme avant | N/A |
| Aucun modèle | moteur absent | étape `skipped`, raison dédiée ; run `ok` ; option annotée dès le catalogue | N/A |
| Arrêter pendant la génération | « Arrêter » | étape `cancelled`, run `cancelled`, état `idle` | N/A |
| Borne atteinte | sortie = réserve | étape `ok`, `warning_text` de coupe | N/A |
| Prompt trop long | tokens > place utile | rien envoyé | étape `error`, chiffres dans `error_text` |
| Cache principal non restauré | local, snapshot impossible, contexte principal en cache | prochain tour : `prefix_not_reused` cause `rag_lab` | N/A |
| Étape amont en échec | chaîne arrêtée avant | Generation `skipped`, aucun appel | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `OPTIONS["generation"]` (l. 74) → `("active", "not_run")` ; `default_pipeline` (l. 385) → `active` ; `_run_chain` (l. ~1441) envoie `generation` `active` par le chemin normal (started / ended, `cancelled` vérifié avant) ; `_run_stage` route vers un nouveau `_generation_run` ; `_generation` (l. 2143) reste pour `not_run`. `LabDeps` : nouveau `generator: Callable[[GenerationAsk], Generated] | None = None` (défaut : étape sautée) ; `_Result.prompt_text`. `RagLabContent` : nouveaux champs (progression en tokens, textes du focus).
- `src/wavestack/session/app_session.py` -- `_run_rag_lab` (l. 9369) : `generator=` vers une nouvelle `_rag_lab_generate` sur le modèle de `_run_lab` (l. ~8880-9060 : `render_context` local, `render_chat_body` cloud, `_save_main_state`/`_lab_restore`, `_lab_cloud_call` l. 9075) mais avec `build_turn_state()`, `_reserve_of(state)`, `_reasoning_on(state)`, et messages système (`state.system_prompt` si `"system_prompt" in state.effective`) puis utilisateur (`Part(RAG_EXCERPT, context, "rag", "rag.retriever")`, `Part(USER_MESSAGE, question)`). `_rag_lab_catalog` (l. 9170) : option `active` nommée d'après `active_model()`, note sans modèle. `run_rag_lab` docstring (« nothing is generated »).
- `src/wavestack/trace/catalog.py` -- `PrefixCause` (l. 652) + `"rag_lab"` ; `RagLabStageEndedPayload` + `prompt_text: str | None = None`.
- `src/wavestack/web/static/rag.js` -- `applyEnvelope` (l. 1005) : `model_delta` de contexte `rag_lab` accumulé sur l'étape generation en cours ; `statusLine` (l. 1075) : unité tokens pour la génération ; `focusRun` (l. 735) : prompt envoyé (`<details>`), texte en direct pendant le run, réponse ; `subtitle` (l. 577) : tuile `answer` = réponse du run montré. `rag.css` : bloc du prompt, coupe de la tuile.
- `content/rag_lab.yaml` + `content/i18n/{en,de}/rag_lab.yaml` -- `options.generation.{active,not_run}`, `generation_not_run_text`, `steps.generation.note_text` (retirée), `components.answer.note_text`, `components.llm.note_text`, nouveaux champs.
- `content/messages.yaml` ×3 -- `rag_lab.generation.*` (entrée, faits, sauté sans modèle, trop long, coupé), `session.prefix.causes.rag_lab`, libellé `session.rag_lab.generation_active`.
- `content/ui.yaml` ×3 -- `main.orch.prefix_causes.rag_lab` (« Atelier RAG », « RAG workshop », « RAG-Werkstatt »).
- Tests -- `tests/test_rag_lab.py` (l. 92-131 : la génération exécutée par `FakeEngine(output="Quatorze caractères.")`, l. 274, 977-991) ; nouveau `tests/test_rag_lab_generation.py` (matrice) ; `tests/test_i18n.py` si de nouvelles clés l'exigent.
- E2E -- `tools/e2e/run_e2e.py` l. 13671, 13727-13730, 13884, 14001-14008 (« non exécutée » → réponse) ; écrit ici, lancé en fin de lot.
- Docs -- `docs/guide.md` l. 277-285 (Generation exécutée).

## Tasks & Acceptance

**Execution:**
- [x] `trace/catalog.py` -- cause `rag_lab`, champ `prompt_text`.
- [x] `rag/lab.py` -- options, chaîne livrée, `GenerationAsk`/`Generated`, `_generation_run` (progression, statuts, faits, avertissement), textes.
- [x] `app_session.py` -- `_rag_lab_generate`, branchement dans `LabDeps`, option du catalogue.
- [x] contenus ×3 (`rag_lab.yaml`, `messages.yaml`, `ui.yaml`).
- [x] `rag.js`, `rag.css` -- direct, progression en tokens, focus, tuile Réponse.
- [x] tests pytest de la matrice ; E2E mis à jour ; `docs/guide.md`.

**Acceptance Criteria:**
- Given un modèle chargé et la chaîne livrée, when on lance la chaîne, then Generation s'exécute, la réponse est dans `output_text`, la dépense de la session avance et aucun événement ne porte de `turn_id`.
- Given la langue en ou de, when on lit options, raisons, faits et avertissements, then ils sont traduits.
- Given `uv run ruff check .` et `uv run pytest` ciblé, when on les lance, then tout est vert.

## Implementation Notes

- `rag/lab.py` : `OPTIONS["generation"] = ("active", "not_run")`, chaîne livrée sur `active`. `GenerationAsk` (contexte, question, step id, progression, test d'arrêt) et `Generated` (statut `completed` / `limit` / `cancelled` / `error` / `too_long`, prompt rendu, tokens, fenêtre, réserve, réponse, prompt système envoyé ou non). `_generation_run` : sauté sans `generator` ou sur `StageSkipped` de la session (entrée « recevrait » gardée) ; `too_long` → `StageFailed` chiffré (`rag_lab.generation.too_long`), prompt montré ; `cancelled` → `LabCancelled` (réponse partielle gardée) ; `limit` → `ok` + avertissement `rag_lab.generation.cut`. `StageFailed`, `StageSkipped` et `LabCancelled` portent un `result` optionnel que `_run_chain` reprend (le prompt reste visible sur une erreur). `_Result.prompt_text` → `RagLabStageEndedPayload.prompt_text` (optionnel, défaut `None`). `not_run` passe toujours par `_generation` (statut `not_run`, sans `stage_started`).
- `app_session.py` : `_rag_lab_generate(ask, cancel)` — `build_turn_state()`, `_reasoning_on`, `_reserve_of` ; message système = `state.system_prompt` seulement si `system_prompt` est effectif ; un message utilisateur `[RAG_EXCERPT(contexte), USER_MESSAGE(question)]`. Local : `render_context` + `_call_model(..., on_token=…)` entre `_save_main_state` et `_lab_restore(saved, "rag_lab")` ; cloud : `render_chat_body` + `_lab_cloud_call`. Portée `rag_lab`, `step_id` = `call_id` = l'étape (`lab{n}.s7`), `brick=None` (un `harness_error` du modèle n'arrive pas sur la carte RAG), `origin="model"`. Réponse et tokens produits lus dans le `model_call_ended` de l'étape (un `limit` local ne rend pas le texte dans `_ModelOutput`). Progression : `(0, réserve)` avant l'appel puis un compte par token, bornée à dix par seconde par la fabrique de `LabRun`. `_rag_lab_emit` force `origin=None` (la progression est émise pendant l'appel). Catalogue : option `active` nommée `session.rag_lab.generation_active` d'après `active_model()["label"]`, note `generation_no_model` sans modèle (toujours disponible).
- Contenus ×3 : `rag_lab.generation.{sent,system_prompt,no_system,no_model,too_long,produced,cut,empty,model_error}`, `rag_lab.fact.{prompt_tokens,output_tokens}`, `session.rag_lab.generation_{active,no_model}`, `session.prefix.causes.rag_lab`, `main.orch.prefix_causes.rag_lab` ; `rag_lab.yaml` : options `active` / `not_run`, `progress_tokens_text`, `prompt_sent_text`, `answer_title_text`, `answer_waiting_text`, `generation_not_run_text` (« vous avez choisi de ne pas générer »), `steps.generation.note_text` retirée, `chain_help_text` et explication de l'étape mises à jour, notes des tuiles LLM et Réponse.
- `rag.js` : `model_delta` du contexte `rag_lab`, canal `text`, accumulé sur l'étape generation `running` (`stage.live`) ; le raisonnement n'est pas montré. Statut « n / N tokens ». Focus : réponse en direct (ou « Le modèle lit le prompt… »), puis entrée, prompt envoyé (`<details>`, état ouvert gardé entre les rendus), réponse ; carte du détail : prompt replié. Tuile Réponse : réponse du run montré (3 lignes, entière en infobulle), mise à jour entre deux images par `renderAnswerTile`. Un journal ancien (sans `prompt_text`) garde l'affichage d'avant.
- Tests : `tests/test_rag_lab_generation.py` (19 cas : matrice entière, local et cloud, langues) ; `test_rag_lab.py` (génération exécutée, `last_run` sans les `model_*`, plus de note) ; `test_rag_lab_embeddings.py::test_chunks_longer_than_the_model_are_said_truncated` passe la génération en `not_run` (trois chunks de 1 500 caractères dépassent la fenêtre du faux moteur, un token par octet).
- E2E (`_rag_lab`, `_rag_lab_views`) mis à jour, non lancés (fin de lot). `tests/test_trace_catalog.py`, cité par la vérification, n'existe pas.

## Spec Change Log

## Review Triage Log

Passe 1, 2026-10-05.

| # | Source | Constat | Verdict | Preuve | Suite |
| --- | --- | --- | --- | --- | --- |
| 1 | blind | prompt trop long présenté comme « envoyé » (`generation.sent`, « Prompt envoyé au modèle ») alors que l'erreur dit « rien n'est envoyé » | low | `_generation_run`, branche `too_long` : `input_text = generation.sent`, `prompt_text` posé | patch (phrase « recevrait » pour ce cas, libellé du prompt neutre) |
| 2 | blind | `generation.input` (« Ne pas générer », sauté) nomme toujours le prompt système | low | texte antérieur à 5c-3, inchangé par le diff | rejeté (antérieur, peu visible) |
| 3 | blind, edge | progression cloud comptée en fragments sous l'étiquette « tokens » ; `≈` des tokens produits repris de l'exactitude du prompt | low | `_TokenTap` appelle `token` par fragment ; `got.exact` décrit le prompt | rejeté (cloud secondaire, correctif à branches) |
| 4 | blind | modèle qui raisonne : le focus reste sur « Le modèle lit le prompt… » pendant tout le raisonnement | medium | `model_delta` filtré sur `channel === "text"` ; brique raisonnement fréquente sur les SLM livrés | patch (« Le modèle raisonne… » dès un delta `reasoning`) ; « réponse vide après raisonnement » rejeté : le budget ferme le raisonnement avant la réserve |
| 5 | blind | `SPEC.md` du lot : CAP-5 « non implémentées dans ce lot » périmé | low | ligne 35, déjà périmée depuis 5c-1 | defer (mise à jour du SPEC en fin de lot 5c) |
| 6 | blind | E2E : délai de 60 s trop court pour une génération réelle sur CPU | false | la pile E2E tourne sur le fournisseur OpenAI factice (`run_e2e.py:5025`), réponse immédiate | rejeté |
| 7 | blind, verif, edge | échec du modèle : un moteur en processus qui lève passe par le chemin générique et perd le prompt ; branche `got.status == "error"` jamais testée ; test d'échec qui accepte `prompt_text is None` ; ni réponse vide ni réponse partielle à l'arrêt testées | medium | `_call_model_local` relance l'exception (`except Exception: … raise`) ; `test_a_failing_model…` | patch (exception attrapée dans `_rag_lab_generate` ; tests : erreur cloud, échec local précis, réponse vide, réponse partielle à l'arrêt) |
| 8 | blind, edge | rechargement pendant la génération : la réponse en direct ne montre que la fin | low | `last_run` sans `model_delta` | rejeté (rare ; la fin de l'étape rend la réponse entière) |
| 9 | blind | accessibilité : réponse en direct sans `aria-live`, réponse entière de la tuile en `title` seulement, `<details>` de la carte replié à chaque rendu | low | — | rejeté (réponse lisible dans le focus et la carte ; `aria-live` sur un flux de tokens serait bruyant) |
| 10 | blind | tuile Réponse : « La réponse du modèle » quand rien n'est généré | low | `subtitle()` retombe sur `components.answer.note_text` | patch (texte ×3) |
| 11 | blind | libellé « Modèle actif : X » figé si le modèle change page ouverte | low | le run lit le modèle courant ; libellé rafraîchi au rechargement du catalogue | rejeté |
| 12 | blind | messages `generation_no_model` dupliqués ; valeurs 512 / 1 536 en dur dans le guide ; guide en français seulement | false | deux situations (catalogue au futur, étape au présent) ; `docs/` est en français par convention | rejeté |
| 13 | verif | la réponse en direct et la progression « n / N tokens » ne sont vérifiées par aucun E2E | medium | `_WATCH_PLAY_JS` n'enregistre ni la réponse ni le libellé en tokens | patch (E2E) |
| 14 | verif | `_PREFIX_CAUSES` sans `rag_lab` | low | `app_session.py:326-336`, liste des causes de `messages.yaml` | patch |
| 15 | edge | chaîne enregistrée dans le navigateur avant 5c-3 : Generation `not_run` (seule option alors), donc « Ne pas générer » appliqué sans le choix du formateur | medium | `loadChains` reprend l'option telle quelle | patch (migration des chaînes non versionnées) |
| 16 | edge | arrêt cloud d'une autre raison : « le journal dit pourquoi » sans rien dans le journal | false | `run_call` émet `model_call_ended` avec son `stop_reason` | rejeté |
| 17 | edge | erreur du fournisseur dans l'Atelier RAG : effet « La génération de l'écran s'arrête » (texte de l'Atelier LLM) | low | `_lab_cloud_call` code en dur `session.llm_lab.stops` | patch (effet en paramètre, texte RAG ×3) |
| 18 | edge | E2E : `answer[:40]` comparé à `inner_text()` qui replie les blancs | low | `run_e2e.py:13736` | patch |

## Design Notes

- Le prompt système est le texte de la brique (`TurnState.system_prompt`), pas tout le message système d'un tour : la mémoire globale et les skills supposent des méta-outils (`remember`, `load_skill`) que l'atelier n'offre pas, et « rien si la brique est éteinte » ne tiendrait plus avec la mémoire allumée.
- Le prompt montré est le texte rendu exact (`rendered.prompt` en local, le corps de la requête en cloud), comme `llm_generation_started.rendered` de l'Atelier LLM.
- Le texte en direct passe par les `model_delta` déjà émis par `_call_model` dans la portée `rag_lab` : pas de texte dans `rag_lab_stage_progress`, le journal ne double pas la réponse ; après rechargement, `stage_ended` porte la réponse entière.

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q tests/test_rag_lab.py tests/test_rag_lab_generation.py tests/test_rag_lab_embeddings.py tests/test_rag_lab_rerankers.py tests/test_rag_lab_alt.py tests/test_i18n.py tests/test_ui_texts.py` -- expected: vert
- E2E RAG et pytest complet : en fin de lot 5c (consigne d'Anaël).
