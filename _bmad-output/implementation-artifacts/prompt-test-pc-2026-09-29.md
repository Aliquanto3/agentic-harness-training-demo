# Prompt pour le Claude Code du PC cible : recette de la nuit du 2026-09-28 (stories 22 à 34)

À coller tel quel dans Claude Code sur le PC cible, depuis le dossier du dépôt. Il remplace le
prompt intermédiaire (`prompt-test-pc-intermediaire-2026-09-29.md`) et couvre toute la nuit :
stories 22 à 27 et 31 à 34 (déjà dans le cahier `cahier-recette-nuit-2026-09-28.html`), plus
29 (écran « LLM nu »), 30 (atelier RAG) et 28 (guide et cahier du palier 2 corrigés).

---

Tu vas vérifier toi-même, sur ce poste, le plus possible des points « À vérifier sur PC » des
stories de la nuit du 2026-09-28, puis produire un cahier de recette interactif limité à ce
qu'une personne doit encore faire. Travaille en français.

## Contexte

- Poste : Windows 11, PowerShell, **sans droits d'administrateur**, CPU seulement, 16 Go de RAM.
  Modèles réels : Qwen3.5-2B et Qwen3.5-4B en GGUF (en général `%LOCALAPPDATA%\WaveStack\models`),
  Ollama s'il tourne, clés Groq et Mistral éventuelles (variables d'environnement ou
  `api_keys.json`). Navigateurs : Chrome et Edge.
- Dépôt : branche `claude/lucid-cori-1rkbjf`, dernier commit (celui du rapport de nuit
  `rapport-nuit-2026-09-28.md`). PR : https://github.com/Aliquanto3/agentic-harness-training-demo/pull/2
- À lire d'abord : `_bmad-output/implementation-artifacts/rapport-nuit-2026-09-28.md` (état de
  chaque story, décisions prises par défaut, points différés), puis, pour chaque story, sa spec
  `_bmad-output/specs/spec-agentic-harness-training-demo/stories/{id}-*.md` (sections
  « À vérifier sur PC », « Décisions prises par défaut », « Auto Run Result »).
- Déjà en place : le cahier `_bmad-output/implementation-artifacts/cahier-recette-nuit-2026-09-28.html`
  (stories 22 à 27 et 31 à 34, tests P1 à P7 et N22-1 à N34-6), publié en ligne sur
  https://claude.ai/artifact/7Er6qrF3fcLtTsMoY6meLf où Anaël a peut-être déjà enregistré des
  résultats. **Demande-lui son compte rendu** (bouton « compte rendu à copier » du cahier) avant
  de commencer, pour ne pas refaire ce qu'il a déjà jugé.
- Guide et cahier du palier 2 corrigés par la story 28 : `guide-test-pc-palier-2.md` et
  `cahier-recette-palier-2.html` (installation de llama-server sans droits d'administrateur,
  tests réécrits). La procédure llama-server est aussi dans le README (« Utiliser un serveur déjà
  lancé »).
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
   S'il n'est pas installé, suis la procédure sans droits d'administrateur du README ; s'il est
   bloqué (proxy, AppLocker, SmartScreen), marque ses tests « non fait (poste) ».
