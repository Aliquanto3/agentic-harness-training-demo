# Revue d'accessibilité : Atelier MCP en séquence (lot 4 du 2026-10-04)

Date : 2026-10-05. Référentiel : WCAG 2.2 AA, plus le plancher de l'application (EXPERIENCE.md, « Accessibility Floor » : cibles de 32 px, traits de 2 px, jamais la couleur seule, annonces des blocages et échecs).
Sources lues : EXPERIENCE.md (« Atelier MCP en séquence », « Accessibility Floor »), DESIGN.md (composant « Atelier MCP en séquence », `mcp-*` du frontmatter, jetons de couleur clairs et `-dark`), `.working/maquette-atelier-mcp-sequence.html`, `src/wavestack/web/static/diagram.js`, et les règles `diagram-*` de `pages.css`.
Les spines l'emportent sur la maquette. Un écart de la maquette n'est relevé que si les spines ne l'interdisent pas : le build pourrait le reproduire.

**Bilan : 0 critique, 9 hautes, 12 moyennes, 5 basses.**

## Contrastes calculés (valeurs hex du frontmatter de DESIGN.md)

Les fonds composites sont calculés : ligne courante = `accent-soft` à 70 % sur `surface-raised` ; élément « en retrait » = opacité 0,45 sur le fond de sa zone.

| Paire | Clair | Sombre | Verdict |
|---|---|---|---|
| Puce de méthode : encre / `discipline-harness-soft` | 16,7:1 | 13,0:1 | OK |
| Puce réseau : encre / `discipline-network-soft` | 18,0:1 | 11,0:1 | OK |
| Puce du modèle : `on-ink` / `ink-fill` | 19,7:1 | 12,5:1 | OK |
| Puce fantôme : encre douce / `surface-raised` | 8,6:1 | 8,1:1 | OK |
| Bordure de la puce de méthode : `discipline-harness` / `surface-raised` | 5,6:1 | 5,3:1 | OK |
| Trait fantôme ou source : `muted` / `surface-raised` | 3,38:1 | 4,90:1 | OK (trait), limite en clair |
| Trait `muted` sur la ligne courante | 3,11:1 | 4,15:1 | limite en clair |
| Trait d'erreur : `state-error` / `surface-raised` | 3,70:1 | 6,05:1 | OK |
| ✖ : `on-vivid` / `state-blocked` | 5,33:1 | 7,18:1 | OK |
| Encre douce (durées, libellés en italique) sur la ligne courante | 7,95:1 | 6,82:1 | OK |
| **Halo `state-active` / `surface-raised`** | **1,54:1** | 10,8:1 | **échoue en clair (1.4.11)** |
| **Halo `state-active` / ligne courante** | **1,41:1** | n/a | **échoue en clair** |
| **Fond de la ligne courante / `surface-raised`** | **1,09:1** | **1,18:1** | **seul, n'indique rien** |
| **Ligne de vie `line` / `surface-raised`** | **1,24:1** | **1,48:1** | **invisible en projection** |
| **Onglet désactivé : `muted` / `surface-raised`** | **3,38:1** | 4,90:1 | **sous 4,5:1 en clair** (texte de 11,5 px, barré) |
| **« Suivre le direct » pressé ou non : `primary-soft` / `surface-raised`** | **1,20:1** | **1,15:1** | **état visible par la seule teinte** |
| **Client MCP en retrait (texte / fond, opacité 0,45)** | **2,64:1** | **2,87:1** | **échoue (1.4.3)** |
| **Serveur réseau en retrait** | **3,10:1** | **3,51:1** | **échoue (1.4.3)** |
| **Source réseau en retrait (encre douce)** | **2,16:1** | **2,76:1** | **échoue (1.4.3)** |
| Segment pressé : `on-primary` / `primary` | 9,3:1 | 6,7:1 | OK |
| Segment non pressé : `primary` / `surface-raised` | 9,3:1 | 5,7:1 | OK |
| Anneau de focus `primary` sur la ligne courante | 8,6:1 | 4,9:1 | OK |
| Anneau de focus `primary` sur le halo vert | 6,1:1 | n/a | OK |
| Lien « Pourquoi… ? » : `primary` / `surface` | 8,6:1 | 6,4:1 | OK |
| Antenne au repos : `muted` / `ink-fill` | 5,8:1 | 3,7:1 | OK (trait) |

