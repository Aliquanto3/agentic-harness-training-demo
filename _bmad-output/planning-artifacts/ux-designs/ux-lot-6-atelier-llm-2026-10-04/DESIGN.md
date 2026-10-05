---
title: DESIGN — Atelier LLM, la boucle du modèle (lot 6)
status: final
created: 2026-10-05
updated: 2026-10-05
sources:
  - ../../../implementation-artifacts/plan-corrections-2026-10-04.md
  - ../ux-agentic-harness-training-demo-2026-09-22/DESIGN.md
name: WaveStack — Atelier LLM, lot 6
description: >-
  Delta visuel du lot 6 sur le DESIGN.md principal : la boucle du modèle en trois étapes
  empilées (INPUT, TRANSFORMATION, OUTPUT) en tête de /llm, à la place des sections 1 et 2,
  sur le schéma commun du lot 2 (static/diagram.js, règles diagram-* de pages.css). Aucun
  nouveau jeton de couleur ni de typographie : tout renvoie aux jetons du DESIGN.md
  principal, à reverser dans ce dernier après la fusion du lot 3.
# Jetons hérités tels quels du DESIGN.md principal (non redéclarés ici) : colors.*,
# typography.*, rounded.*, spacing.*. Les composants ci-dessous ne référencent qu'eux.
components:
  llm-stage:
    background: '{colors.surface-raised}'
    border: '{colors.line}'
    radius: '{rounded.lg}'
    relief: '{colors.relief}'
    number-background: '{colors.ink-fill}'
    number-foreground: '{colors.on-ink}'
    title-typography: '{typography.pane-title}'
    caption-border: '{colors.primary}'
    caption-background: '{colors.surface}'
  llm-stage-tag:
    background: '{colors.ink-fill}'
    foreground: '{colors.on-ink}'
    typography: '{typography.label}'
    radius: '{rounded.full}'
  llm-stage-tag-illustrative:
    background: '{colors.surface-raised}'
    foreground: '{colors.ink}'
    border: '{colors.ink-soft}'
    border-style: dashed
  llm-stage-link:
    stroke: '{colors.ink-soft}'
    typography: '{typography.body-sm}'
  llm-input-column:
    segment-typography: '{typography.chat}'
    segment-size: 22px
    cut-mark: '{colors.primary}'
    arrow: '{colors.ink-soft}'
    chip: '{components.token-chip}'
    id-typography: '{typography.number}'
    produced-chip-background: '{colors.produced-soft}'
    produced-chip-border: '{colors.ink-soft}'
  llm-transfo-canvas:
    background: '{colors.discipline-neutral-soft}'
    border: '{colors.ink-soft}'
    border-style: dashed
    radius: '{rounded.md}'
    cell-positive: '{colors.primary}'
    cell-negative: '{colors.discipline-context}'
    cell-stroke: '{colors.line}'
    attention-arc: '{colors.primary}'
    neuron: '{colors.discipline-context}'
    expert-active: '{colors.accent-soft}'
    focus-frame: '{colors.state-active}'
  llm-layer-stack:
    attention: '{colors.primary-soft}'
    attention-border: '{colors.primary}'
    recurrent: '{colors.surface}'
    recurrent-border: '{colors.ink-soft}'
    done: '{colors.primary}'
    now-halo: '{colors.state-active}'
  llm-output-part:
    background: '{colors.surface}'
    border: '{colors.line}'
    radius: '{rounded.md}'
    active-halo: '{colors.state-active}'
  llm-output-bars:
    track: '{colors.line}'
    model-fill: '{colors.primary-soft}'
    model-stroke: '{colors.primary}'
    chance-fill: '{colors.primary}'
    dropped: '{colors.muted}'
    word-typography: '{typography.code}'
    value-typography: '{typography.number}'
  llm-banner:
    background: '{colors.warning-soft}'
    border: '{colors.warning}'
    typography: '{typography.body-sm}'
---

# Atelier LLM, la boucle du modèle — Design Spine (delta du lot 6)

Ce document ne redéfinit rien du DESIGN.md principal
(`../ux-agentic-harness-training-demo-2026-09-22/DESIGN.md`) : il en hérite la charte,
les deux thèmes, les jetons et la typographie, et ne décrit que les composants du lot 6.
Maquette de référence : [mockups/llm-loop.html](mockups/llm-loop.html) (v3, interactive) ;
les essais précédents sont dans `.working/`. En cas d'écart, ce document et EXPERIENCE.md
l'emportent sur la maquette.

## Brand & Style

La boucle emprunte à 3Blue1Brown sa grammaire, pas son esthétique : un vecteur se dessine
comme une colonne de cellules, l'attention comme des arcs dont l'épaisseur dit le poids, le
MLP comme un petit réseau qui s'élargit puis se resserre, la sortie comme un histogramme de
mots. Tout reste dans la direction « atelier de construction » : cartes à grands arrondis,
relief plein, halo vert pour ce qui agit. Seuls bougent les cellules d'un vecteur qui change
(transition de 0,5 s) et les barres d'un réglage qui change (0,25 s), coupés par
`prefers-reduced-motion`.

