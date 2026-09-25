---
title: 'Rejeu du dernier prompt'
type: 'feature'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'b78866f6fafd62d246766cb99fa11ef3bfcf51e2'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Pour montrer ce qu'une brique change, l'animateur doit pouvoir reposer la même question après avoir modifié la configuration, puis comparer les deux tours (CAP-7, FR-7). Aujourd'hui, retaper la question l'ajoute à la suite de la conversation : le modèle voit la question deux fois, avec sa première réponse, et aucune vue ne met deux tours côte à côte.

**Approach:** « Rejouer le dernier prompt », en tête de la Vue humain, relance le message du dernier tour depuis l'état conversationnel qui précédait ce tour (AD-17), avec la configuration courante, actions armées comprises (story 9). Le tour rejoué est un nouveau tour relié à son origine par `turn_started{replay_of}`, badgé « Rejeu » dans la Vue humain et sur son groupe du rail (8d). « Comparer », en tête de Contexte LLM, montre deux tours côte à côte.

## Boundaries & Constraints

**Always:**
- Rejouer est une intention de classe (b) : refusée hors `idle` avec la raison, 409 comme `send` (AD-3). Sans dernier prompt (aucun tour depuis le lancement ou depuis « Vider la conversation »), refus 409 « Aucun prompt à rejouer : envoyez d'abord un message. ».
- Instantané (AD-17) : le rejeu repart de l'historique de la branche, des skills chargés et des documentations MCP chargées tels qu'ils étaient au début du tour d'origine. Tout le reste est lu dans la configuration courante (briques, sous-options, hooks, prompt système, réglages, actions armées). La même `build_turn_state` sert à l'envoi et au rejeu.
- Branche : rejouer t3 crée t4, qui fait suite à t2 ; t3 quitte l'historique mais reste dans la trace et à l'écran. Un tour rejoué est lui-même rejouable : rejouer t4 repart du même état que t3 et crée t5 avec `replay_of = t4`.
- Le « dernier prompt » est celui du dernier tour lancé, quel que soit son statut (arrêté, limite, bloqué compris).
- La liste armée est prise au moment du rejeu, sous le verrou, comme à l'envoi (correctif BH4 de la story 9).
- Après la reprise de l'instantané, le panneau des briques, le schéma et l'aperçu du contexte reflètent les skills et documentations de la branche rejouée.
- Vue humain : les tours affichés restent dans l'ordre chronologique ; le tour rejoué s'ajoute à la suite, son message utilisateur porte un badge « Rejeu » cliquable qui ouvre la comparaison avec son tour d'origine. « Rejouer le dernier prompt » est désactivé hors `idle` ou sans tour affiché, avec la raison en info-bulle.
- Rail : le groupe d'un tour rejoué porte le badge « Rejeu » à côté du statut.
- Comparaison (`turn-compare`, EXPERIENCE.md) : « Comparer » est désactivé avec moins de deux tours affichés, info-bulle « Il faut au moins deux tours pour comparer. ». Par défaut, compare le dernier tour rejoué et son origine, sinon les deux derniers tours ; deux listes permettent de choisir les tours ; « Fermer » revient à la vue habituelle. Pour chaque tour : tokens d'entrée et de sortie (sommes sur les appels du tour), temps du tour, puis les segments du dernier contexte rendu, alignés par brique, avec l'écart de tokens entre les deux tours.
- Textes en français ; contrôles atteignables au clavier avec un nom accessible.

**Never:** sélecteur de branche ou navigation entre branches ; rejouer un tour autre que le dernier ; sélection d'un tour par clic sur un message (FR-4, hors périmètre) ; nouvelle dépendance ; nouveau `SegmentKind` ; toucher au forçage (story 9), au redimensionnement (8f) ou au schéma (8e) au-delà de la reprise de l'état chargé.

## I/O & Edge-Case Matrix

