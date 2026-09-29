---
title: 'Lot K, suite : corrections après la contre-vérification sur PC du 2026-09-29 (K1 à K3, favicon)'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: '1eae76c0f1868bf9a19bff3cfbc23ac6341f5b88'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-lot-k-corrections-recette-pc-2026-09-29.md'
  - '{project-root}/_bmad-output/implementation-artifacts/resultats-lot-k-2026-09-29.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La contre-vérification du lot K (`resultats-lot-k-2026-09-29.md`, section
« Contre-vérification indépendante ») relève : au zoom 150 % émulé (853 px CSS), « Réinitialiser »
sort de la barre haute de 114 px et la page défile horizontalement (56 px à 911 px), régression du
lot K (K1) ; IAM p1 et p2 et Souveraineté p1 coupés par la réserve de 512 tokens avant les liens
(K2) ; SOC p2 bloqué par H1 mais « Transmettez ce fichier au Démonstrateur » (K2) ; sans secours,
Lazy répond de tête après `load_tool_doc` et Souveraineté affirme « J'ai effectué une recherche »
avec des jeux inventés (K3) ; Edge reçoit un 404 sur `/favicon.ico` (K7).

**Approach:** Quatre corrections sur `claude/lot-k-recette-pc` (tête `1eae76c`), un commit par
point, chacune avec un test automatique : palier CSS sous 1 000 px CSS ; prompts IAM, Souveraineté
p1 et SOC p2 reformulés ; consignes de Lazy loading et Souveraineté réécrites ; favicon servi.

**Décision (Anaël, 2026-09-29) :** avec le 2B, les secours « Forcer l'appel » restent la règle et
sont la leçon : les consignes décrivent ce qu'on observe (le modèle s'arrête après le chargement,
voire prétend avoir cherché), pourquoi (petit modèle), et « Forcer l'appel » comme démonstration
du harnais. Le harnais et AD-17 ne changent pas.

## Boundaries & Constraints

**Always:** textes en français, code en anglais ; `uv`, `ruff`, `pytest` ; E2E sans FAIL sous
Windows (`PYTHONUTF8=1`), dossier de données temporaire ; puce « · lié » entière (10 px de marge) à
1 280, 1 366, 1 440 et 1 600 px, normal et projection (contrôle existant inchangé) ; 1 024 px
inchangé ; déclencheurs du faux fournisseur (`tools/e2e/fake_openai.py` : « entra id »,
« data.gouv », pas de « confidentiel » dans SOC p2) gardés.

**Never:** toucher au harnais (session, lazy loading, actions forcées), à AD-17, à la réserve de
sortie ; retirer « Réinitialiser » ou son texte ; masquer la puce « · lié » au-dessus de 1 100 px.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Attendu |
|---|---|---|
| Zoom 150 % | viewport 853 × 433 et 911 × 512, normal et projection, puce liée affichée ou non | barre sur une ligne, « Réinitialiser » entier dans la barre et la fenêtre, `scrollWidth − clientWidth` ≤ 1 |
| Zoom 125 % | 1 024 × 700 | comme avant (légende visible, non recouverte) |
| Favicon | `GET /favicon.ico` ; les quatre pages (`/`, `/diagnostic`, `/models`, `/llm`) | 200, image ; chaque page déclare `<link rel="icon">` |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/app.css` -- barre haute : `.top-bar` l. 172 (gap, padding
  `spacing-4`), `.gauge` l. 549, `.gauge-stack` l. 636 (`width: 300px`), `.gauge-legend` l. 677,
  `.gauge-figures` l. 706 (cède, texte entier en `title`) ; lot K l. 4696-4835 : facteurs de
  repli, `.top-bar > .gauge` `min-width: calc(300px + spacing-3)` (l. 4712), palier 1 600, 1 400,
  1 100 (titre masqué, puce liée rétrécissable). Sélecteur de thème déjà compact sous 1 400 px
  (l. 4162) et en projection sous 1 600 (l. 4776). Projection : `:root.projection` l. 4575.
- Mesures Chromium (tête `1eae76c`, sans puce) : 853 px normal, « Réinitialiser » finit à 967
  pour une barre à 845 (scenario 64, gauge 312, window 59, Volets 73, indicateur 64, modèle 48,
  « Projection » 81, LLM 33, thème 34, reset 103, gap 8, padding 16) ; projection, 962 (scénario
  40, gauge 312, window 61, Volets 86, indicateur 32, modèle 40, « Projection » 95, LLM 39, thème
  38, reset 123).
- `src/wavestack/web/static/index.html` l. 13-66 -- barre haute ; bouton `#projection-toggle`
  (`projection-toggle-long` / `-short`, `aria-label` « Mode projection »). `.window-panel` l. 3900
  (ancré à gauche de « Fenêtre », 30 rem).
