---
title: 'Raisonnement'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_revision: '81dba76e0b239a7c18d6ff0628b0223299434492'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      Le front de la story 13 (option « Afficher le raisonnement », reasoning-block de la Vue humain et de Contexte LLM, carte « toujours active ») n'a aucun test automatique.
    evidence: |-
      Même écart que pour les stories 5b à 11b : aucun banc de test JS ; retirer le bloc de Contexte LLM ou ignorer l'option passerait pytest et `node --check`. Le harnais E2E (tools/e2e/, faux serveur OpenAI + Playwright) en cours de création pourra le couvrir.
    location: >-
      src/wavestack/web/static/app.js (renderChat, renderContext, renderBricks)
    severity: medium
  - summary: >-
      Non vérifié : un fournisseur au format `field` accepte-t-il le raisonnement renvoyé dans le champ `reasoning` du message assistant (`resend = true`) ?
    evidence: |-
      Aucun préréglage ne déclare `resend = true` ; la forme est tirée d'AD-4 (« dans la forme reçue ») et du champ lu par l'adaptateur. À trancher par un tour réel avec `resend = true` déclaré dans settings.json : si le fournisseur refuse (400), renvoyer sous le nom de champ reçu.
    location: >-
      src/wavestack/session/app_session.py (_assistant_message)
    severity: medium
---

<intent-contract>

## Intent

**Problem:** Rien ne montre en salle ce que change le mode raisonnement d'un modèle : le gabarit local le coupe toujours (`enable_thinking=False`), un modèle cloud reçoit toujours ses paramètres « éteint », et aucune brique ne permet de l'activer ni de dire pourquoi c'est impossible (CAP-10, FR-9).

**Approach:** Une brique `reasoning` au contrat d'AD-12, disponible selon la capacité raisonnement du modèle actif (AD-6). Active, elle allume la variable de raisonnement du gabarit en local, ou écrit `reasoning.on` dans le corps en cloud, et porte la réserve de sortie à 1 536 tokens (aperçu et jauge recalculés, AD-9). Le raisonnement reste toujours visible dans Contexte LLM ; l'option « Afficher le raisonnement » de la Vue humain le montre ou le masque. Un scénario de la brique rejoint le programme.

## Boundaries & Constraints

**Always:**
- Brique `reasoning` : catégorie `prompt` (« prompt engineering »), un composant `reasoning.mode` (`local_process`, arête vers `core.harness`, dessiné en puce du cadre Harnais), explication en français dans `content/bricks/reasoning.yaml` (AD-19). Aucune dépendance à une autre brique.
- Disponibilité calculée au seul point d'AD-12 (`_availability`), depuis une capacité `reasoning` de `Capabilities` : en local, vraie si le registre connaît la variable de raisonnement du gabarit ; en cloud, vraie si l'entrée déclare `reasoning`. Sinon, raison « Indisponible : le modèle actif ne sait pas raisonner. » suivie de la cause (gabarit sans variable de raisonnement, ou modèle cloud sans `reasoning` déclaré). `wanted` n'est jamais modifié par un changement de modèle.
- Raisonnement actif pour un tour = `reasoning` dans `TurnState.effective`, ou entrée cloud à `reasoning.always`. Il fixe tout pour le tour et pour l'aperçu : réserve 1 536 (sinon 512), `usable`, `max_tokens` envoyé (local et cloud), `max_tokens` d'`output_truncated` et message de sortie coupée.
- Local : la variable de raisonnement du registre (`enable_thinking`) vaut `True` si le raisonnement est actif, `False` sinon. Le séparateur incrémental et le canal `reasoning` de `model_delta` existent (story 3) : aucun nouveau séparateur ni canal.
- Cloud : `context` écrit `reasoning.on` si le raisonnement est actif, sinon `reasoning.off` (AD-4, AD-6). Entrée `always` : la carte porte `always_fr` (« Toujours active pour ce modèle », avec la raison), interrupteur coché et désactivé, réserve 1 536 même brique éteinte. « Tester » du diagnostic garde le corps « brique éteinte ».
- `reasoning.resend` (AD-4) : faux → le raisonnement ne part jamais au fournisseur ; vrai → il repart dans la forme du format déclaré (`field` : champ `reasoning` du message assistant ; `content_blocks` : bloc `thinking` avant le bloc `text` ; `think_tags` : `<think>…</think>` avant le texte), compté en `assistant_turn` dans le tour et `history` ensuite. Préréglages inchangés.
- Le raisonnement rendu par un gabarit local (sorties du tour, historique) est un segment `assistant_turn` ou `history`, jamais `template`.
- Un `<tool_call>` écrit dans le raisonnement n'est jamais exécuté ni signalé mal formé.
- Front (AD-1, AD-18) : option « Afficher le raisonnement » dans l'en-tête de la Vue humain, préférence du navigateur mémorisée (cochée par défaut) ; `reasoning-block` (DESIGN.md) replié par défaut, dépliable, état de dépliage conservé entre deux rafraîchissements ; dans Contexte LLM, bloc « Raisonnement du modèle » toujours présent quand l'appel affiché en a un, quelle que soit l'option.
- Scénario `reasoning` au schéma de la story 10 (AD-19), dans un module « Raisonnement » de 30 min ajouté en fin de programme : briques `short_memory`, `system_prompt`, `reasoning`, un prompt qui demande un calcul en plusieurs étapes.

