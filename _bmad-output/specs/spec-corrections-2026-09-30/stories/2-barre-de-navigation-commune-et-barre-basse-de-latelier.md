---
title: "Barre de navigation commune et barre basse de l'atelier"
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_revision: 'ba09fd6b102d33f1d10a55b8eaae026e73d224b2'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/ecrans-lots-2-a-4.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred:
  - '`back_text` des contenus `llm_lab` et `rag_lab` gardé, inutilisé (deferred-work.md)'
---

<intent-contract>

## Intent

**Problem:** Chaque page a sa propre navigation : `.page-tabs` dans un ordre différent sur `/llm`, `/rag`, `/diagnostic` et `/models`, des liens `#llm-link` et `#rag-link` dans la barre de l'atelier, la langue et la projection seulement sur l'atelier. La barre haute de l'atelier porte à la fois la navigation et les contrôles du scénario, et sature à 1 600 px (CAP-2 de `SPEC.md`).

**Approach:** Une barre de navigation identique en tête des cinq pages (marque, liens des pages dans un ordre fixe, menu « Affichage ▾ »). La barre de l'atelier perd sa navigation et descend en bas de l'écran. Les titres de volets baissent d'un cran de la rampe typographique.

## Boundaries & Constraints

**Always:**
- **Barre commune** `nav.site-nav` (balisage identique dans les cinq HTML, au seul `aria-current="page"` près) : marque « WaveStack » (lien vers `/`), puis `/` Atelier, `/llm` LLM nu, `/rag` Atelier RAG, `/diagnostic` Diagnostic, `/models` Modèles, puis le menu `#display-menu` (« Affichage ▾ ») poussé à droite. Elle garde `data-i18n-aria-label="common.links.pages"` et `data-i18n-links` ; le lien `/` prend une clé nouvelle `common.links.home` (« Atelier », « Workshop », « Werkstatt ») ajoutée à `LINK_NAMES` de `i18n.js`. Le HTML garde son texte français.
- **Menu « Affichage ▾ » sur toutes les pages** : thème (`#theme-picker`, `data-theme-picker`, géré par `theme.js`) et langue (`#language-picker`, même verrou, même infobulle, même refus qu'aujourd'hui) partout ; `#projection-toggle` seulement sur l'atelier (seul `app.js` applique la projection). La logique du menu et du sélecteur de langue sort de `app.js` dans un module partagé `site-nav.js`, chargé par les cinq pages après `i18n.js` ; `app.js` l'importe au lieu de la dupliquer. Mêmes identifiants qu'aujourd'hui (`#display-menu`, `#display-menu-toggle`, `#display-menu-panel`, `#theme-picker`, `#language-picker`, `#language-picker-code`, `#projection-toggle`).
- **Atelier** : la barre `header.top-bar` (scénario, jauge, consommation, fenêtre, volets, modèle, statut, réinitialiser) passe **sous** les volets, en bas de l'écran ; elle garde sa classe et ses identifiants (nom historique conservé pour limiter la casse, noté dans DESIGN.md). Elle perd `.top-bar-title`, `#llm-link`, `#rag-link` et `#display-menu`. Ses panneaux déroulants (`.window-panel`, `.pane-menu-list`, `.top-status`) s'ouvrent vers le haut.
- `#open-link` (« Ouvrir WaveStack ») disparaît des pages Diagnostic et Modèles : le lien `/` de la barre commune le remplace. `#back-link` (« ← Atelier ») disparaît de `/llm` et `/rag` ; `llm.js` et `rag.js` cessent de l'écrire (`back_text` reste dans les contenus, inutilisé, noté en `deferred`).
- **Titres de volets** : `typography.pane-title` passe de 19 px à 18 px (24 px → 23 px en projection, rampe ×9/7), dans `tokens.css` et DESIGN.md ensemble (`test_web_tokens` les compare).
- **Tenue** : en `fr` et en `de`, à 1 280 et 1 600 px, en mode normal et en projection, aucun contrôle de la barre commune ni de la barre basse n'est tronqué ou réduit à deux lettres suivies de « … » (`_bar_fits` étendu aux deux barres). Les paliers de `app.css` qui visaient la navigation (`.screen-link*`, `.top-bar-title`, `.display-menu*` dans la barre) sont retirés ou déplacés sur `.site-nav`.
- Textes nouveaux par `ui.yaml` (`common.links.home`, et tout autre libellé) dans les trois langues ; aucun libellé en dur.
- DESIGN.md et EXPERIENCE.md décrivent la barre commune, la barre basse, le menu « Affichage » (absent d'EXPERIENCE.md aujourd'hui) et le nouvel ordre clavier (barre commune, volets, barre basse).