| Scénario | État | Comportement attendu |
|---|---|---|
| Rejeu simple | t1, t2, t3 terminés | t4 : prompt = historique t1, t2 puis le message de t3 ; ni la question ni la réponse de t3 deux fois ; `turn_started{replay_of: "t3"}` ; historique final t1, t2, t4. |
| Brique activée avant le rejeu | prompt système activé après t1 | Le contexte de t2 (rejeu de t1) contient le segment du prompt système. |
| Skill chargé dans le tour d'origine | Caveman chargé pendant t2 | Au rejeu de t2, Caveman n'est plus chargé (retour au catalogue) ; le modèle peut le recharger. |
| Documentation chargée dans le tour d'origine | lazy loading, doc chargée pendant t2 | Au rejeu de t2, la doc n'est plus chargée ; une doc chargée pendant t1 le reste. |
| Rejeu d'un rejeu | t4 = rejeu de t3 | Rejouer donne t5, `replay_of: "t4"`, même historique de départ que t3. |
| Action armée | skill armé avant le rejeu | Consommée par le tour rejoué, badge « Forcé par l'utilisateur ». |
| Tour d'origine arrêté | t2 arrêté | Rejouer t2 repart de t1. |
| Hors idle | un tour en cours | 409 avec la raison ; rien ne change. |
| Rien à rejouer | aucun tour, ou juste après « Vider la conversation » | 409 « Aucun prompt à rejouer : envoyez d'abord un message. ». |

</frozen-after-approval>

## Code Map

- `src/wavestack/session/app_session.py` :
  - `send()` (1166-1196) : l'extraire en `_start(message, replay_of)` partagé par `send(message)` et `replay()`. Sous le premier verrou, `send` enregistre `self._last = (turn_id, message, tuple(self._history), frozenset(self._loaded_skills), frozenset(self._loaded_docs))` ; `replay()` lit `_last`, refuse s'il est `None`, remet `_history`, `_loaded_skills`, `_loaded_docs` à l'instantané, puis enregistre le même instantané sous le nouveau `turn_id`. Tout sous le verrou où l'état passe à `turn` et où `armed` est pris.
  - `build_turn_state(origin_turn)` (884-927) : l'instantané étant repris avant l'appel, le paramètre `origin_turn` et le découpage deviennent inutiles ; les supprimer (appelants : `_emit_preview` 1136, `send` 1180, tests).
  - `_run_turn` (1679-1728) : recevoir `replay_of` et l'émettre dans `turn_started` (1691 émet `None`).
  - `clear_conversation()` (1628) : remettre `_last` à `None`.
  - Après reprise de l'instantané dans `replay()` : `_emit_bricks()`, `_emit_architecture()` (le schéma montre les skills chargés, cf. `_apply_skill_loaded` 2188) ; l'aperçu (`_emit_preview`) suit déjà `turn_started`.
  - `SendRefused` (256), `_refusal_reason` (1640).
