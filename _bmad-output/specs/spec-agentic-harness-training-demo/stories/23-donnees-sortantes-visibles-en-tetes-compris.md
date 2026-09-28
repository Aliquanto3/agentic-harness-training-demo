---
title: 'Données sortantes visibles, en-têtes compris'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_revision: 'f5f35230567c87be63f3cc7d89aaaa8de333dca5'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/33-contrastes-et-code-couleur-par-discipline.md'
warnings: ['oversized']
deferred:
  - summary: >-
      Secrets éventuels dans l'URL tracée (userinfo, paramètre de requête) non masqués.
    evidence: |-
      Seuls les en-têtes sont masqués ; aucun chemin actuel ne met de clé dans l'URL. Vérifier si un fournisseur ou un téléchargement l'exige.
    location: >-
      src/wavestack/net/factory.py (_check_and_trace)
    severity: medium (unverified)
  - summary: >-
      Logique de visibilité d'Orchestration recopiée dans revealOutbound et shownConnections.
    evidence: |-
      renderSteps et shownConnections filtrent les connexions par deux expressions différentes ; le gel de la vue recopie toggleStep.
    severity: low
  - summary: >-
      Masquage non testé pour les origines download et diagnostic.
    evidence: |-
      Même crochet _check_and_trace pour toutes les origines ; seuls brick et model ont un test.
    severity: medium (unverified)
  - summary: >-
      Vérifications de masquage inégales entre test_net_factory et test_cloud (constante en dur, journal non parcouru en entier).
    evidence: |-
      Une aide commune sur get_journal().all_events() alignerait les deux suites sur le critère « dans aucun événement ».
    severity: low
  - summary: >-
      Rendu d'une valeur masquée (.outbound-masked et son infobulle) non vérifié en E2E.
    evidence: |-
      La pile E2E n'a aucune requête tracée portant un en-tête non public ; il faudrait un faux serveur MCP joignable hors boucle locale.
    severity: low
---

<intent-contract>

## Intent

**Problem:** La recette du palier 2 a échoué sur deux tests. En C3, `outbound_request` ne porte que `method`, `url` et `body` : aucun en-tête n'apparaît, donc pas le User-Agent qui transporte le contact `[net] contact`. En M2, l'utilisateur ne trouve pas où lire les données sortantes : le bloc est enfoui dans une étape repliée, son libellé est « 🌐 RÉSEAU » et non « Données sortantes », et rien n'y mène depuis la carte Outils ni depuis le schéma.

**Approach:** La fabrique `net` ajoute à `outbound_request` la liste des en-têtes envoyés. Une liste blanche fermée laisse en clair les en-têtes publics. Tout autre en-tête garde son nom, mais sa valeur devient « [masqué] » avant l'émission : elle n'entre jamais dans le journal. L'interface ne fait que mettre en forme. Le bloc « 🌐 Données sortantes » d'une étape d'outil réseau ou MCP affiche la méthode, l'URL, les en-têtes et le corps. Un clic sur le nœud réseau du schéma déplie ce bloc. Les cartes Outils et MCP disent ce qui sort du poste et où le lire, avec un texte construit par la session.

## Boundaries & Constraints