**Never:**
- Revenir sur le menu « Affichage ▾ » ou changer ses identifiants ; appliquer la projection aux pages annexes.
- Une dépendance JS ou un framework ; une barre générée côté serveur.
- Toucher au contenu des pages annexes sous leur barre (stories 3 et 5).

</intent-contract>

## Code Map

Chemins relatifs à `src/wavestack/web/static/` sauf mention.

- `index.html:15-93` -- `header.top-bar` actuel : `.top-bar-title` (l.16), `#llm-link`/`#rag-link` (l.62-63), `#display-menu` (l.66-91), `#reset-button` (l.92). Volets `h2.pane-title` (l.97+). Charge `theme.js`, `i18n.js` (module), `fonts.css`, `tokens.css`, `app.css`, `app.js` (l.279).
- `llm.html:16-27`, `rag.html:16-27`, `diagnostic.html:69-81`, `models.html:113-125` -- `nav.page-tabs` (ordres différents, `#back-link`, `#open-link` caché, `#theme-picker` nu). `diagnostic.html` a un `<style>` en ligne (`body { max-width: 640px }`) ; `models.html:23` `main, .page-tabs { max-width: 1500px }`.
- `pages.css` -- règles `.page-tabs` seulement (l.3-57) : à remplacer par `.site-nav`. `llm.css:22-32`, `rag.css:15-25` -- `.page-tabs` et `a.llm-back`/`a.rag-back`.
- `app.css` -- `body` flex colonne (l.10-26) ; `.top-bar` (l.173-190) ; `.pane-title` (l.493-499) ; `.pane-menu-list` absolu `top: calc(100% + 4px)` (l.245) ; `.top-status` (l.3607) ; `.window-panel` (l.3887-3908, `max-height` calculé sur la barre) ; `.display-menu*` (l.4925-4993, `.display-menu-panel` l.4942) ; `.screen-link*` (l.4606-4675) ; projection `:root.projection` (l.4541-4587) ; paliers ≤1100/1300/1400/1500/1600/1700 et ≥1200 (l.3855, 4631, 4677, 4759, 4801, 4813, 4830, 4893, 4899, 4910, 4995-5093).
- `app.js` -- `fitFootprint()` l.2357, `topBarFits(bar)` l.2376 (`closest(".top-bar")`) ; `renderLanguagePicker()` l.3243, `changeLanguage()` l.3263 ; projection l.7121-7153 ; `closePaneMenu()` l.7157, `setDisplayMenu()` l.7166 ; `boot()` l.7180 (toggles l.7205-7220, pickers l.7247-7248, Échap l.7298-7323).
- `i18n.js` -- `t()` l.70, `ready` l.132, `applyTexts()` l.116, `LINK_NAMES`/`LINK_IDS` l.111-112 (`/` non associé).
- `theme.js` -- déjà indépendant de la page (tous les `select[data-theme-picker]`).
- `llm.js:157-158`, `rag.js:697` -- écrivent `#back-link` avec `back_text`.
- `content/ui.yaml:74-88` (`common.links`, `common.theme`), `:768` (`main.projection`), `:849-851` (`main.display`) ; `content/i18n/{en,de}/ui.yaml` mêmes clés ~9 lignes plus haut.
- `tests/test_web_app.py:49-79` -- balisage littéral des onglets et ordre `llm-link` < `rag-link` < `theme-picker` : à réécrire pour `.site-nav`.
- `tests/test_ui_texts.py:190-204` -- premier `<nav>` des pages annexes : liens exactement {diagnostic, models, llm, rag}, `open-link` : à réécrire (5 liens + marque, toutes les pages dont index).
- `tests/test_web_tokens.py:100-118, 578-644` -- miroir DESIGN.md ↔ `tokens.css`, `theme.js` en premier, `select[data-theme-picker]` par page, rampe de projection.
- `tests/test_i18n.py:366-369` -- `#language-picker` dans index.html (à étendre aux cinq pages).
- `tools/e2e/run_e2e.py` -- `_fully_visible` l.1154 ; `_bar_fits` l.1590 (exige `#reset-button` et `#display-menu` dans `.top-bar`) et ses appelants l.1811, 1822, 5025, 6814, 6876, 7134, 7515 ; `_top_bar_problems` l.1620 ; `_window_panel_outside` l.1603 ; menu l.1669-1731 ; `s_disciplines` l.1196-1247 ; `_themes` l.1790-1999 ; `s_linked_view` l.2405-2509 ; `s_model_catalog` l.6267-6350 ; `_llm_screen` l.7124-7152 ; `_rag_lab` l.7504-7551 ; `s_diagnostic` l.359 (`#open-link`) ; `_readable_bar` l.5025, captures `ui-language-de-*` l.5042, 5129.
- `_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md` -- frontmatter `typography.pane-title` l.137, `spacing.top-bar-height` l.201, `components.top-bar` l.237, `theme-picker` l.302 ; corps : projection l.878-889, mise en page l.894, « Barre haute » l.946, « Onglets de page » l.970, écrans LLM/RAG l.1016-1024.
- `.../EXPERIENCE.md` -- surfaces l.25-35, schéma à 5 volets l.48-72, composants l.117-146 (`page-tabs` l.133), ordre clavier l.245, résolutions l.255.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/web/static/site-nav.js` (nouveau) -- menu « Affichage » (ouverture, fermeture au clic extérieur et à Échap, retour du focus), sélecteur de langue (rendu, verrou, `POST /api/intentions/language`, rechargement, refus affiché) sortis de `app.js` -- une seule implémentation pour cinq pages.
- `index.html`, `llm.html`, `rag.html`, `diagnostic.html`, `models.html` -- `nav.site-nav` identique en tête ; atelier : `header.top-bar` déplacé après les volets, sans titre, liens ni menu ; suppression de `#back-link`, `#open-link`, `.page-tabs`.
- `pages.css` (chargé aussi par index.html), `app.css`, `llm.css`, `rag.css`, `tokens.css` -- styles `.site-nav` (tokens seulement), barre basse et panneaux vers le haut, paliers nettoyés, `pane-title` 18/23.
- `app.js`, `llm.js`, `rag.js`, `diagnostic.html` et `models.html` (scripts en ligne), `i18n.js` -- import de `site-nav.js`, `topBarFits` sur la barre basse, plus d'écriture de `#back-link` ni `#open-link`, `LINK_NAMES["/"]`.
- `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- `common.links.home` et libellés nouveaux.
- `tests/test_web_app.py`, `tests/test_ui_texts.py`, `tests/test_web_tokens.py`, `tests/test_i18n.py` -- barre identique sur les cinq pages (au `aria-current` près), ordre des liens, un seul `aria-current` et le bon, `#language-picker` et `#display-menu` sur chaque page, `#projection-toggle` sur l'atelier seulement, rampe mise à jour.
- `tools/e2e/run_e2e.py` -- `_bar_fits` sur `.site-nav` et `.top-bar` ; navigation par la barre commune au lieu de `#llm-link`, `#rag-link`, `#open-link`, `.page-tabs` ; vérification que la barre de l'atelier est sous les volets (son haut ≥ bas du dernier volet) et que ses panneaux s'ouvrent dans la fenêtre ; tenue en `de` à 1 280 et 1 600 px, normal et projection, sur les deux barres.
- DESIGN.md, EXPERIENCE.md -- composants et schéma mis à jour ; entrée « Barre haute saturée à 1 600 px » de `_bmad-output/implementation-artifacts/deferred-work.md` fermée avec la preuve E2E.

