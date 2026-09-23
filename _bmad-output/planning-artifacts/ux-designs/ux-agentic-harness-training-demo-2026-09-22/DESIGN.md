---
title: DESIGN — WaveStack
status: draft
created: 2026-09-22
updated: 2026-09-23
sources:
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/addendum.md
name: WaveStack
description: Démonstrateur pédagogique local de harnais agentique, à la charte Wavestone, pensé pour la projection. Thème clair uniquement en V1.
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
    fontFamily: 'Manrope, Inter, system-ui, sans-serif'
    fontSize: 13px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: 0.06em
  heading:
    fontFamily: 'Aptos, Inter, system-ui, sans-serif'
    fontSize: 18px
    fontWeight: '600'
    lineHeight: '1.3'
  chat:
    fontFamily: 'Aptos, Inter, system-ui, sans-serif'
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  body:
    fontFamily: 'Aptos, Inter, system-ui, sans-serif'
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  body-sm:
    fontFamily: 'Aptos, Inter, system-ui, sans-serif'
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.4'
  label:
    fontFamily: 'Manrope, Inter, system-ui, sans-serif'
    fontSize: 12px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: 0.04em
  number:
    fontFamily: 'Manrope, Inter, system-ui, sans-serif'
    fontSize: 14px
    fontWeight: '700'
    lineHeight: '1.2'
  number-lg:
    fontFamily: 'Manrope, Inter, system-ui, sans-serif'
    fontSize: 20px
    fontWeight: '800'
    lineHeight: '1.1'
  code:
    fontFamily: "'Cascadia Mono', Consolas, ui-monospace, monospace"
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.5'
rounded:
  sm: 12px
  md: 16px
  lg: 22px
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
  architecture-band-height: 200px
  stroke-min: 2px
  hit-target-min: 32px
components:
  top-bar:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border-bottom: '{colors.line}'
    height: '{spacing.top-bar-height}'
  pane:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    radius: '{rounded.md}'
    padding: '{spacing.pane-padding}'
    title-typography: '{typography.pane-title}'
    title-color: '{colors.ink-soft}'
  pane-focused:
    border: '{colors.primary}'
  button-primary:
    background: '{colors.primary}'
    foreground: '{colors.on-primary}'
    radius: '{rounded.sm}'
    min-height: '{spacing.hit-target-min}'
  button-secondary:
    background: '{colors.surface-raised}'
    foreground: '{colors.primary}'
    border: '{colors.primary}'
    radius: '{rounded.sm}'
    min-height: '{spacing.hit-target-min}'
  reset-button:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.sm}'
  scenario-picker:
    background: '{colors.primary-soft}'
    foreground: '{colors.primary-deep}'
    radius: '{rounded.sm}'
  model-picker:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.sm}'
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
    radius: '{rounded.sm}'
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
    radius: '{rounded.md}'
  context-segment:
    radius: '{rounded.sm}'
    label-color: '{colors.ink}'
    label-typography: '{typography.label}'
    body-typography: '{typography.code}'
    selected-outline: '{colors.ink}'
  brick-card:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    radius: '{rounded.md}'
    active-border: '{colors.primary}'
    active-background: '{colors.primary-soft}'
    unavailable-foreground: '{colors.muted}'
    reason-color: '{colors.ink-soft}'
  brick-toggle:
    on: '{colors.primary}'
    off: '{colors.line}'
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
    radius: '{rounded.lg}'
  chat-message-user:
    background: '{colors.primary-soft}'
    foreground: '{colors.ink}'
    radius: '{rounded.md}'
    typography: '{typography.chat}'
  chat-message-model:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.md}'
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
    radius: '{rounded.md}'
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
    radius: '{rounded.sm}'
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
    radius: '{rounded.sm}'
  turn-compare:
    background: '{colors.surface-raised}'
    diff-increase: '{colors.ink}'
    diff-decrease: '{colors.ink}'
    radius: '{rounded.md}'
  arch-zone-local:
    background: '{colors.surface-raised}'
    label-color: '{colors.primary}'
  arch-zone-network:
    background: '{colors.surface}'
    label-color: '{colors.ink}'
  arch-boundary:
    stroke: '{colors.hosting-boundary}'
    stroke-width: '{spacing.stroke-min}'
  arch-node-local:
    background: '{colors.hosting-local}'
    foreground: '{colors.on-primary}'
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

