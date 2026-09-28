---
title: DESIGN — WaveStack
status: draft
created: 2026-09-22
updated: 2026-09-28
sources:
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/addendum.md
name: WaveStack
description: Démonstrateur pédagogique local de harnais agentique, à la charte Wavestone, dans une direction « atelier de construction » pensée pour la projection. Thème clair uniquement en V1.
colors:
  # Charte Wavestone
  primary: '#451DC7'
  primary-deep: '#250F6B'
  primary-soft: '#EDE7FE'
  accent: '#04F06A'
  accent-soft: '#CAFEE0'
  ink: '#0A0A14'
  ink-soft: '#4A4A5E'
  muted: '#8A8A9E'
  line: '#E6E6EC'
  surface: '#F6F5FA'
  surface-raised: '#FFFFFF'
  warning: '#FFCA4A'
  danger: '#FF2A49'
  on-primary: '#FFFFFF'
  # Relief et fond à pois (teintes du violet de charte, sans autre usage)
  relief: '#D9D0F6'
  relief-active: '#C9BCF5'
  dot: '#D6CCF5'
  # Codage local / réseau (lieu d'hébergement)
  hosting-local: '#451DC7'
  hosting-network: '#FFCA4A'
  hosting-boundary: '#0A0A14'
  # Couleurs d'état
  state-active: '#04F06A'
  state-ok: '#04F06A'
  state-blocked: '#FF2A49'
  state-error: '#FF2A49'
  state-unavailable: '#8A8A9E'
  # Palette catégorielle des segments de contexte (ordre d'empilement)
  segment-system-prompt: '#6B4EE6'
  segment-global-memory: '#27B060'
  segment-tool-descriptions: '#2A78D6'
  segment-history: '#B39CF7'
  segment-rag: '#0E8C7E'
  segment-tool-results: '#E0762B'
  segment-message: '#9C5BB5'
  segment-free: '#F6F5FA'
typography:
  # Base à 100 % ; les paliers 125 % et 150 % (NFR-9) multiplient toutes les tailles.
  pane-title:
    fontFamily: 'Fredoka, system-ui, sans-serif'
    fontSize: 19px
    fontWeight: '600'
    lineHeight: '1.15'
  pane-subtitle:
    fontFamily: "'Atkinson Hyperlegible', system-ui, sans-serif"
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.3'
  heading:
    fontFamily: 'Fredoka, system-ui, sans-serif'
    fontSize: 18px
    fontWeight: '600'
    lineHeight: '1.3'
  chat:
    fontFamily: "'Atkinson Hyperlegible', system-ui, sans-serif"
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  body:
    fontFamily: "'Atkinson Hyperlegible', system-ui, sans-serif"
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  body-sm:
    fontFamily: "'Atkinson Hyperlegible', system-ui, sans-serif"
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.4'
  label:
    fontFamily: 'Fredoka, system-ui, sans-serif'
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.2'
  number:
    fontFamily: 'Fredoka, system-ui, sans-serif'
    fontSize: 14px
    fontWeight: '600'
    lineHeight: '1.2'
  number-lg:
    fontFamily: 'Fredoka, system-ui, sans-serif'
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.1'
  code:
    fontFamily: "'JetBrains Mono', 'Cascadia Mono', Consolas, ui-monospace, monospace"
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.5'
rounded:
  sm: 12px
  md: 18px
  lg: 26px
  full: 9999px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '5': 24px
  '6': 32px
  gutter: 8px
  pane-padding: 12px
  top-bar-height: 48px
  brick-panel-width: 280px
  architecture-band-height: 250px
  stroke-min: 2px
  hit-target-min: 32px
  relief-offset: 4px
  relief-offset-pressed: 1px
  relief-offset-overlay: 6px
  dot-grid: 18px