**Acceptance Criteria:**
- Given n'importe laquelle des cinq pages, when elle s'ouvre, then la même barre commune est en tête, la page courante y est marquée, et ses liens mènent aux quatre autres pages.
- Given l'atelier en `de` à 1 280 px en projection, when la page est chargée, then la barre commune et la barre basse tiennent sans contrôle tronqué, et la barre basse est sous les volets.
- Given la page `/models` avec une conversation vide, when l'utilisateur choisit `en` dans « Affichage », then la page se recharge en anglais.
- Given l'atelier, when le panneau « Fenêtre » ou le menu « Volets » s'ouvre, then il s'affiche en entier dans la fenêtre, au-dessus de la barre basse.

## Design Notes

- Barre commune en HTML statique dupliqué plutôt que générée en JS : la page reste navigable si le JS échoue, et un test garantit l'identité des cinq copies.
- Classe `.top-bar` conservée pour la barre basse : la renommer toucherait des centaines de sélecteurs CSS et E2E sans gain pour l'utilisateur.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `node --check` sur chaque fichier JS touché -- expected: aucune erreur de syntaxe.
- `uv run pytest -q tests/test_web_app.py tests/test_ui_texts.py tests/test_web_tokens.py tests/test_i18n.py` -- expected: tout passe.
- E2E (orchestrateur) : `--only themes disciplines linked_view`, `--only language ui_language annex_language`, `--only model_catalog llm_screen rag_lab` -- expected: 0 échec.

