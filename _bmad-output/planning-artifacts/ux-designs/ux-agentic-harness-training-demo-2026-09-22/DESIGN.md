---
title: DESIGN — WaveStack
status: draft
created: 2026-09-22
updated: 2026-09-29
sources:
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/addendum.md
name: WaveStack
description: Démonstrateur pédagogique local de harnais agentique, à la charte Wavestone, dans une direction « atelier de construction » pensée pour la projection. Thème clair en V1, jetons prêts pour un second thème (story 31).
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
  # Lieu d'hébergement (story 33 : le local n'a plus de couleur, voir Colors)
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
  # Code couleur par discipline (story 33) : une couleur et son fond doux par discipline
  discipline-prompt: '#451DC7'
  discipline-prompt-soft: '#EEE9FC'
  discipline-context: '#0F7B6C'
  discipline-context-soft: '#E2F3EF'
  discipline-harness: '#B8327A'
  discipline-harness-soft: '#FBE7F1'
  discipline-network: '#D9A400'
  discipline-network-soft: '#FFF5D1'
  discipline-neutral: '#8A8A9E'
  discipline-neutral-soft: '#EFEFF4'
  # Sur encre (story 33) : textes et traits posés sur un fond {colors.ink}
  on-ink: '#FFFFFF'
  on-ink-soft: '#CFCDE4'
  # Contexte LLM (story 32) : ce que l'appel a produit, sa réflexion, et les couleurs de texte
  # des arbres JSON (distinctes des disciplines)
  produced-soft: '#E8EEF7'
  reasoning-soft: '#F3EFE3'
  json-key: '#1E3A8A'
  json-string: '#7A3410'
  json-literal: '#0B5E73'
typography:
  # Base ; le mode projection (story 34, NFR-9) multiplie toute la rampe par 9/7, dans app.css.
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
  top-bar-height: 56px
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
  # Story 33 : une couleur et son fond doux par discipline ; `model` = ce que fait le modèle.
  discipline-code:
    prompt: '{colors.discipline-prompt}'
    prompt-soft: '{colors.discipline-prompt-soft}'
    context: '{colors.discipline-context}'
    context-soft: '{colors.discipline-context-soft}'
    harness: '{colors.discipline-harness}'
    harness-soft: '{colors.discipline-harness-soft}'
    network: '{colors.discipline-network}'
    network-soft: '{colors.discipline-network-soft}'
    neutral: '{colors.discipline-neutral}'
    neutral-soft: '{colors.discipline-neutral-soft}'
    model: '{colors.ink}'
    on-model: '{colors.on-ink}'
  discipline-legend:
    swatch-border: '{colors.ink-soft}'
    swatch-border-on-ink: '{colors.on-ink-soft}'
    foreground: '{colors.ink-soft}'
    foreground-on-ink: '{colors.on-ink-soft}'
    typography: '{typography.label}'
  top-bar:
    background: '{colors.ink}'
    foreground: '{colors.on-ink}'
    title-color: '{colors.on-ink}'
    focus-ring: '{colors.on-ink}'
    shadow: '{colors.relief}'
    radius: '{rounded.lg}'
    height: '{spacing.top-bar-height}'
  pane:
    background: '{colors.surface-raised}'
    header-background: '{colors.surface}'
    shadow: '{colors.relief}'
    radius: '{rounded.lg}'
    padding: '{spacing.pane-padding}'
    title-typography: '{typography.pane-title}'
    title-color: '{colors.ink}'
    subtitle-typography: '{typography.pane-subtitle}'
    subtitle-color: '{colors.ink-soft}'
  # Story 34: the reading order, a numbered disc before the title of the four demo panes.
  pane-step:
    background: '{colors.ink}'
    foreground: '{colors.on-ink}'
    typography: '{typography.number}'
    size: 1.7em
    radius: '{rounded.full}'
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
  # Story 34: replaces the « Aa » text-size-control, never built; on the ink top bar.
  projection-toggle:
    background: transparent
    foreground: '{colors.on-ink}'
    border: '{colors.on-ink-soft}'
    pressed-background: '{colors.on-ink}'
    pressed-foreground: '{colors.ink}'
    typography: '{typography.label}'
    radius: '{rounded.md}'
    min-height: '{spacing.hit-target-min}'
    scale: 9/7
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
    match-label: ' · lié'
  # Story 34: the linked view. Hover or focus: ring in the element's discipline (ink for the
  # network and the neutral), the rest dimmed; selection: ink outline, nothing dimmed.
  link-state:
    dimmed-opacity: '0.35'
    hover-ring: '{components.discipline-code}'
    hover-ring-network: '{colors.ink}'
    hover-ring-neutral: '{colors.ink}'
    hover-ring-on-ink: '{colors.on-ink}'
    ring-width: '{spacing.stroke-min}'
    selected-outline: '{colors.ink}'
    selected-outline-width: '{spacing.stroke-min}'
    selected-outline-offset: 2px
    transition: 150ms
    reduced-motion-transition: none
  pane-menu:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    shadow: '{colors.relief}'
    radius: '{rounded.md}'
  context-gauge:
    track: '{colors.surface-raised}'
    border: '{colors.on-ink-soft}'
    segment: '{components.discipline-code}'
    separator: '{colors.surface-raised}'
    radius: '{rounded.full}'
    label-typography: '{typography.number}'
    label-color: '{colors.on-ink}'
    legend-color: '{colors.on-ink-soft}'
    near-limit-marker: '{colors.ink}'
    overflow-color: '{colors.danger}'
  context-gauge-detail:
    background: '{colors.surface-raised}'
    cell-free: '{colors.segment-free}'
    cell-border: '{colors.line}'
    legend-typography: '{typography.body-sm}'
    number-typography: '{typography.number}'
    radius: '{rounded.lg}'
  # Turn comparison only since story 32; Contexte LLM reads by section (context-section).
  context-segment:
    radius: '{rounded.md}'
    rule: '{components.discipline-code}'
    background: '{components.discipline-code}'
    swatch: '{colors.segment-system-prompt}' # celle de son type : segment-*
    label-color: '{colors.ink}'
    label-typography: '{typography.label}'
    body-typography: '{typography.code}'
    selected-outline: '{colors.ink}'
  # Story 32: one call of the turn, « Appel i sur n », its figures, then read and produced.
  context-call:
    title-typography: '{typography.heading}'
    figures-typography: '{typography.number}'
    figures-color: '{colors.ink-soft}'
    rule: '{colors.line}'
    between-typography: '{typography.body-sm}'
    between-color: '{colors.ink-soft}'
    mode-pressed-background: '{colors.ink}'
    mode-pressed-foreground: '{colors.on-ink}'
    mode-border: '{colors.line}'
  # Story 32: consecutive segments of one source, the margin (source) beside the text.
  context-section:
    radius: '{rounded.md}'
    rule: '{components.discipline-code}'
    background: '{components.discipline-code}'
    swatch: '{colors.segment-system-prompt}' # celle de son type : segment-*
    label-color: '{colors.ink}'
    label-typography: '{typography.label}'
    body-typography: '{typography.code}'
    template-color: '{colors.ink-soft}'
    new-badge-background: '{colors.ink}'
    new-badge-foreground: '{colors.on-ink}'
    seen-background: '{colors.surface}'
    seen-foreground: '{colors.ink-soft}'
    margin-stack-below: 28rem
    selected-outline: '{colors.ink}'
  # Story 32: what the call produced (reasoning, answer, tool call), on its own background.
  produced-block:
    background: '{colors.produced-soft}'
    reasoning-background: '{colors.reasoning-soft}'
    rule: '{colors.ink}'
    tag-background: '{colors.ink}'
    tag-foreground: '{colors.on-ink}'
    foreground: '{colors.ink}'
    label-typography: '{typography.label}'
    body-typography: '{typography.code}'
    radius: '{rounded.md}'
  # Story 32: a JSON, indented and foldable, in native JS; text colours only.
  json-tree:
    key: '{colors.json-key}'
    string: '{colors.json-string}'
    literal: '{colors.json-literal}'
    punctuation: '{colors.ink-soft}'
    indent: '{spacing.4}'
    typography: '{typography.code}'
  brick-card:
    background: '{colors.discipline-neutral-soft}'
    border: '{colors.line}'
    rule: '{colors.discipline-neutral}'
    rule-width: 5px
    foreground: '{colors.ink-soft}'
    shadow: '{colors.relief}'
    radius: '{rounded.md}'
    active-rule: '{components.discipline-code}'
    active-background: '{components.discipline-code}'
    active-foreground: '{colors.ink}'
    active-shadow: '{colors.relief-active}'
    unavailable-foreground: '{colors.ink-soft}'
    reason-color: '{colors.ink-soft}'
    status-typography: '{typography.body-sm}'
    status-color: '{colors.ink-soft}'
    group-title-typography: '{typography.label}'
    group-title-color: '{colors.ink-soft}'
  brick-toggle:
    on: '{components.discipline-code}'
    off: '{colors.line}'
    parent-off: '{colors.muted}'
    radius: '{rounded.full}'
  category-chip:
    background: '{components.discipline-code}'
    foreground: '{colors.ink}'
    border: '{components.discipline-code}'
    radius: '{rounded.full}'
    typography: '{typography.label}'
  hosting-tag-local:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.ink-soft}'
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
    background: '{colors.ink}'
    foreground: '{colors.on-ink}'
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
    tile: '{components.discipline-code}'
    tile-letter-typography: '{typography.label}'
    model-tile: '{colors.ink}'
    model-icon: '{colors.on-ink}'
    current-marker: '{colors.state-active}'
    selected-background: '{colors.primary-soft}'
    via-color: '{colors.ink-soft}'
  # Story 34: what left the workstation during the last turn shown, under the schema.
  schema-outbound:
    foreground: '{colors.ink}'
    rule: '{colors.line}'
    typography: '{typography.body-sm}'
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
    section-typography: '{typography.label}'
    section-color: '{colors.ink-soft}'
    masked-background: '{colors.surface}'
    masked-foreground: '{colors.ink-soft}'
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
    plate: '{colors.ink}'
    label-color: '{colors.on-ink}'
    name-color: '{colors.on-ink-soft}'
    body: '{colors.primary}'
    ears: '{colors.primary-deep}'
    outline: '{colors.on-ink}'
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
    background: '{components.discipline-code}'
    foreground: '{colors.ink}'
    border: '{components.discipline-code}'
    border-style: solid
    radius: '{rounded.sm}'
  arch-node-network:
    background: '{colors.discipline-network-soft}'
    foreground: '{colors.ink}'
    border: '{colors.ink}'
    border-style: dashed
    rule: '{colors.discipline-network}'
    rule-width: 6px
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

