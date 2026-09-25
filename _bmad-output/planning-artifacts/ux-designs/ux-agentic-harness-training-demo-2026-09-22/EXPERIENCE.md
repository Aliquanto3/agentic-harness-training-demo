---
title: EXPERIENCE — WaveStack
status: draft
created: 2026-09-22
updated: 2026-09-23
sources:
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/addendum.md
---

# WaveStack — Experience Spine

> Brouillon en mode rapide. Les hypothèses sont marquées `[ASSUMPTION]`. Le vocabulaire est celui du glossaire du PRD (§3), repris tel quel. Maquettes : [`.working/layout-5-volets-v2.html`](.working/layout-5-volets-v2.html) (référence) et [`.working/layouts-4-vs-5-volets.html`](.working/layouts-4-vs-5-volets.html) (historique de la comparaison 4 contre 5 volets). En cas de conflit, ces spécifications priment sur les maquettes.

## Foundation

- **Forme** : application web locale, une seule surface desktop, ouverte dans le navigateur du poste (FR-36) et servie sur `127.0.0.1` (NFR-4). Pas de mobile, pas de mode multi-utilisateur.
- **Usage principal** : le formateur est seul aux commandes, l'écran est projeté ou partagé en visio (UJ-1, UJ-4). Usage secondaire : un participant technique seul sur son poste (UJ-2, UJ-3).
- **Système d'interface** : aucun système de composants tiers nommé. `DESIGN.md` est la référence d'identité visuelle ; ce document décrit le comportement. Le choix du framework (NiceGUI ou Streamlit, addendum) relève de l'architecture et ne change pas ce contrat.
- **Principe directeur** : tout ce que fait le harnais est visible, rien n'est masqué pour aller plus vite (SM-C3, NFR-1). Une défaillance du modèle est un matériau pédagogique, jamais un plantage (NFR-8).
- **Langue** : interface et contenus en français (NFR-7). Thème clair uniquement `[ASSUMPTION]`.

## Information Architecture

### Surfaces

Tout ce qui suit est indépendant de la découpe en 4 ou 5 volets.

| Surface | Atteinte depuis | Rôle | Besoins servis |
|---|---|---|---|
| Diagnostic de démarrage | Lancement (FR-36) ; icône d'état dans la barre haute `[ASSUMPTION]` | Vérifier mémoire, modèle, réseau, port ; proposer l'action corrective et les modèles déjà présents sur le poste | FR-37, FR-34, UJ-3 |
| Barre haute | Permanente | Programme et scénario, jauge de contexte, puces des volets masqués et menu « Volets ▾ », modèle, taille de texte, réinitialisation | FR-38, FR-41, FR-4, FR-32, NFR-9, FR-39 |
| Panneau des briques | Volet masquable (colonne gauche) | Activer, désactiver, expliquer chaque brique ; forcer une action | FR-5, FR-6, FR-9, FR-13, FR-18, FR-21, FR-23, FR-27, FR-42 |
| Tiroir d'édition | Carte « Prompt système » ou « Mémoire globale » → « Modifier » | Modifier le prompt système ; consulter, modifier, effacer la mémoire globale | FR-11, FR-12 |
| Vue humain | Volet masquable | Converser comme dans un chatbot ; prompts suggérés ; rejeu ; raisonnement affiché ou masqué | FR-1, FR-7, FR-9, FR-10, FR-38 |
| Contexte LLM (vue harnais) | Volet masquable | Contexte exact de l'appel au modèle sélectionné, segmenté par brique, et sortie brute du modèle | FR-2, FR-8, FR-17, FR-24, FR-29, FR-30, FR-31 |
| Orchestration (vue harnais) | Volet masquable | Étapes d'orchestration du tour, événements du harnais, échanges MCP, données sortantes | FR-2, FR-14, FR-15, FR-18, FR-22, FR-28, FR-29, FR-42, NFR-8 |
| Détail de la jauge | Clic sur la jauge (barre haute) → s'ouvre dans Contexte LLM | Grille de la fenêtre de contexte, part de chaque segment, espace libre | FR-41 |
| Comparaison de tours | Contexte LLM → « Comparer » ; badge « Rejeu » d'un message | Deux tours côte à côte : contextes, tokens d'entrée et de sortie, temps | FR-7, FR-25, FR-21, FR-24 |
| Schéma d'architecture | Volet masquable (bande basse, à droite du panneau des briques) | Composants actifs, lieu d'hébergement, composant en action | FR-3, FR-12, FR-16, FR-19, FR-20, UJ-1, UJ-4 |
| Sélecteur de scénario | Barre haute | Parcourir le programme, lancer un module ou un scénario en un clic | FR-38, FR-40 |

La « vue harnais » du glossaire correspond aux deux volets Contexte LLM et Orchestration. Tous les volets sont synchronisés (FR-4), qu'ils soient visibles ou masqués : voir Interaction Primitives. Aucune fenêtre modale ne recouvre la zone de démonstration ; seuls le tiroir d'édition et les listes déroulantes se superposent, un niveau au plus.

### Découpe retenue : 5 volets masquables

Référence : [`.working/layout-5-volets-v2.html`](.working/layout-5-volets-v2.html).

```
┌──────────────────────────── Barre haute ──────────────────────────────────┐
│ Scénario │ ███████▒▒▒ Jauge │ + Volet │ Volets ▾ │ Modèle │ Aa 100 % │ ⟲ │
├──────────┬─────────────┬────────────────────┬──────────────────────────────┤
│ Briques  │ Vue humain  │ Contexte LLM       │ Orchestration                │
│          │             │ segments, sortie   │ rail d'étapes, événements    │
│          ├─────────────┴────────────────────┴──────────────────────────────┤
│          │ Schéma d'architecture       Poste de travail ┊ Réseau           │
└──────────┴────────────────────────────────────────────────────────────────┘
```