## Spec Change Log

## Review Triage Log

### 2026-10-01 — Review pass
- verdicts: 34 findings — high 0, medium 3, low 31, false 0, maybe-false 0 (dont 8 constats descriptifs de l'audit d'intention)
- findings:
  - `[low]` `[patch]` (verification-gap) refus de changement de langue (`#display-menu-alert`) jamais testé — étape E2E avec `page.route` en 409.
  - `[low]` `[patch]` (verification-gap) verrou de langue des pages annexes testé seulement déverrouillé — étape E2E conversation non vide, puis vidée.
  - `[low]` `[patch]` (verification-gap) fermeture d'« Affichage » par Échap et clic extérieur non testée — étape E2E.
  - `[low]` `[patch]` (verification-gap, autre) message de refus jamais effacé — effacé quand le sélecteur redevient disponible et à la fermeture.
  - `[low]` `[reject]` (intent-alignment) tenue en projection seulement sur l'atelier — la projection n'existe que sur l'atelier (story).
  - `[medium]` `[patch]` (intent-alignment) barre commune en `de` à 1 280 px non vérifiée sur les pages annexes — `_site_nav_problems` en `de` à 1 280 et 1 600 px sur les quatre pages annexes.
  - `[low]` `[reject]` (intent-alignment) marque en mot et non en image — lecture défendable ; aucune image de logo n'existe.
  - `[low]` `[reject]` (intent-alignment) liens cliqués seulement pour trois pages — `href` vérifiés sur les cinq pages ; coût E2E sans gain.
  - `[low]` `[reject]` (intent-alignment) « Ouvrir WaveStack » remplacé par un lien toujours visible — prescrit par la story.
  - `[low]` `[reject]` (intent-alignment) changement de langue possible depuis les pages annexes — prescrit par la story (menu partout).
  - `[low]` `[reject]` (intent-alignment) `back_text` orphelin — noté en `deferred`.
  - `[low]` `[reject]` (intent-alignment) preuve E2E seulement en prose — l'orchestrateur rejoue les tranches.
  - `[medium]` `[patch]` (edge-case + blind) « Fenêtre » peut passer sous la barre commune (`max-height` sans la barre commune, z-index 30 < 40) — hauteur de la barre commune soustraite ; E2E vérifie le recouvrement.
  - `[low]` `[patch]` (edge-case) Échap sur `/llm` ferme le menu et efface aussi le candidat épinglé — `defaultPrevented` respecté.
  - `[low]` `[patch]` (edge-case) état en cache non rafraîchi après un refus sur une page annexe — `refreshState()` après le refus.
  - `[low]` `[patch]` (edge-case) refus périmé affiché — même correctif que ci-dessus.
  - `[low]` `[reject]` (edge-case) réponses de `/api/state` dans le désordre — ouverture rapide répétée du menu, cas improbable ; un jeton ajoute de l'état.
  - `[low]` `[patch]` (edge-case) sélecteur désactivé sur `/diagnostic` avant tout `session_state` — état absent traité comme repos ; le serveur tranche.
  - `[low]` `[reject]` (edge-case + blind) langue changée dans un autre onglet non suivie par les pages annexes — cas rare ; un rechargement suffit.
  - `[low]` `[reject]` (edge-case + blind) barre commune sans repli au zoom 150-200 % — hors des largeurs de référence de la démo.
  - `[low]` `[patch]` (edge-case) `_bar_under_panes` passe sans volet visible — échec explicite.
  - `[low]` `[reject]` (edge-case) `s_diagnostic` continue si le diagnostic n'est jamais prêt — l'échec suivant reste visible.
  - `[low]` `[reject]` (edge-case, suppression) plus d'indice « prêt » sur le diagnostic — prescrit par la story ; la liste des contrôles le dit.
  - `[medium]` `[patch]` (edge-case, affirmation) panneau dit « entier » alors que la barre commune le recouvre — même correctif que « Fenêtre ».
  - `[low]` `[reject]` (edge-case, affirmation) `test_web_tokens` non modifié pour 18/23 — le test miroir DESIGN.md ↔ `tokens.css` couvre la valeur, modifiée des deux côtés.
  - `[low]` `[reject]` (edge-case, affirmation) `topBarFits` ne mesure pas la barre commune — la barre commune n'a pas d'éléments à réduire dynamiquement.
  - `[low]` `[patch]` (blind) test « await ready » satisfait par `site-nav.js` pour toutes les pages — vérifié sur le script propre de la page.
  - `[low]` `[patch]` (blind) styles en ligne de `/diagnostic` décalent « Affichage » — règles restreintes hors de `.site-nav`.
  - `[low]` `[reject]` (blind) barre basse exposée comme `banner` et ordre clavier — ordre prescrit par la story ; landmark à revoir (noté au rapport).
  - `[low]` `[reject]` (blind) deux liens vers `/` (marque et Atelier) — prescrit (marque et liens).
  - `[low]` `[reject]` (blind) `aria-haspopup="true"` du menu — préexistant (Langues 2).
  - `[low]` `[patch]` (blind) DESIGN.md `site-nav.min-height` différent du CSS — aligné.
  - `[low]` `[reject]` (blind) ~48 px de hauteur perdus par les volets — compromis de la décision ; capture de projection comparée, pas de régression visible.
  - `[low]` `[patch]` (blind) libellés et commentaires E2E et docs périmés (« barre haute », « Ouvrir WaveStack ») — reformulés.

