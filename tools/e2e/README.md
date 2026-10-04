# Tests de bout en bout (faux modèle)

Rejoue l'interface de WaveStack dans un Chromium sans affichage, sans GGUF ni accès à un
fournisseur : un faux serveur compatible OpenAI, déclaré comme modèle cloud, répond de façon
scriptée et déterministe.

## Relancer

```bash
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py
```

- `--only h5 caveman` : seulement ces scénarios (le diagnostic est toujours joué). Chaque
  scénario se lance seul : aucun ne dépend de ceux qui le précèdent dans le parcours.
- `--keep` : garde le dossier de données temporaire (journaux `wavestack.log`,
  `fake_openai.log`, `settings.json`, `audit.log`) ; son chemin s'affiche au début.
- `--headed` : navigateur visible.
- `--channel msedge` (story 6 des restes différés) : un navigateur installé (Edge, Chrome) au
  lieu du Chromium de Playwright ; absent du poste, le parcours le dit et sort avec le code 2.
- `--no-rag-alt` (story 30) : WaveStack comme sur un poste sans l'extra `rag-alt` (FAISS et
  LanceDB indisponibles) ; le scénario `rag_lab` prend alors la branche « sans l'extra ».
- `--no-headroom` : WaveStack comme sur un poste sans l'extra `compression` ; le scénario
  `compression` vérifie alors la carte (commande d'installation) et un tour sans étape, puis
  se saute (`--only compression --no-headroom`).

Le parcours coupe lui-même le réseau sortant de WaveStack, pour donner le même résultat sur un
poste connecté, derrière un proxy d'entreprise ou hors ligne (Linux comme Windows) : `stack.py`
remplace les variables de proxy du processus lancé (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`)
par un port de la boucle locale sur lequel rien n'écoute, et contourne ce proxy fermé pour la
boucle locale (`NO_PROXY=127.0.0.1,localhost,::1`), où tournent le faux serveur, le faux
llama-server, le faux Ollama et WaveStack. Une requête vers un service public (`public_holidays`,
Wikipédia, data.gouv.fr, Microsoft Learn) passe donc la garde réseau et est tracée
(`outbound_request`), puis échoue : service injoignable, échec expliqué. Ni `allowed_hosts` ni le
réseau du poste ne changent (pas de pare-feu, pas de droits administrateur). Sous Windows, ce
parcours reste à vérifier sur le PC cible : une connexion refusée sur la boucle locale y prend
1 à 2 s (le système retente), l'échec arrive donc plus lentement que sous Linux.

Playwright n'est pas une dépendance du projet : `--with` l'ajoute le temps de la commande.
Il faut un Chromium de la révision attendue par Playwright 1.56 (`PLAYWRIGHT_BROWSERS_PATH`),
sinon le script essaie `/opt/pw-browsers/chromium`. Code de sortie 1 si une vérification
échoue ; `KNOWN [Ax]` signale une anomalie déjà décrite dans
`_bmad-output/implementation-artifacts/test-e2e-palier-1-cloud.md`, sans faire échouer.

Les captures (JPEG) sont réécrites dans `tools/e2e/screenshots/`.

Pour explorer à la main : `uv run python tools/e2e/stack.py` lance le faux modèle et WaveStack
(adresse affichée), puis choisissez « Faux fournisseur (e2e) » au diagnostic. Le réseau sortant
y est coupé comme pendant le parcours ; `--network` garde les proxys du poste, pour joindre les
vrais services.

## Fichiers

- `fake_openai.py` : le faux serveur (`/v1/chat/completions` en SSE avec `usage`,
  `/v1/models`, `/_e2e/requests` pour relire les corps reçus ; `POST /v1/messages`, le même
  script au format de l'API Messages d'Anthropic, clé dans `x-api-key`, finition V1). Clé
  attendue : `e2e-fake-key`.
  `/_e2e/model.gguf` est le fichier du faux modèle d'embedding : 503 tant que
  `POST /_e2e/model_ready` n'a pas été appelé (un téléchargement qui échoue, puis réussit) ;
  avec `{"slow": true}`, il est servi à un octet par seconde (« Arrêter » pendant le
  téléchargement, finition V1 #20).
  `/_e2e/reranker.gguf` est celui du faux reranker (story 16), servi sauf après
  `POST /_e2e/reranker_fail` `{"fail": true}` (503 jusqu'à `{"fail": false}`, story 6 des
  restes différés) ; `POST /_e2e/reranker_slow` `{"slow": true}` le sert à un octet par seconde
  jusqu'à `{"slow": false}` (« Arrêter », finition V1).
  Mode Gemini quand le `model` du corps commence par `gemini`, calqué sur les formes relevées
  sur le vrai `gemini-3.5-flash-lite` le 2026-09-29 : appels d'outil en un seul fragment, sans
  `index`, le premier seul avec `extra_content.google.thought_signature` (`signature-fausse-…`),
  puis
  `{"role": "assistant"}` et `finish_reason: "stop"` (jamais `tool_calls`) ; réponse texte close
  par un fragment qui porte une signature et aucun contenu ; `usage` sur chaque fragment,
  cumulé, `completion_tokens` sans les tokens de réflexion que `total_tokens` compte ; réflexion
  dans `content`, seulement si `extra_body.google.thinking_config.include_thoughts` la demande :
  `<thought>` et la pensée dans des fragments marqués `extra_content.google.thought`, puis un
  fragment non marqué `</thought>` + le début de la réponse (jamais de champ `reasoning`) ; un
  message d'assistant du tour renvoyé sans signature sur son premier appel reçoit un 400 dont
  le corps est un tableau JSON
  (`[{"error": …}]`, « missing a thought_signature … `default_api:nom` , position n »).
- `stack.py` : réseau sortant de WaveStack coupé (proxy fermé, voir plus haut), dossier de
  données temporaire, `settings.json` qui déclare six modèles sur le faux serveur (avec `sampling = ["temperature", "top_p"]` depuis la story 29, sauf `fake_a` : `["temperature"]`, comme Haiku), `fake`
  (`wavestack-fake`), `fake_b` (`faux-modele-b`, pour le changement de modèle de la
  story 17), `fake_r` (`faux-modele-raisonne`, `reasoning: {format: "field", always: true}`,
  pour la carte Raisonnement verrouillée de la story 33) et `fake_g` (`gemini-e2e-flash-lite`,
  « Faux Gemini (e2e) », avec le `reasoning` et le `tool_call_extra` du préréglage `gemini` lus
  dans `wavestack.toml`) et, depuis la story 6 des restes différés, `fake_m`
  (`faux-modele-tarife`, « Faux fournisseur M (e2e) », prix du préréglage `mistral`,
  `stream_usage = false` : coûts estimés, « ≈ ») et `fake_a` (`faux-claude`, au format
  Anthropic, finition V1), clé par
  `key_env = WAVESTACK_FAKE_API_KEY`, lancement des deux serveurs sur
  `127.0.0.1`. `wavestack.toml` n'est jamais modifié. Pour le RAG (story 15),
  `settings.json` pointe `[rag]` vers un index dans ce dossier, absent au départ comme sur
  une installation neuve (le scénario `rag` le construit depuis la carte), et déclare un faux
  fichier de modèle servi par le faux serveur ; de même pour `[rag.reranker]` (story 16).
- `fake_local_server.py` (story 18) : un faux llama-server (`/health`, `/props` avec le gabarit
  Qwen3.5, `/v1/models` (avec `n_vocab: 1004` et `n_embd: 2048` depuis la story 29), `/tokenize` avec les pièces, `/detokenize`, `/completion` en SSE ;
  tokenizer octet par octet, marqueurs du gabarit en un token) et un faux Ollama (`/api/tags`,
  avec `details` `{family: qwen3, parameter_size: 0.6B}` depuis la story 25, `/api/ps`,
  `/api/generate` pour `keep_alive: 0`) qui sert un modèle sans GGUF sur le disque.
  `stack.py` les lance sur deux ports libres, que `settings.json` déclare en
  `[net.loopback_ports]` ; `/_e2e/requests` relit les corps reçus.
- `wavestack_e2e.py` : le lanceur de WaveStack pendant le parcours. Il lance `wavestack.cli`
  tel quel (garde réseau d'abord), la brique RAG chargeant le faux modèle d'embedding de
  `tests/fake_embedder.py` (sac de mots haché, 64 dimensions, aucun GGUF nécessaire) et le
  faux reranker de `tests/fake_reranker.py` (part des mots de la question présents dans
  l'extrait), qui lève sur une question portant `[reranker-en-panne]` (story 6 des restes
  différés), et applique `launch_app.py`.
- `launch_app.py` : ralentit la seule préparation de `fake_b` (`WAVESTACK_E2E_LOAD_DELAY_S`,
  2 s par défaut) : sans cela, un modèle cloud se prépare trop vite pour que le parcours voie
  le chronomètre « Chargement du modèle… ». Story 6 des restes différés : `read_file` de
  `confidentiel/outil-lent-e2e` attend `WAVESTACK_E2E_TOOL_DELAY_S` (1,5 s) avant d'échouer
  (fichier absent), un outil assez lent pour voir le schéma au travail.
- `run_e2e.py` : les scénarios Playwright ; le journal est lu en parallèle sur `/api/stream`.
- `tests/test_e2e_fake_openai.py` : tests pytest du faux serveur, sans navigateur.

## Reranking (story 16)

Le scénario `rag_rerank`, joué juste après `rag` (index construit, modèle d'embedding
présent) : la case « Reranking » est cochée par le scénario, le modèle de reranking absent
(raison « modèle absent », « Télécharger le modèle de reranking ») et le RAG cherche sans lui ;
le téléchargement réussit ; le rejeu de la question sur l'hôtel à Paris montre « Recherche
RAG » (8 candidats) puis « Reranking » (« 3 gardés sur 8 »), le faux reranker remontant
« Déplacements et notes de frais » du 6ᵉ au 1er rang ; seuls 3 extraits partent dans le
message ; l'étape dépliée montre l'ordre avant et après ; un clic sélectionne la puce ↕️ du
reranker dans le schéma ; l'étape reste après un rechargement ; décochée, la case affiche
« Prend effet au prochain tour » et le rejeu n'a plus d'étape « Reranking ». Capture :
`25-reranking-avant-apres.jpg`.

## Changement de modèle (story 17)

Le scénario `model_switch` : sélecteur de la barre haute (modèle actif
marqué « (actif) » et grisé, dernière entrée « Autre fichier ou clé API… », aucune mention
« Prochain lancement »), choix noté sans effet tant que « Choisir… » n'est pas cliqué,
avertissement cloud dans la page (« Annuler » ne change rien, « Utiliser ce modèle » charge),
chronomètre dans la barre haute et en fin de Vue humain, envoi et sélecteur désactivés avec la
raison, conversation gardée, appel envoyé avec le nouveau modèle, lignes « Modèle : … », rejeu
joué par le nouveau modèle, « Comparer » avec le modèle de chaque colonne, puis retour au
premier modèle par « Choisir » au diagnostic, issue exacte « wavestack-fake est actif. », jamais
« relancez WaveStack pour l'utiliser ». Capture :
`22-changement-de-modele.jpg`.

## Serveur local déjà lancé (story 18)

Le scénario `local_server` : au diagnostic, le modèle du faux
llama-server est listé (« Local », adresse, mémoire, « Choisir ») et celui du faux Ollama est
incompatible, sans « Choisir » (GGUF introuvable) ; plus de mention « palier 2 ». Dans le
sélecteur de la barre haute, le modèle servi est choisi puis chargé (« Préparation du modèle
servi par llama-server… »), l'indicateur devient « Local · llama-server » (infobulle : processus
distinct), et le schéma dessine le robot hors du cadre Harnais, dans une boîte
« llama-server · 127.0.0.1:port » de la zone Poste de travail. Un tour complet avec
`get_datetime` vérifie que les ids reçus par le serveur sont ceux du texte rendu par le harnais
(somme des segments = `prompt_tokens`). Après un rechargement, indicateur et boîte reviennent ;
le scénario revient enfin au faux modèle cloud. Capture : `23-serveur-local-llama-server.jpg`.

## Compression du contexte (story 20)

Le scénario `compression` utilise le vrai Headroom : l'environnement du
parcours doit avoir l'extra (`uv sync --extra compression` une fois ; `uv run --with
playwright…` le garde). Carte disponible avec son seuil, puce 🗜️ dans le harnais ; un tour
brique éteinte (le journal `journal_serveur.log` part en entier), puis le rejeu brique allumée :
étape « Compression (Headroom) » avant → après, erreur du journal gardée dans le corps reçu par
le faux fournisseur et dans la réponse, segment marqué « compressé » et total « Sans
compression » dans Contexte LLM, « Comparer », étape toujours là après rechargement, puis le
second prompt (« à quelle heure le lot 12… ») : le journal relu est compressé de nouveau, la
ligne du lot 12 coupée manque au modèle. Sans Headroom (extra absent, ou `--no-headroom`), le
scénario vérifie la carte et un tour sans étape, puis se saute proprement. Capture :
`24-compression-avant-apres.jpg`.

## Programme et scénarios métier (story 21)

Le scénario `programme` attend que les groupes du sélecteur de scénario soient ceux de
`content/scenarios.yaml` (modules « Module N · titre · durée », puis « Transverses et métier ») :
la liste attendue et les prompts des scénarios métier sont lus dans ce fichier, pas recopiés.
Il lance ensuite le premier scénario du module 5 directement (briques des modules 1 à 4, sans
le raisonnement ni le RAG, consigne qui le dit) et « MCP en documentation complète » (RAG
éteint, « sauf le raisonnement et le RAG »).

Story 27 : les prompts des scénarios `mcp_full`, `mcp_lazy`, `skills`, `subagent` (suivi de
« [lent] »), `compression`, `soc`, `iam` et `sovereignty` sont lus dans `content/scenarios.yaml` (`_prompts`), pas recopiés ; ils
nomment l'outil ou le skill attendu. Le RAG n'est voulu dans aucun module après le 3 :
`mcp_lazy` (consigne « le RAG, laissé éteint »), `skills` (consigne qui cite « Déclencher le
skill » sur « Compte rendu de réunion »), `subagent` (« sans le raisonnement ni le RAG ») et
`compression` (préréglage « Journal de sauvegarde (compression) » cité, `read_file` sur
`journal_serveur.log` au premier tour, aucun extrait RAG dans le corps envoyé ni parmi les
candidats de la compression ; à la fin, le préréglage « Guide du harnais (prose,
compression) » forcé puis rejoué : la prose passe inchangée, la limite de Headroom).
`data_flows` est actif au lancement, sans geste : brique MCP voulue, serveurs `datagouv` et
`local` en lazy loading, échec expliqué de data.gouv.fr attendu après le lancement, flux qui
franchit la frontière, serveur local sur le poste, puis les vérifications de la story 23 ; enfin
le geste de la consigne : data.gouv.fr décoché, plus aucun flux ne franchit la frontière (hors
modèle cloud du parcours), recoché, son flux revient.

- `soc` : consigne qui cite l'analyste habilité ; `read_file` lit `alertes_siem.log`, H2
  journalise ; au second prompt, qui ne nomme aucun fichier et demande de ne pas contourner un
  refus, le modèle liste le dossier puis tente `confidentiel/comptes_privilegies.txt`,
  que H1 bloque ; la réponse escalade vers un analyste habilité et le contenu du fichier
  n'atteint pas le modèle ; `/api/audit` porte les lectures ; un clic sur « Journal d'audit »
  dans le schéma ouvre le fichier (attendu jusqu'au blocage de H1, puis défilé en bas).
  Capture : `26-metier-soc-journal-audit.jpg`.
- `iam` : Microsoft Learn seul, en documentation complète ; réseau coupé par le lanceur, échec
  expliqué, nœud indisponible dans la zone Réseau ; ses deux prompts aboutissent sans outil.
- `sovereignty` : data.gouv.fr et Microsoft Learn, en lazy loading ; réseau coupé, échec
  expliqué pour les deux (un serveur déjà contacté par le scénario précédent ne l'est pas de
  nouveau : sa dernière réponse fait foi) ; hors du modèle cloud du parcours, seules leurs
  deux arêtes franchissent la frontière du poste ; ses deux prompts aboutissent.

Les appels réels restent à tester à la main, avec le réseau (PC cible, hors du parcours, ou
`stack.py --network`) : Wikipédia (`wikipedia_summary`, `fetch_page`), `public_holidays`,
Microsoft Learn et data.gouv.fr. Le parcours, qui coupe le réseau, n'en vérifie que l'échec
expliqué.

## Retours de recette (story 22)

Vérifications ajoutées aux scénarios existants :

- `bare_llm` : « Raisonnement » en tête du panneau ; MCP (passé en lazy loading par l'API,
  brique éteinte), Outils, Skills et Hooks éteints : sous-options désactivées, raison au
  survol, « · brique éteinte » dans le résumé ; la consigne derrière le « i » de la Vue humain,
  fermée au lancement.
- `system_prompt` : « Enregistrer » désactivé tant que le texte est inchangé, puis
  « Prompt système enregistré. » (`role=status`), effacé à la saisie suivante.
- `subagent` : onglets « Agent principal » / « Sous-agent subN » (`role=tablist`), retour à
  « Agent principal » au tour suivant ; « Annuler » et un second clic sur « Déléguer au
  sous-agent » ferment le formulaire.
- `soc` : consigne de 1 276 caractères derrière le « i » : clic, Échap, aperçu au survol qu'un
  clic garde ouvert ; entière dans la fenêtre, champ et dernière bulle visibles ; laissée
  ouverte, elle suit le scénario lancé ensuite.
- `global_memory` : 6 entrées ; croix, « Tout effacer » (danger) et « Fermer » visibles sans
  défiler ; la croix ferme le tiroir.
- `rag_rerank` : « Reranking » coché, brique RAG éteinte : grisé, désactivé, raison au
  survol ; rallumée : de nouveau réglable. Capture : `27-reranking-brique-rag-eteinte.jpg`.
- `reload_and_reset` : après « Réinitialiser » puis « Vider la conversation », Orchestration
  repart à « Tour 1 », l'infobulle et le journal gardant l'identifiant `t{n}` suivant.

## Code couleur par discipline (story 33)

- `disciplines`, joué après `network_tools` : scénario « Outils réseau » et un tour « Résume
  l'article Wikipédia… ». Barre haute sur `--color-ink`, légende `#gauge-legend` (prompt,
  context et harness engineering), chaque `.gauge-seg` avec sa discipline et le fond de son
  jeton, total en tokens et en pourcentage, légende et chiffres entiers à 1600 × 1000. Panneau
  des briques : légende des quatre disciplines, « Ce que le modèle lit » puis « Ce que le
  harnais fait », premier groupe Raisonnement, Prompt système, Mémoire courte, Mémoire globale,
  RAG ; trait de la carte Prompt système et fond de la carte RAG éteinte ; lignes d'état
  (« n tokens dans le contexte », « n entrées · n tokens », « n déclarés · c contacté(s) », avec
  la puce « RÉSEAU ») ; Prompt système éteint par l'API, « Éteinte », explication toujours
  ouverte. Bulle de l'utilisateur sur l'encre, en-têtes des cinq volets sur `--color-surface`,
  sections de Contexte LLM (filet du prompt système, pastille de son type), tuiles
  d'Orchestration (appel au modèle sur l'encre, `wikipedia_summary` en réseau, « Description
  des outils » en harness), plaque du modèle et nœuds du schéma. `c` compte les outils réseau
  déjà contactés dans la session : 1 (Wikipédia) quand le scénario est joué seul, 2 après
  `network_tools` (les jours fériés aussi). Captures `28-disciplines-barre-haute.jpg`,
  `29-disciplines-briques.jpg`, `30-disciplines-vue-humain.jpg`, `31-disciplines-contexte.jpg`,
  `32-disciplines-orchestration.jpg`, `33-disciplines-schema.jpg` (`Run.shot_element` : la
  pièce seule).
