---
title: 'Lot C : budget de raisonnement fermé par le harnais'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '0f5412097f0b8859f382299c61236325fac9f73e'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/CLAUDE.md'
warnings: []
deferred:
  - summary: >-
      Un arrêt demandé au moment exact de la coupe n'est pas testé.
    evidence: |-
      Course étroite entre le contrôle d'annulation du moteur et celui du harnais ; effet limité à la trace (`reasoning_cut` émis pour un tour arrêté).
    location: >-
      src/wavestack/session/app_session.py:_call_model
    severity: low
  - summary: >-
      Le rendu de l'étape « Raisonnement coupé » et de la ligne de budget n'est vérifié par aucun test automatique.
    evidence: |-
      Pas de banc de test JS dans le dépôt ; à voir au test sur le PC cible.
    location: >-
      src/wavestack/web/static/app.js
    severity: low
  - summary: >-
      Le critère « réponse en moins de 120 s » peut être manqué par construction avec le budget par défaut.
    evidence: |-
      Non vérifié : ≈ 11 tokens/s sur le PC cible (1 536 tokens en 137 s), soit ≈ 90 s pour 1 024 tokens de réflexion. Se tranche au test du prompt du train ; levier : `[reasoning] budget_tokens`.
    location: >-
      wavestack.toml:[reasoning]
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Scénario Raisonnement sur le PC cible avec Qwen3.5-2B : le modèle réfléchit 1 536 tokens, toute la réserve de sortie, sans jamais fermer `</think>` ; `output_truncated` sur le canal `reasoning`, bulle vide, 137 s, aucune réponse.

**Approach:** Décision N4. En mode local, un budget de raisonnement (1 024 tokens par défaut) : quand la réflexion l'atteint sans s'être fermée, le harnais arrête la génération, ferme lui-même la réflexion (le `</think>` du gabarit) et relance le modèle sur la suite, avec la réserve restante (512 tokens) pour la réponse. La coupe est tracée et affichée (« raisonnement coupé par le harnais à N tokens ») ; la carte de la brique Raisonnement donne le budget et la réserve.

## Boundaries & Constraints

**Always:** code en anglais, textes en français ; `uv`, `ruff`, `pytest` ; tests verts sous Linux et Windows ; réserve totale inchangée (1 536 tokens avec le raisonnement, donc 2 560 utilisables sur une fenêtre de 4 096) ; la réponse de la relance va dans le canal `text` et le tour se termine normalement ; la fermeture injectée est le texte exact que le gabarit écrit entre réflexion et réponse (`reasoning_wrap` du lot A : `"\n</think>\n\n"` pour Qwen3.5), à défaut la balise fermante des capacités suivie de `"\n\n"` ; le lot A tient : la réponse passée se rend au tour suivant comme elle a été produite, et la relance réutilise le cache du moteur ; le même chemin sert au sous-agent quand il raisonne.

**Never:** mode chat (cloud) : ses fournisseurs gèrent leur propre effort de raisonnement, rien ne change ; couper une réflexion qui s'est fermée seule avant le budget ; changer `MAX_RESERVE` ou `OUTPUT_RESERVE` ; masquer une coupe de la réponse elle-même (au-delà de la réserve restante, `output_truncated` sur `text` comme aujourd'hui).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Réflexion trop longue | Brique active, modèle qui réfléchit au-delà de 1 024 tokens | Génération arrêtée à 1 024 tokens de réflexion ; `reasoning_cut{budget, reasoning_tokens, answer_reserve, message_fr}` ; relance avec la fermeture injectée ; la réponse arrive dans `text` ; tour `completed` ; un seul `model_call_ended` dont la sortie brute contient la fermeture | — |
| Réflexion courte | La réflexion se ferme avant le budget | Comportement actuel, aucun événement de coupe | — |
| Réponse trop longue après la coupe | La relance dépasse les 512 tokens restants | `output_truncated` sur `text`, texte reçu gardé (comportement actuel pour une réponse coupée) | — |
| Arrêt pendant la relance | L'utilisateur arrête | Tour `cancelled` comme aujourd'hui | — |
| Brique éteinte | Pas de raisonnement | Aucun budget, réserve 512 | — |
| Mode chat | Modèle cloud qui raisonne | Inchangé | — |
| Tour suivant | Après une coupe | La réponse passée (réflexion coupée + fermeture + réponse) prolonge le cache : pas de `prefix_not_reused` | — |
| Réglage invalide | `[reasoning] budget_tokens` absent, non entier, trop petit ou ≥ 1 536 | Défaut 1 024 ; borné entre 128 et 1 536 − 128 | — |

