---
title: 'Refonte visuelle « atelier de construction » : tokens, polices locales, relief, schéma à robot'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '5cbffb1a002c16df33b52e8afc30c7e52d4f55a2'
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** DESIGN.md (révisé le 2026-09-24, non commité) adopte la direction « atelier de construction » : nouveaux tokens (relief, pois, rayons 12/18/26, Fredoka / Atkinson Hyperlegible / JetBrains Mono), relief jouet à ombre pleine, fond à pois, sous-titres de volet, cadre « Harnais » et robot-mascotte dans le schéma. L'interface applique encore l'ancienne spine, et `tests/test_web_tokens.py` est rouge.

**Approach:** Aligner `tokens.css` sur le frontmatter, servir les trois polices en local (WOFF2 + `@font-face` dans un fichier à part), appliquer relief, rayons, pois et sous-titres dans `app.css` et `index.html`, redessiner le schéma autour d'un cadre Harnais et d'un robot, et durcir les tests de tokens. DESIGN.md fait foi ; il est commité avec son memlog et le code.

## Boundaries & Constraints

**Always:**
- `tokens.css` contient exactement les tokens `colors`, `typography`, `rounded`, `spacing` du frontmatter, ni plus ni moins (vérification dans les deux sens).
- Polices OFL servies depuis `/static/fonts/` (sous-ensemble latin de fontsource : Fredoka 500 et 600, Atkinson Hyperlegible 400 et 700, JetBrains Mono 400), avec leur licence OFL à côté ; `font-display: swap`. Aucun fichier statique ne référence `fonts.googleapis.com`.
- Relief : `box-shadow: 0 <offset> 0 <couleur>` sans flou, jamais de `rgba` ni de dégradé de volume. 4 px `relief` pour barre haute, volets, cartes de brique ; 4 px `relief-active` pour carte active, boutons secondaires, cadre du harnais ; 4 px `primary-deep` pour boutons primaires, qui s'enfoncent à 1 px (`:active`, `translateY` d'autant) ; 6 px `relief` pour tiroir et menu Volets. À plat : pièces indisponibles, contenu interne des volets, boutons icônes.
- Rayons selon DESIGN > Shapes ; bulles à coin de 6 px côté locuteur.
- Fond de page : pois `dot` de 1,3 px sur grille `dot-grid`, visibles seulement dans les gouttières (`gutter`) entre volets et barre haute flottante.
- Sous-titres de volet en `pane-subtitle`, encre douce, textes du tableau DESIGN > Components ; titres en casse normale, encre, `pane-title`.
- Schéma : cadre Harnais (bordure violette 2 px, étiquette pilule « Harnais », relief `relief-active`) contenant le robot au centre et une puce violet doux par brique voulue (icône + nom ; brique indisponible en tirets gris, raison en infobulle) ; sans brique : « Aucune brique : LLM nu ». Outils, serveurs MCP et fichiers restent des nœuds hors du cadre, reliés à lui. Les nœuds `brick` (`short_memory.history`, `system_prompt.prompt`) deviennent les puces : pas de doublon.
- Robot (`arch-model`) : trois poses (au repos, réfléchit, utilise un outil) déduites des événements du tour ; libellé accessible de la pose ; antenne clignotante seulement hors repos, coupée sous `prefers-reduced-motion`. Sous « Modèle », le nom du fichier du modèle chargé.
- Tout tient dans une fenêtre utile de 1280×650 sans barre de défilement de page.

**Décisions (2026-09-24) :**
- Fredoka n'a pas de fonction `tnum`, ni dans fontsource ni dans le fichier amont google/fonts (chiffres proportionnels, vérifié avec fontTools). Repli prévu par DESIGN : chaque compteur qui change en direct reçoit une largeur fixe (`min-width` en `ch`) ; `tabular-nums` reste posé pour Atkinson et JetBrains Mono, qui l'ont.
- Le nom du modèle passe par un champ `model` du nœud `core.model` de `architecture_changed` (AD-1 : le front ne le devine pas).

