# Rapport de la nuit du 2026-09-28 : suites de la recette du palier 2 (stories 22 à 34)

Exécution autonome par Claude Code dans le cloud, selon `plan-nuit-2026-09-28.md`, à partir des
retours `retours-recette-palier-2-2026-09-28.md` et de la maquette de refonte. Branche de travail :
**`claude/lucid-cori-1rkbjf`**, créée depuis `claude/dreamy-cerf-gdjtee` (commit `9187b55`) et
poussée ; PR : https://github.com/Aliquanto3/agentic-harness-training-demo/pull/2 (base
`claude/dreamy-cerf-gdjtee`).

## 1. Résumé

- **Les 13 stories sont livrées** (`done`), dans l'ordre du plan : 22, 33, 23, 34, 32, 24, 25,
  26, 27, 31, 29, 30, 28. Aucune n'est bloquée. Les deux grandes stories (29 écran « LLM nu », 30
  atelier RAG) sont livrées **avec leurs quatre incréments**.
- **Méthode.** Chaque story est passée par `bmad-build-auto` en mode dossier + id : spec
  (planifiée par un sous-agent, avec le champ `invoke_dev_with`), implémentation par un
  sous-agent, revue à quatre relecteurs en parallèle (Blind Hunter, Edge Case Hunter, écarts de
  vérification, alignement sur l'intention), triage, corrections, puis ruff, pytest et le parcours
  E2E complet. Les sous-agents ne pouvant pas lancer de sous-agents, l'orchestrateur a mené lui-même
  les étapes 1 à 4 du workflow ; le triage de chaque revue est dans la section « Review Triage Log »
  de la spec.
- **État final** : ruff vert ; `uv run pytest -q` : **1 294 passés, 3 ignorés** (935 au départ) ;
  parcours E2E complet : **668 PASS, 0 FAIL** (392 au départ), plus 86 PASS sur la branche « sans
  l'extra rag-alt ». Aucun vrai modèle ici : faux moteur, faux serveurs, GGUF synthétiques (dont
  le GGUF minuscule du dépôt pour un premier test des candidats sur un vrai moteur llama.cpp).
