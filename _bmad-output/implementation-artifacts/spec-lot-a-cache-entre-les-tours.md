---
title: 'Lot A : réutiliser le cache du moteur entre les tours'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '373d30ab58932913f9fa3b08c8a75e83d399656b'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/CLAUDE.md'
warnings: ['multiple-goals', 'oversized']
deferred:
  - summary: >-
      La copie de l'état du moteur avant un sous-agent n'est ni bornée ni comptée dans le budget mémoire (AD-8).
    evidence: |-
      Non vérifié : la taille réelle sur Qwen3.5-2B est inconnue ici (tiny-llama : quelques Ko). Se tranche en lisant `state_saved_bytes` de `subagent_ended` sur le PC cible.
    location: >-
      src/wavestack/session/app_session.py:_save_main_state
    severity: medium (unverified)
  - summary: >-
      Avec le raisonnement actif, les blancs réels autour de `</think>` peuvent différer de ceux du gabarit : la réponse passée reconstruite ne prolongerait plus le cache.
    evidence: |-
      Non vérifié sans vrai GGUF. Se tranche sur le PC cible : deux tours avec la brique raisonnement, aucun `prefix_not_reused` attendu (sinon cause `history`).
    location: >-
      src/wavestack/session/app_session.py:_as_produced
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Avec le moteur intégré (llama-cpp-python) et Qwen3.5, modèle hybride dont llama.cpp ne sait pas tronquer l'état, toute divergence entre le prompt d'un tour et ce que le moteur a en cache force une relecture complète : 20 s à 729 tokens, 111 à 119 s vers 3 200 (NFR-1). Trois causes vérifiées sur le PC cible : (1) le gabarit retire `<think>\n\n</think>\n\n` des réponses passées alors que ces tokens sont en cache ; (2) une écriture en mémoire globale réécrit le message système dès le tour suivant ; (3) le sous-agent occupe le même contexte llama.cpp et, au retour, le contexte principal est relu. Le contrôle `prefix_not_reused` ne regarde que l'intérieur d'un tour et n'a rien signalé.

**Approach:** En mode local (gabarit rendu par le harnais), rendre l'historique exactement comme il a été produit (A1) ; figer la mémoire globale par conversation (A2, décision N1) ; contrôler aussi le premier appel de chaque tour contre les ids en cache du moteur et nommer la cause de la relecture (A3) ; sauvegarder et restaurer l'état du moteur autour d'une délégation (A4, décision N2) ; tests sans GGUF et test `model` qui relève côté moteur le nombre de tokens réellement évalués (A5).

## Boundaries & Constraints

**Always:** code et identifiants en anglais, textes d'interface en français ; `uv`, `ruff`, `pytest` ; tests verts sous Linux et Windows ; le prompt envoyé reste le rendu du vrai gabarit du modèle (AD-4 : jamais de gabarit réécrit ni de texte collé hors gabarit) ; la jauge et « Contexte LLM » restent exactes (somme des segments = total) ; le mode chat (cloud) est inchangé ; un moteur qui ne sait pas donner son cache ou son état (llama-server, Ollama) continue de marcher, avec un repli honnête (relecture signalée) ; les nouveaux champs d'événements sont optionnels et déclarés dans `trace/catalog.py`.

