---
reviewed: ARCHITECTURE-SPINE.md (WaveStack, draft du 2026-09-23)
lens: grille « bon spine » (contrat de cohérence)
date: 2026-09-23
---

# Revue du spine d'architecture WaveStack

## Verdict

Le spine est solide sur le cœur métier (journal d'événements, texte brut, exécuteur unique, budget mémoire, bornes de boucle). Il n'est pas prêt pour les epics : l'enveloppe opérationnelle comporte des trous qui laisseront des stories diverger. Il manque le modèle de concurrence (appel llama-cpp bloquant, flux, arrêt), le bac à sable de l'outil de lecture de fichier, la méthode déterministe de rendu et de comptage des segments, et une règle réseau réellement applicable aux bibliothèques tierces. Il faut une révision ciblée (3 AD nouveaux, 5 AD précisés), pas une refonte.

Échelle : **Critique** (bloque les epics) · **Haute** (divergence ou faille probable) · **Moyenne** (divergence possible, à trancher avant la story concernée) · **Basse** (hygiène).

## Synthèse

| # | Sévérité | Emplacement | Sujet |
|---|---|---|---|
| 1 | Critique | Absent (AD-3, AD-5, AD-11, AD-13) | Modèle de concurrence : async, appel bloquant, flux, arrêt |
| 2 | Critique | AD-14, FR-13, H1 (AD-13) | Outil de lecture de fichier sans bac à sable (traversée de chemin) |
| 3 | Haute | AD-4 | Ordre des segments, rôles, méthode de comptage, environnement Jinja non fixés |
| 4 | Haute | AD-15, AD-21, AD-22 | « Seul `net` ouvre des connexions » inapplicable aux bibliothèques tierces |
| 5 | Haute | AD-15, AD-13 (H5), FR-20 | H5 et « données sortantes » au mauvais niveau ; connexion MCP public au démarrage contraire à NFR-4 |
| 6 | Haute | AD-18, AD-3 | Sécurité de l'API locale : Host/Origin, CSRF, rebinding DNS, SSRF vers la boucle locale |
| 7 | Haute | AD-3, AD-10, AD-17, diagramme du tour | Moment d'exécution des actions armées (FR-42) non fixé |
| 8 | Moyenne | Diagramme de dépendances | Flèches manquantes ; émission d'événements sans émetteur injecté |
| 9 | Moyenne | AD-2 | Cycle de vie du journal (réinitialisation, redémarrage) et granularité des tokens en flux |
| 10 | Moyenne | AD-21 | Installation et mise à jour : `uv.lock`, certificats, Python géré, procédure de mise à jour |
| 11 | Moyenne | AD-6, AD-5 | Registre sans séquences d'arrêt ni extracteur de raisonnement ; BOS mieux garanti par des ids |
| 12 | Moyenne | AD-9, Deferred | Performance : réutilisation du préfixe KV non décidée, alors qu'elle conditionne NFR-1 |
| 13 | Moyenne | AD-8, AD-21 | Processus enfant MCP : budget mémoire, cycle de vie, arrêt propre |
| 14 | Basse | Diagramme « Déroulé d'un tour » | Branches manquantes : H5, arrêt, `harness_error`, borne avant appel |
| 15 | Basse | Capability map | NFR-5, 6, 7, 9, 10 et 11 liés dans `binds` mais absents de la carte |
| 16 | Basse | Stack, Deferred, diagramme de processus | Versions, redondance possible, rationale résiduelle, échappement Mermaid |

---

## Constats détaillés

### 1. Modèle de concurrence absent — Critique

- **Emplacement :** aucun AD ; touche AD-3 (arrêt du tour), AD-5 (`complete(... stream)`), AD-11 (suspension), AD-13 (attente H5 sans délai).
- **Problème :** l'axe concurrence de l'altitude n'est ni décidé ni différé. Plusieurs points restent ouverts :
  - FastAPI et le SDK `mcp` sont asynchrones (anyio). `llama-cpp-python` est bloquant, sans sûreté entre threads, et le chargement d'un modèle prend de 5 à 20 s.
  - Rien ne dit si le tour est une coroutine ou un thread, comment les tokens rejoignent le flux SSE, ni comment l'intention « arrêt » interrompt une génération en cours, une attente H5, un appel réseau ou un appel MCP.
  - Rien ne dit ce que devient la sortie partielle d'un tour arrêté.

  Sans règle, la story « flux de tokens » bloquera la boucle d'événements (SSE figé pendant la génération). La story « MCP » appellera du code asynchrone depuis un thread. La story « arrêt » inventera sa propre sémantique.
- **Correction :** ajouter un **AD-23 — Modèle d'exécution et arrêt** :
  - Le tour est une coroutine unique sur la boucle d'uvicorn, protégée par un verrou de tour (`asyncio.Lock`, ce qui applique « un seul tour à la fois »).
  - Tout appel bloquant passe par `anyio.to_thread.run_sync` avec un **limiteur d'inférence à 1 place**, partagé par le LLM, l'embedding, le reranking, `tokenize` et le chargement : `models`, `rag`, `context`, lecture de fichier, `sqlite-vec`.
  - Les tokens passent du thread d'inférence à la coroutine par une file (`anyio.from_thread` ou `asyncio.Queue` + `call_soon_threadsafe`).
  - **Arrêt :** un jeton d'annulation est vérifié entre chaque token (l'adaptateur abandonne l'itérateur puis appelle `reset`) ; les attentes H5, réseau et MCP sont annulées par une annulation de portée anyio.
  - Un tour arrêté émet `turn_stopped`. La sortie partielle reste visible dans la trace, mais **n'entre pas** dans l'historique.
  - Le chargement ou le changement de modèle passe par le même verrou : jamais pendant un tour.
  - Ajouter `cancel` au contrat `Engine.complete` (AD-5).

### 2. Outil de lecture de fichier sans bac à sable — Critique

- **Emplacement :** AD-14 (outils), FR-13 (« lecture de fichier dans un dossier de démonstration »), H1 (AD-13).
- **Problème :**
  - Le seul contrôle d'accès évoqué est H1, un hook **désactivable** par conception.
  - H1 désactivé, un argument du modèle comme `../../../Users/x/.ssh/id_rsa`, un chemin absolu, un lien symbolique ou une jonction NTFS lit n'importe quel fichier du poste. Ce fichier entre alors dans le contexte et peut sortir ensuite par un outil réseau.
  - Deux stories (outil, H1) risquent en plus de comparer des chemins de façons différentes (casse Windows, `/` contre `\`).
- **Correction :** ajouter une règle dans AD-14, ou un **AD-24 — Bac à sable des fichiers** :
  - L'outil résout `(root / arg).resolve(strict=True)` avec `root = content/demo_files`. Il refuse si `not resolved.is_relative_to(root.resolve())`, si le chemin est absolu, UNC (`\\`) ou contient `:` (flux ADS).
  - Il plafonne la taille lue. Le refus est un `harness_error` en français.
  - Ce contrôle est **dans l'outil, toujours actif, et indépendant des briques**.
  - H1 ne fait que bloquer le sous-dossier `confidentiel/` **à l'intérieur** du bac à sable, et réutilise la même fonction de résolution (exposée par `tools`).
  - Ajouter un test pytest de traversée : `..`, chemin absolu, lien symbolique, casse.
  - Au passage : la calculatrice n'utilise jamais `eval`. Elle passe par l'AST avec une liste blanche d'opérateurs.

### 3. AD-4 : rendu et comptage non déterministes entre stories — Haute

- **Emplacement :** AD-4.
- **Problème :** la règle fixe le résultat (somme des segments = total), mais pas la méthode. Quatre points de divergence restent ouverts :
  - **Ordre et rôle des segments.** Qui décide qu'un extrait RAG va dans le message système ou utilisateur, et où s'insèrent H3, la mémoire globale et les descriptions de skills ? Chaque brique choisira.
  - **Descriptions d'outils.** Elles sont rendues **par le gabarit** à partir de la variable `tools`, pas par la brique. Leur texte de segment n'existe donc qu'après rendu.
  - **Comptage.** Tokeniser chaque segment séparément ne donne pas le même total que tokeniser le texte rendu (fusions BPE aux frontières). La règle « la somme égale le total » ne peut donc pas être tenue par une méthode naïve.
  - **Environnement Jinja.** Les gabarits GGUF supposent l'environnement de `transformers` : `ImmutableSandboxedEnvironment`, `trim_blocks`, `lstrip_blocks`, extension `loopcontrols`, `raise_exception`, `strftime_now`, `tojson` sans échappement ASCII. Un autre environnement produit un texte différent de celui prévu par le modèle.
- **Correction :** préciser AD-4.
  - **Emplacements fixes**, tenus par `context` et non par les briques. Ordre : système [prompt système → mémoire globale → descriptions de skills → contenus de skills déclenchés], variable `tools`, historique, extraits RAG et injections de hook dans le message utilisateur courant, puis tours assistant/outil du tour en cours. Une brique déclare son emplacement, jamais une position.
  - **Méthode de comptage unique :** rendre une fois avec des marqueurs sentinelles autour de chaque segment, relever les intervalles de caractères, retirer les marqueurs, tokeniser **une seule fois** le texte final, reconstruire les décalages par `token_to_piece`, puis attribuer chaque token au segment qui contient son premier caractère. Le reste va à « Message et gabarit ». Le bloc `tools` est repéré de la même façon.
  - **Environnement Jinja** : figé dans `context` et identique à celui de `transformers` (liste ci-dessus). Un test compare le rendu à une référence enregistrée pour Qwen3.5.

### 4. AD-15 inapplicable aux bibliothèques tierces — Haute

- **Emplacement :** AD-15 (« Seul `net` ouvre des connexions HTTP »), AD-21 (`huggingface_hub`), AD-22 (headroom-ai, repli fastembed).
- **Problème :** plusieurs dépendances ouvrent leurs propres connexions, hors de `net`, sans trace ni liste d'adresses autorisées. Cela contredit AD-15, NFR-3 (aucune télémétrie) et NFR-4 :
  - `huggingface_hub` (télémétrie, appels HEAD) ;
  - `mcp` si on ne lui passe pas le client ;
  - headroom-ai, qui tire `litellm` (téléchargement de la table des coûts depuis GitHub à l'import, sauf `LITELLM_LOCAL_MODEL_COST_MAP=True`) et télécharge ONNX Runtime depuis `cdn.pyke.io` à l'exécution (noté dans le memlog, absent du spine) ;
  - fastembed, qui télécharge ses modèles.

  La règle actuelle ne peut pas être tenue par une story qui ajoute une dépendance.
- **Correction :** réécrire AD-15 en deux volets.
  1. **Code du projet :** tout passe par `net`. `mcp` reçoit la fabrique de client de `net`, et `huggingface_hub` reçoit le client de `net` par sa fabrique de client httpx (à vérifier en 1.32), sinon il est appelé uniquement depuis `net`.
  2. **Dépendances :** `cli` pose avant tout import `HF_HUB_DISABLE_TELEMETRY=1`, `LITELLM_LOCAL_MODEL_COST_MAP=True`, `DO_NOT_TRACK=1`, et `HF_HUB_OFFLINE=1` hors téléchargement explicite. Toute nouvelle dépendance est auditée pour ses accès réseau (ajouter une ligne « Réseau » à la convention Licences). Un test pytest lance un tour complet avec `socket.connect` bloqué hors boucle locale.
  - Ajouter au critère de sortie du test préalable Headroom (Deferred) : « aucune connexion réseau à l'import ni à l'exécution ».

### 5. H5 et « données sortantes » au mauvais niveau ; connexion MCP au démarrage — Haute

- **Emplacement :** AD-15, AD-13 (H5 en `before_tool`), AD-16 (« au démarrage »), FR-20, FR-27 H5, NFR-4.
- **Problème :**
  - **Charge exacte inconnue.** H5 doit montrer « les données qui sortiraient du poste » **avant** l'exécution. Or seul `net` connaît la charge exacte, au moment de l'envoi, et pour le MCP public c'est le SDK qui sérialise le JSON-RPC. La story hooks et la story outils ou MCP vont diverger : H5 affichera les arguments, pas la requête réelle.
  - **Fuite au démarrage.** AD-16 parle d'un serveur MCP public qui « ne répond pas au démarrage ». Si « démarrage » désigne le lancement de l'application, `initialize` et `tools/list` partent vers data.gouv.fr et Microsoft Learn sans brique réseau activée, ce qui contredit NFR-4.
- **Correction :**
  - Dans AD-15 : `net` émet `outbound_request` depuis un crochet `request` de httpx (corps exact). Si H5 est actif pour la requête courante, il **attend la décision au même point**, avant l'envoi. H5 est donc une porte appelée par `net`, déclarée comme hook `before_tool` pour l'affichage, mais décidée sur la requête réelle.
  - Dans AD-16 : un serveur MCP public se connecte **à l'activation de sa brique**, jamais au lancement.
  - Le test réseau du diagnostic (FR-37) vise une seule adresse fixe de la liste autorisée, et il est affiché.

### 6. Sécurité de l'API locale — Haute

- **Emplacement :** AD-18 (écoute sur `127.0.0.1`), AD-3 (intentions `POST`), Conventions (réglages écrits par intention).
- **Problème :** écouter sur la boucle locale ne protège pas du navigateur lui-même.
  - Une page web ouverte dans un autre onglet peut viser `127.0.0.1:port` : `POST` en `text/plain` ou formulaire (CSRF), ou rebinding DNS pour lire le flux SSE (qui contient le contexte et la mémoire).
  - Si les intentions peuvent modifier `settings.json`, et donc la liste d'adresses autorisées, une page tierce peut ouvrir la sortie de données.
  - Enfin, l'outil « page web » peut viser la boucle locale (API WaveStack, Ollama), car AD-15 exempte la boucle locale de toute règle (SSRF). Les redirections HTTP ne sont pas revérifiées contre la liste autorisée.
- **Correction :** dans AD-18 :
  - `TrustedHostMiddleware` limité à `127.0.0.1` et `localhost:<port>` ;
  - refus de tout `POST` dont l'`Origin` n'est pas l'origine de l'application ;
  - intentions acceptées en `application/json` seulement ;
  - aucun en-tête CORS.

  Dans AD-15 :
  - la liste d'adresses autorisées vient **uniquement** de `wavestack.toml` ou de `settings.json` édité à la main, **jamais d'une intention** ;
  - l'exemption de boucle locale est réservée aux adaptateurs de modèle et à la découverte (AD-5, AD-7) ; les outils ne visent jamais la boucle locale ;
  - chaque redirection est revérifiée contre la liste (`follow_redirects=False` et suivi manuel borné).

### 7. Moment d'exécution des actions armées (FR-42) — Haute

- **Emplacement :** AD-3 (« actions armées »), AD-10 (« ne consomme pas d'appel »), AD-17 (rejeu), diagramme « Déroulé d'un tour » (branche « appel d'outil / action forcée » sous la sortie du modèle).
- **Problème :** le diagramme place l'action forcée **dans la sortie du modèle**, ce qui n'a pas de sens pour une action armée par l'utilisateur avant le tour. Le moment d'exécution change le résultat selon l'action :
  - skill chargé avant le premier appel, ou après ;
  - lecture du fichier sensible avant l'appel, ou à la place d'un appel d'outil ;
  - écriture en mémoire globale avant ou après la réponse.

  Chaque story FR-12, 21, 24, 29 choisira différemment.
- **Correction :** ajouter une règle à AD-3 ou AD-14.
  - Les actions armées s'exécutent **une fois**, après `on_user_message` et avant le premier `assemble_context`, dans l'ordre d'armement, par l'exécuteur unique, avec `actor = user`. Leurs résultats deviennent des segments de leur brique.
  - Exception : l'écriture en mémoire globale forcée s'exécute en fin de tour, avant `on_turn_end`.
  - Les actions sont consommées à la fin du tour et copiées dans l'instantané pour le rejeu.
  - Corriger le diagramme : un nœud « actions armées » entre C et D.

### 8. Graphe de dépendances incomplet ; émission sans émetteur injecté — Moyenne

- **Emplacement :** diagramme « Design Paradigm » et règle « les flèches ne remontent jamais ».
- **Problème :** le graphe fait office de règle d'import, mais il manque des arêtes indispensables, qui seront donc « interdites » : `net → trace` (AD-15 émet), `session → hooks`, `session → tools` (actions forcées), `session → models` (changement de modèle, `LoadRegistry`), `rag → models` (AD-22), `web → trace`, `* → config`, `cli`. Par ailleurs, `trace` n'importe rien et `seq` est « strictement croissant par session » : qui alloue `seq`, et comment `net`, `tools` ou `hooks` émettent-ils ? Un module global, ou un émetteur injecté ? Les stories feront les deux.
- **Correction :**
  - Compléter le graphe avec les arêtes ci-dessus.
  - Ajouter à AD-2 : « `trace` définit l'enveloppe et un protocole `Emit`. La `Session` possède l'unique `EventLog` : allocation de `seq` sous verrou, sûre entre threads (constat 1). Tout module reçoit `emit` par injection ; aucun journal global. »

### 9. Cycle de vie du journal et granularité du flux — Moyenne

- **Emplacement :** AD-2, AD-17 (réinitialisation), FR-1.
- **Problème :**
  - Le spine ne dit pas où vit le journal (mémoire seule ?), ni ce qu'il devient à la réinitialisation (vidé ? `seq` repart à 0 ?) ou au redémarrage du processus. Un navigateur qui reprend avec un ancien `seq` rejouera alors un journal qui n'est plus le bon.
  - La granularité des tokens n'est pas fixée : un événement par token, ou par paquet ? Et le texte complet est-il répété en fin d'appel ? Le front et le moteur diverge­ront.
- **Correction :** dans AD-2 :
  - Journal **en mémoire uniquement**, perdu au redémarrage ; la réinitialisation émet `session_reset` et `seq` continue.
  - La poignée de main SSE envoie un `instance_id` (UUID du processus) : s'il change, le client repart de 0.
  - Les tokens passent en `model_delta` groupés toutes les ~50 ms. `model_call_finished` porte la sortie brute complète, pour que les projections n'aient jamais à concaténer.

### 10. Installation, mise à jour, distribution — Moyenne

- **Emplacement :** AD-21, Deferred (CI).
- **Problème :** l'axe « installer, mettre à jour, distribuer » est à moitié décidé.
  - Rien sur `uv.lock` (versionné ? `uv sync --locked` ?).
  - Rien sur la syntaxe exacte de l'index épinglé.
  - Rien sur `requires-python`.
  - Rien sur les certificats d'entreprise pour `uv` lui-même : le memlog note `UV_SYSTEM_CERTS` / `--system-certs`, mais le spine ne le dit pas, alors que c'est le premier échec probable derrière un proxy TLS.
  - Rien sur le téléchargement de Python par `uv` (GitHub, bloqué par certains proxys).
  - Aucune procédure de mise à jour, et aucune version affichée.
- **Correction :** compléter AD-21 :
  - `uv.lock` versionné ; installation et mise à jour par `git pull` (ou nouveau zip) puis `uv sync --locked`, que `uv run` fait implicitement ;
  - `requires-python = "==3.13.*"` ;
  - `[[tool.uv.index]] name = "llama-cpu", url = …, explicit = true` + `[tool.uv.sources] llama-cpp-python = { index = "llama-cpu" }` + `[tool.uv] no-build-package = ["llama-cpp-python"]` ;
  - README : `UV_SYSTEM_CERTS=1` en premier recours derrière un proxy, et `UV_PYTHON_INSTALL_MIRROR` si GitHub est bloqué ;
  - le diagnostic affiche la version de WaveStack (métadonnées du paquet) et le commit si disponible.

### 11. Registre des capacités incomplet ; BOS — Moyenne

- **Emplacement :** AD-6, AD-5.
- **Problème :**
  - Le registre fixe le parseur d'appels et la **variable** de raisonnement, mais pas les **séquences d'arrêt** (`<|im_end|>`…), que `complete(stop=…)` exige, ni l'**extracteur** du raisonnement (séparer `<think>…</think>` du texte, en flux). Chaque story (FR-9, FR-14, sous-agent) les codera à sa façon.
  - « Neutraliser le BOS » est laissé à chaque adaptateur, ce qui est fragile.
- **Correction :**
  - Ajouter au registre d'AD-6 : `stop_sequences`, `reasoning_extractor` (fonction de flux) et `tool_call_parser`.
  - Dans AD-5 : les adaptateurs qui l'acceptent (`llama_cpp`, `llama_server`) reçoivent **les ids déjà tokenisés par le harnais** (ceux du constat 3) : identité garantie par construction. `ollama_raw` reçoit la chaîne, et un test vérifie `prompt_eval_count == len(ids)`.

### 12. Performance : réutilisation du préfixe KV — Moyenne

- **Emplacement :** AD-9, AD-11, Deferred (valeur de la fenêtre).
- **Problème :** NFR-1 impose un premier token en moins de 30 s à chaque appel. Or, à 60 tokens/s (bas de l'estimation), 3 584 tokens de contexte donnent environ 60 s **si tout le contexte est relu à chaque appel**. Le memlog note que Qwen3.5 est hybride et que réécrire le début force probablement une relecture complète. La réutilisation du préfixe, et donc un ordre de segments stable (constat 3), conditionne NFR-1. Pourtant, rien ne l'impose, et le critère de décision de la fenêtre n'est pas écrit.
- **Correction :**
  - Dans AD-9 : « les segments stables précèdent les segments variables (constat 3) ; aucune brique n'insère de contenu variable dans le message système ».
  - Dans Deferred : le banc sur le poste de référence mesure (a) le temps de lecture de 4 096 tokens à froid, (b) le gain de préfixe entre deux appels du même tour. La fenêtre par défaut est la plus grande qui tient 30 s **à froid**.

### 13. Processus enfant MCP : budget et cycle de vie — Moyenne

- **Emplacement :** AD-8, AD-21, NFR-2 (le périmètre inclut les serveurs MCP locaux).
- **Problème :**
  - Le `LoadRegistry` ignore l'interpréteur enfant du serveur MCP local (plusieurs dizaines de Mo) et le socle du processus principal (Python, FastAPI, pydantic). Le budget de 4 Go sera dépassé sans refus.
  - Rien ne dit quand l'enfant démarre (au lancement ou à l'activation), ni comment on l'arrête : sous Windows, un Ctrl+C peut laisser un orphelin.
- **Correction :**
  - Dans AD-8 : le registre compte un **socle fixe** (mesuré, par défaut 300 Mo) et chaque processus enfant (RSS lu par `psutil`).
  - Dans AD-21 : le serveur MCP local démarre à l'activation de la brique MCP et s'arrête à sa désactivation. Le `lifespan` FastAPI ferme les moteurs (`close()`) et les enfants à l'arrêt, avec une attente bornée puis `terminate`.

### 14. Diagramme « Déroulé d'un tour » incomplet — Basse

- **Emplacement :** Structural Seed, 2ᵉ diagramme.
- **Problème :**
  - La borne d'appels n'est vérifiée qu'après un outil, alors qu'elle s'applique avant chaque appel (AD-10).
  - Il manque l'attente H5 et le refus réinjecté (AD-13), l'arrêt par l'utilisateur, `harness_error` (AD-16) et la délégation au sous-agent (AD-11).
  - L'action forcée est mal placée (constat 7).
- **Correction :** déplacer le test de borne juste avant E, ajouter un nœud « actions armées » entre C et D, une branche `ask_human` sur I, et un nœud « arrêt / harness_error » qui mène à Z.

### 15. Carte des capacités incomplète — Basse

- **Emplacement :** Capability → Architecture Map.
- **Problème :** `binds` liste NFR-5, 6, 7, 9, 10 et 11, qui n'ont pas de ligne. FR-9 (raisonnement) et FR-12 (mémoire globale, écrite par la `Session` d'après AD-3) sont fondus dans « FR-8 à FR-12 » sans AD-6, AD-3 ni AD-11.
- **Correction :** ajouter les lignes NFR-5 (AD-21), NFR-6 (AD-20), NFR-7 (Conventions), NFR-9 (AD-18, UX), NFR-10 et NFR-11 (Conventions, AD-19). Détailler FR-9 (AD-6) et FR-12 (AD-3, AD-20).

### 16. Stack et hygiène — Basse

- **Versions :** aucune n'est manifestement fausse pour septembre 2026. Points à faire confirmer par le relecteur des versions :
  - `mcp` 2.2.0 : majeure 2 récente, vérifier le renommage `MCPServer` ;
  - `httpx` 0.28.1 : inchangé depuis fin 2024, plausible, mais vérifier qu'aucune 1.0 n'est sortie ;
  - vérifier si FastAPI 0.141 fournit désormais une réponse SSE native, ce qui rendrait `sse-starlette` inutile (une dépendance de moins).
- **Python 3.13 :** cohérent (roue `py3-none`), mais figer `requires-python` (constat 10).
- **Rationale résiduelle :** l'estimation « 60 à 110 tokens/s » dans Deferred, et « le contexte principal est relu ensuite » dans AD-11, relèvent du memlog. Les garder seulement si elles servent de critère.
- **Mermaid :** les trois diagrammes sont syntaxiquement valides. Dans le diagramme de processus, `\\` dans le libellé `%LOCALAPPDATA%\\WaveStack` s'affichera en double barre oblique inverse : écrire `\` simple ou `/`.
- **Gabarits :** aucun élément générique non rempli. `companions: []` est cohérent avec l'absence de compagnon.

---

## Points conformes (à ne pas retoucher)

- Paradigme journal + projections (AD-1, AD-2) : il ferme la divergence principale entre volets.
- Un seul écrivain et des intentions (AD-3), un exécuteur d'outils unique (AD-14), une disponibilité centrale (AD-12) : des règles applicables et testables.
- Texte brut et absence d'adaptateur au format chat (AD-5) : cohérent avec FR-2. Signaler au PM la correction de FR-34 (« compatible OpenAI »), notée dans le memlog.
- `LoadRegistry` qui refuse, et fenêtre plafonnée avec un événement de dépassement (AD-8, AD-9) : l'enveloppe mémoire est bien tenue.
- Données d'exécution hors dépôt et hors OneDrive, résolues par `config` seul (AD-20).
- Tests avec un moteur factice, sans réseau (Conventions).
- Deferred : aucun élément différé n'ouvre de divergence, sauf le critère « sans réseau » manquant pour Headroom et fastembed (constat 4). Le schéma YAML des scénarios est bien confié à une story amont unique.
