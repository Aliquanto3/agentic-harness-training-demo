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
  `/v1/models`, `/_e2e/requests` pour relire les corps reçus). Clé attendue : `e2e-fake-key`.
  `/_e2e/model.gguf` est le fichier du faux modèle d'embedding : 503 tant que
  `POST /_e2e/model_ready` n'a pas été appelé (un téléchargement qui échoue, puis réussit).
  `/_e2e/reranker.gguf` est celui du faux reranker (story 16), toujours servi.
- `stack.py` : réseau sortant de WaveStack coupé (proxy fermé, voir plus haut), dossier de
  données temporaire, `settings.json` qui déclare trois modèles sur le faux serveur, `fake`
  (`wavestack-fake`), `fake_b` (`faux-modele-b`, pour le changement de modèle de la
  story 17) et `fake_r` (`faux-modele-raisonne`, `reasoning: {format: "field", always: true}`,
  pour la carte Raisonnement verrouillée de la story 33), clé par
  `key_env = WAVESTACK_FAKE_API_KEY`, lancement des deux serveurs sur
  `127.0.0.1`. `wavestack.toml` n'est jamais modifié. Pour le RAG (story 15),
  `settings.json` pointe `[rag]` vers un index dans ce dossier, absent au départ comme sur
  une installation neuve (le scénario `rag` le construit depuis la carte), et déclare un faux
  fichier de modèle servi par le faux serveur ; de même pour `[rag.reranker]` (story 16).
- `fake_local_server.py` (story 18) : un faux llama-server (`/health`, `/props` avec le gabarit
  Qwen3.5, `/v1/models`, `/tokenize` avec les pièces, `/detokenize`, `/completion` en SSE ;
  tokenizer octet par octet, marqueurs du gabarit en un token) et un faux Ollama (`/api/tags`,
  avec `details` `{family: qwen3, parameter_size: 0.6B}` depuis la story 25, `/api/ps`,
  `/api/generate` pour `keep_alive: 0`) qui sert un modèle sans GGUF sur le disque.
  `stack.py` les lance sur deux ports libres, que `settings.json` déclare en
  `[net.loopback_ports]` ; `/_e2e/requests` relit les corps reçus.
- `wavestack_e2e.py` : le lanceur de WaveStack pendant le parcours. Il lance `wavestack.cli`
  tel quel (garde réseau d'abord), la brique RAG chargeant le faux modèle d'embedding de
  `tests/fake_embedder.py` (sac de mots haché, 64 dimensions, aucun GGUF nécessaire) et le
  faux reranker de `tests/fake_reranker.py` (part des mots de la question présents dans
  l'extrait), et applique `launch_app.py`.
- `launch_app.py` : ralentit la seule préparation de `fake_b` (`WAVESTACK_E2E_LOAD_DELAY_S`,
  2 s par défaut) : sans cela, un modèle cloud se prépare trop vite pour que le parcours voie
  le chronomètre « Chargement du modèle… ».
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
  survol, « · brique éteinte » dans le résumé ; « Afficher plus » seulement si la consigne
  dépasse 3 lignes.
- `system_prompt` : « Enregistrer » désactivé tant que le texte est inchangé, puis
  « Prompt système enregistré. » (`role=status`), effacé à la saisie suivante.
- `subagent` : onglets « Agent principal » / « Sous-agent subN » (`role=tablist`), retour à
  « Agent principal » au tour suivant ; « Annuler » et un second clic sur « Déléguer au
  sous-agent » ferment le formulaire.
- `soc` : consigne de 1 276 caractères sur 3 lignes, « Afficher plus » / « Réduire », champ
  et dernière bulle visibles ; laissée dépliée, repliée au lancement d'un autre scénario.
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
  « llama-server »), puis « Réseau · Mistral (Mistral AI) » et « Réseau · gpt-oss (OpenAI) »
  (préréglages de `wavestack.toml`, sans clé) et « Réseau · Autres éditeurs » (les trois faux
  modèles cloud) ; dans le groupe Qwen, le faux Ollama (0.6B) avant le faux llama-server
  (taille inconnue) ; chaque modèle commence par « Local · » ou « RÉSEAU · » ; « Tableau des
  modèles et de leurs capacités… » puis « Autre fichier ou clé API… » en dernier. « Ouvrir le
  tableau » mène à `/models` : onglet « Modèles » courant, « Diagnostic » vers `/diagnostic`
  (mêmes onglets) ; lignes du faux llama-server (Qwen, outils « oui », « activable »,
  « 4 096 tokens »), de R (« toujours »), de `wavestack-fake` (« jamais », « actif »), du faux
  Ollama (« inconnu », raison « introuvable » visible), « RÉSEAU » sur chaque ligne cloud,
  étiquette sur le jeton jaune, un en-tête par groupe du sélecteur. Puis R activé depuis le
  sélecteur : carte Raisonnement verrouillée et ligne « toujours », « actif » ; retour à A :
  ligne « jamais », carte indisponible « ne déclare pas de raisonnement ». Captures
  `43-modeles-selecteur.jpg` (la liste affichée en boîte de liste : une liste native ne se
  capture pas ouverte) et `44-modeles-tableau.jpg` (page entière).

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
  summary replie, un second déplie. Retour à « Lecture groupée » (mémorisée par le navigateur).
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
| `[coupé]`, `[long]`, `[lent]`, `[raisonne]` | `finish_reason: length`, texte long, flux lent (pour « Arrêter »), champ `reasoning` |
| `[sans-usage]` | réponse sans `usage` en fin de flux (tokens estimés par WaveStack) |