- `tools/e2e/run_e2e.py` -- `_fully_visible` l. 1150, `_top_bar_problems` l. 1599, contrôle
  lot K dans `s_linked_view` l. 2360-2394 (4 largeurs puis 1 024) : y ajouter 853 × 433 et
  911 × 512, projection puis normal.
- `content/scenarios.yaml` -- `mcp_lazy` l. 206, `soc` prompts l. 382-391, `iam` l. 395,
  `sovereignty` l. 428.
- `tests/test_program.py` -- `test_small_model_prompts_name_the_tool_or_skill_and_the_fallback`
  l. 230 (libellés exacts, ordre des secours de Souveraineté, « deux liens Microsoft Learn » dans
  les prompts IAM, SOC p2 « ne la contourne pas » et « transmettre ») ; test `fits` (prompts plus
  longs : à relancer).
- `tests/test_e2e_fake_openai.py` l. 238-285 -- SOC, IAM et Souveraineté par le faux fournisseur.
- `src/wavestack/web/app.py` l. 245-267 -- `/static` monté, routes des quatre pages ; tests web
  existants (`tests/test_web_app.py`).

## Tasks & Acceptance

**Execution:**
- [x] 1 · `app.css`, `index.html`, `run_e2e.py` -- palier `@media (width < 1000px)` : légende de
  la jauge masquée et barre de la jauge à 180 px (chiffres cèdent, texte entier en infobulle comme
  aujourd'hui), gaps `spacing-1`, padding de la barre `spacing-2`, noms (scénario, indicateur,
  sélecteur de modèle) à leur minimum (3 / 2 / 2,5 rem, projection comprise), « Mode projection »
  réduit à « Aa » (nouveau `span` `aria-hidden`, nom accessible et infobulle inchangés), thème
  compact (déjà). E2E : à 853 × 433 et 911 × 512, projection puis normal, puce liée affichée :
  `_top_bar_problems(r, None)` vide, « Réinitialiser » dans la fenêtre, aucun défilement
  horizontal, panneau « Fenêtre » ouvert entier dans la fenêtre.
- [x] 2 · `content/scenarios.yaml`, `tests/test_program.py` -- IAM p1 et p2 : chercher, puis
  « en 5 lignes au plus : d'abord deux liens Microsoft Learn tirés du résultat, puis
  l'explication » ; Souveraineté p1 : « en 5 lignes au plus : trois jeux au plus, chacun avec son
  lien data.gouv.fr en premier » ; SOC p2 : « … dis-le et propose de transmettre la vérification à
  un analyste SOC habilité ». Tests : « 5 lignes au plus » dans ces prompts, « liens » avant
  l'explication, « analyste » et « habilité » dans SOC p2 ; `fits` vert.
- [x] 3 · `content/scenarios.yaml`, `tests/test_program.py` -- consignes de `mcp_lazy` et
  `sovereignty` : ce qu'on observe (arrêt après `load_tool_doc`, réponse de tête, voire « j'ai
  cherché » sans appel ni requête sortante : Orchestration le montre), pourquoi (un petit modèle
  enchaîne mal deux appels et prend la documentation pour la réponse), le geste « Forcer
  l'appel » présenté comme la démonstration : le harnais garantit l'appel que le modèle ne fait
  pas. Libellés et ordre existants gardés. Test : ces trois éléments présents dans les deux
  consignes.
- [x] 4 · `static/favicon.svg`, `app.py`, quatre pages HTML, `tests/test_web_app.py` -- icône SVG
  (violet encre de la barre), `<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">`
  sur chaque page, route `/favicon.ico` qui sert la même icône. Test : 200 et `image/svg+xml`,
  lien présent sur les quatre pages.
