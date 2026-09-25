---
title: Sprint Change Proposal — lisibilité pédagogique d'Orchestration et du schéma
date: 2026-09-25
author: Anaël (avec Claude, workflow bmad-correct-course)
trigger: test manuel de la story 8c (commit 15301a4)
scope: modéré
status: approuvée (2026-09-25)
---

# Sprint Change Proposal — lisibilité pédagogique d'Orchestration et du schéma

## 1. Résumé du problème

Au test manuel de la story 8c (commit `15301a4`), deux défauts de lisibilité vont à l'encontre de l'objectif pédagogique de WaveStack :

1. **Schéma d'architecture** : on ne distingue pas visuellement un hook d'un outil. Tous les nœuds hors du cadre Harnais sont des rectangles identiques (`renderSchema`, `src/wavestack/web/static/app.js:1477`), posés en grille de trois lignes dans l'ordre d'arrivée ; jusqu'à 20 nœuds (6 outils, 3 serveurs MCP, 6 skills, 4 hooks, fichier d'audit). Seuls le libellé et l'infobulle diffèrent.
2. **Orchestration** : dès le lancement, le volet est rempli de texte brut. `renderJournal()` (`app.js:1257`) affiche chaque enveloppe en `JSON.stringify(payload, null, 2)`, sans titre ni repli, sous les étapes : diagnostic, `bricks_changed`, aperçu du contexte, découverte MCP. Le déroulé d'un tour est difficile à suivre.

**Nature** : spécification juste, implémentation partielle, dérive accumulée depuis la story 2.