L'identité reste celle de la charte Wavestone : violet ancre, vert en unique accent secondaire, crème, encre. L'information est dense mais rangée. Les couleurs vives ont chacune un rôle précis : violet = marque et prompt engineering, vert d'eau = context engineering, framboise = harness engineering, jaune = ce qui sort du poste, vert = « en train d'agir » et « OK », rouge = « bloqué / en échec ». Les éléments clés (barre haute, message de l'utilisateur, ce que fait le modèle) reposent sur l'encre (story 33, maquette de refonte du 2026-09-28). Le fond à pois est la seule ornementation, et il reste derrière les volets.

Les composants vitrine de la charte (curseur personnalisé, révélations au scroll, compteurs animés) ne s'appliquent pas : une application qui s'anime pour elle-même vole l'attention que la démonstration doit capter.

Thème clair en V1 `[ASSUMPTION]` : plus robuste en projection dans une salle éclairée. Jetons prêts pour un second thème (story 31) : chaque couleur passe par une variable de `tokens.css`, jamais écrite en dur dans `app.css` ni `app.js` (`tests/test_web_tokens.py`) ; un thème sombre n'aura qu'à redéfinir les jetons.

## Colors

**Charte Wavestone.**
- **Violet (`#451DC7`)** : couleur ancre, celle de la marque et du prompt engineering (`discipline-prompt` a la même valeur). Boutons primaires, cadre du harnais, focus. Il ne dit plus le lieu d'hébergement local (story 33). Contraste 9,3:1 sur blanc.
- **Violet foncé (`#250F6B`)** : texte sur fonds violet doux (puces de catégorie, badge « déclenché par le modèle »).
- **Violet doux (`#EDE7FE`)** : fond d'étape sélectionnée, de puce de volet et de sélecteur de scénario. La brique active et le message de l'utilisateur ont quitté ce fond (story 33).
- **Vert (`#04F06A`)** : seul accent secondaire. Réservé à « composant en cours d'action » (halo, flux animé, étape courante) et à « diagnostic OK ». Contraste 1,5:1 sur blanc : jamais en texte ni en trait fin isolé, toujours en fond ou halo avec texte encre (12,8:1).
- **Vert clair (`#CAFEE0`)** : réserve de la charte, sans usage assigné en V1.
- **Encre (`#0A0A14`)**, **encre douce (`#4A4A5E`)** : texte principal et secondaire. L'encre sert aussi de fond aux éléments clés (story 33) : barre haute, bulle de l'utilisateur, tuile d'une étape du modèle, plaque du modèle dans le schéma. L'encre de la charte reste en place, pas celle de la maquette (`#1A1733`).
- **Sur encre** (`on-ink` `#FFFFFF`, `on-ink-soft` `#CFCDE4`) : texte et traits posés sur l'encre, 19,7:1 et 12,7:1. **Gris (`#8A8A9E`)** : 3,4:1, donc réservé à l'état indisponible et aux éléments non textuels ; jamais pour un texte à lire.
- **Ligne (`#E6E6EC`)**, **crème (`#F6F5FA`)**, **blanc (`#FFFFFF`)** : séparateurs, fond de page, fond des volets. Le blanc n'est pas listé dans la charte relevée au memlog `[ASSUMPTION]`.
- **Relief (`#D9D0F6`)**, **relief actif (`#C9BCF5`)**, **pois (`#D6CCF5`)** : trois teintes du violet de charte, ajoutées pour la direction « atelier de construction ». Elles ne servent qu'à l'ombre pleine (`{colors.relief}` sous volets et cartes, `{colors.relief-active}` sous pièces actives et bouton secondaire) et aux pois du fond de page (`{colors.dot}`). Jamais en texte, en fond de contenu ni en trait porteur de sens.

La maquette de référence teinte aussi les neutres en lilas (encre `#1C1535`, encre douce `#4E4868`, violet doux `#EAE3FF`, page `#EFEBFB`, ligne `#E4DEF5`, violet clair `#8E73F0` dans le logo). Ces écarts ne sont pas repris : les tokens de charte ci-dessus s'appliquent.
- **Jaune (`#FFCA4A`)** et **rouge (`#FF2A49`)** : avec parcimonie, chacun avec une seule signification (ci-dessous).

**Codage local / réseau** `[ASSUMPTION]`. Il porte le message sur la souveraineté (FR-3, SM-3) et doit se lire en une seconde, projeté.
- Le lieu d'hébergement est porté par les zones du schéma (« Poste de travail », « RÉSEAU · hors du poste »), la frontière, l'icône globe et le libellé « RÉSEAU ». Le local n'a plus de couleur propre (story 33) : le violet dit le prompt engineering, et un nœud local prend la couleur de la discipline de sa brique. L'étiquette « Local » (`hosting-tag-local`) est neutre : fond blanc, bordure encre douce.
- Réseau = jaune, jamais seul : `{colors.hosting-network}` en fond des étiquettes « RÉSEAU » et de l'en-tête des données sortantes, texte encre (12,9:1) et bordure en tirets encre ; `{colors.discipline-network}` en trait épais ou en fond sous texte encre (8,7:1) dans le code couleur des disciplines, toujours doublé du globe ou du libellé « RÉSEAU ». Seul sur blanc, ni l'un (1,5:1) ni l'autre (2,3:1) ne suffit.
- La frontière Poste de travail / Réseau est un trait `{colors.hosting-boundary}` de `{spacing.stroke-min}`.
- Le jaune ne sert **qu'au** réseau, c'est-à-dire à ce qui sort du poste. Il n'est pas utilisé comme couleur d'avertissement, pour que « jaune » veuille toujours dire « ça sort du poste ».

**Code couleur par discipline** (story 33, maquette de refonte du 2026-09-28). Une discipline, une couleur, dans les cinq volets : carte de brique, segment de la jauge et de Contexte LLM, tuile d'étape, nœud et puce du schéma. Chaque discipline a une couleur (trait, interrupteur, segment de jauge) et un fond doux (carte active, segment, nœud). Les valeurs viennent de la maquette, sauf l'encre, qui reste celle de la charte. La session porte la discipline de chaque segment et de chaque groupe de la jauge (sa catégorie de brique, AD-9) ; l'interface ne la calcule pas (AD-1).

| Discipline | Couleur | Fond doux | Où |
|---|---|---|---|
| Prompt engineering | `discipline-prompt` `#451DC7` | `discipline-prompt-soft` `#EEE9FC` | Raisonnement, prompt système |
| Context engineering | `discipline-context` `#0F7B6C` | `discipline-context-soft` `#E2F3EF` | mémoires, RAG, skills, compression |
| Harness engineering | `discipline-harness` `#B8327A` | `discipline-harness-soft` `#FBE7F1` | outils, MCP, hooks, sous-agent, étapes du harnais |
| Sort du poste de travail | `discipline-network` `#D9A400` | `discipline-network-soft` `#FFF5D1` | nœuds réseau, étapes avec données sortantes, puce « RÉSEAU » |
| Neutre | `discipline-neutral` `#8A8A9E` | `discipline-neutral-soft` `#EFEFF4` | message et gabarit, fichiers du harnais, brique éteinte |
| Modèle | `ink` | `ink` | tuiles des appels, demandes d'outil et réponses finales ; plaque du modèle |

Contrastes, verrouillés par `tests/test_web_tokens.py` (calcul WCAG en Python) :

| Paire | Ratio | Seuil |
|---|---|---|
| `on-ink` sur `ink` | 19,7 | 4,5 |
| `on-ink-soft` sur `ink` | 12,7 | 4,5 |
| `on-ink` sur prompt | 9,3 | 4,5 |
| `on-ink` sur context | 5,2 | 4,5 |
| `on-ink` sur harness | 5,6 | 4,5 |
| `ink` sur network | 8,7 | 4,5 |
| `ink-soft` sur chaque fond doux | ≥ 7,2 | 4,5 |
| prompt, context, harness et neutral sur `surface-raised` | ≥ 3,4 | 3 |

- `discipline-network` fait 2,3:1 sur blanc : il sert toujours de fond sous un texte encre, ou de trait accompagné du globe ou du libellé « RÉSEAU ».
- Le violet sur l'encre fait 2,1:1 : la jauge garde donc une piste claire (`surface-raised`) dans la barre foncée, et les pastilles des légendes sont bordées (`on-ink-soft` sur l'encre, `ink-soft` sur blanc). Pour la même raison, le robot posé sur sa plaque d'encre a un contour `on-ink`.
- La discipline « réseau » ne s'applique qu'à ce qui sort du poste : nœuds `hosting: network`, étapes avec données sortantes, puces « RÉSEAU », légende. Les segments et la jauge n'ont que prompt, context, harness et neutre : un résultat d'outil réseau est entré dans le contexte, il n'en sort pas.
- La catégorie d'une brique (sa discipline) n'est pas son groupe du panneau : skills et compression sont en context engineering mais rangés dans « Ce que le harnais fait ».