**Never:** nouveau `kind` d'événement, nouveau type de segment ou nouveau canal ; recalcul côté front ; toucher aux préréglages cloud ; changement de modèle à chaud ; réglage de l'effort de raisonnement dans l'interface ; nouvelle dépendance ; test réseau réel.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Local, brique active | gabarit avec `enable_thinking`, brique voulue | rendu avec `enable_thinking=True` ; `context_rendered.reserve` = 1 536 ; moteur appelé avec `max_tokens` 1 536 ; deltas `reasoning` puis `text` ; `model_call_ended.reasoning` rempli | — |
| Local, brique éteinte | même modèle | `enable_thinking=False`, réserve 512 | — |
| Local sans capacité | gabarit sans variable de raisonnement, brique voulue | carte `available = false`, raison « Indisponible : le modèle actif ne sait pas raisonner. … » ; tour rendu comme brique éteinte (réserve 512) | aucun plantage |
| Aperçu | bascule de la brique hors tour | `context_preview` réémis avec `reserve` et `usable` recalculés | — |
| Cloud déclaré | Mistral (`on` / `off`), brique active puis éteinte | corps `reasoning_effort: high` et `max_tokens` 1 536, puis `none` et 512 | — |
| Cloud `always` | Groq, brique éteinte | carte avec `always_fr`, corps avec `reasoning_effort: low`, `max_tokens` 1 536, réserve 1 536 | — |
| Cloud sans `reasoning` | entrée déclarée sans raisonnement | brique indisponible avec la raison ; corps sans paramètre de raisonnement | — |
| Renvoi | entrée `resend = true`, tour avec outil puis tour suivant | raisonnement dans le 2ᵉ corps (forme du format), segment `assistant_turn`, puis `history` au tour suivant | `resend = false` : absent du corps |
| Raisonnement du tour en local | 2ᵉ appel d'un tour après un outil, gabarit qui garde le raisonnement | texte du raisonnement dans un segment `assistant_turn` | — |
| Appel d'outil dans le raisonnement | sortie locale `<think><tool_call>…</tool_call></think>Réponse` | aucun outil exécuté, aucun appel mal formé, tour `completed` | — |
| Scénario | lancer `reasoning` | briques voulues = `short_memory`, `system_prompt`, `reasoning` ; programme à 12 scénarios | — |

</intent-contract>

## Code Map