- `src/wavestack/trace/catalog.py` : `TurnStartedPayload.replay_of` existe déjà (102) ; aucun changement.
- `src/wavestack/web/app.py` : `POST /api/intentions/replay` sur le modèle de `send` (211-217), sans corps, renvoie `{"turn_id"}`, `SendRefused` → 409.
- `src/wavestack/web/static/index.html` : bouton `#replay-last` « Rejouer le dernier prompt » dans `.pane-actions` de la Vue humain (67-68, avant `#clear-conversation`) ; bouton `#compare-turns` « Comparer » dans `.pane-actions` de Contexte LLM (93).
- `src/wavestack/web/static/app.js` :
  - `applyEnvelope` `turn_started` (166-188) : garder `replayOf: p.replay_of` sur le tour.
  - `renderComposer` (1110-1140) : activer/désactiver `#replay-last` comme `#clear-conversation` (1115-1117), plus la condition « au moins un tour affiché » (`shownTurns()` 433) ; `#compare-turns` désactivé avec moins de deux tours affichés.
  - `replayLast()` sur le modèle de `clearConversation()` (953-965) : `postIntention("/api/intentions/replay")`, refus dans `store.composerError`. Branchement dans `boot()` (3117-3118).
  - `renderChat()` (1032-1096) : badge « Rejeu » (bouton, nom accessible « Rejeu de … : comparer ») dans la bulle utilisateur d'un tour avec `replayOf`, qui ouvre la comparaison sur ce tour et son origine.
  - `renderSteps()` (2036-2041) : `headParts` crée ses spans une fois (1892) : ajouter une part fixe `turn-group-replay` avec « Rejeu » ou `null`.
  - `renderContext()` (1183-1222) : si `store.compare` est ouvert, rendre la comparaison au lieu du dernier tour. Chiffres : sommes de `step.ended.prompt_tokens`/`output_tokens` des étapes `call` du tour, `turnDuration(turn)` (1905), `fmt`/`seconds` (81-82). Segments : `turn.context.segments` groupés par `brick`, dans l'ordre de première apparition, couleurs via `breakdown`/`GROUP_COLORS` (65) comme la vue habituelle ; texte intégral dans un `<details>`.
  - « Vider la conversation » (`conversation_cleared` 161-165) : fermer la comparaison.
