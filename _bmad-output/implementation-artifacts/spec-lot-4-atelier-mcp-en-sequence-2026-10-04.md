---
title: 'Lot 4 du plan de corrections du 2026-10-04 : Atelier MCP en séquence'
type: 'feature'
created: '2026-10-05'
status: 'done'
baseline_commit: '98014e6cd918d33e15c754c19ee512d0a533eb44'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/.working/maquette-atelier-mcp-sequence.html'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La page `/mcp` (story 6) empile cinq sections statiques : elle ne montre ni qui parle à qui, ni ressources et prompts, ni le modèle qui choisit un outil. Le lot 4 veut un diagramme de séquence progressif, une architecture et « Ce que le modèle voit », dans quatre volets comme l'Atelier Harnais.

**Approach:** Dans cet ordre : (1) backend et contrat d'AD-27 (`mcp/lab.py`, `local_server.py`, session, catalogue, routes) ; (2) modules communs d'AD-28 (`panes.js` extrait d'`app.js`/`app.css`, retouches et `reveal()` de `diagram.js`, sans changement visible pour l'Atelier Harnais hors anneau et fil) ; (3) réécriture de `mcp.html`/`mcp.js`/`mcp.css` (découverte progressive des trois volets, gouttières, barre WaveStack fixe). Préséance : AD-27/AD-28 > EXPERIENCE.md « Atelier MCP en séquence » > maquette.

## Boundaries & Constraints

**Always:**
- Le contrat est celui d'AD-27, mot pour mot : pas `^mcp(\d+)(\.[ct]\d+)?$`, une paire `mcp_lab_*` par pas, `Capture.begin/end`, appariement (sens, `id`), `unsolicited`, champs de `mcp_lab_message`, `exchange_started`, `connect_ended` (primitives, listes, `list_errors`), table des fins (`status`, `error_kind`, `connection`, `failed_seq`), `mcp_lab_closed`, `read/prompt/ask_ended`, `model_started/ended`, `outbound_request.message_seq`, `last_session` (dix `mcp_lab_*` + `model_call_*` + `outbound_*`), cause `mcp_lab`.
- AD-1 : la page ne calcule rien, ne lit `jsonrpc` que dans l'encart, ne compare aucun `*_text` ; direct et restitution passent par le même code.
- Un `ask` ne touche ni jauge, ni `_ratio`, ni coûts du tour : local par `_call_model`, cloud par `run_call` direct ; registre, exécuteur et définitions propres à l'atelier ; aucun hook ni effet ; aucun nouvel essai.
- Brique MCP inchangée (`McpConnection`, `_mcp_conns`, registre principal).
- Atelier Harnais : seuls l'anneau d'encre du bloc actif et le cœur du fil à 3 px changent visiblement ; ses volets passent par `panes.js` sans autre changement (E2E `panes`, `linked_view`, `themes`).
- Textes en fr/en/de (`content/mcp_lab.yaml`, `ui.yaml` section `mcp` et `common`, `messages.yaml`) ; couleurs par jetons seulement ; `aria-disabled` pour les commandes indisponibles.

