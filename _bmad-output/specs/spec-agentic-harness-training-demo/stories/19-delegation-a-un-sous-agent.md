---
title: 'Délégation à un sous-agent'
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

**Problem:** Rien ne montre encore qu'un harnais peut confier une sous-tâche volumineuse (lire un long document) à un second agent au contexte propre, pour que seul le résultat entre dans le contexte principal : l'économie de tokens de la délégation reste invisible (CAP-30, FR-29, UJ-6).

**Approach:** Une brique `subagent` (harness engineering) déclare le méta-outil du harnais `delegate(task)` (AD-25). Son exécution lance, sur la même instance du moteur, une boucle bornée dans le contexte `sub{n}` (AD-11) : prompt système du sous-agent, tâche, outils listés par la brique ; son résultat seul revient en `subagent_result`. La délégation est décidée par le modèle ou forcée (« Déléguer au sous-agent », mécanisme de la story 9). Contexte LLM bascule entre contexte principal et contexte du sous-agent ; Orchestration montre l'étape dépliable et l'économie de tokens ; le schéma dessine un second nœud Modèle.

## Boundaries & Constraints

**Always:**
- AD-11 : même `Engine`, séquentiellement ; `context_id = sub{n}`, `n` croissant sur toute la session (jamais remis à zéro) ; ce n'est pas un tour : jamais `turn_started`/`turn_ended` ni `on_user_message`/`on_turn_end` dans `sub{n}` ; `before_model_call`, `before_tool`, `after_tool` s'y appliquent (H1, H2, H5 compris). Identifiants : `call_id = {turn}.sub{n}.c{k}`, `step_id = {turn}.sub{n}.s{k}`, étapes de hook `{turn}.sub{n}.h{k}` ; `parent_step` = `step_id` de l'étape `delegate` sur tous les événements du sous-agent ; `trigger` hérité (modèle ou utilisateur).
- Contexte du sous-agent = gabarit + prompt système du sous-agent (`content/prompts/subagent.md`, segment `system_prompt`, brique `subagent`) + tâche (segment `user_message`, brique `subagent`) + outils = `[subagent] tools` ∩ outils activés de la brique Outils effective dans ce tour ; jamais de méta-outil (pas de délégation imbriquée). Rien d'autre du contexte principal (ni historique, ni prompt système principal, ni skills, ni injection H3).
- Bornes (AD-10) : `[subagent] max_calls` (4 par défaut) sur un compteur propre ; nouveaux essais après appel mal formé selon `tool_max_retries`, comptés dans ces 4 ; la délégation compte pour 1 dans le tour principal (l'appel du modèle qui l'a demandée) ; forcée, elle ne consomme aucun appel principal.
- Échec de la délégation (AD-9, AD-11, AD-16) : dépassement → `context_overflow` ; sortie coupée → `output_truncated` ; borne → `limit_reached{sub_calls|retries}` ; issue fournisseur ou exception moteur → `harness_error` ; tous avec `context_id = sub{n}`, puis `tool_ended{status: overflow|limit|error}` de `delegate`, une erreur en français réinjectée, et le tour principal continue. Une sortie coupée au milieu d'un appel d'outil suit la voie de l'appel mal formé (AD-9). Un arrêt pendant le sous-agent donne `subagent_ended{cancelled}`, `tool_ended{error}` (« Délégation arrêtée ») et termine le tour `cancelled`, sans autre appel. Une réponse finale vide du sous-agent devient « (Le sous-agent n'a rendu aucun texte.) ».
- Résultat : la réponse d'outil de `delegate` est un segment `subagent_result` (brique `subagent`, composant `subagent.agent`), aussi en cas d'échec ; bloquée par un hook, elle reste attribuée au hook (règle existante). Dans l'historique : type `history`, sans talon.
- Économie visible, calculée par la session (AD-1) : `subagent_ended` porte `context_tokens` (le `used` du dernier appel du sous-agent, réconcilié s'il l'a été), `result_tokens` (tokens du résultat : tokenizer en local, estimation en mode chat avec `estimated = true`) et `saved_tokens = max(0, context_tokens − result_tokens)`.
- La jauge de la barre haute reste sur le contexte principal ; le compteur du sous-agent est dans son étape (EXPERIENCE, « Sous-agent au travail »). La Vue humain ne reçoit jamais le texte du sous-agent, seulement l'indicateur « Appel au sous-agent » et les validations H5 éventuelles.
- Mode chat (AD-4) : même corps construit par `context`, ratio d'estimation tenu séparément pour `main` et pour tous les `sub{n}` ; aucune préservation d'état.
- Textes en français sous `content/` (AD-19) ; code en anglais ; aucune nouvelle dépendance, aucun nouveau `SegmentKind`, enveloppe inchangée.