**Contexte LLM : lu et produit** (story 32). Ce qu'un appel a lu garde les fonds doux de discipline ; ce qu'il a lui-même produit repose sur un fond propre, qu'aucune discipline ne prend, avec un filet et une étiquette encre (« Produit par le modèle », `on-ink` sur `ink`, 19,7:1). Les arbres JSON colorent leur texte avec trois couleurs distinctes des disciplines, pour ne pas brouiller le code couleur de la story 33.

| Jeton | Valeur | Rôle | Contrastes (`tests/test_web_tokens.py`) |
|---|---|---|---|
| `produced-soft` | `#E8EEF7` | fond de la réponse et des appels d'outil produits | encre 16,9 ; encre douce 7,4 |
| `reasoning-soft` | `#F3EFE3` | fond de la réflexion produite | encre 17,1 ; encre douce 7,5 |
| `json-key` | `#1E3A8A` | clés des arbres JSON | ≥ 8,7 |
| `json-string` | `#7A3410` | chaînes | ≥ 7,6 |
| `json-literal` | `#0B5E73` | nombres, booléens, `null` | ≥ 6,2 |

Les trois couleurs JSON sont mesurées sur les deux fonds produits, sur `surface-raised` et sur chaque fond doux de discipline (une section lue). Ce sont des couleurs de texte seulement. Les jetons n'ont pas encore de jumeau sombre : la story 31 couvrira tous ceux de `tokens.css`.

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

