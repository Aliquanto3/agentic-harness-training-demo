# Revue rubrique : mise à jour lot 4 du spine (2026-10-05)

**Périmètre.** AD-27 (Atelier MCP en séquence), AD-28 (module commun de schéma), paragraphes « Lot 4 du 2026-10-04 » d'AD-2, AD-3, AD-18, AD-19 et AD-26, ligne Identifiants, ligne CAP-6, élément différé « Atelier MCP, au-delà du lot 4 ».
**Confronté à :** AD-1 à AD-4, AD-9, AD-10, AD-14, AD-15, AD-25 (hérités, contraignants) ; code existant (`mcp/lab.py`, `mcp/connection.py`, `trace/catalog.py`, `session/app_session.py` l. 7692-8140, 8780-8935, 9387-9764, `web/static/diagram.js`, `pages.css` l. 425-575, `mcp.js`) ; EXPERIENCE.md l. 320-610.
**Grille :** le spine fixe tous les vrais points de divergence pour le build du lot 4 ; chaque règle est vérifiable et empêche bien la divergence annoncée ; rien dans les éléments différés ne peut faire diverger deux unités ; le spine entérine le code existant au lieu de le contredire ; les nouveaux AD n'affaiblissent pas les anciens ; l'entrée produit est couverte.

## Verdict

AD-27 répond bien à la question ouverte bloquante d'EXPERIENCE (« Contrat d'événements »). Il nomme chaque fin d'échange, place les appels au modèle sur `mcp{n}.c{k}`, fixe la liste de `last_session` et interdit que la page renvoie elle-même un contenu au modèle. AD-28 reprend fidèlement les retouches d'accessibilité. Il reste toutefois **un point critique** : le chemin cloud imposé contredit le code existant et une règle d'AD-27. S'y ajoutent **quatre lacunes hautes** : exception à AD-14 et AD-25 non dite, fins d'échange qui forcent la page à deviner, volets et mode projection de `/mcp` non traités, annonce du stepper impossible avec des trames opaques. **À corriger avant `bmad-build`.**

---

## Critique

### C1 — Le chemin cloud d'un `ask` émet ce qu'AD-27 interdit et touche à l'état du tour principal

- **Où :** AD-27, « Appels au modèle d'un `ask` » (« les `model_call_*` réels que `_call_model` émet ») et « Modèle cloud » (« `_call_model_chat` émet donc `outbound_request` ») ; AD-26, dernière puce.
- **Problème :** en mode chat, `_call_model` délègue à `_call_model_chat` (`app_session.py` l. 7711). Or `_call_model_chat` fait toujours ce qui suit :
  - il émet `context_reconciled` dès que `usage.prompt_tokens` existe (l. 8097-8100). Cela contredit « Aucun `context_rendered`, `context_preview` ni `context_reconciled` dans `mcp_lab` » ;
  - il recalcule `self._ratio` (l. 8102), le ratio d'estimation de la jauge principale (AD-4). Un appel de l'atelier changerait donc l'estimation du tour suivant ;
  - il ajoute `_turn_costs` et `_turn_impacts` (l. 8087-8096) hors de tout tour ;
  - sur `ProviderError`, il émet `harness_error` avec l'effet `session.turn.over` (« le tour s'arrête »), un texte faux dans l'atelier.

  L'écran « LLM nu » évite précisément ce chemin : `_lab_cloud_call` appelle `run_call` directement, « neither `context_reconciled` nor the estimate's ratio » (l. 8889-8891). En écrivant « comme “LLM nu” » pour le cache tout en imposant `_call_model_chat`, le spine laisse deux implémentations possibles, toutes deux défendables. L'une enfreint la règle d'AD-27. L'autre doit refaire l'analyse des appels d'outils (`call.calls`, `malformed`, identifiants du fournisseur).