L'identité reprend la charte Wavestone (violet ancre, vert en unique accent secondaire, crème, encre) avec la sobriété d'un outil d'ingénierie. Les surfaces sont claires, les traits nets, l'information dense mais rangée. Les couleurs vives ont chacune un rôle précis : violet = local et marque, jaune = réseau, vert = « en train d'agir » et « OK », rouge = « bloqué / en échec ». Rien n'est décoratif.

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

- **Aptos** (repli Inter, puis `system-ui`) : voix de l'interface, messages, explications. Aptos est présent sur les postes Windows équipés d'Office ; Inter est embarqué localement en repli.
- **Manrope** : étiquettes (`label`, `pane-title`) et nombres (`number`, `number-lg`). Chiffres tabulaires pour que les compteurs de tokens ne sautent pas pendant la mise à jour.
- **Cascadia Mono** (repli Consolas) `[ASSUMPTION]` : contenu brut du contexte et des sorties du modèle, en `{typography.code}`. Le memlog ne fixe pas de police à chasse fixe ; Cascadia Mono est livrée avec Windows 11, donc disponible hors ligne.
- Toutes les polices non système sont servies en local : aucune requête vers un service de polices (NFR-3, NFR-4).

Rampe à 100 % : `pane-title` 13 px, `heading` 18 px, `chat` 16 px, `body` 14 px, `body-sm` et `code` 13 px, `label` 12 px, `number` 14 px, `number-lg` 20 px. Les paliers 125 % et 150 % (NFR-9), choisis par le contrôle unique « Aa 100 % », multiplient toute la rampe ; aucun texte ne descend sous 12 px au palier 100 %. `[ASSUMPTION]` Rampe dimensionnée pour la fenêtre utile de 1280×650.

Titres de volet en capitales espacées (`pane-title`), en `{colors.ink-soft}`. Pas de tailles « display » : l'écran appartient au contenu de la démonstration.

## Layout & Spacing

Échelle de 4 px (`{spacing.1}` à `{spacing.6}`). Les volets sont séparés par une gouttière étroite (`{spacing.gutter}`) et ont un rembourrage de `{spacing.pane-padding}` : la densité prime, car tout doit tenir dans 1280×650.

Grille retenue : 5 volets masquables (référence : [`.working/layout-5-volets-v2.html`](.working/layout-5-volets-v2.html)) :
- barre haute de `{spacing.top-bar-height}` sur toute la largeur ;
- colonne de gauche sur toute la hauteur : panneau des briques (`{spacing.brick-panel-width}`) ;
- à droite, rangée du haut : vue humain, Contexte LLM, Orchestration ; Contexte LLM et Orchestration se partagent à parts égales la largeur restante ;
- à droite, bande basse sous ces trois volets : schéma d'architecture, `{spacing.architecture-band-height}`.

Un volet masqué libère sa place : les volets visibles de la même rangée se la partagent ; si le panneau des briques est masqué, les autres volets prennent toute la largeur ; si le schéma est masqué, la rangée du haut prend toute la hauteur. Le mode focus redistribue la grille sans changer l'ordre des volets (voir EXPERIENCE.md). Le comportement par taille d'écran est dans EXPERIENCE.md, section Responsive & Platform.

## Elevation & Depth

Pas d'ombres portées pour la hiérarchie : un vidéoprojecteur les écrase et la visio les floute. La profondeur passe par le ton : page `{colors.surface}`, volets `{colors.surface-raised}` bordés de `{colors.line}`. Seule exception : le tiroir d'édition (`edit-drawer`) et les menus déroulants portent une ombre courte et nette pour se détacher du volet qu'ils recouvrent.

