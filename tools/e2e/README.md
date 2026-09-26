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

Playwright n'est pas une dépendance du projet : `--with` l'ajoute le temps de la commande.
Il faut un Chromium de la révision attendue par Playwright 1.56 (`PLAYWRIGHT_BROWSERS_PATH`),
sinon le script essaie `/opt/pw-browsers/chromium`. Code de sortie 1 si une vérification
échoue ; `KNOWN [Ax]` signale une anomalie déjà décrite dans
`_bmad-output/implementation-artifacts/test-e2e-palier-1-cloud.md`, sans faire échouer.

Les captures (JPEG) sont réécrites dans `tools/e2e/screenshots/`.

Pour explorer à la main : `uv run python tools/e2e/stack.py` lance le faux modèle et WaveStack
(adresse affichée), puis choisissez « Faux fournisseur (e2e) » au diagnostic.

## Fichiers

- `fake_openai.py` : le faux serveur (`/v1/chat/completions` en SSE avec `usage`,
  `/v1/models`, `/_e2e/requests` pour relire les corps reçus). Clé attendue : `e2e-fake-key`.
  `/_e2e/model.gguf` est le fichier du faux modèle d'embedding : 503 tant que
  `POST /_e2e/model_ready` n'a pas été appelé (un téléchargement qui échoue, puis réussit).
- `stack.py` : dossier de données temporaire, `settings.json` qui déclare deux modèles sur le
  faux serveur, `fake` (`wavestack-fake`) et `fake_b` (`faux-modele-b`, pour le changement de
  modèle de la story 17), clé par `key_env = WAVESTACK_FAKE_API_KEY`, lancement des deux
  serveurs sur `127.0.0.1`. `wavestack.toml` n'est jamais modifié. Pour le RAG (story 15),
  `settings.json` pointe `[rag]` vers un index dans ce dossier, absent au départ comme sur
  une installation neuve (le scénario `rag` le construit depuis la carte), et déclare un faux
  fichier de modèle servi par le faux serveur.
- `fake_local_server.py` (story 18) : un faux llama-server (`/health`, `/props` avec le gabarit
  Qwen3.5, `/v1/models`, `/tokenize` avec les pièces, `/detokenize`, `/completion` en SSE ;
  tokenizer octet par octet, marqueurs du gabarit en un token) et un faux Ollama (`/api/tags`,
  `/api/ps`, `/api/generate` pour `keep_alive: 0`) qui sert un modèle sans GGUF sur le disque.
  `stack.py` les lance sur deux ports libres, que `settings.json` déclare en
  `[net.loopback_ports]` ; `/_e2e/requests` relit les corps reçus.
- `wavestack_e2e.py` : le lanceur de WaveStack pendant le parcours. Il lance `wavestack.cli`
  tel quel (garde réseau d'abord), la brique RAG chargeant le faux modèle d'embedding de
  `tests/fake_embedder.py` (sac de mots haché, 64 dimensions, aucun GGUF nécessaire), et
  applique `launch_app.py`.
- `launch_app.py` : ralentit la seule préparation de `fake_b` (`WAVESTACK_E2E_LOAD_DELAY_S`,
  2 s par défaut) : sans cela, un modèle cloud se prépare trop vite pour que le parcours voie
  le chronomètre « Chargement du modèle… ».
- `run_e2e.py` : les scénarios Playwright ; le journal est lu en parallèle sur `/api/stream`.
- `tests/test_e2e_fake_openai.py` : tests pytest du faux serveur, sans navigateur.

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
compression » dans Contexte LLM, « Comparer », étape toujours là après rechargement. Capture :
`24-compression-avant-apres.jpg`.

## Déclencheurs du faux modèle

La réponse dépend du dernier message de l'utilisateur (sans le texte ajouté par H3 ni les
extraits RAG), des outils proposés et des résultats déjà reçus dans le tour :

| Message contient | Réponse |
|---|---|
| « heure », « Combien font », « recette_crepes », « confidentiel », « férié », « Wikipédia », « compte rendu », « MCP … veut dire » | appel de l'outil correspondant s'il est proposé (`get_datetime`, `calculator`, `read_file`, `public_holidays`, `wikipedia_summary`, `load_skill`, `load_tool_doc` puis `local__define_term`), puis « D'après le résultat de l'outil : … » |
| « Délègue … sous-agent » (story 19) | appel de `delegate`, tâche « Lis le fichier guide_harnais.md et résume-le… » (` [lent]` recopié ; avec « page web » : tâche de lecture de page, le sous-agent appelle `fetch_page`) ; le sous-agent (tâche avec « guide_harnais ») appelle `read_file`, puis répond « D'après le résultat de l'outil : … » |
| « Je m'appelle X » / « Comment je m'appelle » | retient X s'il est dans l'historique |
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
