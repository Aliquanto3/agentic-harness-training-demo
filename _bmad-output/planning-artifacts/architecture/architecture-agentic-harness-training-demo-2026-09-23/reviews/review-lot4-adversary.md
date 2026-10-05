# Revue adversaire du lot 4 : AD-27 (contrat `mcp_lab`) et AD-28 (`static/diagram.js`)

- **Date** : 2026-10-05
- **Spine** : `ARCHITECTURE-SPINE.md` (statut `final`, mis à jour le 2026-10-05)
- **Périmètre** : AD-27, AD-28, et les paragraphes « Lot 4 du 2026-10-04 » d'AD-2, AD-3, AD-18, AD-19. AD-1, AD-2 (enveloppe, règle de paire), AD-3, AD-14 et AD-15 servent de contexte obligatoire.
- **Méthode** : construire deux unités, un niveau plus bas, qui respectent chaque AD à la lettre et ne s'emboîtent pourtant pas :
  - **(A) backend** : `session/app_session.py` (méthodes de l'atelier, l. 9387-9764), `mcp/lab.py` (`Capture`, `LabConnection`, `last_session`, `step_number`), les modèles de `trace/catalog.py` ;
  - **(B) frontend** : `static/mcp.js` refait en diagramme de séquence selon EXPERIENCE.md (l. 320-610). Il doit tirer chaque flèche de « Lignes de chaque phase » et chaque ligne de « États » des seuls événements (AD-1), et passer par `createStepper` d'AD-28.
- **Lecture du code** : la lecture du code actuel sert à vérifier qu'un écart est réaliste. Elle n'en fait pas un défaut du code : chaque trou reste un trou de la spine.

## Verdict

**AD-27 ne suffit pas encore à garantir deux builds compatibles.** Le contrat nomme bien les événements, mais il laisse trois choses à l'interprétation de chaque unité. D'abord, la nature de chaque message JSON-RPC (requête, réponse, notification, erreur), sa paire et son résumé. Ensuite, la fin de chaque échange (deux `*_ended` sur un même `mcp{n}`), avec la cause d'un échec et l'état de la connexion qui suit. Enfin, le propriétaire des flèches « déduites » et « non capturé ». Dans ces conditions, une page conforme à AD-1 doit soit lire le JSON capturé, ce que l'AD-27 interdit dans ses « Prevents », soit comparer des textes traduits. AD-28 n'a pas de quoi annoncer la flèche courante par son nom ni restituer une session sans rejouer chaque trame.

Bilan : **3 critiques, 8 majeures, 9 mineures.** Il faut fermer les trois critiques avant `bmad-build`.

---

## Critiques

### C1. `mcp_lab_message` est trop pauvre : la page devra lire le JSON pour dessiner une flèche JSON-RPC

**Les deux unités.**
- (A) `Capture.record` émet `{direction, method, jsonrpc, elapsed_ms, reconstructed}`, ce qu'AD-2 et AD-27 demandent à la lettre, et rien de plus.
- (B) Pour chaque flèche JSON-RPC, EXPERIENCE.md exige :
  - la sorte (« requête | réponse | notification sans réponse », dans le nom accessible) ;
  - « aller-retour 1 352 ms » pour une réponse, mais « à 1 363 ms » pour une requête ;
  - le résumé de la réponse (« 2 outils », « 1 bloc texte », « capacités : tools · resources · prompts ») ;
  - le trait rouge et ✖ d'une réponse `error` ou d'un résultat `isError` ;
  - « la dernière requête reste sans réponse, marquée « arrêté » ».

  Le payload ne permet aucune de ces lectures. `method` est rempli pour une réponse (repris de la requête), si bien que `direction` et `method` ne distinguent pas une réponse d'une requête du serveur. Rien ne relie une réponse à sa requête : il n'y a ni `id` ni référence. Le résumé n'existe pas. Pour dessiner, B doit faire `JSON.parse(jsonrpc)`, ce qu'AD-1 refuse (« ne calcule pas ce qu'il n'a pas reçu ») et que les Prevents d'AD-27 interdisent au moins pour les capacités. Une page qui ne lit pas le JSON dessine des flèches sans sorte, sans résumé et sans erreur.

**Aggravant, côté A.** `Capture._pending` est indexé par le seul `id`, sans tenir compte du sens. Prenons une requête du serveur (`ping`, que la ligne « Méthode capturée sans explication » d'EXPERIENCE.md prévoit) dont l'`id` est celui d'une requête du client encore en attente (les deux côtés numérotent depuis 0 ou 1) :
1. la réponse du client à ce `ping` retire de `_pending` l'entrée de la requête du client ;
2. la vraie réponse du serveur arrive ensuite avec `method = ""` et un `elapsed_ms` compté depuis le début de l'échange, pas depuis sa requête ;
3. `received("tools/call")` reste vide, donc `call_ended.raw` vaut `null`.

**Règle proposée (AD-27, « Messages capturés »).**
- `mcp_lab_message` gagne les champs suivants, tous calculés par `Capture` et la session :
  - `message_type: request|notification|response|error` ;
  - `rpc_id: str | int | null` ;
  - `reply_to_seq: int | null` (le `seq` de la requête à laquelle répond ce message, gardé par `Capture`) ;
  - `elapsed_kind: round_trip|since_start` ;
  - `summary_text: str | null` (« 2 outils », « 1 bloc texte », « capacités : … », produit par `msg()` dans la langue de la session) ;
  - `error: {code, message} | null` (réponse JSON-RPC `error`) ;
  - `is_error: bool` (résultat `isError`).
- La paire requête-réponse se fait sur la clé `(sens de la requête, id)`, jamais sur l'`id` seul.
- Les Prevents d'AD-27 s'élargissent : « la page ne lit jamais `jsonrpc` hors de l'encart qui l'affiche ».

### C2. La règle de paire d'AD-2 casse sur un `ask` : deux `*_ended` sur `mcp{n}`

**Les deux unités.**
- (A) Elle suit la lettre d'AD-27 : `exchange_started{exchange: ask}` sur `mcp{n}`, puis, toujours sur `mcp{n}`, `mcp_lab_call_ended{by: model}` (l'outil demandé par le modèle) et enfin `mcp_lab_ask_ended`. Les messages JSON-RPC du `tools/call` restent aussi sur `mcp{n}`.
- (B) Elle suit la lettre d'AD-2 (« toute opération qui dure émet une paire `*_started` / `*_ended` sur le même `step_id` ») et d'AD-1 (« chronomètre ancré sur le `ts` d'un `*_started`, que remplace le `duration_ms` du `*_ended` »). Elle clôt donc la phase au premier `*_ended` reçu sur `mcp{n}`, c'est-à-dire au `call_ended`. La synthèse affiche alors la durée de l'outil, pas celle de l'échange, et les flèches 10 à 12 arrivent dans une phase close.

AD-27 écrit bien que `exchange_started` « forme une paire avec le `*_ended` de sa sorte ». Mais rien n'interdit un second `*_ended` sur le même `step_id`, et AD-2 ne connaît pas la notion de « sorte ».

**Effet de bord.** `Capture.begin(step_id)` remet à zéro l'horloge des requêtes (« à n ms »). Prenons A1, qui appelle `begin` au début de l'`ask`, et A2, qui l'appelle au moment du `tools/call`. Avec A1, la requête `tools/call` affiche « à 15 400 ms », génération comprise. Avec A2, elle affiche « à 2 ms ». Les deux respectent la spine.

**Règle proposée.**
- L'outil demandé par le modèle a son propre sous-pas `mcp{n}.t1` (`parent_step = mcp{n}`), comme les appels au modèle sont des sous-pas `mcp{n}.c{k}`. Son `tools/call` capturé, ses `outbound_request` et son `mcp_lab_call_ended{by: model}` sont sur `mcp{n}.t1`. `Capture.begin(mcp{n}.t1)` fixe l'origine de « à n ms ».
- Règle générale, à ajouter à AD-27 : **chaque `step_id` porte exactement un `*_ended`.** `exchange_started{exchange: X}` se clôt par `mcp_lab_{X}_ended`, et par lui seul.
- `step_number` suit une grammaire écrite : `^mcp(\d+)(\.[ct]\d+)?$` (voir m9).

### C3. Pas de cause d'échec ni d'état de la connexion après un `*_ended` : les états « Arrêté », « injoignable », « Délai dépassé » et « isError » ne se dessinent pas sans comparer des textes

**Les deux unités.**
- (A) `connect_ended`, `call_ended`, `read_ended` et `prompt_ended` ont `status: ok|error` et `error_text` (traduit). Le code actuel met `status: error` à un résultat `isError`, puisque AD-27 ne dit pas s'il est `ok` ou `error` : « un résultat `isError` est un résultat » se lit dans les deux sens.
- (B) Le tableau « États » d'EXPERIENCE.md demande des rendus différents :

| Cas | Ce que montre la page |
|---|---|
| Arrêté | « arrêtée par l'utilisateur » ; les clients reviennent à « non connecté » |
| Injoignable | carte « injoignable », fil rouge ✖, volet de droite vidé |
| Délai dépassé | même marquage que « injoignable », autre texte |
| Erreur JSON-RPC | Séquence seule, la carte reste « connecté » |
| `isError` | flèche rouge, mais « le protocole a fonctionné » |
| Requête bloquée par la garde réseau | ✖ et la raison de la garde |

  Avec le seul `status: error`, B ne peut distinguer ces cas qu'en comparant `error_text` à des messages traduits, ce qui casse en `en` et en `de`.

**Deuxième trou : l'état de la connexion n'appartient à personne.**
- Après un `call_ended` en erreur, le code ferme parfois la connexion (`cancel`, `lost`, `not conn.alive`) et parfois non (erreur JSON-RPC). Aucun événement ne le dit. En direct, B garde « connecté » ; après un rechargement, `open_server` dit `null`. La page en direct et la page restituée divergent.
- Le changement de langue (`_mcp_lab_drop`, `app_session.py` l. 5837) et la fermeture de la session ferment la connexion sans rien émettre dans `mcp_lab`. AD-18 limite la page à `mcp_lab`, `session_state` et `model_load_ended` : elle n'entend pas `language_changed`.
- Pendant un `ask`, « Arrêter » garde la connexion s'il tombe pendant une génération et la ferme s'il tombe pendant une requête MCP. B ne sait pas lequel des deux s'est produit.

**Règle proposée.**
- Chaque `mcp_lab_*_ended` (connexion, appel, lecture, prompt, envoi) gagne :
  - `error_kind: stopped|unreachable|timeout|jsonrpc_error|is_error|closed|guard_blocked|refused|interrupted|null` ;
  - `connection: open|closed`, l'état de la connexion de l'atelier **après** l'événement.
- Table de vérité dans AD-27 :
  - `isError` donne `status: ok`, `is_error: true`, `error_kind: is_error` ;
  - une erreur JSON-RPC donne `status: error`, `error_kind: jsonrpc_error`, `connection: open` ;
  - etc., une ligne par cas.
- Nouveau `kind` : `mcp_lab_closed{server, cause: language|session_close|reset}`, émis à chaque fermeture hors échange et ajouté à `KINDS`.
- `open_server` et le dernier `connection` du journal disent toujours la même chose (test).

---

## Majeures

### M1. Messages hors échange et réponses tardives : `Capture` les range dans le mauvais `mcp{n}`

**Le défaut.** `Capture` a un `step_id` courant, global à la connexion, que `begin` remplace. Trois cas le mettent en défaut :
- **Message spontané.** Un message du serveur arrive entre deux échanges (`notifications/message`, `ping`, `list_changed`, prévus par EXPERIENCE.md). Il porte le `step_id` de l'échange déjà clos, avec un `seq` postérieur à son `*_ended`.
- **Réponse tardive.** Après un délai dépassé, la réponse arrive pendant l'échange suivant. Elle porte le **nouveau** `step_id`, avec un `method` et un `elapsed_ms` de l'ancien.
- **Ordre `begin` / `exchange_started`.** AD-27 veut `exchange_started` « avant tout message », mais ne fixe pas l'ordre entre `exchange_started` et `Capture.begin`. A1 appelle `begin` puis émet. A2 émet puis appelle `begin`. Un message qui tombe entre les deux est rangé différemment.

**Contexte du fil.** Les messages sont émis depuis la boucle asyncio et les autres événements depuis le thread de travail. Pour une requête et sa réponse, l'ordre des `seq` suit bien l'ordre logique : le lecteur du SDK enregistre avant de résoudre le futur qu'attend le thread de travail. Cet ordre n'est plus garanti pour les messages non sollicités.

**Trafic de l'ancienne connexion.** La fermeture de l'ancienne connexion (requête `DELETE` HTTP, notifications) produit des événements sur l'ancien `mcp{p}` **après** `exchange_started` de la nouvelle connexion. `last_session` les écarte (`number >= first`). Rien ne dit à la page en direct d'en faire autant.

**Règle proposée.**
1. La session émet `exchange_started`, **puis** appelle `Capture.begin(step)`. Au `*_ended`, elle appelle `Capture.end()`.
2. Une réponse porte toujours le `step_id` de sa requête (gardé dans `_pending`).
3. Un message reçu hors de tout échange ouvert est émis sur le pas de la connexion, `mcp{first}`, avec `unsolicited: true`. La page le range dans une ligne « hors échange » de la phase de poignée de main. Ce message ne compte pas comme un second `*_ended`.
4. La page ignore tout événement dont `step_number` est inférieur au `first` de la série courante, la même règle que `last_session`.

### M2. `outbound_request` n'est relié à aucun message : l'encart ne sait pas quelle requête HTTP montrer

**Les deux unités.**
- (A) Sur un serveur public, chaque message JSON-RPC part en `POST` dans une tâche du transport Streamable HTTP. S'y ajoutent un `GET` pour le flux SSE et un `DELETE` à la fermeture. Tout cela est émis comme `outbound_request` sur `mcp{n}`, sans référence au message. L'ordre des `seq` entre `mcp_lab_message`, enregistré à l'écriture dans le flux, et `outbound_request`, émis par le hook HTTP d'une autre tâche, n'est pas garanti quand le client envoie une notification et une requête coup sur coup.
- (B) L'encart de la flèche doit montrer « sa » requête HTTP sortante (« 🌐 RÉSEAU · Données sortantes »). Pour la trouver, B doit apparier les deux par ordre d'arrivée (fragile) ou en comparant le corps HTTP au JSON capturé (un calcul).

**Règle proposée.** `OutboundRequestPayload` gagne `message_seq: int | null`. Le hook de `LabConnection` côté session le remplit : il retrouve, parmi les messages `to_server` de la connexion, celui dont le texte sérialisé est le corps envoyé. Le `GET` et le `DELETE` du transport gardent `null`, et la page les place dans une ligne « transport » de la phase. Un `outbound_response` (R2) suit la même règle.

### M3. Les flèches déduites et non capturées n'ont pas de propriétaire

EXPERIENCE.md prévoit plusieurs flèches qu'aucun événement ne porte en propre :
- « Hôte → Client : exécute define_term(…) » ;
- « Client → Hôte : texte du résultat, tokens » ;
- « Client → Hôte : 2 outils · 1 ressource · 1 prompt » ;
- « Serveur → Source : lit glossary.yaml » et « Source → Serveur » ;
- « Hôte → Utilisateur : début de la réponse ».

Chacune est en revanche une étape du stepper (« les flèches non capturé comprises »). La spine ne dit pas de quel événement chacune naît, à quelle place dans la liste, ni sous quelle condition. Deux pages B1 et B2 conformes divergent :
- B1 insère les deux flèches non capturées à la requête ; B2 les insère à la réponse.
- B1 les montre sur un `isError` (le serveur a lu la source) ; B2 ne les montre que sur `status: ok`.
- Sur une erreur « injoignable » ou un délai dépassé, aucune règle ne dit s'il faut les montrer.
- Le libellé « lit glossary.yaml », « API data.gouv.fr » ou « Docs Microsoft » n'est dans aucun contenu. Le `servers` de `GET /api/mcp_lab` n'a pas de `source_text`. B l'écrira donc en dur, contre la convention `t()` et `content/`.

Le nombre total N du stepper dépend de ces choix : « Étape 4 sur 12 » devient « 4 sur 10 » selon l'unité.

**Règle proposée.**
- Une **table de projection normative dans AD-27**, une ligne par flèche de « Lignes de chaque phase ». Chaque ligne donne :
  - la sorte de flèche ;
  - l'événement et le champ qui la font naître ;
  - sa place (avant ou après tel événement) ;
  - sa condition (par exemple « Serveur ↔ Source : seulement si la réponse est arrivée, `isError` compris ; jamais sur `unreachable`, `timeout` ou `stopped` »).
- `content/mcp.yaml` gagne, par serveur, `source_label_text` et `source_action_text`, servis dans `servers`.
- Un test E2E compte N sur les huit scénarios de la maquette.

### M4. Tokens et durées : plusieurs propriétaires, plusieurs définitions

**Les faits en double ou mal définis.**
- `mcp_lab_model_started.prompt_tokens` (compté au rendu, estimé en cloud), `mcp_lab_model_ended.prompt_tokens` et `model_call_ended.prompt_tokens` (`usage` du fournisseur) disent trois choses. AD-27 ne dit pas laquelle porte la flèche 2 (« Hôte → SLM : question + outils, tokens ») ni le bloc « Envoyé au modèle ».
- La somme des `sends[].tokens` n'égale pas `prompt_tokens` (gabarit de chat, rôles). Sans `context_reconciled` dans `mcp_lab`, rien ne réconcilie une estimation en cloud.
- `call_ended.tokens`, `call_ended.truncated.tokens` et `sends[part = tool_result].tokens` de l'appel suivant comptent le « même » résultat, avec ou sans enveloppe de message. Le formateur verra « 64 tokens » sur la flèche 9 et « 71 tokens » sur la flèche 10. De même pour `read_ended.tokens` face à `sends[part = resource].tokens`, gabarit compris.
- Les booléens sont inversés : `exact` sur `model_started`, mais `estimated` sur `connect_ended`, `read_ended` et `call_ended`. Une unité qui prend l'un pour l'autre affiche « estimé » quand le compte est exact.
- « durée de génération » (flèche 3) peut être `mcp_lab_model_ended.duration_ms`, `model_call_ended.gen_ms` ou `prompt_ms + gen_ms`. `ask_ended.model_ms` est sans définition. La synthèse « part de la génération » est un rapport `model_ms / duration_ms` : AD-1 ne permet que l'**écart** entre deux valeurs reçues.

**Règle proposée.** Une table « Chiffres de l'atelier » dans AD-27 :
- `model_started.prompt_tokens` est le compte du rendu (exact en local, estimé en cloud) ;
- `model_ended.prompt_tokens`, `output_tokens` et `usage_source` sont une **copie** de `model_call_ended`, qui fait foi (ou bien ils sont supprimés de `model_ended`) ;
- la flèche 2 lit `model_started`, le bloc « Envoyé au modèle » lit les deux ;
- `sends[].tokens` compte chaque partie telle qu'elle est rendue, et `sends_total_tokens` est fourni ;
- `call_ended.tokens` égale par définition `sends[tool_result].tokens` de l'appel suivant (même texte, même compteur), à défaut d'un libellé distinct imposé ;
- un seul nom de booléen, `estimated`, partout ;
- `model_ms = Σ model_call_ended.duration_ms` ;
- `share_text` (« 82 % de génération ») est calculé par la session dans `ask_ended`.

### M5. Ce que désigne `of`, ce qui part au modèle, et comment s'appellent les arguments

**Contenu gardé.** « La session envoie le contenu qu'elle a gardé ». Mais est-ce le `text` borné de `read_ended` ou les `contents` bruts ? Si c'est le brut, `read_ended.tokens` (« contenu · 64 tokens ») n'est pas ce qui part.

**Prompt.** « Un prompt envoie ses messages tels quels » ne règle ni les messages `assistant` d'un prompt ni l'usage de `messages[].text` face au `text` borné.

**Champs d'`exchange_started` pour un `ask`.** « Un champ qui ne concerne pas cette sorte d'échange vaut `null` ». Pour un `ask` avec `of`, A peut donc mettre `uri` et `prompt` à `null`. Or le titre de phase « Envoi au modèle · {uri} » et l'étape 1 (« envoie le prompt explain_term ») en ont besoin. B devrait retrouver l'échange désigné par `of` dans son magasin, ce qu'aucune règle ne lui permet.

**Connexion et contenu gardé.** Après un « Arrêter » qui a fermé la connexion, sans connexion suivante, le contenu gardé existe encore. A accepte alors `ask{of}`. B grise le bouton, puisque la carte dit « non connecté ».

**Noms et types des arguments.** `args` (dans `exchange_started` et dans l'intention), `arguments` (dans `prompt_ended` et `tool_call`), `name` (dans l'intention prompt) et `prompt` (dans `exchange_started`) désignent les mêmes choses. Le type de `tool_call.arguments` n'est pas fixé : un dictionnaire, ou la chaîne brute du modèle ? Le cas « arguments invalides » d'EXPERIENCE.md exige la chaîne, car un JSON invalide n'est pas un dictionnaire.

**Règle proposée.**
- Le contenu gardé est **exactement** `read_ended.text`, ou les `prompt_ended.messages` bornés.
- `exchange_started` d'un `ask` avec `of` recopie `uri` ou `prompt` et `args` de l'échange désigné.
- Un `ask` exige une connexion vivante au serveur (sinon 409). Le contenu gardé meurt avec la connexion, quelle qu'en soit la cause.
- Un seul nom, `arguments`, partout.
- `tool_call` porte `arguments_text: str` (brut) et `arguments: dict | null` (`null` s'il ne s'analyse pas).

### M6. Fins d'un `ask` : la matrice `status × outcome` n'est pas fermée

Plusieurs cas restent ouverts :
- **Sortie coupée.** `model_ended.outcome: cut` « clôt l'échange », mais `cut` n'existe pas dans `ask_ended.outcome` (`answer|no_tool|refused|second_tool|null`). A1 écrit `status: limit, outcome: null` ; A2 écrit `status: error`.
- **`max_calls` atteint.** `max_calls` peut être atteint par des `load_tool_doc` répétés. L'issue est `status: limit` comme pour `second_tool`, sans valeur propre.
- **Second outil refusé.** Quand le second outil est aussi refusé par `ToolExecutor.check`, on ne sait pas lequel l'emporte, `refused` ou `second_tool`.
- **Dépassement de la fenêtre avant envoi (AD-9).** Il « refuse l'appel avant tout envoi (`status: error`) ». A1 émet `model_started` (avec `sends`) puis `model_ended{error}`, sans `model_call_*`. A2 n'émet que `ask_ended{error}`. La paire de `mcp{n}.c{k}` diffère, et la flèche « Hôte → SLM » rouge existe ou non.
- **« réponse directe, aucun outil ».** Ce libellé se lit sur `ask_ended.outcome: no_tool`, qui arrive **après** `model_ended{answer}`. En direct, la flèche SLM → Hôte s'affiche donc d'abord comme une « réponse finale » ordinaire.
- **Qui a choisi ?** `exchange_started.by: model` sur un envoi de prompt ferait afficher « choisi par le modèle » pour un prompt, qui est choisi par l'utilisateur.

**Règle proposée.**
- Une table de toutes les fins possibles : `status ∈ {ok, error, cancelled, limit}` × `outcome ∈ {answer, no_tool, refused, second_tool, cut, max_calls, overflow, null}`, avec la priorité « refused avant second_tool ».
- Un dépassement avant envoi émet toujours `model_started` puis `model_ended{status: error, error_kind: overflow}`, sans `model_call_*`.
- `model_ended` gagne `final: bool` et `direct: bool`, calculés par la session.
- Pour un `ask`, `by` dit qui a choisi la primitive envoyée (`user` pour un prompt, `app` pour une ressource, `model` sans `of`).

### M7. Un échange interrompu n'émet pas de `*_ended` : la restitution montre une phase sans fin

**Les deux unités.**
- (A) Le chemin `except` de `_run_mcp_lab_connect` et `_run_mcp_lab_call` (l. 9575 et 9718) n'émet que `harness_error`, puis repasse en `idle`. Cela arrive quand l'émission elle-même échoue, par exemple sur une validation pydantic. Lot 4 : `exchange_started` est déjà parti.
- (B) En direct, la page voit `harness_error`. Après un rechargement, `last_session` exclut `harness_error` (AD-27), et la page montre une phase « en cours » pour toujours, avec la session en `idle`.

**Règle proposée.** Le `*_ended` de la sorte est émis dans un `finally`, avec un payload minimal qui ne peut pas échouer à la validation (`status: error, error_kind: interrupted`, `error_text`), en plus de `harness_error`. C'est l'application d'AD-2 (« toute opération qui dure émet une paire ») au chemin d'erreur, à écrire en clair.

### M8. AD-28 : `createStepper` ne permet ni l'annonce nommée, ni une restitution en bloc, ni le rafraîchissement d'une trame

**Annonce nommée.**
- EXPERIENCE.md veut l'annonce « Étape 4 sur 12 : Client MCP vers Serveur MCP, tools/call ». AD-28 fait remplir le nœud `role="status"` par le module, mais « les trames du stepper restent opaques au module ».
- Le module ne peut donc écrire que « 4 / 12 » (`common.diagram.position`). Un module conforme et une page conforme produisent ensemble une annonce sans nom.

**Restitution.**
- Après un rechargement, la page pousse N trames en direct : `push` appelle `go`, puis `onShow`, N fois.
- À chaque trame : repli des phases précédentes, défilement, rallumage de l'Architecture, et peut-être `onLive`. Avec `last_session`, cela fait des dizaines de rendus et de défilements, alors qu'EXPERIENCE.md veut « toutes les phases repliées sauf la dernière ».

**Trame modifiée.**
- Une flèche change après coup : une réponse devient rouge au `call_ended`, un libellé se complète au `connect_ended`.
- Hors du direct, la seule façon de redessiner la trame courante est `show(index)`, qui fixe `live = false`. Sans effet de bord ici, mais rien ne le garantit.
- En direct, la page doit appeler `follow()`, qui saute à la dernière trame.

**Règle proposée.** AD-28 ajoute trois options, sans changer de signature :
- `createStepper(host, {onShow, onLive, describe})` : `describe(frame) → string` donne le nom annoncé, et le module compose « Étape {n} sur {N} : {nom} » ;
- `push(frame, {quiet: true})` pousse une trame sans `onShow`, ou bien `load(frames)` charge une restitution en une fois avec un seul `onShow` ;
- `refresh()` redessine la trame courante sans toucher au mode direct.

L'Atelier Harnais passe à `describe` dans la même livraison (la règle « une retouche vaut pour toutes les pages » d'AD-28).

---

## Mineures

**m1. `outbound_response` et les autres `kind` du modèle manquent à `KINDS`.**
- Une réponse d'erreur (400 ou plus) d'un fournisseur cloud (clé refusée, quota) ou d'un serveur public émet `outbound_response` (R2) dans `mcp_lab`. La page en direct peut l'afficher ; après un rechargement, elle disparaît.
- Il en va de même pour `output_truncated`, `limit_reached`, `context_overflow` et `prefix_not_reused`, si `_call_model` les émet dans ce contexte.
- **Règle** : `KINDS` les liste, ou AD-27 dit que `_call_model` ne les émet pas dans `mcp_lab` et que la page les ignore.

**m2. Capacités sur une poignée de main ratée.**
- Si `tools/list` échoue après un `initialize` réussi, AD-27 ne dit pas si `connect_ended{status: error}` porte encore `capabilities`, `server_info` et `protocol_version`.
- `tools` n'a pas la sémantique `null` ou `[]` de `resources` et `prompts`, alors qu'EXPERIENCE.md barre aussi un onglet Outils non annoncé.
- `capabilities` liste tous les noms de premier niveau (`logging`, `completions`, `experimental`), alors que la flèche ne montre que « tools · resources · prompts ».
- **Règle** : ces champs sont remplis dès qu'`initialize` a répondu, quel que soit le `status` ; `tools` reçoit la même sémantique `null` ou `[]` ; un champ `primitives` est réduit aux trois capacités.

**m3. Origine de « à n ms ».** Elle dépend de l'endroit où l'unité appelle `begin` (voir C2). À fixer dans la règle : la requête est datée depuis le `ts` d'`exchange_started` de son pas.

**m4. `doc_mode` a deux propriétaires.** `exchange_started.doc_mode` reprend l'intention (`lazy`), alors que `model_started.doc_mode` peut valoir `none`. **Règle** : la page lit `model_started`, et `exchange_started` dit « demandé ».

**m5. La réponse a deux propriétaires.** `answer_text` est à la fois dans `model_ended` et dans `ask_ended`. **Règle** : un seul, `model_ended` ; `ask_ended` le référence par `final_step`.

**m6. Réinitialisation.**
- AD-3 ne liste pas `reset` parmi les fermetures de la connexion de l'atelier.
- La page `/mcp` n'écoute pas `session_reset`, et `_mcp_lab_since` survit à la réinitialisation.
- **Règle** : `reset` ferme la connexion (`mcp_lab_closed{cause: reset}`) et remet `first` et `since` à zéro.

**m7. Plusieurs `outbound_request{origin: model}` sur un `mcp{n}.c{k}`.** Un fournisseur qui fait des tentatives produit plusieurs requêtes pour un même appel. **Règle** : l'encart montre la dernière, et une mention « n tentatives » vient de la session.

**m8. Disponibilité de « Envoyer au modèle ».** La page combine `ask.available`, lecture réussie, connexion ouverte et `idle`, alors qu'AD-1 lui interdit de calculer une disponibilité. **Règle** : `read_ended` et `prompt_ended` portent `sendable` et `send_reason_text`, recalculés dans `GET /api/mcp_lab`.

**m9. Grammaire des identifiants.**
- `step_number` doit rendre `None` pour `mcp_lab`, le `step_id` d'un `harness_error` de contenu.
- La convention des identifiants (« Consistency Conventions ») doit ajouter `mcp{n}.t{j}` (voir C2).
- **Règle** : écrire la grammaire `^mcp(\d+)(\.[ct]\d+)?$` dans les conventions et la tester.

---

## Tableau de synthèse

| # | Gravité | Trou | Règle qui le ferme |
|---|---|---|---|
| C1 | critique | message JSON-RPC sans sorte, paire, résumé ni erreur ; `_pending` indexé par l'`id` seul | `message_type`, `rpc_id`, `reply_to_seq`, `summary_text`, `error`, `is_error` ; paire sur `(sens, id)` |
| C2 | critique | deux `*_ended` sur `mcp{n}` dans un `ask` | sous-pas `mcp{n}.t1` ; un seul `*_ended` par `step_id` |
| C3 | critique | ni cause d'échec ni état de la connexion | `error_kind`, `connection`, table de vérité, `mcp_lab_closed` |
| M1 | majeure | messages hors échange, réponses tardives, ordre `begin` / `exchange_started` | `begin` après `exchange_started`, réponse sur le pas de sa requête, `unsolicited` |
| M2 | majeure | `outbound_request` non relié à son message | `message_seq`, rempli par la session |
| M3 | majeure | flèches déduites et non capturées sans propriétaire | table de projection normative, `source_*_text` |
| M4 | majeure | tokens et durées en double ou mal définis | table « Chiffres », `share_text` |
| M5 | majeure | `of`, contenu gardé, noms et types des arguments | contenu = `text` borné, recopie dans `exchange_started`, `arguments_text` |
| M6 | majeure | matrice `status × outcome` du `ask` incomplète | table fermée, dépassement avant envoi normé |
| M7 | majeure | échange interrompu sans `*_ended` | `*_ended` dans un `finally`, `error_kind: interrupted` |
| M8 | majeure | API du stepper : annonce, restitution, rafraîchissement | `describe`, `quiet` ou `load`, `refresh` |
| m1-m9 | mineures | voir ci-dessus | voir ci-dessus |