Le halo vert du composant en cours d'action (`arch-node-active`) n'est pas une ombre mais un signal d'état.

## Shapes

Rayons de la charte : `{rounded.sm}` (12 px) pour boutons, champs, étapes, nœuds du schéma et segments ; `{rounded.md}` (16 px) pour volets, cartes de brique et messages ; `{rounded.lg}` (22 px) pour le tiroir d'édition. `{rounded.full}` pour la jauge, les badges, les puces et le réglage de taille de texte.

Les nœuds réseau gardent le même rayon que les nœuds locaux : seule la bordure (continue ou en tirets) et la couleur changent, pour que la comparaison porte sur le lieu d'hébergement et rien d'autre.

## Components

Noms de composants identiques dans EXPERIENCE.md, section Component Patterns.

- **Barre haute (`top-bar`)** : fond blanc, filet bas `{colors.line}`. De gauche à droite : sélecteur de scénario, jauge de contexte (élément le plus large), puces des volets masqués et menu « Volets ▾ », sélecteur de modèle, réglage de taille de texte, bouton Réinitialiser.
- **Volet (`pane`)** : titre `pane-title` en haut à gauche ; en haut à droite, bouton ⛶ (mode focus) puis bouton « — » (`pane-hide-button`, masquer). Volet en mode focus : bordure `{colors.primary}`.
- **Puce de volet masqué (`pane-chip`)** : « + Nom du volet » sur violet doux, bordure en tirets violette. Quand le volet masqué contient un élément correspondant à la sélection, la puce porte un point encre et le libellé « lié ».
- **Menu Volets (`pane-menu`)** : bouton « Volets ▾ » ; liste déroulante des cinq volets avec case à cocher chacun.
- **Boutons (`button-primary`, `button-secondary`, `reset-button`)** : primaire violet plein ; secondaire contour violet ; Réinitialiser neutre, pour ne pas attirer le clic par erreur. Hauteur minimale `{spacing.hit-target-min}`.
- **Sélecteur de scénario (`scenario-picker`)** : pastille violet doux avec le nom du module et du scénario en cours.
- **Sélecteur de modèle (`model-picker`)** : liste déroulante neutre, nom du modèle et taille (ex. « 2B »).
- **Réglage de taille de texte (`text-size-control`)** : contrôle unique « Aa 100 % », pastille neutre ; le nombre affiche le palier courant (100, 125 ou 150 %).
- **Jauge de contexte (`context-gauge`)** : barre horizontale empilée, rayons pleins, segments dans l'ordre de la palette catégorielle, espace libre en crème hachuré. À droite : `number` « 1 840 / 4 096 tokens · 45 % ». Un marqueur vertical en encre indique le seuil d'alerte. Au dépassement, le pourcentage passe sur pastille rouge avec icône.
- **Détail de la jauge (`context-gauge-detail`)** : grille de cellules à la manière de `/context`, une cellule par tranche de tokens, colorée selon la palette catégorielle, cellules libres en crème hachuré. Légende à droite : pastille, nom du segment, tokens et pourcentage en `number`.
- **Segment de contexte (`context-segment`)** : bloc de texte brut en `{typography.code}`, filet latéral gauche de 4 px dans la couleur du segment, étiquette `label` en encre avec pastille de couleur et nombre de tokens. Segment sélectionné : contour encre de 2 px.
- **Carte de brique (`brick-card`)** : nom, interrupteur (`brick-toggle`), puce de catégorie (`category-chip` : « prompt engineering », « context engineering », « harness engineering »), étiquette de lieu d'hébergement (`hosting-tag-local` ou `hosting-tag-network`), explication dépliable. Active : fond violet doux, bordure violette. Indisponible : texte gris, interrupteur désactivé, raison toujours visible en `{colors.ink-soft}`.
- **Tiroir d'édition (`edit-drawer`)** : panneau qui glisse par-dessus le panneau des briques pour éditer le prompt système ou la mémoire globale ; champ en `{typography.code}`.
- **Messages (`chat-message-user`, `chat-message-model`)** : utilisateur sur violet doux, modèle sur blanc bordé. Typographie `chat`. Bloc de raisonnement (`reasoning-block`) replié sur crème, en `body-sm`.
- **Champ de saisie (`composer`)** : zone de texte en `chat`, bordure `{colors.line}`, `{colors.primary}` au focus ; bouton d'envoi primaire à droite.
- **Prompt suggéré (`suggested-prompt-chip`)** : puce contour violet au-dessus du champ de saisie.
- **Indicateur de travail (`working-indicator`)** : point vert pulsé, libellé de phase et chronomètre en `body-sm`.
- **Rail d'étapes (`turn-rail`, `turn-step`)** : colonne verticale d'étapes reliées par un filet ; étape courante marquée d'un point vert, étape sélectionnée sur violet doux.
- **Compteur de tokens (`token-counter`)** : nombres Manrope tabulaires ; entrée, sortie, temps écoulé.
- **Badge de déclenchement (`trigger-badge-model`, `trigger-badge-user`)** : « Déclenché par le modèle » sur violet doux avec icône puce ; « Forcé par l'utilisateur » en contour encre avec icône main. La différence tient à l'icône et au libellé, pas seulement au style.
- **Bouton Forcer (`force-button`)** : contour encre, icône main, pour rappeler le badge « Forcé par l'utilisateur ».
- **Événement du harnais (`harness-event`)** : carte avec filet latéral épais et icône ; rouge pour blocage et échec, violet pour information (hook qui laisse passer, compression, limite d'appels atteinte).
- **Carte de dépassement (`overflow-card`)** : carte à bordure rouge de `{spacing.stroke-min}`, icône d'alerte, titre « Contexte dépassé — l'appel au modèle n'a pas été envoyé », compte de tokens en `number`, puis deux sous-parties titrées en `label` : « En production, un harnais pourrait » et « Pour continuer la démo ».
- **Données sortantes (`outbound-payload`)** : en-tête jaune « RÉSEAU » avec icône globe et adresse de destination ; corps en `{typography.code}`, bordure en tirets encre.
- **Comparaison de tours (`turn-compare`)** : deux colonnes alignées segment par segment, écarts signalés par un signe (+ / −) et une valeur, jamais par la couleur seule.
- **Schéma d'architecture (`arch-zone-local`, `arch-zone-network`, `arch-boundary`, `arch-node-local`, `arch-node-network`, `arch-node-unavailable`, `arch-node-active`, `arch-flow`)** : deux zones séparées par la frontière verticale ; nœuds locaux violets à trait continu, nœuds réseau jaunes à tirets encre avec globe et « RÉSEAU ». Processus local et fichier local se distinguent par l'icône (engrenage / document) et le libellé `[ASSUMPTION]`. Nœud indisponible : fond crème, tirets gris, icône barrée et raison. Nœud en action : halo vert. Flux : trait `{spacing.stroke-min}` encre douce, vert quand il est parcouru.
- **Ligne de diagnostic (`diagnostic-row`)** : pastille d'état (vert « OK », rouge « Échec ») avec texte encre, libellé de la vérification, action corrective en dessous.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Une couleur = un sens : jaune pour réseau, vert pour « en action / OK », rouge pour « bloqué / échec » | Utiliser le jaune comme avertissement générique |
| Icône + libellé + couleur pour tout état et tout lieu d'hébergement | Coder un état ou le local / réseau par la seule couleur |
| Étiquettes de segment hors du segment, en encre, avec légende | Écrire en blanc sur les segments bleu ou vert d'eau |
| Traits d'au moins 2 px dans le schéma | Traits fins ou gris clair, illisibles en projection et en visio |
| Polices servies localement | Charger une police depuis un CDN |
| Surfaces claires, ton sur ton, bordures `{colors.line}` | Ombres portées pour hiérarchiser, dégradés, mode sombre |
| Animations réservées au signal « en action » | Curseur personnalisé, révélations au scroll, compteurs animés de la charte vitrine |