L'honnêteté du schéma fait partie du style. Les étapes INPUT et OUTPUT sont réelles
(étiquette pleine) ; l'étape TRANSFORMATION est illustrative (étiquette et cadre en
tirets, fond neutre) et le dit en toutes lettres.

## Colors

Aucun nouveau jeton.

| Rôle | Jeton | Pourquoi |
| --- | --- | --- |
| Carte d'étape | `{colors.surface-raised}`, bordure `{colors.line}`, relief `{colors.relief}` | Les cartes de section de l'écran LLM. |
| Numéro d'étape | `{colors.ink-fill}` / `{colors.on-ink}` | Le disque numéroté des sections. |
| Étiquette « Réel » | pilule `{colors.ink-fill}` / `{colors.on-ink}` | Pleine : l'appli le lit dans le moteur. |
| Étiquette et cadre « Illustratif » | tirets `{colors.ink-soft}`, fond `{colors.discipline-neutral-soft}` | Neutre ; la forme (tirets) porte le sens, pas la couleur seule. |
| Marque de découpe (INPUT) | soulignement 3 px `{colors.primary}` | La couleur de la marque. |
| Token produit (revenu de l'OUTPUT) | `{colors.produced-soft}`, bordure en tirets `{colors.ink-soft}`, texte en italique | Les blocs produits de Contexte LLM. |
| Cellule de vecteur | `{colors.primary}` (positif) / `{colors.discipline-context}` (négatif), opacité = intensité | Deux teintes déjà lisibles dans les deux thèmes ; le signe est aussi dit par l'explication, jamais par la seule couleur. |
| Arc d'attention | `{colors.primary}`, épaisseur = poids, pourcentage écrit | Le poids est toujours écrit. |
| Neurones / experts | `{colors.discipline-context}` ; expert actif `{colors.accent-soft}` + bordure épaisse + « actif » | Le mot « actif » double la couleur. |
| Pile des couches | attention `{colors.primary-soft}` bordé `{colors.primary}`, récurrente `{colors.surface}` bordé en tirets, traversée pleine, en cours halo `{colors.state-active}` | Forme et couleur. |
| Barres OUTPUT | piste `{colors.line}` ; probabilité du modèle `{colors.primary-soft}` cerclé `{colors.primary}` ; chance `{colors.primary}` plein ; écarté `{colors.muted}` + « écarté (top-p) » | Reprise de `distribution-bars`. |
| Partie en action | halo `{colors.state-active}` | Règle commune `diagram-block.is-active`. |
| Bandeau D4 | `{colors.warning-soft}` bordé `{colors.warning}` | Le bandeau « indisponible » de l'écran LLM. |

## Typography

Reprise stricte du DESIGN.md principal : titre d'étape en `pane-title` agrandi (20 px), sous-
titre en `body` encre douce ; étiquettes de ligne et de zone en `label` majuscule ; texte
découpé de l'INPUT en `chat` à 22 px (lisible au fond de la salle) ; tokens et mots des
graphiques en `code` (sans ligature) ; identifiants, pourcentages et réglages en `number` ;
explications en `body`, notes en `body-sm`.

## Layout & Spacing

- **Trois cartes empilées** en tête de `/llm` (INPUT, TRANSFORMATION, OUTPUT), reliées par
  un trait vertical de 56 px et sa phrase (« les identifiants entrent dans le modèle », « le
  vecteur du dernier token est comparé à tout le vocabulaire »). Les sections Chargement,
  Lecture du prompt, Génération et Raisonnement suivent, renumérotées 4 à 7.
- **Chaque carte tient entière dans l'écran** (contrainte d'Anaël) : vérifié à 1600 × 1000
  (300, 730, 648 px) et à 1366 × 768 (300, 683, 648 px). Le canevas SVG de la
  TRANSFORMATION est limité à 60 % de la hauteur de l'écran ; les graphiques de l'OUTPUT
  montrent six mots au plus.
- **En-tête de carte** : numéro, titre et sous-titre, étiquette Réel / Illustratif, pas à pas
  poussé à droite. **Pied** : la légende du pas en cours (filet gauche 4 px).