**Never:**
- Toucher aux ateliers LLM et RAG (lots 5 et 6), ni à la page Diagnostic.
- Réimplémenter ou surcharger une règle `diagram-*` ou `pane-*` hors de `pages.css`.
- Suivre le curseur de pagination des listes ; inliner un contenu non textuel ; renvoyer au modèle un contenu fourni par la page.
- Dépendance externe ou CDN ; `pip`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Poignée de main locale | Se connecter au Glossaire | `initialize`, `notifications/initialized`, `tools/list`, `resources/list`, `prompts/list` capturés ; onglets 🔧 2 · 📄 1 · 💬 1 | N/A |
| Serveur public sans ressources | data.gouv.fr (faux serveur en test) | ni `resources/list` ni `prompts/list` ; onglets ⊘ ; note dans la phase | N/A |
| Liste en échec | `prompts/list` hors délai | `list_errors`, connexion `open`, onglet actif « La liste … a échoué » | flèche rouge |
| Injoignable | serveur hors ligne | `connect_ended{error, unreachable, closed}`, ✖ sur flèche et fil | « Le glossaire, local, reste disponible » |
| `isError` | `define_term("xyz")` | `call_ended{status: ok, is_error: true}`, flèche rouge | réinjecté tel quel |
| Lecture puis envoi | `glossary://terms`, question | `read_ended` ; `ask{of}` envoie le contenu gardé par la session | 409 sans lecture réussie |
| Prompt puis envoi | `explain_term(term)` | `prompt_ended.messages` ; `ask{of}` sans question | 409 si argument requis manquant |
| Par le modèle | question, outil choisi | `c1` tool_call → `t1` `tools/call` → `c2` answer ; `ask_ended{ok, answer}` | refus harnais : `refused` |
| Arrêter | pendant requête MCP / génération | `cancelled, stopped, closed` / `open` | état `idle` |
| Fenêtre dépassée | contexte > utile | `model_started` puis `model_ended{error, overflow}`, aucun `model_call_*` | N/A |
| Rechargement | après échanges | `last_session` rejoué, phases repliées sauf la dernière, en direct | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/mcp/lab.py` -- `Capture` (pas courant, appariement, `seq` des requêtes, `summary_text`), `LabConnection` (remplace `_serve` : `start()` → `Handshake`, file `call_tool|read_resource|get_prompt`), `KINDS`, `step_number`, `last_session`, `McpLabContent` (8 méthodes, nouveaux textes), `METHODS`.
- `src/wavestack/mcp/local_server.py` -- ajouter ressource `glossary://terms` et prompt `explain_term(term)` ; textes dans `content/mcp_local/*.yaml` (fr/en/de).
- `src/wavestack/mcp/connection.py` -- `describe_error` réutilisé ; `McpConnection` inchangée.
- `src/wavestack/trace/catalog.py:52,649,1320-1444` -- `OutboundRequestPayload.message_seq`, `PrefixCause += "mcp_lab"`, nouveaux payloads mcp_lab, `PAYLOAD_MODELS`.
- `src/wavestack/session/app_session.py:9387-9764` -- réécriture de la partie atelier MCP : intentions `mcp_lab_read`, `mcp_lab_prompt`, `mcp_lab_ask`, `mcp_lab_state().ask`, fermetures (`reset` ajouté). Réutiliser `_run_lab` (rendu local/cloud, `render_context`, `render_chat_body`, `output_reserve`), `_call_model(..., registry=)` (paramètre facultatif pour les schémas de `parse_tool_calls`), `_tool_definitions`/`_doc_catalog` (registre en paramètre facultatif), `ToolExecutor(registry).check`, `_bound_result`, `_count_tokens`, `_save_main_state`, `_lab_restore(saved, cause)`, `_PREFIX_CAUSES:324`.
- `src/wavestack/web/app.py:237-540,557` -- routes `mcp_lab_read|prompt|ask`, filtre de jauge `/api/state` excluant `mcp_lab`.
- `content/mcp_lab.yaml` (+en/de), `content/ui.yaml` (`mcp`, `common.diagram`, `common.panes`, `main.log.kinds`, `main.orch.prefix_causes`), `content/messages.yaml` (`session.mcp_lab.*`, `session.prefix.causes.mcp_lab`).
- `src/wavestack/web/static/diagram.js` -- `reveal`, options `describe/onLive`, `load`, `refresh`, `aria-disabled`, nœud `status`, `explain()` focusout.
- `src/wavestack/web/static/app.js:901-924,6083-6418,7413-7511` + `app.css:200-537,2249-2289,4636-4653` -- mécanique des volets et projection → `static/panes.js` + `pages.css` (`pane-*`, `:root.projection`).
- `src/wavestack/web/static/mcp.{html,js,css}` -- réécriture complète d'après la maquette.
- `tokens.css` -- `--spacing-stroke-path: 3px`.
- Tests : `tests/test_mcp_lab.py` (fixtures `test_mcp.loop/web/McpWeb`, ajouter ressources/prompts au faux serveur HTTP si besoin), `tests/test_ui_texts.py:30-33`, `tests/test_web_tokens.py:537,616-628`, `tests/test_i18n.py:254`, `tools/e2e/run_e2e.py` (`s_mcp_lab:6700`, `s_mcp_lab_page:6848`, `_mcp_fake_session:7148`, `_diagram_module:1040`, `s_panes:3345`), faux modèle cloud `tools/e2e/fake_openai.py` (`_plan`).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/mcp/lab.py`, `local_server.py`, `content/mcp_local/*` -- capture, `LabConnection`, ressource et prompt -- socle AD-27.
- [x] `src/wavestack/trace/catalog.py` -- payloads et `message_seq`, cause `mcp_lab` -- contrat validé.
- [x] `src/wavestack/session/app_session.py` -- échanges `connect|call|read|prompt|ask`, fins, fermetures, `ask`, état -- AD-27.
- [x] `src/wavestack/web/app.py` -- routes et filtre de jauge.
- [x] `content/*.yaml` (fr/en/de) -- textes du contrat et de la page.
- [x] `tests/test_mcp_lab.py` -- couvrir la matrice côté session (dont `ask` avec `FakeEngine` à appel d'outil, `last_session`, `open_server` = dernière `connection`).
- [x] `src/wavestack/web/static/panes.js`, `pages.css`, `app.js`, `app.css`, `index.html` -- extraction sans changement visible.
- [x] `src/wavestack/web/static/diagram.js`, `pages.css`, `tokens.css` -- retouches et `reveal()` d'AD-28 ; test pytest « aucun `.diagram-` hors de `pages.css` ».
- [x] `src/wavestack/web/static/mcp.{html,js,css}` -- quatre volets, Séquence progressive, Ce que le modèle voit, Architecture (Avant/Avec MCP), barre fixe, projection.
- [x] `tools/e2e/run_e2e.py` -- réécrire `s_mcp_lab`/`s_mcp_lab_page` (poignée de main, appel, ressource, prompt, ask par le faux modèle cloud, stepper, restitution, volets) ; étendre `_diagram_module` (reveal, aria-disabled, status, load/refresh).

**Acceptance Criteria:**
- Given le Glossaire connecté, when on avance ◀ ▶ dans la Séquence, then colonnes, flèches, phases, blocs d'architecture et blocs de « Ce que le modèle voit » apparaissent et disparaissent avec l'étape, sans déplacer les colonnes.
- Given « Par le modèle » sur le faux modèle cloud, when la question part, then la séquence montre Hôte → modèle, modèle → Hôte (appel), `tools/call`, résultat, réponse finale, et la jauge de l'atelier principal ne bouge pas.
- Given l'Atelier Harnais, when les E2E `panes`, `linked_view`, `themes` et `native_tools` tournent, then ils passent.
- Given un rechargement de `/mcp`, when la page se reconstruit, then elle montre les mêmes flèches qu'en direct.

## Implementation Notes

- Implémentation par un sous-agent et deux bifurcations parallèles (modules communs AD-28 ; page `/mcp` et E2E), intégrée et revérifiée sur l'arbre final : ruff propre, `node --check` propre, pytest 5607 passés, 1 échec préexistant (`test_docs_links.py::test_readme_is_a_short_onboarding_page`, README inchangé, 121 lignes à `98014e6`), E2E ciblés 183 PASS, 0 FAIL.
- Ajouts hors Code Map : `content/mcp_local/primitives.yaml` (fr/en/de, textes de la ressource et du prompt), `servers.load_local_primitives`, `create_async_client(annotate=)` dans `net/factory.py` pour `message_seq`, `spacing.stroke-path` dans le frontmatter de DESIGN.md (miroir testé de `tokens.css`).
- L'intention `mcp_lab_call` accepte `arguments` (AD-27) et encore `args`.
- Vérification visuelle à 1280×650 et 1600×1000 (script Playwright hors dépôt) : relevés V1 à V4 dans le journal de triage.
- Après les correctifs de la passe 1 : ruff et `node --check` propres ; pytest 5618 passés, 1 échec préexistant (README) ; E2E `mcp_lab mcp_lab_page panes linked_view themes native_tools` : 185 PASS, 0 FAIL ; contrôle visuel refait : l'Architecture tient dans sa bande (étiquette « Poste de travail » déplacée dans une case libre du bas pour gagner la hauteur), « Avant MCP » en schéma, boutons des volets visibles en projection.
- Captures E2E : seules 61, 62, 63 (nouvelle) et 66 sont mises à jour ; celles de l'Atelier Harnais régénérées par la passe E2E sont rendues à leur version commitée, comme au lot 2.
- Écarts restants, connus : AD-27 nomme `session_reset`, l'événement réel est `harness_reset` (la page suit le réel ; à corriger dans la spine) ; budget vertical en projection à 1280×650 : environ trois flèches visibles avec les quatre volets, le repli prévu (masquer un volet, focus) reste nécessaire.

## Review Triage Log

Passe 1 (Blind Hunter BH, Edge Case Hunter EC, Verification Gap VG, vérification visuelle V).

| # | Constat | Verdict | Preuve | Route |
| --- | --- | --- | --- | --- |
| BH1/EC15/EC18 | La page attend `session_reset`, la session émet `harness_reset` : après une réinitialisation, la série reste affichée en direct, vide au rechargement | medium | `mcp.js:2066` ; `catalog.py:1618` ne connaît que `harness_reset` (AD-27 nomme l'événement par erreur) | patch |
| BH2/EC7 | `_lab_restore` qui lève empêche `mcp_lab_ask_ended` | low | même `try` que `_mcp_lab_finish` (`app_session.py:10281-10286`) | patch |
| EC8 | Le second emit de repli de `_mcp_lab_finish` peut lever et faire sortir l'exception du worker | low | `app_session.py:9653` hors `try` | patch |
| BH3/EC13 | Synthèse de phase muette sur l'échec d'un appel ou d'un `ask` | medium | `phaseSummary` sort avant la branche d'échec pour `call` et `ask` (`mcp.js:730-737`) | patch |
| BH4 | Les échecs historiques sont réannoncés en `alert` après rechargement | low | `announce()` saute sans marquer `store.announced` pendant `restoring` | patch |
| BH5/EC12 | Flèches Serveur → Source dessinées sur une réponse JSON-RPC `error` | false | AD-27, table des flèches déduites : « isError et erreur JSON-RPC compris » | reject |
| BH6 | Une liste en `jsonrpc_error` est marquée « sans réponse » | low | `mcp.js:298-302` met `unanswered` sans regarder `error_kind` | patch |
| BH7/EC1 | Gabarit ressource rempli par `.replace` successifs : un `{question}` dans la ressource est substitué | medium | `app_session.py:10334-10336` | patch |
| BH8 | `ask_ended` d'un dépassement sans `error_text` | low | `app_session.py:10455-10463` ; le `model_ended` le porte | patch |
| BH9/EC4 | Seul le premier appel d'outil d'une sortie est considéré, les autres disparaissent sans trace | low | AD-27 ne traite que le premier outil ; ajout de champ = surface nouvelle | reject |
| BH10 | Une erreur JSON-RPC sur `mcp{n}.t1` clôt l'`ask` au lieu d'être réinjectée | false | AD-27, fins d'un `ask` : « erreur … du `tools/call` → error, null » | reject |
| BH11 | `prompt_ended` ne dit pas la troncature | low | AD-27 ne prévoit pas `truncated` pour un prompt ; rare (plafond des résultats) | reject |
| BH12 | `outbound_response` et requêtes sans `message_seq` non dessinées | low | AD-27 : seul le `POST` porte un message ; GET/DELETE hors séquence | reject |
| BH13 | `LabConnection` duplique `_transport`/`_serve` de `McpConnection` | low | la brique doit rester inchangée (spec, Always) ; refactor non trivial | reject |
| BH14/EC11 | Gabarits du prompt local non validés (`{term}`, `{definition}`, `{known}`) | medium | `servers.py` `LocalPromptText` sans validateur : une traduction fautive lève `KeyError` à `prompts/get` | patch |
| BH15/VG1 | `max_calls`, `second_tool`, `cut` jamais testés ; le test « borne » finit en `refused` | medium | `FakeEngine` répète sa dernière sortie (`fake_engine.py:50`) ; aucun assert sur ces issues | patch |
| BH15b | Refus `missing_argument`, `question_with_prompt`, `of_unknown`, échec `provider` non testés | low | les trois refus sont exercés par `test_resource_and_prompt_then_sent_to_the_model:489-571` sans vérifier le texte ; `provider` couvert par E2E seulement | reject |
| BH16 | La route `mcp_lab_call` répète son try/except au lieu du helper | low | `app.py:564-576` | patch |
| BH17 | `handshake_help_text` et `phases.connect.why_text` identiques | low | double maintenance, aucun défaut visible | reject |
| BH18 | Code mort dans `refresh()` | low | sans effet | reject |
| BH19 | `_mcp_lab_kept` et `redraw()` croissent sans borne | low | sessions de démo courtes | reject |
| EC2 | `ask` sur ressource avec `mcp_lab.yaml` devenu invalide → `AssertionError` | low | improbable en séance (connexion refusée sans textes) | reject |
| EC3 | Prompt sans message envoyé au modèle | low | le serveur local renvoie toujours un message ; serveurs publics sans prompts | reject |
| EC5/EC19 | « Arrêter » entre `model_ended` et `tools/call` : l'outil part quand même | medium | aucune lecture de `cancel` avant `_mcp_lab_model_tool` (`app_session.py:10548`) | patch |
| EC6 | « Arrêter » avant l'envoi d'un `tools/call` qui réussit : fin `ok` puis connexion fermée | low | `_mcp_lab_after` ferme sur `cancel` mais garde `status: ok` | patch |
| EC9 | `emit` qui lève avant d'enregistrer la requête en attente | low | `record` avale l'exception ; validation déjà testée | reject |
| EC10 | Listes bornées par `call_timeout` dans `connect_timeout` | false | c'est la règle d'AD-27 (« bornée par `call_timeout`, dans `connect_timeout` ») | reject |
| EC14 | Serveur qui liste zéro outil : `callTool` lève `TypeError` | low | `connect.tools = []` passe le garde (`mcp.js:1629`), `tool.tool` sur `undefined` | patch |
| EC16 | `refreshAsk` peut écraser un état de session plus récent | low | fenêtre de course minime, état corrigé au `session_state` suivant | reject |
| EC17 | `panes.js` : masquer le volet en focus laisse une page vide | false | comportement identique à `app.js` à `98014e6` (`hidePane` ne touchait pas `focusedPane`) : pas une régression | reject |
| VG2 | Restauration de l'état moteur et cause `mcp_lab` non testées | medium | aucun test `restores` / `prefix_not_reused` après un `ask` (modèle : `test_llm_lab.py:374-416`) | patch |
| VG3 | `doc_mode` de la route `mcp_lab_ask` non vérifié | low | seul l'appel direct à la session teste `lazy` | patch |
| VG4 | Le test « serveur perdu » accepte l'une ou l'autre fin selon la course | medium (non vérifié) | rendre la course déterministe exige un point d'accroche dans la tâche de connexion | defer |
| VG5 | Repli « une fin vient toujours » jamais exercé | low | aucun test n'invalide une fin | patch |
| VG6 | Côté page, « Liste en échec » et « Fenêtre dépassée » jamais pilotés en E2E | medium | `_mcp_fake_session` sans `list_errors` ni `ask` | patch |
| VG7 | Règle « aucune règle `pane-*` hors de `pages.css` » non gardée ; `app.css` surcharge encore `.pane-chip` et `.pane-text-action` | medium | spec, Never ; `app.css:146,374,384,2546` | patch |
| V1 | Le cadre de l'hôte déborde de la bande Architecture (coupé en bas à 1280×650 et 1600×1000) | medium | captures de la vérification visuelle | patch |
| V2 | Les lignes de vie barrent les légendes des flèches | low | EXPERIENCE : lignes de vie interrompues sous une flèche qui les traverse | patch |
| V3 | En projection, les boutons ⛶ et — du volet Serveurs sont coupés | low | capture `02-projection-1280` | patch |
| V4 | « Avant MCP » rendu en liste, sans zones, cadre d'hôte ni connecteurs ●◆▲ ; « Avec MCP » sans prise 🔌 | medium | EXPERIENCE, Volet Architecture, « Avant MCP \| Avec MCP » ; DESIGN `mcp-arch-before` | patch |

## Design Notes

- **Pas.** `mcp{n}` porte `exchange_started` puis son `*_ended` ; un `ask` ouvre `mcp{n}.c{k}` (`model_started/ended` encadrant les `model_call_*` via `scoped(step_id=..., parent_step=mcp{n})`) et `mcp{n}.t1` (`exchange_started{call, by: model}` → `call_ended`). Le `step_id` courant de la `Capture` change à chaque sous-pas.
- **Étapes de la page.** Une fonction pure `frames(envelopes)` construit, dans l'ordre des `seq`, la liste des flèches (capturées, déduites selon la table d'AD-27, fantômes et notes) ; le stepper reçoit les flèches-étapes, la page révèle selon `revealAt`. Direct = `push` à chaque nouvelle flèche ; restitution = `load`.
- **Faux serveur public** (`McpWeb`) : n'annonce que `tools` ; suffisant pour le cas « ⊘ ».

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: propre
- `node --check` sur `diagram.js panes.js app.js mcp.js` -- expected: sans erreur
- `uv run pytest -q` -- expected: tout passe
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only mcp_lab mcp_lab_page panes linked_view themes native_tools` -- expected: 0 FAIL
