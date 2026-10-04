---
title: DESIGN — WaveStack
status: draft
created: 2026-09-22
updated: 2026-10-04
sources:
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
  - ../../prds/prd-agentic-harness-training-demo-2026-09-22/addendum.md
name: WaveStack
description: Démonstrateur pédagogique local de harnais agentique, à la charte Wavestone, dans une direction « atelier de construction » pensée pour la projection. Deux thèmes, clair et sombre, « Système » par défaut (story 31).
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
  # Rôles (story 31) : ceux qui divergent en sombre ; en clair, la valeur d'avant la story
  ink-fill: '#0A0A14'
  ink-fill-edge: '#0A0A14'
  on-discipline: '#FFFFFF'
  on-vivid: '#0A0A14'
  warning-soft: '#FFF4D6'
  danger-soft: '#FDE8EB'
  # Lot 3 du 2026-10-04 : tuile des logos d'éditeurs, blanche dans les deux thèmes
  logo-tile: '#FFFFFF'
  # Thème sombre (story 31) : un jumeau `{clé}-dark` par couleur, mêmes rôles, dessiné jeton
  # par jeton (voir Colors > Thème sombre). tokens.css le pose sous `[data-theme="dark"]` et
  # sous `prefers-color-scheme: dark` sans attribut, sous le nom de la clé claire.
  primary-dark: '#9C86FF'
  primary-deep-dark: '#C9BDFF'
  primary-soft-dark: '#2A2350'
  accent-dark: '#04F06A'
  accent-soft-dark: '#0F3A24'
  ink-dark: '#ECEBF5'
  ink-soft-dark: '#B4B3C7'
  muted-dark: '#8A8A9E'
  line-dark: '#3A394F'
  surface-dark: '#12121C'
  surface-raised-dark: '#1E1D2C'
  warning-dark: '#FFCA4A'
  danger-dark: '#FF6B7F'
  on-primary-dark: '#0E0B1E'
  relief-dark: '#2A2156'
  relief-active-dark: '#3A2E78'
  dot-dark: '#262538'
  hosting-network-dark: '#FFCA4A'
  hosting-boundary-dark: '#ECEBF5'
  state-active-dark: '#04F06A'
  state-ok-dark: '#04F06A'
  state-blocked-dark: '#FF6B7F'
  state-error-dark: '#FF6B7F'
  state-unavailable-dark: '#8A8A9E'
  segment-system-prompt-dark: '#8C74FF'
  segment-global-memory-dark: '#3CC878'
  segment-tool-descriptions-dark: '#4F95EA'
  segment-history-dark: '#A48EF0'
  segment-rag-dark: '#1FB3A2'
  segment-tool-results-dark: '#F08A42'
  segment-message-dark: '#C07FDA'
  segment-free-dark: '#2A2938'
  discipline-prompt-dark: '#9C86FF'
  discipline-prompt-soft-dark: '#262047'
  discipline-context-dark: '#2FB8A3'
  discipline-context-soft-dark: '#12302B'
  discipline-harness-dark: '#E8639F'
  discipline-harness-soft-dark: '#3A1A2B'
  discipline-network-dark: '#E8B516'
  discipline-network-soft-dark: '#3A3010'
  discipline-neutral-dark: '#8A8A9E'
  discipline-neutral-soft-dark: '#26252F'
  on-ink-dark: '#FFFFFF'
  on-ink-soft-dark: '#CFCDE4'
  produced-soft-dark: '#1A2335'
  reasoning-soft-dark: '#2A2618'
  json-key-dark: '#9DBBFF'
  json-string-dark: '#F2A77E'
  json-literal-dark: '#6FD3E3'
  ink-fill-dark: '#33257A'
  ink-fill-edge-dark: '#7C6AD6'
  on-discipline-dark: '#0E0B1E'
  on-vivid-dark: '#0A0A14'
  warning-soft-dark: '#3A3010'
  danger-soft-dark: '#3A1820'
  logo-tile-dark: '#FFFFFF'
typography:
  # Base ; le mode projection (story 34, NFR-9) multiplie toute la rampe par 9/7, dans app.css.
  # Story 2 of 2026-09-30: a notch lower (19 → 18 px), under the shared bar.
  pane-title:
    fontFamily: 'Fredoka, system-ui, sans-serif'
    fontSize: 18px
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
    model: '{colors.ink-fill}'
    on-model: '{colors.on-ink}'
    on-color: '{colors.on-discipline}' # texte sur prompt, context et harness
    on-color-vivid: '{colors.on-vivid}' # texte sur network et neutral
  discipline-legend:
    swatch-border: '{colors.ink-soft}'
    swatch-border-on-ink: '{colors.on-ink-soft}'
    foreground: '{colors.ink-soft}'
    foreground-on-ink: '{colors.on-ink-soft}'
    typography: '{typography.label}'
  # Story 2 of 2026-09-30: the shared bar at the head of the five pages (pages.css).
  site-nav:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    radius: '{rounded.lg}'
    brand-typography: '{typography.heading}'
    link-typography: '{typography.label}'
    link-foreground: '{colors.ink-soft}'
    current-foreground: '{colors.ink}'
    current-underline: '{colors.primary}'
    focus-ring: '{colors.primary}'
    # Fixed: `spacing.hit-target-min` + 2 × `spacing.1` + its border (`--site-nav-height`, 42 px).
    height: 'calc({spacing.hit-target-min} + 2 * {spacing.1} + 2px)'
  # Its historical name kept: since story 2 of 2026-09-30, the main screen's bar under the panes.
  top-bar:
    background: '{colors.ink-fill}'
    foreground: '{colors.on-ink}'
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
    background: '{colors.ink-fill}'
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
    confirmed-foreground: '{colors.on-vivid}'
  scenario-picker:
    background: '{colors.primary-soft}'
    foreground: '{colors.primary-deep}'
    radius: '{rounded.full}'
  model-picker:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.md}'
  # Story 31: « ◐ Système », « ☀ Clair », « ☾ Sombre », a native select like model-picker, in
  # the « Affichage ▾ » menu (languages 2/5), at the right of the shared bar of the five pages
  # since story 2 of 2026-09-30.
  theme-picker:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    focus-ring: '{colors.on-ink}'
    page-focus-ring: '{colors.primary}'
    radius: '{rounded.md}'
    typography: '{typography.label}'
    min-height: '{spacing.hit-target-min}'
  # Story 34: replaces the « Aa » text-size-control, never built; in « Affichage ▾ » of the
  # main screen (languages 2/5, story 2 of 2026-09-30), on surface-raised.
  projection-toggle:
    background: transparent
    foreground: '{colors.ink}'
    border: '{colors.line}'
    pressed-background: '{colors.primary}'
    pressed-foreground: '{colors.on-primary}'
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
  # Story 26: « Fenêtre ▾ » on the ink top bar (as projection-toggle), and its panel (as the
  # « Volets ▾ » list, on white); no new token.
  window-picker:
    toggle-background: transparent
    toggle-foreground: '{colors.on-ink}'
    toggle-border: '{colors.on-ink-soft}'
    toggle-expanded-background: '{colors.on-ink}'
    toggle-expanded-foreground: '{colors.ink-fill}'
    panel-background: '{colors.surface-raised}'
    panel-foreground: '{colors.ink}'
    panel-border: '{colors.line}'
    panel-shadow: '{colors.relief}'
    radius: '{rounded.md}'
    choice-border: '{colors.line}'
    choice-picked-border: '{colors.primary}'
    choice-picked-background: '{colors.primary-soft}'
    detail-foreground: '{colors.ink-soft}'
    refusal-rule: '{colors.danger}'
    refusal-foreground: '{colors.ink}'
    focus-ring: '{colors.primary}'
    typography: '{typography.body-sm}'
    figure-typography: '{typography.number}'
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
    overflow-foreground: '{colors.on-vivid}'
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
    mode-pressed-background: '{colors.ink-fill}'
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
    new-badge-background: '{colors.ink-fill}'
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
    tag-background: '{colors.ink-fill}'
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
    foreground: '{colors.on-vivid}'
    border: '{colors.ink}'
    border-style: dashed
    radius: '{rounded.full}'
  edit-drawer:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    shadow: '{colors.relief}'
    radius: '{rounded.lg}'
  chat-message-user:
    background: '{colors.ink-fill}'
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
    model-tile: '{colors.ink-fill}'
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
    header-foreground: '{colors.on-vivid}'
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
    label-background: '{colors.hosting-network}'
    label-color: '{colors.on-vivid}'
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
    plate: '{colors.ink-fill}'
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
  # Story 31: the page on tokens.css; a row's background says its state, a result its rule.
  diagnostic-row:
    background: '{colors.surface-raised}'
    ok-background: '{colors.accent-soft}'
    warning-background: '{colors.warning-soft}'
    error-background: '{colors.danger-soft}'
    cloud-background: '{colors.discipline-network-soft}'
    cloud-border: '{colors.hosting-boundary}'
    ok-badge: '{colors.state-ok}'
    error-badge: '{colors.state-error}'
    badge-foreground: '{colors.on-vivid}'
    result-rule-width: '{spacing.1}'
    # Story 3 of 2026-09-30: rows and cloud cards on the ramp, sized by the tokens only.
    radius: '{rounded.md}'
    search-border: '{colors.ink-soft}'
    search-bar: '{colors.primary}'
  # Lot 3 of 2026-10-04: the merged « Diagnostic et modèles » page (/diagnostic). One card per
  # GGUF file, served model or cloud model, in a grid grouped Local then Cloud, then publisher.
  model-card:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    secondary-foreground: '{colors.ink-soft}'
    border: '{colors.line}'
    hover-border: '{colors.ink-soft}'
    shadow: '{colors.relief}'
    radius: '{rounded.md}'
    padding: '{spacing.4}'
    gap: '{spacing.4}'
    min-width: 250px
    name-typography: '{typography.body}'
    size-typography: '{typography.number-lg}'
    params-typography: '{typography.body-sm}'
    active-border: '{colors.ink}'
    active-border-width: 3px
    active-shadow: '{colors.state-active}'
    unusable-background: '{colors.danger-soft}'
    unusable-size-foreground: '{colors.ink-soft}'
    cloud-background: '{colors.discipline-network-soft}'
    cloud-border: '{colors.hosting-boundary}'
    cloud-border-style: dashed
    cloud-border-width: 2px
    sources-chip-background: '{colors.surface}'
    sources-chip-foreground: '{colors.ink}'
    sources-chip-border: '{colors.ink-soft}'
  model-card-expanded:
    border: '{colors.primary}'
    border-width: 2px
    padding: '{spacing.5}'
    name-typography: '{typography.heading}'
    section-title-typography: '{typography.label}'
    section-title-foreground: '{colors.ink-soft}'
    divider: '{colors.line}'
    path-typography: '{typography.code}'
    path-background: '{colors.surface}'
    message-rule-width: '{spacing.1}'
    message-ok-rule: '{colors.state-ok}'
    message-warning-rule: '{colors.ink-soft}'
    message-error-rule: '{colors.state-error}'
    source-row-background: '{colors.surface}'
    source-row-border: '{colors.line}'
    source-row-radius: '{rounded.sm}'
    source-active-border: '{colors.ink}'
  # A light tile in both themes, so that dark marks (OpenAI, Llama) stay readable in dark mode.
  model-logo:
    background: '{colors.logo-tile}'
    border: '{colors.line}'
    radius: '{rounded.sm}'
    size: 48px
    size-expanded: 64px
    size-group: 28px
    initial-background: '{colors.primary-soft}'
    initial-foreground: '{colors.primary}'
    initial-border: '{colors.relief}'
    initial-typography: '{typography.pane-title}'
  # A dot and a label; colour never carries the state alone, and never yellow (yellow = network).
  state-pill:
    background: '{colors.surface}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.full}'
    typography: '{typography.label}'
    dot-size: 12px
    dot-border: '{colors.ink-soft}'
    active-background: '{colors.accent-soft}'
    active-dot: '{colors.state-active}'
    ok-background: '{colors.accent-soft}'
    ok-dot: '{colors.state-ok}'
    error-background: '{colors.danger-soft}'
    error-dot: '{colors.state-error}'
    unavailable-foreground: '{colors.ink-soft}'
    unavailable-dot: '{colors.state-unavailable}'
    unavailable-dot-style: dashed
  publisher-group-header:
    foreground: '{colors.ink}'
    count-foreground: '{colors.ink-soft}'
    typography: '{typography.pane-title}'
    gap: '{spacing.3}'
  checks-panel:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    radius: '{rounded.md}'
    summary-foreground: '{colors.ink-soft}'
    min-height: 44px
  models-filters:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    radius: '{rounded.md}'
    label-typography: '{typography.label}'
    segment-selected-background: '{colors.primary}'
    segment-selected-foreground: '{colors.on-primary}'
  # Story 29: the « LLM nu » screen (/llm). A token: two alternating existing grounds, its id
  # beneath; a special token dashed in the harness colour and named « spécial ».
  token-chip:
    background: '{colors.primary-soft}'
    background-alt: '{colors.accent-soft}'
    foreground: '{colors.ink}'
    id-foreground: '{colors.ink-soft}'
    border: '{colors.line}'
    special-background: '{colors.surface-raised}'
    special-border: '{colors.discipline-harness}'
    special-border-style: dashed
    text-typography: '{typography.code}'
    id-typography: '{typography.number}'
    radius: '{rounded.sm}'
  # Story 29: text → tokens → ids → the embedding table's row → the vector → the layers.
  embedding-diagram:
    background: '{colors.surface}'
    step-background: '{colors.surface-raised}'
    step-border: '{colors.ink-soft}'
    step-name-typography: '{typography.label}'
    step-value-typography: '{typography.number-lg}'
    picked-cell: '{colors.primary}'
    cell: '{colors.line}'
    unknown-foreground: '{colors.ink-soft}'
    radius: '{rounded.sm}'