- `src/wavestack/web/static/app.css` : `.replay-badge` (sur le modèle de `.step-badge` 612), `.turn-compare` en grille à deux colonnes qui passe en une colonne sur écran étroit ; `.turn-group-replay` près de `.turn-group-status` (864).
- Tests : `tests/fake_engine.py` (`FakeEngine(outputs=…)`, `engine.calls` décodables par `bytes(...).decode()`, `booted_session`), `tests/test_turn.py` (`_run` 23, patron 409 avec `TestClient` 192), `tests/test_forced.py` (15-42 : `tool_session`, `skills_session`, `lazy_session`, `loop`, `run`, `armed`), `tests/test_skills.py` (`skills_session` 26), `tests/test_mcp_lazy.py` (`lazy_session` 27).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/session/app_session.py` -- `_start`, `replay`, `_last`, `replay_of` dans `turn_started`, `clear_conversation`, suppression d'`origin_turn` -- AD-17, AD-3.
- [x] `src/wavestack/web/app.py` -- route `/api/intentions/replay` -- AD-18.
- [x] `src/wavestack/web/static/index.html`, `app.js`, `app.css` -- bouton de rejeu, badges « Rejeu » (Vue humain, rail), « Comparer » et vue `turn-compare` -- EXPERIENCE.md.
- [x] `tests/test_replay.py` (nouveau) -- une ligne de la matrice par test, plus la route (200, 409).
- [x] Tests existants qui appellent `build_turn_state(...)` avec un argument -- les adapter si besoin.

**Acceptance Criteria:**
- Given un tour rejoué, when la page est rechargée, then le badge « Rejeu » réapparaît dans la Vue humain et le rail (projection du journal, AD-1).
- Given deux tours affichés dont un rejeu, when on clique « Comparer » ou le badge « Rejeu », then les deux tours s'affichent côte à côte avec leurs tokens d'entrée et de sortie, leur temps et leurs segments alignés par brique ; « Fermer » revient au dernier contexte.
- Given moins de deux tours affichés, when on survole « Comparer », then il est désactivé avec « Il faut au moins deux tours pour comparer. ».
- Given le clavier, when on tabule, then « Rejouer le dernier prompt », le badge « Rejeu », « Comparer », les deux listes et « Fermer » sont atteignables avec un nom accessible.

## Implementation Notes

## Spec Change Log

## Review Triage Log

Passe 1 (2026-09-25) — relecteurs : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| EC1 | Un rejeu arrêté fait sortir le tour d'origine de la branche sans le remplacer | false | Comportement voulu : Boundaries (« t3 quitte l'historique ») et Design Notes (« Un rejeu arrêté laisse donc la branche à t1, t2 »). | rejeté |
| EC2 | Badge « Rejeu » cliqué en mode focus sur la Vue humain : la comparaison s'ouvre dans un volet masqué | low | `openCompare` ne retire que `hiddenPanes` ; `focusedPane` reste « human ». Correction directe d'une ligne. | patch |
| EC3 | Tour d'origine absent du store après rechargement : badge manquant | false | Le front rejoue le journal depuis 0 : l'origine précède toujours son rejeu ; « Vider » ne retire rien de `store.turns`. | rejeté |
| VG1 | Projection front du rejeu et comparaison sans test automatique | medium | Gap pré-vérifié : aucun banc de test JS, même écart que 5b à 9. | defer |
| VG2 / BH5 | `_emit_bricks()` au rejeu sans effet : `bricks_changed` ne porte ni skills ni docs chargés | low | Vérifié dans `_skill_options` et `_mcp_options` ; seul `_emit_architecture` change le schéma (testé par `nodes()`). Correctif = suppression. | patch |
| BH1 | La comparaison ouverte masque le contexte en direct des tours suivants | medium | `renderContext` retourne dans `renderCompare` tant que `store.compare` est posé ; un envoi après « Comparer » ne montre rien de neuf. | patch |
| BH2 | « en cours » jamais affiché, temps figé pour un tour en cours | low | `turnDuration` renvoie `Date.now() - startedAt` pour `status === null`, jamais `null`. Correction directe. | patch |
| BH3 | « Fermer » rend le focus à « Comparer » même si le badge a ouvert la vue | low | Réel ; parcours clavier rare en salle, correctif = état en plus. | rejeté |
| BH4 | Le tour d'origine reste affiché sans signe qu'il a quitté la branche | low | Décision de l'intention (ordre chronologique, deux tours consultables) ; le correctif modifierait la spec. | rejeté |
| BH6 | Test de l'action armée faible : ni `replay_of` ni liste vidée | low | Assertion directe à ajouter. | patch |
| BH7 | Route : cas « hors idle » non testé | low | Couvert au niveau session ; la route partage le mappage 409 de `send`, testé par `test_turn.py`. | rejeté |
| BH8 | Rejeu après un rejeu arrêté non testé | low | Même chemin que « Tour d'origine arrêté », testé. | rejeté |
| BH9 | `_last` en 5-uplet anonyme | low | Écrit et lu à un seul endroit ; un `NamedTuple` ajoute un type. | rejeté |
| BH10 | État restauré avant que le tour soit sûr de démarrer | low | `build_turn_state`/`submit` ne lèvent pas dans un cas montré ; correctif = restauration différée. | rejeté |
| BH11 | `.turn-compare` sans son jeton DESIGN.md (fond `surface-raised`, `rounded.md`) | low | Vérifié dans DESIGN.md (335-339). Correction CSS directe. | patch |
| BH12 | Libellés d'options non tronqués | low | `max-width: 100%` borne la liste ; troncature = logique en plus. | rejeté |

## Design Notes

L'instantané est pris à chaque envoi plutôt que reconstruit depuis les étapes de l'historique : les skills et documentations chargés ne figurent pas dans `Exchange` (une documentation n'est lisible que dans le texte d'un stub), et seul le dernier prompt est rejouable. Rejouer = reprendre l'instantané du dernier tour, puis le même chemin que l'envoi :

```python
# dans _start, sous le verrou, après le contrôle `idle` et avant le passage à `turn`
origin, message, history, skills, docs = self._last
self._history[:] = history
self._loaded_skills, self._loaded_docs = set(skills), set(docs)
```

Un rejeu arrêté laisse donc la branche à t1, t2 : le tour d'origine en est sorti, comme tout tour non terminé.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run python -m pytest` -- expected: tout passe
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks:**
- `uv run wavestack` avec Qwen : un tour, activer le prompt système, rejouer, ouvrir « Comparer » ; rejouer le rejeu ; armer Caveman puis rejouer ; recharger la page ; vider la conversation (bouton de rejeu désactivé).
