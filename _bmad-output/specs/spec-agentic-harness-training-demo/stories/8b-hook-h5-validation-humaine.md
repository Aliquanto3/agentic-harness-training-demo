---
title: 'Hook H5 : validation humaine avant tout outil réseau'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: 'b92d481464d524bc0cf305b92312f1e97c5f0d35'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Rien ne montre encore qu'un harnais peut suspendre un tour pour demander à un humain s'il accepte qu'une donnée sorte du poste (CAP-28, CAP-29, FR-27, FR-28) : c'est le « human in the loop » qui parle aux practices cyber et DLP.

**Approach:** Un quatrième hook de la brique « Hooks », H5, en `before_tool` sur tout outil `network = true` (outils réseau natifs, outils des serveurs MCP publics). Il rend `ask_human` avec l'aperçu exact de la requête ; la session passe en `awaiting_human`, montre une carte violette à trois boutons et attend, sans délai d'expiration, une intention de classe (c) (AD-3, AD-13, AD-14). Tout passe par `_run_tool` et `_hook` livrés en story 8.

## Boundaries & Constraints

**Always:**
- `ask_human` rejoint `HookDecision` (`trace/catalog.py`) et `ALLOWED["before_tool"]`. Comme `block`, c'est une décision qui arrête la boucle des hooks du point : H1 bloquant passe avant H5.
- H5 (`hooks.h5`, fonction pure) ne se sent pas concerné (`None`) si l'outil n'est pas `network` ou n'a pas d'aperçu, ou si l'aperçu est refusé (`ToolError`, hôte hors liste) : rien ne sortirait, c'est l'exécuteur qui refuse. Sinon `HookResult("ask_human", detail_fr, preview={method, url, body})`.
- L'aperçu est exactement ce qui sortirait : pour un outil réseau natif, son `preview` (AD-15) ; pour un outil MCP public, `preview` est ajouté à sa `ToolSpec` (`_mcp_spec`, serveurs réseau seulement) : `POST` vers l'URL du serveur, corps JSON `{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": <nom réel de l'outil sur le serveur>, "arguments": …}}`. L'`id` JSON-RPC, attribué par le client MCP à l'envoi, n'y figure pas ; l'`outbound_request` émis à l'envoi montre le corps réel.
- Sur `ask_human`, la session émet `hook_decided{decision: ask_human}`, puis `approval_requested{approval_id, tool, destination, preview}` (`destination` = hôte de l'URL, brique `hooks`, composant `hooks.h5`, même étape), passe en `awaiting_human` (« En attente de votre validation : autorisez ou refusez l'appel réseau. ») et attend.
- Intention de classe (c) `POST /api/intentions/approval {approval_id, approved, disable_hook}` : acceptée seulement pour la validation en attente ; la première réponse l'emporte, toute autre (id inconnu, déjà répondue, hors attente) → 409 avec la raison en français. `disable_hook` ne vaut qu'avec `approved`.
- Résolution : `approval_resolved{approval_id, decision: approved|refused|cancelled, hook_disabled}` (`actor = user`), puis retour à l'état `turn`.
  - `approved` : l'outil s'exécute comme sans H5 (`tool_started`, `outbound_request`, `tool_ended`, `after_tool`).
  - `refused` : rien n'est envoyé, pas de `tool_started` ; le refus est réinjecté comme un blocage de H1 (`tool_result` de la brique `hooks`, composant `hooks.h5`) : « Refusé par l'utilisateur (validation humaine) : l'appel à « X » vers {hôte} n'a pas été envoyé. » ; il ne compte pas comme un nouvel essai ; le tour continue.
  - « Arrêter » pendant l'attente : `stop()` est accepté en `awaiting_human`, arme le `CancelToken` et résout l'attente en `cancelled` ; `turn_ended{cancelled}`. `close()` (arrêt de l'application) passe par `stop()` et ne reste donc jamais bloqué.
- « Autoriser et ne plus demander » : l'appel part, H5 sort de `_hooks_enabled` (et de la configuration figée `_sent`, pour qu'aucun « Prend effet au prochain tour » n'apparaisse) et ne demande plus rien pour les appels réseau suivants du même tour ; cartes des briques et schéma réémis.
- H2 consigne chaque `approval_resolved` : `validation humaine | {outil} vers {hôte} | autorisé|refusé|annulé`.
- `GET /api/state` gagne `pending_approval` : le payload du dernier `approval_requested` sans `approval_resolved`, sinon `null`.
- Brique : `HOOKS = ("h1", "h2", "h3", "h5")`, nœud `hooks.h5` (`kind: hook`, local, relié au harnais) ; libellé « Validation humaine » et description dans `content/hooks.yaml` ; la carte de la brique (`content/bricks/hooks.yaml`) cite H5.
- UX (EXPERIENCE.md) : la carte de l'étape H5 est violette, titrée « En attente de votre validation », avec l'outil, la destination, le bloc `outbound-payload` de l'aperçu (réutilisé) et les boutons « Autoriser », « Refuser », « Autoriser et ne plus demander », actifs seulement pendant l'attente. Une fois résolue, les boutons laissent la place à la décision (« Autorisé », « Refusé », « Annulé : tour arrêté », plus « H5 désactivé » le cas échéant). Dans la vue humain, l'indicateur de travail affiche « En attente de validation » ; « Arrêter » reste visible en `awaiting_human`. Le front rejoue le journal : une page rechargée retrouve la carte en attente.

**Décisions (2026-09-24) :**
- Q1 : à l'activation de la brique, H5 est désactivé (H1, H2, H3 activés). Carte : « Hooks : 3 activés sur 4 ».
- Q2 : trois boutons « Autoriser », « Refuser », « Autoriser et ne plus demander » ; ce dernier autorise l'appel puis désactive H5, y compris pour les appels réseau suivants du même tour. Remplace les deux boutons d'EXPERIENCE.md.

**Never:** pas de délai d'expiration ; pas de validation pour un outil local ni pour le serveur MCP local ; aucun appel réseau avant la réponse ; H5 n'écrit aucun état (la session applique la désactivation) ; pas d'action forcée ni de sous-agent (story 9) ; le front ne calcule aucun état (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Activation | Brique « Hooks » cochée | H5 dans la carte, décoché ; nœud absent du schéma tant qu'il est désactivé ; « 3 activés sur 4 » | N/A |
| Autoriser | H5 actif, `public_holidays(2026)` | `ask_human`, `approval_requested` (aperçu = `preview`), `awaiting_human`, puis `approved`, requête envoyée, réponse finale | N/A |
| Refuser | Idem, refus | Aucune requête, refus réinjecté (`hooks.h5`), réponse finale, H2 : ligne « refusé » | N/A |
| Ne plus demander | Deux appels réseau dans le tour | Une seule demande ; H5 désactivé dans le panneau, sans « Prend effet au prochain tour » | N/A |
| Arrêter | Stop pendant l'attente | `approval_resolved{cancelled}`, `turn_ended{cancelled}`, rien d'envoyé | N/A |
| Double réponse | Deux `approval` pour le même id | La première l'emporte | Seconde : 409 |
| Hôte hors liste | `fetch_page("https://exemple.com")` | Pas de demande ; l'exécuteur refuse | Erreur réinjectée |
| MCP public | Outil data.gouv.fr, H5 actif | Aperçu `POST` URL du serveur, corps `tools/call` | N/A |
| Outil local | `get_datetime`, H5 actif | Pas de demande | N/A |
| H5 éteint | Appel réseau | Envoyé sans demande | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/trace/catalog.py` : `HookDecision` (L294) + `ask_human` ; payloads `approval_requested{approval_id, tool, destination, preview: {method, url, body}}` et `approval_resolved{approval_id, decision, hook_disabled}` dans `PAYLOAD_MODELS`. `awaiting_human` existe déjà dans `SessionState` (L40).
- `src/wavestack/hooks.py` : `ALLOWED["before_tool"]` + `ask_human` ; `HookResult.preview: dict[str, str] | None` ; fonction `ask` (H5) ; `DEMO_HOOKS` + `Hook("h5", {"before_tool"}, ask)` ; `audit` : ligne sur `approval_resolved` (le `tool_started` n'existe pas pour un refus : prendre l'outil et l'hôte dans l'`approval_requested` du même `approval_id`).
- `src/wavestack/bricks/registry.py` L31 : `HOOKS` + `h5`.
- `content/hooks.yaml`, `content/bricks/hooks.yaml` : texte H5 (AD-19).
- `src/wavestack/session/app_session.py` :
  - `__init__` (L218) : `_hooks_enabled = set(ids) - {"h5"}` (Q1), `_sent` en conséquence ; `self._approval` (validation en attente : id, payload, `threading.Event`, réponse) et `self._hooks_off: set[str]` (hooks coupés pour le reste du tour, vidé dans `_run_turn`).
  - `_hook` (L1696) : filtre aussi `self._hooks_off` ; `ask_human` rend la main comme `block`.
  - `_run_tool` (L1664) : sur `ask_human`, `_await_human(hook_id, call, spec, result)` → `approved` (continue), `refused` (retourne le texte et `hook_id`, comme un blocage), `cancelled` (retourne `None`). Ids `{turn_id}.a{n}`.
  - `answer_approval(approval_id, approved, disable_hook) -> None`, lève `SendRefused` si la réponse n'est pas acceptée ; `stop()` (L1477) accepte `awaiting_human` et résout en `cancelled` ; `_refusal_reason` (L1470) : raison pour `awaiting_human`.
  - `_mcp_spec` (L1398) : `preview` pour `server.network`.
- `src/wavestack/web/app.py` : `ApprovalIntention`, `POST /api/intentions/approval` (409 sur `SendRefused`), sur le modèle de `send` (L185) ; `pending_approval` dans `api_state` (L131).
- `src/wavestack/web/static/app.js` : `applyEnvelope` (L104) : `approval_requested` / `approval_resolved` rattachés à la dernière étape `hook` (comme `effect_applied`, L234) ; `hookCard` (L924) : titre et bloc de validation, `outboundPayload` (L907) réutilisé, boutons → `postIntention("/api/intentions/approval", …)` (L691) ; `HOOK_DECISIONS` : `ask_human` ; `renderComposer` (L674) : « Arrêter » visible en `awaiting_human` ; indicateur de travail (L657) : « En attente de validation ». `app.css` : boutons de la carte si les styles existants ne suffisent pas.
- Tests : `tests/test_hooks.py` (`hooks_session`, `since`, `check`, `audit_lines`) et `network_session`/`MockTransport` de `tests/test_tools.py` (L444-490) ; `tests/test_mcp.py` (L120) pour le serveur public simulé. La réponse se donne depuis le fil du test une fois `approval_requested` émis (attente bornée sur le journal).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/trace/catalog.py`, `src/wavestack/hooks.py`, `src/wavestack/bricks/registry.py`, `content/hooks.yaml`, `content/bricks/hooks.yaml` -- `ask_human`, H5, événements, texte, ligne d'audit -- AD-2, AD-13, AD-19
- [x] `src/wavestack/session/app_session.py` -- attente, réponse, arrêt, désactivation, aperçu MCP -- AD-3, AD-13, AD-14, AD-15
- [x] `src/wavestack/web/app.py`, `static/app.js`, `static/app.css` -- intention `approval`, `pending_approval`, carte, indicateur -- AD-1, AD-18
- [x] `tests/test_hooks.py` -- les lignes de la matrice, la route HTTP (200 puis 409) et `pending_approval` ; chaque rendu : somme des tokens égale au total, aucun `harness_error`

**Acceptance Criteria:**
- Given H5 actif et un outil réseau activé, when le modèle l'appelle, then Orchestration montre la carte violette avec l'URL et le corps exacts, la vue humain affiche « En attente de validation », et aucune requête ne part avant un clic.
- Given une validation en attente, when l'utilisateur clique « Refuser », then la requête n'apparaît jamais dans les `outbound_request` et la réponse finale du modèle s'affiche.
- Given une validation en attente, when on recharge la page, then la carte en attente réapparaît avec ses boutons actifs.

## Implementation Notes

- Aperçu MCP : le client MCP ajoute `"_meta": {}` à `params` à l'envoi ; l'aperçu l'inclut, pour rester identique au corps envoyé à l'`id` JSON-RPC près (vérifié par `test_h5_public_mcp_preview_is_the_tools_call_body` contre l'`outbound_request` réel).
- Matrice, ligne « Activation » : précisée avec Anaël (2026-09-24), règle de la story 8 : un hook désactivé est dans la carte, pas dans le schéma.
- Titre de la carte une fois résolue : « Validation humaine » ; mention « Décision demandée par le harnais (code), pas par le modèle ».
- `pending_approval` compare l'ordre des événements (`seq`), pas les ids : les ids `t1.a1` se répètent entre sessions dans le journal du processus.
- « Arrêter » juste après « Autoriser » : la résolution reste `approved`, l'exécuteur voit le `CancelToken` armé, rien n'est envoyé, `turn_ended{cancelled}`.

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 25 constats) :

- [EC1/EC7] `host()` passe par `urlsplit`, qui lève `ValueError` sur une URL que httpx accepte (`https://x]@fr.wikipedia.org/`, vérifié) : H5 échoue, `_hook` le compte comme `allow`, la requête part sans validation. `high`, confirmé (contournement du garde-fou par une URL choisie par le modèle). -> P1 `patch` (analyser avec `httpx.URL`, le parseur de l'envoi).
- [BH9] Sur `cancelled`, `_await_human` repasse en `turn` avant `idle` : « Arrêter » réapparaît un instant. `low`, confirmé ; correction d'une condition. -> P2 `patch`.
- [BH6/EC5] `approvalLines` : après une réponse non-ok, `step.answering` reste vrai et les boutons restent grisés. `low`, confirmé ; correction directe. -> P3 `patch`.
- [BH1] La carte de la brique promet une suspension « avant tout appel réseau », alors que H5 ne vise que les outils réseau et démarre désactivé. `low`, confirmé ; correction du texte. -> P4 `patch`.
- [VG1] Rien ne vérifie que `_hooks_off` est vidé à chaque tour : H5 recoché après « ne plus demander » pourrait ne plus jamais demander. Pré-vérifié. -> P5 `patch`.
- [VG2/BH12c] La branche « arrêt juste avant l'attente » de `_await_human` n'a aucun test ; une régression bloquerait le tour et `close()`. Pré-vérifié. -> P6 `patch`.
- [VG3] Un hook `modify` avant H5 : rien ne vérifie que l'aperçu et l'envoi portent les arguments modifiés. Pré-vérifié ; aucun hook livré ne modifie en `before_tool`. -> `defer`.
- [VG4] Carte de validation, boutons et « Arrêter » en `awaiting_human` sans test automatique (pas de banc JS). Pré-vérifié. -> `defer`.
- [EC2] `preview` qui lève autre chose que `ToolError`. `false` : l'exécuteur appelle le même `preview` avant `run` ; l'exception l'empêche d'envoyer quoi que ce soit.
- [EC3/VG-o1] Un `ask_human` sans `preview` exécute l'outil sans validation. `low`, rejeté : `ask` fournit toujours l'aperçu ; seul un hook de test y parvient, et la correction ajoute une branche.
- [EC4] `_await_human` avec `self._cancel` à `None`. `false` : `send` arme le jeton avant de lancer le tour, `_run_turn` ne le remet à `None` qu'à la fin.
- [EC6] L'aperçu MCP omet l'`id` JSON-RPC. `low`, rejeté : voulu et écrit dans la spec ; vérifié contre le corps réellement envoyé.
- [BH2] « Requête exacte » alors que l'aperçu omet les en-têtes. `low`, rejeté : même convention que `outbound_request` (AD-15 : méthode, adresse, corps).
- [BH3] `_sent` modifié par position (index 6). `low`, rejeté : structure préexistante ; la correction (NamedTuple) dépasse une correction directe.
- [BH4] L'id d'étape recalculé dans `_await_human`. `false` : `_hook` rend la main sur `ask_human` sans incrémenter `_hook_steps` ; un test vérifie l'égalité des trois `step_id`.
- [BH5] `pending_approval` n'est pas lu par le front. Rejeté : demandé par la spec pour les clients qui démarrent sur l'instantané ; le front rejoue le journal.
- [BH7] `approval_requested` rattaché à la dernière étape `hook` et non par `step_id`. `false` : il suit immédiatement le `hook_decided` de H5 ; les sous-agents (story 9) ne sont pas livrés.
- [BH8] `_approval` jamais remis à `None` : une réponse tardive reçoit « déjà reçu une réponse ». `false` : 409 avec une raison exacte, comme le veut la spec.
- [BH10] La ligne d'audit n'a pas les arguments. Rejeté : format de ligne fixé par la spec.
- [BH11] `test_h5_close_while_waiting_never_hangs` bloquerait au lieu d'échouer. `low`, rejeté : la correction ajoute du code de test pour une régression improbable.
- [BH12a] H1 bloquant avant H5 sur le même appel, sans test. `low`, rejeté : inatteignable avec les hooks de démonstration (H1 ne vise que les outils à chemin local, H5 que les outils réseau).
- [BH12b] « Arrêter » juste après « Autoriser », sans test. `low`, rejeté : chemin du `CancelToken` déjà couvert par l'exécuteur (`run` retourne `None`).
- [BH12d] `send`/`clear_conversation` pendant l'attente. `low`, rejeté : refus par `state != "idle"`, raison `_AWAITING_FR` portée par `reason_fr`.
- [BH13] Le test « première réponse » n'est pas concurrent. `low`, rejeté : l'exclusion est sous `self._lock`, un test séquentiel suffit à la règle.
- [BH1b] Ligne de YAML trop longue. `false` : déjà repliée avant la revue.

Groupes routés en `patch` : P1 à P6 ; `defer` : VG3, VG4 ; aucun `intent_gap` ni `bad_spec`, pas de retour en arrière.

## Design Notes

L'attente bloque le fil du tour (`threading.Event`, sans délai, AD-13 et R-09 de la revue d'architecture) ; le fil HTTP la débloque par `answer_approval` ou `stop`. Le tour tourne déjà sur l'unique fil de travail de la session : rien d'autre n'y attend.

L'aperçu vient de la `ToolSpec`, que l'exécuteur appelle aussi avant d'envoyer : H5 montre ce que l'exécuteur enverra, sans étape `prepare()` supplémentaire (R-10). Pour MCP, seul l'`id` JSON-RPC échappe à l'aperçu.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks (if no CLI):**
- `uv run wavestack` : activer « Outils » (jours fériés) et « Hooks », cocher H5 ; demander les jours fériés 2026 ; vérifier la carte, l'indicateur, puis « Refuser » ; recommencer avec « Autoriser et ne plus demander ».