</intent-contract>

## Code Map

- `src/wavestack/config.py:92-98` -- `OUTPUT_RESERVE = 512`, `MAX_RESERVE = 1536`, `output_reserve(reasoning)` ; patron `_int` pour une propriété `reasoning_budget_tokens`.
- `wavestack.toml` -- nouvelle section `[reasoning]` commentée en français.
- `src/wavestack/session/app_session.py` :
  - `_reasoning_on(state)` (l.~2540), `_reserve_of` : la réserve choisie par appel.
  - `_call_model` (l.~5812) : un seul `self._engine.complete(rendered.ids, stop, reserve, cancel)` ; `ChannelSplitter(in_reasoning=…)` ; `raw`, `channels`, `take`, `flush`, `end` (`model_call_ended`) ; sortie coupée → `output_truncated{channel}` puis `_ModelOutput("limit")` hors appel d'outil. C'est ici que s'insèrent l'arrêt au budget et la relance.
  - `_engine_cached_ids` (lot A) : ids en cache du moteur, pour construire la relance sans retokeniser la réflexion quand ils prolongent le prompt.
  - `_emit_bricks` (l.~1233 : `always_fr` de la carte Raisonnement), `_always_fr` (l.~2544).
- `src/wavestack/context/render.py` -- `reasoning_wrap(template)` (lot A) : `(avant, milieu)` ; le milieu est la fermeture à injecter.
- `src/wavestack/models/capabilities.py` -- `reasoning_tags`, `ChannelSplitter` (le texte injecté passe par `feed` pour basculer en `text`).
- `src/wavestack/trace/catalog.py` -- `OutputTruncatedPayload` (l.~215), registre (l.~764) : ajouter `ReasoningCutPayload`.
- `src/wavestack/web/static/app.js` -- `output_truncated` (l.505, 688, 2010, 4279, 4420) : modèle pour une étape « Raisonnement coupé » et son résumé ; carte des briques (l.~862-886).
- `content/bricks/reasoning.yaml` -- puce « Coût » (réserve 512 → 1 536).
- `tests/fake_engine.py` -- `outputs` : une sortie par appel ; la sortie compte un token par caractère et s'arrête à `max_tokens` (`length`).
- `tests/test_reasoning.py` -- `RecordingEngine`, `_qwen`, `LONG_REASONING` (l.~385), `test_local_output_cut_in_the_reasoning_is_cut_at_the_reasoning_reserve` (l.388, à remplacer : c'est le défaut corrigé), `test_local_tool_call_cut_names_the_reasoning_reserve` (l.402).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- entrée du 2026-09-27 « le raisonnement épuise la réserve » (lot C), à fermer.

## Tasks & Acceptance

**Execution:**
- `wavestack.toml`, `src/wavestack/config.py` -- `[reasoning] budget_tokens = 1024` commenté ; propriété bornée (128 à `MAX_RESERVE − 128`, défaut sur valeur invalide).
- `src/wavestack/session/app_session.py` -- dans `_call_model`, en mode local, quand l'appel commence en réflexion (ou y entre) et que la réserve dépasse le budget : dès que la réflexion atteint le budget sans s'être fermée, fermer le générateur du moteur, émettre `reasoning_cut`, ajouter la fermeture à la sortie brute et la passer au découpeur, puis relancer `complete` sur les ids de la relance (ids en cache du moteur s'ils prolongent le prompt et correspondent aux octets déjà générés, suivis de la tokenisation de ce qui manque et de la fermeture ; sinon ids du prompt + tokenisation de la sortie brute) avec `reserve − tokens déjà générés` ; compteurs, `first_at`, deltas et `model_call_ended` couvrent les deux générations ; `evaluated_tokens` en est la somme quand le moteur les donne ; la suite (appels d'outils, `output_truncated` sur `text`, annulation) inchangée. Carte Raisonnement : ligne dynamique « Budget de réflexion : N tokens ; au-delà, le harnais ferme la réflexion et garde M tokens pour la réponse. »
- `src/wavestack/trace/catalog.py` -- `ReasoningCutPayload{budget, reasoning_tokens, answer_reserve, message_fr}` enregistré sous `reasoning_cut`.
- `src/wavestack/web/static/app.js` -- étape « Raisonnement coupé » (message) dans Orchestration et résumé du journal ; ligne de budget sur la carte.
- `content/bricks/reasoning.yaml` -- puce « Coût » : la réserve de 1 536 se partage entre la réflexion (au plus le budget) et la réponse.
- `tests/test_reasoning_budget.py` (nouveau) -- une ligne par cas de la matrice avec le faux moteur (réflexion `LONG_REASONING` au premier appel, réponse courte au second) : coupe au budget, ids de la relance terminés par la fermeture, `max_tokens` de la relance = 512, réponse dans le texte, tour `completed`, deltas `text`, pas de coupe quand la réflexion se ferme seule, réponse coupée, arrêt, brique éteinte, mode chat inchangé, tour suivant sans `prefix_not_reused`, réglage invalide.
- `tests/test_reasoning.py` -- remplacer le test qui attend une bulle vide ; adapter les tests de réserve s'il le faut (la réserve reste 1 536).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer l'entrée du lot C (« à vérifier sur PC » : le prompt du train en moins de 120 s).

**Acceptance Criteria:**
- Given le scénario Raisonnement et un modèle qui réfléchit sans fin, when l'utilisateur envoie le prompt du train, then une réponse s'affiche dans la bulle et Orchestration montre « Raisonnement coupé par le harnais à 1 024 tokens ».
- Given la carte de la brique Raisonnement, when elle est affichée, then elle donne le budget et la réserve de la réponse.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 22 findings (constats des quatre couches, doublons regroupés avec leurs sources) — high 0, medium 5, low 12, false 2, maybe-false 3
- findings:
  - `[medium]` `[patch]` Réserve de la relance sans les tokens de la fermeture : prompt + réserve peut dépasser la place d'AD-9 (blind, edge) — `left = len(prompt) + réserve − len(ids de relance)`.
  - `[medium]` `[patch]` Budget appliqué quand la brique est éteinte si le modèle écrit `<think>` quand même (edge) — budget seulement si l'appel raisonne.
  - `[medium]` `[patch]` Repli de la relance (moteur sans cache : llama-server, Ollama) jamais testé (verification-gap, blind) — test `stateful=False`.
  - `[medium]` `[patch]` Branche « reste non en cache » (cas réel de llama.cpp, dernier token absent du cache) jamais exercée (verification-gap) — option du faux moteur et test.
  - `[medium]` `[patch]` Coupe sur un fragment vide (arrêt partiel ou UTF-8 retenus par le moteur) : octets perdus, repli coûteux (blind, edge) — coupe seulement sur un fragment non vide.
  - `[low]` `[patch]` Budget proche de la réserve : réponse réduite à quelques tokens (blind, edge) — `réserve − budget ≥ 128` exigé.
  - `[low]` `[patch]` Reports de coupe qui mangent la place de la réponse (edge) — coupe forcée sous 128 tokens restants.
  - `[low]` `[patch]` `evaluated_tokens` nul pour toute coupe sur un serveur (blind, edge, verification-gap) — somme des valeurs connues.
  - `[low]` `[patch]` `output_truncated` après coupe annonce 1 536 au lieu de la réserve restante (blind) — `max_tokens` = réserve restante.
  - `[low]` `[patch]` Ligne de budget sur la carte sans modèle ou sans balises de raisonnement (blind, edge) — affichée seulement si le modèle raisonne.
  - `[low]` `[patch]` « jusqu'au budget » non défini dans la carte (blind) — valeur, réglage et mode local nommés.
  - `[low]` `[patch]` Garde « jamais dans une balise fermante » non vérifiée (verification-gap) — test.
  - `[low]` `[patch]` Fermeture de repli sans `reasoning_wrap` non testée (verification-gap) — test.
  - `[low]` `[patch]` Erreur pendant la relance et appel d'outil après une coupe non testés (blind) — tests.
  - `[low]` `[defer]` Arrêt au moment exact de la coupe non testé (verification-gap) — course étroite, effet limité à la trace.
  - `[low]` `[defer]` Rendu JS de l'étape « Raisonnement coupé » non testé (verification-gap, intent) — pas de banc JS ; vérification visuelle sur PC.
  - `[low]` `[reject]` La fermeture n'est pas marquée comme écrite par le harnais dans `raw_output` (blind) — l'événement `reasoning_cut` le dit, placé avant la suite dans Orchestration.
  - `[maybe-false]` `[defer]` Critère des 120 s peut-être manqué par construction (≈ 11 tokens/s : 1 024 tokens ≈ 90 s) (blind, intent) — si vrai : medium ; se tranche sur le PC ; levier documenté (`[reasoning] budget_tokens`).
  - `[maybe-false]` `[reject]` Lien avec le faux serveur E2E `[raisonne]` (intent) — ce faux serveur est en mode chat, où la correction ne s'applique pas ; le plan dit « faux moteur » ; si vrai : low.
  - `[maybe-false]` `[reject]` Le cache de llama-server garde-t-il un flux interrompu ? (intent) — sans effet sur la justesse : la relance est un prompt complet ; si vrai : low (relecture).
  - `[false]` `[reject]` Le sous-agent n'a jamais de budget avec le réglage par défaut (blind) — un sous-agent qui raisonne a la réserve de 1 536 (`_reserve_of`) ; sans raisonnement, rien à couper.
  - `[false]` `[reject]` Spec absente du diff (blind) — la spec est le fichier de revue, hors du diff par construction.

## Design Notes

- Même principe que le `thinking_budget` de Qwen3 dans vLLM/SGLang et le « budget forcing » : on force la fin de la réflexion au lieu de perdre toute la sortie. La fermeture exacte du gabarit garde l'ajout seul (AD-4) : le tour suivant et la relance réutilisent le cache.
- Relancer sur les ids en cache évite qu'une retokenisation différente de la réflexion ne force une relecture complète sur un modèle hybride.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert
- `node --check src/wavestack/web/static/app.js` -- expected: pas d'erreur

## Auto Run Result

Status: done

**Résumé.** En mode local, quand l'appel raisonne, un budget de réflexion (`[reasoning] budget_tokens`, 1 024 par défaut, borné pour laisser au moins 128 tokens à la réponse) : dès que la réflexion l'atteint sans se fermer (jamais au milieu d'une balise, ni sur un fragment retenu par le moteur, ni juste après un blanc, sauf si la place de la réponse est en jeu), le harnais arrête la génération, émet `reasoning_cut`, ajoute la fermeture exacte du gabarit (`reasoning_wrap`, sinon `</think>` + ligne vide) et relance le modèle sur les ids en cache du moteur (sinon prompt + sortie retokenisée) avec la place restante de la réserve de 1 536. Un seul `model_call_ended` couvre les deux générations. Orchestration montre « Raisonnement coupé par le harnais à N tokens » ; la carte Raisonnement donne le budget et la réserve de la réponse. Mode chat inchangé.

**Fichiers.** `wavestack.toml`, `src/wavestack/config.py` (budget), `src/wavestack/session/app_session.py` (`_call_model`, `_reasoning_closure`, `_relaunch_ids`, carte), `src/wavestack/models/capabilities.py` (`ChannelSplitter.holding`), `src/wavestack/trace/catalog.py` (`reasoning_cut`), `src/wavestack/web/static/app.js`, `content/bricks/reasoning.yaml`, `tests/fake_engine.py` (`cache_lags`), `tests/test_reasoning_budget.py` (nouveau), `tests/test_reasoning.py`, `deferred-work.md` (entrée fermée).

**Revue.** 14 patchs (5 medium, 9 low), 3 différés (arrêt au moment de la coupe, rendu JS, critère des 120 s : medium si vrai), 5 rejetés. `followup_review_recommended: false` : aucun high ; les medium sont des calculs de réserve et des chemins de relance, désormais testés.

**Vérification.** `ruff check`, `ruff format --check`, `node --check app.js` : OK ; `pytest -q` : 854 réussis, 4 sautés.

**Risques résiduels (à vérifier sur PC).** Prompt du train en moins de 120 s (≈ 90 s de réflexion à 11 tokens/s : baisser le budget si besoin) ; relance sur les ids en cache de llama-cpp-python sans relecture ; tour suivant sans `prefix_not_reused`.
