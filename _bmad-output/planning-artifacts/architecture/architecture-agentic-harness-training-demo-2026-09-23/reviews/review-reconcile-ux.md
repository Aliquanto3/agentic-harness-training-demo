---
title: Revue de réconciliation — spine d'architecture × spécifications UX
date: 2026-09-23
reviewed: ../ARCHITECTURE-SPINE.md, ../.memlog.md
against:
  - ../../../ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
  - ../../../ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md
---

# Revue de réconciliation — spine × UX

## Verdict

Le paradigme retenu (journal d'événements, volets en projection) convient très bien à l'UX : il n'y a aucune incompatibilité de fond. En revanche, le spine fige l'enveloppe des événements (« chaque story ajoute ses `kind` sans modifier l'enveloppe ») alors que cette enveloppe ne porte pas les champs de corrélation dont l'UX a besoin : sélection synchronisée, « Suivre le direct », animation du schéma, ouverture des données sortantes depuis un flux. S'y ajoutent trois contradictions de règles : la fenêtre utile face à la jauge, les intentions refusées pendant un tour, et l'ordre du diagnostic de démarrage. Tout cela doit être corrigé dans le spine avant les premières stories.

**Bilan** : 1 bloquant, 11 majeurs, 5 moyens, 7 mineurs.

Échelle de gravité :
- **Bloquant** : fige un mauvais contrat avant le développement.
- **Majeur** : deux stories divergeront, ou un comportement UX sera impossible sans une règle du spine.
- **Moyen** : ambiguïté que la première story tranchera seule, avec un risque d'incohérence.
- **Mineur** : précision ou demande de changement à l'UX.

## Synthèse

| ID | Gravité | Sujet | Type |
|---|---|---|---|
| R-01 | Bloquant | Enveloppe sans champs de corrélation (appel, étape, composant) | Lacune |
| R-02 | Majeur | Cycle de vie des phases : indicateur de travail, chronomètre | Lacune |
| R-03 | Majeur | Fenêtre utile (réserve de 512) contre pourcentage de la jauge | Contradiction |
| R-04 | Majeur | Segments : catégorie d'empilement, plages, exactitude des tokens | Lacune |
| R-05 | Majeur | Contexte assemblé mais non envoyé (dépassement) | Lacune |
| R-06 | Majeur | Jauge qui bondit à l'activation d'une brique (Flow 1, étape 8) | Contradiction UX / spine |
| R-07 | Majeur | AD-3 refuse presque tout pendant un tour ; l'UX l'autorise | Contradiction |
| R-08 | Majeur | Canal des tokens en flux (raisonnement, texte, appel d'outil) | Lacune |
| R-09 | Majeur | Modèle d'exécution concurrent (flux, H5, arrêt, chronomètre) | Lacune |
| R-10 | Majeur | Données exactes affichées par H5 avant la construction de la requête | Lacune |
| R-11 | Majeur | Schéma d'architecture : nœuds, flux, activité, lieu de dérivation | Lacune |
| R-12 | Majeur | Diagnostic dans le terminal et le navigateur, port occupé, mode dégradé | Contradiction |
| R-13 | Moyen | Changement de modèle entre deux tours, conversation conservée | Lacune |
| R-14 | Moyen | API de lecture et état initial au rechargement | Lacune |
| R-15 | Moyen | Rejeu : branche active, comparaison, tours après réinitialisation | Lacune |
| R-16 | Moyen | Appel mal formé : partie fautive et numéro d'essai | Lacune |
| R-17 | Moyen | Magasin de projection indépendant des volets masqués | Lacune |
| R-18 | Mineur | Tokens de design sans compilation, polices locales et licences | Lacune et contradiction interne |
| R-19 | Mineur | Gravité et annonce des événements ; mouvement réduit | Lacune |
| R-20 | Mineur | Commandes du spine absentes de l'UX (fenêtre, bornes, arrêt) ; périmètre de la réinitialisation | Demande de changement à l'UX |
| R-21 | Mineur | Scénario qui demande une brique indisponible | Lacune |
| R-22 | Mineur | « Lecture du contexte (N tokens) » et cache de préfixe | Lacune |
| R-23 | Mineur | AD-1 « ne recalcule ni tokens » contre les écarts (+/−) et le chronomètre | Contradiction |
| R-24 | Mineur | Données sortantes hors tour (initialisation MCP, sonde réseau, téléchargement) | Lacune |

---

## Constats

### R-01 — Enveloppe sans champs de corrélation · **Bloquant**

- **Référence UX** : EXPERIENCE, Interaction Primitives (sélection synchronisée, « Direct par défaut ») ; Component Patterns `turn-rail`, `token-counter`, `context-gauge-detail`, `arch-*` ; Codage local / réseau (« un clic sur le flux ouvre les données sortantes de cet appel ») ; Flow 1, étape 10 ; Flow 4, étape 6.
- **Lacune** : l'enveloppe AD-2 `{seq, ts, turn_id, context_id, kind, actor, brick, payload}` ne permet de rattacher un événement :
  - ni à un **appel au modèle** (l'identifiant du segment porte l'appel, `{turn_id}.{call}.{n}`, mais pas les événements) ;
  - ni à une **étape** du rail ;
  - ni à un **composant** du schéma : une même brique MCP porte le serveur local et plusieurs serveurs publics.

  Sans ces champs, chaque volet devinera ses liens à partir des `payload`, ce qui contredit AD-1. De plus, `turn_id` est implicitement obligatoire, alors que beaucoup d'événements surviennent hors tour : bascule de brique, chargement de modèle, réinitialisation, disponibilité, diagnostic. Enfin, le spine interdit de modifier l'enveloppe après coup.
- **Correctif** (AD-2) : l'enveloppe devient `{seq, ts, turn_id?, context_id, call?, step_id?, parent_step?, component?, kind, actor, brick?, payload}` :
  - `turn_id` vaut `null` hors tour ;
  - `call` est l'index de l'appel au modèle dans le contexte (0, 1…) ;
  - `step_id` vaut `{turn_id}.{context_id}.s{n}` : c'est une étape du rail, et tous les événements d'une même action la partagent ;
  - `parent_step` sert aux étapes dépliables : délégation au sous-agent, étapes de brique ;
  - `component` est l'identifiant stable d'un nœud du schéma (voir R-11).

  Ajouter la règle : « tout événement qui concerne une action porte son `step_id` ; tout événement qui touche un composant porte son `component` ». La convention d'identifiants (Consistency Conventions) reçoit `step_id` et `component`.

### R-02 — Cycle de vie des phases : indicateur de travail et chronomètre · **Majeur**

- **Référence UX** : `working-indicator` (« Lecture du contexte (1 840 tokens) », « Exécution de l'outil heure », « Appel au sous-agent », chronomètre en secondes, disparaît au premier token, réapparaît entre deux appels) ; état « Travail sans token visible » ; « Changement de modèle en cours » (chronomètre de 5 à 20 s) ; H5 (« En attente de validation ») ; Voice and Tone : « … 6 s ».
- **Lacune** : le spine ne définit aucune convention de début et de fin d'opération, aucun événement « premier token », ni la source du libellé de phase (français, construit en Python selon la convention Erreurs). La précision de `ts` n'est pas fixée (ISO 8601 sans millisecondes, horloge murale). Deux stories produiront des libellés et des durées incohérents.
- **Correctif** (AD-2, nouvelle sous-règle « Phases ») :
  - Toute opération qui dure émet une paire `*_started` / `*_ended` sur le même `step_id`.
  - `*_started` porte `phase_label` en français (par exemple « Lecture du contexte (1 840 tokens) »).
  - `*_ended` porte `duration_ms`, mesuré avec `time.monotonic()`.
  - `ts` est en ISO 8601 à la milliseconde.
  - Catalogue minimal, fixé dans le spine :
    - `turn_started` / `turn_ended` ;
    - `model_call_started` (`prompt_tokens`) ;
    - `model_first_token` ;
    - `model_call_ended` (`output_tokens`, `prompt_ms`, `gen_ms`) ;
    - `tool_started` / `tool_ended` ;
    - `subagent_started` / `subagent_ended` ;
    - `awaiting_human` / `human_decision` ;
    - `model_load_started` / `model_load_ended` ;
    - `rag_search_*`, `rerank_*`, `compression_*`.
  - Le chronomètre en direct est un décompte local au navigateur, ancré sur le `ts` du `*_started` ; la valeur affichée ensuite est `duration_ms`. Préciser dans AD-1 que ce décompte n'est pas un recalcul (voir R-23).

### R-03 — Fenêtre utile contre pourcentage de la jauge · **Majeur (contradiction)**

- **Référence UX** : `context-gauge` et DESIGN, Components (« 1 840 / 4 096 tokens · 45 % », seuil d'alerte à 80 %, dépassement « au-delà de 100 % ») ; Voice and Tone : « 4 310 tokens pour une fenêtre de 4 096 ».
- **Contradiction** : AD-9 déclare un dépassement dès que *contexte + 512 > 4 096*. Entre 3 585 et 4 096 tokens, la jauge affiche donc 88 à 100 % alors que l'appel est déjà refusé. La salle voit « 95 % » et une carte « Contexte dépassé » : c'est incompréhensible. Le seuil de 80 % n'est pas non plus placé dans l'architecture (configuration ? front ?).
- **Correctif** (AD-9) :
  - L'événement de contexte porte `window`, `output_reserve`, `usable = window − output_reserve`, `used`, `percent = used / usable`, `near_limit` et `overflow`, tous calculés par la session. Le seuil d'alerte (0,8) est dans `wavestack.toml`.
  - La jauge affiche « 1 840 / 3 584 tokens utiles · 51 % », et la réserve de sortie est expliquée au survol et dans le détail de la jauge.
  - Variante : dessiner la réserve comme une zone distincte en fin de jauge. Cela exige un token `segment-reserve` dans DESIGN.md, donc une demande de changement à l'UX.
  - Aligner le message de dépassement : « 3 800 tokens + 512 réservés à la réponse, pour une fenêtre de 4 096 ».

### R-04 — Segments : catégorie d'empilement, plages et exactitude des tokens · **Majeur**

- **Référence UX** : `context-gauge` (ordre d'empilement imposé : prompt système, mémoire globale, descriptions, historique, RAG, résultats d'outils, message et gabarit, espace libre) ; DESIGN, palette catégorielle à 7 couleurs et `context-segment` (texte intégral) ; état « LLM nu » (un seul segment, « Message et gabarit ») ; `turn-compare` (« aligne les segments par brique »).
- **Lacune** :
  - Le `kind` de segment d'AD-4 est libre. Aucune énumération fermée ne relie les segments aux 7 catégories de la palette, donc le front inventera cette correspondance.
  - Les tokens du gabarit sont répartis entre tous les messages (`<|im_start|>…`). Or AD-4 les attribue au seul segment « Message et gabarit » sans dire comment le texte affiché dans Contexte LLM reste fidèle à l'ordre réel.
  - Tokeniser segment par segment ne donne pas le total : les fusions BPE aux frontières faussent la somme. La promesse « la somme des segments est égale au total envoyé » n'a pas de méthode.
  - Enfin, l'alignement dans la comparaison n'a pas de clé stable d'un tour à l'autre, puisque `segment.id` contient le `turn_id`.
- **Correctif** (AD-4) :
  - Les segments deviennent des **plages** `{id, start, end, category, brick, component?, source_key, label_fr, tokens}` du texte rendu.
  - Les plages couvrent **tout** le texte rendu, sans trou. Chaque fragment de gabarit est une plage de catégorie `message_template`.
  - `category` est une énumération fermée, définie une seule fois dans `trace` et dans l'ordre de l'UX : `system_prompt, global_memory, tool_descriptions, history, rag, tool_results, message_template`.
  - Les tokens se comptent en tokenisant **une fois** le texte rendu entier. Chaque token est attribué à la plage qui contient son premier caractère ; les positions s'obtiennent en détokenisant token par token. La somme est donc exacte par construction. Test pytest avec le moteur factice.
  - L'événement `context_rendered` porte `rendered_text`, `segments[]` et `totals_by_category` (dans l'ordre d'empilement), pour que le front n'agrège rien.
  - `source_key` est une clé stable d'un tour à l'autre (par exemple `mcp.datagouv.descriptions`) qui sert à l'alignement de la comparaison.

### R-05 — Contexte assemblé mais non envoyé (dépassement) · **Majeur**

- **Référence UX** : `overflow-card` (compte de tokens, segments les plus lourds, « Pour continuer la démo » où chaque piste nomme sa commande) ; état « Contexte dépassé » (jauge au-delà de 100 % sur pastille rouge, Contexte LLM toujours consultable) ; Voice and Tone (« les descriptions MCP en documentation complète pèsent 2 900 tokens »).
- **Lacune** : AD-9 dit que l'événement de dépassement porte « les tokens, la fenêtre et les segments les plus lourds ». Mais AD-4 ne dit pas **quand** le rendu est émis par rapport au contrôle. Si le rendu n'est émis qu'à l'envoi, la jauge et Contexte LLM n'ont rien à afficher au dépassement. Rien ne relie non plus les pistes « Pour continuer la démo » aux commandes réelles.
- **Correctif** (déroulé d'un tour et AD-9) :
  - Ordre imposé : `assemble_context`, `before_model_call`, **`context_rendered` (toujours émis)**, contrôle, puis soit `model_call_started`, soit `context_overflow`, sur le même `step_id` et le même `call`.
  - `context_overflow` porte `used`, `usable`, `window`, les trois plus lourds (`source_key`, `label_fr`, `tokens`) et `suggestions[]`. Chaque suggestion donne `{label_fr, intent}`, ce qui permet à la carte de désigner la commande à utiliser.
  - Les textes « En production, un harnais pourrait » viennent de `content/`.

### R-06 — Jauge qui bondit à l'activation d'une brique · **Majeur (contradiction UX et spine)**

- **Référence UX** : Flow 1, étape 8 (« Il active la brique MCP, puis le serveur public data.gouv.fr […] la jauge fait un bond d'environ 2 900 tokens », **avant** l'envoi de l'étape 9). Cela contredit `context-gauge` (« Montre le contexte de l'appel au modèle le plus récent ») et `brick-card` (« effet au tour suivant »).
- **Lacune** : le spine ne prévoit aucun aperçu du contexte hors tour. Or le moment pédagogique de Flow 1 repose sur ce bond. L'activation d'un serveur MCP public exige en plus un `tools/list` sur le réseau au moment de l'activation.
- **Correctif** — deux options à trancher ; l'option A est recommandée, car elle coûte peu (l'assemblage est déterministe et la tokenisation de quelques kilo-octets est rapide) :
  - **A (spine)** : après chaque changement de configuration, la session calcule un **aperçu** avec `assemble_context`, sans message utilisateur, sans RAG ni résultats d'outils, et avec seulement le gabarit vide pour « Message et gabarit ». Elle l'émet en `context_preview` (`turn_id = null`, champs de R-03). La jauge l'affiche avec la mention « Prochain tour, avant votre message ». L'UX doit ajouter cette mention (demande de changement).
  - **B (UX)** : réécrire Flow 1, étape 8, pour que le bond apparaisse au tour suivant.

  Dans les deux cas, le `tools/list` réseau à l'activation émet l'événement de données sortantes hors tour (voir R-24).

### R-07 — AD-3 refuse presque tout pendant un tour ; l'UX l'autorise · **Majeur (contradiction)**

- **Référence UX** :
  - Ce que l'UX désactive pendant un tour : `composer` (« Désactivé pendant un tour […] avec la raison ») et `model-picker`. Rien d'autre.
  - Ce que l'UX laisse utilisable : `brick-card` (« effet au tour suivant »), `force-button` (« Arme l'action pour le prochain tour »), `reset-button` (« Un clic, sans confirmation »), `scenario-picker` et `edit-drawer`.
  - Conduite de session : le formateur prépare le tour suivant pendant qu'un tour de 30 s s'exécute.
- **Contradiction** : AD-3 n'accepte pendant un tour que la décision H5 et l'arrêt ; tout le reste est refusé. Pendant un tour de 20 à 30 s, le formateur verrait ses clics refusés. Aucun mécanisme n'expose non plus l'état de la session, alors que l'UX veut que les commandes désactivées donnent leur raison.
- **Correctif** (AD-3) : répartir les intentions en trois classes.
  - **(a) Acceptées à tout moment, appliquées au prochain instantané** (AD-17 isole déjà le tour en cours) : bascule de brique et de sous-option, armement et désarmement, enregistrement du prompt système.
  - **(b) Refusées pendant un tour, avec la raison** : envoi, rejeu, changement de modèle, fenêtre, bornes, modification de la mémoire globale (lue en direct à chaque appel), vider la conversation, lancer un scénario.
  - **(c) Préemptives** : décision H5, arrêt, réinitialisation (qui vaut arrêt puis réinitialisation).

  Ajouter un événement `session_state` (`idle | turn_running | awaiting_human | loading_model | diagnostic`, avec `reason_fr`) que le front utilise pour désactiver ses commandes et afficher la raison. Demande de changement à l'UX : lister les commandes désactivées pendant un tour, cohérentes avec la classe (b).

### R-08 — Canal des tokens en flux · **Majeur**

- **Référence UX** : messages en streaming (FR-1) ; `reasoning-block` (masqué ou affiché dans la vue humain, toujours visible dans Contexte LLM) ; Contexte LLM, « sortie brute (raisonnement, texte, appels d'outils) » ; `working-indicator` (« Remplacé par le texte dès que les tokens arrivent ») ; état « Streaming » (le compteur de sortie avance).
- **Lacune** : le spine ne dit pas qui découpe le flux en raisonnement (`<think>`), texte et appel d'outil (XML `qwen3_coder`). Si le front le fait, il duplique le parseur d'AD-6 et contredit AD-1. La vue humain afficherait aussi le XML de l'appel d'outil comme du texte de réponse.
- **Correctif** (AD-6 et AD-2) :
  - Le registre par famille fournit aussi un **découpeur incrémental** du flux.
  - Les événements `model_token` portent `{text, channel: reasoning|text|tool_call, index}`.
  - `model_call_ended` porte la sortie brute complète et le résultat analysé, pour que le rejeu, la comparaison et le rechargement n'aient pas à rassembler les fragments.
  - L'indicateur de travail disparaît au premier token du canal `text`, ou au premier `reasoning` si le raisonnement est affiché.

### R-09 — Modèle d'exécution concurrent · **Majeur**

- **Référence UX** : streaming, chronomètre qui avance pendant la lecture du contexte (jusqu'à 30 s), H5 « sans délai d'expiration », chargement de modèle de 5 à 20 s, mode focus et sélection utilisables pendant un tour.
- **Lacune** : le spine ne dit pas où s'exécute le tour par rapport à la boucle asyncio de FastAPI. Or llama-cpp-python est bloquant, et H5 attend sans limite. Sans règle, une story mettra l'appel au modèle dans la boucle et bloquera le flux SSE : plus de chronomètre, plus de décision H5.
- **Correctif** (nouvelle règle, ou ajout à AD-3) :
  - Chaque tour, chaque chargement de modèle et chaque diagnostic s'exécute dans **un seul fil de travail** dédié à la session.
  - Les événements passent par une file sûre entre fils vers un diffuseur asyncio, qui alimente le SSE.
  - H5 attend sur un `threading.Event`.
  - L'arrêt est un drapeau vérifié entre deux tokens et entre deux étapes. La lecture du contexte par llama.cpp n'est pas interruptible : le dire dans le message d'arrêt.
  - Aucun appel au moteur dans la boucle asyncio.

### R-10 — Données exactes affichées par H5 avant la construction de la requête · **Majeur**

- **Référence UX** : état « Validation humaine en attente » (« l'outil, la destination et les données exactes qui sortiraient du poste », boutons « Autoriser » et « Refuser ») ; `outbound-payload` (« données exactement envoyées ») ; Flow 1, étape 10.
- **Lacune** : AD-15 émet les données sortantes dans `net`, juste avant l'envoi, donc **après** `before_tool`, où H5 suspend le tour. Au moment de H5, la requête n'existe pas encore. Pour le MCP public, le JSON-RPC est même construit à l'intérieur du SDK `mcp`. Deux stories produiront un aperçu H5 et un envoi réel qui ne correspondent pas.
- **Correctif** (AD-14 et AD-15) :
  - Un outil réseau et le client MCP public exposent une étape `prepare(args) → OutboundRequest{request_id, method, url, body}`, exécutée **avant** `before_tool`. Le `payload` de `before_tool` et d'`awaiting_human` porte cette requête.
  - `net` envoie exactement cet objet et émet `outbound_sent` avec le même `request_id`.
  - Pour le MCP public, l'aperçu montre `tools/call` et ses `params` exacts. `outbound_sent` montre les octets réellement envoyés, capturés par un crochet d'événement `httpx` du client partagé.
  - Un test vérifie que les `params` de l'aperçu figurent à l'identique dans le corps envoyé.
  - Dire quels en-têtes sont montrés : méthode, adresse et corps ; aucun en-tête sensible n'existe en V1.

### R-11 — Schéma d'architecture : nœuds, flux, activité et lieu de dérivation · **Majeur**

- **Référence UX** :
  - EXPERIENCE : `arch-node-*`, `arch-flow` (halo, flux animé), clic sur un nœud (sélection) ; nœud serveur MCP ou skill dépliable (outils exposés) ; hook bloquant (« le flux s'arrête au nœud du hook ») ; H5 (« le flux […] s'arrête avant la frontière ») ; second nœud Modèle pour le sous-agent ; mémoire globale et index RAG en fichiers locaux ; serveur MCP local distinct du harnais ; Codage local / réseau (clic sur le flux qui franchit la frontière).
  - DESIGN : `arch-boundary`, `arch-node-unavailable`, `architecture-band-height` de 200 px.
- **Lacune** : AD-12 dit que le schéma est « dérivé des déclarations et de l'état » sans dire **où** (serveur ou navigateur), sans modèle de nœuds et de flux, et sans relier les événements d'activité aux nœuds et aux flux. Les hooks ne figurent pas dans les composants déclarés. La règle de visibilité est aussi ambiguë : l'UX dit « seules les briques actives, sauf les serveurs publics indisponibles », alors qu'une sous-option indisponible ne peut pas être activée.
- **Correctif** (AD-12) :
  - La session dérive le schéma, en un seul point testable par pytest, et émet `architecture_changed` avec :
    - `nodes[] {id, label_fr, brick, kind, hosting, zone: local|network, available, reason_fr?, children[]}`, où `kind` vaut `harness | model | subagent_model | tool | mcp_server | hook | file | external_model_server` et où `children[]` liste les outils du serveur ou le détail du skill ;
    - `edges[] {id, from, to, crosses_boundary}`.
  - Les hooks H1 à H5 sont des composants déclarés de la brique hooks.
  - Les événements d'activité portent `component` et, s'il y en a un, `edge`. Le navigateur allume le nœud et anime le flux, marque `blocked` au hook, ou `pending` avant la frontière pour H5.
  - Un clic sur un flux qui franchit la frontière ouvre le dernier `outbound_sent` qui porte cet `edge` dans le tour sélectionné.
  - Règle de visibilité : un composant est dessiné dès que sa brique parente est active, qu'il soit disponible ou non.
  - Mise en page : emplacements fixes par zone et par `kind`, sans bibliothèque de graphe, ce qui tient dans 200 px. Animations en CSS uniquement (voir R-19).

### R-12 — Diagnostic dans le terminal et le navigateur, port occupé, mode dégradé · **Majeur (contradiction)**

- **Référence UX** :
  - State Patterns, diagnostic :
    - les quatre lignes passent d'« En cours » à OK ou Échec ;
    - le même diagnostic s'écrit dans le terminal ;
    - si le port est indisponible, « seul le terminal parle » ;
    - un échec bloquant rend l'interface inaccessible ;
    - un échec non bloquant affiche « Continuer » ;
    - un diagnostic vert affiche « Ouvrir WaveStack » ;
    - le diagnostic reste consultable depuis la barre haute.
  - Flow 3 : le diagnostic propose les GGUF déjà présents ou un chemin à saisir.
- **Contradiction** : AD-21 dit « diagnostic (terminal, puis navigateur) », puis « démarre le serveur ». Si le diagnostic tourne avant le serveur, le navigateur ne peut pas montrer les lignes « En cours ». Si le modèle manque (échec bloquant), le spine ne dit pas si le serveur démarre, ni comment la page propose les modèles découverts d'AD-7. Rien ne conserve non plus les résultats pour l'icône de la barre haute, et un port occupé par une instance WaveStack déjà lancée n'est pas distingué d'un conflit.
- **Correctif** (AD-21 réécrit) :
  1. **Port d'abord** : `cli` tente de réserver `127.0.0.1:port`.
     - Si le port est occupé, `cli` interroge `GET /api/health`. Si une instance WaveStack répond, il ouvre le navigateur sur elle et quitte avec le code 0.
     - Sinon, il écrit dans le terminal un message français : le port en conflit, puis `uv run wavestack --port 8766` ou la clé de `settings.json`. Il quitte avec un code non nul.
  2. **Serveur en mode `diagnostic`** : il démarre aussitôt et ouvre `/diagnostic`. Les vérifications (mémoire, modèle, réseau) tournent dans le fil de travail (R-09).
  3. Chaque résultat est un événement `diagnostic_check {check, status: running|ok|failed, message_fr, action_fr, blocking}`. Le **même objet** s'affiche dans le terminal et part vers le SSE : une seule source.
  4. **Échec bloquant** : aucune session n'est créée. La page liste les candidats d'AD-7 et un champ de chemin, via l'intention `select_model`, puis relance la vérification du modèle sans redémarrer. La voie « relancer WaveStack » de Flow 3 reste valable.
  5. `GET /api/diagnostic` conserve le dernier résultat, pour l'icône de la barre haute.
  6. Le téléchargement du modèle par défaut affiche sa progression chiffrée dans la ligne « Modèle ».
  7. Définitions :
     - la vérification mémoire compare la RAM disponible (`psutil`) au coût estimé par le `LoadRegistry` pour le modèle par défaut ;
     - la vérification réseau est une donnée sortante (voir R-24).

### R-13 — Changement de modèle entre deux tours, conversation conservée · **Moyen**

- **Référence UX** : `model-picker` et état « Changement de modèle en cours » (« conversation conservée », « faisabilité à confirmer en architecture ») ; FR-33 (briques qui passent indisponibles).
- **Lacune** : le spine ne confirme pas la faisabilité demandée par l'UX. Il ne dit pas sous quelle forme l'historique est conservé, alors que le gabarit et le format d'appel d'outils changent avec la famille. Il ne dit pas non plus ce qui se passe si le nouveau modèle est refusé ou échoue après la libération de l'ancien, puisqu'AD-8 interdit d'avoir deux modèles en même temps.
- **Correctif** (AD-4, AD-8 et AD-17) :
  - L'historique est stocké **structuré** (rôle, contenu, raisonnement, appels d'outils analysés, résultats), jamais en texte rendu. Il est rendu à chaque appel avec le gabarit du modèle actif : la conservation est acquise par construction.
  - Séquence de changement :
    1. Estimation du nouveau modèle par le `LoadRegistry`, l'ancien étant compté comme libéré. En cas de refus, l'ancien reste chargé.
    2. `close()` de l'ancien, puis chargement du nouveau.
    3. En cas d'échec, rechargement de l'ancien et `harness_error`.
    4. Réévaluation des capacités et des disponibilités.
  - Le changement émet `model_load_started` et `model_load_ended`, ainsi que `session_state = loading_model`.

### R-14 — API de lecture et état initial au rechargement · **Moyen**

- **Référence UX** :
  - `model-picker` : modèles découverts, incompatibles avec leur raison, serveurs, taille (« 2B ») ;
  - `scenario-picker` : programme par modules ;
  - `brick-card` : explications, sous-options ;
  - `edit-drawer` : entrées de la mémoire globale ;
  - prompts suggérés ;
  - état « Aucun tour » : la jauge montre la fenêtre avant tout appel.
- **Lacune** : AD-1 évoque « une réponse de lecture de l'API construite à partir du journal » sans en donner la liste. Au rechargement, le seul mécanisme prévu est la relecture du SSE depuis `seq = 0`, qui relit chaque token de chaque tour.
- **Correctif** (AD-18) — contrat minimal :
  - `GET /api/state` renvoie la projection courante et `last_seq` : briques (déclarations, disponibilité, modifications en attente), actions armées, réglages, modèle actif, scénario, schéma, `session_state` et liste des tours.
  - `GET /api/models` (AD-7), `GET /api/scenarios`, `GET /api/memory`, `GET /api/diagnostic`.
  - `GET /api/turns/{turn_id}` renvoie les événements d'un tour (comparaison).
  - Le SSE utilise `id: seq`, et la reconnexion native `Last-Event-ID`.
  - Au rechargement : `state`, puis SSE à partir de `last_seq + 1`.

### R-15 — Rejeu : branche active, comparaison, tours après réinitialisation · **Moyen**

- **Référence UX** : état « Rejeu » (le tour rejoué exclut la question d'origine ; « la conversation continue à partir du tour rejoué » ; les deux tours restent consultables) ; badge « Rejeu » qui ouvre la comparaison ; `turn-compare` (tour rejoué contre tour d'origine par défaut ; tokens d'entrée et de sortie, temps) ; sélecteur « Tour 1, Tour 2… » ; réinitialisation et « Vider la conversation ».
- **Lacune** :
  - Aucun champ `replay_of`.
  - Rien ne dit quels tours composent l'historique courant : après un rejeu, le tour d'origine sort de l'historique mais reste dans le journal, et la vue humain ne sait pas quoi afficher.
  - Un tour compte jusqu'à 6 appels, et le spine ne dit pas quel contexte comparer.
  - Le devenir des tours du journal après réinitialisation, vidage ou lancement de scénario n'est pas fixé, alors que le rechargement relit tout.
- **Correctif** (AD-17) :
  - `turn_started` porte `replay_of?`, `history_turn_ids[]` et `display_n`.
  - `turn_ended` porte `input_tokens` (dernier appel), `output_tokens` (somme), `duration_ms` et `calls`.
  - La comparaison aligne par index d'appel, le dernier appel par défaut, et par `source_key` (R-04).
  - Réinitialisation, vidage et scénario émettent `conversation_cleared` ou `session_reset`, avec un numéro d'`epoch`. Le journal reste en ajout seul et `turn_id` reste unique. Le sélecteur de tours et la comparaison ne montrent que l'`epoch` courante, et le numéro d'affichage repart à 1.

### R-16 — Appel mal formé : partie fautive et numéro d'essai · **Moyen**

- **Référence UX** : état « Appel d'outil mal formé » (« sortie brute du modèle, partie fautive signalée, réaction du harnais ») ; Voice and Tone (« essai 2 sur 3 »).
- **Lacune** : AD-6 et AD-14 ne donnent pas de contrat de retour au parseur. Sans position de l'erreur, le front ne peut pas signaler la partie fautive sans analyser la sortie lui-même.
- **Correctif** (AD-6) : le parseur renvoie `ParseResult{calls[], error?: {message_fr, span: [start, end]}}`, où la plage se situe dans la sortie brute. L'événement `tool_call_malformed` porte `call`, `span`, `reaction: retry|reinjected|stopped`, `attempt` et `max_attempts`. Avec 2 nouveaux essais, `max_attempts` vaut 3, ce qui est cohérent avec AD-10.

### R-17 — Magasin de projection indépendant des volets masqués · **Moyen**

- **Référence UX** : Interaction Primitives (sélection synchronisée ; « Volet masqué qui contient un élément lié → sa puce le signale ») ; `pane-chip` (marque « lié ») ; mode focus (les volets réduits gardent leur signal d'état).
- **Lacune** : AD-1 classe la sélection parmi les « projections côté navigateur », mais rien n'impose qu'un volet masqué continue d'être projeté. Si une story démonte les volets masqués, la marque « lié » devient impossible. Les relations de sélection (segment → nœud, nœud → segments) n'ont pas non plus de source déclarée.
- **Correctif** (AD-18) :
  - Le navigateur tient **un seul magasin de projection**, alimenté par le SSE et indépendant de l'affichage. Les volets n'en sont que des vues ; masquer ou réduire un volet ne suspend pas sa projection.
  - La sélection est un objet `{type: segment|brick|node|edge|turn|step, id}`.
  - Les liens se déduisent **uniquement** des champs `brick`, `component`, `turn_id`, `call` et `step_id` (R-01, R-04).

### R-18 — Tokens de design sans compilation, polices locales et licences · **Mineur**

- **Référence UX** : DESIGN, en-tête YAML (couleurs, typographie, espacements, composants) ; Typography (Aptos avec Inter en repli embarqué, Manrope à chiffres tabulaires, Cascadia Mono avec Consolas en repli, « toutes les polices non système sont servies en local ») ; Do's and Don'ts (aucun CDN) ; NFR-9 (paliers de 100, 125 et 150 %).
- **Lacune** :
  - Le spine ne dit pas comment les tokens de DESIGN.md deviennent du CSS sans étape de compilation.
  - AD-18 place les polices sous `static/vendor`, alors que l'arborescence montre `static/fonts` : c'est une contradiction interne.
  - **Aptos est une police Microsoft propriétaire** : elle ne doit jamais être recopiée dans le dépôt (NFR-10), seulement appelée par `local()`. Inter et Manrope sont sous OFL et doivent être embarquées **avec leur licence**. Cascadia Mono est sous OFL : l'embarquer si sa présence sur tous les postes Windows 11 n'est pas confirmée.
  - La présence de chiffres tabulaires (`tnum`) dans Manrope est à vérifier.
  - Rien n'indique comment la taille de texte s'applique aussi aux libellés SVG du schéma.
- **Correctif** (AD-18 et arborescence) :
  - `static/tokens.css` est tenu à la main, avec des variables CSS de mêmes noms et mêmes valeurs que DESIGN.md. Un test pytest lit l'en-tête YAML de DESIGN.md et vérifie chaque token.
  - Polices dans `static/vendor/fonts/`, avec leurs fichiers de licence. `@font-face` appelle `local('Aptos')`, jamais un fichier Aptos.
  - La taille de texte est une variable `--text-scale`, appliquée à la rampe typographique et aux libellés SVG.
  - Corriger l'arborescence pour qu'elle corresponde à AD-18.

### R-19 — Gravité et annonce des événements ; mouvement réduit · **Mineur**

- **Référence UX** :
  - Accessibility Floor : événements de blocage, d'échec et de dépassement annoncés dès qu'ils surviennent ; réponse annoncée en fin de tour ; `prefers-reduced-motion`.
  - `harness-event` : rouge pour blocage et échec, violet pour information.
  - Clavier : `Entrée`, `Maj+Entrée`, `Échap`, raccourcis de mode focus.
- **Lacune** : aucun champ ne porte la gravité. Le front devra maintenir sa propre liste de `kind` « rouges » et « à annoncer », en double du catalogue. Le spine ne précise pas non plus comment le schéma s'anime, alors qu'une animation en JS (`requestAnimationFrame`) ou SMIL échapperait à la requête média.
- **Correctif** :
  - La base du `payload` des événements du harnais porte `severity: info|blocked|error` et `announce: bool`, décidés en Python.
  - AD-18 : les animations du schéma et de l'indicateur sont **uniquement en CSS**, et `@media (prefers-reduced-motion)` les remplace par une surbrillance fixe.
  - Le clavier ne demande rien à l'architecture ; il relève du front seul.

### R-20 — Commandes du spine absentes de l'UX ; périmètre de la réinitialisation · **Mineur (demande de changement à l'UX)**

- **Référence UX** : barre haute et `brick-card` (liste des sous-options) ; `reset-button` et état « Réinitialisation ».
- **Lacune** :
  - AD-9 rend la fenêtre réglable « dans l'interface ». AD-10 ajoute une sous-option « boucle agent » à la brique outils. AD-3 prévoit une intention d'arrêt du tour. L'UX ne place aucune de ces trois commandes.
  - Le périmètre de la réinitialisation n'est pas le même : le spine dit « recharge l'état initial depuis `content/` », l'UX dit « LLM nu, conversation vide, mémoire restaurée ». Ni l'un ni l'autre ne dit si le modèle actif, la fenêtre, les bornes, le prompt système modifié et les actions armées sont remis à zéro.
- **Correctif** :
  - AD-17 énumère ce que la réinitialisation remet à zéro : briques éteintes, conversation, mémoire de démonstration, prompt système par défaut, actions armées vidées.
  - Elle conserve le modèle actif, la fenêtre, les bornes et, côté navigateur, les volets et la taille de texte.
  - Demande de changement à l'UX : placer le réglage de fenêtre (par exemple dans le détail de la jauge), la sous-option « boucle agent » et un bouton « Arrêter le tour » dans l'en-tête d'Orchestration.

### R-21 — Scénario qui demande une brique indisponible · **Mineur**

- **Référence UX** : `scenario-picker` (« un clic applique sa configuration de briques ») ; Flow 1 et Flow 4, cas sans réseau.
- **Lacune** : rien ne dit ce qui se passe quand un scénario active une brique ou un serveur indisponible.
- **Correctif** (AD-19) : la session applique ce qui est disponible et émet `scenario_applied {scenario, skipped: [{brick, component?, reason_fr}]}`. Le composant reste dessiné comme indisponible, selon la règle de visibilité de R-11.

### R-22 — « Lecture du contexte (N tokens) » et cache de préfixe · **Mineur**

- **Référence UX** : `working-indicator` (« Lecture du contexte (1 840 tokens) ») ; principe « rien n'est masqué » et NFR-1 (latence visible).
- **Lacune** : llama-cpp-python réutilise le préfixe du contexte déjà en cache. Afficher 1 840 tokens alors que 200 seulement sont relus rendrait le chronomètre trompeur. Le memlog note aussi que le modèle hybride relit probablement tout le contexte, notamment après une délégation au sous-agent.
- **Correctif** : `model_call_started` porte `prompt_tokens` et `cached_tokens`, que l'adaptateur mesure quand c'est possible. Le libellé devient « Lecture du contexte (1 840 tokens, dont 1 640 déjà en cache) ».

### R-23 — AD-1 « ne recalcule ni tokens » contre les écarts et le chronomètre · **Mineur (contradiction)**

- **Référence UX** : `turn-compare` (« écarts de tokens d'entrée, de sortie et de temps », + / −) ; chronomètre ; légende du détail de la jauge (pourcentages).
- **Contradiction** : lue strictement, AD-1 interdit au front de calculer une différence ou de faire tourner un chronomètre.
- **Correctif** (AD-1) : « L'interface n'estime ni ne tokenise rien. Elle peut faire de l'arithmétique simple (somme, différence, pourcentage) sur des valeurs émises par le harnais, et faire avancer un chronomètre à partir d'un `ts`. »

### R-24 — Données sortantes hors tour · **Mineur**

- **Référence UX** : `outbound-payload` (placé dans une étape d'Orchestration) ; principe « tout ce que fait le harnais est visible ».
- **Lacune** : AD-15 émet un événement de données sortantes pour toute destination hors boucle locale. Certaines sorties n'appartiennent pourtant à aucun tour : `initialize` et `tools/list` du MCP public au démarrage ou à l'activation (R-06), sonde réseau du diagnostic, téléchargement Hugging Face. L'UX ne leur donne aucun emplacement.
- **Correctif** : ces événements ont `turn_id = null` et sont conservés dans le journal (ou dans le diagnostic avant la création de la session). Demande de changement à l'UX : un groupe « Hors tour » en tête d'Orchestration, ou un lien depuis la ligne de diagnostic.

---

## Points conformes

- **AD-1 et AD-2** : paradigme journal et projection, `actor` qui alimente les badges « Déclenché par le modèle » et « Forcé par l'utilisateur » et la mention « Décision du harnais ».
- **AD-3** : sélecteur de modèle désactivé pendant un tour, conforme au `model-picker`.
- **AD-9** : dépassement sans envoi, jauge plafonnée à la fenêtre et non à la taille native (sous réserve de R-03).
- **AD-11** : second nœud Modèle et `context_id` distinct ; la jauge reste sur `main`, conforme à l'hypothèse de l'UX.
- **AD-13** : H5 sans délai d'expiration, refus réinjecté, tour qui continue.
- **AD-15** : aucune télémétrie ; données sortantes émises avant l'envoi (sous réserve de R-10).
- **AD-16** : serveur MCP public indisponible jusqu'au redémarrage, les autres serveurs restent utilisables ; aucune erreur brute en anglais.
- **AD-17** : le rejeu exclut la question et la réponse d'origine ; la mémoire globale courante est utilisée.
- **AD-18** : `localStorage` pour les volets, la taille de texte et le mode focus ; aucun CDN ; écoute sur `127.0.0.1` seulement.
- **AD-20** : mémoire globale et journal d'audit dessinés comme fichiers locaux.
- **Clavier, mode focus, mouvement réduit** : entièrement côté front, sans exigence d'architecture en dehors de R-19.

## Étape suivante recommandée

- **Skill** : `bmad-architecture` (mise à jour du spine)
- **Prompt** : « Mets à jour ARCHITECTURE-SPINE.md de WaveStack à partir de reviews/review-reconcile-ux.md : d'abord R-01 (enveloppe), R-03, R-07 et R-12 (contradictions), puis les majeurs. Tranche R-06 (aperçu du contexte contre modification de Flow 1) avec moi. Consigne les décisions dans .memlog.md et liste les demandes de changement à l'UX (R-06, R-07, R-20, R-24). »
- **Modèle** : Opus
- **Effort** : high
- Ouvrir un nouveau chat (`/clear`) avant cette étape.
