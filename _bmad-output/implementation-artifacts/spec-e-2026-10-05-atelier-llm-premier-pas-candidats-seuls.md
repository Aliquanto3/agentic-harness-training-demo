---
title: 'Correction E du 2026-10-05 — Atelier LLM : premier pas automatique = candidats seuls, sans tirage (côté session)'
type: 'bugfix'
created: '2026-10-05'
status: 'done'
baseline_commit: '75060d10a084a0190b01bb72f89c6e7a60b5f43c'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-d-2026-10-05-atelier-llm-premier-pas-et-espace-virgule.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Depuis la correction D, l'Atelier LLM présente le pas automatique du premier chargement (GGUF chargé, session au repos) comme une simple lecture des probabilités, mais côté session c'est encore un vrai `llm_step` : le moteur tire un token (`llm_token`), et le journal du Harnais montre ce tirage (« Atelier LLM : tokens produits × 1 », « génération commencée/terminée »), en contradiction avec la page.

**Approach:** Décision d'Anaël « candidats seuls ». `llm_step` reçoit un mode `candidates_only` : la session évalue le texte de l'INPUT (et les ids ajoutés) puis lit les logits de la dernière position, sans échantillonner (nouvelle méthode du moteur en processus `next_candidates`) ; elle garde les `TOP` candidats comme index 0 de la mémoire (même `/api/llm_lab/distribution`, mêmes `candidates.distribution`/`dropped_by`, `token_text` nul), n'émet aucun `llm_token`, et encadre la lecture par `llm_generation_started`/`llm_generation_ended` marqués `candidates_only: true`, avec une phase et un message « lecture des probabilités, aucun token tiré ». La page demande ce mode pour le seul pas automatique et lit les barres à la fin ; le journal du Harnais nomme ces lignes « lecture des probabilités ». « 🎲 Tirer le token suivant » garde le vrai tirage.

**Décisions prises en autonomie (Anaël injoignable, option recommandée) :**
- Un drapeau de `llm_step` (même route, même état `llm_lab`, même id `llm{n}.step`, mêmes refus) plutôt qu'une nouvelle route : la page route déjà ces événements vers l'OUTPUT, et les refus (hors repos, cloud, serveur, bornes) restent identiques.
- Lecture sans échantillonnage réel (logits de la dernière position après évaluation) plutôt qu'un tirage caché : rien n'est tiré, même dans le moteur.
- Pas de `model_call_started`/`model_call_ended` ni de mesure CodeCarbon pour cette lecture : ce n'est pas un appel de génération ; le coût CPU d'une évaluation est accepté (consigne).
- Le libellé des lignes du journal change pour ce mode (« Atelier LLM : lecture des probabilités commencée / terminée ») ; sinon le résumé (phase, « terminée · durée · message ») suffit.

## Boundaries & Constraints

**Always:** AD-1 (la page ne calcule aucune probabilité, ne tire aucun token) ; refus hors `idle`, sans moteur en processus, au-delà de `STEP_LIMIT` ou hors vocabulaire, comme `llm_step` ; l'état du cache principal sauvé puis restauré autour de la lecture (`_save_main_state`/`_lab_restore`) ; textes en fr + `content/i18n/{en,de}/` (parité) ; ids et classes de la page conservés.

**Never:** tirer un token (ni `complete`, ni `generate`) en mode candidats seuls ; émettre `llm_token` ; changer le comportement du clic « Tirer » ; charger un GGUF réel ou lancer un serveur sur 8420/8421.

## I/O & Edge-Case Matrix