**Never:** changer le moteur par défaut (décision N6 ouverte) ; garder les extraits RAG dans l'historique (choix explicite de la story 15, « Extraits hors de l'historique ») ; toucher au talon des documentations chargées ou à la compression ; ajouter une dépendance ; exiger un vrai GGUF pour la suite par défaut.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Deux tours sans raisonnement | Gabarit Qwen3.5 (fixture), `native_tools`, t1 avec un appel d'outil puis une réponse, t2 | Le texte envoyé au 1er appel de t2 commence par le prompt du dernier appel de t1 suivi de sa sortie ; aucun `prefix_not_reused` | — |
| Deux tours avec raisonnement | Brique raisonnement active, sortie `réflexion\n</think>\n\nréponse` | Au tour suivant, la réponse passée est rendue `<think>\nréflexion\n</think>\n\nréponse` ; aucun `prefix_not_reused` ; la réflexion passée est comptée en `history` | — |
| Gabarit sans bloc de raisonnement | Gabarit qui garde les réponses passées telles quelles (ex. tiny-llama, Llama 3.2) | Rendu inchangé par rapport à aujourd'hui | — |
| Écriture en mémoire | `remember` au tour 1 | Tour 2 : message système identique au tour 1 ; l'entrée est dans le tiroir ; après « Vider la conversation » ou un changement de scénario, elle entre dans le message système | — |
| Rejeu | Rejeu du dernier tour après une écriture en mémoire | Le rejeu utilise l'instantané mémoire de sa conversation | — |
| Divergence entre les tours | Prompt système modifié entre t1 et t2 | `prefix_not_reused` au 1er appel de t2, `cause: "system"`, texte qui nomme la cause et le nombre de tokens à relire | — |
| Autres divergences | Conversation vidée, rejeu, tour précédent annulé ou en erreur, historique réécrit (talon, extraits RAG retirés) | `prefix_not_reused` avec `cause` `reset`, `replay`, `abandoned` ou `history` | — |
| Délégation, moteur avec état | Moteur qui sait sauvegarder et restaurer (llama-cpp-python, faux moteur) | État sauvegardé avant le sous-agent, restauré après ; 1er appel principal après la délégation sans `prefix_not_reused` ; taille de la copie tracée | Échec de sauvegarde ou de restauration : tour poursuivi, relecture signalée (`cause: "subagent"`), pas d'erreur fatale |
| Délégation, moteur sans état | llama-server, Ollama | Pas de sauvegarde ; au retour, `prefix_not_reused` `cause: "subagent"` | — |

</intent-contract>

## Code Map