- **INPUT** : grille « étiquettes de ligne (8,5 em) | colonnes de tokens | compteurs ». Une
  colonne par token, cinq lignes de hauteur fixe (texte 34, flèche 36, token 36, flèche 36,
  identifiant 30 px). Les colonnes sont collées au pas 1 (le texte se lit d'un bloc), puis
  s'écartent de 26 px (transition 0,45 s) quand le texte se découpe. Les colonnes passent à
  la ligne pour un long texte.
- **TRANSFORMATION** : canevas (1fr) | panneau (330 px). Canevas en `viewBox` 820 × 420 :
  tokens et identifiants en haut, vecteurs en bas (y 262), l'opération du pas entre les
  deux, le MLP ou les experts à droite du dernier vecteur.
- **OUTPUT** : trois parties empilées (Logits, Tirage, Token tiré) reliées par une flèche et
  sa phrase. Tirage : curseurs (300 px) | graphique.
- **Sous 900 px** : une colonne partout (étiquettes de ligne de l'INPUT masquées, panneau
  sous le canevas, curseurs au-dessus du graphique). Hors cible (projection et PC), mais
  aucun défilement horizontal.

## Elevation & Depth

Cartes d'étape en relief plein `{colors.relief}` (comme les sections) ; parties de l'OUTPUT
et canevas à plat. L'explication d'un bloc reste l'encart `diagram-explain` de la règle
commune.

## Shapes

Cartes `{rounded.lg}`, canevas et parties `{rounded.md}`, puces `{rounded.sm}`, pilules
`{rounded.full}`. Cellules de vecteur carrées de 15 unités du `viewBox`, 2 unités d'écart.

## Components

- **Carte d'étape (`llm-stage`)** : en-tête, corps, légende du pas. Trois instances :
  `#stage-input`, `#stage-transfo`, `#stage-output`.
- **Colonnes de l'INPUT (`llm-input-column`)** : le morceau de texte (souligné en
  `{colors.primary}` une fois découpé), une flèche, la puce `token-chip` (même alternance de
  fonds, blancs visibles ␣ ↵), une flèche, l'identifiant. Compteurs à droite en `number-lg` :
  caractères, tokens, « nombres entre 0 et {vocabulaire − 1} ». Un token revenu de l'OUTPUT
  a la puce « produit » et son texte en italique encre douce.
- **Canevas de la TRANSFORMATION (`llm-transfo-canvas`)**, un dessin par pas :
  - *Embeddings* : une table à gauche (« {vocabulaire} lignes × {dimension} »), une ligne
    allumée par token, un fil en tirets de cette ligne au vecteur du token.
  - *Attention* : un arc par token précédent vers le dernier token, épaisseur = poids, le
    pourcentage au-dessus du vecteur source ; une petite boucle « {p} lui-même ».
  - *MLP* : un réseau 8 → 16 → 8 neurones à droite du dernier vecteur ; la couche cachée
    occupe toute la hauteur (le vecteur « s'élargit »), cinq neurones allumés ; « entrée »,
    « sortie », et « en vrai : {dimension} → {largeur} → {dimension} ». MoE : un routeur et
    six experts, deux « actifs ».
  - *… et ainsi de suite* : une pile de six couches fantômes.
  - *Dernier vecteur* : les autres tokens estompés (30 %), le dernier cerclé de vert, une
    flèche vers le bas « vers l'OUTPUT : comparé aux {vocabulaire} tokens du vocabulaire ».
  Sous le canevas, la note en tirets : « Le moteur n'expose ni les poids d'attention ni les
  états cachés : 5 tokens, 8 nombres par vecteur et une poignée de neurones montrent la
  forme du calcul ; les couleurs sont inventées, les chiffres du panneau sont ceux du
  modèle. » (avec le vrai nombre de tokens s'il diffère).
- **Panneau de la TRANSFORMATION** : titre du pas en `heading`, explication en `body`, encart
  « En vrai, pour {modèle} » (`{colors.surface}`, `{rounded.sm}`) : vecteurs, table
  d'embedding, couches (têtes, têtes K/V, MLP ou experts) ; puis « Couches du modèle »
  (`llm-layer-stack`) : une barre de 9 × 22 px par couche, et sa légende.
- **Parties de l'OUTPUT (`llm-output-part`)** :
  - *Logits* : « les 6 plus probables après « {trois derniers tokens} » », six lignes mot |
    barre de probabilité du modèle | pourcentage, puis « reste du vocabulaire » en italique.
  - *Tirage* : les quatre réglages (`sampling-controls` compacts : nom, curseur, valeur ;
    « off » pour top-k à 0) ; le graphique « chance d'être tiré », mêmes mots dans le même
    ordre, chaque ligne gardant aussi la probabilité du modèle en petite barre fantôme ; un
    écarté grisé avec « écarté (top-k | top-p | min-p) » ; dessous, « {gardés} gardés sur 6 ·
    la chance est partagée entre eux seuls ».
  - *Token tiré* : bouton primaire « 🎲 Tirer le token suivant », la puce tirée (20 px,
    contour encre 2 px), bouton secondaire « ↺ Ajouter à la suite », « Retirer » (annule le
    dernier ajout), l'historique des derniers tirages en `body-sm`.
- **Bandeau D4 (`llm-banner`)** : en tête de la TRANSFORMATION seulement (c'est là que le
  schéma est inexact). « ⚠ Schéma simplifié, inexact pour cette architecture. » puis la
  raison chiffrée (EXPERIENCE.md).

## Do's and Don'ts

- **Do** écrire « Illustratif » et la note sous le canevas, en plus des tirets.
- **Do** écrire chaque poids et chaque pourcentage : jamais l'épaisseur ou la couleur seules.
- **Do** n'afficher dans l'INPUT et l'OUTPUT que des valeurs reçues de la session (AD-1).
- **Don't** présenter les couleurs des vecteurs ou les poids d'attention comme lus dans le
  moteur.
- **Don't** introduire de couleur hors des jetons du DESIGN.md principal.
- **Don't** laisser une carte d'étape dépasser la hauteur de l'écran à 1366 × 768.