- **Livré en plus, à la demande d'Anaël pendant la nuit** : une première PR après la story 31, le
  cahier interactif `cahier-recette-nuit-2026-09-28.html` (stories 22 à 27 et 31 à 34, 80 tests),
  publié en artefact avec enregistrement des résultats
  (https://claude.ai/artifact/7Er6qrF3fcLtTsMoY6meLf), et un prompt de recette intermédiaire
  (`prompt-test-pc-intermediaire-2026-09-29.md`).
- **Prompt pour le Claude Code du PC cible** : `prompt-test-pc-2026-09-29.md` (couvre toute la
  nuit et remplace le prompt intermédiaire ; liste consolidée « À vérifier sur PC » en annexe).
- **Incidents** : un redémarrage du conteneur (pendant les corrections de la 34) et une limite
  d'usage (pendant les corrections de la 30 et la 28) ; le travail non commité a été sauvegardé
  puis repris sans perte.
- **Une revue de suivi est recommandée pour la story 29** (défaut high corrigé : onglet de
  l'atelier bloqué après une génération sur `/llm` ; lecture des logits dépendante des internes
  de llama-cpp-python).

## 2. Stories

Horodatage = fin d'implémentation (commit poussé après vérification complète). Tests = état au
moment de la story (pytest passés ; E2E complet).

| Ordre | Story | Statut | Commit(s) | Fin (UTC) | pytest | E2E | Revue (constats → suite) |
|---|---|---|---|---|---|---|---|
| 1 | 22 Retours de recette : briques, volets et tiroirs | done | `c1f171e` | 2026-09-28 20:53 | 937 | 392 PASS, 0 FAIL | 27 → 15 corrigés, 6 différés, 5 rejetés |
| 2 | 33 Contrastes et code couleur par discipline | done | `f5f3523` | 2026-09-28 21:55 | 947 | 437 / 0 | 26 → 17 corrigés, 4 différés, 4 rejetés |
| 3 | 23 Données sortantes visibles, en-têtes compris | done | `19b6ee6` | 2026-09-28 22:40 | 968 | 454 / 0 | 25 → 17 corrigés, 5 différés, 1 rejeté |
| 4 | 34 Vue liée au survol et lecture guidée des volets | done | `838ba49` | 2026-09-28 23:48 | 977 | 482 / 0 | 31 → 23 corrigés, 4 différés, 2 rejetés |
| 5 | 32 Contexte LLM lisible | done | `a1980cb` | 2026-09-29 00:45 | 993 | 511 / 0 | 29 → 22 corrigés, 3 différés, 4 rejetés |
| 6 | 24 Mémoire comptée juste, budget dynamique, sonde interruptible | done | `01e65e9` | 2026-09-29 01:36 | 1 042 | 521 / 0 | 27 → 16 corrigés, 4 différés, 3 rejetés |
| 7 | 25 Sélecteur de modèles regroupé et tableau des capacités | done | `db86e0f` | 2026-09-29 02:24 | 1 133 | 545 / 0 | 19 → 13 corrigés, 4 différés, 1 rejeté |
| 8 | 26 Fenêtre de contexte réglable | done | `78f6e5a` | 2026-09-29 03:37 | 1 181 | 569 / 0 | 27 → 16 corrigés, 5 différés |
| 9 | 27 Lot H : scénarios et consignes | done | `72cf3f5` | 2026-09-29 04:24 | 1 185 | 583 / 0 | 24 → 16 corrigés, 3 différés |
| 10 | 31 Mode sombre | done | `175eb5a` | 2026-09-29 05:08 | 1 194 | 609 / 0 | 24 → 16 corrigés, 4 différés |
| 11 | 29 Écran « LLM nu » (4 incréments) | done | `fcca50b` `43dbb57` `28c88f9` `c761f42`, revue `e42ce11`, clôture `23701e3` | 2026-09-29 06:47 | 1 235 | 637 / 0 | 36 → 25 corrigés (dont 1 high), 2 différés ; **revue de suivi recommandée** |
| 12 | 30 Atelier RAG (4 incréments) | done | `a2f4c7a` `da021d6` `b573ae0` `69f0cf3`, revue `90b4145`, clôture `342d807` | 2026-09-29 11:11 | 1 294 | 668 / 0 (+86 sans l'extra) | 33 → 26 corrigés, 4 différés |
| 13 | 28 Guide de test et cahier de recette corrigés | done | `4b830b0` (prompt PC `d1c3ee6`) | 2026-09-29 11:29 | 1 294 | non concerné (documentation) | 26 → 18 corrigés, 2 différés |

Chaque spec (`_bmad-output/specs/spec-agentic-harness-training-demo/stories/{id}-*.md`) donne le
détail : Code Map, tâches, critères, journal de triage, points différés (frontmatter `deferred`),
« Auto Run Result », « Décisions prises par défaut » et « À vérifier sur PC ».

## 3. Décisions prises par défaut

Environ 170 décisions sont consignées, story par story, dans la section « Décisions prises par
défaut » de chaque spec. Les plus structurantes, à confirmer :

- **22** : correctifs d'affichage seulement (l'API accepte encore une sous-option brique
  éteinte) ; « Tour N » repart de 1 après vidage ou réinitialisation, `t{n}` reste au journal et en
  infobulle ; consigne dépliée plafonnée à 12 lignes.
- **33** : groupe du panneau distinct de la catégorie (skills et compression rangés dans « ce que
  le harnais fait ») ; discipline réseau seulement pour ce qui sort du poste ; encre de la charte
  gardée ; le violet ne signifie plus « local » ; discipline et tokens par brique calculés par la
  session.
- **23** : liste blanche d'en-têtes publics, tout le reste « [masqué] » avant le journal ; un nom
  d'en-tête de clé cloud pris dans la liste blanche est refusé ; les en-têtes ajoutés par le
  transport (proxy) ne sont pas tracés.
- **34** : liens tirés du journal (brique, composant, appel) ; seul l'appel affiché dans Contexte
  LLM est lié à ses segments ; bilan des sorties sur le dernier tour affiché, tentatives en échec à
  part ; mode projection à deux états (18 px), mémorisé.
- **32** : sections et déjà-lu calculés par la session ; relance après coupe du raisonnement = même
  appel avec une note ; trois vues (« Lecture groupée », « Texte exact », « Corps JSON » en chat).
- **24** : budget = min(plafond 4 096 Mo, max(512 Mo, 60 % de la RAM disponible au lancement)),
  calculé une fois au lancement, mode `fixed` possible ; sonde interruptible seulement au
  changement à chaud ; coût d'un modèle Ollama = poids + cache à la fenêtre (« décision provisoire,
  à valider », AD-8).
- **25** : page dédiée `/models` en onglets avec le diagnostic ; « toujours » réservé aux
  déclarations cloud ; groupes « Sur ce poste · éditeur » / « Réseau · éditeur ».