**Always:**
- AD-2 / AD-1 : la session fixe les en-têtes et le masquage. L'interface ne recalcule ni ne filtre rien. Le texte des cartes est construit par la session à partir de `content/bricks/*.yaml` (AD-19).
- AD-15 / AD-20 / NFR-4 : aucune valeur d'en-tête hors liste blanche n'est émise, que ce soit la clé cloud, un cookie, `Proxy-Authorization`, `Mcp-Session-Id` ou un en-tête inconnu. Le masquage se fait dans `_check_and_trace`, avant `emit`, pour les quatre origines tracées : `brick`, `diagnostic`, `download` et `model`.
- Les en-têtes sont tracés dans l'ordre et avec la casse d'envoi (`request.headers.raw`, décodés en latin-1). Chaque redirection trace les en-têtes de son propre saut.
- Les requêtes vers un modèle cloud restent tracées comme aujourd'hui (corps exact, `origin: model`, `call_id`). Elles gagnent leurs en-têtes, avec l'en-tête d'authentification à « [masqué] ». Rien ne change dans leur rendu.
- Pour le front, le Code Map s'appuie sur les noms de fonctions (story 33 en cours : les numéros de ligne bougent). Le CSS n'emploie que des variables, car story 33 interdit `#hex`, `rgb(` et `hsl(` dans `app.css` et `app.js`.
- Aucune dépendance nouvelle. Aucun vrai modèle ni réseau réel dans le conteneur : `httpx.MockTransport`, faux fournisseur cloud de `tests/test_cloud.py` et réseau coupé par le lanceur E2E (`tools/e2e/stack.py`, `closed_port`).
- Aucune story livrée ne casse : `pytest` complet vert. EXPERIENCE.md, DESIGN.md, SPEC.md et ARCHITECTURE-SPINE.md sont mis à jour là où le comportement décrit change.

**Never:**
- Pas de liste noire seule : le nom de l'en-tête de clé est configurable (`AuthHeader.name`, `config.py`).
- Pas d'en-têtes dans l'aperçu H5 (`ApprovalPreview`) : ils sont posés par le client HTTP à l'envoi.
- Pas de nouveau bloc pour l'appel au modèle cloud dans Orchestration : le corps reste dans Contexte LLM et l'événement dans le journal.
- Pas de bilan des sorties du tour ni de vue liée au survol : c'est la story 34.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Outil réseau | `public_holidays(year=2026)` | `headers` contient `Host`, `Accept: */*`, `Accept-Encoding`, `Connection` et `User-Agent: WaveStack/0.1 (demonstrateur pedagogique; <contact>)`, en clair, `masked: false` | — |
| POST avec corps | `client.post(..., content=b'{"q":1}', headers={"Content-Type": "application/json"})` | `Content-Type` et `Content-Length` en clair | — |
| Clé cloud | `Authorization: Bearer <SENTINEL>` (ou `x-api-key`, nom configurable) | `{"name": "Authorization", "value": "[masqué]", "masked": true}` ; ni la clé ni ses 4 premiers ou derniers caractères dans le journal | — |
| Secrets divers | `Cookie`, `Proxy-Authorization`, `Mcp-Session-Id`, `X-Custom` | nom gardé, valeur « [masqué] » | — |
| Loopback / hôte refusé | `127.0.0.1` / `example.com` | inchangé : rien de tracé | `NetworkBlocked` pour l'hôte refusé |
| Clic nœud réseau contacté | nœud « Wikipédia » après un tour | Orchestration montrée si masquée, tour et étape dépliés, vue figée, bloc ouvert et amené à l'écran | — |
| Clic nœud non contacté | aucune étape avec sortie pour ce composant | sélection seule, comme aujourd'hui ; l'infobulle dit « Non contacté » | — |

</intent-contract>

## Code Map