**Never:** `save_state()`/`load_state()` (contexte principal relu, latence affichée) ; second moteur ou second modèle en mémoire ; sous-agent qui reçoit l'historique ou le contexte principal ; délégation imbriquée ; mode `forced` sans parseur d'appels (reporté comme en story 9) ; repli hors ligne de `fetch_page` (différé 5b) ; ajout d'hôte à la liste d'adresses autorisées ; changement de la disposition du schéma (8e) ou du redimensionnement (8f).

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu | Erreur |
|---|---|---|---|
| Délégation par le modèle | brique active, `read_file` activé ; le modèle appelle `delegate` | `tool_started{delegate}` (main, `trigger=model`), `subagent_started` puis appels `sub1` (lecture du fichier dans `sub1`), `subagent_ended{completed, …}`, `tool_ended{ok}` ; l'appel principal suivant ne contient que le résultat en `subagent_result` | — |
| Délégation forcée | action armée « Déléguer au sous-agent » avec une tâche | Consommée avant le premier appel principal (`trigger=user`), même cycle ; aucun appel principal consommé | — |
| Tâche vide ou cible inconnue à l'armement | `arm("delegate", "delegate", {task: " "})` ; `target` autre | 422 « La tâche du sous-agent est vide. Rien n'est armé. » ; 404 | rien n'est armé |
| Brique éteinte après armement | `subagent` décochée | `action_dropped` avec la raison ; le tour continue | — |
| Contexte du sous-agent dépassé | tâche + résultat d'outil > `usable` | `context_overflow` (`sub1`), `tool_ended{overflow}`, erreur réinjectée ; le modèle principal est rappelé et le tour se termine normalement | pas de plantage |
| Borne du sous-agent | 4 appels du sous-agent tous avec appel d'outil | `limit_reached{sub_calls}` (`sub1`), `tool_ended{limit}`, tour principal continue | — |
| Sortie coupée | sortie texte du sous-agent coupée à la réserve | `output_truncated` (`sub1`), `tool_ended{limit}` | — |
| Fournisseur refuse (cloud) | 429 dans `sub1` | `harness_error` (`sub1`), `tool_ended{error}`, tour principal continue | message filtré (AD-15) |
| H5 dans le sous-agent | `fetch_page` activé, H5 actif | `approval_requested` au sous-agent, carte dans la Vue humain ; refus réinjecté au sous-agent | — |
| Arrêt pendant le sous-agent | « Arrêter » pendant `sub1` | tour `cancelled`, plus aucun appel | — |
| Aucun outil pour le sous-agent | brique Outils éteinte | le sous-agent reçoit la tâche sans `tools` et répond | — |

</intent-contract>

## Code Map