- La story 2 posait « Orchestration = journal brut des événements » comme échafaudage provisoire ; aucune story ne l'a remplacé. La story 8c l'a ensuite figé dans EXPERIENCE.md (« restent dans la liste des événements, en bas d'Orchestration »).
- Le rail d'étapes spécifié (`turn-rail`, étapes dépliables, « Suivre le direct ») n'a jamais été construit : `renderSteps()` (`app.js:1143`) empile des cartes à plat, tous tours confondus, sans en-tête de tour.
- Les zones Poste de travail / Réseau et la frontière ont été exclues de la 6c (« Never ») et reportées dans `deferred-work.md`, avec la mention qu'elles imposent de refaire la disposition du schéma.

**Preuve** : maquette interactive de la cible, validée par Anaël : `ux-designs/ux-agentic-harness-training-demo-2026-09-22/.working/maquette-orchestration-schema-v3.html`.

## 2. Analyse d'impact

### Stories

| Story | Impact |
|---|---|
| 2, 6c, 8c (faites) | Aucune reprise de code annulée ; leurs écarts sont repris par 8d et 8e. |
| **8d** (nouvelle) | Orchestration : rail par tour, préparation du harnais, journal replié. |
| **8e** (nouvelle) | Schéma : bacs par catégorie, points d'accroche, zones et frontière. |
| **8f** (nouvelle) | Volets redimensionnables par les gouttières (ajout demandé pendant la revue de la maquette). |
| 9 (à faire) | Doit s'appuyer sur le rail par tour (badge « Rejeu », « Forcé par l'utilisateur » sur la ligne d'étape) et sur le bac Fichiers (mémoire globale). Dépend de 8d et 8e. |
| 10 (à faire) | La réinitialisation ramène Orchestration à « Aucun tour » ; le journal affiché repart de zéro. Le scénario « Hooks » s'appuie sur la bande des points d'accroche. |

### Artefacts

| Artefact | Impact |
|---|---|
| PRD | Aucun. FR-2, FR-3, FR-4, FR-14, FR-20, FR-22 inchangés ; MVP inchangé. |
| Architecture (ARCHITECTURE-SPINE) | Aucun. AD-1 (le front ne calcule pas d'état) et AD-2 (journal) respectés : grouper par tour et par `kind` relève de la mise en forme. Seule réserve : si `tool_started` / `hook_decided` ne permettent pas de retrouver l'id du composant en action, l'ajouter à leur payload (8e). |
| EXPERIENCE.md | Surfaces, Découpe retenue, Masquage des volets (redimensionnement), Component Patterns (rail, préparation, journal, données sortantes, vue humain, schéma), State Patterns (Aucun tour), Interaction Primitives, Responsive & Platform, Codage local / réseau. |
| DESIGN.md | Frontmatter (`architecture-band-height`), Layout & Spacing (poignées), Components (rail, préparation, journal, schéma, poignée de gouttière), Do's and Don'ts. |
| `tokens.css`, `tests/test_web_tokens.py` | Token `architecture-band-height` 200 → 250 px (story 8e). |
| `stories.yaml` | Insertion de 8d, 8e et 8f ; descriptions de 9 et 10. |
| `deferred-work.md` | Élément 6c sur les arêtes du schéma repris par 8e. |

### Technique

Front seul (`app.js`, `app.css`, `index.html`, `tokens.css`) ; pas de nouvelle dépendance ; pas de changement d'événement, sauf la réserve de 8e ci-dessus.

## 3. Approche recommandée

**Ajustement direct** : trois stories front insérées avant la 9 (8d, 8e, 8f), sans retour arrière ni revue du MVP.

- *Retour arrière* : écarté. La 6c et la 8c posent des fondations réutilisées (robot, cadre Harnais, tokens, validation H5).
- *Revue du MVP* : sans objet, aucune exigence ne change.
- **Effort** : moyen (trois stories front, dont une réécriture de `renderSchema` ; 8f est petite).
- **Risque** : faible à moyen. Point d'attention : le budget vertical à 1280×650 (la bande du schéma passe à 250 px), atténué par 8f, qui laisse le formateur ajuster les tailles.
- **Calendrier** : +3 stories avant la 9 ; la 9 devient plus simple à rendre lisible.

## 4. Propositions de modification détaillées

### A. Orchestration (approuvée)

**A1. EXPERIENCE.md, Surfaces, ligne « Orchestration », colonne Rôle**

- OLD : « Étapes d'orchestration du tour, événements du harnais, échanges MCP, données sortantes »
- NEW : « Étapes groupées par tour, préparation du harnais (connexions MCP hors tour), journal des événements replié ; événements du harnais, échanges MCP, données sortantes »

**A2. EXPERIENCE.md, Component Patterns, « Rail d'étapes » (remplacée)**

- OLD : « Une étape par action du harnais, dans l'ordre (FR-2). Pendant un tour, la vue suit l'étape courante ; un clic sur une étape fige la vue sur celle-ci et fait apparaître « Suivre le direct ». Les étapes de brique (recherche RAG, reranking, hook, compression, délégation) sont dépliables. »
- NEW : Rail d'étapes (`turn-rail`, `turn-group`, `turn-step`). Les étapes sont groupées par tour, dans l'ordre réel (FR-2). En-tête de groupe : « Tour N », début du message de l'utilisateur, statut (en cours, terminé, arrêté, contexte dépassé), durée totale, nombre d'appels au modèle. Le tour en cours (ou le dernier) est déplié ; les tours précédents sont repliés à leur en-tête, un clic les déplie. Dans un tour déplié, chaque étape tient sur une ligne : icône du type, titre, qui décide (modèle, harnais, utilisateur), chiffre clé (tokens, durée ou décision). L'étape courante est dépliée et suivie pendant le tour ; un clic déplie ou replie une étape et fige la vue, ce qui fait apparaître « Suivre le direct ». Restent dépliés : événements en échec ou en blocage (appel mal formé, hook qui bloque, dépassement) et validation humaine en attente.

**A3. EXPERIENCE.md, Component Patterns, deux nouvelles lignes**

- Préparation du harnais (`harness-prep`) | Orchestration, au-dessus du premier tour | Ce que le harnais fait hors tour : connexion aux serveurs MCP et liste de leurs outils (FR-19, FR-22). Replié par défaut : une ligne par serveur, état (connecté · N outils, ou indisponible · raison) et, pour un serveur public, « RÉSEAU → adresse ». Déplié : l'étape de connexion complète, données sortantes comprises. Une connexion faite entre deux tours prend la même forme, à sa place dans le rail.
- Journal des événements (`event-log`) | Orchestration, en bas | Tous les événements émis par le harnais, pour aller plus loin (AD-2). Replié par défaut, titre « Journal des événements (N) » ; il ne s'ouvre jamais seul. Déplié : une ligne par événement, heure, nom en français et nom technique (`tool_started`), résumé d'une ligne ; le JSON brut s'ouvre ligne par ligne, à la demande. « Vider la conversation » ne le vide pas.

**A4. EXPERIENCE.md, Component Patterns, « Données sortantes »**

- OLD : « Ouvert par défaut, jamais replié automatiquement. »
- NEW : « Ouvert dès que son étape est dépliée, jamais replié automatiquement. Une étape réseau repliée affiche « RÉSEAU → adresse » sur sa ligne : la sortie du poste reste visible sans dépliage. »

**A5. EXPERIENCE.md, Component Patterns, « En-tête de la vue humain »**

- OLD : « …et restent dans la liste des événements, en bas d'Orchestration ; »
- NEW : « …et restent dans le journal des événements (replié, en bas d'Orchestration) ; »

**A6. EXPERIENCE.md, State Patterns, « Aucun tour »**

- OLD : « Contexte LLM et Orchestration : « Aucun tour pour l'instant. Envoyez un message : le contexte envoyé au modèle apparaîtra ici. » »
- NEW : « Contexte LLM : « Aucun tour pour l'instant. Envoyez un message : le contexte envoyé au modèle apparaîtra ici. » Orchestration : « Aucun tour pour l'instant. Envoyez un message : les étapes du harnais apparaîtront ici. », avec au-dessus la préparation du harnais et au-dessous le journal replié. Dès le lancement, aucun texte brut n'est déplié. »

**A7. EXPERIENCE.md, Interaction Primitives, « Bannis »** : ajouter « texte brut ou JSON déplié sans que l'utilisateur l'ait demandé ».

**A8. DESIGN.md, Components, « Rail d'étapes » (enrichi) et deux composants**

- OLD : « colonne verticale d'étapes reliées par un filet ; étape courante marquée d'un point vert, étape sélectionnée sur violet doux. »
- NEW : Groupe de tour (`turn-group`) : en-tête « Tour N » en `heading`, extrait du message en `body-sm` encre douce, statut en badge, chiffres en `number` ; les étapes sont reliées par un filet vertical `{colors.line}` de 2 px. Étape (`turn-step`) repliée : une ligne, tuile d'icône `{rounded.sm}`, titre en `label`, chiffre clé en `number` aligné à droite, chevron ▸ / ▾. Icône par type (appel au modèle, demande d'outil, exécution, chargement de documentation, skill, hook, validation humaine, réinjection, réponse finale), toujours doublée du titre. Étape courante : point vert ; étape sélectionnée : violet doux. Contenu interne sans relief.
- Ajout : Préparation du harnais (`harness-prep`) : même traitement qu'un groupe de tour, titre « Préparation du harnais », sans relief.
- Ajout : Journal des événements (`event-log`) : en-tête repliable en `label` avec chevron ; lignes en `body-sm`, nom technique en `{typography.code}` encre douce, JSON en `{typography.code}` sur crème. Aucune couleur d'état ni de segment.

**A9. EXPERIENCE.md, Découpe retenue**

- OLD : « En tête d'Orchestration : sélecteur de tour (« Tour 1, Tour 2… ») et « Suivre le direct ». »
- NEW : « En tête d'Orchestration : « Suivre le direct » et l'indicateur de travail. Pas de sélecteur de tour : les tours repliables du rail le remplacent. »

**A10. EXPERIENCE.md, Rail d'étapes (complément)** : quand la ligne manque de place, elle se tronque dans cet ordre : titre de l'étape (avec points de suspension, texte entier en infobulle et au dépliage), puis l'adresse de « RÉSEAU → adresse ». Le marqueur « RÉSEAU », l'acteur qui décide et le chiffre clé ne sont jamais tronqués.

### B. Schéma d'architecture (approuvée)

**B1. EXPERIENCE.md, Component Patterns, « Schéma d'architecture » (remplacée)**

- OLD : « Seules les briques actives y figurent (FR-3), sauf les serveurs publics indisponibles, qui restent dessinés (FR-20). Pendant un tour, le nœud en action a un halo et le flux parcouru s'anime. Clic sur un nœud : sélection synchronisée. Nœud serveur MCP ou skill : dépliable pour lister les outils exposés ou le détail du skill (FR-3). »
- NEW : Seules les briques actives y figurent (FR-3), sauf les serveurs publics indisponibles, qui restent dessinés (FR-20). Deux zones séparées par la frontière (voir Codage local / réseau). Les composants sont rangés en bacs par catégorie, chaque bac titré avec son icône et son nombre de composants : Outils, Serveurs MCP, Fichiers, Skills côté Poste de travail ; Outils réseau, Serveurs MCP publics côté Réseau. Le cadre Harnais contient le modèle et les puces des briques sans composant externe (mémoire courte, prompt système). Les hooks ne forment pas un bac : ils occupent la bande « Points d'accroche », dans le cadre Harnais, un hook par ligne avec son point d'accroche. Tout flux vers un bac part de cette bande. Liaisons : un tronc sous les bacs, parti de la bande, qui franchit la frontière ; un rail par colonne de bacs. Pendant un tour : halo sur le nœud ou le hook en action, chemin parcouru en vert, animé quand il franchit la frontière. Validation H5 en attente : le chemin s'arrête avant la frontière, marqueur ✋. Blocage par un hook : le chemin s'arrête à la bande, marqueur ✖, hook sur filet rouge. Clic sur un nœud : sélection synchronisée. Nœud serveur MCP : nombre d'outils exposés affiché, liste au dépliage (FR-3).

**B2. EXPERIENCE.md, Codage local / réseau (ajout)** : **Catégories** : la catégorie d'un composant se lit à son bac, à sa forme et à son icône, jamais à une couleur. Les couleurs restent réservées au lieu d'hébergement (violet, jaune) et à l'état (vert, rouge, gris).

**B3. DESIGN.md, Components, « Schéma d'architecture » (enrichi)**

- Bac (`arch-group`) : contenant blanc à bordure `{colors.line}` 2 px, `{rounded.md}`, sans relief ; titre `label` posé sur la bordure (icône, nom, nombre). Côté Réseau : fond crème.
- Forme par catégorie, dans les couleurs du lieu d'hébergement : outil = tuile d'icône ronde à gauche du nom ; serveur MCP = double trait (local) ou double tirets (réseau), pastille « N outils » ; skill = filet gauche épais de 7 px ; fichier = fond crème, icône document. Toutes gardent `{rounded.sm}` ; la maquette utilise des coins de 4 à 6 px sur skill et fichier, la spine l'emporte.
- Bande des hooks (`arch-hook-strip`) : dans le cadre Harnais, séparée du modèle par un tiret violet, étiquette pilule « Points d'accroche » ; hook en pièce violet doux à deux lignes (nom, point d'accroche). En action : halo vert. Bloquant : filet rouge de 7 px et « ✖ a bloqué ». Désactivé : tirets gris.
- Tronc et rails (`arch-trunk`) : trait `{spacing.stroke-min}` encre douce, en tirets après la frontière ; chemin parcouru en halo vert 7 px avec un trait encre au centre, en tirets animés quand il franchit la frontière. Marqueurs ✋ (violet) et ✖ (rouge).
- Le robot et les puces de brique s'empilent verticalement dans le cadre.

**B4. DESIGN.md, frontmatter + Layout & Spacing** : `architecture-band-height` 200px → 250px. `[ASSUMPTION]` À 1280×650, la rangée du haut perd 50 px ; si c'est trop juste, le formateur masque un volet ou passe le schéma en mode focus (EXPERIENCE, Responsive). Répercuté dans `tokens.css` et `tests/test_web_tokens.py` par la story 8e.

**B5. DESIGN.md, Do's and Don'ts (ajout)** : Do « Distinguer les catégories du schéma par le bac, la forme et l'icône » / Don't « Donner une couleur à chaque catégorie ».

### C. Backlog (approuvée)

**C1. `stories.yaml`** : insérer après la story 8 :

```yaml
- id: "8d"
  title: Orchestration lisible : rail par tour, préparation du harnais, journal replié
  description: >-
    Remplace la liste brute des événements, restée de l'échafaudage de la story 2, par le
    rail d'étapes groupé par tour (une ligne par étape, étape courante dépliée,
    « Suivre le direct »), la préparation du harnais (connexions MCP hors tour) et le
    journal des événements replié en bas du volet (CAP-2, CAP-4). Dès le lancement, aucun
    texte brut n'est déplié.
  spec_checkpoint: true
  done_checkpoint: true
  invoke_dev_with: >-
    Réécrire renderSteps et renderJournal (app.js) selon EXPERIENCE.md (turn-rail,
    turn-group, harness-prep, event-log, données sortantes) et DESIGN.md. Aucun
    changement de backend, d'événement ni de /api/state (AD-1, AD-2). Maquette de
    référence : ux-designs/.../.working/maquette-orchestration-schema-v3.html.

- id: "8e"
  title: Schéma par catégories, points d'accroche et frontière
  description: >-
    Bacs par catégorie (outils, serveurs MCP, fichiers, skills), bande « Points
    d'accroche » des hooks dans le cadre Harnais, zones Poste de travail / Réseau
    séparées par la frontière, chemin parcouru, arrêt H5 et blocage visibles (CAP-3,
    FR-3, FR-20). Ferme l'élément de deferred-work sur les arêtes du schéma (6c).
  spec_checkpoint: true
  done_checkpoint: true
  invoke_dev_with: >-
    Réécrire renderSchema (app.js). Grouper par node.kind et hosting, déjà fournis par
    architecture_changed (AD-12). Vérifier que tool_started et hook_decided permettent de
    retrouver l'id du composant en action ; sinon, l'ajouter à leur payload (seul
    changement de backend admis). Token architecture-band-height à 250 px (tokens.css et
    test_web_tokens.py). Même maquette de référence.
```

**C2. Story 9, description (ajout)** : S'appuie sur le rail par tour (8d) : un tour rejoué devient un nouveau groupe de tour avec le badge « Rejeu » ; une action forcée porte « Forcé par l'utilisateur » sur sa ligne d'étape. La mémoire globale s'ajoute au bac Fichiers du schéma (8e). Dépend de 8d et 8e.

**C3. Story 10, description (ajout)** : La réinitialisation ramène Orchestration à « Aucun tour » en gardant la préparation du harnais. Le journal des événements affiché repart de zéro, alors que le journal côté serveur reste complet. Le scénario « Hooks » (UJ-2) s'appuie sur la bande des points d'accroche (8e).

**C4. `deferred-work.md`** : sur l'élément 6c « l'arête d'un nœud de la colonne 2 passe sous le nœud de la colonne 1 », ajouter « Repris par la story 8e (tronc et rails, zones et frontière). »

### D. Volets redimensionnables (approuvée)

**D1. EXPERIENCE.md, Masquage des volets (ajout)**

- **Redimensionner** : la gouttière entre deux volets voisins est une poignée. Cliquer-glisser déplace la limite : entre les colonnes de la rangée du haut, entre la rangée du haut et le schéma, entre le panneau des briques et le reste. Chaque volet garde une taille minimale (en-tête lisible, au moins 240 px de large, 160 px de haut). Un double-clic sur une poignée rétablit les proportions par défaut.
- Au clavier, la poignée prend le focus et se déplace avec les flèches, par pas de 16 px.
- Les tailles choisies survivent au changement de scénario, à la réinitialisation et au rechargement, comme la configuration des volets. Le navigateur les mémorise.
- Masquer un volet libère sa place selon les tailles courantes ; le réafficher lui rend sa dernière taille.

**D2. EXPERIENCE.md, Interaction Primitives et Responsive & Platform**

- Interaction Primitives : « Masquer, réafficher » devient « Masquer, réafficher, redimensionner » ; la redistribution de l'espace se fait sans animation décorative.
- Responsive : les proportions par défaut s'appliquent tant que l'utilisateur n'a rien déplacé ; ensuite, ses tailles priment, dans la limite des minimums.

**D3. DESIGN.md, Layout & Spacing et Components**

- Poignée de gouttière (`pane-resize-handle`) : invisible au repos (on voit les pois de la page). Au survol ou au focus, une pilule violette de 4 × 32 px apparaît au milieu de la gouttière, avec le curseur ↔ ou ↕. Pendant le glissement, la pilule reste visible. La zone de saisie fait au moins `{spacing.hit-target-min}`, même si la gouttière visible reste à `{spacing.gutter}`.

**D4. `stories.yaml`** : insérer après 8e :

```yaml
- id: "8f"
  title: Volets redimensionnables
  description: >-
    Poignées de gouttière pour redimensionner les volets par glisser-déposer ou au
    clavier, tailles minimales, double-clic pour rétablir, tailles mémorisées par le
    navigateur (complète CAP-2 et CAP-3 en salle).
  spec_checkpoint: false
  done_checkpoint: true
  invoke_dev_with: >-
    Front seul (app.js, app.css) : tailles en variables CSS de la grille, poignées
    accessibles (role="separator", aria-valuenow), mémorisation comme la configuration
    des volets. Aucun changement de backend.
```

## 5. Passage de relais

**Portée : modérée.** Réorganisation du backlog et mise à jour de la spec UX, sans replanification ni changement de PRD ou d'architecture.

| Rôle | Responsabilité |
|---|---|
| Développeur (Claude, workflow bmad-correct-course) | Appliquer les modifications A, B, C et D à EXPERIENCE.md, DESIGN.md, `stories.yaml` et `deferred-work.md`. |
| Développeur (`bmad-build`) | Spécifier puis livrer 8d, 8e (point de contrôle de spec pour chacune), puis 8f. |
| Anaël | Valider la spec de 8d et de 8e aux points de contrôle, puis tester à la main avec la maquette comme référence. |

**Critères de succès**

- Au lancement, Orchestration n'affiche aucun JSON ni texte brut déplié ; le journal des événements est replié et compte ses événements.
- Pendant un tour, on suit le déroulé de haut en bas dans un seul groupe de tour, étape courante dépliée ; les tours précédents sont repliés.
- Dans le schéma, un hook, un outil, un serveur MCP, un skill et un fichier se distinguent sans lire leur libellé, et la frontière Poste de travail / Réseau est visible.
- Un blocage H1 et une attente H5 se lisent dans le schéma (✖ sur la bande, ✋ avant la frontière).
- Les volets se redimensionnent à la souris et au clavier, sans descendre sous leur taille minimale, et retrouvent leurs tailles après rechargement.
- Aucune régression des tests existants ; `test_web_tokens.py` vert avec le nouveau token.
