# Prompt pour le Claude Code du PC cible : recette intermédiaire (stories 22 à 27 et 31 à 34)

À coller tel quel dans Claude Code sur le PC cible, depuis le dossier du dépôt. Il couvre le
code du commit `175eb5a` (PR 2), testé au commit `3ed8482` qui ajoute le cahier. Les stories 29, 30 et 28 auront leur propre prompt
(`prompt-test-pc-2026-09-29.md`).

---

Tu vas vérifier toi-même, sur ce poste, le plus possible des tests de recette de WaveStack pour
les stories 22 à 27 et 31 à 34, afin qu'Anaël n'ait plus à faire à la main que ce qu'une machine
ne peut pas juger. Travaille en français.

## Contexte

- Poste : Windows 11, PowerShell, **sans droits d'administrateur**, CPU seulement, 16 Go de RAM.
  Modèles réels : Qwen3.5-2B et Qwen3.5-4B en GGUF (dossier des modèles de WaveStack, en général
  `%LOCALAPPDATA%\WaveStack\models`), Ollama s'il tourne, clés Groq et Mistral éventuelles
  (variables d'environnement ou `api_keys.json`). Navigateurs : Chrome et Edge.
- Dépôt : branche `claude/lucid-cori-1rkbjf`, commit à tester `3ed8482` : le code de la fin de
  la story 31 (`175eb5a`) plus le cahier de recette. Les commits suivants de la branche
  (stories 29, 30, 28) ne font pas partie de ce test.
- Liste des tests : le cahier `_bmad-output/implementation-artifacts/cahier-recette-nuit-2026-09-28.html`
  (identifiants P1 à P7 et N22-1 à N34-6, chacun avec geste, attendu et critère). Version en
  ligne, où Anaël enregistre ses résultats : https://claude.ai/artifact/7Er6qrF3fcLtTsMoY6meLf
- Détail de chaque story : `_bmad-output/specs/spec-agentic-harness-training-demo/stories/{id}-*.md`,
  sections « À vérifier sur PC », « Décisions prises par défaut » et « Auto Run Result ».
- Précédent utile : `_bmad-output/implementation-artifacts/resultats-test-pc-palier-2-2026-09-27.md`
  (script qui pilote une `AppSession` hors du dépôt, avec un dossier de données jetable).

## Règles, à respecter sans exception

1. **Ne modifie rien sans l'accord d'Anaël** : ni le code, ni la configuration du dépôt, ni son
   dossier de données réel. Tes scripts vivent hors du dépôt (dossier temporaire) et utilisent un
   dossier de données jetable (`WAVESTACK_DATA_DIR` vers une copie, `models` en jonction vers le
   vrai dossier). Si un test échoue, décris l'anomalie et propose un correctif : ne l'applique pas.
2. **Mesures** : avant toute mesure de temps ou de mémoire, demande à Anaël de fermer Edge,
   Outlook et Teams, attends sa confirmation, et note l'état réel (Edge se relance parfois seul :
   vérifie avec `Get-Process msedge`). Claude in Chrome passe par Chrome, pas par Edge.
3. **llama-server** : jamais sans `-c` quand le 2B est chargé (`-c 4096`, ou la fenêtre testée).
   S'il n'est pas installé, suis la procédure sans droits d'administrateur de la section
   Préparation du cahier ; s'il est bloqué (proxy, AppLocker), marque ses tests « non fait (poste) ».
4. **Consigne au fil de l'eau** dans `_bmad-output/implementation-artifacts/resultats-test-pc-2026-09-29.md`
   (ce fichier seul, pas de commit) : pour chaque vérification, identifiant du test, commande ou
   geste, attendu, obtenu (valeur mesurée), statut OK / KO / non fait, et moyen utilisé (script,
   pytest, E2E, Playwright, Claude in Chrome).
5. N'appelle un modèle cloud (Groq, Mistral) que pour les tests qui le demandent : chaque appel
   envoie des données hors du poste.

## Étapes

### 1. Installation et tests automatiques

```powershell
git fetch origin claude/lucid-cori-1rkbjf
git checkout --detach 3ed8482
uv sync --extra compression
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
$env:WAVESTACK_TEST_GGUF = "<chemin du Qwen3.5-2B .gguf>"
$env:WAVESTACK_TEST_MODELS_DIR = "$env:LOCALAPPDATA\WaveStack\models"
uv run pytest -q -m model
$env:WAVESTACK_TEST_WINDOWS_FILES = "1"; uv run pytest -q; Remove-Item Env:WAVESTACK_TEST_WINDOWS_FILES
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py
```

Chromium pour Playwright est déjà dans `%LOCALAPPDATA%\ms-playwright` : ne lance pas
`playwright install`. Attendus : pytest vert (1 194 passés dans le conteneur), E2E sans FAIL
(609 PASS dans le conteneur). Note toute différence propre à Windows.

### 2. Plan de vérification

Lis le cahier et les sections « À vérifier sur PC » des dix stories. Classe chaque test selon le
moyen qui le vérifie le mieux : **script** (`AppSession` et vrai modèle), **Playwright** (vraie
application, rendu, mise en page, contrastes), **Claude in Chrome** (regard sur l'écran réel,
survols, clics), ou **humain seulement**. Écris ce plan en tête du fichier de résultats, puis
exécute-le dans cet ordre.