- [x] Fin · spec du lot K (Implementation Notes : décisions, « À vérifier sur PC ») et prompt de
  recette court `prompt-recette-lot-k-suite-2026-09-29.md` : zoom 150 % émulé puis vrai zoom
  d'Edge, IAM p1 et p2, Souveraineté p1 sans secours (longueur, liens), SOC p2 (destinataire).

**Acceptance Criteria:**
- Given la tête du lot, when on lance `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest -q` et l'E2E, then tout est vert, et le test de chaque point échoue sur le
  commit précédent.
- Given 853 × 433, when la page est chargée, then `document.scrollingElement.scrollWidth` ne
  dépasse pas `clientWidth` et « Réinitialiser » est entier dans la barre.

## Implementation Notes

Commits, un par point, sur `claude/lot-k-recette-pc` (base `1eae76c`) : `e4da3d3` (1, K1),
`0bc5f56` (2, K2), `9bca13d` (3, K3), `e103b5e` (4, K7). Le test de chaque point a été lancé sur
le code d'avant son point (fichiers remis en place le temps du test) : il échouait à chaque fois
(détail plus bas).

### Décisions prises par défaut

- **Point 1.** Palier `@media (width < 1000px)` en fin de `app.css`, après celui de 1 100 px :
  légende de la jauge masquée (l'infobulle de chaque segment nomme sa discipline), barre de la
  jauge à 180 px et minimum de `.gauge` à `180px + spacing-3` (normal et projection), gaps
  `spacing-1` et padding `spacing-2` (normal et projection), bouton de projection à « Aa »
  (nouveau `span.projection-toggle-tiny`, `aria-hidden` ; nom accessible « Mode projection » et
  infobulle inchangés) avec un padding `spacing-2`. Noms : 3 / 2 / 2,5 rem en mode normal ; la
  projection garde ses minimums déjà plus bas sous 1 400 px (scénario 2,5 rem, indicateur 2 rem,
  sélecteur de modèle 2,5 rem) : les remonter à 3 rem aurait élargi le scénario (les « −8 » de
  la Design Note pour la projection ne se retrouvent pas dans les mesures). La puce « · lié »
  reste rétrécissable sous 1 100 px (inchangé) : elle cède avec les chiffres de la jauge.
  Mesures Chromium (E2E, poste de développement, puce liée affichée) : à 853 px, puce coupée de
  42 px et chiffres sur 34 px (normal), coupée de 78 px et chiffres à 0 (projection) ; à 911 px,
  28 px et 78 px (normal), 61 px et 41 px (projection). La place qui reste à céder (puce et
  chiffres) est la marge pour les polices de Windows : de l'ordre de 90 px en projection à
  853 px, davantage en mode normal. Avant le palier : « Réinitialiser » finissait à 996 (projection)
  et 1 001 px (normal) pour une barre à 845, défilement horizontal de 143 et 148 px, panneau
  « Fenêtre » coupé à droite. Le contrôle E2E ajouté (dans `s_linked_view`, après les quatre
  largeurs de chaque mode, projection puis normal) vérifie `_top_bar_problems(r, None)`,
  « Réinitialiser » dans la fenêtre, `scrollWidth − clientWidth` ≤ 1 et le panneau « Fenêtre »
  ouvert entier (gauche, droite, bas), puce « · lié » affichée ; 1 024 × 700 inchangé.
- **Point 2.** IAM p1 et p2 : « Cherche avec l'outil …, puis réponds en 5 lignes au plus :
  d'abord deux liens Microsoft Learn tirés du résultat, puis l'explication. » (« deux liens
  Microsoft Learn » gardé pour le test existant). Souveraineté p1 : la phrase de la spec ajoutée
  après « sans répondre de tête ». SOC p2 : « … dis-le et propose de transmettre la vérification à
  un analyste SOC habilité. » (ni « confidentiel » ni nom de fichier ; « fichiers disponibles »
  gardé : déclencheurs du faux fournisseur intacts). `fits` en décompte exact (2B) : réussi (aperçus
  sans le prompt : IAM 1 062, Souveraineté 677, SOC 345 sur 3 584).
- **Point 3.** Les deux consignes suivent le même fil, avec des phrases communes que le test
  cherche : « Ce qu'on observe » (arrêt après `load_tool_doc`, « répond de tête », parfois
  « j'ai cherché » alors qu'Orchestration ne montre « ni appel de l'outil ni requête
  sortante » ; Souveraineté ajoute l'appel sans documentation, refusé par le harnais, et les
  jeux inventés), « Pourquoi : un petit modèle enchaîne mal deux appels et prend la
  documentation pour la réponse », « C'est la démonstration » puis le geste « Forcer l'appel »
  inchangé, conclu par « le harnais garantit l'appel que le modèle ne fait pas ». Ordre testé :
  observation, pourquoi, démonstration, bouton. Libellés, préréglages et ordre des secours de
  Souveraineté (datagouv, « Vider la conversation », mslearn) inchangés.
