---
title: 'Tests backend manquants et garde réseau'
type: 'chore'
created: '2026-10-01'
status: 'draft'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/triage.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Sept comportements livrés ne sont protégés par aucun test (CAP-1 de `SPEC.md`) : une mutation nommée dans chaque entrée de `deferred-work.md` passerait pytest. La garde réseau (AD-15) laisse en outre passer une résolution par `socket.gethostbyname`/`gethostbyname_ex` et un envoi UDP par `socket.sendto`.

**Approach:** Un test par entrée, écrit pour échouer sur la mutation qu'elle nomme ; ajouter les trois événements d'audit au hook de `src/wavestack/net/guard.py`, avec la même règle que `getaddrinfo` / `connect`.

## Boundaries & Constraints

**Always:**
- Entrées fermées (`closed: <date> (story 1 des restes différés) — <test>`) :
  - **E008** — test marqué `model`, sauté sans `WAVESTACK_TEST_GGUF`, qui exerce `LlamaCppEngine.complete` sur un vrai GGUF : arrêt sur EOG, sortie coupée à exactement `max_tokens`, séquence d'arrêt jamais émise (ni son préfixe), annulation, décodage UTF-8 incrémental (caractère multi-octets coupé entre deux tokens).
  - **E013** — `socket.gethostbyname`, `socket.gethostbyname_ex` et `socket.sendto` vers un hôte ou une IP hors liste sont refusés par la garde et tracés comme les autres refus ; boucle locale permise.
  - **E022** — test paramétré sur les vraies déclarations `skills`, `tools`, `mcp` (et `subagent` si elle déclare la capacité) de `bricks/registry.py` : sur un modèle sans `tool_call_parser`, chacune est indisponible avec sa raison.
  - **E025** — H2 : une écriture d'`audit.log` qui échoue en `after_tool` (échec ponctuel injecté) puis réussit en `on_turn_end` du même tour ; le fichier contient toutes les lignes, sans trou ni doublon.
  - **E027** — un hook `before_tool` qui modifie les arguments, H5 actif sur un outil réseau : `approval_requested.preview` et `outbound_request` portent les mêmes arguments modifiés.
  - **E056**, **E066** — brique Raisonnement voulue : indisponible avec un modèle dont le gabarit n'a pas `enable_thinking`, effective sans nouveau clic après un changement à chaud vers un modèle qui raisonne ; `wanted` jamais modifié (patron : `test_lost_capability_leaves_wanted_and_comes_back`).
- Vérifier chaque test en appliquant la mutation de son entrée, constater l'échec, puis la défaire.
- pytest en quarts l'un après l'autre ; aucun modèle local chargé hors du test `model`.

**Never:**
- Lancer le test `model` avec un vrai GGUF sans l'accord d'Anaël.
- Modifier le comportement d'une brique, d'un hook ou du moteur pour faire passer un test : un test qui révèle un défaut le note dans `deferred` de cette story et dans `deferred-work.md`.
- Toucher aux entrées des autres stories.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Résolution hors liste | `socket.gethostbyname("example.org")` sous la garde | refus, comme `getaddrinfo` | exception de la garde, refus tracé |
| UDP hors liste | `sendto(b"x", ("203.0.113.5", 53))` | refus | idem |
| Boucle locale | `gethostbyname("localhost")`, `sendto` vers `127.0.0.1` | permis | aucune |
| H2 après échec | échec en `after_tool`, succès en `on_turn_end` | toutes les lignes du tour dans `audit.log` | échec tracé, tour poursuivi |

</intent-contract>

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q tests/test_net_guard.py tests/test_bricks.py tests/test_hooks.py tests/test_model_switch.py tests/test_render_reference.py` (noms réels à confirmer au plan) -- expected: tout passe, le test `model` sauté.