- Colonne de gauche sur toute la hauteur : Briques (panneau des briques). À droite, rangée du haut : Vue humain, Contexte LLM, Orchestration ; bande basse sous ces trois volets : Schéma d'architecture. Quand les briques sont masquées, les autres volets prennent toute la largeur ; quand le schéma est masqué, la rangée du haut prend toute la hauteur.
- **Contexte LLM** : les tokens envoyés lors de l'appel au modèle sélectionné, segmentés et étiquetés, puis la sortie brute (raisonnement, texte, appels d'outils). Le détail de la jauge et la comparaison de tours s'y ouvrent.
- **Orchestration** : le rail d'étapes du tour (appel au modèle, interprétation de la sortie, exécution, réinjection, décision de continuer ou de s'arrêter, plus les étapes des briques actives : recherche RAG, reranking, hook, compression, délégation au sous-agent) et le détail de chaque étape. Sélectionner une étape « Appel au modèle » met à jour Contexte LLM.
- Chaque volet peut être masqué ; les volets visibles se partagent l'espace libéré (voir Masquage des volets). Le contexte et l'orchestration restent visibles en même temps.
- Pas d'onglet RAG dédié `[ASSUMPTION]` : les extraits RAG sont des segments du contexte ; la recherche et le reranking sont des étapes dépliables de l'orchestration.
- En tête d'Orchestration : sélecteur de tour (« Tour 1, Tour 2… ») et « Suivre le direct ». En tête de Contexte LLM : « Comparer ».

**Option A (4 volets, vue harnais fusionnée) : écartée.** Anaël préfère voir le contexte et l'orchestration en même temps ; le manque de largeur est compensé par le masquage des volets.

### Masquage des volets

- Chaque volet a un bouton « — » dans son en-tête pour le masquer.
- Un volet masqué devient une puce « + Nom » dans la barre haute ; un clic le réaffiche à sa place.
- Le menu « Volets ▾ » de la barre haute bascule chaque volet, affiché ou masqué.
- Les volets visibles se partagent l'espace libéré. Au moins un volet reste visible : le dernier « — » est désactivé.
- La synchronisation (FR-4) continue : si un volet masqué contient un élément correspondant à la sélection, sa puce le signale.
- `[ASSUMPTION]` La configuration des volets survit au changement de scénario et à la réinitialisation (FR-39), qui ne touche que la conversation et les briques. Le navigateur la mémorise.
- Configurations d'exemple, sans mécanisme de préréglages :
  - **Plongée dans le harnais** : Contexte LLM, Orchestration, Schéma d'architecture ;
  - **Configuration salle** : Vue humain, Orchestration, Schéma d'architecture, texte à 125 %.
- Le panneau des briques replié en rail d'icônes est abandonné : le masquage le remplace.

## Voice and Tone

Microcopie. La voix de marque vit dans `DESIGN.md`, section Brand & Style.

Règles :
- Le vocabulaire du glossaire (PRD §3) est repris tel quel : brique, tour, contexte, fenêtre de contexte, vue humain, vue harnais, schéma d'architecture, panneau des briques, lieu d'hébergement (processus local, fichier local, service réseau), LLM nu, rejeu d'un prompt. Les termes anglais consacrés du PRD restent en anglais : tokens, lazy loading, reranking, prompt engineering, context engineering, harness engineering.
- Un message d'état = ce qui se passe + pourquoi, en une phrase, + l'action possible s'il y en a une. Le « pourquoi » est la matière pédagogique.
- On nomme toujours qui décide : le modèle, le harnais (code) ou l'utilisateur. C'est la distinction centrale de WaveStack (FR-28, FR-42).
- Vouvoiement `[ASSUMPTION]`, phrases courtes et complètes, pas de point d'exclamation, pas d'emoji, pas de jargon d'erreur technique brut sans traduction.
- Les nombres sont précis : « 1 840 tokens », « 6 s », jamais « beaucoup » ou « un moment ».

| Do | Don't |
|---|---|
| « Indisponible : le modèle actif ne sait pas raisonner. » | « Erreur de capacité » |
| « Indisponible : le lazy loading exige la brique MCP. » | Interrupteur grisé sans explication |
| « data.gouv.fr indisponible : pas de réponse au démarrage. Le serveur MCP local reste utilisable. » | « Connexion échouée » |
| « Lecture du contexte (1 840 tokens)… 6 s » | Un spinner seul |
| « Le modèle a produit un appel d'outil mal formé. Le harnais réinjecte l'erreur et relance (essai 2 sur 3). » | « Parsing error » |
| « Bloqué par le hook garde-fou. Décision du harnais (code), pas du modèle. » | « Action refusée » |
| « Ces données quittent le poste vers mcp.data.gouv.fr. » | « Requête externe envoyée » |
| « Contexte plein à 85 % : les prochains tours risquent de dépasser la fenêtre. » | « Attention ! » |
| « Contexte dépassé — l'appel au modèle n'a pas été envoyé. 4 310 tokens pour une fenêtre de 4 096 : les descriptions MCP en documentation complète pèsent 2 900 tokens. » | « Context overflow » |
| « Modèle introuvable. Copiez le fichier du modèle depuis le partage du formateur dans le dossier indiqué, puis relancez WaveStack. » | « Model not found » |
| « Aucun tour pour l'instant. Envoyez un message : le contexte envoyé au modèle apparaîtra ici. » | Volet vide sans texte |

Explications de brique (FR-6) : deux ou trois phrases sur ce que la brique ajoute au LLM nu, puis sa catégorie et le lieu d'hébergement de ses composants. Les termes émergents (loop engineering, agentic engineering) sont cités avec leur date, jamais présentés comme une catégorie.

## Component Patterns

Comportement. Les specs visuelles sont dans `DESIGN.md`, section Components ; les noms sont identiques.

