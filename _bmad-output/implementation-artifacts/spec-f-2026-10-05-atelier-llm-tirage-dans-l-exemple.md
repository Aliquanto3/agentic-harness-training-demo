---
title: 'Correction F du 2026-10-05 — Atelier LLM : « Token tiré » tire dans l''exemple quand le modèle ne donne pas ses probabilités'
type: 'bugfix'
created: '2026-10-05'
status: 'done'
baseline_commit: 'e44b9ce320b3082c0a0d5e14c5a3828034ae9d9f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-e-2026-10-05-atelier-llm-premier-pas-candidats-seuls.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Avec un modèle qui ne donne pas ses probabilités (cloud, serveur Ollama ou llama-server, aucun modèle), les parties Logits et Tirage de l'OUTPUT montrent l'exemple d'illustration (correction C), mais la partie « Token tiré » reste une action sur le vrai modèle, grisée avec sa raison : l'étape mélange exemple et réel.

**Approach:** Décision d'Anaël (option A). Dans ce cas seulement, « 🎲 Tirer le token suivant » tire un token parmi les candidats gardés de l'exemple, selon les chances affichées. Le tirage est fait par la session (AD-1), par une nouvelle route en lecture seule `POST /api/llm_lab/example_draw` (mêmes réglages que `example_distribution`). La puce du token porte la mention « exemple », la ligne tirée est marquée dans les deux graphiques, « derniers tirages » se remplit, « Ajouter à la suite » et « Retirer le dernier » sont masqués (l'exemple n'a pas de suite). Avec un moteur en processus, rien ne change.

**Décisions prises en autonomie (choix que l'utilisateur ne remarque pas, ou suite directe de A) :**
- Mode exemple = `store.candidates` lu et `available` faux. Un moteur en processus qui montre encore l'exemple (avant découpage) garde le comportement actuel (« Découpez d'abord… », puis vrai tirage).
- Route sans état ni événement, servie dans tout état de session et sans modèle, comme `example_distribution` : rien au journal du Harnais, aucun appel au modèle, aucune trace.
- Seuls les 6 candidats de l'exemple peuvent sortir, jamais le reste du vocabulaire (la page dit déjà qu'il « n'est pas tiré ici »).
- Le bouton n'est grisé que pendant son propre tirage. Un réglage bougé efface le token tiré (règle existante `clearDrawn`) ; une réponse arrivée après un réglage bougé est ignorée.
- La phrase « Candidats du token tiré par le moteur » n'est pas écrite en mode exemple (aucun moteur n'a tiré).

## Boundaries & Constraints

**Always:** AD-1 (la page ne calcule aucune probabilité et ne tire rien : elle envoie les réglages affichés et dessine la réponse) ; le tirage suit exactement `candidates.distribution` (mêmes `kept` et `p_sampled` que les barres) ; textes en fr + `content/i18n/{en,de}/` (parité) ; ids et classes existants conservés.

**Never:** toucher au chemin réel (`llm_step`, `candidates_only`, premier chargement, « Ajouter » réel) ; émettre un événement de session ou une ligne de journal pour un tirage d'exemple ; charger un GGUF réel ou lancer un serveur sur 8420/8421.

## I/O & Edge-Case Matrix

