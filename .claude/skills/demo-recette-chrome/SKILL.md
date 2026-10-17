---
name: demo-recette-chrome
description: Rejoue en direct la démo de recette fonctionnelle de WaveStack avec Claude in Chrome, dans une copie vierge du cahier de tests (docs/recette). Utiliser quand l'utilisateur demande la démo de recette Chrome, de rejouer la campagne de tests, ou tape /demo-recette-chrome. Argument facultatif « gif » pour enregistrer la démo.
allowed-tools: Bash(uv run *), Bash(curl *), Bash(date *), Bash(git rev-parse *), PowerShell(Get-NetTCPConnection *), mcp__claude-in-chrome__*
---

# Démo de recette WaveStack avec Claude in Chrome

Objectif : montrer en partage d'écran ce que Claude in Chrome ajoute aux TU, TI et E2E :
juger le sens d'une réponse, recouper l'écran avec une source extérieure, porter un avis
visuel, lire une langue. Le cahier `docs/recette/cahier-tests-chrome.html` est le modèle
vierge ; chaque démo travaille dans sa propre copie sous `docs/recette/runs/`.

L'audience regarde Chrome. Dans le chat, une ligne par étape, en français : ce que tu fais
et ce que tu constates. Pas de pavés entre les cas.

## Guider le regard du présentateur

La personne qui partage son écran ne sait pas où tu vas agir. Juste **avant** chaque appel
d'outil visible dans Chrome (ou chaque `browser_batch`), écris une ligne de repère, seule
sur sa ligne, au format :

`👀 Onglet <WaveStack | Cahier> › <zone> : <ce qui va bouger>`

- « WaveStack » désigne l'onglet de l'application (titre « WaveStack — Atelier … ») et
  « Cahier » l'onglet « Cahier de tests WaveStack ». À la préparation, une fois les deux
  onglets ouverts, le dire une fois en clair au présentateur.
- Exemples : `👀 Onglet WaveStack › barre du bas à gauche : je choisis le scénario « LLM nu ».`,
  `👀 Onglet WaveStack › volet ③ Orchestration (en haut à droite) : l'appel à get_datetime va apparaître.`,
  `👀 Onglet Cahier › cas CT-03 : je coche OK et je tape le constat.`
- **Changement d'onglet** : quand l'action suivante se passe dans l'autre onglet que la
  précédente, commencer par `👀 Basculez sur l'onglet <nom>` : les actions dans un onglet
  en arrière-plan ne se voient pas.
- Nommer les zones avec le vocabulaire de l'écran : barre de navigation (en haut), panneau
  des briques (à gauche), ① Vue humain, ② Contexte LLM, ③ Orchestration, ④ Schéma
  d'architecture (en bas), barre du bas, menu « Affichage » (en haut à droite), et dans le
  cahier le cas CT-0X et le compteur d'avancement (en haut).
- Ce qui ne se voit pas dans la page (`javascript_tool`, `read_network_requests`, console,
  `date`, PowerShell) : l'annoncer `👀 Terminal : <ce que je vérifie en coulisse>`, pour
  que la personne regarde le terminal et explique que c'est la partie « au-delà de l'E2E ».
- Une attente du modèle : `👀 Onglet WaveStack › ① Vue humain : réponse en cours (quelques secondes sur CPU).`
- Découper les `browser_batch` par zone regardée : un repère, puis un lot qui reste dans
  cette zone. Ne pas annoncer une zone et agir dans une autre.
- Pas de repère pour les captures d'écran seules ni pour les `find` : rien ne bouge.

## 1. Préparation (hors caméra si possible, une minute)

1. WaveStack : `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8420/`. Si ce n'est
   pas 200, lancer `uv run wavestack` en arrière-plan et attendre le 200.
2. Serveur du cahier : même test sur `http://127.0.0.1:8430/cahier-tests-chrome.html`.
   Sinon lancer en arrière-plan
   `uv run python -m http.server 8430 --bind 127.0.0.1 -d docs/recette`.
3. Copie vierge : `uv run python scripts/new_recette_run.py`. Le script affiche l'adresse
   de la copie (`http://127.0.0.1:8430/runs/cahier-<date-heure>.html`).
4. Charger les outils Chrome en un seul ToolSearch : `tabs_context_mcp`, `tabs_create_mcp`,
   `tabs_close_mcp`, `navigate`, `computer`, `find`, `read_page`, `get_page_text`,
   `form_input`, `javascript_tool`, `read_console_messages`, `read_network_requests`,
   `browser_batch`, et `gif_creator` si l'argument « gif » est donné.
5. `tabs_context_mcp`, puis deux nouveaux onglets : la copie du cahier, et WaveStack sur
   `http://127.0.0.1:8420/`. Ne jamais réutiliser un ID d'onglet d'une autre session.
6. Appeler tout de suite `read_console_messages` (pattern `.`, onlyErrors) et
   `read_network_requests` sur l'onglet WaveStack : le suivi ne commence qu'au premier
   appel. Recharger ensuite l'onglet WaveStack pour capter le chargement.

## 2. Déroulé

Pour chaque cas, dans l'ordre CT-01 à CT-06 :

1. Lire le cas dans l'onglet du cahier (`get_page_text` ou `find`) : c'est la page qui fait
   foi, pas ce fichier. Annoncer le cas en une ligne.