| Composant | Où | Règles de comportement |
|---|---|---|
| Barre haute (`top-bar`) | Toutes surfaces | Toujours visible, y compris en mode focus. Ne défile jamais. |
| Volet (`pane`) | Chaque volet | Bouton ⛶ → mode focus sur ce volet ; ⛶ de nouveau ou `Échap` → retour à la grille. Bouton « — » (`pane-hide-button`) → masque le volet ; désactivé sur le dernier volet visible. |
| Puce de volet masqué (`pane-chip`) | Barre haute | Une puce « + Nom » par volet masqué, dans l'ordre des volets. Un clic réaffiche le volet à sa place. Si le volet masqué contient un élément lié à la sélection, la puce porte la marque « lié » (FR-4). |
| Menu Volets (`pane-menu`) | Barre haute | « Volets ▾ » ouvre la liste des cinq volets avec une case chacun ; cocher ou décocher affiche ou masque. La dernière case cochée est désactivée. |
| Sélecteur de scénario (`scenario-picker`) | Barre haute | Liste le programme par modules, dans l'ordre de FR-38, puis les scénarios transverses et métier (FR-40). Un clic sur un module ou un scénario applique sa configuration de briques. `[ASSUMPTION]` Lancer un scénario vide la conversation ; la mémoire globale n'est pas touchée. |
| Jauge de contexte (`context-gauge`) | Barre haute | Montre le contexte de l'appel au modèle le plus récent. Se met à jour à chaque appel, y compris entre les étapes d'un même tour (FR-41). Survol d'un segment : nom et tokens. Clic : ouvre le détail de la jauge dans Contexte LLM (réaffiche le volet s'il est masqué). Ordre d'empilement : prompt système, mémoire globale, descriptions d'outils et de skills, historique, extraits RAG, résultats d'outils, message et gabarit, puis espace libre. Seuil d'alerte à 80 % `[ASSUMPTION]`. |
| Sélecteur de modèle (`model-picker`) | Barre haute | Change le modèle actif (FR-32), entre deux tours seulement : désactivé pendant un tour. Chargement d'environ 5 à 20 s, annoncé par l'indicateur de travail ; la conversation est conservée (validé par Anaël, faisabilité à confirmer en architecture). Au changement, les briques qui exigent une capacité absente passent indisponibles avec leur raison (FR-33). Validé par Anaël : la liste propose aussi les fichiers GGUF déjà présents sur le poste (Ollama, LM Studio, cache Hugging Face) ou un chemin saisi ; un serveur local Ollama ou llama.cpp déjà lancé passe par l'adaptateur de FR-32. Demande de changement au PRD (FR-34). |
| Réglage de taille de texte (`text-size-control`) | Barre haute | Contrôle unique « Aa 100 % » : chaque clic passe au palier suivant, 100 → 125 → 150 → 100 %. Effet immédiat, sans recharger la page. Mémorisé sur le poste `[ASSUMPTION]`. |
| Bouton Réinitialiser (`reset-button`) | Barre haute | Un clic, sans confirmation (FR-39 : « en un geste ») : LLM nu, conversation vide, mémoire globale de démonstration restaurée. Placé à l'extrémité droite, à l'écart des autres commandes, pour limiter le clic accidentel `[ASSUMPTION]`. Ne touche pas la configuration des volets. Confirmation par un message discret : « WaveStack réinitialisé : LLM nu. » |
| Détail de la jauge (`context-gauge-detail`) | Contexte LLM, ouvert depuis la jauge | Grille de la fenêtre de contexte et légende par segment, pour l'appel sélectionné. Clic sur une cellule ou une ligne de légende : sélection synchronisée. « Fermer » revient à l'étape en cours. |
| Carte de brique (`brick-card`) | Panneau des briques | Interrupteur (`brick-toggle`) : effet au tour suivant (FR-5), indiqué par « Prend effet au prochain tour » tant qu'aucun tour n'a eu lieu depuis le changement. Explication dépliable (FR-6). Sous-options dépliables : outils individuels (FR-13), reranking (FR-18), serveurs MCP et mode documentation complète / lazy loading (FR-21), skills (FR-23), hooks (FR-27). Indisponible : interrupteur désactivé, raison visible en permanence. Clic sur le nom : sélection synchronisée (FR-4). |
| Étiquette de lieu d'hébergement (`hosting-tag-local`, `hosting-tag-network`) | Cartes de brique, sous-options, schéma | Présente sur toute brique ou tout outil qui introduit un composant. Un outil réseau porte toujours l'étiquette « RÉSEAU » (FR-13). |
| Bouton Forcer (`force-button`) | Sous-options des briques mémoire globale, MCP (lazy loading), skills, sous-agent | Arme l'action pour le prochain tour ou le prochain rejeu (FR-42) `[ASSUMPTION]`. L'action armée s'affiche en puce au-dessus du champ de saisie (« Armé : Caveman ») ; un clic sur la puce désarme. Libellés : « Écrire en mémoire », « Charger la documentation », « Déclencher le skill », « Déléguer au sous-agent ». |
| Tiroir d'édition (`edit-drawer`) | Par-dessus le panneau des briques | Prompt système : texte modifiable, « Enregistrer » applique au tour suivant (FR-11), « Rétablir le prompt par défaut ». Mémoire globale : liste des entrées, modification et suppression unitaire, « Tout effacer » (FR-12). Se ferme par `Échap` ou « Fermer » ; une modification non enregistrée est signalée à la fermeture. |
| En-tête de la vue humain | Vue humain | « Afficher le raisonnement » (FR-9) ; « Rejouer le dernier prompt » avec la configuration actuelle, actif dès le premier tour (FR-7) ; « Vider la conversation » (FR-10), sans toucher aux briques ni à la mémoire globale : les tours précédents disparaissent de la vue humain, de Contexte LLM et d'Orchestration (connexions MCP comprises), y compris après rechargement, et restent dans la liste des événements, en bas d'Orchestration ; la jauge, les briques et le journal d'audit ne sont pas vidés. La réinitialisation complète relève de la story 10 (CAP-41). |
| Champ de saisie (`composer`) | Vue humain | `Entrée` envoie. Désactivé pendant un tour et pendant un changement de modèle, avec la raison. Les actions armées s'affichent au-dessus. |
| Messages (`chat-message-user`, `chat-message-model`) | Vue humain | Le message du modèle s'affiche en streaming (FR-1). Un message issu d'un rejeu porte un badge « Rejeu » qui ouvre la comparaison. Clic sur un message : sélectionne son tour dans Contexte LLM et Orchestration (FR-4). |
| Bloc de raisonnement (`reasoning-block`) | Vue humain | Visible si l'option « Afficher le raisonnement » est cochée dans l'en-tête de la vue humain (FR-9) ; toujours visible dans Contexte LLM. Replié par défaut, dépliable. |
| Prompt suggéré (`suggested-prompt-chip`) | Vue humain, au-dessus du champ de saisie | Proposé par le scénario actif (FR-38). Un clic remplit le champ sans envoyer `[ASSUMPTION]` : le formateur peut commenter ou modifier avant d'envoyer (UJ-2). |
| Indicateur de travail (`working-indicator`) | Vue humain ; en-tête d'Orchestration | Apparaît dès l'envoi et reste jusqu'à la réponse finale. Libellé de la phase en cours (« Lecture du contexte (1 840 tokens) », « Exécution de l'outil heure », « Appel au sous-agent ») et chronomètre en secondes (NFR-1 : latence visible). Remplacé par le texte dès que les tokens arrivent, réapparaît entre deux appels du même tour. |
| Rail d'étapes (`turn-rail`, `turn-step`) | Orchestration | Une étape par action du harnais, dans l'ordre (FR-2). Pendant un tour, la vue suit l'étape courante ; un clic sur une étape fige la vue sur celle-ci et fait apparaître « Suivre le direct ». Les étapes de brique (recherche RAG, reranking, hook, compression, délégation) sont dépliables. |
| Segment de contexte (`context-segment`) | Contexte LLM, détail de la jauge, comparaison | Texte intégral, sans troncature par défaut (FR-2). Étiquette = brique d'origine + tokens. Les segments longs se replient à la demande de l'utilisateur, jamais automatiquement. Clic : sélection synchronisée. |
| Compteur de tokens (`token-counter`) | Chaque étape « Appel au modèle » | Tokens du contexte au total et par segment, tokens de sortie, temps écoulé (FR-30). |
| Badge de déclenchement (`trigger-badge-model`, `trigger-badge-user`) | Orchestration, sur l'étape concernée | Présent sur chaque écriture en mémoire globale, chargement de documentation MCP, déclenchement de skill, délégation au sous-agent (FR-42). « Déclenché par le modèle » ou « Forcé par l'utilisateur ». Jamais absent sur ces quatre actions. |
| Événement du harnais (`harness-event`) | Orchestration, dans le rail et le détail de l'étape | Pour : hook (FR-28), appel mal formé (FR-15), limite d'appels par tour (NFR-8), compression (FR-31). Donne l'événement, la décision, qui l'a prise, l'effet sur le tour. Le reflet dans le schéma d'architecture est simultané. |
| Carte de dépassement (`overflow-card`) | Orchestration, à la place de l'étape « Appel au modèle » | Titre « Contexte dépassé — l'appel au modèle n'a pas été envoyé », compte de tokens (contexte / fenêtre) et cause (segments les plus lourds). Puis « En production, un harnais pourrait » : fenêtre glissante, compaction, retrait des anciens résultats d'outils, lazy loading. Puis « Pour continuer la démo » : passer en lazy loading, désactiver un serveur, vider la conversation ; chaque piste nomme la commande à utiliser (NFR-8, FR-41). |
| Données sortantes (`outbound-payload`) | Orchestration, étape d'un outil réseau ou d'un serveur MCP public | Adresse de destination et données exactement envoyées hors du poste (FR-22). Ouvert par défaut, jamais replié automatiquement. |
| Comparaison de tours (`turn-compare`) | Contexte LLM | Par défaut, compare le tour rejoué et son tour d'origine, côte à côte ; sinon l'utilisateur choisit deux tours. Aligne les segments par brique ; affiche les écarts de tokens d'entrée, de sortie et de temps (FR-7, FR-25). « Fermer » revient au tour sélectionné. |
| Schéma d'architecture (`arch-node-*`, `arch-flow`, `arch-boundary`) | Bande basse | Seules les briques actives y figurent (FR-3), sauf les serveurs publics indisponibles, qui restent dessinés (FR-20). Pendant un tour, le nœud en action a un halo et le flux parcouru s'anime. Clic sur un nœud : sélection synchronisée. Nœud serveur MCP ou skill : dépliable pour lister les outils exposés ou le détail du skill (FR-3). |
| Ligne de diagnostic (`diagnostic-row`) | Diagnostic de démarrage | Une ligne par vérification (mémoire, modèle, réseau, port). État, explication, action corrective (FR-37). |

