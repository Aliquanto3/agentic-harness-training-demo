---
title: 'Story 10b — corrections post-test manuel de la story 10'
type: 'bugfix'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '3f83f09bd0db3e4e99bedf763840c106c2e7a504'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le test manuel de la story 10 (PC cible, 2026-09-25, Qwen3.5-2B Q4_K_M, CPU) a montré trois écarts : (1) le scénario `mcp_full` annonce un débordement de contexte qui n'a pas lieu (jauge 3 018 / 3 584 tokens utiles) ; (2) « ⟲ Réinitialiser » ne replie pas les cartes de briques du volet gauche (options et explications restent ouvertes) ; (3) l'explication de brique en `<details>` est peu lisible (un seul paragraphe de prose, pas de mise en forme).

**Approach:** Reformuler la consigne de `mcp_full` autour d'une jauge presque pleine et du contraste avec « Lazy loading », retirer `expects_overflow` (champ narratif, non testé, plus utilisé nulle part ailleurs) et clore l'entrée `deferred-work.md` correspondante avec les mesures du test. Faire vider `store.openExplanations` (et fermer les popovers d'explication ouverts) par `resetHarness()`, sans toucher à `clearConversation` ni au rechargement. Remplacer le `<details>` « Ce que la brique ajoute » par un bouton rond « ? » ouvrant une bulle d'aide via l'attribut natif `popover`, et restructurer `explanation_fr` de `content/bricks/*.yaml` en une liste de blocs paragraphe/liste, rendus en `<p>`/`<ul>` sans Markdown. Ajouter deux entrées à `deferred-work.md` (latence hors NFR-1, risque BH1a non vérifié).

## Boundaries & Constraints

**Always:** Conserver le rendu par nœuds DOM via `el()` (jamais d'`innerHTML`). Le bouton « ? » et la bulle respectent les tokens de `DESIGN.md`/`tokens.css` (`--rounded-full`, couleurs de charte, `hit-target-min`). Le popover reste accessible : ouverture/fermeture clavier et Échap (comportement natif de `popover`), nom accessible sur le bouton (`aria-label`). `clearConversation()` et le rechargement de page restent inchangés dans leur comportement observable.

**Never:** Pas de nouvelle dépendance JS (pas de lib de popover/tooltip). Pas de moteur Markdown. Ne pas réintroduire `expects_overflow` ailleurs. Ne pas modifier les entrées existantes de `deferred-work.md` autres que celle citée.

</frozen-after-approval>

## Code Map

- `content/scenarios.yaml:5-7,82-94,96-109` -- retirer la doc et le champ `expects_overflow: true` de `mcp_full` ; reformuler `description_fr` de `mcp_full` (jauge presque pleine, sans annoncer de débordement) et ajuster celle de `mcp_lazy` (ne plus présupposer un débordement du scénario précédent).
- `src/wavestack/scenarios.py:30,58` -- retirer le champ Pydantic `expects_overflow` (plus aucun scénario ne l'utilise) et sa sérialisation.
- `src/wavestack/web/static/app.js:1261` -- retirer la phrase concaténée liée à `expects_overflow`.
- `_bmad-output/implementation-artifacts/deferred-work.md:175-177` -- clore l'entrée `mcp_full` avec les mesures (3 018/3 584 tokens ; lazy loading ~1 040) ; ajouter deux entrées (tour MCP doc complète 109,5 s / 91 tokens de sortie / contexte 3 018 tokens, bien au-delà de NFR-1 ; risque BH1a — flèches clavier sur le sélecteur sous Windows non vérifié, l'animateur ayant utilisé la souris).
- `src/wavestack/web/static/app.js:41` -- `store.openExplanations` (Set) ; après ce changement il ne sert plus qu'aux listes d'options (clé `options:{brick.id}`), plus aux explications.
- `src/wavestack/web/static/app.js:1300-1302` (`resetHarness`) -- ajouter `store.openExplanations.clear()` et fermer tout popover d'explication ouvert (`.hidePopover()`), avant le `render()` déjà déclenché par `scenarioIntention`.
- `src/wavestack/web/static/app.js:536-545` (`<details class="brick-explanation">`) -- remplacer par un bouton rond `popovertarget` + un élément `popover` positionné en haut à droite de la carte, contenu généré depuis les blocs d'`explanation_fr`.
- `src/wavestack/web/static/app.js:568-621` (`brickOptions`) -- inchangé (garde `store.openExplanations`, clé `options:`).
- `src/wavestack/bricks/contract.py:40-46` (`BrickContent.explanation_fr`) -- passe de `str` à `list[str | list[str]]` (un `str` = paragraphe, une liste = puces).
- `src/wavestack/trace/catalog.py:223` (`BrickState.explanation_fr`) -- même type, pour rester aligné avec `BrickContent`.
- `src/wavestack/session/app_session.py:~671` (`_emit_bricks`) -- transmet la structure telle quelle (plus une simple chaîne).
- `content/bricks/{mcp,hooks,short_memory,skills,system_prompt,tools}.yaml` -- restructurer `explanation_fr` en blocs courts ; `mcp.yaml` doit isoler les deux modes (documentation complète / lazy loading) en liste.
- `src/wavestack/web/static/app.css:1417-1496` (`.brick-card`) -- `position: relative` sur la carte ; nouveau style pour le bouton rond et le popover (rayons/couleurs des tokens existants).
- `tests/test_bricks.py:250,329,370,384` -- adapter `explanation_fr="x"` à la nouvelle structure (ex. `["x"]`).

## Tasks & Acceptance

**Execution:**
- [x] `content/scenarios.yaml` -- retirer `expects_overflow` de `mcp_full`, reformuler les deux `description_fr` -- corrige l'annonce erronée constatée au test.
- [x] `src/wavestack/scenarios.py` -- retirer le champ `expects_overflow` du modèle et de la sérialisation -- plus aucun consommateur.
- [x] `src/wavestack/web/static/app.js` (ligne ~1261) -- retirer la phrase liée à `expects_overflow` -- suit la suppression du champ.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- clore l'entrée `mcp_full`, ajouter les deux nouvelles entrées -- trace les constats du test.
- [x] `src/wavestack/bricks/contract.py`, `src/wavestack/trace/catalog.py` -- changer le type d'`explanation_fr` -- support de la restructuration en blocs. (Aussi retiré `ScenarioEntry.expects_overflow` dans `catalog.py`, manqué par la Code Map, nécessaire une fois la clé disparue de `payload()`.)
- [x] `content/bricks/*.yaml` (6 fichiers) -- restructurer `explanation_fr` en paragraphes/listes -- lisibilité demandée.
- [x] `src/wavestack/session/app_session.py` -- adapter `_emit_bricks` à la nouvelle structure -- garde l'API front cohérente.
- [x] `src/wavestack/web/static/app.js` -- remplacer le `<details>` d'explication par bouton « ? » + `popover`, rendre les blocs en `<p>`/`<ul>` -- UX demandée.
- [x] `src/wavestack/web/static/app.js` (`resetHarness`) -- vider `store.openExplanations` et fermer les popovers ouverts -- comportement de Réinitialiser demandé.
- [x] `src/wavestack/web/static/app.css` -- styles du bouton rond et du popover -- cohérence avec `DESIGN.md`.
- [x] `tests/test_bricks.py` -- adapter à la nouvelle structure d'`explanation_fr` -- garde les tests verts.

**Acceptance Criteria:**
- Given le scénario `mcp_full` chargé, when la jauge est lue après envoi du prompt, then elle affiche un contexte proche du plein sans dépassement, et la consigne ne prétend plus qu'il déborde.
- Given au moins une brique avec une liste d'options ouverte et une bulle d'aide ouverte, when on clique « ⟲ Réinitialiser », then les deux se referment, alors que « Vider la conversation » et un rechargement de page ne les referment pas (comportement inchangé).
- Given une carte de brique, when on clique le bouton « ? », then une bulle s'ouvre avec le contenu d'`explanation_fr` en paragraphes et listes HTML, se ferme à Échap ou au clic extérieur, et le bouton porte un nom accessible.
- Given `content/bricks/mcp.yaml`, when l'explication est affichée, then les deux modes MCP apparaissent comme deux items distincts d'une liste, pas noyés dans un paragraphe unique.

## Implementation Notes

- Le bouton « ? » utilise le positionnement natif par ancre CSS (`anchor-name`/`position-anchor`, `position-area`), sans dépendance ; `ponytail:` noté en commentaire dans `app.js` : pas de repli hors moteurs Chromium, acceptable car la démo cible un navigateur Chromium sur le PC.
- `ScenarioEntry.expects_overflow` (`src/wavestack/trace/catalog.py`) retiré en plus de la Code Map : `payload()` ne l'émet plus, ce champ aurait fait échouer la validation du DTO de trace.
- Vérifié : `uv run pytest` (310 passed, 2 deselected), `uv run ruff check .` (aucune erreur), `node --check app.js` (syntaxe OK). Non vérifié : contrôles manuels (jauge `mcp_full`, ouverture/fermeture au clic/clavier/Échap, non-régression de « Vider la conversation » et du rechargement) — à faire sur le PC cible, aucun navigateur disponible dans cet environnement.
- Revue (Blind Hunter, Edge Case Hunter, Verification Gap) : un `patch` appliqué — le popover d'aide perdait son état ouvert à chaque `render()` non lié (déclenché par `model_delta` toutes les ~50 ms pendant un tour en cours) ; ajout de `store.openBrickHelp` et rouverture via `showPopover()` après reconstruction. Corrigés dans la foulée : relief au clic sur `.brick-help` (cohérence avec les autres boutons ronds), position de repli statique pour `.brick-explanation` si le positionnement par ancre CSS n'est pas supporté. Reste diagnostiqué mais différé (voir `deferred-work.md`) : aucun banc de test JS pour ce popover ni pour `resetHarness`, écart déjà connu et accepté depuis les stories 5b–9b. Re-vérifié après patch : `uv run pytest` (310 passed, 2 deselected), `uv run ruff check .` (aucune erreur).

## Spec Change Log

_Vide : aucun `bad_spec` de bouclé sur cette revue._

## Review Triage Log

- [Blind Hunter] Popover open state not tracked in `store`; `render()` rebuilds every `.brick-card` from scratch → **high** — Verified: `renderBricks()` recreates each card (including the popover) on every call; `scheduleRender()` (`app.js:363-370`) calls `render()` on every `model_delta` SSE event, throttled to ~1/frame, during any streaming turn. An open help popover is destroyed and never reopened, unlike the old `<details>` which restored `.open` from `store.openExplanations` on every render. Real, frequent regression.
- [Edge Case Hunter] Same finding, same root cause (`app.js:429-431,536-561`) — merged with the row above.
- [Blind Hunter] `BrickState.explanation_fr` (`catalog.py:223`) lacks `Field(min_length=1)` unlike `BrickContent` → **false** — different semantics: `BrickContent` validates authored YAML (must be non-empty); `BrickState.explanation_fr` legitimately falls back to `[]` when `content` is `None` (`app_session.py:671`), and the front-end already guards on `?.length` before rendering. No bug.
- [Blind Hunter] `.brick-help` lacks the relief press style every other round/pill button uses → **low** — verified against `app.css` (lines 35, 45, 89, 1435…). Real but cosmetic; fix is a direct one-line addition, so not auto-rejected.
- [Blind Hunter] Tasks & Acceptance checked `[x]` despite manual browser checks being unverified → **false** — the checklist covers code-change tasks (done, verified against the diff); the still-open manual checks live under `## Verification > Manual checks` and are already flagged as not run in Implementation Notes. No contradiction.
- [Blind Hunter] CSS anchor positioning has no fallback position for non-Chromium engines → **low** — verified: an unsupported browser silently ignores `position-area`/`position-try-fallbacks`, leaving `.brick-explanation` at a default top-left `position: fixed`. Real degradation; fix is a direct, trivial default position.
- [Blind Hunter] Reformulated `mcp_full` copy ("déjà presque pleine") is tied to one measurement/model and could go stale → **low, rejected** — the reformulation direction was explicitly dictated by the human's story-corrective request; the wording is qualitative (no hardcoded numbers); unlikely to be hit in this fixed demo setup, and a model-aware dynamic fix would be well beyond a direct correction.
- [Blind Hunter] No in-app warning for the ~109.5 s `mcp_full` turn latency → **rejected, out of scope** — the Approach explicitly limited this concern to a `deferred-work.md` entry, not a new UI warning; the intent excludes building new UI here.
- [Blind Hunter] `test_bricks.py` fixtures only cover the flat `["x"]` shape, not nested bullets → folded into the verification-gap row below — same underlying gap (no rendering test exists at all); the nested shape is exercised incidentally by `test_http_intentions_and_state` loading the real YAML files.
- [Verification Gap, pre-verified] No automated test for popover open/close or `resetHarness` clearing `openExplanations`/popovers → **medium, filed disposition `defer`** — repo-wide search confirms no JS test harness exists; continues an already-documented, accepted gap (`deferred-work.md`, stories 5b–9b).
- [Edge Case Hunter] `anchor-name`/popover id built from raw, unescaped `brick.id` → **low, rejected** — all current brick ids are fixed backend-declared slugs, never user input; not reachable today.
- [Edge Case Hunter] `Field(min_length=1)` on `explanation_fr` doesn't forbid an empty nested bullet list → **low, rejected** — unlikely (all 6 shipped YAML files are well-formed) and the fix is more than a direct correction (a new `model_validator`).
- [Edge Case Hunter] `brick.explanation_fr?.length` doesn't guard a non-array truthy value (e.g. a stale cached string) → **low, rejected** — single-page app with no persisted cross-deploy client cache; not reachable in normal operation.

**Routing:** patch — popover-survives-re-render fix; `.brick-help` relief style; anchor-positioning fallback. defer — JS test coverage gap (see new `deferred-work.md` entry).

## Design Notes

Structure retenue pour `explanation_fr` (YAML et Pydantic `list[str | list[str]]`) : chaque item est soit une chaîne (rendue en `<p>`), soit une liste de chaînes (rendue en `<ul><li>`). Exemple pour `mcp.yaml` :

```yaml
explanation_fr:
  - "Un serveur MCP est un programme séparé du harnais qui expose ses propres outils."
  - - "En documentation complète : la documentation de chaque outil entre dans le contexte."
    - "En lazy loading : le modèle ne voit qu'une ligne par outil, chargée à la demande."
  - "Un serveur public reçoit les données de chaque appel, visibles dans Orchestration."
```

Popover : `<button class="brick-help" popovertarget="explain-{brick.id}" aria-label="Ce que la brique {label} ajoute">?</button>` associé à `<div id="explain-{brick.id}" popover>…</div>`. Pas de gestion JS de l'ouverture/fermeture (natif) ; seul `resetHarness` appelle `hidePopover()` explicitement puisque le reset est un événement programmatique, pas une interaction utilisateur sur le popover.

## Verification

**Commands:**
- `uv run pytest` -- expected: tests verts, y compris `tests/test_bricks.py` adapté.
- `uv run ruff check .` -- expected: sans erreur.

**Manual checks (if no CLI):**
- Lancer le scénario `mcp_full`, lire la jauge, vérifier l'absence de mention de débordement.
- Ouvrir une bulle d'aide et une liste d'options, cliquer « ⟲ Réinitialiser », vérifier qu'elles se referment ; vérifier que « Vider la conversation » ne les referme pas.
- Vérifier au clavier (Tab, Entrée, Échap) l'ouverture/fermeture du popover d'aide.