- **Correctif proposé :** trancher dans AD-27, sous « Modèle cloud ». Recommandation : garder `_call_model` (un seul analyseur d'appels d'outils, AD-4 et AD-10), mais le conditionner au contexte. `context_reconciled`, l'apprentissage de `_ratio` et `_turn_costs`/`_turn_impacts` ne sont produits que pour `context_id ∈ {main, sub{n}}`. Dans `mcp_lab`, l'effet du `harness_error` vient de `messages.yaml` (`session.mcp_lab.*`). La dépense de session (`consumption_updated`, par `run_call`) reste comptée. Ajouter un test : un `ask` cloud avec `usage` ne produit aucun `context_reconciled` et laisse `_ratio` inchangé.

---

## Haute

### H1 — L'exception à AD-14 et AD-25 n'est pas dite, et le régime de lazy loading reste ouvert

- **Où :** AD-27, « Déroulé et bornes d'un `ask` » (« contrôlé par `ToolExecutor.check` », « `load_tool_doc` (`meta_call`) est répondu par le harnais »).
- **Problème :**
  1. AD-14 impose qu'« Tout appel passe par un seul exécuteur, qu'il vienne du modèle […] : `before_tool`, exécution, `after_tool`, réinjection ». AD-25 impose que les méta-outils passent par l'exécuteur unique, et son Prevents vise « des actions décidées par le modèle qui échappent aux hooks ». AD-27 fait choisir un outil MCP par le modèle sans exécuteur : `check` seul, puis la file de `LabConnection`, sans H1, sans H5 ni effet. C'est cohérent avec le bac à sable, mais cela affaiblit en silence deux AD contraignants. Un développeur qui lit AD-14 branchera les hooks ; un autre suivra AD-27 à la lettre.
  2. AD-25 fixe deux régimes de lazy loading. En local, la documentation entre en réponse d'outil. En chat, elle entre dans `tools` à l'appel suivant, faute de quoi le fournisseur répond `tool_use_failed`. AD-27 permet le cloud mais écrit seulement « Sa documentation entre dans l'appel suivant (`sends.part = tool_doc`) », sans choisir de régime. En cloud, un développeur qui prend le régime local obtient un refus du fournisseur.
  3. AD-10 envoie un appel mal formé sur la voie du nouvel essai. AD-27 clôt l'échange sur `refused` et ne dit pas qu'il n'y a jamais de nouvel essai. Il ne dit pas non plus si une sortie illisible pour le parseur (`malformed`, avant `check`) donne `refused`.
- **Correctif proposé :** ajouter une puce « Bac à sable et AD-14 » dans AD-27 : « L'atelier n'exécute ni hooks ni effets. Un appel du modèle passe seulement par `ToolExecutor.check(call, enabled, loadable)`, avec `enabled` et `loadable` tirés du registre de l'atelier et des documentations chargées dans l'échange. H5 ne s'applique pas : le clic “Envoyer au modèle” et l'avertissement cloud en tiennent lieu. AD-14 et AD-25 restent la règle du tour. » Préciser aussi :
  - le régime de `load_tool_doc` : celui d'AD-25 selon le mode, réponse `tool` en local, définition ajoutée à `tools` en chat ;
  - « aucun nouvel essai » : `malformed`, outil inconnu et arguments invalides donnent `outcome: refused` avec la raison.

  Mettre un renvoi d'une ligne dans AD-14 et AD-25.

### H2 — Les fins d'échange ne disent ni l'arrêt ni l'état de la connexion, ni le statut d'un `isError`