- **Point 4.** `static/favicon.svg` : carré arrondi `#33257A` (le violet encre de la barre en
  thème sombre ; en clair, la barre est presque noire) et un « W » blanc tracé (aucune police).
  `<link rel="icon" href="/static/favicon.svg" type="image/svg+xml" />` sous le `<title>` des
  quatre pages ; route `/favicon.ico` (hors schéma OpenAPI) qui sert le même fichier en
  `image/svg+xml`. Le fichier SVG est hors du contrôle des couleurs de `test_web_tokens` (qui ne
  lit que `.css`, `.js`, `.html`).

### À vérifier sur PC (2B, fenêtre 4 096)

| Point | Geste | Attendu | Critère |
|---|---|---|---|
| 1 | Chromium et Edge, 853 × 433 et 911 × 512 émulés, normal puis projection, après un tour (nœud Calculatrice, « — » de Contexte LLM) | barre sur une ligne, « Réinitialiser » entier, pas de défilement horizontal, panneau « Fenêtre » entier, « Aa » sur le bouton de projection | `scrollWidth − clientWidth` ≤ 1 ; « Réinitialiser » dans la barre |
| 1 | Vrai zoom d'Edge, 1 280 × 650 à 150 % puis 125 % | idem à 150 % ; à 125 %, légende visible et non recouverte | aucune commande coupée ; légende lisible |
| 1 | 1 280, 1 366, 1 440, 1 600 px, normal et projection | puce « · lié » entière (contrôle du lot K) | inchangé |
| 2 | « Métier IAM », p1, « Vider la conversation », p2, sans secours | deux liens learn.microsoft.com en tête, 5 lignes environ | tour `completed` ; deux liens par réponse |
| 2 | « Métier Souveraineté », p1 sans secours, puis avec le secours « cybersécurité » | trois jeux au plus, lien data.gouv.fr en premier | tour `completed` ; liens présents |
| 2 | « Métier SOC », p1 puis p2 (secours si besoin) | `h1 block`, escalade vers un analyste SOC habilité | « analyste » dans la réponse, pas de « Démonstrateur » |
| 3 | Consignes « Lazy loading » et « Métier Souveraineté » face au 2B | elles décrivent ce qu'on voit | avis d'Anaël |
| 4 | Edge, profil neuf, `/`, `/diagnostic`, `/models`, `/llm` | icône dans l'onglet, aucun 404 | console sans `favicon.ico` |

Prompt de recette : `_bmad-output/implementation-artifacts/prompt-recette-lot-k-suite-2026-09-29.md`.

### Vérification faite ici