## State Patterns

| État | Surface | Traitement |
|---|---|---|
| Premier démarrage, diagnostic en cours | Diagnostic de démarrage | Les quatre lignes passent d'« En cours » à OK ou Échec. Le même diagnostic s'écrit dans le terminal. `[ASSUMPTION]` Si le port est indisponible, le navigateur ne peut rien afficher : seul le terminal parle, avec l'action corrective. |
| Diagnostic : échec bloquant (modèle absent, mémoire insuffisante) | Diagnostic de démarrage | Ligne rouge, cause et action (voie hors ligne pour le modèle, FR-34). L'accès à l'interface est impossible tant que le modèle manque. |
| Diagnostic : échec non bloquant (pas de réseau) | Diagnostic de démarrage, puis panneau des briques et schéma | Ligne rouge « Pas de réseau », suivie de « Les briques réseau seront indisponibles. Le reste fonctionne. » (NFR-3). Bouton « Continuer ». |
| Diagnostic vert | Diagnostic de démarrage | Quatre lignes OK, bouton « Ouvrir WaveStack ». `[ASSUMPTION]` Le diagnostic reste consultable depuis une icône d'état de la barre haute. |
| Aucun tour | Vue humain, Contexte LLM, Orchestration | Vue humain : champ de saisie et prompts suggérés du scénario. Contexte LLM et Orchestration : « Aucun tour pour l'instant. Envoyez un message : le contexte envoyé au modèle apparaîtra ici. » Jauge : espace libre seul. Schéma : nœuds Harnais et Modèle dans la zone Poste de travail. |
| LLM nu | Toutes | Panneau des briques tout éteint. Contexte LLM : un seul segment, « Message et gabarit » (FR-8) ; la jauge ne montre que lui. Schéma : Harnais et Modèle seulement. |
| Travail sans token visible | Vue humain, Orchestration, schéma | Indicateur de travail avec phase et chronomètre ; nœud en action avec halo vert ; étape courante marquée dans le rail (FR-1). Jamais de spinner muet. |
| Streaming | Vue humain, Contexte LLM | Le texte arrive au fil de la génération dans la vue humain et, en brut, dans Contexte LLM pour l'appel en cours. Le compteur de tokens de sortie avance. Le défilement suit la fin du texte, sauf si l'utilisateur a remonté. |
| Brique indisponible : capacité du modèle | Panneau des briques | Interrupteur désactivé, raison : « Indisponible : le modèle actif ne sait pas raisonner. » (FR-9, FR-33). Absente du schéma. |
| Brique indisponible : dépendance | Panneau des briques | « Indisponible : le lazy loading exige la brique MCP. » (FR-5). |
| Brique ou outil réseau indisponible | Panneau des briques, schéma | Sous-option désactivée avec la raison (« pas de réseau », « pas de réponse au démarrage »). Les autres serveurs et outils restent utilisables (FR-20, NFR-3). |
| Serveur MCP public indisponible mais dessiné | Schéma d'architecture, panneau des briques | Nœud dans la zone Réseau, style indisponible (tirets gris, icône barrée), libellé « RÉSEAU · INDISPONIBLE » et raison. Le flux qui le relie au harnais reste tracé en pointillés. Le message sur l'hébergement demeure visible (FR-20). Pas de nouvel essai sans redémarrer WaveStack : c'est accepté, le serveur MCP local sert de repli et la raison le dit. |
| Appel d'outil mal formé | Orchestration, schéma, vue humain | Événement rouge « Appel d'outil mal formé » : sortie brute du modèle, partie fautive signalée, réaction du harnais (nouvel essai, erreur réinjectée ou arrêt) (FR-15). Schéma : nœud Harnais sur filet rouge le temps de l'étape. Vue humain : l'indicateur de travail continue ; en cas d'arrêt, « Le modèle n'a pas pu utiliser l'outil. » L'application ne plante jamais. |
| Limite d'appels par tour atteinte | Orchestration | Événement « Limite de N appels au modèle atteinte : le harnais arrête le tour. » (NFR-8). |
| Hook qui laisse passer ou modifie | Orchestration | Événement violet : événement du tour, hook, décision (« laissé passer », « modifié » avec le détail), mention « Décision du harnais (code), pas du modèle ». |
| Hook qui bloque | Orchestration, schéma, vue humain | Événement rouge « Bloqué par le hook garde-fou » : événement du tour, appel d'outil visé, effet sur le tour, mention « Décision du harnais (code), pas du modèle » (FR-28). Schéma : nœud du hook sur filet rouge ; le flux vers l'outil s'arrête au hook. Vue humain : la réponse finale du modèle, sans maquillage. |
| Validation humaine en attente (hook H5) | Orchestration, vue humain, schéma | Le hook « validation humaine » suspend un appel d'outil réseau avant son exécution. Vue humain : carte violette « En attente de votre validation » dans le fil du tour, sous la bulle du modèle, avec le libellé de l'outil, la destination et les données exactes qui sortiraient du poste (ligne « 🌐 RÉSEAU » visible, corps replié par défaut), et trois boutons « Autoriser », « Refuser » et « Autoriser et ne plus demander » ; une fois la réponse donnée, les boutons laissent la place à la décision et le titre devient « Validation humaine ». L'indicateur de travail affiche « En attente de validation ». Si la vue humain est masquée, sa puce est marquée. Orchestration : la même carte en lecture seule, sans bouton (point d'accroche, hook, outil, destination, aperçu ouvert, décision ou « En attente de votre réponse dans la Vue humain »), avec la mention « Décision demandée par le harnais (code), pas par le modèle ». Schéma : le flux vers le service réseau s'arrête avant la frontière du poste. Refuser réinjecte un refus dans le contexte, et le tour continue. Pas de délai d'expiration en V1 `[ASSUMPTION]`. Démontre le concept de human in the loop (CR-8, H5). |
| Contexte proche de la limite | Barre haute, Contexte LLM | Au-delà du seuil d'alerte, la jauge affiche une icône et « Contexte plein à 85 % » à côté du pourcentage (FR-41). Pas d'interruption. |
| Contexte dépassé | Barre haute, Orchestration, vue humain | L'appel n'est pas envoyé. Jauge au-delà de 100 % sur pastille rouge. Orchestration : carte de dépassement (`overflow-card`) avec compte de tokens, cause, « En production, un harnais pourrait » et « Pour continuer la démo » (NFR-8). Vue humain : « Contexte dépassé : le modèle n'a pas été appelé. » WaveStack reste utilisable. |
| Skill non déclenché / déclenché | Contexte LLM, Orchestration | Non déclenché : segment « descriptions de skills » avec nom et description seulement. Déclenché : étape « Chargement du skill » avec badge de déclenchement, puis segment complet ; le compteur montre l'écart (FR-24). |
| Lazy loading : documentation chargée | Orchestration, Contexte LLM | Étape « Chargement de la documentation » avec badge de déclenchement ; l'écart de tokens est affiché (FR-21). |
| Action armée | Vue humain, panneau des briques | Puce « Armé : … » au-dessus du champ de saisie et sur la carte de brique, jusqu'au tour suivant (FR-42). |
| Sous-agent au travail | Orchestration, Contexte LLM, schéma | Étape « Délégation au sous-agent » dépliable ; bascule « Contexte principal / Contexte du sous-agent » (FR-29). Schéma : second nœud Modèle (même modèle, second contexte) en action. La jauge de la barre haute reste sur le contexte principal `[ASSUMPTION]` ; le compteur du sous-agent est dans son étape. |
| Compression du contexte | Orchestration | Étape « Compression (Headroom) » : contexte avant et après, tokens de chaque version (FR-31). |
| Moins de deux tours | Contexte LLM | « Comparer » désactivé : « Il faut au moins deux tours pour comparer. » |
| Mémoire globale vide | Tiroir d'édition | « Aucune information en mémoire globale. Le modèle peut en écrire, ou vous pouvez forcer une écriture. » |
| Modification non enregistrée | Tiroir d'édition | À la fermeture : « Modification non enregistrée. Enregistrer ou abandonner ? » |
| Rejeu | Vue humain, Contexte LLM, Orchestration | Validé par Anaël : le rejeu reconstruit le contexte à partir de l'état qui précédait le tour d'origine : la question et la réponse d'origine n'y figurent pas, sinon le modèle verrait la question deux fois et sa première réponse. Le tour rejoué porte le badge « Rejeu » ; les deux tours restent consultables côte à côte dans la comparaison (FR-7). La conversation continue à partir du tour rejoué. |
| Changement de modèle en cours | Barre haute, vue humain | Entre deux tours seulement. Indicateur « Chargement du modèle… » avec chronomètre (environ 5 à 20 s) ; envoi désactivé jusqu'à la fin ; conversation conservée. Validé par Anaël, faisabilité à confirmer en architecture. |
| Sélection synchronisée | Tous volets | Voir Interaction Primitives (FR-4). |
| Mode focus | Tous volets | Le volet agrandi occupe la zone principale ; les autres volets visibles se réduisent à leur titre et à leur signal d'état (nœud en action, étape courante). La barre haute reste entière. |
| Volet masqué | Barre haute | Puce « + Nom » ; les volets visibles occupent l'espace. Les signaux du volet masqué ne sont pas perdus : la jauge reste dans la barre haute, et la puce signale un élément lié à la sélection. |
| Un seul volet visible | Tous volets | Son bouton « — » et sa case dans « Volets ▾ » sont désactivés, avec l'infobulle « Au moins un volet reste visible. » |
| Réinitialisation | Tous volets | Retour à l'état « LLM nu » et « Aucun tour » ; la configuration des volets et la taille de texte ne changent pas ; message « WaveStack réinitialisé : LLM nu. » (FR-39). |