- **Où :** AD-27, « Fins d'échange » ; `mcp_lab_connect_ended`, `mcp_lab_call_ended`, `mcp_lab_read_ended` et `mcp_lab_prompt_ended` (`status: ok|error`).
- **Problème :** l'état « Arrêté » d'EXPERIENCE exige trois affichages : « marquée “arrêté” », « la synthèse de phase dit “arrêtée par l'utilisateur” » et « les clients reviennent à l'état non connecté ». Aujourd'hui, l'arrêt et la perte de connexion ne passent que par `error_text` (`session.mcp_lab.stopped`, `session.mcp_lab.closed`, `app_session.py` l. 9546-9549 et 9689-9700). La page devrait donc deviner depuis un texte traduit, exactement ce que le Prevents d'AD-27 interdit (« une page qui devine une phase »). Même chose après un `ask` dont le `tools/call` perd le serveur : rien ne dit que la connexion est fermée (`open_server` n'existe que dans `GET`). Pour `isError`, le code met `status = "error"` (l. 9706-9709). AD-27 ajoute `is_error` sans dire si `status` devient `ok` ni si, dans un `ask`, un résultat `isError` part au modèle comme `tool_result`. EXPERIENCE le veut (« isError est un résultat normal », Flow MCP-2 : « le texte d'erreur serait réinjecté au modèle »).
- **Correctif proposé :**
  - `status: ok|error|cancelled` sur les quatre `*_ended`, `cancelled` pour un arrêt ;
  - un champ `connection: open|closed` sur tous les `*_ended`, `ask_ended` compris, posé par la session après l'échange ;
  - une règle explicite : « un résultat `isError` donne `status: ok, is_error: true` et entre dans l'appel suivant d'un `ask` comme `tool_result` ». Si l'équipe préfère `error`, l'écrire.
  - Ajouter l'issue d'un `tools/call` en échec de transport pendant un `ask` : `ask_ended{status: error, outcome: null}`.

### H3 — Volets, mode projection et état du navigateur de `/mcp` : aucune règle

- **Où :** AD-18 (lot 4), AD-28 (Binds) ; EXPERIENCE, « Découpe en quatre volets » (masquer, focus, redimensionner « comme l'Atelier Harnais » ; mode projection sur `/mcp`, décision du 2026-10-05 ; tailles, volets masqués et vue « Avant/Avec MCP » mémorisés à part).
- **Problème :** les volets (masquer, focus, gouttières, puces) vivent dans `app.js` et `app.css` (`.pane-*`, `.pane-resize-handle`). AD-18 place la rampe du mode projection « sous `:root.projection`, dans `app.css` », une feuille que `/mcp` ne charge pas. AD-28 ne partage que le schéma. Le développeur de `mcp.js` a donc trois options : réécrire les volets (divergence visuelle et d'accessibilité avec l'atelier, celle-là même qu'AD-28 veut empêcher), importer `app.js` (impossible) ou extraire un module (non décidé). La liste « État du navigateur » d'AD-18 ne contient aucune clé de `/mcp`, et le menu « Affichage ▾ » de `pages.css` ne propose la projection que « on the main screen ».
- **Correctif proposé :** ajouter une puce dans AD-28 ou AD-18 :
  - la rampe `:root.projection` passe dans `pages.css`, partagée ;
  - la mécanique des volets est extraite dans un module commun (par exemple `static/panes.js`) sous la même règle qu'AD-28 (seule implémentation, retouche commune, E2E de l'atelier dans la même livraison). À défaut, écrire que `mcp.js` reprend les classes `.pane-*` sans les redéfinir ;
  - ajouter les clés de `/mcp` à « État du navigateur » (disposition des volets, vue « Avant/Avec MCP », projection, avec la mémorisation partagée qu'EXPERIENCE demande).

### H4 — Le stepper ne peut pas produire l'annonce exigée, et il y aurait deux régions `status`

- **Où :** AD-28, « Retouches du lot 4 » (nœud `role="status"` rempli hors du direct) et « Les trames du stepper restent opaques au module ».
- **Problème :**
  - EXPERIENCE (« Flèche courante ») exige l'annonce « Étape 4 sur 12 : Client MCP vers Serveur MCP, tools/call », avec position **et** nom. Le module ne connaît que la position (`common.diagram.position`) et ne sait rien des trames. Soit la page duplique une seconde annonce, soit le module annonce seulement « 4 / 12 ».
  - EXPERIENCE prévoit « une région `status` par page » pour les synthèses. Le nœud `status` du module en ajoute une seconde, sans règle de coexistence.
  - `diagram.js` met `disabled` natif sur ◀ et ▶ (l. 182-183). Arrivé à la première étape au clavier, le focus est perdu, contre la règle d'EXPERIENCE « une commande qui devient indisponible garde le focus (`aria-disabled`) ». Cette retouche manque à AD-28.
- **Correctif proposé :**
  - ajouter l'option facultative `describe(frame, index) → string` à `createStepper`, que le module concatène à la position dans son nœud `status` (sans `describe`, la position seule, ce qui garde l'atelier inchangé) ;
  - dire que ce nœud est réservé au stepper et que la région `status` de la page ne porte que les synthèses ;
  - ajouter aux retouches : « ◀ et ▶ en `aria-disabled`, pas `disabled` ».

---

## Moyenne

### M1 — `ask{available, reason_text, tools, model}` ne suffit pas pour deux segments, et sa fraîcheur n'est pas définie

- **Où :** AD-27, « Intentions », dernière puce ; AD-18 (lot 4).
- **Problème :** avec un modèle chargé qui n'appelle pas d'outils, « Envoyer au modèle » (ressource, prompt) est disponible mais « Par le modèle » ne l'est pas, avec la raison « Le modèle actif n'appelle pas d'outils : choisissez-en un autre dans le diagnostic ». Un seul `reason_text` ne porte pas les deux raisons. Le spine ne dit pas non plus si `available` inclut l'état `idle` : la page ne relit la route qu'après `model_load_ended`, donc une valeur qui dépendrait de l'état serait périmée.
- **Correctif proposé :** `ask{model_ready, model_reason_text, tools, tools_reason_text, model}`, calculé sans l'état de la session. La page le combine avec `session_state` (une conjonction de deux booléens reçus, permise par AD-1). Ajouter les raisons dans `messages.yaml`.

### M2 — AD-26 « aux mêmes règles » renvoie à un `context_rendered` qui n'existe pas dans `mcp_lab`

- **Où :** AD-26, dernière puce (« le corps envoyé reste égal à `context_rendered.body` et à `outbound_request.body` ») ; AD-27 (« Aucun `context_rendered` »).
- **Problème :** la moitié de l'invariant n'a pas d'objet dans l'atelier, et rien ne garantit que `sends` vienne des mêmes octets que le corps envoyé.
- **Correctif proposé :** dans AD-26 ou AD-27, écrire : « Dans `mcp_lab`, le corps envoyé est égal à `outbound_request.body` du même `mcp{n}.c{k}`. `sends` est la somme, par `part`, des segments de ce même rendu. » Ajouter un test.

### M3 — Direct et restitution peuvent diverger

- **Où :** AD-18 (« ne garde que le contexte `mcp_lab` ») ; AD-27, « `last_session` ».
- **Problème :** en direct, la page reçoit tout le contexte `mcp_lab`, donc aussi `harness_error`, `outbound_response` (réponses d'erreur, R2), `reasoning_cut`, `output_truncated`, `special_token_neutralized` et `consumption_updated`, que `_call_model` émet dans la portée. `last_session` ne garde que `KINDS`. Une page qui affiche l'un de ces événements en direct le perd au rechargement. Autre point : `mcp_lab_model_ended.reasoning_cut` porte le même nom que le kind `reasoning_cut` existant (`catalog.py` l. 365), mais son type n'est pas fixé.
- **Correctif proposé :** ajouter à AD-27 : « La page ne rend que les kinds de `mcp/lab.KINDS` (plus `session_state` et `model_load_ended`). » Si l'encart doit montrer une réponse HTTP en erreur, ajouter `outbound_response` à `KINDS`. Typer `reasoning_cut: bool`.

### M4 — Le chemin des résultats de la poignée de main n'est pas défini

- **Où :** AD-27, « Poignée de main ».
- **Problème :**
  - « lus dans `client.server_capabilities` par la session » : le `Client` est une variable locale de la tâche `_serve`, sur la boucle (`connection.py` l. 106-130), et la session ne peut pas le lire. Aujourd'hui, `start()` rend `list[Tool]` par la future `ready`. Le spine ne dit pas comment capacités, `server_info`, `protocol_version`, ressources, prompts et `list_errors` arrivent jusqu'à la session.
  - « `tools/list`, puis `resources/list` et `prompts/list` […], chacune seulement si la capacité est annoncée » ne dit pas si `tools/list` est conditionnel. `tools` n'a pas de `null` dans le payload.
  - Une liste facultative qui ne répond pas fait expirer toute la connexion (`wait_for(ready, connect_timeout)`), alors que la règle veut une connexion `ok`.
- **Correctif proposé :**
  - « `LabConnection.start()` rend un `Handshake{capabilities, server_info, protocol_version, tools, resources, prompts, list_errors}` ; la session ne touche jamais le `Client` » ;
  - écrire explicitement si `tools/list` est conditionnel (et alors `tools: … | null`) ;
  - chaque liste facultative est bornée par `call_timeout` à l'intérieur de `connect_timeout` ; un délai dépassé va dans `list_errors`.

### M5 — Les préconditions de `mcp_lab_ask` sont incomplètes

- **Où :** AD-27, « Intentions ».
- **Problème :** pour `read` et `prompt`, le spine exige « la connexion de l'atelier à ce serveur », mais il ne le dit pas pour `ask`. Un `ask` sans `of` a besoin des outils listés (`_mcp_lab_tools`, vidés par `_mcp_lab_drop`). Rien ne dit non plus si le contenu gardé survit à une connexion fermée par « Arrêter », ni ce qui se passe si `server` ne correspond pas au serveur de `of`.
- **Correctif proposé :** « `mcp_lab_ask` exige une connexion vivante de l'atelier à `server` (sinon 409) ; `of` appartient à cette connexion ; le contenu gardé est vidé à toute fermeture de la connexion (suivante, Arrêter, langue, perte) ».

### M6 — La cause `mcp_lab` n'a pas de chemin dans `_lab_restore`, ni de libellé

- **Où :** AD-27, « Cache du moteur » ; AD-2 (lot 4, `prefix_not_reused.cause` gagne `mcp_lab`) ; AD-19 (lot 4).
- **Problème :** `_lab_restore` écrit `"llm"` en dur (`app_session.py` l. 8933), et `PrefixCause` est un `Literal`. EXPERIENCE (« Retour à l'Atelier Harnais ») demande le libellé « Atelier MCP » dans `prefix_causes`, ce que le paragraphe lot 4 d'AD-19 ne mentionne pas.
- **Correctif proposé :** « `_lab_restore(saved, cause)` ; `PrefixCause` gagne `mcp_lab` ; libellé `prefix_causes.mcp_lab` dans les trois langues (`ui.yaml` ou `messages.yaml`, comme `llm`) ».

### M7 — Les issues de borne sont incomplètes

- **Où :** AD-27, « Déroulé et bornes », « Appels au modèle » (dépassement).
- **Problème :** quand `tools.max_calls` est atteint (par exemple après des `load_tool_doc` répétés), ni `outcome` ni l'émission de `limit_reached` ne sont fixés, et `ask_ended.outcome` n'a pas de valeur pour ce cas. Pour un dépassement d'AD-9, on ne sait pas si `mcp_lab_model_started` est émis avant le refus (comme `llm_generation_started` dans « LLM nu », l. 8795-8804), ni si `model_call_*` est absent.
- **Correctif proposé :**
  - `ask_ended{status: limit, outcome: max_calls}` (nouvelle valeur), sans `limit_reached` (événement du tour) ;
  - dépassement : `mcp_lab_model_started` puis `mcp_lab_model_ended{status: error, error_text}`, sans `model_call_*`.

### M8 — Le serveur local est absent des Binds

- **Où :** CAP-6, AD-27 (Binds) ; AD-19 (lot 4 : « Le serveur local sert la ressource `glossary://terms` et le prompt `explain_term(term)` »).
- **Problème :** `mcp/local_server.py` (`MCPServer`) doit déclarer les capacités `resources` et `prompts`, mais ce module ne figure ni dans la ligne CAP-6 ni dans Binds. Rien ne dit non plus que la brique (sa `McpConnection`, `_serve`) ignore ces capacités, ce qui ne change pas le contexte principal.
- **Correctif proposé :** ajouter `mcp/local_server.py` à CAP-6 et aux Binds d'AD-27, avec une phrase : « la connexion de la brique ignore ressources et prompts ».

---

## Basse

- **B1 — AD-28, « 3 px » contre « Valeurs exactes : DESIGN.md seulement ».** La règle donne une valeur en dur tout en renvoyant les valeurs à DESIGN.md. *Correctif :* nommer le jeton (par exemple `--spacing-stroke-path`) et renvoyer la valeur à DESIGN.md.
- **B2 — AD-28, « jamais surcharger une règle `diagram-*` ».** C'est vérifiable mais aucun test n'est prévu. *Correctif :* un test pytest vérifie qu'aucun sélecteur `.diagram-` n'existe hors de `pages.css`.
- **B3 — `exchange_started` d'un `ask` avec `of`.** Le titre de phase « Envoi au modèle · {uri} | {prompt} » exige que la page retrouve l'échange visé. *Correctif :* dans ce cas, `uri` ou `prompt` sont renseignés par la session.
- **B4 — `null` a deux sens dans `resources` et `prompts`** (capacité non annoncée, liste en échec). *Correctif :* écrire que la page décide « ⊘ » d'après `capabilities` et l'échec d'après `list_errors`.
- **B5 — Différé, « requêtes du serveur vers le client ».** Le comportement actuel n'est pas dit. *Correctif :* « capturées et affichées comme méthode sans explication ; le SDK répond par une erreur ; aucune action de la session ».
- **B6 — « Arrêter » pendant une génération.** `_mcp_lab_stop` ferme toujours la connexion (l. 9761-9763). *Correctif :* nommer le critère (par exemple « requête MCP en cours » = `LabConnection._calling` ou poignée de main inachevée), pour que la règle soit testable.
- **B7 — Identifiants.** `_new_call_id` ajoute les `tool_call_id` de l'atelier à l'ensemble du tour (`_call_ids`, « unique within the turn »). C'est sans collision (empreintes sur `mcp{n}.c{k}`), mais le spine pourrait dire que l'atelier n'utilise pas cet ensemble. La ligne story 6 d'AD-2 garde aussi une définition de `step_id` que remplace AD-27 : une mention « remplacé » suffirait.

---

## Points conformes (pour mémoire)

- La paire `mcp_lab_exchange_started` / `*_ended` sur `mcp{n}` respecte la règle de paire d'AD-2, sans toucher à l'enveloppe.
- `mcp{n}.c{k}` évite deux paires `model_call_*` sur le même `step_id`. `step_number` est étendu en conséquence.
- `trigger = user` avec `by` dans les payloads : choix explicite et justifié, sans conflit avec la sémantique d'AD-2.
- La session garde le contenu lu ou obtenu, et `of` est une référence : le Prevents « contenu qui vient de la page » est tenu.
- `last_session` et `KINDS` sont énumérés, `model_delta` est exclu, `model_call_ended` fait foi : conforme à AD-2.
- Les poids affichés et envoyés passent par le même `ToolRegistry` et `_tool_definitions` : conforme au code (`_mcp_lab_weights`).
- AD-28 reprend une à une les retouches de la dernière puce d'accessibilité d'EXPERIENCE, et `onLive` couvre la puce « ↓ {n} nouveaux messages ».
- L'élément différé ne laisse diverger aucune unité, sous réserve de B5.
