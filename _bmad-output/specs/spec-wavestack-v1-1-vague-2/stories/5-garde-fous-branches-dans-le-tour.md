---
title: 'WaveStack V1.1 vague 2 (5/10) : garde-fous branchés dans le tour, verdicts et brique interactive'
type: 'feature'
created: '2026-10-16'
status: 'review'
baseline_commit: '5524d0b'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/guardrails.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/stories/4-garde-fous-entree-sortie.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-5, CAP-6. Story 4 a livré un moteur de garde-fous mesuré (toxicité,
données personnelles) mais débranché : rien ne l'appelle dans un tour, aucun réglage n'est
accessible depuis l'interface, et aucun verdict n'apparaît ni dans la conversation ni dans
Orchestration ni dans le journal de sécurité (CAP-3, story 1).

**Approach:**
- `AppSession._guardrail_check(turn_id, direction, text)` (nouveau) : appelle
  `GuardrailsManager.check`, applique le masquage retenu (le texte masqué remplace celui
  envoyé plus loin), émet un événement `guardrail_verdict` (un par garde-fou actif, comme
  `hook_decided`) et écrit dans `SecurityJournal` (`source="guardrail"`, interface d'ajout
  simple de la story 1). Jamais d'écriture quand le mode est désactivé.
- Branchement dans `_turn` (`app_session.py`) : une fois en entrée, juste après
  `_consume_armed` et avant RAG (le message de l'utilisateur) ; une fois en sortie, à l'unique
  point de retour `"completed"` (la réponse du modèle). Un verdict qui bloque renvoie
  `"blocked", "", ""` (même statut qu'un hook qui bloque) ; un verdict qui masque remplace le
  texte qui continue vers le reste du tour.
- Brique interactive : `AppSession._guardrails_card()` fournit, par garde-fou actif
  (toxicité, données personnelles), un `guard-mode-switch` (3 segments) et deux boutons
  « Essayer : … » (CAP-6, exemples neutres de `guardrails.md`) ; `injection` reste
  « non installé » (story 13, Prompt Guard, pas construit ici). Réglage par
  `POST /api/intentions/guardrail_mode` → `AppSession.set_guardrail_mode`.
- UI : `verdict-banner` sous la réponse dans Vue humain (rouge si bloqué, jaune si
  masqué/signalé), étape dépliable dans Orchestration (même motif que `hookCard`), toutes
  deux alimentées par les textes déjà rendus dans l'événement (`guardrail_text`,
  `direction_text`, `mode_text`, `verdict_text`, `banner_text`) — le front n'a pas de
  catalogue de libellés à tenir à jour.
- Reports de la revue de la story 4, repris ici : un échec de premier chargement (modèle
  absent/cassé) est mis en cache (`GuardrailsManager._load_errors`), jamais retenté à chaque
  tour ; `unload_idle()` est appelé quand la brique s'éteint (`set_brick("guardrails",
  False)`) ; le coût par phrase de la toxicité est borné à 64 fenêtres (`toxicity.py`,
  `_MAX_WINDOWS`) plutôt qu'affiché.

**Decisions (prises par Claude, sans effet sur le contrat) :**
- Le masquage en sortie s'applique au texte retourné par `_turn` (ce qui part dans
  l'historique), pas au flux de tokens déjà diffusé en direct (`model_delta`) : une
  réponse qui contient des données personnelles les a déjà montrées token par token avant
  que le garde-fou ne s'exécute sur le texte complet. Limite connue, à dire en démo ; le
  scénario validé de `EXPERIENCE.md` (flux 1, étape 5) démontre le masquage en entrée, où ce
  problème ne se pose pas (rien n'est diffusé avant l'appel au modèle).
- NOTICE des licences (OpenRAIL++, MIT) non ajouté : les modèles sont téléchargés par
  l'utilisateur (toxicité) ou installés comme dépendances Python (Presidio, spaCy), jamais
  inclus dans le dépôt — hors du périmètre du fichier NOTICE existant (« third-party material
  included in this repository »).
- `unload_idle` après inactivité (sans que la brique soit éteinte) reporté : aucune
  infrastructure de minuterie d'inactivité n'existe pour aucune brique du harnais ; en
  construire une pour ce seul cas est hors de proportion avec cette story.
- `GuardrailVerdictPayload` et l'extension de `BrickState` (`guardrails`) ajoutées au
  catalogue (`trace/catalog.py`) : tout champ non déclaré y est silencieusement ignoré par
  pydantic (`extra` par défaut), ce qui aurait caché la brique au front sans erreur visible.

## Boundaries & Constraints

**Always:**
- Un verdict en erreur ne bloque jamais le tour (fail-open, matrice figée de la story 4) ;
  son statut `error` reste visible dans le journal et, s'il y a eu détection côté erreur,
  nulle part d'autre (rien n'est affiché sans preuve).
- Toujours dire qui a décidé et ce qui n'est pas parti (`EXPERIENCE.md`), dans
  `banner_text` : « Le modèle ne l'a pas reçu » (entrée bloquée), « Vous n'avez pas reçu la
  réponse » (sortie bloquée).
- Aucun pytest ne télécharge un modèle : `tests/test_guardrails_turn.py` n'injecte que des
  `Classifier` factices, comme `tests/test_guardrails.py`.
- `injection` ne reçoit ni interrupteur ni bouton Essayer (story 13).

**Never:**
- Pas de modification de `src/wavestack/mcp/`, `mcp.html`/`mcp.js` (lane A).
- Pas de contenu dangereux réel (exemples neutres et fabriqués de `guardrails.md`).
- Pas de nouveau minuteur d'inactivité générique (voir Decisions).

## Code Map

- `src/wavestack/guardrails/manager.py` — `GuardrailsManager._load_errors` (cache d'échec de
  chargement), `_classifier`/`_check_one` mis à jour, `unload_idle` le vide aussi.
- `src/wavestack/guardrails/toxicity.py` — `_MAX_WINDOWS` (coût borné par message).
- `src/wavestack/session/app_session.py` — `_guardrail_check` (nouveau), branché deux fois
  dans `_turn` ; `_guardrails_card`, `set_guardrail_mode` (nouveaux) ; `set_brick` appelle
  `unload_idle` quand `guardrails` s'éteint ; `_guardrail_steps` (compteur de pas, comme
  `_hook_steps`).
- `src/wavestack/trace/catalog.py` — `GuardrailVerdictPayload` (+ dans `PAYLOAD_MODELS`),
  `GuardrailCard`/`GuardrailModeOption`/`GuardrailExample`, `BrickState.guardrails`.
- `src/wavestack/web/app.py` — `GuardrailModeIntention`, `POST /api/intentions/guardrail_mode`.
- `content/messages.yaml` (+ i18n en/de) — `guardrails.labels/directions/modes/verdicts/
  banner/decisions/examples/injection_not_installed`, `web.unknown.guardrail_mode`.
- `content/ui.yaml` (+ i18n en/de) — `main.orch.guardrail.*` (détail déplié d'Orchestration),
  `main.bricks.status.not_installed`, `main.log.kinds.guardrail_verdict`.
- `src/wavestack/web/static/app.js` — case `guardrail_verdict` (tour et sous-agent non
  couvert, story 4/5 : hors périmètre, voir Révue) ; ligne Orchestration (`guardrailCard`) ;
  `verdict-banner` (Vue humain) ; `guardrailsParts`/`setGuardrailMode` (brique) ;
  `eventSummary` (E031).
- `src/wavestack/web/static/app.css` — `.verdict-banner`, `.guard-mode-switch`,
  `.guardrail-*`, `.status-chip`.
- `tests/test_guardrails.py` — `test_failed_load_is_cached_never_retried_every_turn`.
- `tests/test_guardrails_turn.py` (nouveau) — blocage en entrée, masquage en sortie,
  journal de sécurité.

## Tasks & Acceptance

**Execution:**
- [x] `GuardrailsManager` : cache d'échec de chargement, borne de la toxicité.
- [x] `AppSession._guardrail_check`, branchement entrée/sortie dans `_turn`.
- [x] `_guardrails_card`, `set_guardrail_mode`, route HTTP.
- [x] Catalogue (`GuardrailVerdictPayload`, `BrickState.guardrails`).
- [x] Textes fr/en/de (messages et ui).
- [x] `app.js`/`app.css` : verdict-banner, étape Orchestration, brique interactive.
- [ ] E2E (non lancés par le développeur, consigne de l'orchestrateur) : voir Verification.

**Acceptance Criteria:**
- Given le garde-fou toxicité en Bloquer, when l'utilisateur envoie l'exemple qui déclenche,
  then le modèle ne reçoit jamais l'appel (aucun `model_call_started`), le tour se termine
  `blocked`, un verdict-banner rouge apparaît sous la ligne du tour, et le journal de
  sécurité reçoit une entrée `blocked`.
- Given le garde-fou données personnelles en Masquer, when la réponse du modèle contient des
  coordonnées, then le texte retourné par le tour (et son historique) les remplace par
  `[TÉLÉPHONE]`/`[E-MAIL]`/…, et le verdict porte `masked_text`.
- Given le garde-fou désactivé, then `GuardrailsManager.check` ne renvoie aucun verdict pour
  lui (aucun événement, aucune ligne du journal).
- Given un classifieur dont le chargement échoue, when deux tours s'enchaînent, then le
  second ne retente pas le chargement (`_load_errors`), et chaque verdict porte `error` sans
  jamais bloquer le tour.
- Given la brique Garde-fous indisponible (dépendance absente) ou éteinte, then la brique
  affiche « non installés » et aucun interrupteur n'agit sur un garde-fou réel.

## Implementation Notes

- Point d'application unique par direction, dans `_turn` seulement (pas dans
  `_run_subagent`) : le sous-agent, contexte séparé (AD-11), n'était pas dans le périmètre
  donné par l'orchestrateur (« touche la boucle de tour (app_session.py) ») ; ses propres
  garde-fous restent à faire si une story future les demande.
- `GuardrailsManager.check` renvoie un verdict par garde-fou actif même sans détection
  (CAP-3 : « chaque verdict de garde-fou » au journal) ; seul le `verdict-banner` filtre sur
  `detected` ou `status == "error"` (rien à dire visuellement quand rien n'a été trouvé).
- `GuardrailModeIntention` refuse `injection` et tout mode hors `block`/`flag`/`off` (422) :
  aucun mode n'est silencieusement ignoré (`AppSession.set_guardrail_mode` lève `ValueError`).
- Testé : `uv run pytest -q --tb=short tests/test_guardrails.py tests/test_guardrails_turn.py`
  (15 tests, 2 nouveaux fichiers/cas) et `tests/test_turn.py tests/test_bricks.py
  tests/test_web_app.py tests/test_ui_texts.py tests/test_trace_architecture.py
  tests/test_i18n.py` pour la non-régression (catalogue, bricks, i18n, app web) — tous verts.

## Spec Change Log

## Review Triage Log

(pas encore de relecture)

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_guardrails.py tests/test_guardrails_turn.py` — 15
  passés (1 skip : le test Presidio réel sans l'extra `guardrails`).
- `uv run pytest -q --tb=short tests/test_turn.py tests/test_bricks.py tests/test_web_app.py` —
  116 passés (pas de régression).
- `uv run pytest -q --tb=short tests/test_ui_texts.py tests/test_trace_architecture.py
  tests/test_i18n.py` — 181 passés (catalogue, textes fr/en/de).
- `python .claude/cost-kit/controle_rapide.py` — propre (lint et format).
- E2E (non lancé par le développeur, consigne de l'orchestrateur) : `s_hooks` (motif de
  disclosure-row le plus proche de `guardrailCard`) et `s_native_tools` (E031 : chaque type
  du catalogue a son libellé et son résumé — couvre `guardrail_verdict`). Aucun scénario
  E2E dédié aux garde-fous n'existe encore : à créer dans une story qui construit la brique
  Garde-fous de bout en bout à l'écran (ou la page Sécurité, story 10).

</frozen-after-approval>