Depuis la story 33, la couleur de segment ne sert plus qu'à la pastille du type (Contexte LLM, détail de la jauge) : le filet et le fond du segment, comme les segments de la jauge, prennent la couleur de sa discipline. Le type reste lisible par la pastille, l'étiquette et l'infobulle.

À éviter : dégradés, fonds colorés derrière du texte courant autres que les fonds doux de discipline, les deux fonds du produit (story 32) et l'encre, toute couleur hors de cette liste, et toute réutilisation d'une couleur de segment pour autre chose que son type.

## Typography

- **Fredoka** (graisses 500 et 600) : titres de volet (`pane-title`), titres (`heading`), étiquettes (`label`) et nombres (`number`, `number-lg`). Ses formes rondes portent le ton « jeu de construction ». Chiffres tabulaires (`font-variant-numeric: tabular-nums`) pour que les compteurs de tokens ne sautent pas pendant la mise à jour. `[ASSUMPTION]` Le fichier servi doit contenir la fonction OpenType `tnum` ; sinon, chaque compteur reçoit une largeur fixe.
- **Atkinson Hyperlegible** (400 et 700) : voix de l'interface, messages, explications, sous-titres de volet. Dessinée pour les lecteurs malvoyants : chaque lettre se distingue, même projetée au fond d'une salle.
- **JetBrains Mono** (400, repli Cascadia Mono puis Consolas) : contenu brut du contexte et des sorties du modèle, en `{typography.code}`.
- Les trois familles sont sous licence OFL et servies en local depuis l'application (fichiers WOFF2 et `@font-face`) : aucune requête vers un service de polices (NFR-3, NFR-4). La maquette de référence les charge depuis Google Fonts ; l'application, non.

Rampe de base : `pane-title` 19 px, `heading` 18 px, `chat` 16 px, `body` 14 px, `pane-subtitle`, `body-sm` et `code` 13 px, `label` 12 px, `number` 14 px, `number-lg` 20 px ; aucun texte ne descend sous 12 px. `[ASSUMPTION]` Rampe dimensionnée pour la fenêtre utile de 1280×650. Aucune taille en px brut hors de la rampe dans `app.css` : les petites pièces (pastilles, icônes) sont en `em` et suivent la rampe.

**Mode projection** (story 34, NFR-9 ; `projection-toggle`) : la rampe × 9/7, arrondie, redéfinie dans `app.css` sous `:root.projection` (`tokens.css` reste le miroir exact de ce fichier). Les autres paliers passent par le zoom du navigateur.

| Rôle | Base | Projection |
|---|---|---|
| `pane-title` | 19 px | 24 px |
| `pane-subtitle`, `body-sm`, `code` | 13 px | 17 px |
| `heading` | 18 px | 23 px |
| `chat` | 16 px | 21 px |
| `body`, `number` | 14 px | 18 px |
| `label` | 12 px | 15 px |
| `number-lg` | 20 px | 26 px |
| `spacing.top-bar-height` | 56 px | 72 px (la barre reste sur une ligne) |
| `spacing.architecture-band-height` | 250 px | 320 px (le schéma et son bilan) |

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

`[ASSUMPTION]` L'en-tête de volet grandit (titre de 19 px et sous-titre) : le budget vertical dans 1280×650 est à vérifier à l'implémentation, les tokens d'espacement restant inchangés. Si la place manque, le sous-titre est le premier élément à masquer en mode projection, pas le contenu.

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
- `{rounded.full}` : jauge, badges, puces, interrupteurs, sélecteur de scénario, champ de saisie et bouton d'envoi.

