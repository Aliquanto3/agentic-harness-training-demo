---
title: "Latence CPU : préremplissage du premier tour et documentation lazy en résultat d'outil"
type: 'feature'
created: '2026-10-01'
status: 'draft'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-lot-a-cache-entre-les-tours.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Sur le PC cible (Qwen3.5-2B, CPU, ≈ 30 tokens/s en lecture), le premier tour d'un scénario chargé attend 46 à 56 s avant le premier token (E122, NFR-1 vise 30 s), alors que l'animateur lit la consigne pendant ce temps. En lazy loading, charger une documentation réécrit la définition des outils : le tour suivant relit tout le contexte (≈ 40 s, `prefix_not_reused{cause: system}`, E121) (CAP-4).

**Approach:** (1) Au lancement d'un scénario en mode local, évaluer dans le moteur la partie du contexte du premier tour qui ne dépend pas du message (message système, outils, mémoire), pour que le premier appel la réutilise. (2) **Si Anaël valide D16**, placer la documentation chargée par `load_tool_doc` dans l'historique, comme résultat d'outil (append-only), au lieu de la définition de l'outil dans `tools`.

## Boundaries & Constraints

**Always:**
- Entrées fermées : **E122** ; **E121** seulement si D16 = oui (sinon, l'entrée reste ouverte avec la décision).
- Préremplissage : mode local et moteur en processus seulement ; démarre après `scenario_changed`, s'abandonne dès qu'un tour, un chargement de modèle, un réglage de brique ou un autre scénario arrive (le moteur est exclusif) ; ne change ni la jauge, ni le contexte envoyé, ni les événements du tour. Un événement le trace (début, fin ou abandon, tokens évalués, durée), visible dans le journal, pas dans le rail du tour.
- Le premier appel du premier tour réutilise les ids préremplis (contrôle de `spec-lot-a` : aucun `prefix_not_reused`) ; `evaluated_tokens` le montre.
- Si D16 = oui : AD-25 et AD-4 amendés dans ARCHITECTURE-SPINE ; le résultat de `load_tool_doc` porte la documentation complète de l'outil (segment `tool_catalog` attribué au serveur MCP) ; l'outil est appelable dans le même tour et les suivants ; « Vider la conversation » et le rejeu suivent la branche (AD-17) ; Contexte LLM et la jauge le montrent comme résultat d'outil ; EXPERIENCE.md et la carte de la brique MCP disent où va la documentation.
- Tests avec le faux moteur (ids, cache) ; mesure réelle renvoyée à la story 7 (`prompt_ms` du premier tour de `mcp_lazy` et `subagent`, et du tour qui suit un `load_tool_doc`, avant et après).

**Never:**
- Préremplir en mode cloud ou serveur local, ou bloquer une action de l'utilisateur en attendant le préremplissage.
- Changer ce que le modèle reçoit au premier tour (même texte, mêmes ids).
- Implémenter E121 sans la validation de D16.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Préremplissage fini | scénario lancé, attente, premier message | premier appel réutilise le préfixe, `evaluated_tokens` réduit | aucune |
| Message pendant le préremplissage | message envoyé à mi-chemin | préremplissage abandonné, tour normal sans attente notable | abandon tracé |
| Mode cloud | modèle cloud actif | aucun préremplissage | aucune |
| D16, documentation chargée | `load_tool_doc(local__define_term)` puis tour suivant | pas de `prefix_not_reused{cause: system}` | aucune |

</intent-contract>

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q tests/test_turn_cache.py tests/test_engine_cache.py tests/test_scenarios.py tests/test_mcp*.py tests/test_forced.py`, en quarts -- expected: tout passe.
- E2E (avec l'accord d'Anaël) : `--only mcp_full mcp_lazy subagent sovereignty` -- expected: 0 échec.