- **26** : réglage dans la barre haute ; modèles servis rechargés comme les locaux ; réserve de
  sortie inchangée ; fenêtre gardée après « Réinitialiser » ; valeur ≤ 512 dans `settings.json`
  ramenée au défaut.
- **27** : RAG jamais reconduit après le module 3 (nouvelle exception au cumul, comme le
  raisonnement) ; « Où vont mes données ? » démarre MCP actif ; prompts qui nomment l'outil
  exact ; la leçon d'escalade du SOC passe par la consigne ; aucun code de harnais modifié.
- **31** : palette sombre dessinée (un jumeau par couleur), jetons de rôle, sélecteur compact sous
  1 400 px ; retouches acceptées du thème clair listées dans DESIGN.md (texte sur rouge, bordures
  des contrôles, diagnostic passé aux jetons).
- **29** : écran sur page à part, sans changement de modèle depuis l'écran ; échantillonnage réglable
  seulement sur l'écran (l'atelier envoie toujours les valeurs du harnais, octet pour octet) ;
  candidats sur le moteur intégré seulement, calculés sur les logits de la dernière position
  (jamais `logits_all`) ; top-k 0 = désactivé.
- **30** : bac à sable séparé de la brique ; socle fixe, seule la récupération se réordonne ;
  génération dessinée, non exécutée ; fastembed ni livré ni dans `rag-alt` ; extra `rag-alt`
  = faiss-cpu 1.15.1 + lancedb 0.39.0, roues seulement ; `uv.lock` régénéré avec un paquet
  llama-cpp-python factice (le proxy du conteneur refuse ses hôtes), bloc d'origine recollé.
- **28** : pas de tests détaillés 22 à 34 dans le cahier du palier 2 (précision d'Anaël), renvoi
  vers le cahier de la nuit et le prompt ; nouvelle clé de stockage (`-v2`) : la prochaine séance
  repart de zéro ; procédures du cahier refaites pour ne rien déplacer ni supprimer.

## 4. Points différés à surveiller

Chaque spec les liste dans son frontmatter `deferred`. Les plus importants :

- **29** : lecture des logits dépendante des internes de llama-cpp-python (surveillée par un test
  T = 0 sur le GGUF minuscule) ; chemins du moteur intégré jamais vus dans un navigateur.
- **30** : absence réelle de l'extra, AppLocker et installation sans droits jamais exercées
  (simulées) ; fastembed jamais exécuté avec le vrai paquet.
- **24** : base mémoire non abaissée quand un composant chargé avant elle est libéré ; modèle
  Ollama déjà chargé au lancement compté deux fois (RAM disponible et coût).
- **26** : scénario M4 (MCP en lazy loading + documentation) non testé à 8 192 ou 16 384.
- **27** : aucune action forcée d'appel MCP (souveraineté, IAM) : le comportement dépend du modèle.
- **23** : secrets éventuels dans l'URL non masqués (aucun chemin actuel).
- **28** : aucune procédure PowerShell exécutée (pas de pwsh dans le conteneur) : installation de
  llama-server, D11, Z2 et Z3 à dérouler une première fois sur le PC.
- Barre haute : de plus en plus serrée (liens « LLM nu » et « Atelier RAG », sélecteur de thème,
  « Fenêtre », « Projection ») ; chiffres de la jauge coupés d'environ 13 px à 1 440 px.

## 5. Recette sur le PC cible

1. Coller `prompt-test-pc-2026-09-29.md` dans Claude Code sur le PC : il installe
   (`uv sync --extra compression --extra rag-alt`), lance ruff, pytest, les tests `model` sur les
   vrais GGUF et l'E2E, vérifie lui-même un maximum de points (script `AppSession`, Playwright,
   Claude in Chrome), puis génère et publie le cahier interactif de ce qui reste à faire à la main.
2. Si la recette manuelle a déjà commencé avec `cahier-recette-nuit-2026-09-28.html`, donner son
   compte rendu au Claude Code du PC : il ne refera pas ce qui est jugé.
3. Règles : Edge, Outlook et Teams fermés avant toute mesure (sur demande à Anaël) ; jamais
   llama-server sans `-c` avec le 2B chargé ; aucune modification du code sans accord.

## 6. Liste « À vérifier sur PC », story par story

Liste consolidée des sections « À vérifier sur PC » des specs, dans l'ordre de la nuit (même
contenu que l'annexe du prompt). Pour les stories 22 à 27 et 31 à 34, le cahier de la nuit les
détaille sous les identifiants N22-1 à N34-6.


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