components:
  page:
    background: '{colors.surface}'
    dot: '{colors.dot}'
    dot-grid: '{spacing.dot-grid}'
  top-bar:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    shadow: '{colors.relief}'
    radius: '{rounded.lg}'
    height: '{spacing.top-bar-height}'
  pane:
    background: '{colors.surface-raised}'
    shadow: '{colors.relief}'
    radius: '{rounded.lg}'
    padding: '{spacing.pane-padding}'
    title-typography: '{typography.pane-title}'
    title-color: '{colors.ink}'
    subtitle-typography: '{typography.pane-subtitle}'
    subtitle-color: '{colors.ink-soft}'
  pane-focused:
    border: '{colors.primary}'
  button-primary:
    background: '{colors.primary}'
    foreground: '{colors.on-primary}'
    shadow: '{colors.primary-deep}'
    radius: '{rounded.md}'
    min-height: '{spacing.hit-target-min}'
  button-secondary:
    background: '{colors.surface-raised}'
    foreground: '{colors.primary}'
    border: '{colors.primary}'
    shadow: '{colors.relief-active}'
    radius: '{rounded.md}'
    min-height: '{spacing.hit-target-min}'
  reset-button:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.md}'
  # Story 22: an erasing button (« Tout effacer »), flat; white on danger fails 4.5:1, ink passes.
  button-danger:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.danger}'
    border-width: '{spacing.stroke-min}'
    radius: '{rounded.md}'
    min-height: '{spacing.hit-target-min}'
    confirmed-background: '{colors.danger}'
    confirmed-foreground: '{colors.ink}'
  scenario-picker:
    background: '{colors.primary-soft}'
    foreground: '{colors.primary-deep}'
    radius: '{rounded.full}'
  model-picker:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.md}'
  text-size-control:
    background: '{colors.surface}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    typography: '{typography.number}'
    radius: '{rounded.full}'
  pane-hide-button:
    foreground: '{colors.ink-soft}'
    border: '{colors.line}'
    radius: '{rounded.sm}'
    min-size: '{spacing.hit-target-min}'
  pane-chip:
    background: '{colors.primary-soft}'
    foreground: '{colors.primary}'
    border: '{colors.primary}'
    border-style: dashed
    radius: '{rounded.full}'
    typography: '{typography.label}'
    match-marker: '{colors.ink}'
  pane-menu:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    shadow: '{colors.relief}'
    radius: '{rounded.md}'
  context-gauge:
    track: '{colors.segment-free}'
    border: '{colors.line}'
    radius: '{rounded.full}'
    label-typography: '{typography.number}'
    near-limit-marker: '{colors.ink}'
    overflow-color: '{colors.danger}'
  context-gauge-detail:
    background: '{colors.surface-raised}'
    cell-free: '{colors.segment-free}'
    cell-border: '{colors.line}'
    legend-typography: '{typography.body-sm}'
    number-typography: '{typography.number}'
    radius: '{rounded.lg}'
  context-segment:
    radius: '{rounded.md}'
    label-color: '{colors.ink}'
    label-typography: '{typography.label}'
    body-typography: '{typography.code}'
    selected-outline: '{colors.ink}'
  brick-card:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    shadow: '{colors.relief}'
    radius: '{rounded.md}'
    active-border: '{colors.primary}'
    active-background: '{colors.primary-soft}'
    active-shadow: '{colors.relief-active}'
    unavailable-foreground: '{colors.muted}'
    reason-color: '{colors.ink-soft}'
  brick-toggle:
    on: '{colors.primary}'
    off: '{colors.line}'
    parent-off: '{colors.muted}'
    radius: '{rounded.full}'
  category-chip:
    background: '{colors.primary-soft}'
    foreground: '{colors.primary-deep}'
    radius: '{rounded.full}'
    typography: '{typography.label}'
  hosting-tag-local:
    background: '{colors.hosting-local}'
    foreground: '{colors.on-primary}'
    border-style: solid
    radius: '{rounded.full}'
  hosting-tag-network:
    background: '{colors.hosting-network}'
    foreground: '{colors.ink}'
    border: '{colors.ink}'
    border-style: dashed
    radius: '{rounded.full}'
  edit-drawer:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    shadow: '{colors.relief}'
    radius: '{rounded.lg}'
  chat-message-user:
    background: '{colors.primary-soft}'
    foreground: '{colors.ink}'
    radius: '{rounded.lg}'
    typography: '{typography.chat}'
  chat-message-model:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.lg}'
    typography: '{typography.chat}'
  reasoning-block:
    background: '{colors.surface}'
    foreground: '{colors.ink-soft}'
    radius: '{rounded.sm}'
    typography: '{typography.body-sm}'
  composer:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    focus-border: '{colors.primary}'
    radius: '{rounded.full}'
    typography: '{typography.chat}'
  suggested-prompt-chip:
    background: '{colors.surface-raised}'
    foreground: '{colors.primary}'
    border: '{colors.primary}'
    radius: '{rounded.full}'
  working-indicator:
    dot: '{colors.state-active}'
    foreground: '{colors.ink-soft}'
    typography: '{typography.body-sm}'
  turn-rail:
    background: '{colors.surface}'
    line: '{colors.line}'
  turn-step:
    foreground: '{colors.ink}'
    radius: '{rounded.sm}'
    current-marker: '{colors.state-active}'
    selected-background: '{colors.primary-soft}'
  token-counter:
    foreground: '{colors.ink}'
    typography: '{typography.number}'
  trigger-badge-model:
    background: '{colors.primary-soft}'
    foreground: '{colors.primary-deep}'
    radius: '{rounded.full}'
    typography: '{typography.label}'
  trigger-badge-user:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.ink}'
    radius: '{rounded.full}'
    typography: '{typography.label}'
  force-button:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.ink}'
    radius: '{rounded.sm}'
  harness-event:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    radius: '{rounded.md}'
    blocked-accent: '{colors.state-blocked}'
    error-accent: '{colors.state-error}'
    info-accent: '{colors.primary}'
  overflow-card:
    background: '{colors.surface-raised}'
    border: '{colors.state-error}'
    border-width: '{spacing.stroke-min}'
    title-typography: '{typography.heading}'
    section-typography: '{typography.label}'
    radius: '{rounded.md}'
  outbound-payload:
    background: '{colors.surface-raised}'
    border: '{colors.hosting-boundary}'
    border-style: dashed
    header-background: '{colors.hosting-network}'
    header-foreground: '{colors.ink}'
    body-typography: '{typography.code}'
    radius: '{rounded.md}'
  turn-compare:
    background: '{colors.surface-raised}'
    diff-increase: '{colors.ink}'
    diff-decrease: '{colors.ink}'
    radius: '{rounded.md}'
  arch-zone-local:
    background: '{colors.surface-raised}'
    label-color: '{colors.primary}'
    radius: '{rounded.lg}'
  arch-zone-network:
    background: '{colors.surface}'
    label-color: '{colors.ink}'
    radius: '{rounded.lg}'
  arch-harness:
    background: '{colors.surface-raised}'
    border: '{colors.primary}'
    border-width: '{spacing.stroke-min}'
    shadow: '{colors.relief-active}'
    label-background: '{colors.primary}'
    label-foreground: '{colors.on-primary}'
    label-typography: '{typography.label}'
    brick-background: '{colors.primary-soft}'
    brick-foreground: '{colors.primary-deep}'
    radius: '{rounded.lg}'
  arch-model:
    body: '{colors.primary}'
    ears: '{colors.primary-deep}'
    visor: '{colors.surface-raised}'
    face: '{colors.ink}'
    antenna-idle: '{colors.muted}'
    antenna-active: '{colors.state-active}'
    tool-badge: '{colors.state-active}'
    label-typography: '{typography.label}'
  arch-boundary:
    stroke: '{colors.hosting-boundary}'
    stroke-width: '{spacing.stroke-min}'
  arch-node-local:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.hosting-local}'
    border-style: solid
    radius: '{rounded.sm}'
  arch-node-network:
    background: '{colors.hosting-network}'
    foreground: '{colors.ink}'
    border: '{colors.ink}'
    border-style: dashed
    radius: '{rounded.sm}'
  arch-node-unavailable:
    background: '{colors.surface}'
    foreground: '{colors.ink-soft}'
    border: '{colors.muted}'
    border-style: dashed
    radius: '{rounded.sm}'
  arch-node-active:
    halo: '{colors.state-active}'
  arch-flow:
    stroke: '{colors.ink-soft}'
    stroke-width: '{spacing.stroke-min}'
    active-stroke: '{colors.state-active}'
  diagnostic-row:
    background: '{colors.surface-raised}'
    ok-badge: '{colors.state-ok}'
    error-badge: '{colors.state-error}'
    badge-foreground: '{colors.ink}'
    radius: '{rounded.sm}'
