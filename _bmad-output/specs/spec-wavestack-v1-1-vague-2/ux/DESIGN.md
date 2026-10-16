---
title: DESIGN — WaveStack V1.1 vague 2 (sécurité, garde-fous, FinOps)
status: final
created: 2026-10-16
updated: 2026-10-16
sources:
  - ../SPEC.md
  - ../../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md
name: WaveStack — vague 2
description: >-
  Delta visuel de la vague 2 sur le DESIGN.md principal : page Sécurité, deux boutons de la
  barre commune (dépense et journal) avec leur panneau, brique Garde-fous, règles d'outils MCP,
  connexion GitHub et lignes FinOps. Aucun nouveau jeton de couleur ni de typographie : tout
  renvoie aux jetons du DESIGN.md principal (miroir de static/tokens.css).
# Jetons hérités tels quels du DESIGN.md principal (non redéclarés) : colors.*, typography.*,
# rounded.*, spacing.*.
components:
  disclosure-row:
    background: '{colors.surface}'
    radius: '{rounded.sm}'
    chevron-color: '{colors.ink}'
    chevron-size: 26px
    body-background: '{colors.surface-raised}'
    body-rule: '{colors.primary}'
    body-typography: '{typography.body-sm}'
    key-color: '{colors.muted}'
    code-typography: '{typography.code}'
  status-chip:
    typography: '{typography.label}'
    radius: '{rounded.full}'
    low-background: '{colors.accent-soft}'
    mid-background: '{colors.warning-soft}'
    mid-edge: '{colors.warning}'
    high-background: '{colors.danger-soft}'
    high-foreground: '{colors.danger}'
    off-background: '{colors.surface}'
    off-foreground: '{colors.muted}'
  rule-switch:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    radius: '{rounded.full}'
    allow-selected: '{colors.accent}'
    ask-selected: '{colors.warning}'
    deny-selected: '{colors.danger}'
    selected-foreground-allow-ask: '{colors.on-vivid}'
  guard-mode-switch:
    selected-background: '{colors.primary}'
    selected-foreground: '{colors.on-primary}'
  bar-button:
    background: '{colors.surface}'
    radius: '{rounded.full}'
    open-edge: '{colors.primary}'
    saved-background: '{colors.accent-soft}'
    saved-foreground: '{colors.ink}'
    count-background: '{colors.danger}'
  bar-flyout:
    background: '{colors.surface-raised}'
    radius: '{rounded.md}'
    width: 460px
  security-question-card:
    background: '{colors.surface}'
    radius: '{rounded.md}'
    figure-typography: '{typography.number-lg}'
    alert-figure: '{colors.danger}'
  verdict-banner:
    blocked-background: '{colors.danger-soft}'
    blocked-rule: '{colors.danger}'
    masked-background: '{colors.warning-soft}'
    masked-rule: '{colors.warning}'
    mask-token-background: '{colors.warning-soft}'
  new-brick:
    edge: '{colors.primary}'
  savings-bars:
    input: '{colors.primary}'
    output: '{colors.primary-deep}'
    subagent: '{colors.warning}'
---

# WaveStack vague 2 — Design Spine (delta)

Delta sur le [DESIGN.md principal](../../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md). Maquette de référence : [../maquette-vague-2.html](../maquette-vague-2.html) (v2). En cas de conflit, ce fichier et [EXPERIENCE.md](EXPERIENCE.md) l'emportent sur la maquette.

## Brand & Style

Même identité que l'appli : sobre, lisible de loin, relief sans flou. La vague 2 ajoute du sérieux « sécurité » sans changer de registre : pas de rouge plein écran, pas d'icône de cadenas décorative. L'état se lit par une pastille et un filet de couleur.

## Colors

Aucun nouveau jeton. Répartition des rôles :
- `{colors.accent}` et `{colors.accent-soft}` : autorisé, rien détecté, économie réalisée.
- `{colors.warning}` et `{colors.warning-soft}` : à décider, demander, masqué, risque moyen, part du sous-agent.
- `{colors.danger}` et `{colors.danger-soft}` : refusé, bloqué, risque élevé, compteur de refus.
- `{colors.primary}` : filet du détail déplié, contour « nouveau », sélection d'un mode.

La couleur n'est jamais seule : chaque état porte aussi un mot (« refusé », « masqué »).

## Typography

Rôles existants. `{typography.code}` pour les noms d'outils, les champs d'API et le JSON, uniquement dans le détail déplié. `{typography.number-lg}` pour les chiffres des cartes-questions de la page Sécurité.

## Elevation & Depth

Relief existant (`{colors.relief}`, décalage 4 px) sur les panneaux. Seuls les deux panneaux de la barre (`bar-flyout`) portent une ombre portée, parce qu'ils passent au-dessus du contenu.

## Components

- **disclosure-row** : ligne sur `{colors.surface}`, chevron ▸ de 26 px à gauche (tourne d'un quart de tour quand c'est ouvert), libellé, pastille d'état à droite. Le détail s'ouvre en dessous, en retrait, sur `{colors.surface-raised}` avec un filet gauche `{colors.primary}` ; il contient une liste clé / valeur et, au besoin, un bloc JSON défilant horizontalement. C'est le seul motif de détail technique de la vague 2.
- **status-chip** : quatre niveaux (low, mid, high, off), toujours avec un mot.
- **rule-switch** : trois segments Autoriser / Demander / Refuser ; le segment choisi prend la couleur de son niveau (vert, jaune, rouge).
- **guard-mode-switch** : Bloquer / Signaler / Désactivé (Bloquer / Masquer / Désactivé pour les données personnelles), segment choisi en `{colors.primary}`.
- **bar-button** : « Dépense 0,033 $ · économisé 0,029 $ » (économie en pastille {colors.accent-soft}, texte {colors.ink} : l'accent vif n'est pas lisible en texte sur fond clair) et « Journal » suivi d'un compteur rouge ; contour `{colors.primary}` quand le panneau est ouvert.
- **bar-flyout** : panneau ancré sous le bouton, aligné à droite, 460 px au plus.
- **security-question-card** : question en petit, chiffre en grand, une ligne d'explication.
- **verdict-banner** : bandeau dans la conversation, rouge si bloqué, jaune si masqué ; le texte masqué montre `[TÉLÉPHONE]`, `[E-MAIL]` en surlignage jaune.
- **new-brick** : la brique Garde-fous porte un contour `{colors.primary}` et la pastille « nouveau » tant que la vague est récente.
- **savings-bars** : deux barres empilées « Sans optimisation » et « Coût réel » à la même échelle, segments entrée, sortie et sous-agent, montant à droite.

## Do's and Don'ts

- Faire : un chevron ▸ pour tout détail technique ; le niveau de risque en mot et en couleur.
- Ne pas faire : de bulle ni de modale pour le détail ; d'information visible seulement au survol ; de JSON hors d'un détail déplié.
- Ne pas faire : de nouveau jeton de couleur pour la sécurité.