**Never:** pas de zones Local / Réseau ni de frontière dans le schéma, pas de sélecteur de scénario, de modèle ni de réglage « Aa », pas de mode sombre ; pas de refonte de `diagnostic.html` ; pas de requête vers un CDN à l'exécution ; pas de nouvelle dépendance Python ou JS.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Token orphelin | `tokens.css` déclare `--typography-label-letter-spacing` absent du frontmatter | Le test inverse échoue en le nommant | N/A |
| CDN | Un fichier de `static/` contient `fonts.googleapis.com` | Le test échoue en nommant le fichier | N/A |
| LLM nu | Aucune brique voulue | Cadre avec robot au repos et « Aucune brique : LLM nu » | N/A |
| Briques | Mémoire courte + Outils (2 outils réseau cochés) | 2 puces dans le cadre ; nœuds outils hors du cadre, réseau en jaune à tirets | N/A |
| Génération | `model_call_started` sans `model_call_ended` | Robot « réfléchit », antenne verte clignotante | N/A |
| Outil | `tool_started` sans `tool_ended` | Robot « utilise un outil », pastille verte | N/A |
| Sans modèle | Démarrage sans GGUF chargé | Robot sans nom de fichier | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/tokens.css` : à réécrire depuis le frontmatter (nouveaux `relief`, `relief-active`, `dot`, `pane-subtitle`, rayons 18/26, `relief-offset*`, `dot-grid` ; plus aucun `letter-spacing`).
- `src/wavestack/web/static/fonts.css` (nouveau) + `static/fonts/*.woff2` et `*-OFL.txt` : fichiers téléchargés depuis `cdn.jsdelivr.net/npm/@fontsource/{fredoka,atkinson-hyperlegible,jetbrains-mono}/files/*-latin-*-normal.woff2` (copie de travail déjà dans le scratchpad). Servis par le montage `/static` existant (`web/app.py` L106), rien à changer côté serveur.
- `src/wavestack/web/static/index.html` : lier `fonts.css` avant `tokens.css` ; dans chaque `.pane-header`, envelopper `h2.pane-title` et un `p.pane-subtitle` dans un `div.pane-heading`.
- `src/wavestack/web/static/app.css` : `body` (pois, `padding`/`gap` en `gutter`, `font-variant-numeric: tabular-nums`) ; `.top-bar` (carte flottante) ; `.layout/.right/.top-row` (gap `gutter`, plus de fond `line` en 1 px) ; `.pane` (rayon lg, relief) ; `.pane-title` (L170, sans majuscules ni `letter-spacing`) ; boutons (L185, L497, L781, L803) ; `.bubble*` (L286) ; `.brick-card*` (L617) ; `.edit-drawer` et `.pane-menu-list` (ombres `rgba` L88, L820 remplacées) ; rayons de `.ctx-segment`, `.step`, `.harness-event`, `.overflow-card`, `.outbound-payload` ; `.gauge-figures` largeur fixe ; retirer les usages de `--typography-*-letter-spacing` (L49, L174, L702) ; nouvelles règles du cadre, des puces et du robot.
- `src/wavestack/web/static/app.js` `renderSchema` (L1050) : réécrit. Réutiliser `svgEl`, `select`, `activeTurn`, `store.bricks.bricks` (`id`, `label_fr`, `wanted`, `available`, `reason_fr`), les classes `arch-node`/`is-network`/`is-unavailable`/`is-not-contacted` et la logique de titre/état existante (L1093-1114). Mémoriser les entrées dessinées (architecture, briques, pose, sélection) et ne pas reconstruire le SVG si rien n'a changé : `render()` tourne à chaque `model_delta` et relancerait l'animation de l'antenne.
- `src/wavestack/trace/catalog.py` `ArchitectureNode` (L50) : `model: str | None = None`.
- `src/wavestack/session/app_session.py` `_emit_architecture` (L302) : le nœud `core.model` porte `model` = nom (sans extension) du fichier chargé, `None` sans moteur ; retenir ce nom dans `_boot` (L502) au succès du chargement.
- `tests/test_web_tokens.py` : réutiliser `_expected_tokens` / `_css_custom_properties`.
- `tests/test_bricks.py` `test_wanted_brick_is_drawn_linked_to_the_harness` (L285) : `booted_session` démarre sur `fake.gguf`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/web/static/fonts/` + `fonts.css` -- copier les 5 WOFF2 et les 3 licences, déclarer 5 `@font-face` -- polices locales (NFR-3, NFR-4)
- [x] `src/wavestack/web/static/tokens.css` -- aligner sur le frontmatter -- test rouge
- [x] `src/wavestack/web/static/index.html` -- lien `fonts.css`, sous-titres des 5 volets -- DESIGN > Components
- [x] `src/wavestack/web/static/app.css` -- relief, rayons, pois, gouttières, titres, compteurs à largeur fixe, styles du schéma -- direction « atelier »
- [x] `src/wavestack/trace/catalog.py`, `src/wavestack/session/app_session.py` -- champ `model` du nœud `core.model` -- nom sous le robot
- [x] `src/wavestack/web/static/app.js` -- `renderSchema` à cadre, puces et robot ; `robotPose()` -- schéma
- [x] `tests/test_web_tokens.py` -- test inverse (aucun token orphelin), test « aucun `fonts.googleapis.com` dans `static/` », test « chaque `url()` de `fonts.css` existe » -- garde-fous
- [x] `tests/test_bricks.py` -- `model == "fake"` sur le nœud `core.model` -- champ testé
- [x] DESIGN.md et `.memlog.md` -- commités avec le code, sans modification

**Acceptance Criteria:**
- Given l'application lancée, when la page se charge, then les trois familles viennent de `/static/fonts/` et aucune requête ne sort vers un service de polices.
- Given une fenêtre utile de 1280×650, when les cinq volets sont visibles, then aucune barre de défilement de page, les en-têtes montrent titre et sous-titre, et le schéma montre cadre, robot et nœuds lisibles.
- Given un bouton primaire, when on le presse, then son relief passe de 4 px à 1 px et il descend d'autant.
- Given `uv run pytest` et `uv run ruff check`, then tout passe.

## Implementation Notes

- Polices : sous-ensembles latins fontsource, licences `*-OFL.txt` à côté. Fredoka mesurée dans la page à 32 px pour `0000` contre 21,4 px pour `1111` (chiffres proportionnels) : `.gauge-figures` reçoit `min-width: 34ch`, `tabular-nums` est posé sur `body`.
- 1280×650 (iframe de cette taille, application réelle) : `scrollWidth`/`scrollHeight` = 1280/650, aucun volet ne déborde, aucune requête hors origine. Les sous-titres des volets étroits (Briques, Vue humain) passent sur deux lignes plutôt que d'être coupés : en-têtes de 73 px au lieu de 56, la page tient.
- Puces du cadre élargies de 112 à 124 unités : « 📜 Prompt système » mesurait 106 unités.
- Poses du robot observées pendant un vrai tour avec la calculatrice : réfléchit → au repos → utilise un outil (antenne clignotante, pastille) → réfléchit → au repos. Le court « au repos » entre la fin de l'appel et le début de l'outil suit la règle du vert : le modèle ne travaille pas.
- Lignes front de la matrice (LLM nu, Briques, Génération, Outil) vérifiées dans le navigateur, faute de banc de test JS (même écart que 5b) ; « Sans modèle » couvert côté Python (`test_toggle_without_engine_raises_no_harness_error`).
- Retouches hors Code Map : `.composer input { min-width: 0 }` (le volet Vue humain défilait horizontalement avec « Arrêter »), `.ctx-heading` en typographie `label` (il héritait du titre de volet à 19 px).
- Un modèle chargé depuis un blob Ollama s'affiche `sha256-…` sous le robot (nom de fichier réel, tronqué à 20 caractères, entier dans l'infobulle).

## Spec Change Log

## Review Triage Log

Passe 1 (2026-09-24) : blind-hunter, edge-case-hunter, verification-gap.

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| 1 | `robotPose` lit `steps.at(-1)` : après `prefix_not_reused`, robot « au repos » pendant toute la génération (edge, verif) | medium | `app.js` L228-230 pousse l'étape après l'étape `call` ; `model_call_started` date `lastCall`, pas la dernière étape | patch |
| 2 | Échec de rechargement d'un GGUF : l'ancien nom reste sous le robot (edge) | low | `_boot` émet l'architecture `model_load` avec l'ancien nom, puis les retours d'échec ne réémettent pas | patch |
| 3 | `.composer input:focus { outline: none }` : focus invisible en couleurs forcées (edge, blind) | medium | En forced-colors, la couleur de bordure est imposée par le système et plus aucun contour ne reste | patch |
| 4 | `.gauge-figures` à 34ch : texte courant (~44 caractères) plus large, la barre bouge encore (edge) | low | « 533 / 3 584 tokens · 14,9 % · prochain tour » mesuré en page ; `min-width` n'est qu'un plancher | patch |
| 5 | « Vider la conversation » devenu bouton secondaire violet à relief (blind) | low | Action destructive ; DESIGN (reset-button) veut neutre et à plat pour ce cas | patch |
| 6 | Plus de 6 briques ou libellé long : puces hors du cadre (edge, blind) | low | 4 briques aujourd'hui, libellés ≤ 106 unités sur 124 ; plafond non marqué | patch (commentaire `ponytail:`) |
| 7 | Arêtes de colonne 2 masquées par les nœuds de colonne 1 : lecture en chaîne (edge, blind) | low | Choix des Design Notes ; visible dès 4 nœuds hors cadre | defer |
| 8 | `robotPose` et la clé de mémo sans test automatique (verif) | medium | Aucun banc de test JS ; poses vérifiées en navigateur | defer |
| 9 | Nom de blob Ollama `sha256-…` sous le robot (blind) | low | Conforme à l'intention (« nom du fichier ») ; la découverte a un nom lisible, non transmis à `boot` | defer |
| 10 | Puces non sélectionnables individuellement (blind) | low | Seul le schéma porte `data-component` ; clic sur une puce sélectionne le harnais ; usage rare, correctif ajoute gestionnaires | reject |
| 11 | Info-bulle « Outils : null » si brique indisponible sans raison (edge) | false | `_availability` renvoie toujours une raison quand `available` est faux (app_session L615-626) | reject |
| 12 | Pas de zones Local / Réseau ni de frontière (blind) | false | Exclu par l'intention (Never) | reject |
| 13 | DESIGN.md et memlog gardent l'hypothèse `tnum` ouverte, liste Colors coupée, relief des cartes contradictoire (blind) | low | Documents commités sans modification par demande ; signalé à l'utilisateur | reject |
| 14 | `.token-counter` sans largeur fixe (blind) | false | Bloc pleine largeur : sa boîte ne change pas, seul le texte suivant les chiffres bouge | reject |
| 15 | Boutons sans `:focus-visible` (blind) | false | Le contour de focus natif des boutons n'est pas retiré | reject |
| 16 | Groupes SVG cliquables sans clavier, robot `role="img"` (blind) | low | Préexistant pour les nœuds (story 2) ; le robot reste une image avec texte alternatif, comme DESIGN le demande | reject |
| 17 | `rx` 10/13 px, coin 6 px, icône 10 px, `RELIEF = 4` en dur (blind) | false | Pilules = demi-hauteur (un `rx` 9999 donnerait des ellipses en SVG) ; 6 px est la valeur de DESIGN ; l'icône n'est pas du texte | reject |
| 18 | « Volets ▾ » et « Modifier le prompt » en secondaire, bouton d'envoi pas rond (blind) | low | DESIGN n'assigne pas ces rôles ; libellé « Envoyer » gardé pour la lisibilité | reject |
| 19 | Test polices limité à `fonts.googleapis.com`, `len(urls) == 5` fragile (blind) | false | Test demandé tel quel ; le compte empêche un test vide si l'expression rate | reject |
| 20 | Spec et licences absentes du diff (blind) | false | Exclues volontairement du diff de revue | reject |

## Design Notes

Schéma (unités du `viewBox`, hauteur fixe ~150) : cadre de largeur fixe à gauche, robot centré, puces en deux colonnes de part et d'autre (alternées, 3 par colonne) ; nœuds hors cadre dans une grille de 3 lignes à droite, fichiers en dernier. Arête vers `core.harness` : segment horizontal du bord droit du cadre au nœud, tracé avant les nœuds (qui le masquent) ; autre arête : centre à centre. Icônes des puces : petite table dans `app.js` (`short_memory` 🧠, `system_prompt` 📜, `tools` 🔧, `mcp` 🔌, sinon 🧩).

Pose du robot, dérivée seulement (AD-1) :

```js
function robotPose() {
  const step = activeTurn()?.steps.at(-1);
  if (!step || step.ended) return "idle";
  if (step.type === "tool") return "tool";
  return step.type === "call" && step.startedAt ? "thinking" : "idle";
}
```

## Verification

**Commands:**
- `uv run pytest` -- expected: tout vert, dont `tests/test_web_tokens.py`
- `uv run ruff check . && uv run ruff format --check .` -- expected: propre
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks (if no CLI):**
- Page d'accueil dans Chrome à 1280×650 : `document.documentElement.scrollHeight <= innerHeight` et `scrollWidth <= innerWidth` ; `document.fonts` montre les trois familles chargées ; capture d'écran relue (relief, pois, sous-titres, cadre et robot).
- Largeur des chiffres Fredoka mesurée dans la page (`0000` contre `1111`) pour confirmer le repli.