| Scénario | État | Attendu | Erreur |
|----------|------|---------|--------|
| Lecture au repos | `idle`, moteur en processus | `llm_generation_started` (`candidates_only`) puis `llm_generation_ended` (`completed`, `candidates_only`, 0 token, message « aucun token tiré ») ; aucun `llm_token` ; `/distribution` index 0 = candidats lus, `token_text` nul ; session revenue `idle`, historique inchangé | — |
| Hors repos, cloud, serveur, bornes | état ≠ `idle`, etc. | `SendRefused` (409), aucun événement | — |
| Moteur en échec pendant la lecture | exception | `llm_generation_ended` `error`, session `idle` | AD-16 |
| Page, 1er chargement | moteur en processus simulé | `llm_step` envoyé avec `candidates_only: true`, barres réelles, rien de tiré | 409 : erreur habituelle, l'exemple reste |
| Page, clic « Tirer » | — | `llm_step` sans `candidates_only` : puce, « derniers tirages », légende | — |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/engine.py` -- `LlamaCppEngine.next_candidates(prompt_ids, cancel)` près de `prefill` (l.~361) : cache ramené à son préfixe commun avec `ids[:-1]` au plus (`kv_cache_seq_rm` ou `reset`, comme `prefill`), puis `llm.eval` par lots de `PREFILL_BATCH` (au moins le dernier id évalué), `llama_get_logits_ith(ctx, -1)` comme `_candidates`, `top_from_logits` + `piece_text` → `{p, texts, tail}` (forme de `top`) ; `None` si annulé ; `_last_evaluated` mis à jour.
- `tests/fake_engine.py` -- `FakeEngine.next_candidates` : appels notés (`peeks`), cache mis à jour, `logits_script[0]` lu par `top_from_logits` ; aucun ajout à `calls`/`samplings`.
- `src/wavestack/trace/catalog.py` -- `LlmGenerationStartedPayload` (l.~1152) et `LlmGenerationEndedPayload` (l.~1209) : `candidates_only: bool = False`.
- `src/wavestack/session/app_session.py` -- `llm_step` (l.~8779) : paramètre `candidates_only=False` ; si vrai, `self._executor.submit(self._run_peek, …)` ; nouveau `_run_peek` après `_step_context` : scope `_lab_scope(request_id, call=True)`, `_step_context` pour les ids, started avec phase `session.llm_lab.step.peek_reading`, `_save_main_state`, `engine.next_candidates`, `memory[0] = {"token_text": None} | top`, `_lab_restore(saved, "llm")`, ended (`message_text` `session.llm_lab.step.peek_done`), `_lab_release` ; erreurs comme `_run_lab`.
- `src/wavestack/web/app.py` -- `LlmStepIntention.candidates_only: bool = False` (l.~216), passé par la route (l.~514).
- `content/messages.yaml`, `content/i18n/{en,de}/messages.yaml` -- `session.llm_lab.step.peek_reading`, `peek_done`.
- `src/wavestack/web/static/llm.js` -- `drawStep` (l.~1500) envoie `candidates_only: store.auto === "step"` ; `stepEvent` (l.~1580) : `llm_token` sans cas automatique ; à `llm_generation_ended` `candidates_only` + `completed` + même texte → `dist.source = "step"`, `index 0`, `tokens 1`, `scheduleDistribution(0)` ; statut d'attente `stages.output.reading_text` pour la lecture.
- `content/llm_lab.yaml`, `content/i18n/{en,de}/llm_lab.yaml` -- `stages.output.reading_text`.
- `src/wavestack/web/static/app.js` -- `logRow` (l.~6455) : nom de ligne `main.log.lab_peek_started` / `lab_peek_ended` pour un `llm_generation_*` à `candidates_only`.
- `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- ces deux clés sous `main.log`.
- `tests/test_llm_lab.py` -- tests après `test_step_route_answers_validates_and_refuses` (l.~1536).
- `tools/e2e/run_e2e.py` -- `_LoopLab` (l.~12700) : `peeked(draw)` (started + ended `candidates_only`, aucun `llm_token`, `/distribution` à `token_text` nul) ; `_llm_loop_first_load` (l.~12862) : contrôle `candidates_only` du pas automatique et absence de tirage, puis clic sans `candidates_only`.
- `EXPERIENCE.md` du lot 6 (l.~99, 108) -- le pas automatique devient une lecture côté session.