## Interaction Primitives

- **Clic pour agir, survol pour prévisualiser.** Aucune information indispensable n'est réservée au survol : en projection, la salle ne voit pas le pointeur.
- **Sélection synchronisée (FR-4).** Une seule sélection à la fois, partagée par tous les volets.
  - Segment de contexte ou segment de la jauge → brique correspondante dans le panneau des briques et composant dans le schéma.
  - Nœud du schéma → brique et segments produits par ce composant.
  - Carte de brique → segments et nœud.
  - Message de la vue humain → tour correspondant dans Contexte LLM et Orchestration.
  - Étape « Appel au modèle » dans Orchestration → contexte de cet appel dans Contexte LLM.
  - Volet masqué qui contient un élément lié → sa puce le signale ; un clic sur la puce réaffiche le volet avec l'élément en évidence.
  - `Échap` ou clic dans le vide efface la sélection. Les éléments sélectionnés portent un contour encre, jamais une couleur seule.
- **Direct par défaut.** Pendant un tour, Contexte LLM, Orchestration et le schéma suivent l'action en cours. Toute sélection manuelle les fige ; « Suivre le direct » les relance.
- **Masquer, réafficher.** « — » dans l'en-tête masque ; la puce « + Nom » ou le menu « Volets ▾ » réaffiche. L'espace se redistribue sans animation décorative. Au moins un volet reste visible.
- **Clavier `[ASSUMPTION]`.** `Entrée` envoie, `Maj+Entrée` passe à la ligne. `Échap` ferme le tiroir, sort du mode focus, efface la sélection. Raccourcis de mode focus par volet, pour agrandir sans viser à la souris devant la salle. Liste exacte fixée en implémentation.
- **Animation.** Réservée au signal « en action » : halo du nœud actif, flux parcouru dans le schéma, point de l'indicateur de travail. Durée courte, pas d'effet d'entrée ou de sortie décoratif.
- **Bannis** : fenêtres modales bloquantes pendant une démonstration, notifications qui masquent un volet, troncature automatique du contexte, information visible au seul survol, défilement automatique qui reprend la main après un défilement manuel.

