---
title: 'Volets redimensionnables'
type: 'feature'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '0dfdee3a9948d2ac10054b2d72ce3f1ca654bb4e'
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les volets ont des tailles fixes (briques 280 px, schéma 250 px, trois colonnes égales) : en salle, le formateur ne peut pas agrandir Orchestration ou le schéma sans masquer d'autres volets (sprint-change-proposal-2026-09-25, D1 à D4).

**Approach:** Les gouttières deviennent des poignées `pane-resize-handle` (souris et clavier) entre les colonnes de la rangée du haut, entre cette rangée et le schéma, entre les briques et le reste. Les tailles vivent dans des variables CSS, sont bornées par des minimums et mémorisées par le navigateur ; un double-clic rétablit les proportions par défaut.

## Boundaries & Constraints

**Always:**
- Minimums : 240 px de large, 160 px de haut pour chaque volet touché par un déplacement. Clavier : flèches, pas de 16 px (←/→ pour une poignée verticale, ↑/↓ pour une horizontale).
- Poignée accessible : `role="separator"`, `aria-orientation`, `tabindex="0"`, `aria-valuenow` (part en % du volet qui précède la poignée), `aria-valuemin`/`aria-valuemax`, `aria-label` en français nommant les deux volets.
- Une poignée n'apparaît qu'entre deux volets visibles voisins ; aucune en mode focus. Masquer un volet libère sa place selon les tailles courantes ; le réafficher lui rend sa dernière taille.
- Tant que rien n'a été déplacé, les proportions par défaut s'appliquent (tokens `brick-panel-width`, `architecture-band-height`, colonnes égales).
- Tailles survivant au rechargement via `localStorage` ; stockage absent, illisible ou corrompu → proportions par défaut, sans erreur.
- Décision (Anaël, 2026-09-25) : la configuration des volets (volets masqués) est mémorisée elle aussi, dans la même clé `localStorage` ; après F5, un volet masqué reste masqué (au moins un volet visible, même si le stockage dit le contraire). Le mode focus n'est pas mémorisé.
- Aspect (DESIGN.md) : invisible au repos ; au survol, au focus et pendant le glissement, pilule `{colors.primary}` de 4 × 32 px au milieu de la gouttière, curseur `col-resize` / `row-resize` ; zone de saisie d'au moins `{spacing.hit-target-min}` ; gouttière visible inchangée (`{spacing.gutter}`). Aucune animation.

**Never:** aucun changement de backend, d'événement ni de `/api/state` ; pas de nouvelle dépendance ; pas de token ajouté à DESIGN.md ; ne pas toucher au rendu d'Orchestration (8d) ni du schéma (8e), sauf si le tracé des fils ne suit plus.

## I/O & Edge-Case Matrix

