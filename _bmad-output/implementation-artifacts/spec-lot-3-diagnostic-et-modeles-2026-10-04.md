---
title: 'Lot 3 du plan de corrections du 2026-10-04 : page fusionnée « Diagnostic et modèles »'
type: 'feature'
created: '2026-10-04'
status: 'done'
baseline_commit: '370bb36d762c23e5f4af66168316104f5d738ecc'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/.working/key-diagnostic-modeles.html'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Diagnostic et Modèles sont deux pages sur la même source (`/api/diagnostic`) : l'une liste en lignes, l'autre en tableau, aucune ne se lit du fond de la salle, et un même modèle trouvé sous plusieurs sources apparaît plusieurs fois.

**Approach:** Une seule page `/diagnostic` (« Diagnostic et modèles ») en grille de cartes, locaux puis cloud, par éditeur, avec logos, filtres et tri de l'ancien tableau, contrôles repliables et carte dépliée au clic, conforme à DESIGN.md, EXPERIENCE.md et la maquette. La session regroupe les sources d'un même modèle local (règles 1 à 3) ; `/models` redirige vers `/diagnostic`.

## Boundaries & Constraints

**Always:**
- Spines UX font foi (composants `diagnostic-models-page`, `publisher-group`, `model-card`, `model-card-expanded`, `model-sources`, `model-logo`, `state-pill`, `checks-panel`, `models-filters`, états et microcopie). Questions 3 à 7 tranchées : un sous-groupe par éditeur ; logotypes recadrés sur leur symbole, tuile inchangée ; Flow 5 validé ; état « Erreur » rattaché au `ref` ; regroupement par les règles 1 à 3.
- Regroupement calculé par la session (`catalog.py`), jamais par la page ; règle 3 seulement si les cinq champs sont présents des deux côtés ; jamais local + cloud ; quantifications différentes = cartes distinctes. Toutes les sources d'une carte rejoignent le groupe d'éditeur de sa première source, dans le payload comme dans le sélecteur (mêmes groupes).
- Le sélecteur de l'atelier garde une option par source.
- Logos : PNG de la banque-visuels copiés dans `static/logos/`, recadrés sur le symbole (Qwen, DeepSeek, Hugging Face, OpenAI), 128 px de plus grand côté. Décisions d'Anaël du 2026-10-04 : Granite prend `ibm.png` entier (watsonx n'a pas de symbole) ; Llama prend le symbole ∞ recadré dans `meta.png` (le logotype « LLaMA by Meta » n'a pas de symbole séparé) ; `SOURCES.md` (provenance, licence, diffusion de la banque, recadrage, « formation interne, à vérifier avant usage client ») ; champ `logo` optionnel dans `publishers.yaml` ; sans logo, l'initiale. Aucun chargement réseau.
- Textes nouveaux (états, titres de section, compteur à sources) en fr/en/de, mêmes clés ; textes existants repris.
- Mise à jour en direct sans perdre carte dépliée, clé en saisie ni focus.

**Never:**
- Pas de nouvelle requête serveur pour filtrer ou trier ; pas de CDN ; pas de bump de `PROBE_VERSION` (les champs GGUF viennent de `catalog.header_metadata`).
- Ne pas toucher aux autres pages, hormis le lien « Tableau des modèles… » du sélecteur (il mène à `/diagnostic`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Règle 1 | blob Ollama + modèle servi par Ollama dont `gguf_path` = ce blob | une carte, « 2 sources » | N/A |
| Règle 2 | deux fichiers : même taille à l'octet, arch, basename, size_label | une carte | N/A |
| Règle 3 | HF Q4_K_M et Ollama `quantization_level` Q4_K_M, mêmes basename/finetune/version/size_label | une carte | N/A |
| Quantif. ≠ | Q4_K_M et Q8_0 du même modèle | deux cartes | N/A |
| Champ absent | `general.version` absent d'un côté | deux cartes | prudence |
| État agrégé | une source active, une incompatible | pastille « Actif » | N/A |
| Erreur | `model_load_ended` `error` pour ce `ref` | carte « Erreur », « Choisir » proposé | cause dans la carte dépliée |
| `/models` | GET | 307 vers `/diagnostic` | N/A |
| Contrôle en avertissement | `diagnostic_check` warning | panneau ouvert d'office | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/servers.py:800-866` -- `ServedModel`, `_served_by` : garder `details.quantization_level` d'Ollama (déjà dans `/api/tags`).
- `src/wavestack/models/discovery.py:25-63,176-230` -- `ModelCandidate` : champ `quantization` (servi) ; `_server_candidates` le recopie.
- `src/wavestack/models/gguf_meta.py`, `catalog.py:326-352` -- en-tête brut déjà en cache : `general.file_type` (entier, table des ftype de llama.cpp → « Q4_K_M »), `general.finetune`, `general.version`, `general.basename`, `general.size_label`.
- `catalog.py:439-474,539-665,726-797` -- `ModelEntry` (+ `card_id`, `quantization_text`, `gguf_path`, `logo`), `local_entries`, `group_models`, `models_payload` : calculer les cartes (union-find sur règles 1→3), `groups[].cards[]` = `{id, name, size_bytes_min, size_text, source_values[]}` ; `logo` de l'éditeur ; compteur à sources.
- `catalog.py:192-220` + `content/models/publishers.yaml` -- champ `logo` (nom de fichier sous `static/logos/`).
- `src/wavestack/session/app_session.py:1916,2023-2032,8445` -- `model_load_ended` ; mémoriser en mémoire le dernier échec par `(kind, ref)`, exposé par `/api/diagnostic` (`load_errors`).
- `src/wavestack/web/app.py:386-393,600-724` -- `/models` → `RedirectResponse("/diagnostic")` ; payload.
- `src/wavestack/web/static/diagnostic.html` -- réécriture d'après la maquette ; réutiliser `patchList`, `chooseModel`, `post`, `setApiKey`, `testCloud`, `openWarning`, `openStream`, `renderSearch`, `renderCap`, `startSwitch`… (l.223-811) et la logique filtres/tri de `models.html:259-356`. Garder les ids `#checks`, `#cloud-cap`, `#cloud-warning*`, `#model-path`, `#submit-path`, `#select-model-status`, `#candidates-search`, `#candidates-progress*`, `#filter-*`, `#filters-reset`.
- `src/wavestack/web/static/models.html` -- supprimé ; `pages.css:204-411` -- règles communes, ajouter les cartes (portée `body.annex-page`).
- `src/wavestack/web/static/app.js:2860-2864` -- entrée « Tableau des modèles… » vers `/diagnostic`.
- `src/wavestack/web/static/i18n.js:112` -- inchangé (pas d'entrée `/models`).
- `content/ui.yaml:1032-1145`, `content/i18n/{en,de}/ui.yaml` -- nouvelles clés `diagnostic.states.*`, `diagnostic.sections.*`, `models.sort_by.*`, compteur à sources.
- Banque : `~/.claude/skills/synced/…/banque-visuels/logos/*.png` + `manifeste.json`.
- Tests : `tests/test_web_app.py:47-167,471,499` ; `tests/test_ui_texts.py:26-36,136-259` ; `tests/test_web_tokens.py:534,583-675` ; `tests/test_i18n.py:378` ; `tests/test_model_catalog.py`, `test_model_servers.py:202,940`, `gguf_writer.py`.
- E2E `tools/e2e/run_e2e.py` : `s_diagnostic` 353, `s_diagnostic_wait` 1936, `_themes` 3125, `ANNEX_PAGES`/`_goto_annex` 8385-8453, `s_model_switch` 8907, `_slow_probe_stopped` 8988, `s_local_server` 9078, `_models_row` 9323, `_models_sort_and_filters` 9405, `_models_window_then_network` 9533, `_diagnostic_search_shown` 9561, `s_model_catalog` 9634, `_models_page_language` 9851, `s_relaunch` 10232, `_gemini_costs` 10485.

## Tasks & Acceptance

**Execution:**
- [x] `servers.py`, `discovery.py` -- quantification Ollama -- règle 3.
- [x] `catalog.py` -- ftype → texte, cartes (règles 1-3), `logo`, publisher aligné, `cards[]` -- regroupement côté session.
- [x] `app_session.py`, `app.py` -- `load_errors` ; redirection `/models`.
- [x] `static/logos/*.png`, `static/logos/SOURCES.md`, `publishers.yaml` -- logos recadrés (script reproductible dans `scripts/`).
- [x] `diagnostic.html`, `pages.css`, suppression de `models.html`, `app.js` -- la page.
- [x] `content/ui.yaml` + en/de -- clés nouvelles.
- [x] Tests pytest : regroupement (matrice), ftype, quantification Ollama, redirection, logos présents et référencés, pages ; E2E : scénarios ci-dessus portés sur les cartes.

**Acceptance Criteria:**
- Given le parcours E2E, when `diagnostic`, `local_server`, `model_catalog`, `model_switch`, `themes`, `annex_language` sont joués, then ils passent sur la page fusionnée.
- Given 1280 px puis 1440 px, when la page s'affiche, then 3 puis 4-5 colonnes ; projection 2 ; < 640 px 1.
- Given le thème sombre, when la page s'affiche, then les logos restent sur tuile blanche et les contrastes passent.

## Implementation Notes

- Grille : `minmax(min(310px, 100%), 1fr)` au lieu de 250 px, pour tenir 3 colonnes à 1280 px (critère d'acceptation) ; reste « au moins 250 px ».
- Règle 2 exige aussi la même quantification (ou deux inconnues), pour respecter « quantifications différentes = cartes distinctes ».
- « Erreur » compte `error` et `restored` (modèle choisi en échec, l'ancien revenu) ; « Arrêter » (`cancelled`) et un refus de fenêtre ne comptent pas. Mémoire seulement, effacée au premier chargement réussi.
- Nom de carte : `general.name`, sinon le nom du fichier sans `.gguf` ; deux cartes de même nom prennent « · Q4_K_M ».
- Logos : `scripts/crop_logos.py` (`uv run --with pillow`, Pillow hors dépendances du projet) régénère `static/logos/` et `SOURCES.md`.
- Vérification de la matrice : ajout de `_diagnostic_card_states` (E2E, `/api/diagnostic` simulé) pour l'état agrégé, la carte « Erreur » et l'ouverture du panneau des contrôles.
- Vérifié : ruff propre ; pytest 5528 passés (hors `test_readme_is_a_short_onboarding_page`, déjà en échec sur HEAD : README de 121 lignes) ; E2E ciblé (diagnostic, diagnostic_wait, themes, model_switch, local_server, model_catalog, annex_language, relaunch) vert. Parcours complet : 8 échecs, dont 5 reproduits sur HEAD (`mcp_full`, textes français rejoués de `harness_error` en en/de) et 3 non rejoués sur HEAD (deux libellés `/models` de `backend_language`, liste corrigée depuis ; `/rag` en de).

## Review Triage Log

Passe 1 (2026-10-05), trois couches : verification-gap (VG), blind-hunter (BH), edge-case-hunter (EC).

| # | Couche | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|---|
| 1 | VG | `_note_load_outcome` : refus de fenêtre, `error`, `cancelled` sans assertion | medium | seuls `restored` puis `ok` sont testés (`test_model_switch.py:1135-1163`) | patch |
| 2 | VG | nom de repli `_stem` sans test | low | aucune assertion de nom sur un en-tête sans `general.name` | patch |
| 3 | BH | « Choisir ce fichier » ni désactivé ni bloqué pendant un chargement | medium | `chooseModel` ne teste que `busy`, `#submit-path` jamais désactivé | patch |
| 4 | BH, EC | carte cloud sans état « Erreur » | low | EXPERIENCE n'a pas d'« Erreur » cloud (états : Clé manquante, Prêt, Test…) ; conforme | rejeté |
| 5 | BH | règle 2 ignore `finetune` et `version` | low | `_same_copy` les omet ; correction directe (valeurs comparées, absentes comprises) | patch |
| 6 | BH, EC | deux cartes non regroupées peuvent garder le même nom | low | cas rare (même nom, quantification inconnue ou identique, octets différents) ; correction = logique nouvelle | rejeté |
| 7 | BH | nom de carte `general.name` ≠ nom du sélecteur | false | EXPERIENCE > `model-sources` impose `general.name`, sinon le nom du fichier | rejeté |
| 8 | BH | carte active dépliée perd la bordure encre de 3 px | medium | `.is-expanded` (l.691) suit `.is-active` (l.665) à spécificité égale ; Flow 5 étape 5 veut la bordure épaisse sur la carte dépliée | patch |
| 9 | BH | sections de carte en `h3`, comme les en-têtes de groupe | low | `cardSection` crée un `h3` ; correction directe (`h4`) | patch |
| 10 | BH | nom accessible sans « choix enregistré » ni origine | false | format imposé par EXPERIENCE > Accessibilité « {nom}, {éditeur}, {taille}, {état} » | rejeté |
| 11 | BH | « {origine} : {valeur} » et annonce en dur avec l'espace français | low | `facts()` et `announce()` ; `common.format.label_value` existe | patch |
| 12 | BH | « Clé manquante » pour un quota bas ou un hôte changé | false | EXPERIENCE : « Même traitement… avec leur propre raison » ; la raison est dans la carte | rejeté |
| 13 | BH | `logo` répété dans fr/en/de et `crop_logos.py` | low | convention du dépôt (copie complète par langue), chaque fichier testé | rejeté |
| 14 | BH | `SOURCES.md` : provenance « non renseignée », diffusion `client` vs « formation interne » | false | provenance et diffusion recopiées de la banque ; l'en-tête est la règle de l'appli (D3) | rejeté |
| 15 | BH, EC | `crop_logos.py` fragile sur entrées inattendues | low | script de développement lancé à la main sur la banque | rejeté |
| 16 | BH | DESIGN.md dit encore « Granite → watsonx » ; commentaire 250 px de `pages.css` | low | décision d'Anaël du 2026-10-04 (IBM, ∞ de Meta) non reportée ; correction directe | patch |
| 17 | BH | carte « Erreur » rouge même si une autre source marche | false | EXPERIENCE (ordre d'agrégation) et DESIGN (« inutilisable : incompatible ou en erreur ») | rejeté |
| 18 | BH | `cardStatus` jamais vidé | low | message périmé dans la carte dépliée, correction = logique nouvelle | rejeté |
| 19 | BH, EC | Échap dans le champ de clé ou un filtre replie la carte et perd la saisie | medium | le gestionnaire `keydown` ne regarde pas la cible | patch |
| 20 | EC | Arrêter, puis l'ancien modèle ne revient pas : `error` noté sur le modèle arrêté | low | `_load_cancelled` rend `error` (cas rare : l'ancien modèle échoue au retour) | rejeté |
| 21 | EC | raison vide : `errorOf` faux, carte « Disponible » | low | `sourceState` teste la valeur, pas la présence ; correction directe (`has`) | patch |
| 22 | EC | fenêtre en échec et ancien modèle en échec : pas d'« Erreur » | low | double échec rare, garde nouvelle | rejeté |
| 23 | EC | test cloud en exception : « Test en cours… » figé | low | bouton désactivé pendant `busy` ; seule une panne réseau du POST le fige, correction non triviale (ordre réponse/événement) | rejeté |
| 24 | EC | `harness_error` avant le contrôle `model` : « en cours » sans fin | low | diagnostic interrompu, rare | rejeté |
| 25 | EC | `harness_error` rejoués comptés comme échecs : panneau ouvert à chaque chargement | medium | `renderHarnessError` ignore `live` ; toute erreur de brique de la séance rouvre le panneau | patch |
| 26 | EC | contrôle cloud réémis avec un autre texte : ancien compté | low | clé `cloud:{message}` préexistante | rejeté |
| 27 | EC | clé effacée avant l'échec de l'enregistrement | low | comportement préexistant de la page | rejeté |
| 28 | EC | logo absent : image cassée | false | `test_every_logo_of_the_publishers_is_shipped` l'empêche | rejeté |
| 29 | EC | quantification ajoutée deux fois en casse différente | low | `quantization not in card.name` sensible à la casse ; correction directe | patch |
| 30 | EC | ordre `g * 10000` | false | aucun groupe n'approche 10 000 cartes | rejeté |
| 31 | EC | llama-server sans `server_url` | false | un candidat servi a toujours son URL (`_server_candidates`) | rejeté |
| 32 | EC | `/models?…` perd sa requête | false | l'ancienne page n'avait aucun paramètre | rejeté |
| 33 | EC | `legend_text` plus affichée | false | la page fusionnée n'en prévoit pas (EXPERIENCE) ; le sélecteur la garde | rejeté |
| 34 | EC | échec de `/api/diagnostic` : « Diagnostic en cours… » figé | low | même comportement que l'ancien diagnostic | rejeté |
| 35 | EC | tri ascendant seul, colonnes supprimées | false | EXPERIENCE > `models-filters` fixe les cinq tris | rejeté |

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: propre
- `uv run pytest -q` -- expected: tout vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge` -- expected: tous les scénarios OK