## Accessibility Floor

Comportement. Le contraste visuel est dans `DESIGN.md`.

- **Jamais la couleur seule** : tout état, tout lieu d'hébergement, tout segment porte icône et libellé. Les segments ont une étiquette directe et une légende.
- **Taille de texte** : contrôle unique « Aa 100 % », trois paliers, 100, 125 et 150 % (NFR-9), sans perte de fonction ; au-delà de ce que la grille peut tenir, le masquage des volets et le mode focus prennent le relais.
- **Volets masqués** : chaque puce est un bouton nommé « Réafficher le volet Nom » ; la marque « lié » est annoncée. Le bouton « — » est nommé « Masquer le volet Nom ».
- **Clavier** : toutes les commandes sont atteignables au clavier, dans l'ordre de lecture (barre haute, panneau des briques, vue humain, Contexte LLM, Orchestration, schéma), en sautant les volets masqués. Anneau de focus visible en `{colors.primary}`, 2 px.
- **Lecteur d'écran** : volets en régions nommées. Le streaming n'est pas lu mot à mot : la réponse est annoncée à la fin du tour (`aria-live` poli). Les événements de blocage, d'échec et de dépassement sont annoncés dès qu'ils surviennent.
- **Mouvement réduit** : avec `prefers-reduced-motion`, le halo et les flux animés deviennent une surbrillance fixe ; l'information reste identique.
- **Cibles** : au moins `{spacing.hit-target-min}` de côté.
- **Traits** : au moins `{spacing.stroke-min}` dans le schéma, pour survivre au vidéoprojecteur et à la compression vidéo en visio.

## Responsive & Platform

WaveStack n'a pas de résolution garantie : la salle impose l'écran.