---

# WaveStack — Design Spine

## Brand & Style

WaveStack est un tableau de démonstration, pas une vitrine. Il vit dans une salle de formation, projeté sur un écran qu'on ne choisit pas, ou sur l'écran d'un EliteBook tourné vers trois personnes. Son esthétique sert une seule chose : que la salle voie ce que le harnais fait au modèle.

**Direction « atelier de construction ».** Le harnais se construit brique par brique autour du modèle ; l'interface le dit par sa forme. Elle ressemble à un jeu de construction posé sur un cahier : pièces aux grands arrondis, relief de jouet par une ombre pleine, fond de page à pois. Le modèle est un petit robot, et le harnais, tout ce qu'on branche autour de lui. Chaque volet porte sous son titre une phrase qui dit ce qu'il montre (« Ce que le modèle lit »). Le ton est ludique, mais l'écran reste un outil : le jeu sert la lecture en projection, jamais l'inverse. Référence : maquette canvas « WaveStack, refonte ludique » ([planches Écran principal et Planche de style](https://claude.ai/artifact/7fM7Cy2UiEnPXiNGvtX7Sq)). Cette spine l'emporte sur la maquette en cas d'écart, notamment sur les couleurs (voir Colors).

L'identité reste celle de la charte Wavestone : violet ancre, vert en unique accent secondaire, crème, encre. L'information est dense mais rangée. Les couleurs vives ont chacune un rôle précis : violet = local et marque, jaune = réseau, vert = « en train d'agir » et « OK », rouge = « bloqué / en échec ». Le fond à pois est la seule ornementation, et il reste derrière les volets.

Les composants vitrine de la charte (curseur personnalisé, révélations au scroll, compteurs animés) ne s'appliquent pas : une application qui s'anime pour elle-même vole l'attention que la démonstration doit capter.

Thème clair uniquement en V1 `[ASSUMPTION]` : plus robuste en projection dans une salle éclairée. Pas de tokens sombres.

## Colors

**Charte Wavestone.**
- **Violet (`#451DC7`)** : couleur ancre. Boutons primaires, brique active, et couleur du lieu d'hébergement local. Contraste 9,3:1 sur blanc.
- **Violet foncé (`#250F6B`)** : texte sur fonds violet doux (puces de catégorie, badge « déclenché par le modèle »).
- **Violet doux (`#EDE7FE`)** : fond de brique active, de message utilisateur, d'étape sélectionnée.
- **Vert (`#04F06A`)** : seul accent secondaire. Réservé à « composant en cours d'action » (halo, flux animé, étape courante) et à « diagnostic OK ». Contraste 1,5:1 sur blanc : jamais en texte ni en trait fin isolé, toujours en fond ou halo avec texte encre (12,8:1).
- **Vert clair (`#CAFEE0`)** : réserve de la charte, sans usage assigné en V1.
- **Encre (`#0A0A14`)**, **encre douce (`#4A4A5E`)** : texte principal et secondaire. **Gris (`#8A8A9E`)** : 3,4:1, donc réservé à l'état indisponible et aux éléments non textuels ; jamais pour un texte à lire.
- **Ligne (`#E6E6EC`)**, **crème (`#F6F5FA`)**, **blanc (`#FFFFFF`)** : séparateurs, fond de page, fond des volets. Le blanc n'est pas listé dans la charte relevée au memlog `[ASSUMPTION]`.
- **Relief (`#D9D0F6`)**, **relief actif (`#C9BCF5`)**, **pois (`#D6CCF5`)** : trois teintes du violet de charte, ajoutées pour la direction « atelier de construction ». Elles ne servent qu'à l'ombre pleine (`{colors.relief}` sous volets et cartes, `{colors.relief-active}` sous pièces actives et bouton secondaire) et aux pois du fond de page (`{colors.dot}`). Jamais en texte, en fond de contenu ni en trait porteur de sens.