---

# WaveStack — Design Spine

## Brand & Style

WaveStack est un tableau de démonstration, pas une vitrine. Il vit dans une salle de formation, projeté sur un écran qu'on ne choisit pas, ou sur l'écran d'un EliteBook tourné vers trois personnes. Son esthétique sert une seule chose : que la salle voie ce que le harnais fait au modèle.

**Direction « atelier de construction ».** Le harnais se construit brique par brique autour du modèle ; l'interface le dit par sa forme. Elle ressemble à un jeu de construction posé sur un cahier : pièces aux grands arrondis, relief de jouet par une ombre pleine, fond de page à pois. Le modèle est un petit robot, et le harnais, tout ce qu'on branche autour de lui. Chaque volet porte sous son titre une phrase qui dit ce qu'il montre (« Ce que le modèle lit »). Le ton est ludique, mais l'écran reste un outil : le jeu sert la lecture en projection, jamais l'inverse. Référence : maquette canvas « WaveStack, refonte ludique » ([planches Écran principal et Planche de style](https://claude.ai/artifact/7fM7Cy2UiEnPXiNGvtX7Sq)). Cette spine l'emporte sur la maquette en cas d'écart, notamment sur les couleurs (voir Colors).

L'identité reste celle de la charte Wavestone : violet ancre, vert en unique accent secondaire, crème, encre. L'information est dense mais rangée. Les couleurs vives ont chacune un rôle précis : violet = marque et prompt engineering, vert d'eau = context engineering, framboise = harness engineering, jaune = ce qui sort du poste, vert = « en train d'agir » et « OK », rouge = « bloqué / en échec ». Les éléments clés (barre de l'atelier, message de l'utilisateur, ce que fait le modèle) reposent sur l'encre (story 33, maquette de refonte du 2026-09-28). Le fond à pois est la seule ornementation, et il reste derrière les volets.

Les composants vitrine de la charte (curseur personnalisé, révélations au scroll, compteurs animés) ne s'appliquent pas : une application qui s'anime pour elle-même vole l'attention que la démonstration doit capter.

Deux thèmes, clair et sombre (story 31), au choix du formateur par un sélecteur « ◐ Système », « ☀ Clair », « ☾ Sombre » (`theme-picker`, dans le menu « Affichage ▾ » de la barre commune des cinq pages) ; « Système » par défaut suit le réglage du poste. Le clair reste le plus robuste en projection dans une salle éclairée ; le sombre sert le poste réglé en sombre, la visio du soir ou la salle sans lumière. Chaque couleur passe par une variable de `tokens.css`, jamais écrite en dur dans une page, une feuille ou un script de `static/` (`tests/test_web_tokens.py`) ; la palette sombre redéfinit les mêmes variables, dessinée jeton par jeton (voir Colors > Thème sombre), jamais calculée ni inversée.

## Colors

**Charte Wavestone.**
- **Violet (`#451DC7`)** : couleur ancre, celle de la marque et du prompt engineering (`discipline-prompt` a la même valeur). Boutons primaires, cadre du harnais, focus. Il ne dit plus le lieu d'hébergement local (story 33). Contraste 9,3:1 sur blanc.
- **Violet foncé (`#250F6B`)** : texte sur fonds violet doux (puces de catégorie, badge « déclenché par le modèle »).
- **Violet doux (`#EDE7FE`)** : fond d'étape sélectionnée, de puce de volet et de sélecteur de scénario. La brique active et le message de l'utilisateur ont quitté ce fond (story 33).
- **Vert (`#04F06A`)** : seul accent secondaire. Réservé à « composant en cours d'action » (halo, flux animé, étape courante) et à « diagnostic OK ». Contraste 1,5:1 sur blanc : jamais en texte ni en trait fin isolé, toujours en fond ou halo avec texte encre (12,8:1).
- **Vert clair (`#CAFEE0`)** : réserve de la charte, sans usage assigné en V1.
- **Encre (`#0A0A14`)**, **encre douce (`#4A4A5E`)** : texte principal et secondaire. Le fond des éléments clés (story 33) passe par le jeton de rôle `ink-fill` (story 31), de même valeur en clair : barre de l'atelier, bulle de l'utilisateur, tuile d'une étape du modèle, plaque du modèle dans le schéma, numéro de volet, étiquettes « Nouveau » et « Produit par le modèle », pilule pressée. L'encre de la charte reste en place, pas celle de la maquette (`#1A1733`).
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
| Modèle | `ink-fill` | `ink-fill` | tuiles des appels, demandes d'outil et réponses finales ; plaque du modèle |

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

Les trois couleurs JSON sont mesurées sur les deux fonds produits, sur `surface-raised` et sur chaque fond doux de discipline (une section lue), dans les deux thèmes. Ce sont des couleurs de texte seulement. Leurs jumeaux sombres sont éclaircis (voir Thème sombre).

**Couleurs d'état** `[ASSUMPTION]`.
- `{colors.state-active}` (vert) : composant en cours d'action, étape courante, diagnostic OK.
- `{colors.state-blocked}` / `{colors.state-error}` (rouge) : blocage par un hook, échec de parsing, dépassement du contexte, diagnostic en échec. Rouge sur blanc = 3,7:1 : utilisé en fond de pastille avec texte `{colors.on-vivid}` (5,3:1), en filet latéral épais ou en icône, jamais en petit texte.
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

### Thème sombre (story 31)