| Scénario | État | Attendu | Erreur |
|----------|------|---------|--------|
| Tirage d'exemple | cloud, serveur ou aucun modèle | 200 `{index, token_text, example: true}`, `index` parmi les `kept` ; puce + « exemple », ligne marquée, historique | — |
| T = 0 ou top-k = 1 | réglages | toujours le premier candidat de l'exemple | — |
| Session occupée | état ≠ `idle` | 200, comme `example_distribution` | — |
| Réglage hors bornes | `sampling` invalide | 422 | — |
| Textes illisibles | `llm_lab.yaml` invalide | 404 avec la raison, comme `example_distribution` | page : statut d'erreur sous « Tirer » |
| Moteur en processus | `available` vrai | page inchangée (vrai `llm_step`) | — |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/candidates.py` -- `distribution` (l.176) : rows `{p, kept, p_sampled}`. Ajouter une fonction pure `draw_index(rows, rng)` : index tiré parmi les `kept` au poids `p_sampled` (`rng.random()`), testable avec `random.Random(seed)`.
- `src/wavestack/session/app_session.py` -- `llm_example_distribution` (l.9022) : réutiliser son contenu (`_lab_content`, `stages.output.example`) ; nouvelle `llm_example_draw(sampling)` juste après, mêmes erreurs (`DistributionMissing`), rend `{"index", "token_text", "example": True}`. Générateur `random.Random()` de l'instance (attribut créé à l'init, remplaçable par les tests).
- `src/wavestack/web/app.py` -- `LlmExampleDistributionRequest` (l.237) réutilisé ; route `POST /api/llm_lab/example_draw` après `example_distribution` (l.548), même gestion 404, même `shown(...)`.
- `src/wavestack/web/static/llm.js` --
  - `drawStep` (l.1500) : en mode exemple, `post("/api/llm_lab/example_draw", {sampling: exampleSampling()})` au lieu de `llm_step`, avec un ticket (`store.step` ou `store.dist.ticket`) pour ignorer une réponse périmée ; `store.step.drawn = {id: null, text, example: true}`, historique, `store.steppers.output?.show(OUTPUT_STEPS.length - 1)`, puis `fetchExample()` pour marquer la ligne.
  - `stepReason` (l.1429) : en mode exemple, pas de raison (ni candidats, ni « Découpez d'abord », ni occupation de session).
  - `renderStep` (l.1460) : puce `is-example` + mention `stages.output.example.drawn_text` ; `aria-label` `stages.output.example.chip_label_text` ; `llm-step-append`/`llm-step-undo` `hidden` en mode exemple ; `aria-describedby="distribution-note"` en mode exemple.
  - `renderDistribution` (l.1302) : en exemple, `chosen = store.step.drawn?.example ? store.step.drawn.text : null` (lignes `is-chosen`), `#distribution-token` vide.
  - `unmarkStepToken` (l.1444) : retirer aussi les marques en exemple.
  - chargement de l'état (l.2349) : si le mode change (`available` change), effacer `drawn` et `history` de l'autre mode.