- `src/wavestack/models/engine.py` -- port `Engine` (Protocol, l.62) et `LlamaCppEngine` (l.179, `complete` appelle `self._llm.generate`, l.204). Vérifié avec `tests/fixtures/tiny-llama.gguf` : `Llama.generate` ne réévalue que les tokens qui prolongent `llm.input_ids` (ids en cache, le dernier token échantillonné n'y est pas) ; `llama_cpp.llama_perf_context_reset(llm.ctx)` puis `llama_cpp.llama_perf_context(llm.ctx).n_p_eval` donnent le nombre de tokens de prompt évalués ; `llm.save_state()` (`LlamaState`, `.llama_state_size`) et `llm.load_state(state)` restaurent aussi `input_ids`.
- `src/wavestack/models/servers.py` -- `LlamaServerEngine` (l.249), `OllamaRawEngine` (l.379) : moteurs à prompt rendu sans accès au cache ni à l'état.
- `src/wavestack/context/render.py` -- `render_template` (l.93), `_neutralize` (l.131 : retire les blancs extérieurs et casse les jetons spéciaux de chaque `Part`, dont `<think>` s'il est déclaré spécial), `_attribute` (l.222), `render_context` (l.321).
- `src/wavestack/context/segments.py` -- `Part`, `Joined`, `SegmentKind.TEMPLATE`.
- `tests/fixtures/qwen3_5_chat_template.jinja` -- l.89-104 : un message assistant d'avant la dernière question est rendu `'<|im_start|>assistant\n' + content` (pas de bloc de raisonnement) ; au-delà, `'<think>\n' + reasoning|trim + '\n</think>\n\n' + content` ; si `reasoning_content` n'est pas une chaîne et que `content` contient `</think>`, le contenu est coupé. Invite de génération l.148-155.
- `src/wavestack/session/app_session.py` :
  - `Exchange` (l.258 : `text`, `reasoning`, `steps`), `TurnState` (l.330), `build_turn_state` (l.2456 ; mémoire lue en direct l.2485-2487).
  - `_step_messages` (l.2525), `_assistant_message` (l.2604 : `reasoning_content` seulement si non vide), `_system_parts` (l.2631, mémoire l.2645), `_messages` (l.2671 : historique l.2690-2710), `_sub_messages` (l.2766), `_render` (l.2784).
  - `_start` (l.2944, rejeu par `_last`, l.637), `_delegate` (l.3264), `_run_subagent` (l.3300, `finally` l.3302-3330, appels l.3412-3444), `_apply_memory` (l.3663), `clear_conversation` (l.3957), `_reconfigure` (l.4042), `_turn` (l.4450 : rendu l.4500, `_check_prefix` l.4504, `previous` l.4516), `_check_prefix` (l.5373), `_call_model` (l.5425, `complete` l.5497, `model_call_ended` avec `prompt_ms`).
- `src/wavestack/trace/catalog.py` -- `PrefixNotReusedPayload` (l.395), `SubagentEndedPayload` (l.597), payload de `model_call_ended`.
- `src/wavestack/web/static/app.js` -- `prefix_not_reused` en étape (l.495, 681) et ligne « Préfixe non réutilisé » (l.3433).
- `tests/fake_engine.py` -- un token par octet, `calls` (l.61) ; `booted_session` (l.85). `tests/test_turn.py:23` `_run` ; `tests/test_tools.py` (`tool_session`, fixture Qwen, `"prefix_not_reused" not in events` l.80) ; `tests/test_reasoning.py:139` ; `tests/test_global_memory.py:114` et `:367` encodent la lecture en direct (à inverser, N1) ; `tests/test_subagent.py` ; `tests/test_render_reference.py:53` (test `model`, `WAVESTACK_TEST_GGUF`).
- `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md` -- l.108 (`prefix_not_reused{common_tokens}`), l.200 (ajout seul pendant un tour), AD-11 l.330 (préservation par `save_state`/`load_state`), AD-17 l.463 (mémoire « toujours dans son état courant »).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- trois entrées du 2026-09-27 (lot A : bloc `<think>` retiré, mémoire qui réécrit le message système, sous-agent qui occupe le contexte), à fermer.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/context/render.py` -- (a) fonction mise en cache `reasoning_wrap(template) -> tuple[str, str] | None` : par deux rendus sonde (un message assistant `content`/`reasoning_content` de repères privés, dans le tour puis avant une nouvelle question), déduit le texte que le gabarit écrit avant la réflexion et entre réflexion et texte pour un message du tour (Qwen3.5 : `"<think>\n"`, `"\n</think>\n\n"`), et le rend seulement si le gabarit l'omet pour un message passé et qu'un troisième rendu confirme qu'un `content` déjà enveloppé avec `reasoning_content = ""` ressort tel quel ; sinon ou en cas d'erreur de rendu, `None`. (b) Une `Part` de genre `TEMPLATE` est un littéral du harnais : `_neutralize` la laisse intacte (ni blancs retirés, ni jetons spéciaux cassés) -- A1 sans détourner AD-4.
- `src/wavestack/session/app_session.py` -- A1 : en mode local, quand `reasoning_wrap` n'est pas `None`, chaque message assistant de l'historique (réponse finale et étapes d'outils passées) a pour contenu un `Joined` sans séparateur `Part(TEMPLATE, avant) + Part(HISTORY, réflexion) + Part(TEMPLATE, milieu) + Part(HISTORY, texte)` et `reasoning_content = ""` (chaîne) ; le mode chat et le tour en cours ne changent pas. A2 : instantané de la mémoire par conversation (pris au premier tour d'une conversation vide, gardé dans l'état conversationnel et dans `_last` pour le rejeu, remis à zéro par `clear_conversation` et `_reconfigure`), lu par `build_turn_state` et l'aperçu ; texte de la carte ou du tiroir Mémoire qui dit qu'une entrée écrite entre dans le message système à la prochaine conversation. A3 : garder, par contexte (`main`), les ids que le moteur a en cache après chaque appel (`engine.cached_ids()` s'il le donne, sinon ids envoyés + `tokenize(sortie brute)`) ; au premier appel de chaque tour, s'ils ne sont pas un préfixe des nouveaux ids, émettre `prefix_not_reused` avec `cause` (`reset` après vidage, changement de scénario ou réinitialisation ; `replay` ; `abandoned` si le tour précédent n'est pas `completed` ; `subagent` si le cache contient un sous-contexte ; sinon selon le genre du segment qui contient le premier octet divergent : message système, mémoire, catalogues ou skills → `system`, `history` → `history`, autre → `template`) et un `message_fr` qui nomme la cause et le nombre de tokens à relire ; le contrôle intra-tour garde son texte avec `cause: "in_turn"`. A4 : dans `_delegate`, `engine.snapshot()` avant le sous-agent et `engine.restore()` dans le `finally`, taille de la copie et durée de restauration dans `subagent_ended` ; échec → relecture signalée, jamais d'erreur fatale. `model_call_ended` porte `evaluated_tokens` (tokens de prompt évalués par le moteur, `None` s'il ne le sait pas).
- `src/wavestack/models/engine.py` -- port : méthodes `cached_ids() -> list[int] | None`, `snapshot() -> EngineSnapshot | None` (`size_bytes`), `restore(snapshot) -> bool`, propriété `last_evaluated: int | None` ; `LlamaCppEngine` les implémente (`input_ids`, `save_state`/`load_state`, compteurs `llama_perf_context`) ; la session tolère un moteur qui ne les a pas (`getattr`).
- `src/wavestack/models/servers.py`, `src/wavestack/models/openai_chat.py` -- `cached_ids`/`snapshot` rendent `None`, `restore` `False`, `last_evaluated` `None` (ou la valeur que la réponse du serveur donne déjà, sans nouvelle requête).
- `src/wavestack/trace/catalog.py` -- `PrefixNotReusedPayload.cause` (littéral des sept causes, défaut `in_turn`) ; `SubagentEndedPayload.state_saved_bytes: int | None`, `state_restore_ms: int | None` ; `evaluated_tokens: int | None` sur `model_call_ended`.
- `src/wavestack/web/static/app.js` -- la ligne « Préfixe non réutilisé » affiche `message_fr` (cause comprise) ; la ligne d'un appel affiche « N tokens évalués » quand `evaluated_tokens` est présent.
- `tests/fake_engine.py` -- cache simulé (`cached_ids` = ids du dernier appel + octets émis), `snapshot`/`restore`, `last_evaluated` (longueur hors préfixe en cache), et une option pour désactiver l'état (moteur sans état).
- `tests/test_turn_cache.py` (nouveau) -- une ligne par cas de la matrice, avec la fixture Qwen3.5 : rendu de t2 = prompt + sortie de t1 (A5 sans GGUF), raisonnement gardé et attribué, gabarit sans bloc inchangé, mémoire figée puis visible après vidage et au rejeu, chaque `cause`, délégation avec et sans état (et échec de restauration), somme des segments = total.
- `tests/test_global_memory.py` -- inverser les deux tests qui encodent la lecture en direct (l.114, l.367) selon N1.
- `tests/test_engine_cache.py` (nouveau, sans marqueur `model`) -- avec `tests/fixtures/tiny-llama.gguf` : deux `complete` qui se prolongent → `last_evaluated` = tokens nouveaux ; `snapshot`, prompt divergent, `restore` → le prompt suivant n'évalue que ses tokens nouveaux.
- `tests/test_render_reference.py` -- test `model` (`WAVESTACK_TEST_GGUF`) : deux tours de `native_tools` sur le vrai GGUF ; au second, `evaluated_tokens` du premier appel = nouveaux tokens seulement, et aucun `prefix_not_reused`.
- `ARCHITECTURE-SPINE.md` -- AD-4 : ajout seul étendu à la conversation en mode local (historique rendu tel que produit, contrôle au premier appel du tour, `prefix_not_reused{common_tokens, cause}`) ; AD-11 : préservation par sauvegarde et restauration, faite ; AD-17 : mémoire globale figée par conversation (N1).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer (`closed:`) les trois entrées du lot A, avec « à vérifier sur PC » pour la mesure.

**Acceptance Criteria:**
- Given la fixture Qwen3.5 et le faux moteur, when deux tours de `native_tools` s'enchaînent, then le texte du premier appel de t2 commence par le texte du dernier appel de t1 suivi de sa sortie, et `prefix_not_reused` n'est pas émis.
- Given le vrai moteur sur `tiny-llama.gguf`, when un prompt prolonge le cache, then `last_evaluated` vaut le nombre de tokens nouveaux.
- Given une délégation avec un moteur qui sait sauvegarder, when le sous-agent rend son résultat, then le premier appel principal suivant n'évalue que les tokens nouveaux et `subagent_ended` porte la taille de la copie.
- Given une relecture inévitable, when elle arrive au premier appel d'un tour, then l'étape « Préfixe non réutilisé » en dit la cause en français.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 28 findings (38 constats des quatre couches, doublons regroupés sur une même ligne avec leurs sources) — high 0, medium 8, low 13, false 3, maybe-false 4
- findings:
  - `[medium]` `[patch]` Tiroir Mémoire (`index.html:65`) : « prend effet au prochain tour », faux sous N1 (blind) — texte réécrit.
  - `[medium]` `[patch]` Mémoire figée aussi pour une suppression ou une modification : une entrée retirée part encore chez un fournisseur cloud (blind) — instantané par (id, texte) : suppressions et modifications immédiates, ajouts à la conversation suivante.
  - `[low]` `[patch]` Instantané pris même brique Mémoire éteinte (blind) — pris au premier tour où la brique est effective.
  - `[medium]` `[patch]` Mémoire courte éteinte : chaque tour signalé « gabarit » (blind, edge, verification-gap) — divergence dans le message du tour → `history`, texte « mémoire courte éteinte ».
  - `[low]` `[patch]` Étapes armées `load_skill`/`load_tool_doc` après l'historique classées `system` (edge) — `system` limité au bloc de tête.
  - `[low]` `[patch]` Message système retiré (brique éteinte) classé `template` sans explication (blind, edge) — texte de `template` : brique activée ou désactivée, ou gabarit.
  - `[low]` `[patch]` Rejeu : « le moteur relit 0 tokens » (blind, edge) — formulation propre au cas.
  - `[low]` `[patch]` Contrôle avant le retour sur débordement : événement pour un appel qui n'a pas lieu (blind) — contrôle déplacé après.
  - `[low]` `[patch]` `abandoned` pour un tour qui n'a pas atteint le moteur (edge) — seulement si un appel principal a eu lieu.
  - `[medium]` `[patch]` `snapshot` : garde `written > size` inopérante (blind, edge) — `written <= 0` aussi.
  - `[medium]` `[patch]` `restore` en échec laisse `n_tokens` sur un état peut-être corrompu (blind, edge) — `n_tokens = 0`.
  - `[low]` `[patch]` Taille de la copie et durée de restauration invisibles dans l'interface (blind) — résumé de `subagent_ended`.
  - `[low]` `[patch]` Texte `system` sans « skill chargé » (blind) — ajouté.
  - `[low]` `[patch]` `FakeEngine(stateful=False)` rend des `cached_ids` (blind) — `None`, comme les serveurs.
  - `[medium]` `[patch]` Changement de modèle : remise à zéro du cache non testée (verification-gap) — assertion ajoutée.
  - `[medium]` `[patch]` Drapeau `subagent` jamais montré remis à zéro (verification-gap) — second tour testé.
  - `[low]` `[patch]` `evaluated_tokens` de llama-server et d'Ollama non testés (verification-gap) — tests ajoutés.
  - `[low]` `[patch]` Moteur sans `cached_ids` : divergence d'une réponse passée non testée (verification-gap) — test ajouté.
  - `[low]` `[patch]` Cause `template` jamais vérifiée (verification-gap) — test ajouté.
  - `[medium]` `[patch]` Restauration sur modèle hybride non couverte, même en test `model` (verification-gap) — test `model` ajouté (à lancer sur PC).
  - `[maybe-false]` `[patch]` Égalité stricte du test `model` (dernier token, lots de 1 token) (blind, edge, intent) — tolérance de ±1 ; à trancher en lançant le test sur le vrai GGUF.
  - `[maybe-false]` `[defer]` Copie d'état hors budget mémoire AD-8, sans contrôle de taille (blind, edge) — si vrai : medium ; se tranche en mesurant `state_saved_bytes` sur le PC cible.
  - `[maybe-false]` `[defer]` Blancs réels autour de `</think>` différents du gabarit (blind, intent) — si vrai : medium (relecture signalée `history`) ; se tranche avec le raisonnement actif sur le PC cible.
  - `[maybe-false]` `[reject]` Gabarit qui ne rogne pas le contenu (edge) — aucun gabarit connu ; la sonde de `reasoning_wrap` refuse déjà un rendu qui ne garde pas le contenu enveloppé ; si vrai : low.
  - `[low]` `[reject]` Durée de la sauvegarde non mesurée (blind) — la taille suffit au critère du plan ; ajout sans usage.
  - `[false]` `[reject]` `n_p_eval` ignore un lot d'un seul token (blind) — vérifié sur tiny-llama : un seul token nouveau est compté (`tests/test_engine_cache.py`).
  - `[false]` `[reject]` Journal des changements de la spec vide malgré l'écart `save_state` (blind) — correctif = modifier la spec.
  - `[false]` `[reject]` Intention : A4 inconditionnel alors que N2 dit « si la mesure confirme » (intent) — la mesure n'est possible que sur le PC ; la trace porte le coût, N2 validée par l'utilisateur.

## Design Notes

- Le bloc de raisonnement est gardé tel qu'il a été produit, vide ou non (plan, A1) : avec la brique raisonnement, la réflexion passée reste dans l'historique et se voit dans la jauge (`history`). C'est le prix de la réutilisation du cache ; le budget du lot C borne sa taille.
- Les extraits RAG, les talons de documentation et la compression réécrivent l'historique par conception : A3 les rend visibles (`cause: "history"`) sans les changer.
- Sur un modèle hybride, toute divergence coûte une relecture complète ; sur un modèle classique, seulement la suite. Le texte le dit sans connaître le type du modèle.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert (les tests `model` restent sautés sans GGUF)
- `node --check src/wavestack/web/static/app.js` -- expected: pas d'erreur de syntaxe

## Auto Run Result

Status: done

**Résumé.** En mode local, l'historique est rendu tel qu'il a été produit : `reasoning_wrap` déduit du gabarit le bloc de raisonnement que le tour écrit (Qwen3.5 : `<think>\n` … `\n</think>\n\n`) et le harnais le remet dans chaque réponse passée (littéraux `template`, réflexion et texte en `history`). La mémoire globale est figée par conversation (N1) : ajouts à la conversation suivante, suppressions et modifications immédiates. Le premier appel de chaque tour est comparé aux ids en cache du moteur ; une relecture émet `prefix_not_reused` avec sa cause (`system`, `history`, `template`, `reset`, `replay`, `abandoned`, `subagent`, `in_turn`) et le nombre de tokens relus. Le sous-agent sauvegarde et restaure l'état llama.cpp (N2, sans la copie des logits) ; taille et durée dans `subagent_ended` et dans l'interface. `model_call_ended.evaluated_tokens` donne les tokens de prompt réellement évalués (llama.cpp, llama-server, Ollama).

**Fichiers.**
- `src/wavestack/context/render.py` -- `reasoning_wrap`, parts `template` non neutralisées.
- `src/wavestack/models/engine.py` -- `EngineSnapshot`, `cached_ids`, `snapshot`, `restore`, `last_evaluated`.
- `src/wavestack/models/servers.py`, `src/wavestack/models/openai_chat.py` -- mêmes méthodes (sans état), `last_evaluated` de llama-server et d'Ollama.
- `src/wavestack/session/app_session.py` -- `_as_produced`, instantané mémoire, `_keep_cache`, `_check_reuse`, `_diverging_cause`, sauvegarde et restauration autour de `_delegate`.
- `src/wavestack/trace/catalog.py` -- `cause`, `evaluated_tokens`, `state_saved_bytes`, `state_restore_ms`.
- `src/wavestack/web/static/app.js`, `index.html`, `content/bricks/global_memory.yaml` -- cause, tokens évalués, état sauvegardé, textes de la mémoire.
- `tests/fake_engine.py`, `tests/test_turn_cache.py`, `tests/test_engine_cache.py`, `tests/test_global_memory.py`, `tests/test_model_servers.py`, `tests/test_model_switch.py`, `tests/test_render_reference.py` -- tests.
- `ARCHITECTURE-SPINE.md` (AD-4, AD-11, AD-17), `deferred-work.md` (trois entrées fermées).

**Revue.** 20 patchs (8 medium, 12 low ou maybe-false), 2 différés (maybe-false, medium si vrais : budget de la copie d'état, blancs autour de `</think>`), 6 rejetés (voir le journal de triage). `followup_review_recommended: false` : aucun high ; les medium corrigés sont des textes, des gardes et des tests, vérifiés par la suite.

**Vérification.** `ruff check` et `ruff format --check` : OK ; `node --check app.js` : OK ; `pytest -q` : 799 réussis, 4 sautés ; tests `model` sur `tiny-llama.gguf` (sauvegarde et restauration) : OK.

**Risques résiduels (à vérifier sur PC).** Gain réel sur Qwen3.5 hybride (second tour de `native_tools` sous 3 s, quiz du sous-agent sous 15 s) ; restauration de l'état récurrent de Qwen3.5 ; taille de la copie ; retokenisation de la sortie (une divergence serait signalée `history`). Les extraits RAG restent hors de l'historique (story 15) : dans les scénarios avec RAG, chaque tour relit le contexte (cause `history`), à revoir au lot H (D5).