- `src/wavestack/net/factory.py:29-50` -- `user_agent()` et `_check_and_trace` : c'est le seul point d'émission. On y ajoute `"headers": _headers(request)`. Les trois clients posent déjà `User-Agent` (l. 86, 110, 137). Le client loopback n'est jamais tracé.
- `src/wavestack/trace/catalog.py:33-37` -- `OutboundRequestPayload` : y ajouter `headers: list[OutboundHeader] = []`. `ApprovalPreview` (l. 496-501) reste inchangé. `BrickState` (l. 331-363) gagne `outbound_fr: str | None = None`.
- `src/wavestack/models/openai_chat.py:256-264` -- `complete` pose `Content-Type` et `entry.auth_header.name`. Le masquage générique suffit. `mask_key` (l. 100) sert aux messages, pas aux en-têtes.
- `src/wavestack/bricks/contract.py:40-46` -- `BrickContent` : ajouter `outbound_fr: str | None = None`, un gabarit à `{tools}` et `{servers}`.
- `src/wavestack/session/app_session.py` -- `_tool_options` (outils avec `spec.network`), `_mcp_options` (`server.network`), `_mcp_label` et `_emit_bricks`, où ajouter `outbound_fr` aux cartes `tools` et `mcp`. Story 33 modifie aussi `_emit_bricks` : il faut s'ancrer sur le symbole.
- `content/bricks/tools.yaml`, `content/bricks/mcp.yaml` -- le texte `outbound_fr` en français.
- `src/wavestack/web/static/app.js`, par symbole :
  - `outbound_request` est rattaché dans le réducteur principal (`case "outbound_request"`, étape `tool` du tour ou connexion MCP hors tour) et dans le réducteur du sous-agent (même `case`, `last("tool")`), `origin === "brick"` seulement. Il faut ajouter `component: envelope.component` à l'entrée poussée.
  - `outboundPayload(request, openSet)` est appelé par `toolBody`, `connectBody`, `approvalCard` et `approvalTrace` (aperçu H5, sans `headers`).
  - `turnRows` (ligne `tool`, `net: hostOf(...)`), `connectRow` (clé `mcp:${seq}`), `renderSteps`, `toggleStep`, `stepNode`, `railNodes` et `store.orch` (`live`, `userOpen`, `turnOpen`, `prepOpen`, `prepGroupOpen`, `selected`), `store.closedPayloads`.
  - `schemaNode` (précédent : `file.audit` et `file.memory` ajoutent un écouteur de clic), `schemaButton` et `select`, `showPane`, `store.hiddenPanes`.
  - `renderBricks` (carte : `brick-note`, `brick-limits`) et `brickOptions` (sous-options, étiquette `hosting-tag-network`).
  - `KIND_LABELS.outbound_request` (« Données sortantes ») et `eventSummary`. `logRow` montre le JSON brut, en-têtes compris, sans changement.
- `src/wavestack/web/static/app.css` -- `.outbound-payload`, `.outbound-head`, `.outbound-tag` : ajouter le libellé, la section En-têtes et la valeur masquée, avec des variables seulement.
- `tests/test_net_factory.py:48-61, 145-159` -- deux égalités strictes de `payload` à étendre. `tests/test_tools.py:~508` (public_holidays), `tests/test_cloud.py:~118-140` (Groq, `SENTINEL`, `_no_sentinel`, `_journal_text`), `tests/test_bricks.py` (cartes).
- `tools/e2e/run_e2e.py` -- `s_network_tools` (réseau coupé : la requête est tracée puis échoue) et `s_data_flows` (data.gouv.fr hors tour). `schema_fits` et `r.shot` aussi. `tools/e2e/README.md` décrit les scénarios.

## Tasks & Acceptance