Une palette dessinée, jeton par jeton : chaque clé de `colors` a son jumeau `{clé}-dark` dans le frontmatter (le test l'exige, dans les deux sens). `tokens.css` pose ces valeurs sous les noms clairs, sous `:root[data-theme="dark"]` (choix « Sombre ») et sous `@media (prefers-color-scheme: dark) { :root:not([data-theme]) }` (« Système » sur un poste sombre) ; `color-scheme` suit (`light`, puis `dark`), pour que les contrôles natifs (listes, barres de défilement, `dialog`) prennent le thème. Aucun `filter: invert`, aucune couleur calculée en JS.

**Jetons de rôle.** Certains jetons jouaient deux rôles qui divergent en sombre : l'encre, texte et fond ; `on-ink`, texte sur l'encre et sur les couleurs de discipline ; `ink`, texte sur les fonds vifs. Chaque rôle a son jeton : `ink-fill`, son bord `ink-fill-edge`, `on-discipline` et `on-vivid` reprennent en clair la valeur d'avant (`tests/test_web_tokens.py` le vérifie). `warning-soft` et `danger-soft` sont des valeurs nouvelles : elles remplacent les fonds écrits en dur dans la page de diagnostic.

| Jeton | Rôle | Clair | Sombre |
|---|---|---|---|
| `ink-fill` | fond des éléments clés (barre de l'atelier, bulle de l'utilisateur, étapes et plaque du modèle, numéro de volet, étiquettes « Nouveau » et « Produit », pilule pressée) | `#0A0A14` | `#33257A` (violet profond) |
| `ink-fill-edge` | bord de ces éléments (liseré de la barre, de la bulle, du numéro et de la plaque ; bordure des tuiles du modèle) : en sombre, `ink-fill` ne fait que 1,3 à 1,5:1 sur la page | `#0A0A14` | `#7C6AD6` |
| `on-discipline` | texte sur prompt, context ou harness | `#FFFFFF` | `#0E0B1E` |
| `on-vivid` | texte sur jaune, vert, rouge ou gris neutre | `#0A0A14` | `#0A0A14` |
| `warning-soft` | fond d'avertissement du diagnostic | `#FFF4D6` | `#3A3010` |
| `danger-soft` | fond d'échec du diagnostic | `#FDE8EB` | `#3A1820` |

**Palette** (clair → sombre). Les fonds deviennent des bleu-nuit teintés de violet, les textes des gris lilas clairs ; les couleurs vives gardent leur rôle, éclaircies là où elles portent un texte ou un trait sur fond sombre.

| Groupe | Jeton | Clair | Sombre |
|---|---|---|---|
| Charte | `primary`, `primary-deep`, `primary-soft` | `#451DC7`, `#250F6B`, `#EDE7FE` | `#9C86FF`, `#C9BDFF`, `#2A2350` |
| Charte | `accent`, `accent-soft` | `#04F06A`, `#CAFEE0` | `#04F06A`, `#0F3A24` |
| Charte | `ink`, `ink-soft`, `muted`, `line` | `#0A0A14`, `#4A4A5E`, `#8A8A9E`, `#E6E6EC` | `#ECEBF5`, `#B4B3C7`, `#8A8A9E`, `#3A394F` |
| Charte | `surface`, `surface-raised` | `#F6F5FA`, `#FFFFFF` | `#12121C`, `#1E1D2C` |
| Charte | `warning`, `danger`, `on-primary` | `#FFCA4A`, `#FF2A49`, `#FFFFFF` | `#FFCA4A`, `#FF6B7F`, `#0E0B1E` |
| Relief | `relief`, `relief-active`, `dot` | `#D9D0F6`, `#C9BCF5`, `#D6CCF5` | `#2A2156`, `#3A2E78`, `#262538` |
| Hébergement | `hosting-network`, `hosting-boundary` | `#FFCA4A`, `#0A0A14` | `#FFCA4A`, `#ECEBF5` |
| États | `state-active`, `state-ok` | `#04F06A` | `#04F06A` |
| États | `state-blocked`, `state-error`, `state-unavailable` | `#FF2A49`, `#FF2A49`, `#8A8A9E` | `#FF6B7F`, `#FF6B7F`, `#8A8A9E` |
| Segments | `system-prompt`, `global-memory`, `tool-descriptions`, `history` | `#6B4EE6`, `#27B060`, `#2A78D6`, `#B39CF7` | `#8C74FF`, `#3CC878`, `#4F95EA`, `#A48EF0` |
| Segments | `rag`, `tool-results`, `message`, `free` | `#0E8C7E`, `#E0762B`, `#9C5BB5`, `#F6F5FA` | `#1FB3A2`, `#F08A42`, `#C07FDA`, `#2A2938` |
| Disciplines | prompt, context, harness | `#451DC7`, `#0F7B6C`, `#B8327A` | `#9C86FF`, `#2FB8A3`, `#E8639F` |
| Disciplines | network, neutral | `#D9A400`, `#8A8A9E` | `#E8B516`, `#8A8A9E` |
| Fonds doux | prompt, context, harness | `#EEE9FC`, `#E2F3EF`, `#FBE7F1` | `#262047`, `#12302B`, `#3A1A2B` |
| Fonds doux | network, neutral | `#FFF5D1`, `#EFEFF4` | `#3A3010`, `#26252F` |
| Sur encre | `on-ink`, `on-ink-soft` | `#FFFFFF`, `#CFCDE4` | `#FFFFFF`, `#CFCDE4` |
| Contexte LLM | `produced-soft`, `reasoning-soft` | `#E8EEF7`, `#F3EFE3` | `#1A2335`, `#2A2618` |
| Contexte LLM | `json-key`, `json-string`, `json-literal` | `#1E3A8A`, `#7A3410`, `#0B5E73` | `#9DBBFF`, `#F2A77E`, `#6FD3E3` |

**Contrastes** (calcul WCAG), valables dans les deux palettes ; valeurs en sombre. `tests/test_web_tokens.py` vérifie chaque paire au seuil dans les deux palettes (`_THEME_PAIRS`), les valeurs exactes en sombre (`_DARK_RATIOS`) et chaque plancher « ≥ » en sombre (`_DARK_FLOORS`) :

| Paire | Sombre | Seuil |
|---|---|---|
| `ink` et `ink-soft` sur `surface`, `surface-raised`, `primary-soft`, `accent-soft`, `warning-soft`, `danger-soft` et chaque fond doux de discipline | ≥ 6,2 | 4,5 |
| `primary` sur `surface-raised` | 5,7 | 4,5 |
| `primary-deep` sur `primary-soft` | 8,4 | 4,5 |
| `on-primary` sur `primary` | 6,7 | 4,5 |
| `on-ink` et `on-ink-soft` sur `ink-fill` | 12,5 et 8,0 | 4,5 |
| `on-discipline` sur prompt, context et harness | 6,7, 7,8 et 6,2 | 4,5 |
| `on-vivid` sur `hosting-network`, `warning`, `discipline-network`, `discipline-neutral`, `state-active`, `accent`, `danger` et `state-error` | ≥ 5,8 | 4,5 |
| prompt, context, harness et neutral sur `surface` et `surface-raised` | ≥ 4,9 | 3 |
| `ink` et `ink-soft` sur `produced-soft` et `reasoning-soft` | ≥ 7,4 | 4,5 |
| `json-key`, `json-string`, `json-literal` sur les fonds de la story 32 | ≥ 6,6 | 4,5 |
| `on-ink-soft` (bordure des commandes de la barre) sur `ink-fill` | 8,0 | 3 |
| `ink-fill-edge` sur `surface` et `surface-raised` | ≥ 3,9 | 3 |

En sombre seulement, car le clair échoue déjà et c'est documenté plus haut : `danger` en texte sur `surface-raised` (6,0), et chaque segment sur `segment-free` (au moins 4,1, seuil 3).

- **Texte sur rouge.** `on-vivid` dans les deux thèmes, comme le prescrit la règle « rouge : texte encre » : la pastille de débordement de la jauge et une tuile d'étape du modèle en échec passent du blanc, 3,7:1, à l'encre, 5,3:1.
- **Retouches acceptées du thème clair.** L'atelier ne change pas, sauf : le texte sur rouge (ci-dessus) ; une tuile du modèle en attente (H5), dont la lettre passe du blanc à l'encre sur violet doux ; les bordures des commandes de la barre, `on-ink-soft` au lieu de `line` ou `primary-soft` (quasi identiques sur l'encre) ; le sélecteur de thème, nouveau, et, sous 1400 px, sa forme compacte ; en mode projection sous 1400 px, les largeurs minimales des sélecteurs de scénario (4,5 → 3,5 rem) et de modèle (4 → 3 rem), pour lui faire place. La page de diagnostic passe aux jetons : fond `surface`, fonds de ligne `accent-soft`, `warning-soft` et `danger-soft` (au lieu de verts, oranges et roses écrits en dur), modèle cloud sur `discipline-network-soft`, étiquettes « RÉSEAU » et « Local » comme dans l'atelier (jaune de charte ; neutre au lieu du violet), résultats en encre derrière un filet d'état.
- **Fonds vifs.** Un jaune, un vert, un rouge ou le gris neutre sous un texte porte un `color` explicite (`on-vivid`) : un texte hérité deviendrait clair en sombre.
- **Robot.** Sur sa plaque `ink-fill` (violet profond), la visière `surface-raised` et le visage `ink` s'inversent d'eux-mêmes : écran sombre, yeux clairs. Aucun jeton propre au robot.
- **Relief.** Les reliefs sombres sont des violets profonds, plus clairs que le fond ; l'ombre pleine du bouton primaire (`primary-deep`) devient un relief clair, comme le reste.
- **Jaune.** Il garde sa valeur (le jaune de discipline s'éclaircit à `#E8B516`) et reste toujours doublé de « RÉSEAU » ou du globe.

## Typography

- **Fredoka** (graisses 500 et 600) : titres de volet (`pane-title`), titres (`heading`), étiquettes (`label`) et nombres (`number`, `number-lg`). Ses formes rondes portent le ton « jeu de construction ». Chiffres tabulaires (`font-variant-numeric: tabular-nums`) pour que les compteurs de tokens ne sautent pas pendant la mise à jour. `[ASSUMPTION]` Le fichier servi doit contenir la fonction OpenType `tnum` ; sinon, chaque compteur reçoit une largeur fixe.
- **Atkinson Hyperlegible** (400 et 700) : voix de l'interface, messages, explications, sous-titres de volet. Dessinée pour les lecteurs malvoyants : chaque lettre se distingue, même projetée au fond d'une salle.
- **JetBrains Mono** (400, repli Cascadia Mono puis Consolas) : contenu brut du contexte et des sorties du modèle, en `{typography.code}`.
- Les trois familles sont sous licence OFL et servies en local depuis l'application (fichiers WOFF2 et `@font-face`) : aucune requête vers un service de polices (NFR-3, NFR-4). La maquette de référence les charge depuis Google Fonts ; l'application, non.

Rampe de base : `pane-title` 18 px (19 px jusqu'à la story 2 du 2026-09-30 : un cran plus bas sous la barre commune), `heading` 18 px, `chat` 16 px, `body` 14 px, `pane-subtitle`, `body-sm` et `code` 13 px, `label` 12 px, `number` 14 px, `number-lg` 20 px ; aucun texte ne descend sous 12 px. `[ASSUMPTION]` Rampe dimensionnée pour la fenêtre utile de 1280×650. Aucune taille en px brut hors de la rampe dans `app.css` : les petites pièces (pastilles, icônes) sont en `em` et suivent la rampe.

**Mode projection** (story 34, NFR-9 ; `projection-toggle`) : la rampe × 9/7, arrondie, redéfinie dans `app.css` sous `:root.projection` (`tokens.css` reste le miroir exact de ce fichier). Les autres paliers passent par le zoom du navigateur.

| Rôle | Base | Projection |
|---|---|---|
| `pane-title` | 18 px | 23 px |
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
- barre commune (`site-nav`, story 2 du 2026-09-30) en tête, sur toute la largeur : la marque et les pages, le menu « Affichage ▾ » à droite ;
- barre de l'atelier (`top-bar`) de `{spacing.top-bar-height}` sur toute la largeur, **en bas de l'écran**, sous les volets ;
- colonne de gauche sur toute la hauteur : panneau des briques (`{spacing.brick-panel-width}`) ;
- à droite, rangée du haut : vue humain, Contexte LLM, Orchestration ; Contexte LLM et Orchestration se partagent à parts égales la largeur restante ;
- à droite, bande basse sous ces trois volets : schéma d'architecture, `{spacing.architecture-band-height}`. `[ASSUMPTION]` Ce token vaut 250 px depuis la story 8e (bacs par catégorie et bande des hooks), au lieu de 200 px, dans ce fichier comme dans `tokens.css`. À 1280×650, la rangée du haut perd 50 px ; si c'est trop juste, le formateur masque un volet, passe le schéma en mode focus ou redimensionne les volets.

Un volet masqué libère sa place : les volets visibles de la même rangée se la partagent ; si le panneau des briques est masqué, les autres volets prennent toute la largeur ; si le schéma est masqué, la rangée du haut prend toute la hauteur. Les gouttières sont aussi des poignées de redimensionnement (`pane-resize-handle`, voir Components). Le mode focus redistribue la grille sans changer l'ordre des volets (voir EXPERIENCE.md). Le comportement par taille d'écran est dans EXPERIENCE.md, section Responsive & Platform.

Pages annexes : 960 px au plus, sauf « Diagnostic et modèles » (lot 3 du 2026-10-04), qui va jusqu'à 1440 px pour sa grille de cartes (voir Components).

Fond de page (`page`) : `{colors.surface}` semé de pois `{colors.dot}` de 1,3 px sur une grille de `{spacing.dot-grid}`, comme un papier de cahier. Les pois restent dans les gouttières et autour des volets ; aucun volet, aucune carte n'en porte.

`[ASSUMPTION]` L'en-tête de volet grandit (titre de 19 px et sous-titre) : le budget vertical dans 1280×650 est à vérifier à l'implémentation, les tokens d'espacement restant inchangés. Si la place manque, le sous-titre est le premier élément à masquer en mode projection, pas le contenu.

## Elevation & Depth

**Relief de jouet.** Les pièces posées sur la page ont du volume, donné par une ombre **pleine, sans flou**, décalée vers le bas : `box-shadow: 0 {spacing.relief-offset} 0 <couleur>`. Une ombre floue disparaît au vidéoprojecteur et bave en visio ; une ombre pleine reste nette, comme l'arête d'une brique de jeu.

| Pièce | Décalage | Couleur |
|---|---|---|
| Barre de l'atelier, volets, cartes de brique | `{spacing.relief-offset}` (4 px) | `{colors.relief}` |
| Carte de brique active, bouton secondaire, cadre du harnais | `{spacing.relief-offset}` | `{colors.relief-active}` |
| Bouton primaire | `{spacing.relief-offset}` | `{colors.primary-deep}` |
| Bouton enfoncé (au clic) | `{spacing.relief-offset-pressed}` (1 px), le bouton descend d'autant | inchangée |
| Tiroir d'édition, menus déroulants | `{spacing.relief-offset-overlay}` (6 px) `[ASSUMPTION]` | `{colors.relief}` |

Sans relief : éléments indisponibles (ils sont « posés à plat »), bouton Réinitialiser (neutre, pour ne pas attirer le clic), boutons danger et actions d'une entrée de la mémoire globale, contenu à l'intérieur d'un volet (messages, segments, étapes), qui se distingue par le ton et la bordure `{colors.line}`.

Le relief ne hiérarchise pas l'information : tous les volets ont le même. Le halo vert du composant en cours d'action (`arch-node-active`) n'est pas une ombre mais un signal d'état.

## Shapes

Grands arrondis, sur une échelle de trois rayons et la pilule :

- `{rounded.lg}` (26 px) : volets, barre commune, barre de l'atelier, zones du schéma, cadre du harnais, tiroir d'édition, détail de la jauge, bulles de message.
- `{rounded.md}` (18 px) : cartes de brique, boutons texte, sélecteur de modèle, segments de contexte, événements du harnais, cartes de dépassement et de données sortantes.
- `{rounded.sm}` (12 px) : boutons icônes (focus, masquer), tuiles d'icône, nœuds du schéma, étapes, bloc de raisonnement.
- `{rounded.full}` : jauge, badges, puces, interrupteurs, sélecteur de scénario, champ de saisie et bouton d'envoi.

Les bulles de message ont un coin de 6 px du côté du locuteur (bas droit pour l'utilisateur, bas gauche pour le modèle), pour se lire comme une conversation.

Le robot du modèle (`arch-model`) est dessiné avec les mêmes arrondis : corps et visière en rectangles très arrondis, oreilles et antenne en pilules. Pas d'angle vif dans le schéma.

Les nœuds réseau gardent le même rayon que les nœuds locaux : seule la bordure (continue ou en tirets) et la couleur changent, pour que la comparaison porte sur le lieu d'hébergement et rien d'autre.

## Components

Noms de composants identiques dans EXPERIENCE.md, section Component Patterns.

- **Fond de page (`page`)** : crème à pois, voir Layout & Spacing.
- **Barre basse de l'atelier (`top-bar`)** : nom historique conservé (classe `.top-bar` et identifiants inchangés : la renommer toucherait des centaines de sélecteurs CSS et E2E sans gain pour l'utilisateur) ; depuis la story 2 du 2026-09-30, elle est en bas de l'écran, sous les volets, et ses panneaux (liste « Volets ▾ », panneau « Fenêtre », message de statut) s'ouvrent vers le haut. Carte flottante sur l'encre (story 33 ; `{colors.ink-fill}`, violet profond en sombre, story 31), haute de `{spacing.top-bar-height}` (56 px, pour loger la légende sous la jauge), rayon `{rounded.lg}`, relief `{colors.relief}`. Chiffres de la jauge et statut en `{colors.on-ink}` ; anneau de focus `{colors.on-ink}` de 2 px (la liste « Volets ▾ » et le panneau « Fenêtre », sur `{colors.surface-raised}`, gardent le leur). Story 31 : un liseré intérieur `{colors.ink-fill-edge}` de `{spacing.stroke-min}` borde la barre (invisible en clair, 3,9:1 sur la page en sombre), et les commandes à fond propre (sélecteurs de scénario et de modèle, « Réinitialiser ») sont bordées `{colors.on-ink-soft}` (8,0:1 sur `ink-fill` en sombre). Les commandes gardent leur fond propre et ne passent jamais sur deux lignes. La jauge a une largeur fixe (barre et légende sur 300 px, la légende sur deux lignes au plus), pour que rien ne la fasse bouger ; sur une fenêtre étroite (1280 px), le nom du scénario et celui du modèle cèdent la place, entiers dans la liste et l'infobulle. De gauche à droite : sélecteur de scénario, jauge de contexte (élément le plus large), bouton « Fenêtre ▾ » (`window-picker`, story 26), puces des volets masqués et menu « Volets ▾ », sélecteur de modèle, bouton Réinitialiser. Le titre « WaveStack », les liens « LLM nu » et « Atelier RAG » et le menu « Affichage ▾ » sont passés dans la barre commune (`site-nav`).
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
- **Réglage de la fenêtre (`window-picker`)** (story 26) : bouton texte « Fenêtre 4 096 ▾ » juste après la jauge, fait comme `projection-toggle` (fond transparent, texte `{colors.on-ink}`, bordure `{colors.on-ink-soft}`, `{rounded.md}`, `label`) ; ouvert (`aria-expanded="true"`), fond `{colors.on-ink}` et texte encre ; sous 1400 px, seul le nombre et ▾ restent visibles, le bouton se resserre, et les noms du scénario et du modèle (et, en mode projection, le sélecteur de modèle) cèdent un peu plus, pour que la barre reste sur une ligne à 1280 px avec les puces des volets masqués (« · lié » lisible en mode projection). Son panneau tombe sous le bouton comme la liste « Volets ▾ » : fond `{colors.surface-raised}`, bordure `{colors.line}`, `{rounded.md}`, relief `{colors.relief}`, texte encre en `body-sm`, largeur 30 rem au plus ; titre en `heading`, aide et note en `{colors.ink-soft}`. Chaque choix est une carte bordée `{colors.line}` (`{rounded.sm}`) : radio à `accent-color` `{colors.primary}`, taille en `number`, « (actuelle) » en encre douce, puis cache, temps de lecture et borne en `{colors.ink-soft}` ; le choix noté est bordé `{colors.primary}` sur `{colors.primary-soft}`. Verdict : « ✓ Tient dans le budget » en encre ; un refus en style danger, texte encre à côté d'un filet `{colors.danger}` de `{spacing.stroke-min}` (le rouge en texte n'atteint pas 4,5:1 sur blanc), comme `button-danger`. « Appliquer » en primaire (fond `{colors.primary}`, texte `{colors.on-primary}`), « Fermer » en secondaire ; l'alerte d'un refus reçu, bordée `{colors.danger}`. Anneau de focus `{colors.primary}` dans le panneau (la barre d'encre garde le sien). Faits des jetons existants, aucun nouveau jeton ; en mode projection, la rampe les agrandit.
- **Poignée de gouttière (`pane-resize-handle`)** : invisible au repos (on voit les pois de la page). Au survol ou au focus, une pilule violette de 4 × 32 px apparaît au milieu de la gouttière, avec le curseur ↔ ou ↕. Pendant le glissement, la pilule reste visible. La zone de saisie fait au moins `{spacing.hit-target-min}`, même si la gouttière visible reste à `{spacing.gutter}`.
- **Boutons (`button-primary`, `button-secondary`, `reset-button`, `button-danger`)** : primaire violet plein sur relief violet foncé, qui s'enfonce au clic (relief de 4 px à 1 px) ; secondaire contour violet sur relief actif ; Réinitialiser neutre et sans relief, pour ne pas attirer le clic par erreur. Danger (« Tout effacer » de la mémoire globale) : fond blanc, bordure `{colors.danger}` de `{spacing.stroke-min}`, texte encre, sans relief ; sa confirmation (« Oui, tout effacer ») est pleine, fond `{colors.danger}` et texte encre (≈ 5,4:1 ; le blanc sur ce rouge ne tient pas 4,5:1). Libellés en `label` Fredoka. Hauteur minimale `{spacing.hit-target-min}`.
- **Sélecteur de scénario (`scenario-picker`)** : pastille violet doux avec le nom du module et du scénario en cours.
- **Sélecteur de modèle (`model-picker`)** : liste déroulante neutre (`select` natif), nom du modèle et taille (ex. « 2B »). Story 25 : groupes « Sur ce poste · {éditeur} » et « Réseau · {éditeur} » (libellés natifs des `optgroup`), options « {préfixe} · {nom} · {taille} » ; la légende est la deuxième option, désactivée, donc dans le gris natif des options désactivées ; aucune couleur propre, le « RÉSEAU » du préfixe suffit dans une liste native.
- **Sélecteur de thème (`theme-picker`)** (story 31) : `select` natif, fait comme `model-picker` (fond `{colors.surface-raised}`, texte encre, bordure `{colors.line}`, `{rounded.md}`, `label`, hauteur `{spacing.hit-target-min}`), nommé « Thème de l'interface » (`aria-label` et infobulle) ; trois options « ◐ Système », « ☀ Clair », « ☾ Sombre ». Il est dans le menu « Affichage ▾ » de la barre commune des cinq pages (story Langues 2/5, story 2 du 2026-09-30), avec le sélecteur de langue et, sur l'atelier seulement, le mode projection, sur `{colors.surface-raised}`, anneau `{colors.primary}` ; la face du menu montre le symbole du choix et le code de la langue. `color-scheme` fait suivre la liste native. Accessibilité, accepté : les lecteurs d'écran lisent le symbole des options (« ◐ Système »…) avec leur mot.
- **Tableau des modèles (`model-table`)** — *remplacé par « Diagnostic et modèles » (lot 3 du 2026-10-04, ci-dessous) ; `/models` redirige vers `/diagnostic`. La bande de filtres est reprise telle quelle.* (story 25, page `/models` ; story 3 du 2026-09-30 : tri et filtres) : page sur `{colors.surface}`, texte encre, sans pois (un tableau à lire) ; titre « Modèles disponibles » en `heading` agrandi, légende et note en `body` `{colors.ink-soft}`. Table blanche (`{colors.surface-raised}`), bordure `{colors.line}`, `{rounded.sm}` ; `caption` en `label` majuscule `{colors.ink-soft}` ; en-têtes de colonnes en `label` `{colors.ink-soft}` ; un `tbody` par groupe, son en-tête (`th scope="rowgroup"`) sur `{colors.surface}` en `heading` à la taille du corps ; filets de lignes `{colors.line}`. Colonne Modèle : `hosting-tag-local` (neutre) ou `hosting-tag-network` (jaune, tirets encre, 🌐), puis le nom en gras. Taille et fenêtre en `number`. Raison sous chaque mot (outils, raisonnement, fenêtre, état) en `body-sm` `{colors.ink-soft}` ; ligne d'un modèle inutilisable en `{colors.ink-soft}` ; « actif » en gras. Erreur du fichier des éditeurs : bandeau blanc bordé `{colors.danger}` de `{spacing.stroke-min}`, texte encre. Story 3 du 2026-09-30 : le nom de chaque colonne triable (toutes sauf Prix) est un bouton plat de la largeur de l'en-tête, en `label` encre douce, encre au survol et quand il trie, cible `{spacing.hit-target-min}`, focus `{colors.primary}` de 2 px ; sa marque : « ↕ » en encre douce au repos, « ▲ » ou « ▼ » en `{colors.primary}` sur l'en-tête actif (`aria-sort`). Au-dessus du tableau, une bande de filtres `{colors.surface-raised}` bordée `{colors.line}`, `{rounded.md}` : chaque champ son nom en `label` encre douce au-dessus, la liste ou la saisie sur `{colors.surface-raised}` bordée `{colors.ink-soft}`, `{rounded.sm}`, cible `{spacing.hit-target-min}` ; la saisie libre prend la place qui reste ; « Réinitialiser les filtres » en `button-secondary`. Aucun résultat : un encadré `{colors.surface-raised}` à tirets `{colors.ink-soft}`, le message et « Réinitialiser les filtres » en `button-primary`. Tableau, étiquettes, boutons et champs sont communs aux pages annexes (`static/pages.css`, portée `body.annex-page`). Aucun nouveau jeton.
- **Barre commune (`site-nav`)** (story 2 du 2026-09-30 ; remplace les onglets de page `page-tabs` de la story 25, les liens et le titre de la barre de l'atelier) : le même balisage en tête des six pages (`/`, `/llm`, `/rag`, `/mcp`, `/diagnostic`, `/models` ; `/mcp` depuis la story 6 du 2026-09-30), stylé par `static/pages.css`, fait des jetons existants. Bandeau `{colors.surface-raised}` bordé `{colors.line}`, `{rounded.lg}`, sur la largeur de la fenêtre moins une marge (sur l'atelier, la largeur des volets) ; de gauche à droite : la marque « WaveStack » en `heading` encre (lien vers `/`), puis les liens Atelier, LLM nu, Atelier RAG, Atelier MCP, Diagnostic, Modèles, dans cet ordre fixe, en `label` agrandi (× 1,2), encre douce ; la page courante (`aria-current="page"`) en encre, soulignée de 3 px `{colors.primary}` ; focus : contour `{colors.primary}` de 2 px. À droite, le menu « Affichage ▾ » : face sur `{colors.surface}`, bordure `{colors.line}`, `{rounded.md}`, `label`, avec le symbole du thème et le code de la langue ; son panneau `{colors.surface-raised}` s'ouvre vers le bas (thème, langue, et mode projection sur l'atelier seulement) ; un refus de changement de langue s'y lit sous les sélecteurs, sur `{colors.danger-soft}`. Aucun contrôle n'y est tronqué en `de` à 1 280 et 1 600 px, en mode normal et en projection.
- **Mode projection (`projection-toggle`)** (story 34, remplace le `text-size-control` « Aa 100 % », jamais construit) : bouton texte « Mode projection » du menu « Affichage ▾ », sur l'atelier seulement (seul `app.js` applique la projection) ; fond transparent, texte encre, bordure `{colors.line}`, `{rounded.md}` ; pressé (`aria-pressed="true"`), fond `{colors.primary}` et texte `{colors.on-primary}`. Il agrandit toute la rampe (voir Typography).
- **Jauge de contexte (`context-gauge`)** : barre horizontale empilée, rayons pleins, sur une piste claire (`{colors.surface-raised}`, bordure `{colors.on-ink-soft}`) dans la barre foncée. Les groupes gardent l'ordre d'empilement de la palette catégorielle, mais chacun prend la couleur de sa discipline (`discipline` reçu de la session), séparé du suivant par un filet blanc de 1 px ; l'infobulle nomme le groupe, ses tokens et sa discipline (« Prompt système : 31 tokens · Prompt engineering » ; « Hors brique » (message, gabarit, tour du modèle) pour le neutre, même libellé que la légende). La discipline d'un groupe est celle qui porte le plus de tokens parmi ses segments (à égalité, la première dans l'ordre du contexte). Espace libre hachuré. Sous la barre, la légende (`#gauge-legend`, `discipline-legend`) : une pastille bordée `{colors.on-ink-soft}` et le nom de chaque discipline présente, dans l'ordre prompt, context, harness, puis « Hors brique » (message, gabarit, tour du modèle), en `label` `{colors.on-ink-soft}` ; elle passe à la ligne plutôt que d'être coupée, et ne donne pas de tokens par discipline. À droite : `number` « 1 840 / 4 096 tokens · 45 % » en `{colors.on-ink}`. Un marqueur vertical en encre indique le seuil d'alerte. Au dépassement, le pourcentage passe sur pastille rouge avec icône.
- **Détail de la jauge (`context-gauge-detail`)** (abandonné : décision D1 d'Anaël du 2026-10-01, la jauge empilée et son survol suffisent ; ne pas construire) : grille de cellules à la manière de `/context`, une cellule par tranche de tokens, colorée selon la palette catégorielle, cellules libres en crème hachuré. Légende à droite : pastille, nom du segment, tokens et pourcentage en `number`.
- **Segment de contexte (`context-segment`)** : bloc de texte brut en `{typography.code}`, filet latéral gauche de 4 px et fond doux de sa discipline (story 33, `data-discipline`), étiquette `label` en encre avec pastille de la couleur du type de segment (palette catégorielle) et nombre de tokens. Depuis la story 32, il ne sert plus qu'à la comparaison de tours ; Contexte LLM lit par section. Segment sélectionné : contour encre de 2 px.
- **Appel au modèle (`context-call`)** (story 32) : un bloc par appel, séparé du précédent par un filet `{colors.line}` de `{spacing.stroke-min}` ; titre « Appel i sur n » en `heading`, chiffres « Lu : … · évalués : … · produits : … » en `number` encre douce ; « Lu par le modèle » en `label` majuscule encre douce. Entre deux appels, la ligne du harnais en `body-sm` encre douce (⚙), avec le bouton de l'onglet du sous-agent après une délégation. En tête du volet, la bascule « Affichage du contexte » : trois pilules `label` bordées `{colors.line}`, la pressée sur l'encre, texte `{colors.on-ink}`. « Texte exact » : un `pre` en `code` sans filet, fond ni couleur.
- **Section de contexte (`context-section`)** (story 32) : une ligne en grille, marge (10 à 15 em) puis texte ; filet gauche de 4 px et fond doux de sa discipline (`data-discipline`, story 33) ; dans la marge, pour chaque section de la ligne, la pastille de son type (palette catégorielle) et son étiquette `label` encre. Texte en `{typography.code}`, un `span` par segment, gabarit (et syntaxe JSON du mode chat) en `{colors.ink-soft}`. Nouveau : filet de 8 px et badge « Nouveau » sur l'encre, texte `{colors.on-ink}`. Déjà lu : un `details` replié, fond `{colors.surface}`, bordure en tirets `{colors.line}`, résumé `label` encre douce. Sous 28rem de volet (requête de conteneur), la marge passe au-dessus du texte. Tailles par les jetons de la rampe ou en `em` : le mode projection (story 34) les agrandit.
- **Bloc produit (`produced-block`)** (story 32) : fond `{colors.produced-soft}` (réflexion : `{colors.reasoning-soft}`), filet gauche de 4 px `{colors.ink}`, `{rounded.md}` ; en tête, l'étiquette « Produit par le modèle » en pilule `{colors.ink}` / `{colors.on-ink}`, puis le type (« Réflexion », « Réponse », « Appel d'outil ») en `label` encre ; texte en `code`. Le produit n'a jamais un fond de discipline : on distingue d'un coup d'œil ce que le modèle a lu de ce qu'il a écrit.
- **Arbre JSON (`json-tree`)** (story 32) : en `code`, indenté de `{spacing.4}` sous un filet `{colors.line}` ; un `details` par objet ou tableau, ouvert par défaut, résumé « … } n clés » quand il est replié ; clés en `{colors.json-key}` (graisse 600), chaînes en `{colors.json-string}`, littéraux en `{colors.json-literal}`, ponctuation en encre douce. Le bouton « Texte exact » (`label`, bordé `{colors.line}`, pressé sur l'encre) montre la sous-chaîne envoyée sur blanc.
- **Panneau des briques** (story 33) : en tête, la légende des quatre disciplines (`discipline-legend` : « Prompt engineering », « Context engineering », « Harness engineering », « Sort du poste de travail » avec 🌐 dans sa pastille), puis deux groupes titrés en `label` majuscule encre douce, « Ce que le modèle lit » et « Ce que le harnais fait », selon le groupe que la session déclare pour chaque brique.
- **Carte de brique (`brick-card`)** : nom, interrupteur (`brick-toggle`), puce de catégorie (`category-chip` : « prompt engineering », « context engineering », « harness engineering », bordée et teintée de sa discipline), étiquette de lieu d'hébergement (`hosting-tag-local`, neutre), puce « 🌐 RÉSEAU » (`hosting-tag-network`) quand une option activée sort du poste, ligne d'état (`brick-status`, `body-sm`), explication dépliable. Relief `{colors.relief}`. Active : fond doux de sa discipline, trait gauche de 5 px de sa couleur, interrupteur coché de sa couleur, texte encre, relief `{colors.relief-active}`. Éteinte : grisée, fond `{colors.discipline-neutral-soft}`, trait `{colors.discipline-neutral}`, texte `{colors.ink-soft}`. Raisonnement imposé par le modèle : interrupteur coché et désactivé, 🔒 à côté. Indisponible : posée à plat (sans relief), bordure en tirets, texte encre douce, interrupteur désactivé, raison toujours visible en `{colors.ink-soft}`. Sous-option d'une brique éteinte ou indisponible : interrupteur désactivé, coché en `{colors.muted}` au lieu du violet (`brick-toggle.parent-off`), libellé et résumé en `{colors.ink-soft}`.
- **Tiroir d'édition (`edit-drawer`)** : panneau qui glisse par-dessus le panneau des briques pour éditer le prompt système ou la mémoire globale ; champ en `{typography.code}`. Confirmation d'enregistrement en `body-sm` encre, précédée de « ✓ ». Mémoire globale : en-tête (titre, croix « × » en bouton icône `{rounded.sm}` bordé `{colors.line}`), liste défilante, pied fixe séparé par un filet `{colors.line}` avec « Tout effacer » (`button-danger`) et « Fermer » (`button-secondary`) ; « Enregistrer » et « Supprimer » d'une entrée en actions compactes à plat, fond crème, bordure `{colors.line}`, `{rounded.sm}`.
- **Messages (`chat-message-user`, `chat-message-model`)** : bulles `{rounded.lg}` à coin de 6 px côté locuteur ; utilisateur sur l'encre, texte `{colors.on-ink}` (story 33), modèle sur `{colors.surface-raised}` bordé. Typographie `chat`. Bloc de raisonnement (`reasoning-block`) replié sur crème, en `body-sm`.
- **Champ de saisie (`composer`)** : pilule en `chat`, bordure `{colors.line}`, `{colors.primary}` au focus ; bouton d'envoi primaire rond à droite.
- **Prompt suggéré (`suggested-prompt-chip`)** : puce contour violet au-dessus du champ de saisie.
- **Consigne du scénario (`scenario-info`)** : « i » italique serif dans un disque de 1,5 em cerclé de violet, à côté du titre de la Vue humain (cible de 32 px) ; plein violet au survol et ouvert ; halo violet au lancement d'un scénario. Popover : surface relevée, filet et ombre de relief des explications de brique, 420 px de large au plus, `body-sm` encre douce, titre en violet foncé gras.
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
- **Ligne de diagnostic (`diagnostic-row`)** — *la ligne de contrôle reste, dans le panneau repliable `checks-panel` ; les lignes de modèles et les cartes cloud deviennent des `model-card` (lot 3 du 2026-10-04, ci-dessous).* Pastille d'état (vert « OK », rouge « Échec ») avec texte `{colors.on-vivid}`, libellé de la vérification, action corrective en dessous. Story 31 : la page `/diagnostic` charge `tokens.css`, fond `{colors.surface}` et texte encre ; le fond d'une ligne dit son état (`{colors.accent-soft}` pour OK, trouvé ou serveur ; `{colors.warning-soft}` pour un avertissement ; `{colors.danger-soft}` pour un échec ou un modèle incompatible) ; un modèle cloud est sur `{colors.discipline-network-soft}`, bordé de tirets `{colors.hosting-boundary}` ; détails et actions en encre douce ; un avertissement de serveur et le résultat d'un test cloud en encre, derrière un filet gauche de 4 px `{colors.state-ok}`, `{colors.warning}` ou `{colors.state-error}` ; étiquettes `hosting-tag-*` comme dans l'atelier ; `dialog` sur `{colors.surface-raised}`, bordé d'encre. Story 3 du 2026-09-30 : page sur la rampe typographique et les espacements de `tokens.css` seulement (plus aucune taille en `rem`), 960 px au plus ; hiérarchie titre (`heading` agrandi), puis trois sections titrées en `pane-title` : Contrôles, Modèles détectés (avec le choix d'un fichier par son chemin), Modèles cloud. Lignes et cartes sur `{rounded.md}`, bordées `{colors.line}`, détails en `body-sm` encre douce. « Choisir » et « Choisir ce fichier » en `button-primary`, « Tester » et « Enregistrer la clé » en `button-secondary`, à plat quand ils sont indisponibles. Un modèle cloud est une carte : l'étiquette réseau, le fournisseur et le modèle en titre (`heading` à la taille du corps) avec ses marques, puis hébergement et entraînement, le prix, un bloc clé sous un filet `{colors.line}` (champ et bouton, d'où vient la clé), les actions, leurs notes et le résultat du test. Pendant la recherche des modèles, un encadré `{colors.surface-raised}` à tirets `{colors.ink-soft}` dit « Recherche et test des modèles en cours… », puis le compte en `number` et une barre `<progress>` teintée `{colors.primary}` (`accent-color`).

- **Écran « LLM nu » (`llm-screen`)** (story 29, page `/llm`) : page sur `{colors.surface}`, sans pois, comme `/models` : barre commune (`site-nav`, « LLM nu » courant) en tête ; titre en `heading` agrandi, modèle actif précédé de `hosting-tag-local` ou `hosting-tag-network` (« 🌐 RÉSEAU · {fournisseur} »). Chaque section est une carte `{colors.surface-raised}` bordée `{colors.line}`, `{rounded.lg}`, relief `{colors.relief}`, titrée en `pane-title` après un disque numéroté `{colors.ink-fill}` / `{colors.on-ink}` (comme `pane-step`). Boutons `button-primary` et `button-secondary`, à plat quand ils sont indisponibles, la raison dans un bandeau `{colors.warning-soft}` bordé `{colors.warning}`. Aucune ligature dans la page : `<|im_end|>` se lit tel qu'il est tapé (JetBrains Mono transformerait `<|` en flèche).
- **Puce de token (`token-chip`)** (story 29) : une pastille `{rounded.sm}` par token, bordure `{colors.line}` ; le texte du token en `code` (blancs rendus visibles : `␣` pour une espace, `↵` pour un retour à la ligne), l'identifiant dessous en `number` petit, encre douce. Deux fonds existants en alternance, `{colors.primary-soft}` et `{colors.accent-soft}` (aucun nouveau jeton, lisibles en encre dans les deux thèmes). Un token spécial (marqueur du gabarit) : fond `{colors.surface-raised}`, bordure en tirets `{spacing.stroke-min}` `{colors.discipline-harness}` et le mot « spécial » en `label` : jamais la couleur seule. Les octets d'un token qui n'est qu'une partie d'un caractère s'écrivent `⟨F0 9F⟩`.
- **Schéma de vectorisation (`embedding-diagram`)** (story 29) : une bande `{colors.surface}` bordée `{colors.line}`, `{rounded.md}`, où six cases `{colors.surface-raised}` bordées `{colors.ink-soft}` se suivent, reliées par « → » : Texte, Tokens, Identifiants, Table d'embedding (« vocabulaire × dimension », une rangée de cellules `{colors.line}` dont une `{colors.primary}` : la ligne choisie), Vecteur, Couches. Nom de la case en `label` majuscule encre douce, valeur en `number-lg`, légende en `body-sm`. Une dimension inconnue s'écrit « inconnue » en italique encre douce, et sa raison est sous le schéma, avec la source des chiffres.
- **Réglages d'échantillonnage (`sampling-controls`)** (story 29) : une grille de cartes `{colors.surface}` bordées `{colors.line}`, `{rounded.sm}`, une par réglage : nom en `heading`, champ numérique en `number` à droite, curseur natif (`accent-color: {colors.primary}`), explication en `body-sm` encre douce. Un réglage non réglable : fond `{colors.discipline-neutral-soft}`, champs désactivés, raison en encre précédée de « ⊘ ». Story 5 du 2026-09-30 : les réglages B de la comparaison reprennent ces cartes, sans l'explication, dans un `fieldset` bordé `{colors.line}` sous la section 5 ; chaque mouvement d'un curseur de la section 2 redessine `distribution-bars`.
- **Flux de tokens (`token-stream`)** (story 29) : les mêmes `token-chip`, ajoutées au fil de l'eau ; le prompt rendu au-dessus, en `code` sur `{colors.surface}`, filet gauche de 4 px `{colors.ink-soft}` ; chiffres (premier token, débits) en `number`.
- **Étapes du chargement (`load-steps`)** (story 29) : une case `{colors.surface}` par étape, bordée `{colors.line}`, filet gauche de 4 px `{colors.state-ok}` (l'étape est franchie, et son nom le dit), nom en `label` majuscule, durée en `number` ; la mémoire dans un bandeau `{colors.surface}`.
- **Couloirs du raisonnement (`reasoning-lanes`)** (story 29) : deux colonnes, « Réflexion » sur `{colors.reasoning-soft}` (filet `{colors.ink-soft}`), « Réponse » sur `{colors.produced-soft}` (filet `{colors.ink}`), comme les blocs produits de Contexte LLM ; la marque de coupe en tirets `{colors.discipline-harness}` précédée de « ✂ » (une décision du harnais). Une puce de token du canal de réflexion a le fond `{colors.reasoning-soft}` et une bordure en tirets.
- **Encart des candidats (`candidates-popover`)** (story 29) : carte `{colors.surface-raised}` bordée `{spacing.stroke-min}` `{colors.primary}`, `{rounded.md}`, relief `{colors.relief}` de `{spacing.relief-offset-overlay}` (un encart, comme les menus). Une ligne par candidat : le texte en `code` entre guillemets, une barre `{colors.primary}` sur piste `{colors.line}` (`{colors.muted}` pour un candidat écarté), le pourcentage en `number` ; dessous, en `body-sm` encre douce, la chance d'être tiré et « écarté par … ». Le token tiré : fond `{colors.primary-soft}`, contour encre et le mot « tiré ». Une puce qui porte des candidats a son texte souligné en pointillés.
- **Distribution vivante (`distribution-bars`)** (story 5 du 2026-09-30) : sous les réglages de la section 2, une figure `{colors.surface}` bordée `{colors.line}`, `{rounded.md}`. Principes `dataviz` : une seule teinte, étiquettes directes, pas de légende séparée (deux en-têtes de colonne en `label` encre douce : « Probabilité du modèle », « Chance d'être tiré »). Une ligne par candidat (dix au plus) : le texte en `code` entre guillemets, puis deux barres sur piste `{colors.line}` `{rounded.full}` suivies de leur pourcentage en `number` : la probabilité du modèle en `{colors.primary-soft}` cerclé `{colors.primary}` (elle ne bouge pas), la chance d'être tiré en `{colors.primary}` plein (elle bouge, transition de 120 ms, coupée par `prefers-reduced-motion`). Un candidat écarté : texte encre douce, barres `{colors.muted}`, « écarté » à la place du pourcentage. Dernière ligne, sous un filet en tirets `{colors.line}` : « Reste du vocabulaire », sa masse seule, en `body-sm` encre douce, dite approximative dessous. La puce de la section 5 dont les candidats sont montrés a un contour de 2 px `{colors.primary}`.
- **Comparaison A/B (`compare-lanes`)** (story 5 du 2026-09-30) : en bas de la section 5, sous un filet `{colors.line}` : titre en `heading`, réglages B (`sampling-controls` compactes), bouton secondaire « Comparer », puis deux colonnes côte à côte (une seule sous 900 px), sur `{colors.produced-soft}` à filet gauche de 4 px `{colors.ink}`, comme le couloir « Réponse » : en tête « A » ou « B » en `heading` suivi des réglages résumés en `number` encre douce (« T 0,7 · top-k 20 · … ») ; la réflexion éventuelle sur `{colors.reasoning-soft}` ; l'issue en `body-sm` encre douce (« En attente de la fin de A. » pour B tant que A tourne).
- **Schéma de la fenêtre (`window-diagram`)** (story 5 du 2026-09-30) : en section 4, une figure `{colors.surface}` bordée `{colors.line}` : une barre en deux parts proportionnelles aux valeurs reçues (`flex-grow`), la part du prompt (`{colors.segment-free}`, remplie de `{colors.segment-message}` jusqu'au nombre de tokens du prompt) puis la réserve de sortie (bordure en tirets, remplie de `{colors.produced-soft}` token après token, tête de lecture en filet encre) ; étiquettes dessous en `number` encre douce, légende en phrase.
- **Questions de section (`llm-questions`)** (story 5 du 2026-09-30) : sous l'introduction de chaque section, un encart `{colors.surface}` à filet gauche de 4 px `{colors.primary}`, `{rounded.sm}` : « Les questions que vous vous posez » en `heading` taille corps, puis une liste à puces.
- **Atelier RAG (`rag-screen`)** (story 30, page `/rag`) : même cadre que l'écran « LLM nu » : page sur `{colors.surface}`, sans pois, barre commune (`site-nav`, « Atelier RAG » courant) en tête ; sections sur `{colors.surface-raised}` bordées `{colors.line}`, `{rounded.lg}`, relief `{colors.relief}`, titrées après un disque numéroté `{colors.ink-fill}` / `{colors.on-ink}` ; boutons `button-primary` et `button-secondary`, à plat quand ils sont indisponibles, la raison dans un bandeau `{colors.warning-soft}` bordé `{colors.warning}`. Aucun jeton nouveau.
- **Chaîne RAG (`rag-chain`)** (story 30) : une grille d'une ligne, une carte par étape, `{rounded.md}`, fond `{colors.discipline-context-soft}`, filet gauche de 4 px `{colors.discipline-context}` (le RAG est du context engineering), texte encre ; entre deux cartes, « → » en encre dans l'écart. Nom de l'étape en `heading` après un disque numéroté `{colors.ink-fill}`, option en gras, réglages et explication en `body-sm`. La génération, celle du modèle, repose sur l'encre : `{colors.ink-fill}`, texte `{colors.on-ink}`, bordure `{colors.ink-fill-edge}`. Une note d'obstacle : fond `{colors.warning-soft}`, filet `{colors.warning}`, précédée de « ⚠ » (jamais la couleur seule).
- **Carte d'étape (`rag-stage-card`)** (story 30) : carte `{colors.surface}` bordée `{colors.line}`, `{rounded.md}`, dont le filet gauche de 4 px dit l'état, doublé d'un libellé dans une pastille (`{colors.surface-raised}`, bordée `{colors.ink-soft}`, en `number`) : `{colors.state-active}` en cours, `{colors.state-ok}` terminée, `{colors.state-error}` en erreur (message sur `{colors.danger-soft}`), `{colors.warning}` arrêtée, fond `{colors.discipline-neutral-soft}` et filet `{colors.muted}` en attente ou sautée ; la génération, filet `{colors.ink-fill}`. Entrée et sortie en liste de définitions (intitulés en `label` majuscule encre douce), chiffres en `number`, tableau des extraits en `body` (rang et score en `number`, rang d'avant suivi de « ↑ » ou « ↓ », extrait en `body-sm` encre douce sur deux lignes), pied (durée, mémoire) derrière un filet `{colors.line}`. « Emprunté à la brique RAG » sur `{colors.accent-soft}`, filet `{colors.accent}`, précédé de « ⇄ ». Une exécution s'affiche sur une colonne ; deux chaînes comparées, sur deux colonnes.
- **Réglages de la chaîne et comparaison** (story 30) : dans une carte de `rag-chain`, la liste des options et les champs numériques sur `{colors.surface-raised}`, bordés `{colors.ink-soft}`, `{rounded.sm}`, chiffres en `number` ; une option indisponible : sa raison en `body-sm` derrière un filet `{colors.muted}`, précédée de « ⊘ » ; la case « Comparer » en `accent-color: {colors.primary}`. Les boutons « ◀ », « ▶ » et « Retirer » : `{colors.surface-raised}`, bordés `{colors.ink-soft}`, `{rounded.sm}`, en `label`, cible `{spacing.hit-target-min}`, à plat et encre douce désactivés. Une carte refusée : bordure `{colors.danger}`, la raison sur `{colors.danger-soft}` derrière un filet `{colors.danger}`, précédée de « ✖ ». « Ajouter un composant » : une liste native et un `button-secondary`. Les rangs d'un extrait dans les listes d'avant, sous son document, en `number` petit. La comparaison (`rag-comparison`) : carte `{colors.surface}` bordée `{colors.line}`, filet gauche `{colors.discipline-context}`, la synthèse en `body`, puis quatre colonnes titrées en `label` majuscule encre douce. Aucun jeton nouveau.
- **Atelier MCP (`mcp-screen`)** (story 6 du 2026-09-30, page `/mcp`) : même cadre que l'Atelier RAG (page `{colors.surface}`, barre commune avec « Atelier MCP » courant, cinq sections `{colors.surface-raised}` numérotées par un disque `{colors.ink-fill}`, boutons `button-primary` et `button-secondary`, bandeau de raison `{colors.warning-soft}`). Les serveurs : une carte chacun en grille qui se replie (`auto-fit`, 20rem au moins), `{rounded.md}`, le glossaire local sur `{colors.discipline-harness-soft}` filet gauche 4 px `{colors.discipline-harness}`, les serveurs publics sur `{colors.discipline-network-soft}` filet `{colors.discipline-network}` ; une pastille « Connexion ouverte » `{colors.state-ok}` / `{colors.on-vivid}`. Les messages JSON-RPC : une ligne chacun, filet de 4 px `{colors.discipline-harness}` à gauche et retrait à droite pour harnais → serveur, à droite et retrait à gauche pour serveur → harnais ; sens en `label`, méthode et JSON en `code` (`{colors.surface}`, bordé `{colors.line}`, `{rounded.sm}`, défilant), durée en `number` encre douce, une étiquette « capturé sur le transport » (ou « reconstitué » sur `{colors.warning-soft}`) ; une requête HTTP sortante sur `{colors.discipline-network-soft}`. Les outils : cartes filet `{colors.segment-tool-descriptions}`, schéma replié ; le tableau des poids en `number`, total souligné d'un filet `{colors.ink-soft}`. Le bloc « outils » (section 5) : deux colonnes, documentation complète et lazy loading, en `code`. Toutes les rangées se replient : l'allemand tient à 1 280 px. Aucun jeton nouveau.

- **Diagnostic et modèles (lot 3 du 2026-10-04)** : la page `/diagnostic` fusionnée, référence visuelle [`.working/key-diagnostic-modeles.html`](.working/key-diagnostic-modeles.html). Page sur `{colors.surface}`, sans pois, **jusqu'à 1440 px** de large (et non plus 960 px) pour la grille. Sous le titre, le panneau des contrôles, la bande de filtres, puis deux zones : « 💻 Modèles locaux détectés » et « ☁️ Modèles cloud », séparées par un filet encre de 2 px au-dessus de la zone cloud.
  - **Groupe d'éditeur (`publisher-group-header`)** : le logo en petite tuile (28 px), le nom de l'éditeur (`label_text` de `publishers.yaml`) en `pane-title`, « · n modèles » en encre douce. Puis la grille de ses cartes.
  - **Grille** : `repeat(auto-fill, minmax(250px, 1fr))`, gouttière `{spacing.4}` ; 4 à 5 colonnes à 1440 px, 2 en projection agrandie. Les lignes incomplètes restent vides (pas d'étirement des cartes).
  - **Carte de modèle (`model-card`)** : tuile de logo de 48 px à gauche ; à droite, le nom en `body` gras (coupé n'importe où plutôt que tronqué), puis l'origine en encre douce (« Fichier GGUF · Hugging Face », « Ollama · serveur local déjà lancé », « llama-server · 127.0.0.1:8080 », ou le fournisseur pour le cloud). Dessous, sur toute la largeur : la **taille en gros chiffre** (`number-lg`, « 2,5 Go », « ≈ 2,7 Go » pour un modèle servi), les paramètres à côté en encre douce (« 4 B ») ; enfin la pastille d'état et les marques (« choix enregistré », « offre d'essai ») en `primary` sur `primary-soft`. Un modèle à plusieurs sources porte en plus la puce « 2 sources » (`label`, encre sur `{colors.surface}`, bordée encre douce, pilule), distincte des marques violettes. Relief jouet habituel (ombre pleine `{colors.relief}` de 4 px), bordure encre douce au survol.
  - **Carte active** : bordure encre de 3 px et ombre `{colors.state-active}` : c'est la carte qu'on repère du fond de la salle. **Carte inutilisable** (incompatible ou en erreur) : fond `{colors.danger-soft}`, taille en encre douce.
  - **Carte cloud** : fond `{colors.discipline-network-soft}`, bordure en tirets encre de 2 px, sans ombre ; la ligne de taille porte à la place l'étiquette `hosting-tag-network` « 🌐 RÉSEAU · {fournisseur} » (un modèle cloud n'a pas de taille). Ce codage réseau, déjà celui de l'atelier, est ce qui sépare local et cloud d'un coup d'œil.
  - **Carte dépliée (`model-card-expanded`)** : elle prend toute la largeur de sa ligne (`grid-column: 1 / -1`), bordure `{colors.primary}` de 2 px (tirets encre pour une carte cloud), rembourrage `{spacing.5}`, tuile de 64 px, nom en `heading`, et « ✕ Replier » en `button-secondary` en haut à droite. Avec plusieurs sources, une section « Sources » d'abord, sur toute la largeur : une ligne par source sur `{colors.surface}`, bordée `{colors.line}`, `{rounded.sm}` (bordure encre pour la source active), avec l'origine en gras, le chemin en `code`, la taille, la pastille d'état et « Choisir cette source » en `button-primary` à droite. Sous un filet `{colors.line}`, deux colonnes (une seule sous 640 px) de sections titrées en `label` majuscule encre douce : Diagnostic (messages complets derrière un filet gauche de 4 px : `state-ok`, encre douce pour un avertissement, `state-error`), Fichier ou Adresse (`code` sur `{colors.surface}`), Capacités (liste Fenêtre, Appel d'outils, Raisonnement, Prix, la raison de chaque valeur dessous en `body-sm` encre douce) ; pour le cloud, « Où partent les données », Clé API et Dernier test. Les actions, sous un dernier filet : « Choisir ce modèle » en `button-primary`, « Tester » et « Enregistrer la clé » en `button-secondary`, l'aide en encre douce à côté.
  - **Tuile de logo (`model-logo`)** : fond `{colors.logo-tile}`, blanc dans les deux thèmes (nouveau jeton, à reporter dans `tokens.css`), bordure `{colors.line}`, `{rounded.sm}`, logo contenu sans déformation. Logo de la famille quand la banque-visuels l'a (Qwen, Gemma, Gemini, Claude, DeepSeek, Mistral), sinon celui de la société (Llama → symbole ∞ de Meta, le logotype « LLaMA by Meta » n'ayant pas de symbole séparé ; Phi → Microsoft, Nemotron → NVIDIA, gpt et gpt-oss → OpenAI, SmolLM → Hugging Face, Granite → logo IBM entier, watsonx n'ayant pas de symbole). Sans logo (LFM, MiniCPM, « Autres éditeurs ») : l'initiale en `pane-title` `{colors.primary}` sur `{colors.primary-soft}`. Symbole seulement, jamais le logotype : Qwen, DeepSeek, Hugging Face, OpenAI et Meta, logotypes larges dans la banque, sont recadrés sur leur symbole à l'intégration (`scripts/crop_logos.py`, provenance dans `static/logos/SOURCES.md`) ; la tuile garde sa taille (décisions d'Anaël du 2026-10-04).
  - **Pastille d'état (`state-pill`)** : un point de 12 px et un libellé en `label`, sur `{colors.surface}` bordé `{colors.line}`. Actif et Test réussi : point vert bordé encre sur `{colors.accent-soft}` ; Incompatible, Erreur, Échec du test : point rouge sur `{colors.danger-soft}` ; Disponible et Prêt : point creux encre douce ; Clé manquante : point en tirets gris, libellé encre douce ; Avertissement et Test en avertissement : « ⚠ » à la place du point. Le jaune n'est jamais un état (il dit « ça sort du poste »), y compris pour les avertissements, à la différence de `diagnostic-row`.
  - **Panneau des contrôles (`checks-panel`)** : `details` blanc bordé `{colors.line}`, `{rounded.md}`, résumé de 44 px de haut au moins : « ▸ Contrôles · 4 contrôles OK : mémoire, modèle, réseau, port ». Ouvert, il contient les `diagnostic-row` actuelles.
  - **Bande de filtres (`models-filters`)** : celle du tableau des modèles, avec l'hébergement en bouton segmenté (Tous, Local, Réseau ; segment choisi en `{colors.primary}`, texte `{colors.on-primary}`) et un menu « Trier par » en plus ; le compteur à droite en encre douce.

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
| Chaque couleur par un jeton de `tokens.css`, avec son jumeau `-dark` (story 31), dans toutes les pages de `static/` | Couleur écrite en dur (`#hex`, `rgb(`, `hsl(`) dans une page, une feuille ou un script de `static/` hors `tokens.css` |
| Fond d'encre = `{colors.ink-fill}` (violet profond en sombre) | `{colors.ink}` en fond : en sombre, c'est un texte clair |
| Texte sur fond vif (jaune, vert, rouge, gris neutre) = `{colors.on-vivid}`, explicite | Laisser un texte hériter sa couleur sur un fond vif : il deviendrait clair en sombre |
| Palette sombre dessinée jeton par jeton, dans DESIGN.md puis `tokens.css` | `filter: invert`, ou une palette calculée en JS |
| Logos d'éditeurs embarqués dans `static/logos/`, sur une tuile `{colors.logo-tile}`, pour désigner le modèle (lot 3 du 2026-10-04) | Logo chargé d'un CDN, logo recoloré ou inversé en sombre, ou logo qui suggère un partenariat |