Windows 11, polices de Windows, dossier de données temporaire (tests et E2E). Sur la tête
`e103b5e` : `uv run ruff check .` et `uv run ruff format --check .` propres. `uv run pytest -q` :
1 251 réussis, 3 sautés, 3 en échec dans les tests du cycle de vie du serveur MCP local
(`test_mcp.py` : délai de connexion de 30 s dépassé, processus local pas encore arrêté ;
`test_forced.py::test_a_documentation_no_longer_loadable_is_dropped[full]`, même attente),
suite lente (19 min 38 contre 9 d'habitude, poste chargé) ; relancés seuls
(`test_forced.py`, `test_mcp.py`, `test_mcp_lazy.py`) : 65 réussis. Aucun de ces tests ne lit
les fichiers du lot. `fits` en décompte exact (`WAVESTACK_TEST_GGUF` = le 2B du poste) :
réussi. E2E complet (`PYTHONUTF8=1`, sortie redirigée dans le dossier temporaire) :
658 vérifications réussies, 0 en échec ; 5 `harness_error` voulus ; console : 2 `ERR_FAILED`
et 1 `ERR_CONNECTION_RESET` (réseau coupé du parcours), aucune erreur `favicon.ico` ; captures
restaurées.

« Échoue avant » : point 1, E2E `--only linked_view` sur la CSS de `1eae76c` : 4 échecs
(« Réinitialiser » hors de la barre, 85 à 148 px de défilement horizontal, panneau « Fenêtre »
coupé à 853 px), puis 0 avec le palier ; point 2, `test_small_model_…` sur l'ancien
`scenarios.yaml` : échec (« 5 lignes au plus » absent d'IAM p1) ; point 3, même test sur les
anciennes consignes : échec ; point 4, `test_favicon_is_served_and_declared_on_every_page` sans
la route ni les liens : échec (404).

### Suites de la revue et vérification finale (tête `dc4b911`)

- `a5b22c4` : les huit correctifs de la revue (voir le Review Triage Log). E2E : légende visible
  exigée à 1 024 et 1 005 px, 840 × 433 ajouté, « Aa » exigé sous 1 000 px et absent de 1 280 à
  1 600 px ; min-width de la jauge en état « contexte dépassé » sous 1 000 px ; consigne Lazy :
  « aucun appel de local__define_term » (plus de « requête sortante », serveur local) ; SOC p2
  « en 3 lignes au plus » ; docstring du favicon ; étape Lazy loading ajoutée au prompt de
  recette.
- `dc4b911` : le contrôle à 1 005 px échouait. Dans la bande de 1 000 à 1 008 px (le vrai zoom
  125 % d'une fenêtre de 1 280 px), « Réinitialiser » dépassait de 4 à 9 px. Correction : gaps
  `spacing-1` et padding `spacing-2` dès le palier de 1 100 px, au lieu de 1 000 px ; la légende
  reste visible. `linked_view` : 47 vérifications sur 47.
- Vérification finale : ruff et format propres. `uv run pytest -q` complet : 1 253 réussis,
  3 sautés, 1 échec, `test_program.py`. Cet échec vient d'une course : les consignes et le test
  ont changé pendant la suite. Relancés seuls sur la tête, `test_program.py`, `test_web_app.py`
  et `test_e2e_fake_openai.py` donnent 52 réussis. Les tests MCP qui dépassaient leur délai à la
  première passe réussissent. E2E complet (`PYTHONUTF8=1`) : 661 vérifications réussies, 0 en
  échec, 5 `harness_error` voulus. Console : 5 erreurs réseau du parcours hors ligne, aucune sur
  `favicon.ico`. Captures restaurées.

## Spec Change Log

## Review Triage Log

Revue du 2026-09-29, passe 1 (Blind Hunter, Edge Case Hunter, Verification Gap).

| # | Source | Constat | Verdict | Preuve | Suite |
|---|---|---|---|---|---|
| 1 | VG, BH | À 1 024 × 700, une légende masquée passe le contrôle (`#gauge-legend` imbriqué, hors de `_top_bar_problems` ; `display: none` donne un recouvrement négatif) | medium | écart déposé ; la matrice veut la légende visible à 1 024 | patch |
| 2 | VG, BH | Rien ne vérifie le texte visible du bouton de projection (« Aa » sous 1 000 px, absent au-dessus) | medium | écart déposé ; un bouton vide garde sa largeur (padding) | patch |
| 3 | BH | Consigne Lazy : « ni requête sortante » n'a pas de sens pour le serveur local (bouclage jamais tracé en `outbound_request`, AD-15) | medium | recette t4 : appel forcé « aucune requête sortante (serveur local) » | patch |
| 4 | ECH | État « contexte dépassé » sous 1 000 px : le padding des chiffres (2 × `spacing-2`) dépasse le minimum de la jauge, ≈ 16 px sur « Fenêtre ▾ » | medium | `box-sizing` : largeur utilisée ≥ padding même avec `min-width: 0` ; la jauge est à son minimum sous 1 000 px | patch |
| 5 | BH | Vrai zoom : une fenêtre de 1 280 px à 150 % donne un peu moins de 853 px CSS (cadre), à 125 % ≈ 1 010 px (bande 1 000-1 023 non testée) | medium | largeur intérieure < largeur de la fenêtre | patch (840 et 1 005 px ajoutés à l'E2E) |
| 6 | BH, ECH | SOC p2 seul prompt repris sans borne de longueur | low | correction directe, cohérente avec SOC p1 | patch |
| 7 | BH | Prompt de recette, étape 7 : juge un prompt 1 de Lazy loading qu'aucune étape ne lance | low | texte de l'étape 7 | patch |
| 8 | BH | Docstring de `/favicon.ico` : « Edge la demande quoi que déclare la page » non établi | low | Chromium ne la demande qu'à défaut d'icône déclarée | patch |
| 9 | BH | K3 laisse SOC de côté | false | l'intention ne nomme que Lazy loading et Souveraineté ; la consigne SOC décrit déjà le secours | rejeté |
| 10 | BH | Vérification « pytest vert » contredite par les 3 échecs notés | low | correction = éditer la spec ; suite complète relancée à la fin | rejeté (notes finales) |
| 11 | BH | Chiffres « avant » incohérents (967 contre 1 001 px) | low | mesures sans puce (plan) contre avec puce (E2E) ; correction = éditer la spec | rejeté |
| 12 | BH | Design Notes périmées | low | correction = éditer la spec | rejeté |
| 13 | BH | Légende masquée : perdue pour les lecteurs d'écran | false | chaque segment porte un `aria-label` avec sa discipline et reçoit le focus (`app.js` l. 2183-2191) | rejeté |
| 14 | BH | `@media (width < 1000px)` diffère des `max-width` du fichier | low | la syntaxe d'intervalle évite le trou des largeurs fractionnaires (zoom) ; choix voulu | rejeté |
| 15 | BH, ECH | Couleur du favicon codée en dur, barre presque noire en thème clair | low | cosmétique, choix noté dans les notes du point 4 | rejeté |
| 16 | BH | Autres constats de la contre-vérification (K4 à K8) non classés | low | K4 traité par le point 2, K7 par le point 4 ; K5, K6, K8 hors intention | rejeté |
| 17 | BH | Menus de la barre (Volets, thème, modèle) non vérifiés à 853 px | low | listes natives ou ancrées à gauche, peu probable ; ajout de complexité | rejeté |
| 18 | ECH | À 853 / 911 px, la puce liée peut être à 0 px sans que l'E2E échoue | false | la matrice décrit l'état (« puce liée affichée ou non »), pas sa largeur ; sous 1 100 px la puce cède (lot K) ; largeur rapportée dans le détail | rejeté |
| 19 | ECH | `chip_cut` et `figures` calculés sans seuil | false | valeurs d'information, voulues (même raison que 18) | rejeté |
| 20 | ECH | IAM et Souveraineté p1 : liens inventés si le résultat n'en a pas deux | low | risque préexistant (« cite deux liens ») ; hors intention | rejeté |
| 21 | ECH | Souveraineté p2 sans borne | low | réponse mesurée : 320 tokens, `completed` ; l'intention ne nomme que p1 | rejeté |
| 22 | ECH | Minimums de la projection à 2,5 rem, pas 3 rem | low | écart noté dans les notes du point 1 : les remonter élargirait le scénario | rejeté |

## Design Notes

Budget du palier, mesures Chromium à 853 px : jauge 312 → 192 (−120), noms −56 (normal) ou −8
(projection), gaps 9 × 4 (−36), padding −16, « Aa » au lieu de « Projection » (≈ −40 à −50) :
« Réinitialiser » finit vers 720 px (normal) et 760 px (projection) pour une barre à 845, soit
80 à 130 px de marge pour les polices de Windows et la puce liée (rétrécissable sous 1 100 px).
Sans masquer la légende, la projection déborde encore : c'est le poste qui décide.

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- propre
- `uv run pytest -q` -- vert
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- 0 FAIL