La maquette de référence teinte aussi les neutres en lilas (encre `#1C1535`, encre douce `#4E4868`, violet doux `#EAE3FF`, page `#EFEBFB`, ligne `#E4DEF5`, violet clair `#8E73F0` dans le logo). Ces écarts ne sont pas repris : les tokens de charte ci-dessus s'appliquent.
- **Jaune (`#FFCA4A`)** et **rouge (`#FF2A49`)** : avec parcimonie, chacun avec une seule signification (ci-dessous).

**Codage local / réseau** `[ASSUMPTION]`. Il porte le message sur la souveraineté (FR-3, SM-3) et doit se lire en une seconde, projeté.
- Local = `{colors.hosting-local}` plein, trait continu.
- Réseau = `{colors.hosting-network}` en fond, bordure en tirets couleur encre, icône globe, libellé « RÉSEAU ». Le jaune seul sur blanc n'a pas assez de contraste (1,5:1) : la bordure en tirets est donc tracée en `{colors.ink}`, le texte est en encre sur jaune (12,9:1).
- La frontière Poste de travail / Réseau est un trait `{colors.hosting-boundary}` de `{spacing.stroke-min}`.
- Le jaune ne sert **qu'au** réseau. Il n'est pas utilisé comme couleur d'avertissement, pour que « jaune » veuille toujours dire « ça sort du poste ».

**Couleurs d'état** `[ASSUMPTION]`.
- `{colors.state-active}` (vert) : composant en cours d'action, étape courante, diagnostic OK.
- `{colors.state-blocked}` / `{colors.state-error}` (rouge) : blocage par un hook, échec de parsing, dépassement du contexte, diagnostic en échec. Rouge sur blanc = 3,7:1 : utilisé en fond de pastille avec texte encre (5,3:1), en filet latéral épais ou en icône, jamais en petit texte.
- `{colors.state-unavailable}` (gris) : brique, outil ou serveur indisponible, toujours accompagné de la raison en `{colors.ink-soft}`.
- Toujours avec icône et libellé. Jamais la couleur seule.

**Palette catégorielle des segments de contexte** `[ASSUMPTION]`, validée en mode clair (`validate_palette.js`), dans l'ordre d'empilement de la jauge (FR-41) :

| Token | Segment | Hex |
|---|---|---|
| `segment-system-prompt` | prompt système | `#6B4EE6` |
| `segment-global-memory` | mémoire globale | `#27B060` |
| `segment-tool-descriptions` | descriptions d'outils, de serveurs MCP et de skills | `#2A78D6` |
| `segment-history` | historique | `#B39CF7` |
| `segment-rag` | extraits RAG | `#0E8C7E` |
| `segment-tool-results` | résultats d'outils | `#E0762B` |
| `segment-message` | message et gabarit (message courant + gabarit de conversation du modèle ; seul segment présent en LLM nu, FR-8) | `#9C5BB5` |
| `segment-free` | espace libre (crème hachuré) | `#F6F5FA` |

Validation (`validate_palette.js`, mode clair) : les paires de segments **voisins** dans l'empilement passent, y compris le nouveau segment « Message et gabarit » à côté des résultats d'outils. Le contrôle sur **toutes** les paires échoue déjà entre prompt système (`#6B4EE6`) et descriptions d'outils (`#2A78D6`) ; c'est acceptable pour une barre empilée, où ces deux segments ne se touchent jamais, à condition que les étiquettes directes et la légende restent obligatoires. Avertissement de contraste sur `#27B060` et `#B39CF7` (faibles sur blanc) : même règle. Les étiquettes de segment sont posées **hors** du segment, en encre, avec une pastille de couleur ; le blanc sur `#2A78D6` (4,4:1) et `#0E8C7E` (4,1:1) ne passe pas pour du petit texte, et l'encre sur `#9C5BB5` non plus (4,3:1).

À éviter : dégradés, fonds colorés derrière du texte courant, toute couleur hors de cette liste, et toute réutilisation d'une couleur de segment pour autre chose que son segment.

## Typography

- **Fredoka** (graisses 500 et 600) : titres de volet (`pane-title`), titres (`heading`), étiquettes (`label`) et nombres (`number`, `number-lg`). Ses formes rondes portent le ton « jeu de construction ». Chiffres tabulaires (`font-variant-numeric: tabular-nums`) pour que les compteurs de tokens ne sautent pas pendant la mise à jour. `[ASSUMPTION]` Le fichier servi doit contenir la fonction OpenType `tnum` ; sinon, chaque compteur reçoit une largeur fixe.
- **Atkinson Hyperlegible** (400 et 700) : voix de l'interface, messages, explications, sous-titres de volet. Dessinée pour les lecteurs malvoyants : chaque lettre se distingue, même projetée au fond d'une salle.
- **JetBrains Mono** (400, repli Cascadia Mono puis Consolas) : contenu brut du contexte et des sorties du modèle, en `{typography.code}`.
- Les trois familles sont sous licence OFL et servies en local depuis l'application (fichiers WOFF2 et `@font-face`) : aucune requête vers un service de polices (NFR-3, NFR-4). La maquette de référence les charge depuis Google Fonts ; l'application, non.