---

## Hautes

### A11Y-01 · haute · 1.4.11, 1.4.1, 1.3.1 / 4.1.2 : la flèche courante ne se voit pas en clair et ne s'entend pas
- **Où** : EXPERIENCE.md, « Stepper du lot 2 » et « Accessibilité » (« flèche courante = halo + fond ») ; DESIGN.md, « Flèche courante » ; `pages.css`, `.diagram-block.is-active` ; `diagram.js`, `createStepper` (seule la position « n / N » est annoncée).
- **Problème** : en thème clair, le halo vert mesure 1,54:1 sur blanc et 1,41:1 sur la ligne courante, dont le fond mesure 1,09:1 face au blanc. Les deux indices sont verts : au vidéoprojecteur, la flèche courante (le climax du Flow MCP-1, « Anaël remonte avec ◀ ») disparaît. Côté lecteur d'écran, rien ne marque la flèche courante (pas d'`aria-current`), et ◀ ▶ n'annoncent que « 4 / 12 », sans dire de quel message il s'agit. Le fil allumé de l'Architecture a le même défaut : seul le halo vert de 7 px le distingue, le cœur encre de 2 px étant presque aussi sombre que le fil au repos (`ink-soft`).
- **Correctif à porter dans les spines** :
  - DESIGN.md, composant `diagram-block.is-active` (lot 2, donc partagé) : halo double, `0 0 0 2px {colors.ink}, 0 0 0 6px {colors.state-active}`. L'anneau d'encre donne 19:1 en clair ; en sombre, utiliser `ink-dark`. Même règle sur la puce, les en-têtes de colonnes et les blocs de l'Architecture. Le cœur du fil parcouru (`diagram-path-core`) passe à 3 px d'encre.
  - Ligne courante : un repère de forme en plus de la couleur, par exemple « ▶ » en `label` encre dans la marge gauche de la ligne (ou le numéro d'étape dans une pastille encre).
  - EXPERIENCE.md, « Accessibilité » : `aria-current="step"` sur le bouton de la flèche courante. Hors du direct, l'annonce donne le nom de la flèche : « Étape 4 sur 12 : Client MCP vers Serveur MCP, tools/call ». Libellé gabarit dans `ui.yaml` (fr, en, de).

### A11Y-02 · haute · 1.3.1, 2.5.3 : le nom des flèches perd ce que le trait et les étiquettes disent
- **Où** : EXPERIENCE.md, « Accessibilité », 1er point (nom « {de} → {vers} : {méthode} {résumé} », plus « (non exécuté ici) ») ; maquette, `renderRow`, dont l'`aria-label` remplace tout le contenu visible.
- **Problème** : l'« honnêteté de la trace » (capturé, déduit, non capturé, fantôme), le réseau (🌐, « les messages quittent le poste »), l'erreur (✖, « isError »), la notification (« sans réponse »), l'aller-retour, « à la place du modèle », et l'étiquette exacte du fantôme (« c'est vous qui l'avez fait », « si l'hôte l'ajoute ») sont visibles mais absents du nom. Deux flèches portent le même nom (« … : initialize » à l'aller et au retour). Les étiquettes visibles ne figurent pas dans le nom (2.5.3), et « → » se lit « flèche droite ».
- **Correctif** : remplacer la règle par un gabarit ordonné, tiré de `ui.yaml` dans les trois langues : « {de} vers {vers} : {méthode ou libellé} {résumé}[, réseau, sort du poste][, requête | réponse | notification sans réponse][, {origine : capturé sur le transport | dans l'hôte, déduit | dans le serveur, non capturé | événement du modèle}][, erreur : {raison}][, fantôme : {étiquette du fantôme}][, aller-retour {n} ms | à {n} ms] ». Préférer le contenu visible complété de fragments masqués visuellement plutôt qu'un `aria-label` qui écrase le texte. Ne jamais mettre le chronomètre en cours dans le nom.

### A11Y-03 · haute · 4.1.3 (plancher : « blocage, échec, dépassement annoncés dès qu'ils surviennent ») : rien n'est annoncé quand les messages arrivent ou échouent
- **Où** : EXPERIENCE.md, États (« Poignée de main en cours », « Serveur injoignable », `isError`, « Erreur JSON-RPC », « outil inconnu ») et Accessibilité ; `createStepper` met la position en `aria-live="off"` en direct.
- **Problème** : un utilisateur de lecteur d'écran clique « Se connecter » et n'entend rien : ni la fin de la poignée de main, ni « serveur injoignable (ConnectError) » après 10 s, ni « isError ». Le plancher de l'application exige l'annonce immédiate des échecs.
- **Correctif** : EXPERIENCE.md, « Accessibilité » : une région `role="status"` par page, masquée visuellement. À la fin de chaque phase, elle annonce la synthèse de l'en-tête de phase (« Poignée de main · Glossaire WaveStack : ouverte en 1 371 ms, 2 outils, 1 ressource, 1 prompt »). Les échecs (injoignable, délai dépassé, `isError`, erreur JSON-RPC, outil inconnu refusé par le harnais) passent dans un `role="alert"`, une seule fois. Pas d'annonce flèche par flèche, pas de chronomètre en région live ; la fin d'un appel « par le modèle » s'annonce une fois, avec sa durée.

### A11Y-04 · haute · 2.4.3, 2.2.1 / 3.2 (plancher : pas de défilement qui reprend la main) : focus perdu et défilement imposé pendant le direct
- **Où** : EXPERIENCE.md, « Phases » (« Quand une phase commence, les précédentes se replient ») et « Stepper » (« défile pour rester visible ») ; maquette, `renderSeq` (`list.replaceChildren()` à chaque rendu) et `onShow` (`scrollIntoView` à chaque arrivée en direct).
- **Problème** : (a) si le focus est sur une flèche ou dans un encart d'une phase qui se replie seule, l'élément devient `hidden` et le focus tombe sur `body` ; (b) si le build reconstruit la liste comme la maquette, chaque arrivée détruit le focus et referme les encarts ; (c) en direct, chaque arrivée fait défiler la Séquence, même quand l'utilisateur lit un JSON déplié plus haut, ce que la section « Bannis » interdit.
- **Correctif** : dans EXPERIENCE.md, « Phases » et « Stepper » :
  - ajout incrémental des lignes, jamais de reconstruction de la liste pendant une session ;
  - une phase qui contient le focus ne se replie pas d'elle-même (ou le focus passe à son bouton d'en-tête avant le repli) ;
  - un défilement manuel, ou un focus dans la liste, suspend le défilement automatique, comme dans Orchestration (vue figée, « Suivre le direct » la relance). Une puce « ↓ n nouveaux messages », bouton de 32 px, ramène à la flèche courante.

### A11Y-05 · haute · 2.1.1, 4.1.2 : « Pourquoi… ? » est inaccessible au clavier dans l'en-tête de phase
- **Où** : EXPERIENCE.md, « Phases » (« en en-tête le titre, la synthèse et un lien « Pourquoi… ? » ») ; DESIGN.md, `mcp-phase-header` ; maquette : `span.phase-why` cliquable dans le `button` d'en-tête, et `aria-expanded` posé sur le `li`.
- **Problème** : un élément interactif dans un bouton n'est ni atteignable au Tab ni annoncé. Entrée replie la phase au lieu d'ouvrir l'explication (le restaurant, la règle « qui choisit »). Dans la maquette, `aria-expanded` est posé sur un `li`, qui ne le prend pas.
- **Correctif** : structure à fixer dans EXPERIENCE.md. En-tête de phase = `h3` contenant le bouton de repli (`aria-expanded` et `aria-controls` vers la liste de la phase), puis, à côté, un bouton distinct « Pourquoi… ? » (`aria-expanded`, `aria-controls` vers l'explication, cible de 32 px). DESIGN.md : « lien » devient « bouton à l'aspect d'un lien ».

### A11Y-06 · haute · 1.4.4, 1.4.12 (NFR-9) : pas de mode projection sur /mcp, et une mise en page en pixels fixes
- **Où** : DESIGN.md, `projection-toggle` (« sur l'atelier seulement (seul `app.js` applique la projection) ») ; EXPERIENCE.md, « Repli » (« si 1 280 × 650 ne suffit pas en projection… ») ; `mcp-arrow.row-height: {spacing.6}` ; `mcp-panes` (290 px, 206 px) ; maquette : légendes en `position: absolute; bottom: 12px` dans une ligne de 32 px, rangées de 32 px dans l'Architecture.
- **Problème** : la page est faite pour être projetée, mais le mode projection n'existe que sur l'écran principal (`site-nav.js` et `mcp.js` ne l'appliquent pas). Le formateur doit passer par le zoom du navigateur ; or la rampe ×9/7 (ou un zoom de 125 %) donne une puce d'environ 28 px de haut, posée à 12 px du bas d'une ligne fixe de 32 px. Elle déborde sur la ligne précédente, et les nœuds de 32 px de l'Architecture se tronquent.
- **Correctif** : DESIGN.md, `projection-toggle` : « appliqué aussi par `/mcp`, même mémorisation que l'atelier ; le bouton apparaît dans « Affichage ▾ » ». `mcp-arrow.row-height` devient un minimum (`min-height: max({spacing.6}, 2.4em)`), la légende et le trait sont posés en grille (légende au-dessus, trait dessous) et non en positions absolues. Hauteur de la bande Architecture et de ses rangées en `em`, ou recalculée sous `:root.projection`. Critère de build : à 1 280 × 650, en projection et en allemand, aucune légende ne chevauche une autre ligne.

### A11Y-07 · haute · 1.4.4 (plancher : `label` 12 px, lisible en visio) : des textes sous 12 px, en dur, que la projection n'agrandit pas
- **Où** : DESIGN.md, « Serveur et source » : primitives « en `label` réduit » ; maquette : `.prim` 9,5 px, `.robot small` 10 px, `.wire-label`, `.boundary span` et `.seq-head small` 10,5 px, `.tag` 11 px, `.host-label` et `.node.client` 11 px, `.ms`, `.tabs button` et `.node` 11,5 px.
- **Problème** : « 🔧 2 · 📄 1 · 💬 1 » (étape 4 du Flow MCP-1), les noms des transports « stdio » et « HTTP » (climax du Flow MCP-2), les durées et les sous-titres des colonnes deviennent illisibles au fond d'une salle et après compression vidéo. En pixels écrits en dur, ils échappent de plus à la rampe ×9/7.
- **Correctif** : DESIGN.md, composant MCP : « aucun texte sous `{typography.label}` (12 px) ; toutes les tailles passent par les jetons de typographie ». Supprimer « `label` réduit » ; si la place manque, les primitives passent sous le nom sur une seconde ligne, ou le nœud grandit.

### A11Y-08 · haute · 2.5.8 (AA 24 px), plancher `hit-target-min` 32 px : cibles trop petites
- **Où** : DESIGN.md, sélecteurs segmentés « À la main | Par le modèle » et « Documentation complète | Lazy loading », onglets, `mcp-phase-header`, étiquette « Hôte · WaveStack », puces des volets masqués, « Voir le JSON envoyé au modèle » ; maquette : `.diagram-stepper button { min-height: 28px }`.
- **Problème** (hauteurs estimées dans la maquette) : segments environ 23 px, sous le minimum AA puisque les segments se touchent ; puce de volet masqué environ 19 px ; étiquette « Hôte · WaveStack » et « Voir le JSON » environ 15 px ; onglets environ 26 px ; en-tête de phase environ 24 px ; en-têtes de colonnes 30 px ; stepper ramené à 28 px, alors que `pages.css` en donne 32.
- **Correctif** : DESIGN.md, composant MCP, une ligne explicite : « Toute commande, y compris segments, onglets, en-têtes de colonnes et de phase, « Pourquoi… ? », « Voir le JSON », étiquette de l'hôte et puces, a `min-height: {spacing.hit-target-min}` ; le stepper garde les règles du lot 2 ». L'étiquette de l'hôte devient un bouton de 32 px au-dessus du cadre, ou c'est le cadre entier qui porte l'explication.

### A11Y-09 · haute · 1.1.1, 1.3.1, 1.4.1 : dans l'Architecture, transport, échec et connexion ne sont que visuels
- **Où** : EXPERIENCE.md, « Volet Architecture » (fils nommés par leur transport ; ✖ sur le fil ; « Les clients et serveurs non connectés sont en retrait ») ; `wireLayer` : SVG en `aria-hidden` ; maquette : `.node.dim` (opacité seule), zones en `span`.
- **Problème** : « stdio » ou « HTTP », le ✖ rouge du fil HTTP (climax du Flow MCP-2) et l'état connecté ou non n'existent que dans le SVG masqué ou par l'opacité. Les zones « Poste de travail » et « RÉSEAU » (la question clé SM-3) ne sont pas des groupes nommés : au lecteur d'écran, un nœud ne dit pas où il tourne.
- **Correctif** : EXPERIENCE.md, « Accessibilité », point Architecture :
  - chaque zone est un `role="group"` nommé (« Poste de travail », « Réseau, hors du poste ») ; le cadre de l'hôte est un groupe nommé « Hôte WaveStack » ;
  - chaque nœud de serveur porte dans son nom ou sa description son lieu, son transport, son état et ses primitives : « Serveur MCP Glossaire WaveStack, sur le poste, stdio, connecté, 2 outils, 1 ressource, 1 prompt » ; « data.gouv.fr, réseau, HTTP, injoignable (ConnectError) » ;
  - chaque client porte « connecté » ou « non connecté » ;
  - visuellement, « non connecté » se dit autrement que par l'opacité (voir A11Y-10).

## Moyennes

### A11Y-10 · moyenne · 1.4.3 : les éléments « en retrait » descendent sous 4,5:1
- **Où** : DESIGN.md, `mcp-arch-client.dimmed-opacity: 0.45` (« Clients et serveurs non connectés à 45 % d'opacité »).
- **Problème** : ces boutons restent actifs (ils ouvrent leur explication), donc l'exemption des composants inactifs ne s'applique pas. Mesures : client 2,64:1 en clair et 2,87:1 en sombre, serveur réseau 3,10:1 et 3,51:1, source réseau 2,16:1 et 2,76:1.
- **Correctif** : remplacer l'opacité par un état neutre en jetons : fond `{colors.discipline-neutral-soft}`, bordure `{colors.muted}`, texte `{colors.ink-soft}` (au moins 8:1). Si l'opacité doit rester, elle ne touche que le fond et la bordure (au moins 0,7), jamais le texte.

### A11Y-11 · moyenne · 4.1.2, 2.1.1, 1.4.3 (plancher : « un onglet désactivé reste lisible et dit pourquoi ») : motif `tablist` incomplet, onglet désactivé illisible
- **Où** : EXPERIENCE.md, « Onglets des primitives » et « Accessibilité » ; DESIGN.md (« un désactivé barré en `{colors.muted}` ») ; maquette : `disabled` et `title`, sans `tabpanel` ni flèches.
- **Problème** : un onglet `disabled` sort du focus ; sa raison n'existe qu'en `title`, peu lu. En clair, `muted` sur blanc donne 3,38:1 sur un texte de 11,5 px barré. Il manque `aria-controls`, `tabpanel`, la navigation ←/→ et le nom de la liste d'onglets.
- **Correctif** : EXPERIENCE.md : « `role="tablist"` nommé « Primitives du serveur », onglets à tabindex itinérant, ←/→ puis Début/Fin, activation automatique, `aria-controls` vers un `role="tabpanel"`. Un onglet indisponible reste focalisable avec `aria-disabled="true"`, et `aria-describedby` pointe vers la raison écrite sous les onglets ». DESIGN.md : texte `{colors.ink-soft}` (8,6:1), barré, précédé de « ⊘ », au lieu de `{colors.muted}`.

### A11Y-12 · moyenne · 1.3.1, 4.1.2, 4.1.3 : sélecteurs segmentés sans nom de groupe, segment indisponible muet
- **Où** : EXPERIENCE.md, « À la main | Par le modèle » (indisponible pour raisons) et « Documentation complète | Lazy loading » ; maquette : deux boutons `aria-pressed`, sans groupe.
- **Problème** : le lecteur d'écran entend deux boutons bascule sans savoir à quoi ils servent. Quand « Par le modèle » est indisponible, sa raison n'est pas rattachée au segment. Le passage en lazy loading change le total de tokens (« le chiffre baisse ») sans annonce.
- **Correctif** : `role="radiogroup"` nommé (« Qui choisit l'outil », « Documentation des outils envoyée »), segments en `role="radio"` / `aria-checked`, flèches pour naviguer. Segment indisponible en `aria-disabled="true"` avec `aria-describedby` vers sa raison. Le nouveau total passe dans la région `status` d'A11Y-03 (« Bloc outils : 64 tokens en lazy loading »).

### A11Y-13 · moyenne · 1.4.1, 1.4.11, 4.1.3 : « Suivre le direct » pressé ne se distingue que par une teinte, et la première annonce peut manquer
- **Où** : `pages.css`, `.diagram-step-live[aria-pressed="true"]` (lot 2) ; `diagram.js`, `update()` qui bascule `aria-live` de `off` à `polite` au moment même où le texte change.
- **Problème** : pressé ou non, le fond passe de `surface-raised` à `primary-soft`, soit 1,20:1 en clair et 1,15:1 en sombre : on ne voit pas si l'on est en direct. De plus, une région rendue live à l'instant de sa mise à jour n'est souvent pas annoncée par Chromium : le premier ◀ peut rester silencieux.
- **Correctif** : DESIGN.md, `diagram-stepper` : pressé = fond plein `{colors.primary}`, texte `{colors.on-primary}` (9,3:1 et 6,7:1, comme les segments) et un point « ● » devant le libellé. EXPERIENCE.md / lot 2 : un nœud `status` masqué visuellement, toujours `polite`, où l'on n'écrit qu'hors du direct, au lieu de basculer `aria-live`.

### A11Y-14 · moyenne · 1.4.11 : lignes de vie invisibles au vidéoprojecteur
- **Où** : DESIGN.md, `mcp-lifeline.stroke: {colors.line}` ; EXPERIENCE.md, « Lignes de vie et traits sont décoratifs ».
- **Problème** : 1,24:1 en clair, 1,48:1 en sombre. Elles sont masquées aux lecteurs d'écran, ce qui est juste, mais visuellement ce sont elles qui rattachent l'extrémité d'une flèche à sa colonne, une fois les en-têtes loin au-dessus. Le climax du Flow MCP-1 (« la colonne du SLM ne touche jamais celle du serveur ») se lit sur elles.
- **Correctif** : `mcp-lifeline.stroke: {colors.muted}`, tirets de 2 px (3,38:1 et 4,90:1). Les fantômes, horizontaux, restent distincts par leur direction et leur étiquette.

### A11Y-15 · moyenne · 1.4.11, 1.4.1 (plancher `stroke-min`) : traits trop fins, et tirets réseau et fantôme confondus
- **Où** : EXPERIENCE.md, tableau « Cinq sortes de flèches » (« fin, encre douce ») ; maquette : `.k-internal` 1,5 px, pointe ouverte de notification dessinée par un `drop-shadow` d'1 px ; DESIGN.md : réseau « en tirets » et fantôme « tirets `{colors.muted}` ».
- **Problème** : 1,5 px est sous le plancher de 2 px. La pointe ouverte, à 1 px, s'efface en visio. Entre une flèche réseau et une flèche fantôme, le trait ne diffère que par la couleur (encre ou gris) ; seules les étiquettes les séparent.
- **Correctif** : appel dans l'hôte en 2 px `{colors.ink-soft}`, sa finesse relative devenant la seule différence de couleur, doublée de l'italique et de l'absence de puce. Pointe ouverte tracée à 2 px. Motifs nommés dans DESIGN.md : réseau `6 5` (celui des fils), fantôme `3 6` à pointe ouverte grise ; aucun motif ne sert deux sortes.

### A11Y-16 · moyenne · 2.2.2, 2.3.3 : animations sans fin hors mouvement réduit, et liste du mouvement réduit incomplète
- **Où** : EXPERIENCE.md, « Stepper » (fil réseau mouvant tant qu'une flèche réseau est courante) et « Échange en cours » (antenne qui clignote) ; « Accessibilité » : « fil réseau fixe en tirets, antenne fixe ».
- **Problème** : en direct, la dernière flèche reste courante sans limite. Si elle est réseau, le fil s'anime indéfiniment ; l'antenne clignote 10 à 40 s. Sans `prefers-reduced-motion`, rien ne l'arrête : plus de 5 s de mouvement à côté du contenu (2.2.2). La liste du mouvement réduit oublie la rotation du chevron, un éventuel `scrollIntoView` fluide et les apparitions de lignes.
- **Correctif** : le fil ne bouge que pendant un échange en cours, et au plus 5 s après la dernière arrivée ; ensuite, tirets fixes. Avec `prefers-reduced-motion` : défilement `behavior: "auto"`, aucune transition (chevron, apparition, estompage), antenne et fil fixes.

### A11Y-17 · moyenne · 2.4.11 : une explication ouverte peut masquer l'élément suivant au focus
- **Où** : `diagram.js`, `explain()` (popover `auto`, fermé seulement par Échap ou un clic ailleurs) ; en-têtes de colonnes et blocs de l'Architecture ; maquette : popover rattaché à `body`, pas après son bloc.
- **Problème** : au clavier, après une explication ouverte sur « Client MCP », Tab mène à « Serveur MCP » ou aux flèches, que la bulle de 320 px peut couvrir. La maquette déplace aussi la bulle loin de son bloc dans l'ordre de lecture.
- **Correctif** : lot 2, `explain()` : fermer la bulle quand le focus quitte le bloc et n'entre pas dans la bulle. Garder la bulle juste après son bloc dans le DOM (comportement de `diagram.js`, pas celui de la maquette). EXPERIENCE.md, « Accessibilité » : le dire.

### A11Y-18 · moyenne · 1.3.1 : une seule liste mêle phases, explications, notes et flèches
- **Où** : EXPERIENCE.md, « La séquence est une liste ordonnée » ; maquette : en-têtes de phase, « Pourquoi », notes et flèches frères dans un seul `ol` ; notes et fantômes sans explication rendus en boutons désactivés.
- **Problème** : le lecteur annonce « liste de 23 éléments », numérotée avec des en-têtes et des explications. On ne peut pas sauter de phase en phase par les titres. Une note (« pas de resources/list… ») s'entend comme un « bouton indisponible ».
- **Correctif** : par phase, un `h3` (A11Y-05) suivi d'un `ol` des seules flèches. Notes et fantômes sans explication en `li` de texte, sans bouton : « ⓘ Note : … », « Fantôme : … ».

### A11Y-19 · moyenne · 2.4.1 / 2.1.1 (plancher : « une section = un arrêt de tabulation ») : des dizaines d'arrêts de tabulation dans la Séquence
- **Où** : EXPERIENCE.md, « Ordre de tabulation » ; chaque flèche est un bouton.
- **Problème** : une poignée de main, un appel par le modèle et une ressource font plus de 30 flèches. Pour atteindre « Ce que le modèle voit » ou l'Architecture, il faut autant de Tab.
- **Correctif** : liste des flèches en tabindex itinérant : un seul arrêt ; ↑/↓ d'une flèche à l'autre, Début/Fin, Entrée ou Espace pour déplier. À l'entrée dans la liste, le focus va à la flèche courante. Les boutons d'en-tête de phase restent des arrêts propres. Le JSON défilant de l'encart devient une région nommée et focalisable (`role="region"`, `aria-label` « JSON du message tools/call », `tabindex="0"`).

### A11Y-20 · moyenne · 2.4.3 : boutons désactivés sous le focus pendant un échange
- **Où** : EXPERIENCE.md, « Boutons… désactivés hors `idle` » et « boutons désactivés (`mcp_lab`) ».
- **Problème** : dans Chromium, un bouton qui reçoit `disabled` pendant qu'il a le focus (« Se connecter », « Appeler », « Envoyer au modèle ») le perd au profit de `body` : le Tab suivant repart du haut de la page.
- **Correctif** : pendant un échange, `aria-disabled="true"` et activation ignorée, plutôt que `disabled`. `aria-describedby` vers le bandeau de raison. Le focus reste en place.

### A11Y-21 · moyenne · 1.4.4, 1.4.10 (partiel) : légendes tronquées
- **Où** : maquette, `.seq-cap .txt` (`white-space: nowrap; text-overflow: ellipsis`) ; EXPERIENCE.md, « Langues » ne protège que les en-têtes de colonnes.
- **Problème** : « formulaire : define_term(term = « MCP ») », « choisit le prompt explain_term(term = « hook ») » et leurs versions allemandes se tronquent sur une flèche courte, plus encore à ×9/7. Pour un voyant, le texte n'est complet nulle part.
- **Correctif** : EXPERIENCE.md, « Langues » : « une légende de flèche passe sur deux lignes et la ligne grandit ; jamais d'ellipse ». L'en-tête de l'encart reprend la légende entière.

## Basses

### A11Y-22 · basse · 1.3.1, 4.1.2 : cartes de serveurs
- **Où** : EXPERIENCE.md, « Adresse ou commande de lancement… au clic sur le nom » ; maquette : nom dans le `label` du bouton radio.
- **Problème** : un nom cliquable dans le `label` sélectionne le serveur et ouvre son détail du même geste (interactif imbriqué). Le groupe de boutons radio n'a pas de nom.
- **Correctif** : `fieldset` et `legend` « Serveur » ; le détail derrière un bouton « ⓘ » de 32 px, hors du `label`, en `aria-expanded`.

### A11Y-23 · basse · 4.1.2 : dépliages sans état
- **Où** : « Voir le JSON envoyé au modèle » (maquette : sans `aria-expanded`).
- **Correctif** : `aria-expanded` et `aria-controls` sur tout bouton qui déplie (« Voir le JSON », « Pourquoi… ? », en-têtes d'encarts).

### A11Y-24 · basse · 3.1.2 : langue des méthodes et du JSON
- **Où** : puces de méthode, JSON, URI.
- **Problème** : « tools/list » ou « notifications/initialized » sont lus avec la phonétique française (ou allemande).
- **Correctif** : `lang="en"` sur les puces de méthode en `code` et sur les `pre` de JSON ; `html[lang]` suit la langue de l'interface.

### A11Y-25 · basse · 1.1.1 : émojis porteurs de sens
- **Où** : « 🌐 » sur les puces et les en-têtes, « 🔧 📄 💬 » des onglets et des primitives, « 🔌 » des serveurs.
- **Problème** : lus « globe avec méridiens », « clé », « prise » : le sens (réseau, outil, ressource, prompt) n'est pas dit.
- **Correctif** : émojis en `aria-hidden="true"`, un texte masqué visuellement à leur place (« réseau », « outils », « ressources », « prompts »), libellés dans `ui.yaml`.

### A11Y-26 · basse · 4.1.2 (plancher « Volets masqués ») : boutons « — » et ⛶ de la maquette
- **Où** : maquette, `.icon-btn` nommés par leur seul contenu (« — », « ⛶ »), le `title` n'étant qu'une description.
- **Correctif** : rappeler dans EXPERIENCE.md, « Découpe en quatre volets », que le plancher s'applique : « Masquer le volet {Nom} », « Mode focus du volet {Nom} », « Réafficher le volet {Nom} ».
