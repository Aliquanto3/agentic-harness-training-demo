---
title: 'Fournisseurs natifs (5/5) : recette sur le PC cible'
type: 'chore'
created: '2026-10-03'
status: 'done'
baseline_commit: 'c396d6ad6fe8e9870af4deeed914deea1eb56b06'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/SPEC.md'
  - '{project-root}/_bmad-output/implementation-artifacts/resultats-restes-pc-2026-10.md'
  - '{project-root}/_bmad-output/implementation-artifacts/mesures-anthropic-2026-10.md'
  - '{project-root}/_bmad-output/implementation-artifacts/mesures-openai-2026-10.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les stories 3 et 4 ont été testées sur faux serveur et par quelques appels isolés ; le Success signal de SPEC.md (un scénario Outils et un scénario Raisonnement par modèle, réflexion visible, coût fidèle, proxy du poste traversé) n'a jamais été joué dans l'application réelle, sur le PC cible.

**Approach:** Recette réelle dans WaveStack lancé sur le PC cible (port 8420), pilotée par l'API locale (`/api/intentions/*`) et le flux SSE (`/api/stream`) par un script jetable hors du dépôt, comme la recette des restes du 2026-10-02 : « Tester », puis un tour par brique (Raisonnement, Outils, MCP, Sous-agent) pour `claude_haiku`, `claude_sonnet` et `openai_luna`, plafond 5 $, et un tableau de résultats `resultats-fournisseurs-natifs-pc-2026-10.md` sur le modèle de `resultats-restes-pc-2026-10.md`.

## Boundaries & Constraints

**Always:**
- Avant de lancer le serveur : vérifier qu'aucun processus n'écoute sur 8420 (`Get-NetTCPConnection -LocalPort 8420`) ; sauvegarder `settings.json` et `memory.json` de `%LOCALAPPDATA%\WaveStack`, les restaurer après ; arrêter le serveur à la fin (Ctrl+Break dans sa console, voir la mémoire du projet : `CREATE_NEW_CONSOLE`, `GenerateConsoleCtrlEvent`).
- Clés : `ANTHROPIC_API_KEY` et `OPENAI_API_KEY` lues dans l'environnement UTILISATEUR de Windows (registre) et passées au seul processus serveur, jamais affichées, journalisées, écrites ni commitées ; `api_keys.json` n'est pas modifié.
- Par modèle, chaque ligne du tableau dit le geste, l'attendu, l'observé tiré du journal (`model_call_ended`, `outbound_request`, `consumption_updated`, `turn_ended`…) et le verdict : « Tester » ; un tour avec la brique Raisonnement (réflexion visible au canal Raisonnement) ; un tour Outils (`native_tools`) ; un tour MCP (`mcp_lazy`) ; un tour Sous-agent (`subagent`) ; le coût affiché (total de la séance) et l'empreinte EcoLogits (`impact_method`, fourchettes) ; le passage du proxy du poste (`api.anthropic.com`, `api.openai.com`).
- Coût : relever le coût par appel et le total de WaveStack ; la comparaison avec la console du fournisseur (SPEC.md : écart ≤ 10 %) demande la session d'Anaël sur les consoles : la consigner comme geste à faire par Anaël, avec les chiffres de WaveStack à comparer et l'heure des appels.
- Un modèle bloqué par son compte (crédit OpenAI épuisé le 2026-10-03) est noté « non joué » avec la réponse exacte du fournisseur ; essayer d'abord un « Tester » pour savoir si le blocage dure.
- Toute anomalie de code trouvée : corrigée dans cette story si elle relève des stories 1 à 4 (test à l'appui), sinon notée dans `deferred-work.md`.
- Plafond de séance 5 $ ; budget visé : moins de 2 $ pour toute la recette.

**Never:**
- Pas de Chrome ni d'E2E dans cette story (la recette navigateur appartient à la batterie qui suit) ; pas de modèle local chargé en même temps qu'une autre mesure.
- Pas de modification de `api_keys.json`, ni de `settings.json` laissée en place.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Raisonnement | `claude_haiku`, brique Raisonnement, une question qui fait réfléchir | `model_delta` au canal `reasoning`, réponse, coût | N/A |
| Outils | `native_tools`, prompt 1, chaque modèle | appel d'outil natif, résultat, réponse | N/A |
| Compte bloqué | `openai_luna` sans crédit | « non joué », message de WaveStack relevé | consigné |
| Proxy | premier appel à chaque hôte | 200 ou refus du proxy relevé (`outbound_response`) | consigné |

</frozen-after-approval>

## Code Map

- `_bmad-output/implementation-artifacts/resultats-restes-pc-2026-10.md` -- modèle du rapport (en-tête poste/date/code/modèles/méthode, tableau, correctifs).
- `src/wavestack/web/app.py` -- routes `/api/intentions/*` (en-tête `Origin: http://127.0.0.1:8420` exigé) et `/api/stream`.
- `src/wavestack/scenarios.py`, `content/scenarios/` -- scénarios `native_tools`, `mcp_lazy`, `subagent` et leurs prompts.
- `src/wavestack/cli.py` -- lancement (`uv run wavestack`), `BROWSER` (barres obliques) pour ne pas ouvrir de navigateur, délai de grâce de fermeture.

## Tasks & Acceptance

**Execution:**
- [x] Script jetable (bloc-notes de la session) -- lancer le serveur, piloter les tours, relever le journal.
- [x] `_bmad-output/implementation-artifacts/resultats-fournisseurs-natifs-pc-2026-10.md` -- tableau des résultats, coûts, actions d'Anaël (consoles, crédit OpenAI).
- [x] `_bmad-output/specs/spec-fournisseurs-natifs/SPEC.md` -- question ouverte du proxy tranchée.
- [x] Correctifs éventuels avec leurs tests ; sinon entrées dans `deferred-work.md`.

**Acceptance Criteria:**
- Given WaveStack lancé sur le PC cible avec les clés, when la recette est jouée, then chaque ligne du tableau a un verdict (OK, constat, non joué avec sa raison, ou défaut corrigé) et le coût total de la recette est relevé.
- Given la fin de la recette, then `settings.json` et `memory.json` sont restaurés, aucun serveur n'écoute sur 8420 et aucune clé n'apparaît dans le dépôt.

## Implementation Notes

- PC partagé de 16 Go : une seule chose lourde à la fois ; pas de pytest pendant que le serveur tourne. Si un correctif touche le code, `pytest` des fichiers concernés après l'arrêt du serveur.

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-03) : couches sautées, annoncé par l'orchestrateur. La story ne change aucun code (recette et documents seulement) ; le rapport a été relu directement par l'orchestrateur : tableau complet, verdicts étayés par le journal, actions d'Anaël listées.

## Verification

**Commands:**
- `Get-NetTCPConnection -LocalPort 8420` -- expected: rien à la fin
- `git grep -nE "sk-ant-|sk-proj-"` -- expected: aucun résultat