| Scénario | État / action | Comportement attendu |
|---|---|---|
| Glisser une colonne | poignée Vue humain ∣ Contexte LLM, glisser de 100 px | Les deux volets changent de 100 px, Orchestration ne bouge pas. |
| Minimum | glisser jusqu'à ce qu'un voisin passe sous 240 px | Arrêt à 240 px ; au clavier, la flèche n'a plus d'effet. |
| Double-clic | poignée des colonnes | Les trois colonnes redeviennent égales ; poignée du schéma → 250 px ; poignée des briques → 280 px. |
| Masquer, réafficher | Contexte masqué après redimensionnement | Vue humain et Orchestration se partagent la place au prorata ; une seule poignée entre elles ; réafficher rend à Contexte sa part. |
| Rechargement | tailles déplacées, Contexte masqué, puis F5 | Mêmes tailles, Contexte toujours masqué (puce « + Contexte LLM »). |
| Fenêtre rétrécie | briques à 500 px, fenêtre réduite | Le reste garde au moins 240 px ; le schéma laisse au moins 160 px à la rangée du haut. |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/index.html` L29-155 -- `.layout` > (`bricks`, `.right` > (`.top-row` > `human`, `ctx`, `orch` ; `schema`)). Ne pas modifier : les poignées sont insérées par `app.js`.
- `src/wavestack/web/static/app.css` L162-215 -- mise en page en **flexbox** (pas de grille) : `.layout`, `.right`, `.top-row` avec `gap: var(--spacing-gutter)` ; `.layout > .pane[data-pane="bricks"]` (`flex: 0 0` token), `.top-row .pane` (`flex: 1`), `.right > .pane[data-pane="schema"]` (`flex: 0 0` token). L1157-1190 : mode focus (`body.focus-mode`, `flex … !important` sur `.is-focused`) à ne pas casser.
- `src/wavestack/web/static/tokens.css` -- `--spacing-gutter` 8, `--spacing-hit-target-min` 32, `--spacing-brick-panel-width` 280, `--spacing-architecture-band-height` 250, `--color-primary`. Ne pas modifier.
- `src/wavestack/web/static/app.js` L5-24 `PANES`, `PANE_LABELS`, `store` (`hiddenPanes`, `focusedPane`) ; L339-358 `hidePane`/`showPane`/`toggleFocus` ; L1712 `renderPaneVisibility` (appelée par `render()`), où recalculer visibilité et ARIA des poignées ; L2427 `boot()` pour créer les poignées et lire le stockage. L2471 : un `ResizeObserver` sur `#schema` retrace les fils : il suffit si le schéma change de taille.
- `tests/test_web_app.py` -- sert `/static/app.js` ; aucun test JS dans le dépôt.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/web/static/app.css` -- tailles en variables CSS (`--pane-bricks-width`, `--pane-schema-height`, `--pane-human-grow`, `--pane-ctx-grow`, `--pane-orch-grow`) avec les tokens comme valeurs par défaut ; bornes par `clamp()` avec `100%` pour la fenêtre rétrécie ; style `.pane-resize-handle` (gouttière absorbée par des marges négatives, zone de saisie élargie, pilule) ; masquée en mode focus.
- [x] `src/wavestack/web/static/app.js` -- `store.paneSizes`, lecture/écriture `localStorage` protégée des tailles et de `hiddenPanes` (écriture dans `hidePane`/`showPane` et en fin de redimensionnement) ; création des 4 poignées au `boot()` ; glisser (pointer events + capture), flèches, double-clic ; visibilité et ARIA des poignées dans `renderPaneVisibility`.

**Acceptance Criteria:**
- Given l'interface au lancement sans stockage, when on l'affiche, then la disposition est identique à celle d'avant la story.
- Given une poignée focalisée au clavier, when on presse une flèche, then la limite bouge de 16 px et `aria-valuenow` suit.
- Given le mode focus, when on l'active puis le quitte, then aucune poignée n'est visible pendant, et les tailles choisies reviennent après.
- Given le schéma redimensionné, when le glissement se termine, then tronc, rails et chemin suivent les nœuds.

## Implementation Notes

- Fichiers touchés : `app.css`, `app.js` seulement. Clé `localStorage` `wavestack.panes` = `{hidden, sizes}` ; valeurs validées (JSON invalide, nombre hors bornes, cinq volets masqués → défauts).
- Zone de saisie des poignées verticales asymétrique (6 px à gauche, 18 px à droite) pour ne pas couvrir la barre de défilement native du volet de gauche.
- Poignée des briques (après revue) : garantit 240 px à chaque colonne visible du haut ; la borne suit le poids de la colonne la plus étroite (`240 × somme des poids / plus petit poids + gouttières`). Vérifié dans Chrome : colonnes égales → briques jusqu'à 394 px, colonnes 240/240/240 ; une colonne déjà à 240 px bloque l'élargissement des briques.
- Après revue : en-têtes de volet et `#event-log-head` passent au-dessus de la zone de saisie des poignées (`z-index: 2`) ; flèches avec Alt/Ctrl/Meta ignorées ; pilule visible en `forced-colors`. Vérifié dans Chrome (point le plus bas du bouton du journal, haut des boutons du schéma, Alt+←).
- Couverture de la matrice : aucune infrastructure de test JS dans le dépôt et « pas de nouvelle dépendance » ; les six lignes ont été vérifiées à la main dans Chrome (fichiers statiques servis sans backend). Non vérifié : tracé des fils avec de vrais nœuds pendant un tour.

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter BH, edge-case-hunter EC, verification-gap VG).

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| BH1, EC2, EC10 | Colonnes du haut sans minimum : glisser les briques les écrase sous 240 px | medium | `moveBoundary` borne `.right` entier à 240 px, pas chaque colonne visible ; la règle « chaque volet touché par un déplacement » est violée. Le rétrécissement de fenêtre n'est pas un déplacement (hors règle). | patch |
| BH6, EC5, EC6, VG-autre | La zone de saisie élargie déborde dans les volets voisins | medium | Poignée du schéma : 12 px vers le haut sur `.pane-body-orch` (rembourrage 0) → le bas du bouton `#event-log-head` (32 px) démarre un redimensionnement au lieu de déplier le journal ; 4 px du haut des boutons d'en-tête du schéma (rembourrage 8 px). Les 6 px de contenu couverts à droite des poignées verticales sont le prix des 32 px exigés : accepté. | patch |
| EC7 | Flèches avec Alt/Ctrl/Meta avalées | low | `keydown` ne teste aucun modificateur ; Alt+← (retour) redimensionne. Correction directe d'une ligne. | patch |
| BH5 | Aucun indicateur de focus en contraste élevé Windows | low | `outline: none` et pilule en `background`, que `forced-colors` remplace. Règle `@media (forced-colors: active)` de quelques lignes. | patch |
| VG1, VG2, BH11 | Persistance et arithmétique du redimensionnement sans test automatique | medium (non couvert) | Aucun exécuteur de test JS dans le dépôt ; « pas de nouvelle dépendance ». | defer |
| BH2, EC9 | Poids quasi nuls ou partiellement invalides acceptés au chargement | low | Seule l'application écrit la clé ; valeurs arrondies, jamais sous 240 px de part. État non démontré. | rejeté |
| BH3, EC8 | Le double-clic d'une poignée de colonne remet les trois colonnes à égalité | false | Voulu par la matrice gelée (« Les trois colonnes redeviennent égales »). | rejeté |
| BH4 | Pas de remise à zéro au clavier (Entrée, Début, Fin, Échap) | low | Facultatif dans le motif WAI-ARIA « window splitter » ; non demandé. | rejeté |
| BH7 | Mesure synchrone à chaque `pointermove` | low | Une seule mise en page forcée par événement, que le navigateur ferait de toute façon pour l'image suivante ; aucun effet perceptible. | rejeté |
| BH8 | ARIA incomplète (`aria-controls`, `aria-valuetext`, valeur posée une image plus tard) | low | `aria-label` nomme les deux volets ; la poignée reste `hidden` jusqu'au premier rendu. | rejeté |
| BH9 | Donnée mémorisée sans numéro de version | false | Aucun changement de format prévu ; une valeur inconnue retombe sur les défauts. | rejeté |
| BH10 | Seuls `hidePane`/`showPane` enregistrent | false | Ce sont les seuls endroits qui modifient `store.hiddenPanes` (`app.js` L344, L350). | rejeté |
| BH12 | Rendu des puces et du menu fait deux fois au `boot()` | low | Fonctions idempotentes ; coût nul. | rejeté |
| EC1 | Second pointeur pendant un glissement | low | Deux doigts sur une gouttière de 8 px : improbable ; la garde ajoute une branche. | rejeté |
| EC3, EC4 | `clamp()` inversé sous 488 px de large ou 328 px de haut | low | Fenêtres hors cible (1280×650 ; sous 1024 px, mode focus). | rejeté |
| EC11 | Disposition « identique » non tenue sur fenêtre étroite | false | La matrice gelée (« Fenêtre rétrécie ») demande justement ce comportement ; à 1280×650, 280 et 250 px inchangés (vérifié). | rejeté |

## Design Notes

Colonnes du haut en poids `flex-grow` (base 0) plutôt qu'en pixels : masquer un volet répartit sa place au prorata, le réafficher rend sa part, sans recalcul. Au glissement, on mesure les largeurs réelles des deux voisins, on les borne, puis on convertit en poids en gardant constante la somme des poids visibles (les poids des volets masqués ne bougent pas). Briques et schéma restent en pixels.

Poignée zéro-encombrement : `flex: 0 0 var(--spacing-gutter); margin: 0 calc(-1 * var(--spacing-gutter))` (vertical ; idem en hauteur) la pose exactement sur la gouttière existante sans changer l'espacement ; un `::before` élargit la zone de saisie à 32 px, un `::after` dessine la pilule.

## Verification

**Commands:**
- `uv run pytest` -- expected: tous verts.
- `uv run ruff check .` -- expected: aucun problème.

**Manual checks (if no CLI):**
- Navigateur à 1280×650 : dérouler la matrice ci-dessus (souris, clavier, double-clic, masquer/réafficher, F5, mode focus, fenêtre rétrécie) ; console sans erreur.