## Tasks & Acceptance

**Execution:**
- [x] `engine.py`, `fake_engine.py` -- `next_candidates` -- lire sans tirer.
- [x] `catalog.py`, `app_session.py`, `web/app.py`, `messages.yaml` ×3 -- mode `candidates_only` de `llm_step`.
- [x] `llm.js`, `llm_lab.yaml` ×3 -- le pas automatique demande ce mode.
- [x] `app.js`, `ui.yaml` ×3 -- libellé du journal.
- [x] `tests/test_llm_lab.py` -- lecture sans tirage (pas de `llm_token`, `calls` et `samplings` inchangés, mémoire = `top_from_logits`, `token_text` nul, état et historique inchangés, cache principal restauré), refus hors repos et en cloud/serveur, route avec `candidates_only`.
- [x] `tools/e2e/run_e2e.py` -- premier chargement sans tirage émis.
- [x] `EXPERIENCE.md` -- état « Premier chargement ».

**Acceptance Criteria:**
- Given un moteur en processus au repos, when `llm_step(..., candidates_only=True)`, then aucun token n'est tiré ni émis, `/distribution` index 0 rend les candidats lus, la session revient `idle`.
- Given la suite E2E LLM (`llm_loop`, `llm_screen`, `llm_live`), when elle tourne, then tout passe sans erreur JavaScript.

## Implementation Notes

- Point d'arrêt 1 (approbation de la spec) : « Approve and continue » pris en autonomie, Anaël injoignable.
- Step-03 : implémenté directement par l'agent qui a fait l'investigation, sans sous-agent d'implémentation (contexte déjà chargé, comme les corrections C et D) ; les patchs de revue appliqués de même.
- Écarts au Code Map : `_run_peek` tourne sous `_lab_scope(request_id)` sans `call_id` (aucun appel au modèle) ; `src/wavestack/session/llm_lab.py` (`OutputStage.reading_text`) et `tests/test_engine_candidates.py` touchés en plus.
- `LlamaCppEngine.next_candidates` vérifié sur le GGUF synthétique `tests/fixtures/tiny-llama.gguf` (suite par défaut, aucun modèle réel) : mêmes `top` que le premier token tiré au même endroit, cache vide, cache au-delà des ids, cache exactement sur les ids (1 id réévalué), lecture annulée, aucun id (`ValueError`).
- Borne « prompt trop long » de la lecture alignée sur celle de « Tirer » (`window - output_reserve(False)`), après la revue ; `read_tps` mesuré sur la seule lecture du moteur.
- Le `sampling` de `llm_generation_started` reste celui de l'écran (champ obligatoire) : il ne sert qu'aux barres redessinées par `/distribution`.
- Vérification finale : ruff propre (check + format) sur les fichiers Python touchés ; pytest `test_llm_lab`, `test_engine_candidates`, `test_i18n`, `test_ui_texts`, `test_web_app`, `test_web_tokens` : 327 réussis, 1 désélectionné ; E2E `--channel msedge --only llm_loop llm_screen llm_live` : 116/116 (avec `PYTHONIOENCODING=utf-8` : sans lui, la sortie redirigée vers un fichier casse sur « ≈ » et « ␣ »).
- Captures : seules les captures LLM régénérées (52-54, 64, 65, 70, 73, 74, 76) sont gardées ; `01-diagnostic…` restaurée, `01b-diagnostic-cartes.jpg` et les `echec-*.jpg` supprimées.
- Point ouvert pour Anaël : `next_candidates` n'a pas tourné sur un vrai GGUF (consigne) ; sur un modèle hybride (Qwen3.5), `kv_cache_seq_rm` échoue et la lecture relit tout le texte (`reset`), comme `prefill` : coût d'une évaluation, accepté.

## Spec Change Log

## Review Triage Log