4. **Consigne au fil de l'eau** dans `_bmad-output/implementation-artifacts/resultats-test-pc-2026-09-29.md`
   (ce fichier seul, pas de commit) : pour chaque vérification, story et identifiant (celui du
   cahier quand il existe, sinon `S29-n`, `S30-n`, `S28-n` dans l'ordre de la liste en annexe),
   commande ou geste, attendu, obtenu (valeur mesurée), statut OK / KO / non fait, moyen
   (pytest, E2E, script, Playwright, Claude in Chrome).
5. N'appelle un modèle cloud (Groq, Mistral) que pour les tests qui le demandent : chaque appel
   envoie des données hors du poste. L'atelier RAG et l'écran « LLM nu » tournent hors ligne.

## Étapes

### 1. Installation et tests automatiques

```powershell
git fetch origin claude/lucid-cori-1rkbjf
git checkout claude/lucid-cori-1rkbjf
git pull
uv sync --extra compression --extra rag-alt
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
$env:WAVESTACK_TEST_GGUF = "<chemin du Qwen3.5-2B .gguf>"
$env:WAVESTACK_TEST_MODELS_DIR = "$env:LOCALAPPDATA\WaveStack\models"
uv run pytest -q -m model
$env:WAVESTACK_TEST_WINDOWS_FILES = "1"; uv run pytest -q; Remove-Item Env:WAVESTACK_TEST_WINDOWS_FILES
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only rag rag_rerank rag_lab --no-rag-alt
```

- L'extra `rag-alt` (FAISS 1.15.1, LanceDB 0.39.0, environ 400 Mo, roues seulement) est
  nouveau : note s'il s'installe sans droits d'administrateur et sans compilation. S'il est
  refusé (proxy, AppLocker), continue sans lui : l'atelier RAG grise alors FAISS et LanceDB
  avec la commande d'installation, et c'est un résultat à consigner.
- Chromium pour Playwright est déjà dans `%LOCALAPPDATA%\ms-playwright` : ne lance pas
  `playwright install`.
- Attendus relevés dans le conteneur : pytest vert (1 294 passés, 3 ignorés), E2E sans FAIL
  (voir le rapport pour le nombre exact), branche « sans l'extra » sans FAIL. Note toute
  différence propre à Windows, dont `tests/test_engine_candidates.py` (candidats sur un vrai
  moteur llama.cpp) et `pytest -m model` (candidats et échantillonnage sur le vrai 2B).

### 2. Plan de vérification

Lis la liste consolidée en annexe (story par story, dans l'ordre de la nuit) et le compte rendu
d'Anaël. Pour chaque point encore ouvert, choisis le moyen qui le vérifie le mieux : **script**
(`AppSession` et vrai modèle), **Playwright** (vraie application, rendu, mise en page,
contrastes), **Claude in Chrome** (regard sur l'écran réel, survols, clics), ou **humain
seulement**. Écris ce plan en tête du fichier de résultats, puis exécute-le.

### 3. Script sur les vrais modèles

Un script jetable pilote une `AppSession` avec le vrai Qwen3.5-2B (moteur intégré), s'abonne au
journal d'événements et relève la RSS (processus et enfants). Couvre en priorité :

- **Story 24** : budget dynamique réel, base mémoire après libération, « Arrêter » pendant la
  sonde d'un GGUF non sondé, coût d'un modèle Ollama face à `ollama ps`, raisons accentuées.
- **Story 26** : coût affiché de 8 192 et 16 384 face à la RSS et au temps réels, rechargement à
  8 192 avec conversation gardée, borne `-c` de llama-server.
- **Story 27** : comportement réel du 2B sur chaque scénario revu (`load_skill`,
  `local__define_term`, lecture de `journal_serveur.log`, `alertes_siem.log` et escalade,
  quiz du sous-agent sans RAG) et test `fits` à 4 096 avec le vrai tokenizer.
- **Story 32** : « Texte exact » identique octet pour octet au prompt envoyé (local) et au corps
  JSON (cloud).
- **Story 23** : vrai appel Wikipédia avec User-Agent et contact, aucune clé dans les journaux.
- **Story 25** : `/api/diagnostic` et `/models` sur le vrai dossier des modèles (éditeurs,
  tailles, raisonnement, premier appel < 2 s).
- **Story 29** (écran « LLM nu », `/llm`) : tokenisation par le vrai tokenizer (puces, tokens
  spéciaux, dimensions réelles du 2B), réglages d'échantillonnage réellement appliqués (compare quelques générations du même
  prompt à T = 0, identiques, puis à T = 1,2, variées),
  temps jusqu'au premier token et débit face à l'atelier, candidats et probabilités sur le
  moteur intégré (T = 0 : le token choisi est le premier candidat), chargement pas à pas et
  mémoire face au Gestionnaire des tâches, raisonnement et coupe au budget, **atelier intact**
  (un tour de l'atelier après une génération sur `/llm` relit son cache comme avant).
- **Story 30** (atelier RAG, `/rag`) : chaîne livrée exécutée sur le vrai corpus avec le vrai
  embedding et le vrai reranker (durées, mémoire par étape, effet du reranker sur l'ordre),
  FAISS et LanceDB (temps d'import, mémoire, index construit puis relu, mêmes rangs que la
  recherche exhaustive), BM25 et fusion hybride sur des questions à sigle ou à code, fichiers
  écrits seulement sous le dossier de données, rien sous le dépôt.

### 4. Playwright sur la vraie application

Lance WaveStack normalement sur le vrai 2B, puis vérifie avec Playwright (Chromium) : mises en
page à 1 280, 1 366, 1 440 et 1 600 px de large, en normal et en mode projection (barre haute sur
une ligne avec ses liens « LLM nu » et « Atelier RAG », « Réinitialiser » visible, puces « · lié »
lisibles) ; balayage des contrastes en clair et en sombre sur l'atelier, `/diagnostic`,
`/models`, `/llm` et `/rag` ; captures de chaque écran dans les deux thèmes, rangées dans un
dossier temporaire et citées dans le fichier de résultats.

### 5. Claude in Chrome, si l'extension est disponible

Si les outils Claude in Chrome sont disponibles dans ta session, ouvre l'application réelle dans
Chrome et fais toi-même les gestes visuels et interactifs : vue liée et Échap (34), onglets,
tiroirs, « Annuler », consigne repliée (22), code couleur et lignes d'état (33), bloc « Données
sortantes » et nœud réseau (23), appels numérotés, déjà-lu, JSON repliables (32), sélecteur de
modèles et `/models` (25), panneau « Fenêtre » (26), thèmes et sélecteur compact (31), écran
`/llm` (réglages, génération en direct, survol et clavier sur les candidats, couloirs Réflexion
et Réponse) (29), atelier `/rag` (ajouter, retirer, déplacer, options grisées avec leur raison,
comparaison A/B) (30). Décris ce que tu vois et joins une capture pour chaque point jugé. Sans
l'extension, fais ces contrôles avec Playwright et marque ce qui demande un œil humain.

### 6. Ce qui reste à la main

Ne juge pas ce qui demande une personne : Narrateur, lisibilité au projecteur à 3 m ou dans
Teams, rendu dans Edge, suivi du mode sombre de Windows, test avec un novice, installation de
llama-server derrière le proxy de l'entreprise. Prépare seulement le terrain et dis à Anaël quoi
regarder.

### 7. Ensuite seulement : le cahier de recette interactif

Quand tout ce qui précède est fait et consigné, génère un cahier de recette interactif en HTML,
**limité à ce qui reste à faire à la main** (points « humain seulement », points KO à revoir,
points que tu n'as pas pu faire) :

- un test par point : identifiant, story, durée estimée, prérequis, geste pas à pas numéroté
  (où cliquer, quoi saisir, avec les libellés exacts de l'interface), ce qu'il faut voir, le
  critère OK / KO, ce qu'il faut rapporter, **et la mesure déjà obtenue par la machine** pour
  comparer ; étiquette « Mesure » et rappel Edge / Outlook / Teams fermés quand il le faut ;
- enregistrement des résultats : capacité `db` de l'artefact, repli dans le navigateur
  (`localStorage` protégé), bouton « compte rendu à copier » ; reprends le mécanisme du cahier
  `cahier-recette-nuit-2026-09-28.html` avec une nouvelle clé de stockage ;
- copie locale dans `_bmad-output/implementation-artifacts/cahier-recette-pc-2026-09-29.html`
  (pas de commit sans accord), puis **publication en artefact** avec la capacité `db`, et
  donne le lien à Anaël.

## Rendu final

1. Le fichier `resultats-test-pc-2026-09-29.md` complet.
2. Une synthèse par story : OK / KO / non fait, chaque mesure face à son critère.
3. La liste des identifiants vérifiés par la machine (statut et valeur) et le lien du nouveau
   cahier pour ce qui reste.
4. Les anomalies, avec leur cause probable, leur criticité et un plan de correction proposé.
   Aucune modification du code sans l'accord d'Anaël.

---

## Annexe : liste consolidée des points « À vérifier sur PC », story par story

Recopiée des specs des stories (ordre de la nuit). Chaque point donne le geste, l'attendu, le
critère et le moyen proposé. Pour les stories 22 à 27 et 31 à 34, le cahier
`cahier-recette-nuit-2026-09-28.html` les détaille déjà sous les identifiants N22-1 à N34-6.

### Story 22 — Retours de recette : briques, volets et tiroirs

- **Geste** : Edge, lancer WaveStack (`uv run wavestack`), regarder le panneau des briques ; éteindre RAG avec « Reranking » coché ; déplier MCP brique éteinte ; survoler « Reranking » et « Lazy loading ». — **Attendu** : Raisonnement en tête ; interrupteurs gris, raison en infobulle. — **Critère** : infobulle visible en moins de 2 s de survol, sous Edge et Chrome. — **Moyen** : Claude in Chrome ou à la main.
- **Geste** : lancer « Métier SOC » dans le sélecteur de scénario, texte à 125 % puis 150 % (« Aa »), cliquer « Afficher plus » puis « Réduire ». — **Attendu** : 3 lignes, bouton présent, la réponse d'un tour reste lisible. — **Critère** : au moins 2 bulles visibles au-dessus du champ sur l'écran du poste, sans défilement de la page. — **Moyen** : à la main (œil humain).
- **Geste** : scénario « Mémoire globale », « Modifier la mémoire », ajouter des entrées jusqu'à 8 par « Écrire en mémoire ». — **Attendu** : croix en haut à droite, pied « Tout effacer » (rouge) / « Fermer » visible sans défiler. — **Critère** : les deux boutons visibles à 100 % et 150 % de taille de texte ; distinction jugée évidente par Anaël. — **Moyen** : à la main.
- **Geste** : « Modifier le prompt », ne rien changer, puis modifier et « Enregistrer ». — **Attendu** : bouton gris puis confirmation « Prompt système enregistré. ». — **Critère** : confirmation lue par le lecteur d'écran de Windows (Narrateur) — **Moyen** : à la main.
- **Geste** : avec Qwen3.5-4B (tool parser), scénario « Sous-agent », « Afficher les actions forcées », « Déléguer au sous-agent », « Annuler », puis armer et envoyer. — **Attendu** : le formulaire se ferme ; après le tour, onglets « Agent principal » / « Sous-agent sub1 ». — **Critère** : fermeture immédiate (< 0,5 s) ; onglet principal sélectionné par défaut. — **Moyen** : Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`) ou Claude in Chrome.
- **Geste** : envoyer trois messages, « Réinitialiser », renvoyer un message ; puis « Vider la conversation » et renvoyer. — **Attendu** : Orchestration « Tour 1 » à chaque fois, infobulle t4 puis t5 ; journal des événements en t4, t5. — **Critère** : numéro affiché = 1, `turn_id` unique. — **Moyen** : script `AppSession` pour les `turn_id`, à la main pour l'affichage.

### Story 33 — Contrastes et code couleur par discipline

- **Barre haute projetée**
  - **Geste** : dans Chrome puis Edge, lancer `uv run wavestack`, choisir « Outils réseau » dans le sélecteur de scénario, envoyer « Résume l'article Wikipédia sur le Mont-Saint-Michel. », puis projeter ou se placer à 3 m de l'écran.
  - **Attendu** : barre haute foncée, légende de la jauge lisible, total en tokens et en pourcentage.
  - **Critère** : Anaël lit la légende et le total à 3 m, à 100 % puis à 150 % de taille de texte (« Aa »), sans texte coupé.
  - **Moyen** : à la main.
- **Code couleur partout**
  - **Geste** : même tour, regarder les cinq volets.
  - **Attendu** : même couleur pour une discipline dans la carte, le segment, la tuile et le nœud ; jaune seulement pour ce qui sort du poste.
  - **Critère** : Anaël associe chaque couleur à sa discipline sans lire la légende, pour 4 éléments tirés au hasard.
  - **Moyen** : à la main (œil humain).
- **Raisonnement imposé**
  - **Geste** : avec Groq gpt-oss-120b (clé déclarée), choisir le modèle dans le sélecteur, cliquer « Charger », confirmer, puis regarder la carte Raisonnement.
  - **Attendu** : interrupteur verrouillé avec 🔒, « Imposé par ce modèle ».
  - **Critère** : l'interrupteur ne bouge pas au clic.
  - **Moyen** : Claude in Chrome ou à la main.
- **Lignes d'état avec Qwen3.5-4B (GGUF, local)**
  - **Geste** : scénario « Mémoire globale », envoyer deux prompts suggérés, puis éteindre et rallumer « Prompt système ».
  - **Attendu** : tokens exacts (sans « ≈ ») sur les cartes ; « Éteinte » puis de nouveau des tokens.
  - **Critère** : pour chaque carte, les tokens affichés égalent ceux des segments de sa brique dans Contexte LLM.
  - **Moyen** : script AppSession (lecture de `by_brick` dans `context_rendered`) et Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`) pour les cartes.
- **Contrastes réels**
  - **Geste** : dans Edge, ouvrir DevTools, aller dans Lighthouse, puis Accessibility, puis Analyze, sur l'atelier après un tour du scénario « Outils réseau ».
  - **Attendu** : aucun défaut « Contrast ».
  - **Critère** : 0 élément signalé pour le contraste.
  - **Moyen** : à la main (Lighthouse), ou Claude in Chrome.
- **Mode contrasté de Windows**
  - **Geste** : Paramètres, puis Accessibilité, puis Thèmes de contraste, choisir « Désert », puis recharger WaveStack.
  - **Attendu** : barre haute, bulles et tuiles restent lisibles ; les focus sont visibles.
  - **Critère** : tous les textes restent lisibles, et le focus clavier reste visible sur les interrupteurs et la barre haute.
  - **Moyen** : à la main.

### Story 23 — Données sortantes visibles, en-têtes compris

- **Geste** : sur le PC relié à Internet, dans Chrome puis Edge, lancer `uv run wavestack` (PowerShell), choisir le scénario « Outils réseau » et envoyer « Résume l'article Wikipédia sur le Mont-Saint-Michel. », puis cliquer le nœud 🌐 « Wikipédia » du schéma. — **Attendu** : l'étape se déplie sur « 🌐 RÉSEAU · Données sortantes » avec les en-têtes, et l'outil réussit (pas de 403). — **Critère** : `User-Agent: WaveStack/0.1 (demonstrateur pedagogique; <contact de [net] contact>)` est lisible en entier sans défilement horizontal à 1366 × 768, et le résultat est non vide. — **Moyen** : Claude in Chrome, à défaut à la main.
- **Geste** : avec Groq choisi au diagnostic (vraie clé), envoyer « Quelle heure est-il ? », puis dans PowerShell `Select-String -Path <dossier de données>\*.jsonl,<dossier de données>\*.log -Pattern '<8 premiers caractères de la clé>'`, ou le script AppSession qui lit `get_journal().all_events()`. — **Attendu** : `outbound_request{origin: model}` porte `Authorization: [masqué]`. — **Critère** : zéro occurrence de la clé ou de ses fragments. — **Moyen** : script AppSession et `Select-String`.
- **Geste** : derrière le proxy d'entreprise, activer data.gouv.fr dans la brique MCP, déplier sa connexion dans « Préparation du harnais », puis faire un appel MCP. — **Attendu** : chaque requête montre ses en-têtes, `Mcp-Session-Id` et tout `Proxy-Authorization` à « [masqué] ». — **Critère** : aucun identifiant du proxy ni aucun identifiant de session en clair dans le journal. — **Moyen** : Claude in Chrome, puis le JSON du journal.
- **Geste** : donner à un participant novice la consigne « Trouve ce que WaveStack envoie à Wikipédia » (retest M2), en partant du panneau des briques. — **Attendu** : il lit la carte Outils, puis clique le nœud ou l'étape. — **Critère** : il trouve le bloc en moins de 30 s, sans aide. — **Moyen** : à la main seulement (œil humain).

### Story 34 — Vue liée au survol et lecture guidée des volets

- **Vue liée pendant la génération**
  - **Geste** : dans Edge puis Chrome, lancer `uv run wavestack` (PowerShell) avec Qwen3.5-4B (GGUF), choisir le scénario « Outils natifs », envoyer « Combien font 12*37 ? », et pendant la génération survoler la carte Outils, puis le nœud Calculatrice.
  - **Attendu** : éclairage immédiat, sans clignotement, pendant que le texte arrive.
  - **Critère** : l'éclairage suit le pointeur en moins de 100 ms, et le CPU ne dépasse pas celui d'un tour sans survol de plus de 5 points (Gestionnaire des tâches).
  - **Moyen** : Claude in Chrome, et à la main pour le CPU.
- **Bilan réel**
  - **Geste** : avec Groq gpt-oss-120b (clé déclarée) et Internet, scénario « Outils réseau », envoyer « Résume l'article Wikipédia sur le Mont-Saint-Michel. », puis lire la phrase sous le schéma.
  - **Attendu** : « … vers le modèle chez Groq (contexte complet, n appels) et vers Résumé Wikipédia (le titre de l'article, 1 requête). »
  - **Critère** : K égale le nombre d'`outbound_request` du tour dans le journal, sans « en échec ».
  - **Moyen** : script AppSession (`get_journal().all_events()`) et Claude in Chrome.
- **Bilan avec Ollama**
  - **Geste** : choisir un modèle Ollama au diagnostic, envoyer un message sans brique réseau.
  - **Attendu** : « aucune donnée n'a quitté le poste : le modèle est servi sur ce poste (Ollama) ».
  - **Critère** : la phrase exacte, et zéro `outbound_request` dans le tour.
  - **Moyen** : Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`) ou à la main.
- **Mode projection en salle**
  - **Geste** : sur le vidéoprojecteur puis en partage Teams, cliquer « Mode projection », parcourir les quatre volets numérotés à 1280 × 720.
  - **Attendu** : les textes sont agrandis, la barre haute tient sur une ligne, rien ne se chevauche.
  - **Critère** : Anaël lit les sous-titres et la frise à 3 m ; aucun texte coupé dans la barre haute.
  - **Moyen** : à la main (œil humain).
- **Mouvement réduit Windows**
  - **Geste** : Paramètres, Accessibilité, Effets visuels, désactiver « Effets d'animation », recharger WaveStack, survoler une carte.
  - **Attendu** : l'estompage est instantané, sans fondu.
  - **Critère** : aucune transition visible, et l'éclairage reste identique.
  - **Moyen** : à la main.
- **Clavier et Narrateur**
  - **Geste** : Narrateur actif, Tab depuis la barre haute jusqu'à un segment de Contexte LLM, Entrée, masquer Contexte LLM, puis Échap.
  - **Attendu** : les éléments liés sont éclairés au focus ; la puce annonce « lié » ; Échap efface.
  - **Critère** : Narrateur lit « lié » sur la puce, et le focus reste visible à chaque étape.
  - **Moyen** : à la main.

### Story 32 — Contexte LLM lisible : texte groupé, sources en marge, lu et produit distincts

- **Lecture d'un tour à outil**
  - **Geste** : sur Windows 11, dans Chrome puis Edge, lancer `uv run wavestack` (PowerShell), charger Qwen3.5-4B (GGUF) et choisir le scénario « Outils natifs ». Envoyer « Quelle heure est-il ? », puis regarder Contexte LLM.
  - **Attendu** : Appel 1 et Appel 2 ; au second, le déjà-lu est replié et le résultat d'outil marqué « Nouveau » ; réflexion, appel d'outil et réponse sur leur fond.
  - **Critère** : Anaël dit en moins de 10 s ce qui est nouveau à l'appel 2, et juge la vue plus claire que l'ancienne.
  - **Moyen** : à la main (œil humain).
- **Exactitude avec un vrai gabarit**
  - **Geste** : même tour, avec Qwen3.5-2B puis 4B, et avec Ollama. Script AppSession : lire les `context_rendered`, comparer `"".join(text)` au prompt envoyé et Σ `sections.tokens` à `prompt_tokens`. Puis, en Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`), comparer « Texte exact » à la jointure.
  - **Attendu** : égalités.
  - **Critère** : égalité octet pour octet ; écart de tokens nul.
  - **Moyen** : script AppSession et Playwright.
- **JSON des outils avec le vrai gabarit**
  - **Geste** : même tour, lecture groupée de l'appel 1.
  - **Attendu** : chaque schéma d'outil est en arbre indenté et repliable ; la marge nomme gabarit et descriptions d'outils.
  - **Critère** : autant d'arbres que d'outils décrits ; « Texte exact » d'un arbre est égal à la ligne JSON du prompt.
  - **Moyen** : Claude in Chrome ou à la main.
- **Modèle cloud réel**
  - **Geste** : avec Groq (vraie clé), faire le même tour, puis ouvrir « Corps JSON » et « Texte exact ».
  - **Attendu** : arbre lisible (messages, tools, arguments décodés) ; texte exact égal au corps envoyé.
  - **Critère** : `json.loads` du texte exact est égal au `body` de `context_rendered` ; aucune clé dans la page.
  - **Moyen** : Claude in Chrome.
- **Fluidité sur CPU**
  - **Geste** : scénario RAG et outils avec Qwen3.5-4B, contexte d'environ 3 500 tokens, trois appels, en streaming, dans Chrome et Edge. Onglet Performance des DevTools pendant la génération.
  - **Attendu** : le volet suit sans à-coups ; le défilement et les blocs dépliés restent en place.
  - **Critère** : aucune tâche longue de plus de 200 ms due au rendu de Contexte LLM ; déplié et défilement conservés.
  - **Moyen** : à la main (DevTools).
- **Coupe du raisonnement et taille de texte**
  - **Geste** : avec un budget de raisonnement bas (lot C), envoyer un prompt qui fait réfléchir longtemps, puis cliquer « Mode projection » (story 34), à 1366 × 768.
  - **Attendu** : réflexion, note « Raisonnement coupé par le harnais », puis réponse, dans un seul appel ; étiquettes de marge lisibles, sans défilement horizontal.
  - **Critère** : note placée entre les deux blocs ; aucun texte coupé.
  - **Moyen** : Claude in Chrome ou à la main.

### Story 24 — Modèles : mémoire comptée juste, budget dynamique, sonde interruptible

- **Geste** : Edge, Outlook et Teams fermés ; lancer WaveStack, lire la ligne « Mémoire » du diagnostic ; dans PowerShell, `uv run python -c "import psutil; v=psutil.virtual_memory(); print(v.total//2**20, v.available//2**20)"`. — **Attendu** : RAM totale, disponible, 60 %, plafond et budget retenu. — **Critère** : budget = min(4 096, 0,6 × disponible) à 5 % près de la mesure PowerShell. — **Moyen** : script AppSession ou Claude in Chrome.
- **Geste** : rouvrir Edge et Teams, relancer WaveStack. — **Attendu** : budget plus petit si la RAM disponible chute sous 6,8 Go, contrôle en `warn` avec le conseil. — **Critère** : chiffres cohérents avec PowerShell. — **Moyen** : à la main.
- **Geste** : mettre `budget_mode = "fixed"` et `budget_mb = 6144` dans `[memory]` de `wavestack.toml`, relancer. — **Attendu** : « valeur fixe », 6 144 Mo. — **Critère** : texte exact du budget. — **Moyen** : Playwright ou à la main.
- **Geste** : 2B actif, choisir le 4B dans « Changer de modèle ». — **Attendu** : refus chiffré. — **Critère** : « WaveStack occupe N Mo sans le modèle actif » avec 80 ≤ N ≤ 400, jamais 0, proche (±100 Mo) de la RSS mesurée par script après libération. — **Moyen** : script AppSession.
- **Geste** : copier le 2B sous un autre nom dans `models\` (jamais sondé), le choisir à chaud, cliquer « Arrêter » dans les 5 s. — **Attendu** : « Chargement arrêté : … est de nouveau actif. ». — **Critère** : `Get-Process python` ne montre plus l'enfant de sonde 1 s après le clic ; aucune entrée pour ce fichier dans `failed_probes` ; fin d'arrêt ≤ 3 s plus le rechargement du 2B. — **Moyen** : Claude in Chrome et PowerShell.
- **Geste** : Ollama lancé, `llama3.2:3b` non chargé (`ollama ps` vide), le choisir. — **Attendu** : accepté ; ligne du diagnostic ≈ 2,3 Go. — **Critère** : pas de refus ; après un message, `ollama ps` (SIZE) à ±30 % de l'estimation ; noter `OLLAMA_NUM_PARALLEL` et le type de KV d'Ollama. — **Moyen** : script AppSession et PowerShell.
- **Geste** : reprendre le fichier incompatible de C6 (même fichier que la recette), le choisir. — **Attendu** : raison accentuée juste dans le diagnostic et le journal. — **Critère** : aucun « Ã » ni « Â » dans la page ni dans les nouvelles entrées de `settings.json`. — **Moyen** : Claude in Chrome.
- **Geste** : avant la mise à jour, garder le `settings.json` du PC (entrée C6 abîmée) ; après, ouvrir le diagnostic. — **Attendu** : raison réparée sans nouvelle sonde. — **Critère** : « abîmé » et « modèle » corrects ; `settings.json` inchangé tant qu'aucune sonde ne réécrit l'entrée. — **Moyen** : à la main.

### Story 25 — Sélecteur de modèles regroupé et tableau des capacités

- **Geste** : Qwen3.5-2B et 4B en GGUF dans `models\`, Ollama lancé avec au moins `llama3.2:3b` et un modèle Qwen ; lancer WaveStack, ouvrir « Changer de modèle… » dans Chrome puis dans Edge. — **Attendu** : groupes « Sur ce poste · Qwen (Alibaba) » puis « Sur ce poste · Llama (Meta) », 2B avant 4B, préfixes « Local · fichier » et « Local · Ollama », légende lisible en tête de liste. — **Critère** : ordre et libellés exacts, aucun modèle dans « Autres éditeurs » parmi Qwen, Llama et Gemma ; légende entière visible sans troncature dans les deux navigateurs. — **Moyen** : Claude in Chrome ; Edge à la main.
- **Geste** : cliquer « Tableau des modèles et de leurs capacités… » puis « Ouvrir le tableau ». — **Attendu** :
  - Qwen3.5-2B et 4B : outils « oui », raisonnement « activable » ;
  - `llama3.2:3b` : outils « non », avec la raison, et raisonnement « jamais » ;
  - Groq gpt-oss-120b : « toujours », 120B ;
  - Mistral : « activable ».
  — **Critère** : chaque valeur correspond à l'état de la carte Raisonnement et de la carte Outils après avoir chargé le modèle (4 modèles au moins). — **Moyen** : script AppSession pour la comparaison, Claude in Chrome pour la page.
- **Geste** : lire la colonne « Fenêtre » du 2B, puis le charger et lire la jauge. — **Attendu** : même fenêtre. — **Critère** : égalité exacte. — **Moyen** : Playwright.
- **Geste** : en PowerShell, mesurer le temps de `/api/diagnostic` avec un cache Hugging Face ou LM Studio de 10 GGUF ou plus : `Measure-Command { Invoke-RestMethod http://127.0.0.1:<port>/api/diagnostic }`, deux fois. — **Attendu** : lecture des en-têtes rapide, mémorisée. — **Critère** : moins de 2 s au premier appel, moins de 200 ms au second. — **Moyen** : script ou à la main.
- **Geste** : Ollama avec un modèle dont le blob n'a pas de gabarit GGUF, ou un modèle de famille inconnue. — **Attendu** : ligne « inconnu » avec une raison compréhensible. — **Critère** : aucune ligne vide, aucune exception dans le terminal. — **Moyen** : Claude in Chrome.
- **Geste** : llama-server lancé avec `-c 4096` sur le 2B, puis le tableau. — **Attendu** : éditeur Qwen (par l'en-tête ou le gabarit), taille 2B si `model_path` est lisible, fenêtre 4 096. — **Critère** : valeurs exactes. — **Moyen** : Claude in Chrome.
- **Geste** : zoom à 125 % dans Chrome, page `/models`, depuis le fond de la salle. — **Attendu** : table lisible, onglets visibles, 🌐 RÉSEAU sur les lignes cloud. — **Critère** : aucune colonne coupée à 1600 × 1000 ; contraste jugé suffisant à l'œil. — **Moyen** : à la main.

### Story 26 — Fenêtre de contexte réglable (4 096, 8 192, 16 384)

- **Geste** : Edge, Outlook et Teams fermés. Qwen3.5-2B actif, envoyer « Bonjour », ouvrir « Fenêtre ▾ » et lire les trois choix. — **Attendu** : cache, temps de lecture et verdict pour 4 096, 8 192 et 16 384. — **Critère** : le cache du 2B égale `kv_bytes_per_token × fenêtre`, à comparer à l'entrée `probed_models` de `settings.json`. Le débit affiché est à ±20 % de `evaluated_tokens / prompt_ms` du dernier `model_call_ended`, lu dans le journal. — **Moyen** : script AppSession et Claude in Chrome.
- **Geste** : choisir 8 192, cliquer « Appliquer ». — **Attendu** : rechargement, conversation gardée, jauge à 8 192. — **Critère** : rechargement en 30 s au plus ; RSS de WaveStack après rechargement à ±30 % du coût annoncé ; `settings.json` contient `"context": {"window": 8192}`. — **Moyen** : script AppSession et PowerShell (`Get-Process`).
- **Geste** : 2B à 16 384, remplir le contexte (MCP complet, trois serveurs), puis envoyer. — **Attendu** : pas de débordement là où 4 096 débordait (M4). — **Critère** : premier token mesuré face au temps annoncé ; noter s'il dépasse 30 s (NFR-1). — **Moyen** : script AppSession, puis Claude in Chrome pour la jauge.
- **Geste** : 4B actif, choisir 16 384. — **Attendu** : refus chiffré si le budget ne suffit pas. — **Critère** : texte « Fenêtre de 16 384 tokens refusée » avec budget et calcul ; le 4B reste actif à la fenêtre précédente. — **Moyen** : Claude in Chrome.
- **Geste** : Ollama avec `llama3.2:3b` choisi, passer à 8 192 puis envoyer un message ; relever `ollama ps`. — **Attendu** : Ollama recharge le modèle avec `num_ctx` 8192. — **Critère** : la taille de `ollama ps` augmente d'environ le KV annoncé (±30 %). — **Moyen** : PowerShell et script AppSession.
- **Geste** : llama-server lancé avec `-c 4096`, puis choisir 8 192. — **Attendu** : « bornée à 4 096 par llama-server (-c) ». — **Critère** : la jauge reste à 4 096, `window_source=server`. — **Moyen** : Claude in Chrome.
- **Geste** : relancer WaveStack après avoir choisi 8 192. — **Attendu** : 8 192 repris ; le diagnostic conseille `-c 8192` pour llama-server. — **Critère** : bouton « Fenêtre 8 192 » au premier affichage. — **Moyen** : Playwright ou à la main.
- **Geste** : lire le panneau vidéoprojeté, sous Chrome et Edge, à 125 % et à 150 %. — **Attendu** : barre haute sur une ligne, panneau lisible et non coupé. — **Critère** : aucune commande de la barre haute sur deux lignes à 1280×650. — **Moyen** : à la main seulement.

### Story 27 — Lot H : scénarios et consignes du palier 2

- **Geste** : lancer « Sous-agent », envoyer les quatre prompts dans l'ordre (script AppSession, 2B, Edge fermé). — **Attendu** : délégation au premier prompt, puis quiz répondus sans redélégation hors contexte. — **Critère** : `prompt_ms` du premier appel de chaque quiz < 15 s, aucun `prefix_not_reused` de cause `history`. — **Moyen** : script AppSession.
- **Geste** : Edge, sélecteur de scénario → « Où vont mes données ? » ; regarder la carte MCP et le schéma sans rien cocher ; envoyer le prompt. — **Attendu** : MCP actif, serveur local et data.gouv.fr cochés, lazy loading ; `load_tool_doc` puis `datagouv__search_datasets`. — **Critère** : un flux data.gouv.fr franchit la frontière, `tool_ended` `ok`, résultat ≤ 1 200 tokens. — **Moyen** : Claude in Chrome, ou script AppSession pour les événements.
- **Geste** : lancer « Skills », envoyer le prompt suggéré. — **Attendu** : `load_skill("meeting_minutes")`, jamais `load_tool_doc` pour un skill ; sinon, « Déclencher le skill » sur « Compte rendu de réunion » puis « Rejouer » charge le skill. — **Critère** : `tool_started.tool == "load_skill"` dans le premier tour ; durée du tour relevée avec Edge, Outlook et Teams fermés (H6). — **Moyen** : script AppSession, secours à la main.
- **Geste** : lancer « MCP en documentation complète », puis « Lazy loading », et envoyer le premier prompt dans chacun. — **Attendu** : appel de `local__define_term` (en lazy, après `load_tool_doc`) ; définition du glossaire, pas de sens inventé. — **Critère** : la réponse contient « Model Context Protocol ». — **Moyen** : script AppSession.
- **Geste** : lancer « Métier IAM », envoyer les deux prompts. — **Attendu** : `mslearn__microsoft_docs_search` appelé, liens Microsoft Learn cités. — **Critère** : au moins un appel par prompt, `tool_ended.truncated` ≤ 1 200 tokens, aucun `context_overflow`. — **Moyen** : script AppSession.
- **Geste** : lancer « Métier Souveraineté », envoyer le prompt 1, ouvrir les données sortantes de l'appel dans Orchestration. — **Attendu** : recherche réelle sur data.gouv.fr après chargement de la documentation. — **Critère** : `datagouv__search_datasets` `ok` au prompt 1, requête visible (URL, corps, en-têtes). — **Moyen** : script AppSession, puis Claude in Chrome pour l'affichage.
- **Geste** : lancer « Métier SOC », envoyer les deux prompts. — **Attendu** : prompt 1 : lecture d'`alertes_siem.log` (ou nom corrigé après le refus du harnais) ; prompt 2 : blocage H1, puis la réponse signale le refus et renvoie vers un humain. — **Critère** : `hook_decided` `h1` `block` ; la réponse contient « analyste » ou « habilité » (sinon, noter KO : la consigne porte seule la leçon). — **Moyen** : script AppSession.
- **Geste** : lancer « Compression du contexte », éteindre la brique Compression, envoyer le prompt 1 ; si rien n'est lu, forcer read_file avec « Journal de sauvegarde (compression) » et rejouer. — **Attendu** : `read_file("journal_serveur.log")` appelé par le modèle, sans débordement. — **Critère** : `tool_started.trigger == "model"` au premier essai ; jauge sous 3 584. — **Moyen** : script AppSession, secours à la main.
- **Geste** : `$env:WAVESTACK_TEST_GGUF = "<chemin du 2B>"` puis `uv run pytest -s -rA tests/test_program.py -k fits`. — **Attendu** : réussi, avec la jauge locale exacte. — **Critère** : `mcp_full` tient avec son nouveau prompt ; chaque scénario garde une marge positive. — **Moyen** : PowerShell sur le PC cible.
- **Geste** : faire lire les consignes de « Où vont mes données ? », « Skills » et « Métier SOC » (dépliées) à un formateur novice. — **Attendu** : il sait quoi cliquer et quoi dire sans aide. — **Critère** : chaque consigne est suivie jusqu'au bout en moins de 2 min. — **Moyen** : à la main seulement.

### Story 31 — Mode sombre

- **Suivi du mode Windows**
  - **Geste** : Paramètres, Personnalisation, Couleurs, « Choisir votre mode » = Sombre, puis lancer `uv run wavestack` dans PowerShell et ouvrir l'atelier dans Chrome puis dans Edge, sélecteur sur « Système ». Repasser Windows en Clair sans recharger.
  - **Attendu** : l'atelier passe en sombre, puis revient en clair de lui-même.
  - **Critère** : bascule en moins de 2 s, sans rechargement, dans les deux navigateurs.
  - **Moyen** : à la main.
- **Pas de flash sur un poste chargé**
  - **Geste** : « Sombre » choisi, lancer un changement de modèle vers Qwen3.5-4B (GGUF), puis appuyer sur F5 pendant le chargement, dans Edge.
  - **Attendu** : aucun éclair blanc au rechargement.
  - **Critère** : aucune image claire visible à l'œil sur 5 rechargements. Au besoin, Performance de DevTools, où la première image est déjà sombre.
  - **Moyen** : à la main (DevTools).
- **Lisibilité en projection et en visio**
  - **Geste** : scénario « Outils réseau », envoyer « Résume l'article Wikipédia sur le Mont-Saint-Michel. » en thème sombre, projeter, puis partager l'écran dans Teams à 125 %.
  - **Attendu** : barre haute, légendes, segments, jaune « RÉSEAU » et schéma lisibles.
  - **Critère** : Anaël lit la jauge, les lignes d'état des briques et les nœuds du schéma à 3 m et dans la visio. Il tranche entre clair et sombre pour la salle.
  - **Moyen** : à la main (œil humain).
- **Contrastes réels**
  - **Geste** : dans Edge, thème « Sombre », DevTools, Lighthouse, Accessibility, Analyze, sur l'atelier après le tour ci-dessus, puis sur `/diagnostic` et `/models`.
  - **Attendu** : aucun défaut « Contrast ».
  - **Critère** : 0 élément signalé sur les trois pages.
  - **Moyen** : Lighthouse à la main, ou Claude in Chrome.
- **Mémorisation sans droits d'administrateur**
  - **Geste** : choisir « Sombre », fermer Chrome, relancer `uv run wavestack`, puis refaire la même chose dans une fenêtre InPrivate d'Edge.
  - **Attendu** : sombre repris dans Chrome ; dans InPrivate, choix possible sans erreur, puis oublié à la fermeture.
  - **Critère** : thème repris au lancement suivant, aucune erreur dans la console.
  - **Moyen** : Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`) ou à la main.

### Story 29 — Écran « LLM nu » : l'architecture d'un modèle, sans l'agentique

- **Vitesse token par token**
  - **Geste** : PowerShell, `uv run wavestack`, Qwen3.5-2B GGUF actif. Dans Chrome, cliquer « LLM nu », saisir « Explique en deux phrases ce qu'est un token. », puis « Générer ».
  - **Attendu** : les puces arrivent une à une ; premier token, puis débit.
  - **Critère** : premier token en moins de 10 s (NFR-1, LLM nu), débit affiché ≥ 8 tokens/s, pas de saccade de plus de 1 s entre deux puces.
  - **Moyen** : Claude in Chrome ; mesure croisée par script AppSession.
- **Réglages réellement appliqués**
  - **Geste** : même prompt, T 0 deux fois de suite, puis T 1,5 deux fois.
  - **Attendu** : à T 0, deux réponses identiques ; à T 1,5, des réponses différentes.
  - **Critère** : identité exacte à T 0 ; au moins un token différent à T 1,5.
  - **Moyen** : script AppSession ou Playwright.
- **Probabilités sur le vrai moteur**
  - **Geste** : Qwen3.5-2B, « Montrer les tokens candidats » coché, prompt « La capitale de la France est ». Survoler la première puce.
  - **Attendu** : cinq candidats, « Paris » en tête.
  - **Critère** : somme des `p` affichés ≤ 100 %. Le token tiré est marqué, et le débit baisse de moins de 20 % par rapport à la case décochée.
  - **Moyen** : Claude in Chrome, puis `pytest -m model` avec `WAVESTACK_TEST_GGUF`.
- **Dimensions réelles**
  - **Geste** : découper un texte avec Qwen3.5-2B, puis 4B.
  - **Attendu** : dimension d'embedding, couches, têtes et vocabulaire conformes à la fiche du modèle.
  - **Critère** : égalité avec l'en-tête GGUF (`gguf_meta`).
  - **Moyen** : script.
- **Chargement en RAM**
  - **Geste** : Edge, Outlook et Teams fermés. Dans l'atelier, passer du 2B au 4B, puis ouvrir `/llm`.
  - **Attendu** : les étapes et leur durée s'affichent, avec la mémoire et « RAM du CPU, pas de GPU ».
  - **Critère** : durée totale égale à celle de `model_load_ended` à 100 ms près. RSS après chargement à ±15 % du Gestionnaire des tâches (« Mémoire », processus python), mesuré après un premier appel.
  - **Moyen** : Claude in Chrome et Gestionnaire des tâches à la main.
- **Raisonnement et coupe**
  - **Geste** : 4B, raisonnement activé, prompt « Combien font 17 × 23 ? Détaille. ».
  - **Attendu** : le couloir « Réflexion » se remplit, puis « Réponse ». Si le budget est atteint, la marque de coupe apparaît avec son message.
  - **Critère** : compteurs Réflexion + Réponse égaux aux tokens de sortie. Coupe au budget configuré ±1 token.
  - **Moyen** : Claude in Chrome.
- **Ollama et llama-server**
  - **Geste** : dans l'atelier, choisir un modèle Qwen servi par Ollama, puis llama-server lancé avec `-c 4096`. Sur `/llm`, générer avec T 0,2 et top-k 5.
  - **Attendu** : la génération marche ; les candidats sont grisés avec leur raison.
  - **Critère** : le journal d'Ollama ou de llama-server montre les options reçues, et `model_call_started.sampling` du contexte `llm` a les mêmes valeurs.
  - **Moyen** : à la main (journal du serveur) et Playwright.
- **Cloud**
  - **Geste** : Groq gpt-oss-120b, clé saisie, puis `/llm` avec T 0,2.
  - **Attendu** : réponse en fragments, top-k et min-p grisés « non réglables chez Groq », raisonnement « toujours ».
  - **Critère** : aucun 400 du fournisseur, et le corps tracé (`outbound_request`) contient `temperature: 0.2`.
  - **Moyen** : Claude in Chrome.
- **Lisibilité en salle**
  - **Geste** : projeter `/llm` en thème clair puis sombre, zoom 125 %, dans Chrome puis Edge.
  - **Attendu** : puces, identifiants, schéma et encart des candidats lisibles.
  - **Critère** : Anaël lit un identifiant de token à 3 m. Aucune section coupée à 1600 × 1000.
  - **Moyen** : à la main (œil humain).
- **Atelier intact**
  - **Geste** : dans l'atelier, envoyer deux messages, faire une génération sur `/llm`, puis envoyer un troisième message dans l'atelier.
  - **Attendu** : le troisième tour ne reprend rien de l'écran. Avec le moteur en processus, aucun `prefix_not_reused` à cause `llm`.
  - **Critère** : pas de relecture complète du contexte, temps du troisième tour comparable au deuxième (±20 %).
  - **Moyen** : script AppSession.

### Story 30 — Atelier RAG : l'architecture RAG à manipuler

- **Installation de l'extra sans droits d'administrateur**
  - **Geste** : dans PowerShell, depuis le dossier de WaveStack, lancer `uv sync --extra compression --extra rag-alt`, puis `uv run wavestack`.
  - **Attendu** : installation sans invite UAC ni pare-feu, et FAISS et LanceDB disponibles dans `/rag`.
  - **Critère** : code de sortie 0 ; durée et taille de `.venv` notées ; aucune boîte de dialogue.
  - **Moyen** : à la main, ou script PowerShell.
- **DLL non signées (AppLocker ou WDAC)**
  - **Geste** : `/rag`, base vectorielle FAISS puis LanceDB, « Lancer la chaîne ».
  - **Attendu** : le run passe ; si un import est bloqué, l'étape en `error` dit pourquoi et le reste fonctionne.
  - **Critère** : aucune `pageerror` ; WaveStack reste utilisable.
  - **Moyen** : Claude in Chrome ou Playwright.
- **Chaîne livrée avec les vrais modèles**
  - **Geste** : `/rag`, question « Combien de jours de télétravail par semaine ? », « Lancer », avec granite-embedding et bge-reranker (Qwen3.5-2B actif).
  - **Attendu** : les sept étapes sont renseignées, et le reranking réordonne.
  - **Critère** : run complet en moins de 15 s ; RSS de WaveStack sous le budget (4 Go) ; mémoire affichée par étape relevée.
  - **Moyen** : script AppSession, puis Playwright pour la capture.
- **Coût mémoire réel des imports**
  - **Geste** : RSS avant et après la première exécution FAISS, puis LanceDB (Gestionnaire des tâches ou script `psutil`).
  - **Attendu** : les ajouts réels sont relevés.
  - **Critère** : chaque ajout mesuré est au plus égal à `[rag_lab] faiss_cost_mb` (60) et `lancedb_cost_mb` (180). Sinon, ajuster les valeurs.
  - **Moyen** : script AppSession.
- **Taille des extraits et reconstruction**
  - **Geste** : chaîne B avec des extraits de 300 caractères, deux runs de suite.
  - **Attendu** : premier run « calculés (77 passages) », second « relus du cache ».
  - **Critère** : durée de l'embedding du premier run notée (cible : moins de 10 s) ; second run au moins 5 fois plus court sur cette étape.
  - **Moyen** : Playwright.
- **Hors ligne**
  - **Geste** : mode avion, puis `/rag` avec la comparaison sqlite-vec / LanceDB.
  - **Attendu** : tout fonctionne.
  - **Critère** : aucune erreur réseau ; aucune invite du pare-feu.
  - **Moyen** : à la main.
- **Rien dans le dépôt**
  - **Geste** : après les runs, lancer `git status` et regarder `%LOCALAPPDATA%\WaveStack\rag_lab`.
  - **Attendu** : les index sont dans le dossier de données seulement.
  - **Critère** : `git status` propre.
  - **Moyen** : PowerShell.
- **Lisibilité en séance**
  - **Geste** : dans Chrome puis Edge, zoom à 125 %, comparaison A/B et chaîne hybride, dans les thèmes clair et sombre, projetées.
  - **Attendu** : chaîne et colonnes lisibles depuis le fond de la salle.
  - **Critère** : Anaël lit les rangs et les scores à 3 m ; aucune colonne coupée à 1 600 × 1 000.
  - **Moyen** : à la main (œil humain).
- **Arrêt pendant un calcul réel**
  - **Geste** : extraits de 300 caractères, cache supprimé, « Lancer » puis « Arrêter » pendant l'embedding.
  - **Attendu** : l'étape passe en « arrêtée », le retour en `idle` suit, et aucun fichier partiel ne reste.
  - **Critère** : arrêt en moins de 2 s ; aucun dossier `.tmp` restant sous `rag_lab`.
  - **Moyen** : Playwright.

### Story 28 — Guide de test et cahier de recette corrigés

- **Installation de llama-server**
  - **Geste** : ouvrir un nouveau terminal PowerShell, coller le bloc « Procédure llama-server » du guide (test `P3`) ligne par ligne, puis relever `$asset.name` et la sortie de `& $llama --version`.
  - **Attendu** : archive `llama-bNNNNN-bin-win-cpu-x64.zip` téléchargée, puis décompressée dans `%LOCALAPPDATA%\llama.cpp\bNNNNN` ; la version s'affiche.
  - **Critère** : aucune demande d'élévation ; code de sortie 0 pour `--version`.
  - **Moyen** : à la main, ou par le Claude Code du PC.
- **Proxy qui bloque**
  - **Geste** : si `Invoke-RestMethod` échoue, noter le code (403 ou 407), réessayer avec `-ProxyUseDefaultCredentials`, puis avec l'URL fixe.
  - **Attendu** : un des trois chemins aboutit, sinon le repli par copie.
  - **Critère** : le chemin qui a marché est noté dans le champ du test `P3`.
  - **Moyen** : à la main.
- **Exécutable autorisé**
  - **Geste** : lancer `& $llama --version`.
  - **Attendu** : pas de blocage AppLocker ou SmartScreen, pas de « VCRUNTIME140.dll introuvable ».
  - **Critère** : la version s'affiche. Sinon, le message exact est relevé et C9 et C10 passent à « non fait (poste) ».
  - **Moyen** : à la main.
- **Lancement avec -c 4096**
  - **Geste** : lancer la commande de C10, WaveStack arrêté et le 2B non chargé ailleurs, puis lancer WaveStack.
  - **Attendu** : « Local · llama-server » au diagnostic, sans avertissement de contexte.
  - **Critère** : RSS de `llama-server` (commande `PEAK_CMD`) bien sous 5 137 Mo.
  - **Moyen** : script AppSession ou à la main.
- **Clarté des gestes réécrits**
  - **Geste** : Anaël exécute D1, D2m, X1, X3, Z1, Z2, M3, M6, ainsi que D11 et « Réinitialiser » (M1), en suivant seulement le cahier.
  - **Attendu** : aucun « Que dois-je tester ici ? ».
  - **Critère** : chaque test reçoit un statut OK ou KO, pas « non fait » pour cause de consigne.
  - **Moyen** : à la main (œil humain).
- **Vider les clés (Z2)**
  - **Geste** : suivre Z2 dans un nouveau terminal, puis lancer `uv run wavestack` et ouvrir le diagnostic.
  - **Attendu** : aucune ligne « Clé fournie par la variable… » ni clé enregistrée ; le diagnostic demande de choisir un modèle servi.
  - **Critère** : les lignes Groq et Mistral du diagnostic indiquent qu'aucune clé n'est fournie (libellé exact relevé). Après « Défaire », les clés reviennent.
  - **Moyen** : à la main.
- **Mémoire pleine (D11)**
  - **Geste** : lancer le script D11, relancer WaveStack, allumer « Mémoire globale » à la main, puis lire la jauge.
  - **Attendu** : 20 entrées dans le tiroir ; la jauge compte environ 1 550 tokens de mémoire.
  - **Critère** : la jauge reste sous la fenêtre utilisable (sans débordement). `memory.json` est restauré ensuite.
  - **Moyen** : script AppSession pour la jauge, à la main pour l'affichage.
- **Cahier publié**
  - **Geste** : une fois l'artefact republié par Anaël, saisir un statut sous Edge, puis rouvrir la page sous Chrome.
  - **Attendu** : « Enregistré sur claude.ai » ; le statut est retrouvé.
  - **Critère** : même statut dans les deux navigateurs.
  - **Moyen** : à la main.