- `src/wavestack/web/static/llm.css` -- `.llm-output-chip` (l.1006) : style de la mention « exemple » (reprendre le badge d'exemple existant si possible).
- `src/wavestack/session/llm_lab.py` -- `OutputExample` (l.387) : `drawn_text`, `chip_label_text`.
- `content/llm_lab.yaml`, `content/i18n/{en,de}/llm_lab.yaml` -- `stages.output.example.drawn_text` (« exemple »), `chip_label_text` (« {texte}, tiré dans l'exemple »).
- `tests/test_llm_lab.py` -- après `test_the_example_route_says_why_when_the_texts_cannot_be_read` (l.1839).
- `tools/e2e/run_e2e.py` -- `_distribution_unavailable` (l.12087), appelée pour le cloud (l.11899) et llama-server (l.12022) : ajouter le contrôle du tirage d'exemple.
- `_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/EXPERIENCE.md` (l.113) et `ARCHITECTURE-SPINE.md` (AD-1, l.~85) -- « Tirer » tire dans l'exemple.

## Tasks & Acceptance

**Execution:**
- [x] `candidates.py` -- `draw_index` -- tirage pur, testable.
- [x] `app_session.py`, `web/app.py` -- `llm_example_draw` et sa route.
- [x] `llm_lab.py`, `llm_lab.yaml` ×3 -- deux textes.
- [x] `llm.js`, `llm.css` -- mode exemple de « Token tiré ».
- [x] `tests/test_llm_lab.py` -- `draw_index` (seuls les gardés sortent, T = 0 et top-k = 1 → index 0, fréquences proches de `p_sampled` sur un `Random` à graine) ; route (200 sans modèle, en cloud, session occupée ; 422 ; 404 textes illisibles) ; `token_text` = texte du candidat `index`.
- [x] `tools/e2e/run_e2e.py` -- cloud et llama-server : « Tirer » actif, clic → puce + « exemple », une ligne `is-chosen` gardée dans le Tirage, « Ajouter »/« Retirer » masqués, historique ; un réglage bougé efface la puce.
- [x] `EXPERIENCE.md`, `ARCHITECTURE-SPINE.md` -- mise à jour.

**Acceptance Criteria:**
- Given un modèle cloud ou servi, when on clique « Tirer le token suivant », then un des candidats gardés de l'exemple apparaît en puce marquée « exemple », sa ligne est marquée dans les deux graphiques, et aucun événement de session n'est émis.
- Given un moteur en processus, when la suite E2E LLM (`llm_loop`, `llm_screen`, `llm_live`) tourne, then tout passe sans erreur JavaScript.

## Implementation Notes

- `draw_index(rows, rng)` : tirage parmi les `kept` au poids `p_sampled` ; tous les poids nuls → premier gardé ; aucun gardé → `ValueError` (jamais atteint : `distribution` en garde au moins un).
- Session : `self._example_rng = random.Random()` créé à l'init, lu sous `self._lock` ; `llm_example_draw` réutilise `_lab_content` comme `llm_example_distribution` (un fichier illisible trace donc, comme elle, un `harness_error` une fois par message).
- Page : ticket propre `store.step.ticket` (incrémenté par un réglage bougé, `clearDrawn`, et par « Revenir aux valeurs du harnais ») plutôt que `store.dist.ticket`, que le délai de 80 ms de `scheduleDistribution` laisserait passer ; `store.step.drawing` grise « Tirer » pendant son seul tirage. La mention « exemple » réutilise le badge `.llm-stage-tag.is-example` (classe ajoutée `llm-output-chip-mention`, `aria-hidden`, le nom de la puce la dit).
- E2E : `_example_draw` appelé à la fin de `_distribution_unavailable` (cloud A et llama-server de `llm_screen`) et dans `_llm_loop_cloud`, dont le contrôle « Tirer grisé » est remplacé par « Tirer actif, Ajouter/Retirer masqués, llm_step direct toujours 409 ».
- Textes : placeholder `{texte}` (convention des autres textes de `llm_lab.yaml`).
- Point d'arrêt 1 : « Approuver et continuer » donné par Anaël. Implémentation par un sous-agent, puis patchs de revue par le même sous-agent ; contrôle E2E du 404 ajouté par l'orchestrateur avant la revue (ligne « Textes illisibles » de la matrice, côté page).
- Écart assumé au « Never » (chemin réel) : « Revenir aux valeurs du harnais » efface désormais aussi un token tiré par le moteur (`clearDrawn()`), comme tout réglage bougé (règle de la maquette, correction D) ; avant F, la puce réelle restait après la réinitialisation.
- Patchs de revue : ligne marquée par `index` ; `clearDrawn()` dans `resetSampling` ; `!exampleMode()` au pas automatique ; puce précédente effacée sur refus ; deux commentaires ; E2E `_example_draw_mode_switch` (`_SwitchLab`, un `model_load_ended` injecté sur la page ouverte) et contrôle de la réinitialisation.
- Vérification finale (tests ciblés, accord d'Anaël) : ruff propre ; pytest `test_llm_lab`, `test_engine_candidates`, `test_i18n`, `test_ui_texts`, `test_web_app`, `test_web_tokens`, `test_cloud_api`, `test_anthropic_messages`, `test_openai_responses`, `test_backend_messages`, `test_annex_language` : 3979 réussis, 1 désélectionné (avant les patchs) ; `test_llm_lab` après les patchs : 116 réussis, 1 désélectionné ; E2E `--channel msedge --only bare_llm llm_screen llm_live llm_loop` : 155/155, 0 `harness_error` (les 404/409 de la console sont ceux provoqués par les contrôles).
- Captures : captures LLM régénérées gardées (02, 52-54, 64, 65, 70, 73, 74, 76) ; `01-diagnostic…` restaurée, `01b-diagnostic-cartes.jpg` supprimée.

## Spec Change Log

## Review Triage Log

Revue (step-04, 3 relecteurs : blind, edge-case, verification-gap) : 23 constats regroupés en 19 entrées, aucun intent_gap ni bad_spec ; 7 entrées corrigées par patch, 2 différées, 10 rejetées.

| # | Source | Constat | Verdict | Preuve | Route |
| --- | --- | --- | --- | --- | --- |
| 1 | edge, blind | La ligne tirée est marquée par son texte, l'`index` rendu est jeté | low | `renderDistribution` compare `c.text === chosen` ; le validateur d'`OutputExample` n'impose pas des textes distincts | patch (marquer par `index`) |
| 2 | edge (×2), blind | « Revenir aux valeurs du harnais » laisse la puce et sa ligne marquée | medium | `resetSampling` ne fait qu'incrémenter le ticket ; `fetchExample` remarque la ligne d'après `drawn` | patch (`clearDrawn()`, aussi en mode réel : la règle « un réglage bougé efface la puce ») |
| 3 | edge | Pas automatique : candidats devenus indisponibles entre `autoStart` et `llm_tokenized` → tirage d'exemple, `store.auto` reste « step » | low | `stepReason()` rend `null` en mode exemple depuis F, la condition de `renderTokenized` ne bloque plus | patch (`!exampleMode()`, la sémantique d'avant) |
| 4 | blind | Un tirage refusé laisse la puce précédente à côté de l'erreur | low | `drawExample` n'efface rien avant `setStepStatus(…, true)` | patch |
| 5 | blind | Commentaire de `renderStep` périmé (« Tirer » grisé, titre qui garde la raison) | low | l.~1522 | patch |
| 6 | blind | Commentaire d'`OutputExample` : `{text}` au lieu de `{texte}` | low | `llm_lab.py` | patch |
| 7 | verif, blind | Bascule de mode dans `refresh()` jamais jouée (chaque `_example_draw` part d'une page rechargée) | medium | aucun E2E ne bascule `available` sur une page ouverte | patch (E2E de bascule + réinitialisation des réglages) |
| 8 | verif, blind | Garde du ticket (réponse périmée) non testée | low | aucun E2E ne retarde `example_draw` | defer (comme déposé) |
| 9 | verif | « Tirer » actif pendant une session occupée, non vérifié côté page | low | E2E seulement au repos ; la route est testée occupée | defer (comme déposé) |
| 10 | edge | `aria-describedby` vers une note vide si les textes sont illisibles | low | textes illisibles : tout l'écran est en erreur, cas improbable | rejet |
| 11 | edge | `refresh()` efface les tirages réels pendant un chargement transitoire | false | `model_load_started` appelle déjà `clearSteps()` (llm.js:2261) ; `refresh` n'est appelé qu'à `model_load_ended` et à l'ouverture | rejet |
| 12 | edge, blind | Contrôle E2E « aucun événement » limité à `context_id == "llm"` | low | `test_the_session_draws_in_the_example_by_its_chances` et le test de route vérifient le journal entier | rejet |
| 13 | edge | `unmarkStepToken` touche le chemin réel | false | en mode réel les barres d'exemple n'ont aucune ligne marquée : retrait sans effet | rejet |
| 14 | blind | « Retirer » masqué alors que des ajouts réels restent après une bascule vers le cloud | false | tout changement de modèle passe par `_load` → `model_load_started` → `clearSteps()` | rejet |
| 15 | blind | Aucun texte ne dit avant le clic que « Tirer » tire dans l'exemple | low | l'étape porte le badge « Exemple · probabilités d'illustration » et la note d'exemple | rejet |
| 16 | blind | Aucune annonce aux lecteurs d'écran après un tirage réussi | low | même comportement que le tirage réel (puce non vivante, statut vidé) | rejet |
| 17 | blind | Ni « aucun modèle » ni Ollama joués en E2E | low | même branche `exampleMode()` que llama-server ; route testée sans modèle | rejet |
| 18 | blind | Verrou de session pris pour `rng.random()` | maybe-false | il faudrait montrer un détenteur long de `_lock` ; au pire low | rejet |
| 19 | blind | Critères d'acceptation minces ; `[hidden]` local en CSS | low / false | correction = éditer la spec ; aucun autre bouton caché concerné par ce diff | rejet |

## Verification

**Commands:**
- `uv run ruff check` et `uv run ruff format --check` sur les fichiers touchés -- aucun écart
- `uv run pytest -q tests/test_llm_lab.py tests/test_i18n.py tests/test_ui_texts.py tests/test_web_app.py` -- tout vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only llm_loop llm_screen llm_live` (avec `PYTHONIOENCODING=utf-8`) -- tout vert