- `reasoning_locked`, joué après `model_switch` : bascule sur `fake_r` depuis le sélecteur de
  la barre haute ; carte Raisonnement cochée et désactivée, 🔒, « Imposé par ce modèle » ; puis
  retour à l'entrée A, qui ne raisonne pas : plus de verrou. Capture
  `34-raisonnement-impose.jpg`.
- `reasoning_dropped` (finition V1, #28 et #35), joué après `reasoning_locked` : sixième entrée
  `fake_a` (`faux-claude`, « Faux Anthropic (e2e) », `api = "anthropic_messages"`), servie par
  `POST /v1/messages` du faux serveur (le même script, au format de l'API Messages, clé dans
  `x-api-key`). Scénario « Sous-agent », premier prompt suivi de « [jeté] », recopié dans la
  tâche du sous-agent : chaque `message_start` porte `input_transformations`
  (`thinking_dropped`, `prefix_binding_mismatch`). `reasoning_dropped` au tour et au
  sous-agent ; ligne « Raisonnement jeté par le fournisseur » et figure « historique réécrit »
  dans Orchestration, aux deux niveaux ; phrase du harnais dans l'étape dépliée ; journal
  « historique réécrit · <chemin> ». Retour à l'entrée A même après un échec. Capture
  `35-raisonnement-jete.jpg`.

## Gemini (Google AI Studio)

- `gemini_shape`, joué après `reasoning_locked` (seul, il part du faux cloud A et y revient,
  même après un échec) : scénario « Outils natifs », `fake_g` choisi dans le sélecteur, carte
  Raisonnement réglable, sans verrou. Raisonnement éteint, « Quelle heure est-il ? » : deux
  corps relus par `/_e2e/requests`, le premier avec `reasoning_effort: "minimal"`, sans
  `extra_body`, `max_tokens` 512 ; la signature de `model_call_ended.tool_calls[0].extra_content`
  rejouée telle quelle dans le second ; aucun `harness_error`. Raisonnement allumé, « Combien font
  12 multiplié par 37 ? » : `extra_body.google.thinking_config` `{thinking_level: "high",
  include_thoughts: true}`, sans `reasoning_effort`, `max_tokens` 1 536 ; `<thought>…</thought>`
  lu comme réflexion (deltas du canal `reasoning`), absent du texte et de la bulle, gardé dans
  `raw_output` ; signature rejouée. Capture `59-gemini-raisonnement.jpg`.

## Mode sombre (story 31)

- `themes`, joué après `disciplines`, à 1600 × 1000, poste émulé en clair : scénario « Outils
  réseau » et un tour « Résume l'article Wikipédia… », aucun choix mémorisé. `#theme-picker` sur
  « Système » (« ◐ Système », « ☀ Clair », « ☾ Sombre »), pas d'attribut `data-theme`, chaque
  commande de la barre haute entière (`_fully_visible`), sans face compacte ; de même à
  1440 × 900 (mots entiers). À 1280 × 720, en mode normal puis en mode projection : barre sur
  une ligne, « Réinitialiser » entier, sélecteur compact (face « ◐▾ », liste native d'opacité 0
  posée exactement dessus) ; `ArrowDown` sur la liste passe à « Clair » (`data-theme`, face
  « ☀▾ »), puis retour à « Système ». Poste émulé en sombre
  (`emulate_media`) : fond de `body` en `surface-dark` (lu dans DESIGN.md) sans rechargement ;
  de nouveau en clair : `surface`. « Sombre » choisi : `data-theme="dark"`,
  `localStorage["wavestack.theme"] == "dark"`, barre haute, dernière bulle, tuile de l'appel au
  modèle et plaque du modèle en `ink-fill-dark`, filet du prompt système en
  `discipline-prompt-dark`, chaque `.gauge-seg` sur le jeton sombre de sa discipline, puis le
  balayage des contrastes de la liste « Volets ▾ », du panneau « Fenêtre » et du tiroir
  d'édition ouverts (bloquant). Rechargé
  avec `**/static/app.js` interrompu (`route.abort`) : `data-theme="dark"` et le fond sombre sont
  déjà là (`theme.js`, en tête de page) ; `app.js` rendu, le sélecteur montre « Sombre », sans
  `pageerror` (seul le chargement interrompu s'écrit en console). `/diagnostic` et `/models` :
  sombres, sélecteur sur « Sombre ». « Clair » choisi au diagnostic, poste émulé en sombre :
  l'atelier reste clair. `wavestack.theme = "violet"` : « Système ». Un contexte neuf dont
  `Storage.prototype.getItem` et `setItem` lèvent : « Système », puis « Sombre » appliqué à la
  page seule (rien d'écrit), sans erreur. Le scénario finit toujours sur « Système », poste
  clair, `unroute` : les autres scénarios restent en thème clair.
- `_contrast_sweep` : pour chaque élément visible qui porte du texte (et la valeur affichée d'un
  `select`), premier fond opaque en remontant (pour un texte SVG : son `fill`, sur le `fill` de
  la forme posée à côté, le disque d'un marqueur), ratio WCAG, seuil 4,5 (3 à partir de 24 px, ou de
  18,66 px en gras). Ignorés : un ancêtre en `opacity < 1` ou désactivé (exemption WCAG), un fond
  en image. Le pointeur est d'abord écarté (la vue liée estomperait la page). Bloquant en
  sombre, sur la barre haute, les cinq volets, `/diagnostic` et `/models` ; en clair, signalé en
  `KNOWN [clair-préexistant]` (aucun échec à ce jour).
- Captures `46-theme-sombre-atelier.jpg` (page entière), `47-theme-sombre-vue-humain.jpg`,
  `48-theme-sombre-schema.jpg` (`Run.shot_element`), `49-theme-sombre-diagnostic.jpg`,
  `50-theme-sombre-modeles.jpg` et `51-theme-clair-atelier.jpg`, pour comparer.
- `disciplines` : les fonds d'encre se lisent sur `--color-ink-fill` (même valeur que
  `--color-ink` en clair). `linked_view` : le détail d'échec de la puce « · lié » donne les
  pixels manquants.
- Texte sur rouge en `--color-on-vivid`, en clair puis en sombre (attribut posé à la main) :
  lettre de la tuile d'un appel au modèle en erreur (`provider_errors`, `[erreur500]`),
  chiffres de la jauge en dépassement (`busy_and_stop`), « Oui, tout effacer »
  (`global_memory`).

## Données sortantes, en-têtes compris (story 23)

- `network_tools` : la carte Outils, options repliées, dit « Peuvent sortir du poste » et nomme (Jours
  fériés, Résumé Wikipédia, Lecture de page web, data.gouv.fr, Microsoft Learn) et « Données
  sortantes ». Après le tour des jours fériés, l'étape « Exécute l'outil hors du poste · Jours fériés » (story 34) dépliée
  montre « Données sortantes », l'adresse calendrier.api.gouv.fr, « En-têtes », le User-Agent
  avec contact et « Aucun corps : seule l'adresse sort du poste. » ; l'événement
  `outbound_request` porte ses en-têtes, aucun masqué. Après le tour Wikipédia : bloc replié à
  la main, Orchestration défilée en haut puis masquée ; un clic sur le nœud « Lecture de page
  web », jamais contacté, ne fait que le sélectionner (infobulle « Non contacté ») ; un clic
  sur le nœud « Wikipédia » (infobulle « Clic : ses données sortantes dans Orchestration »)
  réaffiche Orchestration, déplie l'étape, rouvre le bloc et l'amène dans `#orch-scroll`
  (« GET https://fr.wikipedia.org/api/rest_v1/page/summary/… », « User-Agent: WaveStack/0.1
  (demonstrateur pedagogique; … », « Accept: */* ») ; la vue est figée. Capture
  `08b-donnees-sortantes-en-tetes.jpg`. Un second clic sur le nœud, déjà sélectionné, le
  garde sélectionné et ramène le bloc. De retour en direct, le tour des jours fériés est
  replié : un clic sur le nœud « Jours fériés » le déplie, avec l'étape et son bloc à l'écran.
  « Lecture de page web » doit n'avoir jamais été contactée dans la session (vérifié).
- `data_flows` : préparation repliée et Orchestration masquée, un clic sur le nœud
  data.gouv.fr réaffiche le volet, déplie la préparation et la connexion, ouvre son bloc et
  l'amène à l'écran, sans figer la vue. La connexion montre son bloc « Données sortantes »
  avec ses en-têtes et le User-Agent (rendu de la story 5b, jusque-là non testé).
- `h5` : l'aperçu garde méthode, adresse et corps, avec une note sur les en-têtes posés à
  l'envoi si l'appel est accepté.

## Vue liée et lecture guidée des volets (story 34)

- `linked_view`, joué après `disciplines`, à 1600 × 1000 : scénario « Outils réseau » et un tour
  « Résume l'article Wikipédia… ». Survol de la carte Outils : `body.linking`, nœuds Wikipédia
  et Calculatrice, segments et étape « Exécute l'outil hors du poste » éclairés, carte Mémoire
  globale estompée (opacité < 0,5) ; pointeur sur le titre de la barre haute : plus rien.
  Survol du segment harness de la jauge (carte Outils), de la plaque du modèle (chaque section
  de Contexte LLM), de « Répond » et de « Appelle le modèle » (plaque et sections de leur appel,
  pas celles de l'autre : story 32). Au clavier, une section focalisée
  puis une ligne d'étape atteinte par Tab éclairent comme au survol ; focus perdu : plus rien.
  Clic sur le nœud Calculatrice, Contexte LLM masqué : carte Outils cerclée d'encre, puce
  « + Contexte LLM · lié » ; Échap efface tout. Mouvement réduit : `transition-duration` 0s.
  Volets numérotés 1 à 4 avec leur sous-titre, briques sans numéro, aide sous la légende.
  Frise : « Décrit les outils », « Appelle le modèle », « Demande un outil », « Exécute l'outil
  hors du poste », « Réinjecte le résultat », « Répond », pastilles H, M, M, R, H, M, ligne
  réseau « 🌐 RÉSEAU → fr.wikipedia.org », figure de « Répond », dépliage au clic. Après le
  clic sur Calculatrice, une section et une étape visibles sont cerclées d'encre, sans estompage
  sous le pointeur resté sur la source. Bilan sous le schéma : K = `model_call_started` +
  `outbound_request{origin: brick}` des étapes d'outil qui n'ont pas échoué ; la requête vers
  Wikipédia, que le réseau coupé fait échouer, est citée à part, « 1 tentative en échec vers
  Résumé Wikipédia (le titre de l'article) ». Infobulles « Au tour 1 : tentative en échec… »
  (Wikipédia, pastille « en échec » ou « indisponible ») et « Au tour 1 : non contacté. »
  (Jours fériés) ; pastille « non contacté » sur « Lecture de page web ». Mode projection :
  `html.projection`, corps à 18 px, `aria-pressed`, « Réinitialiser » entier dans la barre ; à
  1280 × 720, barre sur une ligne et « · lié » lisible sur une puce ; gardé après rechargement
  puis Réinitialiser, bilan « Aucun tour affiché… » ; second clic, 14 px. Captures
  `35-vue-liee-survol.jpg`, `36-selection-liee.jpg`, `37-frise-orchestration.jpg`,
  `38-bilan-des-sorties.jpg`, `39-mode-projection.jpg`.
- `local_server` : après le tour avec le faux llama-server, le bilan dit « aucune donnée n'a
  quitté le poste ».
- `forced_native` : l'étape de la calculatrice forcée porte la pastille « U ».
- Les captures (`Run.shot`, `Run.shot_element`) écartent d'abord le pointeur de tout élément
  liable (`Run.rest_pointer`), pour qu'un clic précédent n'estompe pas la page ; la capture 35
  garde le survol. Les étapes d'outil se repèrent par `.turn-step-title` (le verbe, puis le
  libellé de l'outil).

## Sélecteur regroupé et tableau des capacités (story 25)

- `local_server` : le faux Ollama est « Local · Ollama · faux-ollama:latest · 0.6B
  (incompatible) » (sa taille vient de `details`) ; le faux llama-server garde son libellé.
- `model_catalog`, joué après `local_server` : la deuxième option de `#model-picker` est la
  légende, désactivée (« où tourne le modèle », « qui le sert »), reprise dans l'infobulle ;
  groupes « Sur ce poste · Qwen (Alibaba) » (le faux Ollama par sa famille `qwen3`, le faux
  llama-server par la famille que `capabilities_for` lit dans son gabarit, jamais Llama pour
  « llama-server »), puis « Réseau · Gemma (Google) » (préréglage Gemma), « Réseau · Gemini
  (Google) » (préréglage Gemini et `fake_g`),
  « Réseau · Mistral (Mistral AI) » et « Réseau · gpt-oss (OpenAI) » (préréglages de
  `wavestack.toml`, sans clé) et « Réseau · Autres éditeurs » (les trois autres faux modèles
  cloud) ; lignes des préréglages Gemini (éditeur « Gemini (Google) », raisonnement
  « activable », prix « 0,30 $ / 2,50 $ ») et Gemma (éditeur « Gemma (Google) », « 26 B »,
  prix « — » sans `pricing`) ; dans le groupe Qwen, le faux Ollama (0.6B) avant le faux llama-server
  (taille inconnue) ; chaque modèle commence par « Local · » ou « RÉSEAU · » ; « Tableau des
  modèles et de leurs capacités… » puis « Autre fichier ou clé API… » en dernier. « Ouvrir le
  tableau » mène à `/models` : onglet « 🛠️ Diagnostic » courant, aucun onglet « Modèles »,
  « 🛠️ Diagnostic » vers `/diagnostic` (mêmes onglets) ; lignes du faux llama-server (Qwen, outils « oui », « activable »,
  « 4 096 tokens »), de R (« toujours »), de `wavestack-fake` (« jamais », « actif »), du faux
  Ollama (« inconnu », raison « introuvable » visible), « RÉSEAU » sur chaque ligne cloud,
  étiquette sur le jeton jaune, un en-tête par groupe du sélecteur. Puis R activé depuis le
  sélecteur : carte Raisonnement verrouillée et ligne « toujours », « actif » ; retour à A :
  ligne « jamais », carte indisponible « ne déclare pas de raisonnement ». Captures
  `43-modeles-selecteur.jpg` (la liste affichée en boîte de liste : une liste native ne se
  capture pas ouverte) et `44-modeles-tableau.jpg` (page entière).
- Story 3 du 2026-09-30, dans `model_catalog` : « Taille » cliquée deux fois, ordre décroissant
  dans chaque groupe (octets puis paramètres, inconnues en dernier) et `aria-sort="descending"`
  sur cet en-tête seul ; Entrée sur « Fenêtre », ordre croissant ; le prix sans tri. Filtre
  « Réseau » + texte « gem » : les seules lignes attendues d'après `/api/diagnostic`, compteur
  « n modèles sur N », groupes vides masqués (capture `44b-modeles-filtres.jpg`) ; « zzz » :
  message dédié, tableau masqué, puis « Réinitialiser les filtres ». Au diagnostic, `searching`
  faux une fois le contrôle `model` rendu ; puis, réponse et flux simulés par `page.route` (la pile
  n'est diagnostiquée qu'au lancement) : « Recherche et test des modèles en cours… » sans compteur
  (`0/0`), puis « 3 modèles testés sur 30 » et la barre à 3/30 par un `diagnostic_progress` en
  direct, jamais « Aucun candidat trouvé. » (capture `49b-diagnostic-recherche.jpg`) ; la vraie
  réponse rend ensuite la liste. Dans `annex_language`, en `de` à 1 280 px : « Fenster » puis
  « Netzwerk », les seules lignes réseau, par fenêtre, compteur juste.

## Fenêtre de contexte réglable (story 26)

- `context_window`, joué entre `model_catalog` et `relaunch` (seul, il part du faux cloud A) :
  (a) sur le faux cloud A, après un message, le bouton « Fenêtre 4 096 ▾ » (`aria-haspopup`
  `dialog`, `aria-expanded`) ouvre le panneau (`role="dialog"`) : titre, aide « conçus pour
  4 096 tokens », trois choix 4 096, 8 192 et 16 384 tokens, « (actuelle) » sur 4 096 seulement,
  cache « chez le fournisseur » et « Tient dans le budget » pour chacun, « Appliquer » désactivé
  sur la fenêtre actuelle (raison en infobulle) ; `Échap` le ferme. (b) 8 192 appliqué : aucun
  `model_load_started` (modèle cloud), panneau fermé, bouton « Fenêtre 8 192 », infobulle de
  `#gauge` « Fenêtre de 8 192 tokens », chiffres « / 7 680 tokens », message toujours dans la
  Vue humain, `settings.json` `context.window == 8192`. (c) Le faux llama-server (`N_CTX = 8192`)
  chargé depuis le sélecteur et un message : 16 384 noté montre « bornée à 8 192 par
  llama-server (-c) », le temps de lecture et le cache « réservé par llama-server », avant
  d'appliquer. Deux messages d'abord : le premier appel après un chargement n'est jamais mesuré, le second
  donne « au moins ≈ N s » (le faux llama-server attend 20 ms avant le premier fragment et
  renvoie `timings.prompt_n`, comme le vrai). Capture `45-fenetre-contexte-reglage.jpg`. Puis
  4 096 appliqué au faux llama-server (fenêtre effective 8 192 → 4 096) : rechargement
  « Rechargement de faux-llama-server avec une fenêtre de 4 096 tokens… » (`window` dans
  `model_load_started`), puis « Fenêtre de contexte : 4 096 tokens (conversation gardée). » dans
  la barre haute. (d) Retour au faux cloud A et à 4 096, même après un échec (`finally`, dont
  l'échec est une vérification à part) : `relaunch` reste inchangé. Les nombres portent l'espace fine
  insécable (U+202F).

## Contexte LLM lisible : lu et produit (story 32)

- `native_tools`, après « Quelle heure est-il ? » (faux cloud) : deux `.ctx-call` « Appel 1 sur 2 »
  et « Appel 2 sur 2 », chacun « Lu : n tokens · évalués : … · produits : n » ; l'appel 2 replie
  « Déjà lu à l'appel précédent · k sections · n tokens » et marque « Nouveau » la section
  « Résultats d'outils » ; aucun badge à l'appel 1. Produit : l'appel d'outil de l'appel 1 en arbre
  (`"name"`, `"get_datetime"`), la réponse de l'appel 2 ; fond `--color-produced-soft`, distinct de
  toute section lue ; « Produit par le modèle » visible. « Texte exact » : chaque `pre.ctx-exact`
  est le `body` du `context_rendered` de son appel, et son `json.loads` le corps reçu par le faux
  fournisseur, sans habillage. « Corps JSON » : l'arbre montre `"messages"`, un clic sur le
  summary replie, un second déplie ; la racine s'ouvre seule, ses sous-nœuds repliés, et un
  sous-nœud déplié par un clic le reste au rendu suivant (lot 1 du 2026-10-04). Retour à « Lecture groupée » (mémorisée par le navigateur).
  Captures `40-contexte-appels-numerotes.jpg`, `41-contexte-texte-exact.jpg`,
  `42-contexte-corps-json.jpg` (Contexte LLM en mode focus).
- `bare_llm`, « Bonjour [raisonne] » : la réflexion (`--color-reasoning-soft`) précède la réponse,
  sur un autre fond ; `.ctx-total` commence toujours par « Tour N · ». Puis `Lis ceci : {"a": et
  {x}` : le volet s'affiche, le texte reste tel quel, sans arbre JSON (de même en mode local, dans
  `local_server`).
- `busy_and_stop` : pendant « Explique le harnais [lent] [long] », la réponse de l'appel en cours
  grandit dans Contexte LLM avant `model_call_ended` ; à la fin, un message de 20 000 caractères
  déborde : le dernier appel dit « non envoyé : contexte dépassé » et « Aucun appel : contexte
  dépassé. ».
- `local_server` (faux llama-server, gabarit Qwen3.5) : deux appels numérotés ; à l'appel 1, la
  ligne des descriptions d'outils montre un arbre JSON (`"parameters"`) et sa marge empile les
  sections que les JSON touchent (gabarit, descriptions d'outils) ; Σ `sections.tokens` =
  `prompt_tokens` pour chaque appel ; « Texte exact » = jointure des segments (le prompt). Avec
  la brique Raisonnement, « Bonjour [réfléchis longtemps] » : le faux llama-server raisonne
  au-delà du budget sans fermer, le harnais coupe et relance ; un seul appel, la note du harnais
  entre la réflexion et la réponse.
- `subagent` : l'onglet du sous-agent numérote ses appels et replie le déjà-lu à partir du 2e ;
  sur « Agent principal », la ligne entre les appels nomme la délégation et son bouton « Voir le
  contexte du sous-agent subN » ouvre l'onglet.
- `rag` : l'introduction et les trois extraits forment une section « Extraits RAG » de 4
  segments ; `compression` : un segment compressé, son badge et « Texte avant compression » dans
  sa section ; `disciplines`, `linked_view` : les vérifications portent sur `.ctx-section` (au
  clavier, sa marge `.ctx-section-select`, seul contrôle de la ligne).

## Atelier LLM (story 29)

- `llm_screen`, joué entre `context_window` et `relaunch` (seul, il part du faux cloud A et y
  revient, même après un échec) : (1) à 1600 × 1000, le lien « LLM » de la barre haute est
  entier (`_fully_visible`) et toutes les commandes de la barre restent entières, sur une ligne
  (`_bar_fits`) ; (2) « ☾ Sombre » choisi dans l'atelier, le clic sur le lien ouvre `/llm` en
  sombre (`data-theme`, fond `surface-dark`), avec son sélecteur de thème, son titre « Atelier LLM » (`h1` et
  `<title>`) et l'onglet « LLM » courant ; (3) sur le faux cloud A, « Découper en tokens » : `llm_tokenized` non
  exact, « chez Faux fournisseur (e2e) », l'estimation « ≈ » et aucune puce ; (4) le faux
  llama-server choisi dans le sélecteur de l'atelier, « Bonjour <|im_end|> 🙂 » : une puce par
  token avec son identifiant, autant que `token_count`, `<|im_end|>` une seule puce « spécial »
  (id 1002), « N tokens pour M caractères », et le schéma de vectorisation montre « 2 048 » et
  « 1 004 » (le faux llama-server donne `n_vocab` et `n_embd` dans `/v1/models`, comme le vrai) ;
  contrastes AA de la page dans les deux thèmes (`_contrast_sweep`). Capture
  `52-llm-nu-tokenisation.jpg` (page entière). Incrément 2 : (3b) pendant un tour lent de
  l'atelier (« [lent] [long] », envoyé par l'API), « Générer » est désactivé avec la raison et un
  appel direct à `llm_generate` reçoit 409 ; le tour est arrêté. (3c) Sur le faux cloud A, top-k
  est désactivé avec sa raison, et la génération envoie `temperature: 0.2` et `top_p: 0.9`
  seulement (dernier corps de `/_e2e/requests`), un seul message ; les puces sont dites
  « fragments ». (5) Sur le faux llama-server, T 0,2, top-k 5, top-p 0,9 et min-p 0,05 saisis :
  le dernier corps `/completion` et `model_call_started` du contexte `llm` (source `screen`) les
  portent ; le nombre de puces croît d'un relevé à l'autre ; « Premier token après … » et
  « Débit de sortie » s'affichent ; le prompt rendu commence par `<|im_start|>user` ; la
  session est revenue en `idle`. Capture `53-llm-nu-generation.jpg`. (6) La Vue humain de
  l'atelier a le même nombre de bulles. Incrément 3 : après le passage au faux llama-server,
  la section « Chargement du modèle » montre les étapes, dont « Connexion à llama-server », leur
  durée, « dans son propre processus » et « En local : RAM du CPU, pas de GPU » ; le raisonnement
  coché sur le faux llama-server (gabarit Qwen3.5) : réserve de 1 536, le couloir « Réflexion »
  contient « Je réfléchis. » et le couloir « Réponse » la réponse. Capture
  `54-llm-nu-chargement-raisonnement.jpg`. Incrément 4 : sur le faux cloud A puis sur le faux llama-server,
  « Montrer les tokens candidats » est grisé, sa raison nomme le fournisseur ou « llama-server »,
  et un appel direct qui les demande reçoit 409 (l'affichage des candidats passe par pytest :
  aucun moteur en processus dans le parcours). (7) Retour au faux cloud A, puis `/llm` dit « aucune
  mémoire sur ce poste ».
- Restes du 2026-10-01, dans `llm_screen` : sur le faux cloud A, une comparaison A/B sur
  « Bonjour [lent] » (0,4 s par fragment) : deux requêtes au faux fournisseur, température 0,2
  puis 1,2 ; « Arrêter » de la page pressé dès le premier fragment de B : A « Réponse
  terminée. », B « Génération arrêtée. » dans sa colonne, « Générer » et « Comparer » de nouveau
  actifs.
- `llm_live` (restes du 2026-10-01), juste après `llm_screen`, sans moteur en processus : des
  `page.route` remplacent `/api/llm_lab` (la vraie réponse, candidats disponibles, réglages tous
  permis), `/api/llm_lab/distribution` (calculée par la vraie `candidates.distribution`) et
  `/api/stream` (un `llm_generation_started` puis des `llm_token` avec leurs candidats, rejoués par
  lots que le scénario libère un à un, validés par `Envelope`). Vérifie les barres du premier
  token (largeurs = `p` et chance), le curseur top-k (lignes grisées « écarté », `p` inchangé),
  trois mouvements rapides (le dernier gagne), la température (la chance bouge, pas `p`), le
  schéma de la fenêtre (prompt à 250/1 000 de sa part, réponse à 1/500 puis 3/500 de la réserve)
  et le clic sur une puce (ses candidats en section 2, la puce marquée). Capture
  `65-llm-nu-distribution-vivante.jpg`.

## Atelier MCP (story 6 du 2026-09-30)

- `mcp_lab` : lien de la barre commune et de la carte MCP, trois serveurs, poignée de main avec
  le glossaire local, appel valide puis terme inconnu ; captures 61 et 62.
- `mcp_lab_page` (restes du 2026-10-01) : `/api/mcp_lab` coupé par `page.route` (alerte, puis la
  page se rétablit seule) ; tour lent de l'atelier (bandeau « Occupé », « Se connecter » grisé,
  appel direct 409) ; « Arrêter » pressé pendant la poignée de main du glossaire (jusqu'à trois
  essais si la poignée de main gagne la course) ; préréglage « MCP », appel, rechargement
  (`last_session` rejoué à l'identique) ; data.gouv.fr hors réseau (requête POST sortante
  affichée, connexion en erreur) ; puis un `last_session` servi par `page.route` (serveur public,
  outil à paramètres texte, entier, objet et booléen, appel borné) : note « servie … non
  traduite », un champ par type, JSON invalide dit sans requête, arguments envoyés convertis
  (requête interceptée), note « Borné ». Capture `66-atelier-mcp-serveur-public-hors-reseau.jpg`.

## Atelier RAG (story 30)

- `rag_lab`, joué juste après `rag_rerank` (index construit, faux modèles d'embedding et de
  reranking présents), à 1600 × 1000 : (1) le lien « RAG » de la barre haute est entier
  (`_fully_visible`), vers `/rag`, et toute la barre tient sur une ligne (`_bar_fits`) ; (2) sur
  `/rag`, sept cartes dans l'ordre (Découpage, Embedding, Base vectorielle, Recherche,
  Reranking, Construction du contexte, Génération), les options « Faux embedding (e2e) »,
  « sqlite-vec » et « Faux reranker (e2e) », chaque carte expliquée, la génération sur
  `--color-ink-fill`, l'onglet « RAG » courant et le titre « Atelier RAG », contrastes AA en clair et en sombre
  (`_contrast_sweep`) ; capture `55-atelier-rag-chaine.jpg` ; (3) « Combien de jours de
  télétravail par semaine ? » puis « Lancer la chaîne » : une paire `started`/`ended` par étape
  exécutée, les statuts vus au fil de l'eau (`MutationObserver`) passent par « en cours » puis
  « terminée · N ms », chaque carte donne sa durée en ms et la mémoire en Mo ; la Recherche liste
  8 extraits (`rag_rerank_candidates`) avec rang et score, le Reranking le rang avant et après
  de chacun, le Contexte les 3 extraits au format de la brique, la Génération « non exécutée
  dans l'atelier RAG » ; aucune `pageerror` ; capture `56-atelier-rag-resultats.jpg` ; (4) après
  rechargement, le même run (`last_run`) ; (5) pendant un tour lent de l'atelier, `rag_lab_run`
  répond 409 avec la raison et « Lancer » est grisé. (6) Incrément 2 : « Comparer avec une
  autre configuration » ; B = « Recherche exhaustive en mémoire », 300 caractères, 2 extraits :
  deux colonnes, l'Embedding de B « calculés (77 passages) », son Contexte à 2 extraits, la
  synthèse (en commun, écarts de rang), un dossier nouveau sous `rag_lab/` du dossier de données
  et `git status` inchangé (hors captures) ; capture `57-atelier-rag-comparaison.jpg` ; le second
  run dit « relus du cache » ; les chaînes survivent au rechargement ; 1 candidat pour 2 extraits :
  la raison du 409 s'affiche et rien ne part ; « Revenir à la chaîne livrée ». (7) Incrément
  3, le scénario suit le catalogue et dit sa branche : sans l'extra `rag-alt` (ou avec
  `--no-rag-alt`), FAISS et LanceDB sont désactivés dans la liste de la base vectorielle, et
  leur raison contient `uv sync --extra compression --extra rag-alt` ; avec l'extra
  (l'environnement du parcours le garde une fois `uv sync --extra compression --extra rag-alt`
  fait), A = sqlite-vec et B = FAISS rendent les mêmes extraits aux mêmes rangs, la Base
  vectorielle de B dit « construit (29 vecteurs) », puis « relu », et la mémoire ajoutée au
  premier import. (8) Incrément 4 : le Reranking retiré, « Recherche lexicale BM25 » ajoutée
  sans fusion : la carte BM25 dit « Deux recherches demandent une fusion après elles » et
  « Lancer » est désactivé ; le Reranking rajouté puis la Fusion, puis le Reranking déplacé
  après la Fusion par « Déplacer après » au clavier : chaîne valide ; le run montre, pour la
  Fusion, le rang de chaque extrait dans les deux recherches et son score RRF ; capture
  `58-atelier-rag-hybride.jpg` ; la Fusion déplacée avant BM25 : la raison nomme la Fusion, et
  le 409 est renvoyé si l'on poste quand même. Depuis l'incrément 4, 1 candidat pour 2 extraits
  est refusé sur la carte dès la saisie (« Lancer » grisé), et le 409 donne la même raison.
  Retour à `/` en fin de scénario, thème « Système ».

## Options, cartes et interrupteurs (story 5 des restes différés)

Contrôles préfixés de leur entrée de `deferred-work.md` ; chacun échoue si l'on retire de
`app.js` la ligne qui produit le comportement (vérifié à la main le 2026-10-02). `app.js` est un
module : les contrôles lisent le DOM, `localStorage`, les requêtes (`expect_request`) et, pour
deux états difficiles à atteindre, réécrivent une réponse par `page.route`.

- `mcp_full` (E016, E030) : serveur « Glossaire WaveStack » décoché puis recoché dans la carte
  MCP (corps postés à `/api/intentions/mcp_server`) ; la nouvelle connexion, après le tour, dit
  « connecté », aucune ligne « connexion… », badge « MCP » une fois dépliée ; outils du serveur
  dans l'infobulle de son nœud ; « Vider la conversation » masque cette connexion.
- `mcp_lazy` (E017) : « Lazy loading » décoché puis recoché (`/api/intentions/mcp_mode`) ; étape
  « Chargement de la documentation » avec le badge « MCP ».
- `skills` (E023) : skill décoché puis recoché (`/api/intentions/skill`) ; nœud du schéma
  « Non chargé », puis `is-loaded` et « Chargé dans la conversation. » après le tour.
- `h5` (E028, E030) : « En attente de validation » dans la Vue humain et Orchestration ; carte
  répondue : « Décision : Refusé » puis « Décision : Annulé : tour arrêté », sans bouton ; deux
  clics synchrones sur « Refuser » = une requête ; rechargement avec `/api/state` réécrit en
  `state: turn` : trois boutons inactifs ; validation répondue par l'API puis par la page : 409
  affiché sous le champ (un `MutationObserver` garde chaque texte de `#composer-reason`) ;
  « Vider la conversation » : aucune carte, étape ni appel, nœud « Jours fériés » sans « Au tour ».
- `forced_native` (E035) : « Afficher les actions forcées » gardé après rechargement ; action
  armée puis outil décoché : « Action forcée abandonnée · Heure et date ».
- `reload_and_reset` (E043, E047) : serveur MCP local connecté avant les tours, gardé dans la
  préparation du harnais après « Réinitialiser » ; liste d'options ouverte refermée.
- `bare_llm` (E053) : « Afficher le raisonnement » décoché (Vue humain sans bloc, Contexte LLM
  avec la réflexion), gardé au rechargement, puis recoché.
- `Run.open_options` vérifie que la liste est ouverte et reclique sinon : depuis D3,
  « Afficher les actions forcées » la déplie au rendu suivant, et un clic juste après la
  repliait (`mcp_full`, « Forcer l'appel · local__define_term » absent).

Sous Windows, une sortie redirigée vers un fichier demande `PYTHONIOENCODING=utf-8` (sinon
`UnicodeEncodeError` sur « ℹ »).

## Schéma, rail, volets, comparaison, cas d'erreur (story 6 des restes différés)

Contrôles préfixés de leur entrée de `deferred-work.md` ; chacun échoue si l'on retire de
`app.js` la ligne qui produit le comportement (vérifié à la main le 2026-10-02). `app.js` étant
un module, `robotPose`, `moveBoundary` ou `loadPaneLayout` se lisent par ce qu'ils produisent.

- `native_tools` (E020, E031, E032) : quatrième tour « Lis le fichier
  confidentiel/outil-lent-e2e [lent] » (`read_file` ralenti de 1,5 s par `launch_app.py`). Un
  `MutationObserver` note le nom accessible du robot (« réfléchit », puis « utilise un outil »
  avant tout clic sur le rail, puis « au repos »), le halo de « Lecture de fichier » et le chemin
  tracé vers lui ; l'étape de l'outil porte `tools.read_file` dans ses liens. Rail : le tour
  précédent, ouvert à la main, se replie au nouveau tour ; en direct, seule la ligne courante est
  dépliée ; un clic sur « Décrit les outils » fige la vue, la ligne reste dépliée, celles venues
  après non ; « Suivre le direct » revient au direct, défilé en bas. Journal : le titre compte
  les événements reçus, les lignes (« Morceaux de réponse × N » = les `model_delta` du dernier
  appel) font ce compte, chaque ligne dit le libellé de son type et le résume ; chaque type du
  catalogue a son libellé en `fr`/`en`/`de` et un résumé (les manques déjà notés sortent en
  `KNOWN`).
- `system_prompt` (E042) : un tour après le rejeu ; « Comparer » s'ouvre toujours sur l'origine
  (à gauche) et son rejeu.
- `h5` (E032) : nœuds rangés par type et hébergement (outils du poste, outils réseau) ; pendant
  l'attente, halo sur H5 et chemin arrêté sur ✋ ; après « ne plus demander », H5
  « · désactivé » dans la bande. `hooks` : premier tour en « [lent] » : halo sur H1 et ✖ à la
  bande pendant la suite du tour, « · ✖ a bloqué » ensuite, l'étape du blocage liée à
  `hooks.h1`. `data_flows` : serveur local et data.gouv.fr dans leurs zones.
- `panes` (E033), scénario nouveau : flèches sur les poignées (16 px, seuls les voisins
  bougent, minimum de 240 px), poignée du schéma (↓ : le schéma perd 16 px), double clic
  (proportions par défaut, oubliées du stockage), masquage inscrit aussitôt dans
  `localStorage["wavestack.panes"]`, disposition mémorisée rendue au rechargement, stockage
  illisible, cinq volets masqués et tailles invalides refusés.
- `rag_rerank` (E094) : `POST /_e2e/reranker_fail` fait refuser le fichier du reranker (503) :
  l'échec est dit sous l'interrupteur « Reranking », « Télécharger » revient ; plus loin, une
  question avec `[reranker-en-panne]` fait lever le faux reranker : étape « Reranking » en
  erreur, dépliée, l'erreur dite.
- `subagent` (E125) : `aria-expanded` lu dans le même `evaluate` que le clic, avant la
  reconstruction du panneau. `--channel msedge` joue la tranche sous Edge.
- `priced_estimate` (E135), scénario nouveau joué après `gemini_shape` : `fake_m` (prix du
  préréglage Mistral, `stream_usage = false`) ; « ≈ » sur la ligne de coût de l'appel, dans
  l'en-tête du tour et devant la dépense de la barre haute.
- `gemini_shape` (E141) : `_footprint_line` attend que la page ait rendu le tour terminé, puis
  déplie l'étape « Appelle le modèle » jusqu'à voir son empreinte (sans délai fixe).

## Suites de la recette PC du 02/10

- `markdown`, scénario nouveau : « [markdown] » répond `MARKDOWN_SAMPLE` (`fake_openai.py`).
  La Vue humain rend titre (`##` en h4), listes à puces imbriquées, liste numérotée
  (`start="3"`), gras, italique, code en ligne, bloc `~~~` fermé et bloc ```` ``` ```` encore
  ouvert, et un seul lien (`https://example.org`, `target="_blank"`, `rel="noopener
  noreferrer"`) ; le HTML du modèle, `javascript:`, le lien relatif, l'image, la règle, le
  tableau et la citation restent du texte (aucun `img`, `b`, `hr`, `table`, aucune alerte). Un
  `MutationObserver` vérifie que la `.bubble-text` rendue ne disparaît jamais pendant le flux.
  Contexte LLM, le journal (`model_delta`) et `#chat-live` gardent les `**` ; Orchestration ne
  rend rien ; même rendu après rechargement.
- `diagnostic_wait`, scénario nouveau : `page.route` retient `GET /api/diagnostic` 1,5 s ;
  pendant ce temps, « Diagnostic en cours… » dans Contrôles, Modèles détectés et Modèles cloud,
  puis chaque liste le remplace par ses lignes (R1).
- `provider_errors` : « [quota0] » (429, `x-ratelimit-limit-req-minute: 0`, `x-request-id`)
  laisse `outbound_response` entre `outbound_request` et `model_call_ended` : 429, quota en
  clair, `x-request-id` masqué (sa valeur n'entre pas dans le journal) ; libellé « Réponse
  d'erreur reçue » et résumé `429 · POST url · quota` dans le journal, rien dans Orchestration,
  message D6 inchangé ; conversation vidée ensuite (R2). Le faux fournisseur écoute sur la
  boucle locale, jamais tracée (AD-15) : `wavestack_e2e.py` remplace `factory._traced` pour
  les seules requêtes dont le corps contient `[quota0]`.
- `panes` : chaque volet en mode focus (⛶), à 1280×672 puis 1440×900 ; défilement
  d'Orchestration vers son dernier bloc « Données sortantes » (un tour `network_tools` d'abord
  s'il n'y en a pas), molette, Fin : `document.scrollingElement.scrollTop` reste à 0 et la barre
  basse reste sous les volets (`body.focus-mode .right:has(…) { min-height: 0; }`).

## Finition V1 (nuit du 03/10 et revue de la PR #21)

Contrôles ajoutés aux scénarios existants (le nouveau, `reasoning_dropped`, est décrit plus
haut) :

- `h5` (#16) : pendant l'attente, la carte nomme l'outil par son libellé (« Jours fériés »),
  elle est gardée d'un rendu à l'autre, Orchestration montre la validation sans bouton (libellé
  et nom de l'outil), la puce « + Vue humain » est liée (●) quand ce volet est masqué ; après
  « Autoriser », le focus revient à la carte.
- `hooks` (#16) : H1 dit « ✖ a bloqué » avant « Vider la conversation », plus après.
- `rag` (#20) : fichier servi lentement, « Arrêter » une fois le `.part` ouvert : ligne neutre
  sur la carte (« … le fichier en cours est supprimé … »), ni `harness_error`, ni ligne rouge,
  ni copie à la main, aucun `.part` laissé.
- `rag_rerank` (#20, après l'échec E094) : le fichier du reranker servi lentement
  (`/_e2e/reranker_slow`), « Arrêter » une fois son `.part` ouvert : ligne neutre sous
  l'interrupteur « Reranking », à la place de la ligne rouge de l'échec, effet
  `model_download_stopped` du composant `rag.reranker`, aucun `.part` laissé, « Télécharger »
  de nouveau proposé.
- `markdown` (#18) : `markdown.js` importé dans la page rend les emphases qui suivent une
  ouverture non fermée, et 10 000 caractères de `*` non fermés en moins de 100 ms (≈ 550 ms
  avec l'ancien parcours cubique).
- `gemini_shape` (#27) : l'infobulle de la dépense dit « x $ sur <plafond> $ » et « ce total » /
  « ces totaux » selon les totaux affichés ; le diagnostic dit le plafond et la dépense sous
  les modèles cloud (`#cloud-cap`).

## Lot 1 du plan de corrections du 2026-10-04

- `diagnostic` : sur `/`, `<title>` « WaveStack — Atelier Harnais », un seul `h1` masqué
  (`.sr-only`) et l'onglet « Harnais » courant ; `model_catalog` : `/diagnostic` titré
  « Diagnostic et modèles », lien `#models-link` vers `/models`.
- `themes`, `mcp_lab`, `rag_lab`, `llm_screen` : la barre commune à cinq onglets
  (`Harnais · LLM · RAG · MCP · 🛠️ Diagnostic`), titres et `h1` complets des ateliers.
- `forced_native` : le « ? » d'« Actions forcées » ouvre son aide, ancrée sous le bouton, encore
  ouverte après un nouveau rendu du panneau.
- `gemini_shape`, `local_server`, `priced_estimate` : la dépense sur trois lignes (« Dépense
  estimée », « 💰 … », « 🍃 … »), deux sans appel payant, l'empreinte visible à 1600, 1440 et
  1280 px, en mode normal et projection.
- `local_server` (`_cache_not_reused`) : « Prompt système » basculé entre deux tours,
  `prefix_not_reused` avec `again_tokens`, ligne « Cache non réutilisé » « <cause> · N tokens
  relus », repliée en fin de tour, son message au clic.

## Déclencheurs du faux modèle

La réponse dépend du dernier message de l'utilisateur (sans le texte ajouté par H3 ni les
extraits RAG), des outils proposés et des résultats déjà reçus dans le tour. Un appel déjà fait
dans le tour avec les mêmes arguments n'est pas refait ; le même outil peut l'être avec
d'autres (story 21) :

| Message contient | Réponse |
|---|---|
| « heure », « Combien font », « recette_crepes », « confidentiel », « férié », « Wikipédia », « compte rendu », « MCP … veut dire » | appel de l'outil correspondant s'il est proposé (`get_datetime`, `calculator`, `read_file`, `public_holidays`, `wikipedia_summary`, `load_skill`, `load_tool_doc` puis `local__define_term`), puis « D'après le résultat de l'outil : … » |
| « alertes_siem », « confidentiel/chemin » (story 21) | `read_file` sur `alertes_siem.log`, ou sur le fichier confidentiel nommé dans le message, sous-dossiers compris (`confidentiel/budget_projet.txt` s'il n'en nomme aucun) |
| « fichiers disponibles » (story 21, SOC) | `read_file` sur `.`, puis sur le fichier confidentiel de la liste qui parle de comptes ou de privilèges ; bloqué par H1 : « … je transmets la vérification à un analyste habilité. » |
| « Entra ID », « data.gouv », « qualité de l'air » (stories 21 et 27) | recherche de Microsoft Learn ou de data.gouv.fr si elle est proposée (requête « air » quand le message parle de la qualité de l'air, « cybersécurité » sinon) ; en lazy loading, `load_tool_doc` d'abord (outil lu dans la description du méta-outil) ; serveur absent : les déclencheurs suivants s'appliquent, puis « Sans la documentation Microsoft Learn… » / « Sans accès à data.gouv.fr… » |
| « Délègue … sous-agent » (story 19) | appel de `delegate`, tâche « Lis le fichier guide_harnais.md et résume-le… » (` [lent]` recopié ; avec « page web » : tâche de lecture de page, le sous-agent appelle `fetch_page`) ; le sous-agent (tâche avec « guide_harnais ») appelle `read_file`, puis répond « D'après le résultat de l'outil : … » |
| « Je m'appelle X » / « Comment je m'appelle » | retient X s'il est dans l'historique |
| « lot N » avec un résultat d'outil (story 20) | « D'après le journal : » suivi de la ligne du lot N, ou « Le résultat de l'outil ne mentionne pas le lot N. » si la compression l'a coupée |
| « journal_serveur » (story 20) | appel de `read_file` sur `journal_serveur.log`, puis « D'après le journal : » suivi de la ligne ERROR reçue (gardée par la compression) |
| « mot de passe » et « Exemplia » | avec les extraits RAG : « D'après l'extrait N (Politique des mots de passe) : au minimum 14 caractères » ; sans : « Je ne connais pas les règles d'Exemplia » |
| « Retiens que … » / « Rappelle-moi mon prénom » | appel de `remember` (mémoire globale) / prénom lu dans le message système |
| prompt système « … toujours en une phrase, comme un pirate » | « Arrr ! … » |
| « harnais » | réponse longue, courte si le skill Caveman est chargé |
| `[mal-formé]` / `[mal-formé-toujours]` / `[outil-inconnu]` | arguments JSON invalides puis correction / à chaque essai / outil inexistant |
| `[tool_use_failed]` | 400 `tool_use_failed` (façon Groq) |
| `[erreur429]`, `[erreur500]`, `[erreur401]`, `[flux-erreur]` | refus du fournisseur, erreur au milieu du flux |
| `[quota0]` (recette du 02/10) | 429 `Rate limit exceeded` avec `x-ratelimit-limit-req-minute: 0`, `x-ratelimit-remaining-req-minute: 0` et `x-request-id` (Mistral sans plan) ; tracé malgré la boucle locale par `wavestack_e2e.py` |
| `[markdown]` (recette du 02/10) | `MARKDOWN_SAMPLE` : le sous-ensemble Markdown rendu par la Vue humain et les injections qui doivent rester du texte ; son dernier bloc de code reste ouvert |
| `[coupé]`, `[long]`, `[lent]`, `[raisonne]` | `finish_reason: length`, texte long, flux lent (pour « Arrêter »), champ `reasoning` |
| `[jeté]` (finition V1, `POST /v1/messages` seulement) | `message_start` porte `input_transformations` (`thinking_dropped`, `prefix_binding_mismatch`, chemin `messages.1.content.0`) : le fournisseur dit avoir jeté un raisonnement ; recopié dans la tâche du sous-agent comme ` [lent]` |
| `[sans-usage]` | réponse sans `usage` en fin de flux (tokens estimés par WaveStack) |
| `[reranker-en-panne]` | (lu par le faux reranker de `wavestack_e2e.py`, pas par le faux modèle) le reranking lève, l'étape « Reranking » est en erreur |
