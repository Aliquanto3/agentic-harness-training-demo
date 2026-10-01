---
title: 'Tests backend manquants et garde réseau'
type: 'chore'
created: '2026-10-01'
status: 'done'
baseline_commit: 'd0da6435f3dffa6bd389cc201db53ef95e07f0da'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/triage.md'
warnings: []
deferred: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

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

</frozen-after-approval>

## Code Map

- `src/wavestack/net/guard.py` -- `install()` → `hook(event, args)` : `socket.getaddrinfo` passe par `check_host`, `socket.connect` par la règle « IP résolue pour un hôte permis, ou hôte permis » (`_resolved`, `is_host_allowed`). Garder intacts les ajouts de la story 1e (`_confiscate_proxies`, `office_proxies`, `_proxy_hosts`). Événements d'audit Python : `socket.gethostbyname(hostname)`, `socket.gethostbyname_ex(hostname)`, `socket.sendto(self, address)`.
- `tests/test_net_guard.py` -- `_run_guarded(body)` exécute un corps dans un processus enfant sous la garde (`allowed = fr.wikipedia.org, huggingface.co, *.hf.co`), aides `refused`, `connect`; liste paramétrée de `test_guard_connect_filter` à compléter. Le processus pytest a lui-même la garde (boucle locale seule, `conftest._network_guard`).
- `src/wavestack/bricks/registry.py` -- `BRICKS` : `tools`, `mcp`, `skills`, `subagent` déclarent `capabilities=["tool_call_parser"]`, `reasoning` déclare `capabilities=["reasoning"]` ; aucune brique n'a de `requires`.
- `src/wavestack/session/app_session.py` -- `_availability` / `_capability_reason` (point unique AD-12) ; `_hook` recopie les arguments modifiés dans le résultat `ask_human` (`replace(result, arguments=call.arguments …)`) ; `_apply_audit` n'émet `effect_applied` (curseur de H2) qu'après une écriture réussie. Ne pas modifier.
- `src/wavestack/hooks.py` -- `audit` (H2) reprend après le dernier `effect_applied` de `file.audit`.
- `src/wavestack/models/engine.py` -- `LlamaCppEngine.complete` (EOG, `count >= max_tokens`, `cut_stop`, `cancel.cancelled`, décodeur UTF-8 incrémental) ; attributs `_lib`, `_llm`, `_tokenizer`, `_last_evaluated`. Ne pas modifier.
- `tests/fake_engine.py` (`FakeEngine`, `CHATML`, `booted_session`), `tests/test_tools.py` (`QWEN`, `call`, fixture `web`), `tests/test_hooks.py` (`hooks_session`, `fake_hooks`, `run_asked`, `answer`, `audit_lines`, `HOLIDAYS`), `tests/test_model_switch.py` (`_booted`, `_switch`, `_events`) -- aides à réutiliser.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer les sept entrées (E008 l. 34, E013 l. 57, E022 l. 98, E025 l. 110, E027 l. 119, E056 l. 244, E066 l. 289).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/net/guard.py` -- `hook` : `socket.gethostbyname` et `socket.gethostbyname_ex` → `check_host(args[0])` ; `socket.sendto` → même règle que `socket.connect` sur `args[1]` (factoriser) ; docstring du module à jour -- E013.
- [x] `tests/test_net_guard.py` -- cas paramétrés : `gethostbyname`/`gethostbyname_ex` d'un hôte hors liste refusés (`net.host_refused`), d'un hôte permis ou de `localhost` acceptés ; `sendto` UDP vers `203.0.113.5` ou vers un nom hors liste refusé (`net.address_refused`), vers `127.0.0.1` envoyé et reçu -- E013.
- [x] `tests/test_llama_engine.py` (nouveau) -- les cinq comportements de `LlamaCppEngine.complete`, joués sur deux moteurs par une fixture paramétrée : `gguf` (marqué `model`, sauté sans `WAVESTACK_TEST_GGUF`, échantillonnage glouton) et `stub` (vrai `complete` sur un faux `llama_cpp` scripté) -- E008.
- [x] `tests/test_bricks.py` -- test paramétré sur `skills`, `tools`, `mcp`, `subagent` des vraies `BRICKS`, modèle `FakeEngine()` sans analyseur : indisponible, raison « l'appel d'outils » -- E022.
- [x] `tests/test_hooks.py` -- H2 : échec ponctuel injecté sur la première écriture (`config.audit_path` pointé sur un dossier le temps d'un appel de `_apply_audit`), puis quatre lignes dans l'ordre, une seule erreur tracée -- E025 ; hook `before_tool` qui modifie `year` + H5 + `public_holidays` : aperçu, `outbound_request` et requête envoyée portent `year` modifié -- E027.
- [x] `tests/test_model_switch.py` -- Raisonnement voulue sur A (CHATML) : indisponible avec la raison ; passage à chaud vers B (gabarit Qwen) : disponible, carte `wanted` et `available`, réserve de raisonnement dans l'aperçu ; aucun `set_brick` entre les deux -- E056, E066.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- ligne `closed:` sur les sept entrées.

**Acceptance Criteria:**
- Given chaque test ajouté, when la mutation de son entrée est appliquée à la main, then il échoue ; défaite, il passe (consigné dans Implementation Notes).
- Given aucun `WAVESTACK_TEST_GGUF`, when on lance `tests/test_llama_engine.py`, then les cas `stub` passent et les cas `gguf` ne sont pas collectés (`-m 'not model'`) ou sont sautés.
- Given la garde installée, when un hôte permis est résolu par `gethostbyname`, then aucun refus (pas de régression sur les clients qui résolvent ainsi un hôte de la liste).

## Design Notes

E008 : la fixture `stub` construit un `LlamaCppEngine` par `__new__` et lui donne un faux `_llm.generate` (jetons scriptés selon l'invite), un faux `_tokenizer` (`is_eog`, `token_pieces`) et un faux `_lib` (`llama_perf_context*`). Seul le vrai `complete` est exercé, et chaque mutation se vérifie sans GGUF. Les tests ne dépendent pas du texte produit : la séquence d'arrêt est tirée d'un premier passage de référence (deux tokens consécutifs, première occurrence au début du premier), le reste se mesure (nombre de tokens, `token_id` EOG, `piece` incomplète seule).

E013 : un nom passé à `sendto` (résolu en C, sans `getaddrinfo`) suit la règle de `connect` : refusé s'il n'est pas permis. `gethostbyname` d'un hôte permis n'ajoute pas ses IP à `_resolved` : un `connect` à cette IP reste refusé (sens sûr, consigné en ponytail).

## Verification

**Commands:**
- `uv run ruff check <fichiers touchés>` et `uv run ruff format --check <fichiers touchés>` -- expected: aucun écart.
- `uv run pytest -q tests/test_net_guard.py tests/test_llama_engine.py` puis `tests/test_bricks.py`, `tests/test_hooks.py`, `tests/test_model_switch.py`, l'un après l'autre -- expected: tout passe, le test `model` désélectionné.

## Implementation Notes

- Implémenté directement par l'agent de la story, sans sous-agent : la nuit, un autre agent tourne sur le même PC de 16 Go, et les règles du mode nuit (pas de réseau, pas de modèle, fichiers de tests touchés seulement) ne pouvaient pas passer par le seul texte de la spec.
- E013 : `gethostbyname_ex` lève l'événement `socket.gethostbyname` (vérifié sous Python 3.13.5) ; il n'existe pas d'événement `socket.gethostbyname_ex`. `sendto` reçoit un nom déjà résolu en C avant l'événement : le test n'envoie que des IP en vrai, le cas « nom hors liste » passe par `sys.audit`. Les cas hors liste ajoutent après la garde un hook qui arrête l'appel à l'événement : sous une régression, rien ne part. ARCHITECTURE-SPINE (AD-15) mis à jour : quatre événements.
- E008 : nouveau fichier `tests/test_llama_engine.py` plutôt que `test_render_reference.py` (celui-ci porte le rendu AD-4). La fixture `stub` bâtit un `LlamaCppEngine` par `__new__` avec un faux `_llm.generate`, `_tokenizer` et `_lib` : le vrai `complete` tourne sans modèle, ce qui permet de vérifier les mutations. Les cas `gguf` sont désélectionnés par défaut (`-m 'not model'`) et sautés sans `WAVESTACK_TEST_GGUF` (vérifié avec `-m model`) ; jamais lancés sur un vrai GGUF.
- E027 : `public_holidays` attend un entier ; un hook qui passerait `"2027"` ferait échouer H5 (`TypeError` hors `ToolError`), tracé comme hook en échec. Le test passe `2027`.
- Mutations appliquées à la main puis défaites (chaque fois : le test visé échoue, les autres passent ; défaite, tout passe) :
  - E013 : `_RESOLVE_EVENTS`/`_SEND_EVENTS` ramenés à `getaddrinfo`/`connect` → `gethostbyname-off-list` et `sendto-off-list` échouent.
  - E022 : `capabilities=[]` sur les quatre déclarations → les quatre paramètres échouent.
  - E025 : `effect_applied` émis aussi sur échec d'écriture (curseur avancé) → le test H2 échoue (deux lignes perdues).
  - E027 : `return hook.id, result` sans `replace` → l'envoi part avec `2026`, l'aperçu dit `2027`.
  - E056/E066 : `capabilities=[]` sur `reasoning` → échec dès le modèle A ; `self._wanted.discard(...)` dans `_capability_reason` → échec après le passage à B (`wanted` False).
  - E008 (`stub`) : sans arrêt sur EOG ; `count > max_tokens` ; préfixe d'arrêt non retenu (`emit + pending`) ; séquence d'arrêt émise avec le dernier fragment ; sans test d'annulation ; décodage morceau par morceau (`piece.decode("utf-8", "replace")`) → chaque fois le seul test du comportement échoue.
- Incident pendant la vérification de la mutation E013 : la première version du test appelait le vrai `gethostbyname("example.org")` et `sendto` vers `203.0.113.5` ; sous la mutation, la garde les a laissés passer, d'où une requête DNS pour `example.org` et un datagramme UDP vers une adresse de documentation (TEST-NET-3, non routée). Corrigé aussitôt par le hook d'arrêt ci-dessus, la seconde vérification n'a rien fait sortir.

## Spec Change Log

- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : point d'arrêt 1 (spec) — « Approve and continue », spec conforme au SPEC et au triage (E008, E013, E022, E025, E027, E056, E066) ; aucune question ouverte, taille sous le seuil de 4000 tokens.

## Review Triage Log

Passe 1 (Blind Hunter BH, Edge Case Hunter EC, Verification Gap VG), 2026-10-01.

| # | Constat | Verdict | Preuve | Suite |
|---|---------|---------|--------|-------|
| BH1 / VG1 | Le test EOG `stub` passe si `break` devient `continue` (le script finit avant `max_tokens`, `stop` par défaut). | medium | Reproduit par VG ; le script `short` s'arrêtait 3 tokens après EOG. | patch : script prolongé de 300 tokens après EOG ; la mutation `continue` donne `length`, le test échoue (vérifié). |
| BH2 / EC1 | `socket.sendmsg` (UDP, POSIX) n'est pas filtré. | medium | CPython lève `socket.sendmsg(self, address)` ; même trou que celui que nomme E013. | patch : ajouté à `_SEND_EVENTS`, cas `sys.audit` hors liste refusé, adresse `None` acceptée ; mutation vérifiée. |
| BH3 / EC2 | `gethostbyaddr` et `getnameinfo` ne sont pas filtrés. | medium | Événements distincts, absents de `_RESOLVE_EVENTS` ; préexistant, hors des trois événements de l'intention. | defer (`deferred-work.md`). |
| BH4 / EC3 | La docstring tait que la requête DNS d'un nom passé à `connect`/`sendto` part avant le refus. | low | `getsockaddrarg` résout avant `PySys_Audit` ; la fuite est préexistante pour `connect`. | patch : docstring et AD-15 reformulés ; la fuite elle-même en defer. |
| BH5 | Le compromis « `gethostbyname` ne note pas d'adresse » n'est que dans un commentaire. | low | Vrai ; sens sûr (refus). | patch léger : une phrase dans AD-15 ; pas de test dédié (rejet de cette partie : ajout de test pour un cas que rien n'atteint). |
| BH6 / EC6 | E008 fermée sans passage sur un vrai GGUF ; cas multi-octets `gguf` qui échoue au lieu de sauter, `max_tokens=64` serré. | low | L'intention gelée demande un test `model` jamais lancé sans accord d'Anaël et ferme E008 ; la clôture le dit. Le cas `gguf` sans caractère coupé dépend du vocabulaire, pas du moteur. | patch : `pytest.skip` pour un GGUF sans caractère coupé (le `stub` échoue toujours), `max_tokens=256`. Clôture gardée. |
| BH7 | Le test de séquence d'arrêt n'essaie pas un faux préfixe relâché. | low | `test_turn.py::test_cut_stop_never_leaks_a_stop_prefix` ne couvre pas la libération non plus. | patch : seconde séquence d'arrêt jamais atteinte (`texts[0] + "\x00"`) ; mutation « texte retenu perdu » vérifiée. |
| BH8 | Le test Raisonnement ne distingue pas « voulue » de « effective » pour la réserve. | medium | Avant le passage, aucune assertion sur la réserve ; une réserve calculée sur `wanted` passait. | patch : réserve 512 sur A, 1 536 sur B ; mutation `"reasoning" in self._wanted` dans `_reasoning_on` vérifiée. |
| BH9 | `_REFUSED_KEY` mal nommé, aides en double avec `_CHILD_PREAMBLE`. | low | Nom trompeur réel ; le doublon ne casse rien. | patch : renommé `_REFUSAL_HELPERS` ; fusion rejetée (refactor sans gain). |
| EC4 | GGUF sans gabarit de chat : invite vide. | false | Les tests `model` existants exigent un GGUF de chat (`incompatible_reason is None`) ; un GGUF sans gabarit n'est pas un sujet valide. | rejet. |
| EC5 | Invite `long` sans BOS. | maybe-false | Dépend du modèle (Qwen n'ajoute pas de BOS) ; au pire, faux échec d'un test opt-in : serait `low`. | rejet (low non vérifié). |
| EC7 | Le modèle réel n'atteint pas EOG en 256 tokens. | maybe-false | Invite « oui » sans raisonnement ; au pire, faux échec d'un test opt-in : `low`. | rejet. |
| EC8 | Second passage glouton après réutilisation du cache : sortie différente. | maybe-false | Il faudrait un passage sur un vrai GGUF ; au pire, faux échec opt-in : `low`. | rejet ; à surveiller au premier passage `model`. |
| EC9 | `_events(0, …)[-1]` lit tout le journal. | false | `set_brick` émet toujours `bricks_changed` (la mutation `wanted` le confirme) ; remplacé par une marque avec BH8. | rejet (corrigé au passage). |