| Contexte | Fenêtre utile | Comportement |
|---|---|---|
| EliteBook seul, petit public sans écran | Environ 1280×650 px CSS (14 pouces en 1920×1080, mise à l'échelle Windows 150 %) `[ASSUMPTION]` | Cas de référence le plus contraint : la grille entière tient au palier 100 %. Aux paliers 125 et 150 %, masquer deux volets (par exemple la « Configuration salle ») ou passer en mode focus. Plein écran du navigateur (`F11`) conseillé pour regagner la hauteur. |
| Projection, écran externe | Variable, souvent 1280×720 à 1920×1080 | La grille s'étire ; les proportions des volets sont conservées. La taille de texte se règle selon la distance de la salle, pas selon l'écran. |
| Partage en visio (réunion Teams) | Celle de l'écran partagé | Palier 125 % minimum conseillé : la compression vidéo efface les petits textes et les traits fins. |
| Largeur inférieure à 1280 px | — | Aucun masquage automatique : l'utilisateur choisit ses volets. `[ASSUMPTION]` En dessous de 1024 px, le mode focus devient le seul mode d'affichage. |

- Maquettes dimensionnées sur 1280×720 `[ASSUMPTION]` : [`.working/layout-5-volets-v2.html`](.working/layout-5-volets-v2.html) montre la grille complète, « Plongée dans le harnais » et « Configuration salle ».
- Navigateur : celui du poste professionnel (Edge ou Chrome sous Windows 11, NFR-6). Aucune extension, aucun service distant.
- Polices et ressources servies localement : l'interface fonctionne sans réseau (NFR-3).

## Codage local / réseau

Le schéma d'architecture porte la question clé du produit : où sont hébergés le harnais, les données et le modèle (SM-3). Le codage est partagé par tous les volets `[ASSUMPTION]`.

- **Deux zones** : « Poste de travail » à gauche, « Réseau » à droite, séparées par une ligne frontière. Harnais, modèle, outils hors ligne, serveur MCP local, mémoire globale et index RAG sont dans le Poste de travail ; outils réseau et serveurs MCP publics dans la zone Réseau.
- **Trois lieux d'hébergement** (glossaire) : processus local (icône engrenage), fichier local (icône document), service réseau (icône globe, libellé « RÉSEAU »). Couleurs et bordures selon `DESIGN.md` : local violet plein, trait continu ; réseau jaune, tirets encre.
- **Même codage partout** : étiquette de lieu d'hébergement sur les cartes de brique (FR-6, FR-13), nœuds du schéma (FR-3), en-tête des données sortantes dans Orchestration (FR-22).
- **Franchir la frontière se voit** : pendant un appel à un service réseau, le flux qui traverse la frontière s'anime et un clic dessus ouvre les données sortantes de cet appel.
- **Le serveur MCP local est un processus distinct** du harnais : deux nœuds séparés, même zone (FR-19).
- **Un serveur public indisponible reste dessiné** (FR-20).

## Conduite de session formateur

Comment l'interface soutient le formateur devant la salle (UJ-1, UJ-4). Aucune fonction propre : c'est l'usage combiné des surfaces ci-dessus.

- **Préparer** : lancer le diagnostic avant l'arrivée de la salle ; choisir le module dans le sélecteur de scénario ; masquer les volets inutiles au module (par exemple la « Configuration salle ») ; régler la taille de texte depuis le fond de la salle.
- **Dérouler** : s'appuyer sur les prompts suggérés plutôt qu'improviser (FR-38) ; activer une brique, puis rejouer le même prompt et ouvrir la comparaison (FR-7).
- **Rattraper un SLM faible** : armer l'action que le modèle n'a pas déclenchée, puis rejouer (FR-42). Le badge « Forcé par l'utilisateur » garde la démonstration honnête.
- **Transformer l'échec en matériau** : un appel mal formé, un hook qui bloque ou un contexte qui déborde sont des événements lisibles ; le formateur les agrandit en mode focus pour les commenter (FR-15, NFR-8).
- **Zoomer sur un moment** : mode focus sur le schéma pour la question de l'hébergement, sur Contexte LLM pour le contexte, sur Orchestration pour un événement.
- **Rebondir sur un dépassement** : la carte de dépassement donne la matière (ce que ferait un harnais en production) et la sortie (passer en lazy loading, désactiver un serveur, vider la conversation).
- **Finir** : réinitialiser en un geste pour la session suivante (FR-39).
- **Dernier recours** : la vidéo d'une session précédente, hors de WaveStack (PRD §4.13).

## Inspiration & Anti-patterns

- **Repris de la commande `/context` de Claude Code** (FR-41, addendum) : une vue de la fenêtre de contexte ventilée par source, avec l'espace libre et la part de chaque source. Adapté en deux niveaux : une barre empilée compacte, toujours visible dans la barre haute, et une grille détaillée à la `/context` au clic, dans Contexte LLM, avec légende et tokens par segment.
- **Repris de la charte Wavestone** : palette, polices, rayons. **Rejetés** : curseur personnalisé, révélations au scroll, compteurs animés ; ils servent un site vitrine, pas une application projetée.
- **Rejeté : cacher des étapes pour paraître rapide** (SM-C3). La latence est montrée, chronomètre compris.
- **Rejeté : tronquer le contexte par défaut** (FR-2). Le contexte intégral est la preuve.
- **Rejeté : onglet RAG dédié** `[ASSUMPTION]`. Les extraits RAG sont des segments du contexte comme les autres ; les isoler casserait la lecture « tout ce qui entre dans le modèle ».
- **Rejeté : vue harnais fusionnée en un seul volet (option A).** Elle obligeait à choisir entre voir le contexte et voir l'orchestration ; le masquage des volets règle mieux le manque de largeur. **Rejeté aussi : panneau des briques replié en rail d'icônes**, remplacé par le masquage.
- **Rejeté : mode sombre en V1** `[ASSUMPTION]`. Moins lisible projeté dans une salle éclairée.
- **Rejeté : le code couleur seul pour le local / réseau.** Un participant daltonien, ou un vidéoprojecteur délavé, doit lire la même chose.

## Key Flows

> Parcours RAG, sous-agent, compression et Caveman en attente de la mise à jour du PRD (voir [`prd-change-requests.md`](prd-change-requests.md)).

### Flow 1 — Le « déclic MCP » (Anaël, premier module d'une heure, douze consultants en salle) — UJ-1

1. Avant la session, Anaël lance WaveStack d'une commande sur son portable. Le diagnostic de démarrage passe au vert ; il règle la taille de texte à 125 % depuis le fond de la salle.
2. Il choisit le premier module dans le sélecteur de scénario : panneau des briques tout éteint, LLM nu.
3. Il clique sur le prompt suggéré « Quelle heure est-il ? » et l'envoie. L'indicateur de travail affiche « Lecture du contexte » et son chronomètre, puis la réponse arrive en streaming : le modèle invente une heure.
4. Dans Contexte LLM, l'appel ne contient qu'un segment, « Message et gabarit ». La jauge est presque vide.
5. Il active la mémoire courte, puis le prompt système. Il rejoue le même prompt. La comparaison de tours montre deux nouveaux segments et le compteur de tokens qui grossit ; la jauge s'allonge sous les yeux de la salle.
6. Il active les outils. Nouveau tour : le schéma d'architecture s'anime. Le modèle demande l'outil heure, le nœud de l'outil s'allume, le résultat revient au harnais, qui le réinjecte ; Orchestration déroule les cinq étapes du cycle d'appel d'outil (FR-14).
7. Cas limite : au tour suivant, le modèle émet un appel mal formé. Un événement rouge apparaît dans Orchestration ; Anaël passe Orchestration en mode focus et montre que c'est le harnais, pas le modèle, qui réinjecte l'erreur et relance.
8. Il active la brique MCP, puis le serveur public data.gouv.fr. Un nœud jaune à bordure en tirets apparaît de l'autre côté de la frontière, étiqueté « RÉSEAU » ; la jauge fait un bond d'environ 2 900 tokens.
9. Il envoie le prompt suggéré sur la cybersécurité. Le flux traverse la frontière et s'anime.
10. **Temps fort :** un participant demande « donc là, mes données partent où ? ». Anaël clique sur le flux qui franchit la frontière : Orchestration ouvre les données sortantes, avec l'adresse `mcp.data.gouv.fr` et le texte exact parti du poste. La salle a compris la question de l'hébergement.
11. En fin de session, il clique sur Réinitialiser : retour au LLM nu, conversation vide.

Échec : pas de réseau dans la salle. Le serveur data.gouv.fr reste dessiné dans la zone Réseau, marqué « INDISPONIBLE : pas de réseau ». Anaël fait passer le message sur le dessin, puis poursuit avec le serveur MCP local. Si le modèle ne charge pas un outil en lazy loading, il arme « Charger la documentation » et rejoue ; le badge « Forcé par l'utilisateur » le signale. Si le contexte déborde avec le serveur en documentation complète, la carte de dépassement devient une leçon sur le lazy loading.

### Flow 2 — Ce qu'un hook peut bloquer (Karim, consultant SOC, seul sur son poste après la session) — UJ-2

1. Karim a installé WaveStack en suivant la procédure en français (hors interface). Il lance WaveStack ; le diagnostic est vert.
2. Dans le sélecteur de scénario, il lance le scénario « Hooks ». Les briques outils et hooks s'activent, dont le garde-fou et la journalisation.
3. Il clique sur un prompt suggéré, puis le modifie dans le champ pour demander au modèle de lire un fichier sensible du dossier de démonstration.
4. Le tour démarre. Dans Orchestration, le modèle demande l'outil de lecture de fichier ; l'étape suivante est « Hook : avant l'exécution d'un outil ».
5. **Temps fort :** un événement rouge « Bloqué par le hook garde-fou » s'affiche, avec la mention « Décision du harnais (code), pas du modèle ». Dans le schéma, le flux s'arrête au nœud du hook ; l'outil ne s'allume jamais. Karim voit que c'est du code déterministe, et non le modèle, qui a décidé.
6. L'événement de journalisation apparaît aussi dans le rail : il note une idée de cas d'usage pour la détection d'incidents.

Échec : le modèle ne tente pas l'appel d'outil. Aucun hook ne se déclenche et Orchestration le montre (pas d'étape d'exécution). Karim reformule ou reprend le prompt suggéré tel quel. Voir Questions ouvertes (forçage d'un appel d'outil).

### Flow 3 — Poste verrouillé (Léa, consultante cloud, la veille de la session) — UJ-3

1. Léa suit le README et lance WaveStack d'une commande.
2. Le diagnostic de démarrage s'ouvre. Mémoire : OK. Port : OK. Réseau : OK. Modèle : Échec.
3. La ligne du modèle explique : « Le téléchargement du modèle depuis Hugging Face est bloqué (proxy). » et propose la voie hors ligne : copier le fichier du modèle depuis le partage fourni par le formateur, dans le dossier indiqué, puis relancer WaveStack (FR-34, FR-37). Elle propose aussi les fichiers GGUF déjà présents sur le poste (Ollama, LM Studio, cache Hugging Face) ou un chemin à saisir.
4. Léa copie le fichier et relance la commande.
5. **Temps fort :** les quatre lignes passent au vert et « Ouvrir WaveStack » apparaît. Elle arrive sur le LLM nu, prête pour la session.

Échec : le port est occupé. Le navigateur ne peut rien afficher ; le terminal indique en français le port en conflit et comment en choisir un autre.

### Flow 4 — « Où vont mes données ? » (Anaël face à un client RSSI, démonstration pilotée) — UJ-4

1. Anaël ouvre directement le scénario « Où vont mes données ? » dans le sélecteur de scénario.
2. Il active un outil local. Un nœud violet à trait continu apparaît dans la zone Poste de travail, étiqueté « processus local ».
3. Il active le serveur MCP local. Un second nœud violet apparaît, distinct du harnais : un processus séparé, toujours sur le poste.
4. Il active le serveur MCP public. Un nœud jaune à tirets apparaît de l'autre côté de la frontière, étiqueté « RÉSEAU ».
5. Il envoie le prompt suggéré. Seul le flux vers le serveur public traverse la frontière.
6. **Temps fort :** Anaël passe le schéma en mode focus. Le RSSI voit d'un coup d'œil ce qui reste sur le poste et ce qui en sort ; un clic sur le flux sortant affiche les données exactes envoyées. La démonstration se fait sans adaptation du produit.

Échec : pas de réseau chez le client. Le serveur public reste dessiné, marqué indisponible avec sa raison ; le message sur l'hébergement tient sans l'appel réel.

## Questions ouvertes

Les deux points suivants font l'objet de demandes de changement au PRD, détaillées dans [`prd-change-requests.md`](prd-change-requests.md).

1. **Liste des événements de hook** (FR-26) : hooks retenus par Anaël, H1 à H5, dont la validation humaine. Les événements qui en découlent (réception du message, avant l'appel au modèle, avant un outil, après un outil, fin de tour) sont à reporter dans le PRD (CR-8).
2. **Forçage d'un appel d'outil** pour UJ-2. FR-42 couvre mémoire globale, lazy loading, skills et sous-agent, pas les appels d'outil. Si le SLM n'appelle pas l'outil de lecture, le scénario « Hooks » n'aboutit pas.