Rampe à 100 % : `pane-title` 19 px, `heading` 18 px, `chat` 16 px, `body` 14 px, `pane-subtitle`, `body-sm` et `code` 13 px, `label` 12 px, `number` 14 px, `number-lg` 20 px. Les paliers 125 % et 150 % (NFR-9), choisis par le contrôle unique « Aa 100 % », multiplient toute la rampe ; aucun texte ne descend sous 12 px au palier 100 %. `[ASSUMPTION]` Rampe dimensionnée pour la fenêtre utile de 1280×650.

Titres de volet en casse normale, en `{colors.ink}`, suivis d'un sous-titre pédagogique d'une ligne en `pane-subtitle`, `{colors.ink-soft}`. Pas de tailles « display » : l'écran appartient au contenu de la démonstration.

## Layout & Spacing

Échelle de 4 px (`{spacing.1}` à `{spacing.6}`). Les volets sont séparés par une gouttière étroite (`{spacing.gutter}`) et ont un rembourrage de `{spacing.pane-padding}` : la densité prime, car tout doit tenir dans 1280×650.

Grille retenue : 5 volets masquables (référence : [`.working/layout-5-volets-v2.html`](.working/layout-5-volets-v2.html)) :
- barre haute de `{spacing.top-bar-height}` sur toute la largeur ;
- colonne de gauche sur toute la hauteur : panneau des briques (`{spacing.brick-panel-width}`) ;
- à droite, rangée du haut : vue humain, Contexte LLM, Orchestration ; Contexte LLM et Orchestration se partagent à parts égales la largeur restante ;
- à droite, bande basse sous ces trois volets : schéma d'architecture, `{spacing.architecture-band-height}`. `[ASSUMPTION]` Ce token vaut 250 px depuis la story 8e (bacs par catégorie et bande des hooks), au lieu de 200 px, dans ce fichier comme dans `tokens.css`. À 1280×650, la rangée du haut perd 50 px ; si c'est trop juste, le formateur masque un volet, passe le schéma en mode focus ou redimensionne les volets.

Un volet masqué libère sa place : les volets visibles de la même rangée se la partagent ; si le panneau des briques est masqué, les autres volets prennent toute la largeur ; si le schéma est masqué, la rangée du haut prend toute la hauteur. Les gouttières sont aussi des poignées de redimensionnement (`pane-resize-handle`, voir Components). Le mode focus redistribue la grille sans changer l'ordre des volets (voir EXPERIENCE.md). Le comportement par taille d'écran est dans EXPERIENCE.md, section Responsive & Platform.

Fond de page (`page`) : `{colors.surface}` semé de pois `{colors.dot}` de 1,3 px sur une grille de `{spacing.dot-grid}`, comme un papier de cahier. Les pois restent dans les gouttières et autour des volets ; aucun volet, aucune carte n'en porte.

`[ASSUMPTION]` L'en-tête de volet grandit (titre de 19 px et sous-titre) : le budget vertical dans 1280×650 est à vérifier à l'implémentation, les tokens d'espacement restant inchangés. Si la place manque, le sous-titre est le premier élément à masquer au palier 150 %, pas le contenu.

## Elevation & Depth

**Relief de jouet.** Les pièces posées sur la page ont du volume, donné par une ombre **pleine, sans flou**, décalée vers le bas : `box-shadow: 0 {spacing.relief-offset} 0 <couleur>`. Une ombre floue disparaît au vidéoprojecteur et bave en visio ; une ombre pleine reste nette, comme l'arête d'une brique de jeu.

| Pièce | Décalage | Couleur |
|---|---|---|
| Barre haute, volets, cartes de brique | `{spacing.relief-offset}` (4 px) | `{colors.relief}` |
| Carte de brique active, bouton secondaire, cadre du harnais | `{spacing.relief-offset}` | `{colors.relief-active}` |
| Bouton primaire | `{spacing.relief-offset}` | `{colors.primary-deep}` |
| Bouton enfoncé (au clic) | `{spacing.relief-offset-pressed}` (1 px), le bouton descend d'autant | inchangée |
| Tiroir d'édition, menus déroulants | `{spacing.relief-offset-overlay}` (6 px) `[ASSUMPTION]` | `{colors.relief}` |

Sans relief : éléments indisponibles (ils sont « posés à plat »), bouton Réinitialiser (neutre, pour ne pas attirer le clic), boutons danger et actions d'une entrée de la mémoire globale, contenu à l'intérieur d'un volet (messages, segments, étapes), qui se distingue par le ton et la bordure `{colors.line}`.

Le relief ne hiérarchise pas l'information : tous les volets ont le même. Le halo vert du composant en cours d'action (`arch-node-active`) n'est pas une ombre mais un signal d'état.

## Shapes

Grands arrondis, sur une échelle de trois rayons et la pilule :

- `{rounded.lg}` (26 px) : volets, barre haute, zones du schéma, cadre du harnais, tiroir d'édition, détail de la jauge, bulles de message.
- `{rounded.md}` (18 px) : cartes de brique, boutons texte, sélecteur de modèle, segments de contexte, événements du harnais, cartes de dépassement et de données sortantes.
- `{rounded.sm}` (12 px) : boutons icônes (focus, masquer), tuiles d'icône, nœuds du schéma, étapes, bloc de raisonnement.
- `{rounded.full}` : jauge, badges, puces, interrupteurs, sélecteur de scénario, réglage de taille de texte, champ de saisie et bouton d'envoi.