Les bulles de message ont un coin de 6 px du côté du locuteur (bas droit pour l'utilisateur, bas gauche pour le modèle), pour se lire comme une conversation.

Le robot du modèle (`arch-model`) est dessiné avec les mêmes arrondis : corps et visière en rectangles très arrondis, oreilles et antenne en pilules. Pas d'angle vif dans le schéma.

Les nœuds réseau gardent le même rayon que les nœuds locaux : seule la bordure (continue ou en tirets) et la couleur changent, pour que la comparaison porte sur le lieu d'hébergement et rien d'autre.

## Components

Noms de composants identiques dans EXPERIENCE.md, section Component Patterns.

- **Fond de page (`page`)** : crème à pois, voir Layout & Spacing.
- **Barre haute (`top-bar`)** : carte flottante sur l'encre (story 33), haute de `{spacing.top-bar-height}` (56 px, pour loger la légende sous la jauge), rayon `{rounded.lg}`, relief `{colors.relief}`. Titre, chiffres de la jauge et statut en `{colors.on-ink}` ; anneau de focus `{colors.on-ink}` de 2 px (la liste « Volets ▾ », sur blanc, garde le sien). Les commandes gardent leur fond propre et ne passent jamais sur deux lignes. La jauge a une largeur fixe (barre et légende sur 300 px, la légende sur deux lignes au plus), pour que rien ne la fasse bouger ; sur une fenêtre étroite (1280 px), le nom du scénario et celui du modèle cèdent la place, entiers dans la liste et l'infobulle. De gauche à droite : sélecteur de scénario, jauge de contexte (élément le plus large), puces des volets masqués et menu « Volets ▾ », sélecteur de modèle, bouton « Mode projection » (`projection-toggle`), bouton Réinitialiser.
- **Volet (`pane`)** : carte blanche sans bordure, rayon `{rounded.lg}`, relief `{colors.relief}`. L'en-tête est un bandeau `{colors.surface}` séparé du contenu par un filet `{colors.line}` (story 33). En haut à gauche, le numéro de lecture (`pane-step`, story 34), puis le titre `pane-title` en encre et, dessous, le sous-titre pédagogique `pane-subtitle` en encre douce, qui dit en quelques mots ce que le volet montre :

  | Volet | Numéro | Sous-titre |
  |---|---|---|
  | Briques | — | Branchez des pièces sur le modèle |
  | Vue humain | 1 | Ce que voit l'utilisateur |
  | Contexte LLM | 2 | Ce que le modèle lit, dans l'ordre |
  | Orchestration | 3 | Ce que fait le harnais, pas à pas |
  | Schéma d'architecture | 4 | Où tourne chaque pièce |

  Un volet ne porte plus de cadre de sélection (story 34) : ses éléments liés portent le contour encre (`link-state`).
- **Numéro de volet (`pane-step`)** : disque `{colors.ink}` de 1,7 em, chiffre `number` en `{colors.on-ink}`, devant le titre des quatre volets de la démonstration, dans l'ordre de lecture ; caché aux lecteurs d'écran (le nom du volet ne change pas). Le panneau des briques, qui sert à régler, n'en a pas ; sous sa légende, une aide en `body-sm` encre douce, séparée par un filet `{colors.line}` : « Survolez une brique : elle s'éclaire dans le contexte, l'orchestration et le schéma. »
  En haut à droite, bouton ⛶ (mode focus) puis bouton « — » (`pane-hide-button`, masquer). Volet en mode focus : bordure `{colors.primary}`.
- **Puce de volet masqué (`pane-chip`)** : « + Nom du volet » sur violet doux, bordure en tirets violette. Quand le volet masqué contient un élément lié à la sélection, la puce porte un point encre et devient « + Nom · lié » (story 34) ; elle se tronque après les noms du scénario et du modèle.
- **Vue liée (`link-state`)** (story 34, d'après la maquette de refonte, `.hl`) : un élément liable porte ses clés (`data-links`). Survol ou focus : les éléments liés gardent leur opacité et prennent un anneau de `{spacing.stroke-min}` (un contour : l'ombre propre de l'élément, relief ou halo « en action », reste) de la couleur de leur discipline (`--discipline`), en encre pour le réseau et le neutre (le jaune et le gris n'atteignent pas 3:1 sur blanc) ; sur la plaque d'encre du modèle, l'anneau est `{colors.on-ink}`, à l'intérieur ; dans la jauge, encre, à l'intérieur. Les autres éléments liables passent à une opacité de 0,35 ; un conteneur qui contient un élément éclairé n'est pas estompé, et un élément dans un conteneur estompé ne l'est pas deux fois. Sélection : contour `{colors.ink}` de `{spacing.stroke-min}`, décalé de 2 px (à l'intérieur sur la plaque, en `{colors.on-ink}`), sans estomper le reste : l'estompage n'est jamais le seul signal. Transitions de 150 ms sur l'opacité, l'anneau et le contour, supprimées sous `prefers-reduced-motion`.
- **Menu Volets (`pane-menu`)** : bouton « Volets ▾ » ; liste déroulante des cinq volets avec case à cocher chacun.
- **Poignée de gouttière (`pane-resize-handle`)** : invisible au repos (on voit les pois de la page). Au survol ou au focus, une pilule violette de 4 × 32 px apparaît au milieu de la gouttière, avec le curseur ↔ ou ↕. Pendant le glissement, la pilule reste visible. La zone de saisie fait au moins `{spacing.hit-target-min}`, même si la gouttière visible reste à `{spacing.gutter}`.
- **Boutons (`button-primary`, `button-secondary`, `reset-button`, `button-danger`)** : primaire violet plein sur relief violet foncé, qui s'enfonce au clic (relief de 4 px à 1 px) ; secondaire contour violet sur relief actif ; Réinitialiser neutre et sans relief, pour ne pas attirer le clic par erreur. Danger (« Tout effacer » de la mémoire globale) : fond blanc, bordure `{colors.danger}` de `{spacing.stroke-min}`, texte encre, sans relief ; sa confirmation (« Oui, tout effacer ») est pleine, fond `{colors.danger}` et texte encre (≈ 5,4:1 ; le blanc sur ce rouge ne tient pas 4,5:1). Libellés en `label` Fredoka. Hauteur minimale `{spacing.hit-target-min}`.
- **Sélecteur de scénario (`scenario-picker`)** : pastille violet doux avec le nom du module et du scénario en cours.
- **Sélecteur de modèle (`model-picker`)** : liste déroulante neutre, nom du modèle et taille (ex. « 2B »).
- **Mode projection (`projection-toggle`)** (story 34, remplace le `text-size-control` « Aa 100 % », jamais construit) : bouton texte « Mode projection » sur la barre d'encre, fond transparent, texte `{colors.on-ink}`, bordure `{colors.on-ink-soft}`, `{rounded.md}` ; pressé (`aria-pressed="true"`), fond `{colors.on-ink}` et texte encre. Il agrandit toute la rampe (voir Typography).
- **Jauge de contexte (`context-gauge`)** : barre horizontale empilée, rayons pleins, sur une piste claire (`{colors.surface-raised}`, bordure `{colors.on-ink-soft}`) dans la barre foncée. Les groupes gardent l'ordre d'empilement de la palette catégorielle, mais chacun prend la couleur de sa discipline (`discipline` reçu de la session), séparé du suivant par un filet blanc de 1 px ; l'infobulle nomme le groupe, ses tokens et sa discipline (« Prompt système : 31 tokens · Prompt engineering » ; « Hors brique » (message, gabarit, tour du modèle) pour le neutre, même libellé que la légende). La discipline d'un groupe est celle qui porte le plus de tokens parmi ses segments (à égalité, la première dans l'ordre du contexte). Espace libre hachuré. Sous la barre, la légende (`#gauge-legend`, `discipline-legend`) : une pastille bordée `{colors.on-ink-soft}` et le nom de chaque discipline présente, dans l'ordre prompt, context, harness, puis « Hors brique » (message, gabarit, tour du modèle), en `label` `{colors.on-ink-soft}` ; elle passe à la ligne plutôt que d'être coupée, et ne donne pas de tokens par discipline. À droite : `number` « 1 840 / 4 096 tokens · 45 % » en `{colors.on-ink}`. Un marqueur vertical en encre indique le seuil d'alerte. Au dépassement, le pourcentage passe sur pastille rouge avec icône.
- **Détail de la jauge (`context-gauge-detail`)** : grille de cellules à la manière de `/context`, une cellule par tranche de tokens, colorée selon la palette catégorielle, cellules libres en crème hachuré. Légende à droite : pastille, nom du segment, tokens et pourcentage en `number`.
- **Segment de contexte (`context-segment`)** : bloc de texte brut en `{typography.code}`, filet latéral gauche de 4 px et fond doux de sa discipline (story 33, `data-discipline`), étiquette `label` en encre avec pastille de la couleur du type de segment (palette catégorielle) et nombre de tokens. Depuis la story 32, il ne sert plus qu'à la comparaison de tours ; Contexte LLM lit par section. Segment sélectionné : contour encre de 2 px.
- **Appel au modèle (`context-call`)** (story 32) : un bloc par appel, séparé du précédent par un filet `{colors.line}` de `{spacing.stroke-min}` ; titre « Appel i sur n » en `heading`, chiffres « Lu : … · évalués : … · produits : … » en `number` encre douce ; « Lu par le modèle » en `label` majuscule encre douce. Entre deux appels, la ligne du harnais en `body-sm` encre douce (⚙), avec le bouton de l'onglet du sous-agent après une délégation. En tête du volet, la bascule « Affichage du contexte » : trois pilules `label` bordées `{colors.line}`, la pressée sur l'encre, texte `{colors.on-ink}`. « Texte exact » : un `pre` en `code` sans filet, fond ni couleur.
- **Section de contexte (`context-section`)** (story 32) : une ligne en grille, marge (10 à 15 em) puis texte ; filet gauche de 4 px et fond doux de sa discipline (`data-discipline`, story 33) ; dans la marge, pour chaque section de la ligne, la pastille de son type (palette catégorielle) et son étiquette `label` encre. Texte en `{typography.code}`, un `span` par segment, gabarit (et syntaxe JSON du mode chat) en `{colors.ink-soft}`. Nouveau : filet de 8 px et badge « Nouveau » sur l'encre, texte `{colors.on-ink}`. Déjà lu : un `details` replié, fond `{colors.surface}`, bordure en tirets `{colors.line}`, résumé `label` encre douce. Sous 28rem de volet (requête de conteneur), la marge passe au-dessus du texte. Tailles par les jetons de la rampe ou en `em` : le mode projection (story 34) les agrandit.
- **Bloc produit (`produced-block`)** (story 32) : fond `{colors.produced-soft}` (réflexion : `{colors.reasoning-soft}`), filet gauche de 4 px `{colors.ink}`, `{rounded.md}` ; en tête, l'étiquette « Produit par le modèle » en pilule `{colors.ink}` / `{colors.on-ink}`, puis le type (« Réflexion », « Réponse », « Appel d'outil ») en `label` encre ; texte en `code`. Le produit n'a jamais un fond de discipline : on distingue d'un coup d'œil ce que le modèle a lu de ce qu'il a écrit.
- **Arbre JSON (`json-tree`)** (story 32) : en `code`, indenté de `{spacing.4}` sous un filet `{colors.line}` ; un `details` par objet ou tableau, ouvert par défaut, résumé « … } n clés » quand il est replié ; clés en `{colors.json-key}` (graisse 600), chaînes en `{colors.json-string}`, littéraux en `{colors.json-literal}`, ponctuation en encre douce. Le bouton « Texte exact » (`label`, bordé `{colors.line}`, pressé sur l'encre) montre la sous-chaîne envoyée sur blanc.
- **Panneau des briques** (story 33) : en tête, la légende des quatre disciplines (`discipline-legend` : « Prompt engineering », « Context engineering », « Harness engineering », « Sort du poste de travail » avec 🌐 dans sa pastille), puis deux groupes titrés en `label` majuscule encre douce, « Ce que le modèle lit » et « Ce que le harnais fait », selon le groupe que la session déclare pour chaque brique.
- **Carte de brique (`brick-card`)** : nom, interrupteur (`brick-toggle`), puce de catégorie (`category-chip` : « prompt engineering », « context engineering », « harness engineering », bordée et teintée de sa discipline), étiquette de lieu d'hébergement (`hosting-tag-local`, neutre), puce « 🌐 RÉSEAU » (`hosting-tag-network`) quand une option activée sort du poste, ligne d'état (`brick-status`, `body-sm`), explication dépliable. Relief `{colors.relief}`. Active : fond doux de sa discipline, trait gauche de 5 px de sa couleur, interrupteur coché de sa couleur, texte encre, relief `{colors.relief-active}`. Éteinte : grisée, fond `{colors.discipline-neutral-soft}`, trait `{colors.discipline-neutral}`, texte `{colors.ink-soft}`. Raisonnement imposé par le modèle : interrupteur coché et désactivé, 🔒 à côté. Indisponible : posée à plat (sans relief), bordure en tirets, texte encre douce, interrupteur désactivé, raison toujours visible en `{colors.ink-soft}`. Sous-option d'une brique éteinte ou indisponible : interrupteur désactivé, coché en `{colors.muted}` au lieu du violet (`brick-toggle.parent-off`), libellé et résumé en `{colors.ink-soft}`.
- **Tiroir d'édition (`edit-drawer`)** : panneau qui glisse par-dessus le panneau des briques pour éditer le prompt système ou la mémoire globale ; champ en `{typography.code}`. Confirmation d'enregistrement en `body-sm` encre, précédée de « ✓ ». Mémoire globale : en-tête (titre, croix « × » en bouton icône `{rounded.sm}` bordé `{colors.line}`), liste défilante, pied fixe séparé par un filet `{colors.line}` avec « Tout effacer » (`button-danger`) et « Fermer » (`button-secondary`) ; « Enregistrer » et « Supprimer » d'une entrée en actions compactes à plat, fond crème, bordure `{colors.line}`, `{rounded.sm}`.
- **Messages (`chat-message-user`, `chat-message-model`)** : bulles `{rounded.lg}` à coin de 6 px côté locuteur ; utilisateur sur l'encre, texte `{colors.on-ink}` (story 33), modèle sur blanc bordé. Typographie `chat`. Bloc de raisonnement (`reasoning-block`) replié sur crème, en `body-sm`.
- **Champ de saisie (`composer`)** : pilule en `chat`, bordure `{colors.line}`, `{colors.primary}` au focus ; bouton d'envoi primaire rond à droite.
- **Prompt suggéré (`suggested-prompt-chip`)** : puce contour violet au-dessus du champ de saisie.
- **Consigne du scénario (`scenario-guide`)** : `body-sm` encre douce, titre en violet foncé, coupée à 3 lignes ; « Afficher plus » / « Réduire » en lien souligné violet, `label`.
- **Onglets de Contexte LLM** (sous-agent) : libellés `label` sur un filet `{colors.line}` de 2 px ; onglet sélectionné en encre, souligné de 3 px `{colors.primary}`, les autres en encre douce.
- **Indicateur de travail (`working-indicator`)** : point vert pulsé, libellé de phase et chronomètre en `body-sm`.
- **Rail d'étapes (`turn-rail`, `turn-group`, `turn-step`)** : groupe de tour (`turn-group`) avec en-tête « Tour N » en `heading`, extrait du message en `body-sm` encre douce, statut en badge, chiffres en `number` ; les étapes sont reliées par un filet vertical `{colors.line}` de 2 px. Étape (`turn-step`) repliée, une frise sur deux rangées (story 34) : à gauche, sur les deux, la tuile `{rounded.sm}` porte la lettre de qui agit, en `label` (`M` modèle, `H` harnais, `U` utilisateur, `R` réseau) ; en haut, l'icône du type puis le titre en `label` (un verbe : « Décrit les outils », « Appelle le modèle », « Répond »…, le libellé de l'outil en encre douce après « · ») ; en dessous, le badge de déclenchement, l'acteur, « · via le réseau » en `label` encre douce pour un appel à un modèle hors du poste, puis « 🌐 RÉSEAU → adresse » ; à droite, le chiffre clé en `number` et le chevron ▸ / ▾. La rangée du dessous passe à la ligne plutôt que de couper le marqueur RÉSEAU ou l'acteur ; sur un rail étroit, le chiffre passe sous le reste. Icône par type (appel au modèle, demande d'outil, exécution, chargement de documentation, skill, hook, validation humaine, réinjection, réponse finale), toujours doublée du titre. La tuile prend la couleur de la discipline de l'étape (story 33) : encre, icône `{colors.on-ink}`, pour ce que fait le modèle (appel, demande d'outil, réponse finale) ; réseau pour une étape qui fait sortir des données du poste ; sinon la catégorie de la brique de l'étape, harness par défaut (fond doux, bordure de la couleur). Une étape en échec reste rouge. Étape courante : point vert ; étape sélectionnée : violet doux. Contenu interne sans relief.
- **Préparation du harnais (`harness-prep`)** : même traitement qu'un groupe de tour, titre « Préparation du harnais », sans relief.
- **Journal des événements (`event-log`)** : en-tête repliable en `label` avec chevron ; lignes en `body-sm`, nom technique en `{typography.code}` encre douce, JSON en `{typography.code}` sur crème. Aucune couleur d'état ni de segment.
- **Compteur de tokens (`token-counter`)** : nombres Fredoka tabulaires ; entrée, sortie, temps écoulé.
- **Badge de déclenchement (`trigger-badge-model`, `trigger-badge-user`)** : « Déclenché par le modèle » sur violet doux avec icône puce ; « Forcé par l'utilisateur » en contour encre avec icône main. La différence tient à l'icône et au libellé, pas seulement au style.
- **Bouton Forcer (`force-button`)** : contour encre, icône main, pour rappeler le badge « Forcé par l'utilisateur ».
- **Événement du harnais (`harness-event`)** : carte avec filet latéral épais et icône ; rouge pour blocage et échec, violet pour information (hook qui laisse passer, compression, limite d'appels atteinte).
- **Carte de dépassement (`overflow-card`)** : carte à bordure rouge de `{spacing.stroke-min}`, icône d'alerte, titre « Contexte dépassé — l'appel au modèle n'a pas été envoyé », compte de tokens en `number`, puis deux sous-parties titrées en `label` : « En production, un harnais pourrait » et « Pour continuer la démo ».
- **Données sortantes (`outbound-payload`)** : en-tête jaune « 🌐 RÉSEAU · Données sortantes » (étiquette et libellé en gras), puis méthode et adresse de destination ; bordure en tirets encre. Le corps a trois sections, chacune sous un libellé en `{typography.label}` `{colors.ink-soft}` : « Requête » (méthode et adresse), « En-têtes » (une ligne `Nom: valeur` par en-tête, dans l'ordre d'envoi) et « Corps » (texte exact, ou « Aucun corps : seule l'adresse sort du poste. »), en `{typography.code}`, avec retour à la ligne des longues valeurs (jamais de défilement horizontal). Une valeur masquée par le harnais (`outbound-masked`) s'affiche « [masqué] » en italique, `{colors.ink-soft}` sur `{colors.surface}`, avec une infobulle, et une note (`outbound-note`, `body-sm` `{colors.ink-soft}`) sous les en-têtes explique « [masqué] ». Dans l'aperçu H5, la section « En-têtes » est une note du même style : ils sont posés à l'envoi, si l'appel est accepté (story 23). Ce sont les en-têtes de la requête : ceux qu'ajoute le transport (proxy, HTTP/2) n'y sont pas.
- **Comparaison de tours (`turn-compare`)** : deux colonnes alignées segment par segment, écarts signalés par un signe (+ / −) et une valeur, jamais par la couleur seule.
- **Schéma d'architecture (`arch-zone-local`, `arch-zone-network`, `arch-boundary`, `arch-node-local`, `arch-node-network`, `arch-node-unavailable`, `arch-node-active`, `arch-flow`)** : deux zones séparées par la frontière verticale ; chaque nœud prend la couleur de la discipline de sa brique (`{brick}.*`, story 33), fond doux et trait continu de sa couleur ; les fichiers du harnais (`file.*`) sont neutres ; les nœuds réseau ont un fond jaune doux, des tirets encre, un trait jaune épais à gauche, le globe et « RÉSEAU » (zone). Processus local et fichier local se distinguent par l'icône (engrenage / document) et le libellé `[ASSUMPTION]`. Nœud indisponible : fond crème, tirets gris, icône barrée et raison. Nœud en action : halo vert. Flux : trait `{spacing.stroke-min}` encre douce, vert quand il est parcouru.
  - **Bac (`arch-group`)** : contenant blanc à bordure `{colors.line}` 2 px, `{rounded.md}`, sans relief ; titre `label` posé sur la bordure (icône, nom, nombre). Côté Réseau : fond crème.
  - **Forme par catégorie**, dans la couleur de la discipline : outil = tuile d'icône ronde à gauche du nom ; serveur MCP = double trait (local) ou double tirets (réseau), pastille « N outils » ; skill = filet gauche épais de 7 px ; fichier = fond neutre doux (`{colors.discipline-neutral-soft}`), icône document. Toutes gardent `{rounded.sm}` ; la maquette utilise des coins de 4 à 6 px sur skill et fichier, cette spine l'emporte.
  - **Bande des hooks (`arch-hook-strip`)** : dans le cadre Harnais, séparée du modèle par un tiret violet, étiquette pilule « Points d'accroche » ; hook en pièce à deux lignes (nom, point d'accroche), dans la couleur de la brique Hooks (harness engineering, story 33). En action : halo vert. Bloquant : filet rouge de 7 px et « ✖ a bloqué ». Désactivé : tirets gris.
  - **Tronc et rails (`arch-trunk`)** : trait `{spacing.stroke-min}` encre douce, en tirets après la frontière ; chemin parcouru en halo vert 7 px avec un trait encre au centre, en tirets animés quand il franchit la frontière. Marqueurs ✋ (violet, validation H5 en attente) et ✖ (rouge, blocage par un hook).
- **Harnais et modèle dans le schéma (`arch-harness`, `arch-model`)** : dans la zone locale, un cadre « Harnais » (bordure violette `{spacing.stroke-min}`, étiquette pilule violette en haut à gauche, relief `{colors.relief-active}`) entoure le modèle et liste en puces de la couleur de leur brique (story 33), avec leur icône, les briques actives sans composant externe (mémoire courte, prompt système) ; les autres briques sont représentées par leurs bacs et par la bande des hooks. Le robot et les puces s'empilent verticalement. Sans brique active, le cadre affiche « Aucune brique : LLM nu ». Au centre du cadre, le modèle est un **robot-mascotte** posé sur une plaque d'encre (story 33 ; de même la boîte du modèle cloud, bordée de tirets jaunes, et celle du modèle servi par un serveur local) : corps violet et oreilles violet foncé contournés de `{colors.on-ink}`, visière blanche, visage encre, nom « Modèle » en `label` `{colors.on-ink}` et nom du modèle chargé dessous en `{colors.on-ink-soft}`. Il signifie le modèle et rien d'autre : c'est la pièce autour de laquelle on branche le harnais. Trois poses, pilotées par l'état du tour :

  | Pose | Visage | Antenne |
  |---|---|---|
  | Au repos | yeux fermés | `{colors.muted}`, fixe |
  | Réfléchit (génération en cours) | yeux ouverts, trois points | `{colors.state-active}`, clignote |
  | Utilise un outil | sourire, pastille verte à clé | `{colors.state-active}`, clignote |

  L'antenne verte suit la règle du vert : elle ne s'allume que quand le modèle travaille. La pose est aussi dite par un libellé accessible (le robot est une image avec texte alternatif), jamais par l'antenne seule.
- **Pastilles des nœuds réseau** (story 34) : « contacté », « en échec » ou « non contacté » pour le dernier tour affiché, dans la pastille existante (`arch-node-pill`) ; « indisponible » l'emporte toujours ; l'infobulle dit « Au tour N : contacté. ».
- **Bilan des sorties (`schema-outbound`)** (story 34) : sous le schéma, dans son volet, une phrase en `body-sm` encre, séparée du schéma par un filet `{colors.line}` : « Au tour N, les données ont quitté le poste K fois : vers le modèle chez … et vers … ». Sans couleur ni icône : c'est un texte à lire à voix haute devant la salle.
- **Ligne de diagnostic (`diagnostic-row`)** : pastille d'état (vert « OK », rouge « Échec ») avec texte encre, libellé de la vérification, action corrective en dessous.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Une couleur = un sens : une couleur par discipline (prompt, context, harness), jaune pour ce qui sort du poste, vert pour « en action / OK », rouge pour « bloqué / échec » | Utiliser le jaune comme avertissement générique, ou le violet pour dire « local » |
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
| Distinguer les catégories du schéma (outil, serveur, skill, fichier) par le bac, la forme et l'icône ; la couleur dit la discipline de la brique | Donner une couleur à chaque catégorie de composant |
| Le robot représente le modèle, et seulement lui | Robot comme décoration, sur un autre composant ou dans un état sans rapport avec le modèle |
| Animations réservées au signal « en action » (pouls, flux, antenne) et au fondu de 150 ms de la vue liée, coupées sous `prefers-reduced-motion` | Curseur personnalisé, révélations au scroll, compteurs animés de la charte vitrine, robot animé au repos |
| Chaque couleur par un jeton de `tokens.css`, prêt pour un second thème (story 31) | Couleur écrite en dur (`#hex`, `rgb(`, `hsl(`) dans `app.css` ou `app.js` |