## Auto Run Result

- Changement : barre commune `nav.site-nav` identique en tête des cinq pages (marque, Atelier, LLM nu, Atelier RAG, Diagnostic, Modèles, menu « Affichage ▾ » avec thème et langue partout, projection sur l'atelier) ; module partagé `site-nav.js` (menu, sélecteur de langue, refus) ; barre de l'atelier déplacée sous les volets, panneaux ouverts vers le haut ; `.page-tabs`, `#llm-link`, `#rag-link`, `#back-link`, `#open-link`, `.top-bar-title` retirés ; `pane-title` 19 → 18 px (24 → 23 en projection).
- Fichiers : `static/site-nav.js` (nouveau), les cinq HTML, `pages.css`, `app.css`, `llm.css`, `rag.css`, `tokens.css`, `app.js`, `llm.js`, `rag.js`, `i18n.js`, `session/diagnostic.py` (docstrings), `content/ui.yaml` et surcouches (`common.links.home`, `common.display`), `tests/test_web_app.py`, `tests/test_ui_texts.py`, `tests/test_i18n.py`, `tools/e2e/run_e2e.py`, DESIGN.md, EXPERIENCE.md, `deferred-work.md`.
- Revue : 18 correctifs appliqués (3 medium, 15 low, dont des doublons regroupés), 0 reporté hors `back_text`, 16 rejetés (raisons dans le journal).
- Revue de suivi recommandée : non. Les trois medium relèvent de deux causes : le panneau recouvert par la barre commune, et la tenue non vérifiée sur les pages annexes. Toutes deux sont corrigées et vérifiées par l'E2E.
- Vérification : `ruff`, `node --check` OK ; 4 fichiers de tests : 206 passés ; E2E du sous-agent : `themes disciplines linked_view` 115/115, `language ui_language annex_language` 56/56, `model_catalog llm_screen` 64/64, `rag rag_rerank rag_lab` 87/87, puis `model_catalog annex_language` 61/61 après correctifs. E2E complet rejoué par l'orchestrateur après le commit.
- Risques résiduels : barre basse encore balisée `<header>` (landmark « banner ») ; ~48 px de hauteur en moins pour les volets à 1 280 × 650 ; sur `/diagnostic`, la barre est 8 px plus bas que sur les autres pages (marge de la page, story 3).