- `src/wavestack/bricks/registry.py` -- `BRICKS` : ajouter `subagent` (`category="harness"`, `capabilities=["tool_call_parser"]`, `contributes_to=["main", "sub"]`), composant `subagent.agent` (`kind="subagent"`, `local_process`, `edges_to=["core.harness"]`). `core.model_sub` est déjà dans `RESERVED_NODES`.
- `src/wavestack/config.py` (L259-276, modèle `tool_max_calls`) + `wavestack.toml` -- section `[subagent]` : `tools = ["read_file", "fetch_page"]`, `max_calls = 4` ; propriétés `subagent_tools`, `subagent_max_calls` (≥ 1).
- `src/wavestack/trace/catalog.py` -- `SubagentStartedPayload{task, tools, phase_label}`, `SubagentEndedPayload{status: completed|limit|overflow|error|cancelled, result, context_tokens, result_tokens, saved_tokens, estimated, calls, duration_ms}` (`calls` : appels au modèle du sous-agent ; `estimated` : `result_tokens` estimé, mode chat) dans `PAYLOAD_MODELS` (L447) ; `ArmedActionState.kind` (L399) + `"delegate"` ; `BrickState` (L256) + `force: BrickForce | None` (`{kind, target, label_fr, parameters, presets}`).
- `src/wavestack/tools/registry.py` -- `class DelegationFailed(ToolError)` avec `status: Literal["limit","overflow","error"]`. `src/wavestack/tools/executor.py` `run` : `tool_ended.status = getattr(exc, "status", "error")` pour une `ToolError`.
- `src/wavestack/session/app_session.py` :
  - Constante `DELEGATE = "delegate"` à côté de `LOAD_SKILL` (L105). `TurnState` (L252) + `subagent_tools: tuple[str, ...]`. `_SubContext{context_id, task, prompt, tools}` (dataclass locale).
  - `__init__` (L315) : `_subs = 0` ; `_ratio` (L338, L925) devient `_ratios = {"main": r, "sub": r}`, clé choisie par `current().context_id` (L1356, L2797, L2820) ; `_turn_ctx: tuple[TurnState, CancelToken] | None`, posé au début de `_run_turn` (L2033) et remis à `None` dans son `finally`.
  - `_load_content` (L943) : `content/subagent.yaml` et `content/prompts/subagent.md` quand la brique est déclarée ; échec → `_content_errors["subagent"]`.
  - `_harness_tools` (L1628) : `delegate` (`params={"task": "string"}`, `component="subagent.agent"`, `source="harness"`, `brick="subagent"`, texte de `content/subagent.yaml`), `run=self._delegate` (modèle : `_load_skill` L1692).
  - `build_turn_state` (L1068) : si `subagent` effective, `subagent_tools` = liste configurée ∩ outils de la brique Outils retenus dans `tools` (avant l'ajout des méta-outils), puis `tools += [DELEGATE]`.
  - `_delegate(task)` : lit `_turn_ctx`, numérote `sub{n}`, émet `subagent_started` puis lance `_run_subagent` sous `scoped(context_id, parent_step=<step courant>, component="core.model_sub")` ; renvoie le résultat, ou lève `DelegationFailed` (message français, statut). Exception inattendue → `harness_error` dans `sub{n}` puis `DelegationFailed(status="error")`. Émet toujours `subagent_ended`.
  - `_run_subagent` : boucle bornée calquée sur `_turn` (L2092-2239) avec `before_model_call`, rendu, contrôle de dépassement, `_call_model`, `_check_prefix`, appels d'outils par `_run_tool` (L2241) ; statuts mappés vers `DelegationFailed`. Pas d'armement, pas de `loaded_in_turn`.
  - `_render` (L1300) / `_render_chat` (L1336) : paramètre `sub: _SubContext | None` ; si présent, messages = `_sub_messages(sub, steps, chat)` (système + tâche + `_step_messages(steps, history=False, group="sub")`) et définitions d'outils de `replace(state, tools=sub.tools, loadable=())` (`_tool_definitions` L1256 ne lit que ces deux champs).
  - `_turn` : `harness_brick` (L2141) inclut `subagent` ; construction de `tool_step` (L2220-2230) et `_consume_armed` (L2361-2371) factorisées dans un utilitaire qui pose `kind=SUBAGENT_RESULT`, `brick="subagent"`, `component="subagent.agent"` pour `delegate` non bloqué.
  - `_hook` (L2492) et `_await_human` (L2427) : `step_id` = `{turn}.{context_id}.h{k}` au lieu de `main` en dur.
  - `_emit_overflow` (L2633) : en `sub{n}`, cause « contexte du sous-agent » (texte de `content/subagent.yaml`) ; `_LIMITS_FR` (L169) + `sub_calls`.
  - `arm` (L1537) : `kind == "delegate"` (cible `delegate` sinon 404 ; `task` non vide sinon 422 ; `brick="subagent"`, libellé « Délégation : « {40 premiers caractères} » ») ; `_armed_call` (L2375) et `_armed_unavailable` (L2383, brique `subagent` non effective).
  - `_emit_bricks` (L732) : pour `subagent`, `force` (paramètre `task`, préréglages de `content/subagent.yaml`) et `limits_fr` (« Sous-agent : 4 appels au modèle au plus ; outils : … s'ils sont activés dans la brique Outils. »).
  - `_emit_architecture` (L533) : `subagent` voulue → nœud `core.model_sub` (`kind="model"`, même `hosting`/`model`/`provider` que `core.model`, `label_fr` « Modèle (sous-agent) ») et arête `core.harness → core.model_sub` (`crosses_boundary` si cloud) ; `subagent.agent` reste une puce (`kind="brick"`).
- `content/bricks/subagent.yaml` (carte : « Sous-agent », `harness engineering`, hébergement, explication : contexte propre, même modèle, seul le résultat revient, économie, hooks), `content/subagent.yaml` (texte de `delegate` et de son paramètre, `phase_label_fr` « Appel au sous-agent », `force_label_fr`, préréglages, cause de dépassement), `content/prompts/subagent.md`, `content/demo_files/guide_harnais.md` (≈ 7 000 caractères, texte original non confidentiel), `content/scenarios.yaml` (scénario `subagent` dans un module « Sous-agent », 30 min).
- `src/wavestack/web/app.py` -- `ArmIntention.kind` (L95) + `"delegate"`.
- `src/wavestack/web/static/app.js` :
  - `applyEnvelope` (L146-376) : `turn.subs` (Map `context_id` → projection `{id, parentStep, started, ended, steps, context, callEnded, overflow, limit, truncated, errors, status}`) ; les `kind` d'étape (`context_rendered`/`reconciled`, `model_*`, `tool_*`, `outbound_request`, `hook_decided`, `effect_applied`, `approval_*`, `tool_call_malformed`, `limit_reached`, `prefix_not_reused`, `context_overflow`, `output_truncated`, `harness_error`) visent `sub` quand `context_id` commence par `sub`, sinon le tour ; en `sub`, jamais `store.gauge`, `turn.context`, `turn.text`/`reasoning` ; `model_call_started` en `sub` met `turn.phaseLabel` à « Sous-agent · {phase_label} ». `tool_started` garde `stepId: envelope.step_id` ; `subagent_started` rattache la projection à l'étape outil dont `stepId === parent_step`.
  - `turnRows` (L1948) : une étape `delegate` donne la ligne « Délégation au sous-agent » (icône 👥, badge de déclenchement, chiffre « {result} tokens réinjectés · {saved} économisés ») ; son corps : tâche, outils, phrase d'économie, résultat, bouton « Voir le contexte du sous-agent ». Suivent les lignes de `turnRows(sub)` (clé préfixée, classe `is-sub`, indentées). `LIMITS` (L1938) a déjà `sub_calls`.
  - `renderContext` (L1411) : si le tour affiché a des sous-agents, bascule en tête (`aria-pressed`) « Contexte principal » / « Contexte du sous-agent » (un bouton par `sub{n}` s'il y en a plusieurs) ; état d'interface `store.ctxView` (retour au principal si absent) ; vue sous-agent : segments du dernier appel, total, ligne d'économie, sortie brute.
  - `renderChat` (L1184-1198) : cartes H5 aussi pour les étapes des sous-agents.
  - Panneau des briques : `FORCE_LABELS` (L665) + `subagent: "Déléguer au sous-agent"` ; bouton Forcer au niveau de la carte quand `brick.force` et `store.showForced` ; `forceForm` (L769) réutilisé avec `{id: "delegate", parameters, presets}` et `armAction("delegate", "delegate", {task})`. `BRICK_ICONS` (L3017) + `subagent: "👥"`.
  - Schéma : `buildSchema` (L3209, L3237) dessine un second robot « Sous-agent » à côté du premier (dans la boîte réseau si cloud) quand `core.model_sub` existe ; actif pendant un appel en cours d'un sous-agent du tour actif (`robotPose`, L3062).
- `src/wavestack/web/static/app.css` -- `.turn-step-line.is-sub` (indentation, filet), `.ctx-view-switch`, `.robot-sub`.
- Tests : `tests/fake_engine.py` (`FakeEngine(outputs=…)`, une sortie par appel, sous-agent compris), `tests/test_tools.py` (`QWEN`, `call`, `tool_session`, `_segments`), `tests/test_forced.py` (`run`, `of`, `armed`), `tests/test_hooks.py` (`h5_session`, `wait_asked`), `tests/test_bricks.py` (`_client`, `HEADERS`), `tests/test_cloud.py` (session cloud factice), `tests/test_trace_architecture.py` L70 (`"subagent"` reste un `kind` de nœud invalide : inchangé).

## Tasks & Acceptance

**Execution:**
- [ ] `src/wavestack/trace/catalog.py`, `src/wavestack/tools/registry.py`, `src/wavestack/tools/executor.py`, `src/wavestack/config.py`, `wavestack.toml` -- deux événements, `force`, `delegate` armable, `DelegationFailed` et son statut, section `[subagent]` -- contrat d'abord.
- [ ] `src/wavestack/bricks/registry.py`, `content/bricks/subagent.yaml`, `content/subagent.yaml`, `content/prompts/subagent.md`, `content/demo_files/guide_harnais.md` -- brique, textes, prompt, document long -- AD-12, AD-19.
- [ ] `src/wavestack/session/app_session.py` -- méta-outil, `TurnState`, boucle `sub{n}`, rendu, ratios, hooks par contexte, échecs, économie, armement, carte, schéma -- AD-4, AD-9 à AD-11, AD-25.
- [ ] `src/wavestack/web/app.py` -- `delegate` dans `ArmIntention` -- AD-18.
- [ ] `src/wavestack/web/static/app.js`, `app.css` -- projection par contexte, ligne et lignes filles, bascule de Contexte LLM, Forcer au niveau de la carte, second robot -- EXPERIENCE.
- [ ] `content/scenarios.yaml` -- scénario `subagent` (briques `short_memory`, `system_prompt`, `tools`, `subagent` ; outils `read_file` ; prompt de délégation du `guide_harnais.md` puis trois questions de quiz) -- CAP-40.
- [ ] `tests/test_subagent.py` (nouveau) -- une ligne de la matrice par test, plus : contexte `sub1` sans historique ni prompt principal, identifiants et `parent_step`, `subagent_result` seul dans l'appel principal suivant, chiffres d'économie, schéma (`core.model_sub`, cloud en réseau), ratio `sub` distinct en mode chat, carte (`force`, `limits_fr`), intention HTTP 404/422.

**Acceptance Criteria:**
- Given une délégation terminée, when on ouvre Contexte LLM, then la bascule montre séparément le contexte principal (le résultat en « Résultat du sous-agent ») et celui du sous-agent (prompt du sous-agent, tâche, résultat d'outil), chacun avec son total.
- Given une délégation terminée, when on déplie « Délégation au sous-agent » dans Orchestration, then on lit la tâche, les étapes du sous-agent (appels, outils, hooks) en lignes filles, les tokens restés dans le sous-agent, ceux réinjectés et l'économie, avec « Déclenché par le modèle » ou « Forcé par l'utilisateur ».
- Given la brique activée, when le schéma s'affiche, then un second nœud Modèle « Sous-agent » apparaît (en zone Réseau avec le fournisseur pour un modèle cloud) et s'anime pendant les appels du sous-agent, la jauge de la barre haute restant sur le contexte principal.
- Given « Afficher les actions forcées », when on clique « Déléguer au sous-agent » sur la carte, then un formulaire à préréglages arme l'action ; la puce « Armé : Délégation : … » apparaît et se désarme d'un clic, au clavier aussi.
- Given toutes briques éteintes, when on envoie un message, then le tour reste celui du LLM nu, octet pour octet.

## Spec Change Log

## Review Triage Log

## Design Notes

Le sous-agent réutilise le rendu et l'appel du tour ; seule la source des messages change. Esquisse (non normative) :

```python
def _sub_messages(self, sub, steps, chat):
    system = Part(SYSTEM_PROMPT, sub.prompt, "subagent", "subagent.agent")
    task = Part(USER_MESSAGE, sub.task, "subagent", "subagent.agent")
    return [{"role": "system", "content": [system]}, {"role": "user", "content": [task]},
            *self._step_messages(steps, history=False, group="sub", chat=chat)]
```

`delegate` passe par l'exécuteur unique comme tout méta-outil : `tool_started`/`tool_ended` de `delegate` encadrent, dans le contexte `main`, la paire `subagent_started`/`subagent_ended` et tous les événements `sub{n}`. Le front rattache ces derniers par `parent_step`, jamais par position.

## Hypothèses à valider

- H-1 Outils du sous-agent : liste configurable `[subagent] tools = ["read_file", "fetch_page"]`, restreinte aux outils activés dans la brique Outils effective (une sortie réseau reste un choix explicite, NFR-4) ; sans brique Outils, le sous-agent travaille sans outil. La brique n'exige pas la brique Outils.
- H-2 Démonstration hors ligne d'UJ-6 : document long `content/demo_files/guide_harnais.md` (≈ 2 000 tokens) lu par `read_file` ; la page du glossaire d'Anthropic n'est pas branchée (hôte non autorisé, `fetch_page` coupé à 4 000 caractères) ; le repli hors ligne de `fetch_page` reste différé.
- H-3 Nouveaux essais du sous-agent : même règle `tool_max_retries`, comptés dans ses 4 appels ; épuisés → `limit_reached{retries}` dans `sub{n}` puis `tool_ended{limit}`.
- H-4 Économie = `used` du dernier appel du sous-agent − tokens du résultat (bornée à 0) ; c'est le chiffre montré, pas une simulation du contexte principal sans délégation.
- H-5 Préservation d'état : aucune (`save_state` non tenté, le banc de mesure n'ayant pas eu lieu) ; le contexte principal est relu, la latence de l'appel suivant l'affiche.
- H-6 Résultat réinjecté en `subagent_result` même en cas d'échec de la délégation (message d'erreur), `tool_result` hook seulement si un hook bloque `delegate`.
- H-7 Forçage : bouton au niveau de la carte (la brique n'a pas de sous-option), formulaire à un champ `task` avec préréglages de `content/subagent.yaml` ; cible fixe `delegate`.
- H-8 Programme : scénario `subagent` dans un nouveau module « Sous-agent » (30 min) en fin de programme, à regrouper avec les autres scénarios du palier 2 quand ils existeront.
- H-9 Mode `forced` sans parseur d'appels : non traité (brique indisponible sans `tool_call_parser`, comme les autres briques d'outils).
- H-10 Numérotation `sub{n}` sur la vie de la session, non remise à zéro par « Vider la conversation » ni par la réinitialisation.
- H-11 Investigation menée sans sous-agent de lecture (outil indisponible dans cette exécution) : le Code Map vient d'une lecture directe du code au commit de base.

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run python -m pytest` -- expected: tout passe (tests `model` exclus)
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks (if no CLI):**
- `uv run wavestack` avec Qwen : scénario « Sous-agent », délégation par le modèle puis forcée ; bascule de Contexte LLM, lignes filles et économie dans Orchestration, second robot animé ; H5 actif avec `fetch_page` : carte de validation dans la Vue humain.

## Auto Run Result

Status: ready-for-dev
Blocking condition: aucune — arrêt demandé après la planification (« Halt after planning »).