### 3. Script sur les vrais modèles

Un script jetable pilote une `AppSession` avec le vrai Qwen3.5-2B (moteur intégré), s'abonne au
journal d'événements et relève la RSS (processus et enfants). Cible au moins :

- **N24** : budget dynamique réel (RAM totale, disponible, calcul affiché) ; base mémoire après
  libération (jamais « 0 Mo ») ; « Arrêter » pendant la sonde d'un GGUF non sondé (enfant tué en
  moins de 1 s, rien dans `failed_probes`) ; coût d'un modèle Ollama (llama3.2:3b accepté ?) face à
  ce qu'Ollama occupe vraiment (`ollama ps`) ; raisons accentuées bien décodées et raisons abîmées
  réparées à la lecture.
- **N26** : coût affiché de 8 192 et 16 384 (cache de contexte, temps de lecture au débit mesuré)
  face à la RSS et au temps réels ; rechargement du 2B à 8 192 avec conversation gardée ; refus au
  budget s'il se produit ; borne de llama-server `-c`.
- **N27** : comportement réel du 2B sur chaque scénario revu : `load_skill` appelé (skills),
  `local__define_term` appelé (MCP complet et lazy), lecture de `journal_serveur.log`
  (compression), nom exact `alertes_siem.log` et escalade après le blocage de H1 (SOC), quiz du
  sous-agent sans RAG (durée par quiz, re-délégation) ; test `fits` à 4 096 avec le vrai tokenizer
  (le préréglage « Guide du harnais » tient-il dans la fenêtre ?).
- **N32-2 et N32-4** : « Texte exact » identique, octet pour octet, au prompt envoyé (local) et au
  corps JSON (cloud) ; sections et déjà-lu cohérents avec `model_call_ended`.
- **N23** : vrai appel Wikipédia avec son User-Agent et le contact ; en-têtes vers data.gouv.fr
  derrière le proxy ; aucune clé Groq dans `events-*.jsonl` ni dans les journaux.
- **N25** : `/api/diagnostic` et `/models` sur le vrai dossier des modèles : éditeurs, tailles,
  raisonnement (jamais, toujours, activable), temps du premier appel (< 2 s visé).

### 4. Playwright sur la vraie application

Lance WaveStack normalement sur le vrai 2B, puis pilote-le avec Playwright (Chromium) :
mises en page à 1 280, 1 366, 1 440 et 1 600 px de large, en normal et en mode projection
(barre haute sur une ligne, « Réinitialiser » visible, puces « · lié » lisibles) ; balayage des
contrastes en clair et en sombre (volets, tiroirs, panneau « Fenêtre », liste « Volets », pages
`/diagnostic` et `/models`) ; captures de chaque volet dans les deux thèmes, rangées dans un
dossier temporaire et citées dans le fichier de résultats.

### 5. Claude in Chrome, si l'extension est disponible

Si les outils Claude in Chrome sont disponibles dans ta session, ouvre l'application réelle dans
Chrome et fais toi-même les gestes visuels et interactifs du cahier, en regardant l'écran :
survol et focus clavier liés entre les volets, sélection puis Échap (N34) ; onglets « Agent
principal » et « Sous-agent », tiroir de la mémoire, « Annuler » d'une action forcée, consigne
repliée (N22) ; code couleur et lignes d'état des briques (N33) ; bloc « Données sortantes » et
clic sur un nœud réseau (N23) ; appels numérotés, déjà-lu, JSON repliables, « Texte exact »
(N32) ; sélecteur de modèles regroupé et page `/models` (N25) ; panneau « Fenêtre » (N26) ;
sélecteur de thème, sélecteur compact sous 1 400 px, autre onglet et retour arrière (N31).
Décris ce que tu vois et joins une capture pour chaque point jugé. Sans l'extension, fais ces
contrôles avec Playwright (captures et assertions) et marque ce qui demande un œil humain.

### 6. Ce qui reste à la main

Ne fais pas semblant de juger ce qui demande une personne : Narrateur, lisibilité au projecteur à
3 m ou dans Teams, rendu dans Edge, suivi du mode sombre de Windows, test avec un novice. Pour
ces points, prépare seulement le terrain (application lancée, bon scénario, bon thème) et dis à
Anaël quoi regarder.

## Rendu final

1. Le fichier `resultats-test-pc-2026-09-29.md` complet.
2. Une synthèse par story : OK / KO / non fait, avec chaque mesure face à son critère.
3. **La liste des identifiants du cahier que tu as vérifiés** (statut et valeur), pour qu'Anaël
   les reporte ou les saute, et **la liste de ceux qui restent à faire à la main**, dans l'ordre
   du cahier. Si Claude in Chrome est disponible et qu'Anaël l'accepte, reporte toi-même tes
   statuts et tes valeurs dans le cahier en ligne (bouton de statut et champ de note de chaque
   test).
4. Les anomalies, avec leur cause probable, leur criticité et un plan de correction proposé.
   Aucune modification du code sans l'accord d'Anaël.