2. L'exécuter dans l'onglet WaveStack. Regrouper les actions prévisibles dans
   `browser_batch`. Cibler les éléments par `find` (refs) : la taille de la fenêtre change
   en partage d'écran, et les coordonnées ne valent que pour une capture fraîche.
3. Saisir le verdict dans le cahier : `find` « bouton CT-0X : OK » (ou KO, Bloqué), clic,
   clic sur le libellé « Constat CT-0X », puis `type` d'un constat factuel (valeurs
   relevées, écart, faux positifs écartés).

### Repères par cas (relevés lors de la campagne du 2026-10-08)

- **CT-01** : liens de la barre de navigation ; vérifier `document.title`, le `h1` et
  `nav a[aria-current]` par `javascript_tool`. Sur Diagnostic, compter les images non
  chargées (`img.complete === false`) : le 2026-10-08, les 43 logos sont restés vides au
  premier passage, sans reproduction ensuite. Dire s'il réapparaît.
- **CT-02** : scénario par `form_input` sur le sélecteur « Choisir un scénario » (valeur
  `bare_llm`). Le prompt suggéré « Quelle heure est-il ? » ne fait que remplir le champ :
  cliquer ensuite sur « Envoyer ». Le modèle local tourne sur CPU : attendre par captures
  successives (5 à 10 s) que la réponse et « Tour 1 terminé » apparaissent, sans attente
  fixe longue.
- **CT-03** : valeur `native_tools`, même prompt, puis relever l'heure du poste avec
  `date "+%H:%M:%S"` dès la réponse affichée. Zoomer sur ③ Orchestration pour montrer
  « Demande un outil get_datetime » et « Déclenché par le modèle ». Si le modèle n'appelle
  pas l'outil, activer « Afficher les actions forcées » et le dire : c'est prévu.
- **CT-04** : lire la zone RÉSEAU du schéma, puis `read_network_requests` (tous les hôtes
  doivent être 127.0.0.1:8420 ou `data:`). Recouper côté serveur :
  `Get-NetTCPConnection -OwningProcess (Get-NetTCPConnection -LocalPort 8420 -State Listen).OwningProcess`
  et grouper les connexions établies par adresse distante.
- **CT-05** : menu « Affichage » : `form_input` sur le thème (`dark`), clic sur « Mode
  projection », Échap. **Avant la capture, survoler la barre de navigation** : la souris
  posée sur une étape grise les autres volets (effet voulu, faux positif du 2026-10-08).
  Mesurer ce qu'on voit (hauteur visible de la conversation, `#bricks` qui déborde) ; un
  `select` natif tronqué ne se mesure pas, il se voit. Défauts du 2026-10-08 à confirmer
  ou déclarer corrigés : réponse coupée dans ① Vue humain, « Changer de modèl… » tronqué,
  défilement horizontal du panneau des briques.
- **CT-06** : la langue ne change qu'après « Vider la conversation » (aucune boîte de
  dialogue). `form_input` langue `de`, puis balayer textes et attributs (`title`,
  `aria-label`, `placeholder`) par `javascript_tool` avec un filtre de mots français,
  et trier à la lecture : l'article allemand « des », « Français » (nom de langue) et
  `recette_crepes.txt` sont des faux positifs. Les infobulles d'hébergement des modèles
  cloud (« Google (hébergement non précisé) »…) sont une **limite connue** documentée dans
  `wavestack.toml` (commentaire avant `[[cloud.models]]`) : la citer, ne pas la compter.
  Ouvrir l'Atelier LLM, section « Chargement du modèle » : le 2026-10-08, ses messages
  restaient en français sous des intitulés allemands.

### Règles de verdict

- OK si le résultat attendu du cahier est tenu ; KO (préciser « mineur » ou « bloquant »)
  sinon ; Bloqué si le cas n'a pas pu s'exécuter (modèle absent, page en erreur).
- Un écart ne compte qu'une fois vérifié : rechargement, deuxième essai, ou mesure dans le
  DOM. Dire quand un défaut ne se reproduit pas.
- Ne pas modifier le code de WaveStack pendant la démo.
- Aucune boîte de dialogue JavaScript : ne cliquer ni « Supprimer » ni « Réinitialiser ».

## 3. GIF (seulement avec l'argument « gif »)

`gif_creator` plafonne à 50 images : un GIF par moitié. Démarrer avant CT-01 (capture
juste après), arrêter et exporter après CT-03 (`demo-recette-partie-1.gif`), puis de même
pour CT-04 à CT-06 (`demo-recette-partie-2.gif`). Annoncer les fichiers téléchargés.

## 4. Remise en état et bilan

1. Dans WaveStack : thème clair, mode projection désactivé, langue français.
2. Remonter en haut du cahier pour montrer le compteur d'avancement.
3. Laisser les deux onglets ouverts (l'audience les regarde) et les serveurs tourner.
4. Dans le chat : un tableau cas / verdict / constat en une ligne, puis la comparaison
   avec la campagne du 2026-10-08 (archivée dans
   `http://127.0.0.1:8430/runs/cahier-2026-10-08-1500.html`) : défauts toujours présents,
   corrigés, ou nouveaux.