- `src/wavestack/models/capabilities.py:17-65` -- `Capabilities` : ajouter `reasoning: bool` (vrai si `reasoning_variable`) et `reasoning_always: bool = False` ; `capabilities_for` les remplit. `ChannelSplitter` (72-131) : réutilisé tel quel.
- `src/wavestack/bricks/registry.py:34` -- `BRICKS` : déclarer `reasoning` (capacité exigée `reasoning`), après `system_prompt`.
- `content/bricks/reasoning.yaml` (nouveau) -- libellé, catégorie, hébergement, explication (ce qu'ajoute le raisonnement, son coût en tokens et en temps, la réserve de 1 536).
- `src/wavestack/config.py:64-136` -- `CloudModel.reserve` et `reasoning_params` deviennent fonction du raisonnement actif (`always` force l'actif) ; `MAX_RESERVE` = 1 536 (déjà là) ; `context/window.py:9` `OUTPUT_RESERVE` = 512.
- `src/wavestack/cloud.py:83-90` -- `chat_fields(entry, max_tokens, reasoning=False)`. `session/diagnostic.py:682` : appel « brique éteinte ».
- `src/wavestack/session/app_session.py` :
  - `_CAPABILITIES_FR` 164, `_availability` 1031-1053 : raison propre au raisonnement (local / cloud).
  - `_emit_bricks` 732-782 : `always_fr` sur la carte `reasoning` d'une entrée `always`.
  - `_boot` 845-851 / `_boot_cloud` 911-924 : capacités cloud `reasoning`, `reasoning_always` ; `self._reserve` retiré au profit d'une réserve par `TurnState` (`_reasoning_on(state)`).
  - `_render` 1300-1334 (variable du gabarit, réserve), `_render_chat` 1336-1359 et `_chat_gauge` 1361-1374 (réserve passée), `_emit_preview` 1376.
  - `_step_messages` 1110-1181 et `_messages` 1217-1254 : raisonnement enveloppé en `Part` (`assistant_turn` / `history`) en local ; en chat, seulement si `resend`, dans la forme du format.
  - `_turn` 2092-2239 : passe la réserve à `_call_model`. `_call_model` 2661-2787 : `max_tokens` = réserve du tour (2732, 2772, 2784) ; analyse des appels sur la sortie hors raisonnement. `_call_model_chat` 2789-2855 : réserve du tour (2817, 2845, 2853).
- `src/wavestack/context/render.py:258-270` -- `_attribute` : un `content` fait de blocs (liste de `dict`) est préparé comme toute autre valeur, pour les blocs `thinking` renvoyés.
- `src/wavestack/trace/catalog.py:256-273` -- `BrickState.always_fr: str | None = None`.
- `content/scenarios.yaml` -- module « Raisonnement » et scénario `reasoning`.
- `src/wavestack/web/static/index.html:70-75`, `app.js` (store 195-265, `renderBricks` 523-545, `renderChat` 1159-1164, `renderContext` 1426-1461), `app.css` (bulles 496-530) -- option, `reasoning-block`, bloc de Contexte LLM, carte `always_fr`.
- Tests : `tests/fake_engine.py` (`FakeEngine(template=…)`, `booted_session`), `tests/test_turn.py:249-275` (capacités, départ en raisonnement), `tests/test_cloud.py:62-104` (`Provider`, `_cloud_session`, flux SSE), `tests/test_scenarios.py:30-45` (compte de scénarios), `tests/fixtures/qwen3_5_chat_template.jinja:90-153` (gabarit qui garde le raisonnement du tour).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/models/capabilities.py` -- capacités `reasoning`, `reasoning_always`.
- [x] `src/wavestack/bricks/registry.py`, `content/bricks/reasoning.yaml` -- déclaration et contenu de la brique.
- [x] `src/wavestack/config.py`, `src/wavestack/cloud.py` -- paramètres et réserve selon le raisonnement actif. `src/wavestack/session/diagnostic.py` n'a pas eu à changer : `chat_fields(entry, entry.reserve)` garde le corps « brique éteinte » par la valeur par défaut `reasoning=False`.
- [x] `src/wavestack/context/render.py` -- contenu en blocs.
- [x] `src/wavestack/trace/catalog.py` -- `always_fr`.
- [x] `src/wavestack/session/app_session.py` -- disponibilité, réserve par tour, variable du gabarit, corps cloud, renvoi, attribution, appels d'outils hors raisonnement.
- [x] `content/scenarios.yaml` -- module et scénario.
- [x] `src/wavestack/web/static/index.html`, `app.js`, `app.css` -- option, blocs, carte.
- [x] `tests/test_reasoning.py` (nouveau), `tests/test_scenarios.py`, tests existants touchés par les signatures -- une ligne de la matrice au moins par test.

**Acceptance Criteria:**
- Given l'option « Afficher le raisonnement » décochée, when un tour produit du raisonnement, then la Vue humain ne montre que le texte, Contexte LLM montre le bloc « Raisonnement du modèle », et le choix survit au rechargement de la page.
- Given une carte `reasoning` d'un modèle `always`, when le panneau s'affiche, then l'interrupteur est coché et désactivé avec « Toujours active pour ce modèle » et sa raison.
- Given la brique voulue puis un modèle sans capacité, when le panneau s'affiche, then la carte est indisponible avec sa raison et redevient effective sans nouveau clic avec un modèle qui raisonne.

## Spec Change Log

### 2026-09-26 — Revue indépendante (hors boucle de l'auto-run)

- **Déclencheur :** point 10 du triage de la revue indépendante (scénario non cumulatif, contraire à l'en-tête de `content/scenarios.yaml`).
- **Amendement :** le scénario `reasoning` déclare `short_memory, system_prompt, tools, mcp, skills, hooks, reasoning` et `mcp_lazy: true`. La ligne « Always » et la ligne « Scénario » de la matrice, dans `<intent-contract>`, sont laissées telles quelles (contrat en lecture seule) : cette entrée les remplace.
- **État évité :** un module qui démarre sans les briques des modules précédents (CAP-40).
- **KEEP :** le module « Raisonnement » de 30 min en fin de programme et le prompt du train.

## Review Triage Log

### 2026-09-26 — Review pass

Revue faite dans la même session que l'implémentation (aucun outil de sous-agent disponible) : les quatre lentilles (aveugle, cas limites, écart de vérification, alignement sur l'intention) ont été appliquées successivement au diff, sans relecteur indépendant.

- verdicts: 11 findings — high 0, medium 2, low 6, false 1, maybe-false 2
- findings:
  - `[low]` `[patch]` Contexte LLM : pendant le 2ᵉ appel d'un tour, le bloc « Raisonnement du modèle » montrait le raisonnement de l'appel 1 sous le contexte de l'appel 2 (`turn.callEnded` reste celui de l'appel précédent) — corrigé : `lastCall(turn).ended`, sinon les deltas en direct.
  - `[medium]` `[patch]` Forme `think_tags` du renvoi (`resend`) sans test — ajouté : test paramétré sur les trois formats (`content_blocks`, `field`, `think_tags`).
  - `[medium]` `[defer]` Front (option, `reasoning-block`, carte « toujours active ») sans test automatique — même écart que les stories 5b à 11b, aucun banc JS ; reporté au harnais E2E.
  - `[maybe-false]` `[defer]` Renvoi au format `field` sous la clé `reasoning` : accepté par le fournisseur ? — à trancher par un tour réel avec `resend = true` ; medium si refusé.
  - `[maybe-false]` `[reject]` Latence si le 2ᵉ appel ne prolonge pas le 1ᵉʳ avec le raisonnement re-rendu par le gabarit Qwen — sonde sur le gabarit Qwen3.5 de référence : aucun `prefix_not_reused` ; si le vrai modèle écrit son raisonnement autrement, l'événement l'explique déjà (low).
  - `[false]` `[reject]` « Le raisonnement du tour est compté `template` » — réfuté par `test_the_turn_reasoning_is_attributed_to_the_model_output` (segment `assistant_turn`, rien dans `template`).
  - `[low]` `[reject]` Un `</think>` écrit dans les arguments d'un appel d'outil tronquerait l'appel analysé (`_outside_reasoning` coupe au dernier `</think>`) — cas improbable, correctif = analyse plus complexe.
  - `[low]` `[reject]` Carte `reasoning` d'un modèle `always` : « Prend effet au prochain tour » possible si un scénario change `wanted` — cosmétique, sans effet sur le tour.
  - `[low]` `[reject]` Raison « gabarit sans variable » affichée quand aucun modèle n'est chargé (serveur seul) — l'envoi est de toute façon indisponible avec sa propre raison.
  - `[low]` `[reject]` `store.openReasoning` jamais purgé — quelques clés par tour, négligeable.
  - `[low]` `[reject]` `flex-wrap` sur `.pane-actions` touche tous les volets — voulu : un en-tête trop étroit passe à la ligne au lieu de déborder.

### 2026-09-26 — Revue indépendante

Quatre relecteurs indépendants lancés par le coordinateur (aveugle, cas limites, lacunes de vérification, alignement d'intention) sur le diff `81dba76..7337a1b`. Triage du coordinateur : 19 points « À corriger », 4 « Reporté ». Tous les points « À corriger » ont été vérifiés dans le code et appliqués ; aucun n'a été écarté.

- verdicts: 23 findings — 19 à corriger (patch), 4 reportés (defer), 0 écarté
- findings:
  - `[patch]` 1. Troncature brique active : tests local (raisonnement coupé : `output_truncated` à 1 536, `engine.max_tokens == [1536]`, tour `limit`) et local/chat (appel d'outil coupé : détail « 1 536 tokens »).
  - `[patch]` 2. `<think>` jamais refermé contenant un `<tool_call>` : test, ni `tool_started` ni `tool_call_malformed`.
  - `[patch]` 3. Ordre au renvoi sur le message passé (`_bodies(provider)[2]`) : `thinking` avant `text`, `<think>…</think>` en tête ; ajouté au test paramétré.
  - `[patch]` 4. `_outside_reasoning` (coupe au dernier `</think>`) supprimé : le séparateur d'AD-6 (`ChannelSplitter`) tient désormais `outside`, la sortie sans le raisonnement ni ses balises, balises d'appel d'outil gardées ; aucun second séparateur. Tests : appel valide suivi d'un `<think>` non refermé, puis d'un `</think>` littéral.
  - `[patch]` 5. Pas mal formé local : `content` = sortie hors raisonnement (`_ModelOutput.answer`), raisonnement passé à part ; test (raisonnement en `assistant_turn`, aucun `</think>` dans les segments, raisonnement rendu une fois).
  - `[patch]` 6. `content_blocks` : plus de bloc `text` vide ; test d'une réponse passée de raisonnement seul.
  - `[patch]` 7. Sans modèle chargé : « Indisponible : aucun modèle chargé. » ; test.
  - `[patch]` 8. Modèle `always` : composant `reasoning.mode` dessiné sans toucher à `wanted`, icône 💭 dans `BRICK_ICONS` ; test sur `architecture_changed`.
  - `[patch]` 9. `always_fr` attribué au modèle (« … ; ce modèle ne permet pas de l'éteindre ») ; test (fournisseur absent du texte).
  - `[patch]` 10. Scénario cumulatif (voir Spec Change Log) ; test des briques voulues, du lazy loading et de la réserve de l'aperçu.
  - `[patch]` 11. Option décochée : « Le modèle raisonne… » avec chronomètre pendant le raisonnement (front).
  - `[patch]` 12. Sortie coupée dans le raisonnement : message dédié (front).
  - `[patch]` 13. Tour à plusieurs appels : un bloc de raisonnement par appel dans la Vue humain (`pastReasoning`, front).
  - `[patch]` 14. Règle unique de la réserve : `config.output_reserve(reasoning)`, utilisée par `CloudModel.reserve_for` et `AppSession._reserve_of` ; `OUTPUT_RESERVE` déplacé de `context/window.py` vers `config` (plus de 512 en dur).
  - `[patch]` 15. `think_tags` renvoyé dans la forme reçue : `Joined` sans séparateur (`<think>…</think>Il est 9 h.`), testé.
  - `[patch]` 16. Fenêtre ≤ 1 536 : brique indisponible avec une raison qui cite la réserve (même logique que le garde `tpm // 2`) ; test.
  - `[patch]` 17. `aria-describedby` de l'interrupteur verrouillé vers le paragraphe `brick-always`, règle CSS dédiée (violet du harnais).
  - `[patch]` 18. Fichier de story : `severity` standard, ligne de `diagnostic.py` corrigée, revue indépendante consignée ici.
  - `[patch]` 19. Écart H6 (Mistral `resend = false` contre AD-20) consigné dans `deferred-work.md`.
  - `[defer]` Critère d'acceptation 3 : test à écrire avec la story 17.
  - `[defer]` `_resend()` lu en direct et renvoi brique éteinte : comportement non spécifié.
  - `[defer]` Contexte LLM : raisonnement du dernier appel seulement.
  - `[defer]` Front sans banc de test JS : déjà consigné au premier passage, non dupliqué.

Remarque sur le test du scénario : l'aperçu du scénario `reasoning` déborde avec `FakeEngine` (un token par octet), comme celui du scénario `skills` déjà livré ; le test vérifie donc la réserve, et le fait que le contexte tienne relève du test `model` d'AD-9 avec le vrai tokenizer (à confirmer sur le PC cible).

## Design Notes

Réserve et paramètres découlent du `TurnState` figé (AD-17), pas d'un attribut de session : une bascule en plein tour ne change rien avant le tour suivant, et l'aperçu (rendu sur `build_turn_state()`) suit la configuration courante sans code à part.

```python
def _reasoning_on(self, state: TurnState) -> bool:
    always = self._cloud is not None and self._caps.reasoning_always
    return always or "reasoning" in state.effective
```

Renvoi en `content_blocks` : `content` du message assistant = `[{"type": "thinking", "thinking": [{"type": "text", "text": Part(...)}]}, {"type": "text", "text": Part(...)}]` ; `_attribute` doit donc accepter un `content` qui n'est pas une liste de `Part`.

## Hypothèses à valider

- H1 — « Afficher le raisonnement » est une préférence d'interface (AD-18), mémorisée par le navigateur et cochée par défaut, comme le comportement actuel qui montre déjà le raisonnement reçu.
- H2 — Catégorie « prompt engineering » : la brique change ce que le harnais écrit (variable du gabarit, paramètre du corps).
- H3 — Le scénario ouvre un module « Raisonnement » de 30 min en fin de programme. Revu après la revue indépendante (point 10) : il suit la convention cumulative de `content/scenarios.yaml` (briques des modules précédents actives, MCP en lazy loading pour garder de la place) ; la place définitive des modules du palier 2 reste à la story 21.
- H4 — Brique voulue mais indisponible : dessinée en style indisponible (règle d'AD-12, comme les outils), malgré « Absente du schéma » d'EXPERIENCE.md.
- H5 — En local, seule la variable de raisonnement du gabarit rend la brique disponible ; un gabarit à balises `<think>` sans variable reste indisponible, mais son raisonnement reçu est séparé et affiché.
- H6 — Forme du renvoi par format (`field` → champ `reasoning`) ; le préréglage Mistral reste `resend = false` (AD-20 « vrai pour Mistral » non appliqué sans test réel).

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun écart
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tous les tests passent
- `node --check src/wavestack/web/static/app.js` -- expected: syntaxe valide (si `node` est présent)

**Manual checks (if no CLI):**
- Sur le PC cible avec Qwen3.5 : brique active, un tour montre le raisonnement replié dans la Vue humain et dans Contexte LLM, jauge avec réserve 1 536 ; option décochée, la bulle n'a plus que le texte.

## Auto Run Result

Status: done

**Écart au workflow :** l'agent n'avait aucun outil de sous-agent. Planification, implémentation et revue ont été faites dans la même session ; la revue n'est donc pas indépendante (voir le triage). Une passe de revue indépendante reste souhaitable.

**Résumé :** brique `reasoning` (catégorie prompt, composant `reasoning.mode`), disponible selon la capacité `reasoning` du modèle actif (variable `enable_thinking` du gabarit en local, déclaration `reasoning` en cloud), raison « Indisponible : le modèle actif ne sait pas raisonner. » sinon ; carte « Toujours active pour ce modèle » pour une entrée `always`. Réserve de sortie tirée du `TurnState` (1 536 raisonnement actif, 512 sinon), appliquée à la jauge, à l'aperçu, au `max_tokens` local et cloud et aux messages de sortie coupée. Variable du gabarit à `True` quand la brique est effective ; `reasoning.on`/`off` dans le corps cloud ; renvoi `resend` dans la forme du format ; raisonnement rendu attribué (`assistant_turn` / `history`) ; appels d'outils analysés hors du raisonnement. Front : option « Afficher le raisonnement » (mémorisée, cochée par défaut), `reasoning-block` replié dans la Vue humain et bloc « Raisonnement du modèle » toujours présent dans Contexte LLM. Scénario `reasoning` dans un module « Raisonnement » (30 min).

**Fichiers :**
- `src/wavestack/models/capabilities.py` — capacités `reasoning`, `reasoning_always`.
- `src/wavestack/bricks/registry.py`, `content/bricks/reasoning.yaml` — déclaration et explication de la brique.
- `src/wavestack/config.py`, `src/wavestack/cloud.py` — réserve et paramètres de raisonnement selon le raisonnement actif.
- `src/wavestack/context/render.py` — `content` en blocs accepté (bloc `thinking` renvoyé).
- `src/wavestack/trace/catalog.py` — `BrickState.always_fr`.
- `src/wavestack/session/app_session.py` — disponibilité, réserve par tour, variable du gabarit, corps cloud, renvoi, attribution, appels hors raisonnement.
- `content/scenarios.yaml` — module et scénario « Raisonnement ».
- `src/wavestack/web/static/index.html`, `app.js`, `app.css` — option, blocs de raisonnement, carte « toujours active ».
- `tests/test_reasoning.py` (nouveau, 13 tests), `tests/test_bricks.py`, `tests/test_scenarios.py` — matrice et comptes mis à jour.

**Revue :** 2 correctifs appliqués (1 medium, 1 low), 2 éléments reportés (`deferred`), 7 rejetés avec leur raison (triage ci-dessus). Recommandation de passe de suivi : `false` selon la règle (aucun high, un seul medium corrigé) ; la revue non indépendante reste un risque résiduel.

**Vérification :** `uv run ruff check .` (vert), `uv run ruff format --check .` (vert), `node --check src/wavestack/web/static/app.js` (vert), `uv run pytest -q` : 396 réussis, 3 sautés. Audit de la matrice : chaque ligne couverte par un test de `tests/test_reasoning.py` ou `tests/test_scenarios.py` ; contrôle par mutation de cinq chemins (analyse hors raisonnement, variable du gabarit, attribution, `always`, raison d'indisponibilité) : chaque mutation fait échouer au moins un test.

**Risques résiduels :** front non testé automatiquement ; comportement réel de Qwen3.5 avec `enable_thinking=True` (longueur du raisonnement face à la réserve de 1 536 et à NFR-1 sur CPU) ; renvoi `resend` jamais essayé contre un fournisseur réel.

### Correctifs de la revue indépendante (2026-09-26)

Les 19 points « À corriger » ont été appliqués (détail dans le Review Triage Log), avec 12 tests Python de plus dans `tests/test_reasoning.py` (25 au total) ; le front (points 11, 12, 13, 17) n'a pas de banc de test JS. Vérification : `uv run ruff check .`, `uv run ruff format --check .`, `node --check src/wavestack/web/static/app.js` verts ; `uv run pytest -q` : 408 réussis, 3 sautés. `followup_review_recommended` reste `false` : la revue indépendante a eu lieu, et chaque correctif testable côté Python a son test.