Les bulles de message ont un coin de 6 px du côté du locuteur (bas droit pour l'utilisateur, bas gauche pour le modèle), pour se lire comme une conversation.

Le robot du modèle (`arch-model`) est dessiné avec les mêmes arrondis : corps et visière en rectangles très arrondis, oreilles et antenne en pilules. Pas d'angle vif dans le schéma.

Les nœuds réseau gardent le même rayon que les nœuds locaux : seule la bordure (continue ou en tirets) et la couleur changent, pour que la comparaison porte sur le lieu d'hébergement et rien d'autre.

## Components

Noms de composants identiques dans EXPERIENCE.md, section Component Patterns.

- **Fond de page (`page`)** : crème à pois, voir Layout & Spacing.
- **Barre haute (`top-bar`)** : carte blanche flottante, rayon `{rounded.lg}`, relief `{colors.relief}`. De gauche à droite : sélecteur de scénario, jauge de contexte (élément le plus large), puces des volets masqués et menu « Volets ▾ », sélecteur de modèle, réglage de taille de texte, bouton Réinitialiser.
- **Volet (`pane`)** : carte blanche sans bordure, rayon `{rounded.lg}`, relief `{colors.relief}`. En haut à gauche, titre `pane-title` en encre et, dessous, sous-titre pédagogique `pane-subtitle` en encre douce, qui dit en quatre ou cinq mots ce que le volet montre :

  | Volet | Sous-titre |
  |---|---|
  | Briques | Branchez des pièces sur le modèle |
  | Vue humain | Ce que vous voyez |
  | Contexte LLM | Ce que le modèle lit |
  | Orchestration | Ce que fait le harnais |
  | Schéma d'architecture | Où chaque pièce tourne |

  En haut à droite, bouton ⛶ (mode focus) puis bouton « — » (`pane-hide-button`, masquer). Volet en mode focus : bordure `{colors.primary}`.
- **Puce de volet masqué (`pane-chip`)** : « + Nom du volet » sur violet doux, bordure en tirets violette. Quand le volet masqué contient un élément correspondant à la sélection, la puce porte un point encre et le libellé « lié ».
- **Menu Volets (`pane-menu`)** : bouton « Volets ▾ » ; liste déroulante des cinq volets avec case à cocher chacun.
- **Poignée de gouttière (`pane-resize-handle`)** : invisible au repos (on voit les pois de la page). Au survol ou au focus, une pilule violette de 4 × 32 px apparaît au milieu de la gouttière, avec le curseur ↔ ou ↕. Pendant le glissement, la pilule reste visible. La zone de saisie fait au moins `{spacing.hit-target-min}`, même si la gouttière visible reste à `{spacing.gutter}`.
- **Boutons (`button-primary`, `button-secondary`, `reset-button`, `button-danger`)** : primaire violet plein sur relief violet foncé, qui s'enfonce au clic (relief de 4 px à 1 px) ; secondaire contour violet sur relief actif ; Réinitialiser neutre et sans relief, pour ne pas attirer le clic par erreur. Danger (« Tout effacer » de la mémoire globale) : fond blanc, bordure `{colors.danger}` de `{spacing.stroke-min}`, texte encre, sans relief ; sa confirmation (« Oui, tout effacer ») est pleine, fond `{colors.danger}` et texte encre (≈ 5,4:1 ; le blanc sur ce rouge ne tient pas 4,5:1). Libellés en `label` Fredoka. Hauteur minimale `{spacing.hit-target-min}`.
- **Sélecteur de scénario (`scenario-picker`)** : pastille violet doux avec le nom du module et du scénario en cours.
- **Sélecteur de modèle (`model-picker`)** : liste déroulante neutre, nom du modèle et taille (ex. « 2B »).
- **Réglage de taille de texte (`text-size-control`)** : contrôle unique « Aa 100 % », pastille neutre ; le nombre affiche le palier courant (100, 125 ou 150 %).
- **Jauge de contexte (`context-gauge`)** : barre horizontale empilée, rayons pleins, segments dans l'ordre de la palette catégorielle, espace libre en crème hachuré. À droite : `number` « 1 840 / 4 096 tokens · 45 % ». Un marqueur vertical en encre indique le seuil d'alerte. Au dépassement, le pourcentage passe sur pastille rouge avec icône.
- **Détail de la jauge (`context-gauge-detail`)** : grille de cellules à la manière de `/context`, une cellule par tranche de tokens, colorée selon la palette catégorielle, cellules libres en crème hachuré. Légende à droite : pastille, nom du segment, tokens et pourcentage en `number`.
- **Segment de contexte (`context-segment`)** : bloc de texte brut en `{typography.code}`, filet latéral gauche de 4 px dans la couleur du segment, étiquette `label` en encre avec pastille de couleur et nombre de tokens. Segment sélectionné : contour encre de 2 px.
- **Carte de brique (`brick-card`)** : nom, interrupteur (`brick-toggle`), puce de catégorie (`category-chip` : « prompt engineering », « context engineering », « harness engineering »), étiquette de lieu d'hébergement (`hosting-tag-local` ou `hosting-tag-network`), explication dépliable. Relief `{colors.relief}`. Active : fond violet doux, bordure violette, relief `{colors.relief-active}`. Indisponible : posée à plat (sans relief), bordure en tirets, texte gris, interrupteur désactivé, raison toujours visible en `{colors.ink-soft}`. Sous-option d'une brique éteinte ou indisponible : interrupteur désactivé, coché en `{colors.muted}` au lieu du violet (`brick-toggle.parent-off`), libellé et résumé en `{colors.ink-soft}`.
- **Tiroir d'édition (`edit-drawer`)** : panneau qui glisse par-dessus le panneau des briques pour éditer le prompt système ou la mémoire globale ; champ en `{typography.code}`. Confirmation d'enregistrement en `body-sm` encre, précédée de « ✓ ». Mémoire globale : en-tête (titre, croix « × » en bouton icône `{rounded.sm}` bordé `{colors.line}`), liste défilante, pied fixe séparé par un filet `{colors.line}` avec « Tout effacer » (`button-danger`) et « Fermer » (`button-secondary`) ; « Enregistrer » et « Supprimer » d'une entrée en actions compactes à plat, fond crème, bordure `{colors.line}`, `{rounded.sm}`.
- **Messages (`chat-message-user`, `chat-message-model`)** : bulles `{rounded.lg}` à coin de 6 px côté locuteur ; utilisateur sur violet doux, modèle sur blanc bordé. Typographie `chat`. Bloc de raisonnement (`reasoning-block`) replié sur crème, en `body-sm`.
- **Champ de saisie (`composer`)** : pilule en `chat`, bordure `{colors.line}`, `{colors.primary}` au focus ; bouton d'envoi primaire rond à droite.
- **Prompt suggéré (`suggested-prompt-chip`)** : puce contour violet au-dessus du champ de saisie.
- **Consigne du scénario (`scenario-guide`)** : `body-sm` encre douce, titre en violet foncé, coupée à 3 lignes ; « Afficher plus » / « Réduire » en lien souligné violet, `label`.
- **Onglets de Contexte LLM** (sous-agent) : libellés `label` sur un filet `{colors.line}` de 2 px ; onglet sélectionné en encre, souligné de 3 px `{colors.primary}`, les autres en encre douce.
- **Indicateur de travail (`working-indicator`)** : point vert pulsé, libellé de phase et chronomètre en `body-sm`.
- **Rail d'étapes (`turn-rail`, `turn-group`, `turn-step`)** : groupe de tour (`turn-group`) avec en-tête « Tour N » en `heading`, extrait du message en `body-sm` encre douce, statut en badge, chiffres en `number` ; les étapes sont reliées par un filet vertical `{colors.line}` de 2 px. Étape (`turn-step`) repliée : une ligne, tuile d'icône `{rounded.sm}`, titre en `label`, chiffre clé en `number` aligné à droite, chevron ▸ / ▾. Icône par type (appel au modèle, demande d'outil, exécution, chargement de documentation, skill, hook, validation humaine, réinjection, réponse finale), toujours doublée du titre. Étape courante : point vert ; étape sélectionnée : violet doux. Contenu interne sans relief.
- **Préparation du harnais (`harness-prep`)** : même traitement qu'un groupe de tour, titre « Préparation du harnais », sans relief.
- **Journal des événements (`event-log`)** : en-tête repliable en `label` avec chevron ; lignes en `body-sm`, nom technique en `{typography.code}` encre douce, JSON en `{typography.code}` sur crème. Aucune couleur d'état ni de segment.
- **Compteur de tokens (`token-counter`)** : nombres Fredoka tabulaires ; entrée, sortie, temps écoulé.
- **Badge de déclenchement (`trigger-badge-model`, `trigger-badge-user`)** : « Déclenché par le modèle » sur violet doux avec icône puce ; « Forcé par l'utilisateur » en contour encre avec icône main. La différence tient à l'icône et au libellé, pas seulement au style.
- **Bouton Forcer (`force-button`)** : contour encre, icône main, pour rappeler le badge « Forcé par l'utilisateur ».
- **Événement du harnais (`harness-event`)** : carte avec filet latéral épais et icône ; rouge pour blocage et échec, violet pour information (hook qui laisse passer, compression, limite d'appels atteinte).
- **Carte de dépassement (`overflow-card`)** : carte à bordure rouge de `{spacing.stroke-min}`, icône d'alerte, titre « Contexte dépassé — l'appel au modèle n'a pas été envoyé », compte de tokens en `number`, puis deux sous-parties titrées en `label` : « En production, un harnais pourrait » et « Pour continuer la démo ».
- **Données sortantes (`outbound-payload`)** : en-tête jaune « RÉSEAU » avec icône globe et adresse de destination ; corps en `{typography.code}`, bordure en tirets encre.
- **Comparaison de tours (`turn-compare`)** : deux colonnes alignées segment par segment, écarts signalés par un signe (+ / −) et une valeur, jamais par la couleur seule.
- **Schéma d'architecture (`arch-zone-local`, `arch-zone-network`, `arch-boundary`, `arch-node-local`, `arch-node-network`, `arch-node-unavailable`, `arch-node-active`, `arch-flow`)** : deux zones séparées par la frontière verticale ; nœuds locaux violets à trait continu, nœuds réseau jaunes à tirets encre avec globe et « RÉSEAU ». Processus local et fichier local se distinguent par l'icône (engrenage / document) et le libellé `[ASSUMPTION]`. Nœud indisponible : fond crème, tirets gris, icône barrée et raison. Nœud en action : halo vert. Flux : trait `{spacing.stroke-min}` encre douce, vert quand il est parcouru.
  - **Bac (`arch-group`)** : contenant blanc à bordure `{colors.line}` 2 px, `{rounded.md}`, sans relief ; titre `label` posé sur la bordure (icône, nom, nombre). Côté Réseau : fond crème.
  - **Forme par catégorie**, dans les couleurs du lieu d'hébergement : outil = tuile d'icône ronde à gauche du nom ; serveur MCP = double trait (local) ou double tirets (réseau), pastille « N outils » ; skill = filet gauche épais de 7 px ; fichier = fond crème, icône document. Toutes gardent `{rounded.sm}` ; la maquette utilise des coins de 4 à 6 px sur skill et fichier, cette spine l'emporte.
  - **Bande des hooks (`arch-hook-strip`)** : dans le cadre Harnais, séparée du modèle par un tiret violet, étiquette pilule « Points d'accroche » ; hook en pièce violet doux à deux lignes (nom, point d'accroche). En action : halo vert. Bloquant : filet rouge de 7 px et « ✖ a bloqué ». Désactivé : tirets gris.
  - **Tronc et rails (`arch-trunk`)** : trait `{spacing.stroke-min}` encre douce, en tirets après la frontière ; chemin parcouru en halo vert 7 px avec un trait encre au centre, en tirets animés quand il franchit la frontière. Marqueurs ✋ (violet, validation H5 en attente) et ✖ (rouge, blocage par un hook).
- **Harnais et modèle dans le schéma (`arch-harness`, `arch-model`)** : dans la zone locale, un cadre « Harnais » (bordure violette `{spacing.stroke-min}`, étiquette pilule violette en haut à gauche, relief `{colors.relief-active}`) entoure le modèle et liste en puces violet doux, avec leur icône, les briques actives sans composant externe (mémoire courte, prompt système) ; les autres briques sont représentées par leurs bacs et par la bande des hooks. Le robot et les puces s'empilent verticalement. Sans brique active, le cadre affiche « Aucune brique : LLM nu ». Au centre du cadre, le modèle est un **robot-mascotte** : corps violet, oreilles violet foncé, visière blanche, visage encre, nom « Modèle » en `label` et nom du modèle chargé dessous. Il signifie le modèle et rien d'autre : c'est la pièce autour de laquelle on branche le harnais. Trois poses, pilotées par l'état du tour :

  | Pose | Visage | Antenne |
  |---|---|---|
  | Au repos | yeux fermés | `{colors.muted}`, fixe |
  | Réfléchit (génération en cours) | yeux ouverts, trois points | `{colors.state-active}`, clignote |
  | Utilise un outil | sourire, pastille verte à clé | `{colors.state-active}`, clignote |

  L'antenne verte suit la règle du vert : elle ne s'allume que quand le modèle travaille. La pose est aussi dite par un libellé accessible (le robot est une image avec texte alternatif), jamais par l'antenne seule.
- **Ligne de diagnostic (`diagnostic-row`)** : pastille d'état (vert « OK », rouge « Échec ») avec texte encre, libellé de la vérification, action corrective en dessous.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Une couleur = un sens : jaune pour réseau, vert pour « en action / OK », rouge pour « bloqué / échec » | Utiliser le jaune comme avertissement générique |
| Icône + libellé + couleur pour tout état et tout lieu d'hébergement | Coder un état ou le local / réseau par la seule couleur |
| Étiquettes de segment hors du segment, en encre, avec légende | Écrire en blanc sur les segments bleu ou vert d'eau |
| Traits d'au moins 2 px dans le schéma | Traits fins ou gris clair, illisibles en projection et en visio |
| Fredoka, Atkinson Hyperlegible et JetBrains Mono servies en local (WOFF2 + `@font-face`) | Charger une police depuis un CDN, comme le fait la maquette de référence |
| Tokens de charte pour l'encre, les neutres et les violets | Reprendre les neutres teintés lilas de la maquette (`#1C1535`, `#EFEBFB`…) |
| Relief jouet : ombre pleine sans flou, 4 px (1 px enfoncé, 6 px pour tiroir et menus), dans les couleurs de relief | Ombre floue, ombre en `rgba`, dégradé pour donner du volume, ou relief qui varie selon l'importance |
| Relief pour les pièces posées sur la page ; éléments indisponibles et contenu interne à plat | Relief sur les messages, les segments ou une pièce indisponible |
| Grands arrondis sur l'échelle 12 / 18 / 26 px et la pilule | Rayons hors échelle ou angles vifs |
| Pois uniquement sur le fond de page, en `{colors.dot}` | Pois ou motif derrière du texte, dans un volet ou une carte |
| Un sous-titre par volet, qui dit ce qu'il montre | Sous-titre décoratif, slogan, ou qui répète le titre |
| Distinguer les catégories du schéma par le bac, la forme et l'icône | Donner une couleur à chaque catégorie |
| Le robot représente le modèle, et seulement lui | Robot comme décoration, sur un autre composant ou dans un état sans rapport avec le modèle |
| Animations réservées au signal « en action » (pouls, flux, antenne) et coupées sous `prefers-reduced-motion` | Curseur personnalisé, révélations au scroll, compteurs animés de la charte vitrine, robot animé au repos |
| Thème clair uniquement | Mode sombre en V1 |