**Execution:**
1. `src/wavestack/trace/catalog.py` -- Ajouter `OutboundHeader{name: str, value: str, masked: bool = False}`, puis `OutboundRequestPayload.headers: list[OutboundHeader] = []` et `BrickState.outbound_fr: str | None = None`. Raison : AD-2, le catalogue porte la forme.
2. `src/wavestack/net/factory.py` -- Ajouter la constante `PUBLIC_HEADERS` (noms en minuscules : `host`, `accept`, `accept-encoding`, `accept-language`, `cache-control`, `connection`, `content-length`, `content-type`, `last-event-id`, `mcp-protocol-version`, `user-agent`), la constante `MASKED = "[masqué]"` et `_headers(request)` : ordre et casse de `request.headers.raw`, valeur remplacée hors liste. Appeler `_headers` dans `_check_and_trace`, et mettre à jour la docstring du module. Raison : AD-15 et AD-20, masquer avant l'émission.
3. `tests/test_net_factory.py` -- Étendre les deux égalités strictes. Ajouter : en-têtes présents dans l'ordre d'envoi, `User-Agent` avec contact ; `Authorization`, `x-api-key`, `Cookie`, `Proxy-Authorization`, `Mcp-Session-Id` et un en-tête inconnu à « [masqué] », la valeur secrète absente de `model_dump_json()` du journal ; client async (httpx2) idem ; saut de redirection avec ses en-têtes. Raison : couvrir la matrice.
4. `tests/test_tools.py`, `tests/test_cloud.py` -- `public_holidays` : `headers` contient `User-Agent` avec `DEFAULT_NET_CONTACT` et `Accept`. Groq : l'en-tête d'authentification tracé vaut « [masqué] », `Content-Type: application/json` est en clair, et `_no_sentinel` passe sur le journal. Raison : le parcours réel des outils et du cloud.
5. `src/wavestack/bricks/contract.py`, `content/bricks/tools.yaml`, `content/bricks/mcp.yaml`, `src/wavestack/session/app_session.py` -- Ajouter `outbound_fr` au contenu. Dans `_emit_bricks`, le remplir pour `tools` (libellés des outils `network`, dans l'ordre du registre, et libellés des serveurs MCP `network`) et pour `mcp` (serveurs publics). Textes : voir Design Notes. Raison : point (3), texte par la session (AD-1, AD-19).
6. `tests/test_bricks.py` -- La carte `tools` a un `outbound_fr` qui contient « Jours fériés », « Résumé Wikipédia », « Lecture de page web », les libellés de data.gouv.fr et de Microsoft Learn, et « Données sortantes ». La carte `mcp` nomme ses serveurs publics et pas « Glossaire WaveStack ». Une carte sans réseau (`skills`) a `outbound_fr is None`. Raison : garder la liste juste.
7. `src/wavestack/web/static/app.js` -- Dans les deux `case "outbound_request"`, pousser aussi `component: envelope.component`. Réécrire `outboundPayload`, sans changer sa signature ni son ouverture (ouvert par défaut dans la trace, replié dans H5). L'en-tête `summary` reprend l'étiquette « 🌐 RÉSEAU », puis le libellé constant « Données sortantes », puis `${method} ${url}`. Le corps contient des sections libellées « Requête » (`METHOD URL`), « En-têtes » (un `pre` `Nom: valeur` par ligne, la valeur masquée dans un `span.outbound-masked` avec l'infobulle « Valeur masquée par le harnais : jamais écrite dans le journal ») et « Corps » (texte actuel, ou « Aucun corps : seule l'adresse sort du poste. »). Sans `headers` (aperçu H5), la section En-têtes affiche la note « Posés par le client HTTP à l'envoi (User-Agent, Accept…) : visibles dans les données sortantes de l'étape de l'outil. » Dans `renderBricks`, afficher `brick.outbound_fr` en `p.brick-outbound`, carte repliée comprise. Raison : points (2) et (3).
8. `src/wavestack/web/static/app.js` -- Dans `turnRows` et `connectRow`, ajouter `outbound: step.outbound || []` à la ligne. Nouvelle fonction `revealOutbound(componentId)` : chercher dans `shownTurns()` (via `turnRows`, sous-agent compris) puis dans les connexions visibles (`store.offTurn`, `connectRow`) la dernière ligne dont une entrée `outbound` a ce `component`. Si aucune ligne ne correspond, ne rien faire. Sinon : `showPane("orch")` si l'Orchestration est masquée, tour ouvert (`turnOpen`) ou `prepGroupOpen` et `prepOpen`, et vue figée comme `toggleStep` (`live = false`, `userOpen.add`, `selected`). Retirer ses `seq` de `store.closedPayloads`, appeler `renderSteps()`, puis faire défiler (`scrollIntoView({block: "nearest"})`) jusqu'au premier `.outbound-payload` de `railNodes.get(key)`. Dans `schemaNode`, pour un nœud `network` de forme `tool` ou `mcp`, ajouter un écouteur de clic qui appelle `revealOutbound(node.id)` quand `store.selection === node.id`, et ajouter à l'infobulle d'un nœud contacté « Clic : ses données sortantes dans Orchestration ». Raison : « le nœud réseau du schéma y mène ».
9. `src/wavestack/web/static/app.css` -- Ajouter `.outbound-label` (gras), `.outbound-section` (libellé en `typography.label`), `.outbound-masked` (italique, `ink-soft`, fond `surface`), `.brick-outbound`, et des retours à la ligne pour les longs en-têtes (`white-space: pre-wrap; overflow-wrap: anywhere`). Uniquement des variables `tokens.css`. Raison : DESIGN.md et la règle de story 33.
10. `tools/e2e/run_e2e.py`, `tools/e2e/README.md` -- Dans `s_network_tools`, après le tour Wikipédia : cliquer le nœud « Wikipédia » du schéma (`.arch-zone-network .arch-node`), puis vérifier les critères d'acceptation du bloc. Après le tour `public_holidays` : déplier l'étape « Exécution · Jours fériés » et vérifier le même bloc. Vérifier la carte Outils. Ajouter la capture `08b-donnees-sortantes-en-tetes`. Dans `s_data_flows`, déplier la connexion data.gouv.fr de la préparation et vérifier son bloc (User-Agent). Mettre à jour le README. Raison : point de la recette C3/M2, et item 43 de `deferred-work.md` (rendu 5b non testé).
11. Docs -- Mettre à jour les documents suivants.
    - EXPERIENCE.md : ligne `outbound-payload` (libellé, en-têtes, masquage, note H5), « Franchir la frontière se voit » (le clic sur le nœud réseau mène au bloc), et la carte de brique (ligne « Sort du poste »).
    - DESIGN.md : composant `outbound-payload` (sections, valeur masquée).
    - ARCHITECTURE-SPINE.md : AD-2 (`outbound_request{origin, method, url, headers, body}`), AD-15 (en-têtes en liste blanche, les autres « [masqué] » avant l'émission).
    - SPEC.md : dans le succès de CAP-14, les cartes disent où lire les données sortantes ; dans CAP-23, adresse, en-têtes (secrets masqués) et données.

**Acceptance Criteria:**
- Given le scénario E2E `network_tools` (réseau coupé par le lanceur) et le tour « Résume l'article Wikipédia sur le Mont-Saint-Michel. », when on clique le nœud « Wikipédia » du schéma, then l'étape « Exécution · Résumé Wikipédia » est dépliée dans Orchestration. Son `.outbound-payload` est ouvert, dans la zone visible de `#orch-scroll`, et contient « Données sortantes », « GET https://fr.wikipedia.org/api/rest_v1/page/summary/… », « En-têtes », « User-Agent: WaveStack/0.1 (demonstrateur pedagogique; » et « Accept: */* ».
- Given le tour « Quels sont les jours fériés en France cette année ? », when on déplie l'étape « Exécution · Jours fériés », then son bloc « Données sortantes » affiche l'URL calendrier.api.gouv.fr, le User-Agent avec contact et « Aucun corps : seule l'adresse sort du poste. ». Dans l'événement `outbound_request` lu par `/api/state` ou le flux, `headers` contient `User-Agent`, et aucune entrée n'a `masked: true`.
- Given le panneau des briques du scénario `network_tools`, when on lit la carte Outils sans déplier ses options, then `.brick-outbound` nomme « Jours fériés », « Résumé Wikipédia », « Lecture de page web », les serveurs MCP publics et « Données sortantes ».
- Given un tour Groq (faux fournisseur, clé `SENTINEL`), when on lit le journal, then chaque `outbound_request{origin: model}` a `Authorization` à « [masqué] » avec `masked: true`, et ni la clé ni ses fragments n'apparaissent dans aucun événement.
- Given une validation H5 en attente, when on lit sa carte, then l'aperçu garde méthode, URL et corps, avec la note sur les en-têtes posés à l'envoi. Les E2E existants de `s_h5` restent verts.

## Spec Change Log

## Review Triage Log

### 2026-09-28 — Review pass
- verdicts: 25 findings — high 0, medium 3, low 18, false 1, maybe-false 3 (écarts d'interprétation de l'auditeur d'intention consignés à part : masquage plus strict que « non secrets », clic sur le nœud plutôt que sur le flux — rejetés, conformes aux décisions par défaut)
- findings:
  - `[low]` `[patch]` (blind) liste d'en-têtes vide affichée « Aucun en-tête » pour un événement antérieur — « En-têtes non tracés pour cet événement ».
  - `[low]` `[patch]` (blind) `last-event-id` en clair alors que `Mcp-Session-Id` est masqué — retiré de la liste blanche.
  - `[low]` `[patch]` (blind + edge) en-têtes ajoutés par le transport (proxy) absents de la trace, contrairement à « exactement envoyés » — limite écrite dans EXPERIENCE/DESIGN.
  - `[maybe-false]` `[defer]` (blind) secrets possibles dans l'URL (userinfo, `?api_key=`) — aucun chemin actuel ne met de clé dans l'URL ; à vérifier si un fournisseur l'exige (medium si vrai).
  - `[low]` `[patch]` (blind + edge + vérif.) infobulle « Clic : ses données sortantes » alors que rien n'est révélable — infobulle seulement si une ligne existe.
  - `[medium]` `[patch]` (blind + edge + intention) clic sur un nœud déjà sélectionné : désélection, aucun dévoilement — un nœud réseau contacté révèle toujours.
  - `[low]` `[defer]` (blind) logique de visibilité recopiée (`shownConnections`, gel de la vue) — factorisation à faire.
  - `[low]` `[patch]` (blind) « Sortent du poste » pour des outils éteints — « Peuvent sortir du poste ».
  - `[medium]` `[patch]` (blind + edge) gabarit `outbound_fr` fautif : disparition silencieuse, ou `AttributeError` qui empêche `bricks_changed` — exceptions élargies, avertissement journalisé, tests.
  - `[low]` `[patch]` (blind) `_join_fr` et cas limites de `_outbound_fr` non testés — tests ajoutés.
  - `[maybe-false]` `[defer]` (blind) masquage non testé pour les origines `download` et `diagnostic` — même crochet `_check_and_trace` pour toutes les origines ; un test par origine lèverait le doute.
  - `[low]` `[patch]` (blind) vérification E2E « non contacté » sautée silencieusement — assertion.
  - `[low]` `[defer]` (blind) vérifications de masquage inégales entre les deux suites (constante en dur, journal non parcouru en entier).
  - `[false]` `[reject]` (blind) méthode et URL répétées dans le résumé et la section Requête — voulu : le résumé se lit replié, la section donne le détail complet.
  - `[low]` `[patch]` (blind) explication de « [masqué] » inaccessible au clavier — note visible sous les en-têtes.
  - `[low]` `[patch]` (edge) note de l'aperçu H5 trompeuse si l'appel est refusé — formulation conditionnelle.
  - `[medium]` `[patch]` (edge) nom d'en-tête d'authentification configuré parmi les en-têtes publics : clé en clair — refus à la lecture de la configuration, test.
  - `[low]` `[patch]` (edge) gel de la vue en direct pour une ligne de connexion — gel seulement pour une étape de tour.
  - `[low]` `[patch]` (edge) l'E2E suppose qu'Échap efface la sélection — rendu caduc par le clic qui révèle toujours.
  - `[low]` `[patch]` (vérif.) dépliage d'un tour replié par le clic non testé — clic sur « Jours fériés » après le tour Wikipédia.
  - `[low]` `[patch]` (vérif.) clic sur un nœud MCP (connexion) non testé — clic sur data.gouv.fr dans `s_data_flows`.
  - `[maybe-false]` `[defer]` (vérif.) rendu `.outbound-masked` non vérifié en E2E — demande un faux serveur MCP joignable hors boucle locale ; ajouté aux vérifications sur PC.
  - `[low]` → regroupé (infobulle, vérif. « Other findings »).
  - `[medium]` → regroupé (nœud déjà sélectionné, intention n° 3).
  - `[low]` → regroupé (proxy, intention n° 7).

## Design Notes

Forme émise (exemple, public_holidays) :

```json
{"origin": "brick", "method": "GET", "url": "https://calendrier.api.gouv.fr/jours-feries/metropole/2026.json",
 "headers": [{"name": "Host", "value": "calendrier.api.gouv.fr", "masked": false},
             {"name": "Accept", "value": "*/*", "masked": false},
             {"name": "User-Agent", "value": "WaveStack/0.1 (demonstrateur pedagogique; …)", "masked": false}],
 "body": ""}
```

Texte des cartes (`content/bricks/*.yaml`, gabarit `outbound_fr`) :
- Outils : « Sortent du poste : {tools}, ainsi que les serveurs MCP publics ({servers}) de la brique MCP. Ce qu'ils envoient (adresse, en-têtes, corps) : volet Orchestration, bloc « 🌐 Données sortantes » de leur étape ; un clic sur leur nœud 🌐 du schéma y mène. »
- MCP : « Sortent du poste : {servers}. Ce qu'ils reçoivent (adresse, en-têtes, corps) : volet Orchestration, bloc « 🌐 Données sortantes » de la connexion et de chaque appel ; un clic sur leur nœud 🌐 du schéma y mène. »

Liste blanche plutôt que liste noire : une entrée cloud peut déclarer n'importe quel nom d'en-tête de clé. Un en-tête inattendu masqué reste visible par son nom, ce qui suffit à la pédagogie. Une clé en clair serait une fuite.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun défaut
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, les nouveaux tests compris
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; captures de `tools/e2e/screenshots` mises à jour (`08-outils-reseau-echec-explique`, `08b-donnees-sortantes-en-tetes`, `15-ou-vont-mes-donnees-schema`)

**Manual checks (if no CLI):**
- `grep -rn "\[masqué\]" src/wavestack/net/factory.py` : constante unique. Relire que `_headers` est appelé avant `emit`, jamais après.

## Décisions prises par défaut

- **Liste blanche fermée** (11 noms) plutôt qu'une liste noire. Le nom de l'en-tête de clé est configurable (`AuthHeader.name`) : une liste noire laisserait fuir un nom imprévu.
- **`Mcp-Session-Id` masqué.** C'est un identifiant de session émis par le serveur, rejouable. Il vaut mieux le cacher que l'exposer.
- **Forme `list[{name, value, masked}]`**, dans l'ordre et la casse d'envoi. Un dictionnaire perdrait les doublons et l'ordre. `masked` évite que l'interface compare des chaînes (AD-2).
- **`headers = []` par défaut** dans le catalogue, pour que les événements anciens restent valides.
- **Aperçu H5 sans en-têtes.** Ils sont posés par httpx à l'envoi, après la décision. La carte H5 le dit dans une note au lieu de prétendre à une requête complète.
- **Modèle cloud** : en-têtes dans l'événement et dans le journal (clé masquée), sans nouveau bloc dans Orchestration. Le corps reste dans Contexte LLM (point 4 : « gardent leur transparence actuelle »).
- **Résumé du journal inchangé** (`METHOD URL`). Le JSON déplié montre déjà les en-têtes.
- **Clic sur un nœud réseau** : il re-montre Orchestration si le volet est masqué, puis fige la vue comme un clic sur une étape. Sans sortie tracée pour ce nœud, le clic garde la seule sélection. C'est le geste explicite de l'utilisateur, et « Suivre le direct » reste disponible.
- **La carte Outils liste les outils réseau déclarés**, activés ou non, ainsi que les serveurs MCP publics. C'est ce qui peut sortir du poste. L'état d'activation se lit déjà dans les sous-options, et la ligne d'état vient de la story 33.
- **Le libellé du bloc garde « 🌐 RÉSEAU »** (DESIGN.md) et y ajoute « Données sortantes », le nom que cherche l'utilisateur et celui du journal.

## À vérifier sur PC

- **Geste** : sur le PC relié à Internet, dans Chrome puis Edge, lancer `uv run wavestack` (PowerShell), choisir le scénario « Outils réseau » et envoyer « Résume l'article Wikipédia sur le Mont-Saint-Michel. », puis cliquer le nœud 🌐 « Wikipédia » du schéma. — **Attendu** : l'étape se déplie sur « 🌐 RÉSEAU · Données sortantes » avec les en-têtes, et l'outil réussit (pas de 403). — **Critère** : `User-Agent: WaveStack/0.1 (demonstrateur pedagogique; <contact de [net] contact>)` est lisible en entier sans défilement horizontal à 1366 × 768, et le résultat est non vide. — **Moyen** : Claude in Chrome, à défaut à la main.
- **Geste** : avec Groq choisi au diagnostic (vraie clé), envoyer « Quelle heure est-il ? », puis dans PowerShell `Select-String -Path <dossier de données>\*.jsonl,<dossier de données>\*.log -Pattern '<8 premiers caractères de la clé>'`, ou le script AppSession qui lit `get_journal().all_events()`. — **Attendu** : `outbound_request{origin: model}` porte `Authorization: [masqué]`. — **Critère** : zéro occurrence de la clé ou de ses fragments. — **Moyen** : script AppSession et `Select-String`.
- **Geste** : derrière le proxy d'entreprise, activer data.gouv.fr dans la brique MCP, déplier sa connexion dans « Préparation du harnais », puis faire un appel MCP. — **Attendu** : chaque requête montre ses en-têtes, `Mcp-Session-Id` et tout `Proxy-Authorization` à « [masqué] ». — **Critère** : aucun identifiant du proxy ni aucun identifiant de session en clair dans le journal. — **Moyen** : Claude in Chrome, puis le JSON du journal.
- **Geste** : donner à un participant novice la consigne « Trouve ce que WaveStack envoie à Wikipédia » (retest M2), en partant du panneau des briques. — **Attendu** : il lit la carte Outils, puis clique le nœud ou l'étape. — **Critère** : il trouve le bloc en moins de 30 s, sans aide. — **Moyen** : à la main seulement (œil humain).

## Auto Run Result

Statut : done (2026-09-28, orchestrateur de nuit ; étapes 1 à 4 menées par l'orchestrateur).

**Changement :** chaque `outbound_request` porte ses en-têtes dans l'ordre d'envoi, User-Agent (avec le contact) compris ; liste blanche de 10 en-têtes publics, toute autre valeur remplacée par « [masqué] » avant le journal, pour toutes les origines et chaque saut de redirection. Un nom d'en-tête de clé cloud pris dans la liste blanche est refusé à la lecture de la configuration. Bloc « 🌐 RÉSEAU · Données sortantes » (Requête, En-têtes, Corps) sur les étapes d'outil réseau et les connexions MCP ; clic sur un nœud réseau contacté du schéma : Orchestration réaffiché, étape dépliée, bloc ouvert. Cartes Outils et MCP : « Peuvent sortir du poste : … ». Limite écrite : les en-têtes ajoutés par le transport (proxy, HTTP/2) ne sont pas tracés.

**Fichiers :** `net/factory.py`, `config.py`, `trace/catalog.py`, `bricks/contract.py`, `content/bricks/{tools,mcp}.yaml`, `session/app_session.py`, `web/static/{app.js,app.css}`, `tests/test_{net_factory,cloud,tools,bricks}.py`, `tools/e2e/{run_e2e.py,README.md}`, EXPERIENCE.md, DESIGN.md, ARCHITECTURE-SPINE.md (AD-2, AD-15), SPEC.md (CAP-14, CAP-23), capture 08b.

**Revue :** 25 constats — 17 corrigés (3 medium, 14 low), 5 différés (dont 2 maybe-false), 1 rejeté (false) ; voir le triage. Un contrôle E2E dépendant de l'ordre des scénarios a été rendu indépendant. Revue de suivi recommandée : false.

**Vérification :** ruff check et format verts ; pytest : 968 passés, 3 ignorés ; E2E complet : 454 PASS, 0 FAIL.

**Risques résiduels :** vrai appel Wikipédia et vraie clé Groq à vérifier sur PC ; rendu d'une valeur masquée non vu en E2E.