Revue (step-04, 3 relecteurs : blind, edge-case, verification-gap) : 22 constats regroupés en 20 entrées (même cause), aucun intent_gap ni bad_spec ; 12 entrées corrigées par patch, 8 rejetées, aucune différée. Point d'arrêt de revue tranché en autonomie (option recommandée : appliquer les patchs).

| # | Source | Constat | Verdict | Preuve | Route |
| --- | --- | --- | --- | --- | --- |
| 1 | verif, blind | Libellé « lecture des probabilités » du journal du Harnais non vérifié | medium | aucun test ne lit une ligne `llm_generation_*` du journal | patch (E2E `_llm_loop_journal`, flux routé : lecture puis pas tiré) |
| 2 | verif | Statut d'attente `reading_text` non vérifié | low | lu seulement après la fin | patch (contrôle dans `_llm_loop_first_load`) |
| 3 | edge (×2) | Prompt vide au pas automatique : `store.auto` reste « step », le « Tirer » suivant ne tire pas | low | `drawStep` revient sans remettre `auto` | patch (`store.auto = null`) |
| 4 | edge, blind | Aucun id : `None` pris pour une annulation | low | `next_candidates` rend `None` dans les deux cas | patch (`ValueError`, faux moteur aligné) |
| 5 | edge | Faux moteur sans parité sur les ids vides | low | `keep = -1` | patch (même `ValueError`) |
| 6 | edge, blind | `read_tps` compte découpage et copie d'état | low | `time.monotonic() - started` | patch (chrono autour de `next_candidates`) |
| 7 | blind | Borne « trop long » différente de « Tirer » | low | `tokens > window` contre `window - 512` | patch (même borne, test ajouté) |
| 8 | blind | Branches « annulée » et « trop long » sans test | low | aucun test | patch (`test_a_candidates_only_step_too_long_or_cancelled_keeps_nothing`) |
| 9 | blind | `peek_reading` au passé avant la lecture | low | « tokens lus » dans `started` | patch (« à lire », en, de) |
| 10 | blind | Docstring de la route à moitié mise à jour | low | texte | patch |
| 11 | blind | Cellule « Premier chargement » d'EXPERIENCE.md contradictoire | low | « fait tirer un premier pas » puis « rien tiré » | patch (cellule réécrite) |
| 12 | blind | ARCHITECTURE-SPINE.md (contrat des événements) non mis à jour | low | l.122 : liste des champs, `model_call_*` toujours autour | patch (phrase ajoutée) |
| 13 | blind | Spec en retard sur le code (scope, fichiers) | low | correction = éditer la spec | rejet (écarts notés ci-dessus) |
| 14 | blind | `_run_peek` duplique `_run_lab` | low | pas de défaut nommé | rejet |
| 15 | blind | `next_candidates` réimplémente `prefill` | low | `prefill` rend 0 sans couper quand tout est en cache : il ne convient pas | rejet |
| 16 | blind | Relecture complète sur un modèle hybride | false | `_lab_restore` remet le contexte principal : le texte de l'étape n'est jamais en cache au début d'une lecture, `generate` relit aussi tout | rejet (noté en point ouvert) |
| 17 | blind | `sampling` de `started` jamais appliqué | low | champ obligatoire, valeurs des barres redessinées | rejet |
| 18 | blind | Garde `memory is not None` morte | low | type `Optional` de `_lab_begin` | rejet |
| 19 | edge | Moteur en processus sans `next_candidates` | false | le moteur en processus est toujours `LlamaCppEngine` (ou le faux des tests) ; un serveur ou un cloud est refusé avant | rejet |
| 20 | blind | `llm_step` : docstring qui ouvre sur « draws one token » | low | complétée par la phrase de la correction E | rejet |

## Verification

**Commands:**
- `uv run ruff check` et `uv run ruff format --check` sur les fichiers touchés -- aucun écart
- `uv run pytest -q tests/test_llm_lab.py tests/test_i18n.py tests/test_ui_texts.py tests/test_web_app.py` -- tout vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only llm_loop llm_screen llm_live` -- tout vert
