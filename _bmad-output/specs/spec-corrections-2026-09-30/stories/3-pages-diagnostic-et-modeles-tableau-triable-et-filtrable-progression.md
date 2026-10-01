---
title: 'Pages Diagnostic et Modèles : tableau triable et filtrable, progression'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_revision: 'ea027d2637d93d390d4f0423d97145941195b67d'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/ecrans-lots-2-a-4.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred:
  - summary: >-
      La chaîne réelle de la recherche au lancement (événements émis par une vraie sonde, flux SSE, page, puis bascule en direct vers la liste au contrôle model) n'est jouée par aucun E2E.
    evidence: |-
      _diagnostic_search_shown simule /api/diagnostic et /api/diagnostic/stream par page.route, puis recharge la page ; la pile E2E n'a pas de sonde lente au lancement (SLOW_PROBE est un changement à chaud qui ne sonde pas). Côté serveur, test_diagnostic_says_searching_and_progress_until_the_model_check couvre searching et progress.
    location: >-
      tools/e2e/run_e2e.py (_diagnostic_search_shown)
    severity: medium
  - summary: >-
      Aucun contrôle automatique ne vérifie que la bande de filtres de /models et les cartes cloud de /diagnostic tiennent en de à 1 280 et 1 600 px, en normal et en projection.
    evidence: |-
      L'E2E ne contrôle que le tri et le filtre en de à 1 280 px et prend des captures ; à vérifier pendant la recette de la phase 3 (Edge, trois largeurs, de).
    location: >-
      src/wavestack/web/static/models.html, diagnostic.html
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Sur `/models`, le tableau des modèles (une trentaine de lignes) ne se trie ni ne se filtre. Sur `/diagnostic`, pendant la recherche et le sondage des modèles (jusqu'à 1 min 30 avec 30 modèles Ollama), la liste des candidats affiche « Aucun candidat trouvé. », confondu avec un vrai « aucun ». La page Diagnostic garde un style ancien (tailles en rem, 640 px de large, boutons nus) (CAP-3 de `SPEC.md`).

**Approach:** Tri par colonne et filtres côté page sur les données déjà servies ; un événement de progression émis pendant la découverte et un drapeau « recherche en cours » dans `/api/diagnostic` ; refonte des deux pages sur les tokens.

## Boundaries & Constraints

**Always:**
- **Tri** (`/models`) : chaque en-tête triable porte un `<button>` dans son `<th scope="col">` ; clic ou Entrée/Espace alterne croissant/décroissant ; l'en-tête actif porte `aria-sort="ascending|descending"`, les autres rien. Le tri se fait **à l'intérieur de chaque groupe** (un `<tbody>` par groupe hébergement/éditeur, comme aujourd'hui et comme DESIGN.md le demande). Colonnes triables : modèle (nom), éditeur, taille (`size_bytes`, puis `params_b`), hébergement, fenêtre (`window`), outils, raisonnement, état ; valeurs inconnues toujours en dernier. Le prix n'est pas triable (aucune valeur numérique servie). Comparaison des textes par `Intl.Collator(locale())`.
- **Filtres** au-dessus du tableau : hébergement (tous, local, réseau), éditeur (liste tirée des données), outils (tous, oui, non ou inconnu), raisonnement (tous, oui = `always|toggle`, non = `never`, inconnu), texte libre (nom, éditeur, sur la valeur affichée, sans casse ni accents). Ils se combinent. Un groupe sans ligne visible est masqué. Le compteur dit « {n} modèles sur {total} » (pluriel `.one`/`.other`) ; zéro résultat : message dédié et bouton « Réinitialiser les filtres ».
- Tri et filtres ne rechargent rien ; ils ne touchent pas au serveur ; aucune bibliothèque.
- **Progression** (`/diagnostic`) : nouvel événement `diagnostic_progress{done, total}` (nouveau `kind`, pas une nouvelle valeur de `check`) émis par `DiagnosticSession._discover` : une fois avec `done = 0` après l'énumération et le passage sur le cache (`total` = candidats qui demandent vraiment une sonde), puis après chaque sonde. Payload validé par le catalogue d'événements ; libellé dans `main.log.kinds` et résumé dans `eventSummary` d'`app.js`.
- `/api/diagnostic` gagne `searching: bool` (vrai tant que `session.last_result` est `None`, c'est-à-dire avant le premier résultat du contrôle `model`) et `progress: {done, total} | null` (dernier `diagnostic_progress` du journal pendant la recherche).
- La page affiche, tant que `searching` est vrai : « Recherche et test des modèles en cours… » et, dès qu'un `total > 0` est connu, « {done} modèles testés sur {total} » avec une barre de progression (`<progress>` ou équivalent accessible) ; mise à jour en direct par le flux `/api/diagnostic/stream` (écouteur ajouté). « Aucun candidat trouvé. » n'apparaît que lorsque `searching` est faux et la liste vide.
- **Refonte** : styles des deux pages sur les tokens seulement (aucune couleur ni taille en dur ; `test_web_tokens`) ; styles communs (tableau, badges, boutons primaire et secondaire de DESIGN.md, champs) dans `pages.css` ; Diagnostic : hiérarchie (titre, contrôles, candidats, cloud), boutons « Choisir » primaires et « Tester »/« Enregistrer la clé » secondaires, bloc cloud en cartes lisibles (fournisseur et modèle en titre, hébergement et entraînement, prix, clé, actions). Tout tient en `de` à 1 280 et 1 600 px, en normal et en projection.
- Textes nouveaux dans `ui.yaml` (`models.filters.*`, `models.sort.*`, `models.count_filtered.*`, `diagnostic.searching`, `diagnostic.progress.*`, `main.log.kinds.diagnostic_progress`…) en `fr`, `en`, `de`.
- DESIGN.md (`model-table`, `diagnostic-row`, boutons) et EXPERIENCE.md (`models-page`, états du diagnostic l.182) mis à jour ; contrat d'événements d'ARCHITECTURE-SPINE (liste des `kind`) complété.

**Never:**
- Changer l'ordre ou les groupes servis par `catalog.models_payload`, ni l'ensemble des `check` de `diagnostic_check` (`test_cli_diagnostic.py:336`).
- Émettre un événement par candidat non sondé, ou plus d'un événement par sonde.
- Toucher à la barre commune (story 2) ou au comportement des boutons (endpoints inchangés).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Tri numérique | clic « Taille » deux fois | ordre décroissant par `size_bytes` dans chaque groupe, `aria-sort="descending"` | inconnus en dernier |
| Filtres combinés | réseau + texte « gem » | seules les lignes réseau dont le nom ou l'éditeur contient « gem » ; compteur « 2 modèles sur N » | — |
| Aucun résultat | texte « zzz » | message dédié et bouton de réinitialisation ; groupes masqués | — |
| Recherche en cours | `last_result` nul, 0 progression | « Recherche et test des modèles en cours… », pas « Aucun candidat » | — |
| Progression | `diagnostic_progress{3, 30}` en direct | « 3 modèles testés sur 30 » et barre à 10 % | — |
| Tout en cache | aucun candidat à sonder | un seul `diagnostic_progress{0, 0}` ; la page garde le message sans compteur | — |
| Fin | contrôle `model` rendu, liste vide | « Aucun candidat trouvé. » | — |

</intent-contract>

## Code Map

- `src/wavestack/web/static/models.html:126-148` -- `<main>` : `h1`, `#publishers-error`, `#models-legend`, `#models-status`, `table#models-table.model-table` (thead statique de 9 `th scope=col`, un `tbody` par groupe créé en JS), `p.models-note`. `<style>` en ligne l.13-110 (déjà sur tokens). Script l.150-248 : `COLUMN_ORDER` l.157, `row()` l.178-206 (`tr.dataset.value`, cellules `*_text`), `load()` l.208 (fetch unique de `/api/diagnostic`), compteur `models.count`.
- `src/wavestack/models/catalog.py:349-384` -- `ModelEntry` : `hosting`, `publisher_id`, `params_b`, `size_bytes`, `window`, `tools`, `reasoning` (`never|always|toggle|unknown`, `models/capabilities.py:108`), `usable`, `label_text`, `publisher_text`… ; `sort_key` l.639, `group_models` l.651, `models_payload` l.677. Ajouter aux lignes du tableau des `data-*` bruts (`data-size`, `data-window`, `data-hosting`, `data-publisher`, `data-tools`, `data-reasoning`) côté page.
- `src/wavestack/web/static/diagnostic.html` -- `<style>` en ligne l.13-66 (rem, 640 px) ; corps l.82-104 (`ul#checks`, `ul#candidates`, `ul#cloud-models`, `dialog#cloud-warning`, `div#select-model`) ; module l.106-616 : `patchList` l.177 (préserve focus et clés saisies), `renderCheck` l.188, `renderCandidates` l.214 (liste vide → `diagnostic.no_candidate`), `servedRow` l.272, `renderCloud` l.341, `fetchDiagnostic`/`loadDiagnostic` l.510-545 (`historyUpTo`), `openStream` l.558 (`EventSource("/api/diagnostic/stream")`, écouteurs par `kind`).
- `src/wavestack/web/app.py:471` -- `diagnostic_state()` : ajouter `searching` et `progress` ; `_sse_stream` l.894.
- `src/wavestack/session/diagnostic.py:418-448` -- `_discover` (énumération `discovery.discover`, boucle, cache de sondes, `_probe_candidate` l.444) ; `_emit_check` l.211 (modèle d'émission) ; appelé aussi par `_select_model_locked` l.579 et `_select_server_locked` l.663 ; `last_result` posé à la fin de `_check_model_locked` l.469.
- `src/wavestack/trace/catalog.py` -- `PAYLOAD_MODELS` (~l.1250), `DiagnosticCheckPayload` l.21 ; précédent de progression `RagRerankProgressPayload{done,total}` l.954.
- `src/wavestack/web/static/app.js:6175` -- `eventSummary` (cas `diagnostic_check` l.6299, `rag_rerank_progress` l.6277) ; `content/ui.yaml:646+` `main.log.kinds`.
- `content/ui.yaml:903-957` (`diagnostic`), `:959-985` (`models`, `count.one/other`) ; surcouches `content/i18n/{en,de}/ui.yaml`.
- `src/wavestack/web/static/pages.css` -- styles partagés des pages annexes (après la story 2 : `.site-nav`) ; boutons à reprendre de `llm.css:199-235`.
- `tests/test_ui_texts.py:134,207` -- clés `t()` des modules en ligne ; regex `<th scope="col">([^<]+)</th>` à adapter aux boutons de tri.
- `tests/test_web_tokens.py:528,577` -- pas de couleur en dur, `tokens.css` et `theme.js` d'abord.
- `tests/test_cli_diagnostic.py:336` (ensemble exact des `check`), l.117, l.136, sondes l.204-303 et l.773-858 (`_fake_probe_ok` l.386) ; `tests/test_model_catalog.py:644`.
- `tools/e2e/run_e2e.py` -- `s_diagnostic` l.335 ; `_models_row` l.6155 (lit `#models-table tr[data-value=…] td` dans l'ordre des 9 colonnes, premier texte de ligne et « why ») ; `s_model_catalog` l.6183-6345 (`th[scope=rowgroup]`, une `caption`, capture `44-modeles-tableau`) ; thèmes sombres l.1957-1975 (captures 49, 50) ; `SLOW_PROBE` l.5839+ (`tools/e2e/launch_app.py:34`) ; candidats l.5918-5945.
- DESIGN.md : `model-table` l.969, `diagnostic-row` l.664-677 et l.1014, boutons l.264-270 ; EXPERIENCE.md : `models-page` l.132, `diagnostic-row` l.174-176, états l.182-185 ; ARCHITECTURE-SPINE : liste des `kind` l.104-121, AD-21 l.572-596.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/trace/catalog.py` -- `DiagnosticProgressPayload{done: int ≥ 0, total: int ≥ 0}` enregistré sous `diagnostic_progress`.
- `src/wavestack/session/diagnostic.py` -- émission dans `_discover` (après pré-passage sur le cache, puis après chaque sonde).
- `src/wavestack/web/app.py` -- `searching`, `progress` dans `/api/diagnostic`.
- `src/wavestack/web/static/models.html` -- boutons de tri, filtres, compteur, `data-*` bruts, état vide ; styles sur tokens.
- `src/wavestack/web/static/diagnostic.html` -- état de recherche et progression en direct, refonte des styles et de la hiérarchie.
- `src/wavestack/web/static/pages.css` -- tableau, badges, boutons, champs partagés.
- `src/wavestack/web/static/app.js` -- résumé de `diagnostic_progress` dans le journal de l'atelier.
- `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- clés nouvelles.
- `tests/test_cli_diagnostic.py` -- `diagnostic_progress` : `0/N` puis une émission par sonde ; `0/0` quand tout est en cache ; `searching`/`progress` dans `/api/diagnostic` avant et après le contrôle `model`.
- `tests/test_ui_texts.py`, `tests/test_web_tokens.py` -- adaptés (en-têtes à boutons, clés nouvelles).
- `tools/e2e/run_e2e.py` -- `s_model_catalog` : tri par taille (ordre et `aria-sort`), filtre réseau + texte, compteur, aucun résultat puis réinitialisation ; `_models_row` suit le balisage ; `s_diagnostic` ou le scénario à sonde lente : message de recherche et compteur visibles pendant `SLOW_PROBE`, puis la liste.
- DESIGN.md, EXPERIENCE.md, ARCHITECTURE-SPINE -- mis à jour ; entrée « liste vide pendant la recherche » de `deferred-work.md` (story 8b) fermée.

**Acceptance Criteria:**
- Given `/models` en `de` à 1 280 px, when l'utilisateur trie par « Fenêtre » puis filtre « Netzwerk », then seules les lignes réseau restent, triées par fenêtre dans leur groupe, et le compteur est juste.
- Given un premier lancement avec des modèles à sonder, when `/diagnostic` s'ouvre pendant les sondes, then la page dit que la recherche est en cours et compte les modèles testés jusqu'au résultat.

## Design Notes

- AD-1 (« le front ne calcule rien ») vise l'état du harnais ; trier et filtrer des lignes déjà servies est de la présentation, comme le repli des volets.
- `total` compte les seules sondes à faire, pour que la barre avance au rythme réel (les entrées en cache ne coûtent rien).

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q tests/test_cli_diagnostic.py tests/test_ui_texts.py tests/test_web_tokens.py tests/test_model_catalog.py tests/test_web_app.py tests/test_i18n.py` -- expected: tout passe.
- E2E (orchestrateur) : `--only model_catalog themes local_server`, `--only annex_language model_switch` -- expected: 0 échec.

## Review Triage Log

### 2026-10-01 — Review pass
- verdicts: 35 findings — high 0, medium 14, low 17, false 4, maybe-false 0 (doublons gardés sur leur ligne, avec la route de leur groupe)
- findings:
  - Intent Alignment
    - `[medium]` `[patch]` R1 : `_discover` émet aussi depuis `select_model` et `select_server` (un `{0, 0}` « tout est en cache » à chaque choix de serveur) — `_discover(report_progress=…)`, vrai seulement depuis `_check_model_locked` ; test `test_choosing_a_file_after_the_search_emits_no_progress`.
    - `[low]` `[reject]` R2 : `progress` = dernier événement du journal, pas celui de la recherche en cours — après le correctif R1, seule la recherche au lancement émet, et `searching` n'est vrai qu'avant son premier résultat : aucun autre émetteur ne peut s'intercaler.
    - `[medium]` `[defer]` R7 : rien ne vérifie que tout tient en `de` à 1 280 et 1 600 px — vérification visuelle reportée à la recette de la phase 3 (frontmatter `deferred`).
    - `[low]` `[reject]` R6 : des `px` restent (largeur maximale, bordures `1px`) — « taille » lue comme typographie, contrôlée par `test_web_tokens` ; les bordures `1px` sont la convention de `llm.css` et `rag.css`.
    - `[medium]` `[defer]` La mise à jour en direct n'est éprouvée qu'avec un flux simulé (`page.route`) — la pile E2E n'a pas de sonde lente au lancement ; frontmatter `deferred`.
    - `[medium]` `[defer]` La bascule « Fin » en direct (contrôle `model`, puis liste) n'est jouée nulle part — même cause, même entrée différée.
    - `[false]` `[reject]` `deferred-work.md` se dit « vérifié » sans exécution — les vérifications ont tourné depuis : pytest des fichiers de la spec et tranche `model_catalog` (114 vérifications, 0 échec).
  - Verification Gap
    - `[medium]` `[patch]` Des tags Ollama qui partagent un blob sont sondés une fois chacun (les sondes passent après la boucle, le cache n'est plus écrit entre deux) — `to_probe` dédoublonné par chemin, résultat recopié sur les tags frères ; test `test_ollama_tags_sharing_one_blob_are_probed_once`.
    - `[medium]` `[patch]` Tri et filtres de `/models` peu couverts (outils « non », raisonnement « oui », éditeur, tri à rangs) — `_models_sort_and_filters` étendu.
    - `[low]` `[reject]` Résumé `diagnostic_progress` du journal de l'atelier non testé — texte d'affichage ; ses clés sont vérifiées par `test_ui_texts`, et le pluriel est corrigé (ci-dessous).
    - `[medium]` `[patch]` Émission hors recherche (doublon de R1) — même correctif.
    - `[medium]` `[defer]` Chaîne réelle au lancement non jouée de bout en bout (doublon) — même entrée différée.
  - Edge Case Hunter
    - `[medium]` `[patch]` Blob partagé sondé N fois (doublon) — même correctif.
    - `[low]` `[patch]` `select_server` (`probe_only=set()`) écrit « tout est en cache » (doublon de R1) — même correctif.
    - `[low]` `[patch]` Journal : « 1 modèles testés sur 1 » — `main.log.diagnostic_progress` en `.one`/`.other` dans les trois langues, `app.js` passe `count`.
    - `[low]` `[patch]` Le flux rejoue l'historique : le compteur peut reculer un instant à l'ouverture — `onProgress` ignore l'historique (`live` faux) : `/api/diagnostic` a déjà donné le dernier état.
    - `[low]` `[patch]` Une fenêtre `0` (affichée « — ») se trie en tête — clé `m.window || null`.
    - `[low]` `[patch]` `_models_window_then_network` passe si la liste réseau est vide — `bool(network)` ajouté.
    - `[medium]` `[defer]` Sonde lente simulée (doublon) — même entrée différée.
  - Blind Hunter
    - `[low]` `[patch]` Journal non pluralisé (doublon) — même correctif.
    - `[medium]` `[patch]` Émission hors recherche (doublon) — même correctif.
    - `[low]` `[patch]` `total = 0` toujours dit « tout est en cache », faux sans fichier ou avec des échecs mémorisés — texte neutre « Aucun modèle à tester » (fr, en, de).
    - `[low]` `[reject]` Le tri « Éditeur » ne déplace rien (groupes par éditeur) — colonne exigée triable par l'intention ; le groupe « Autres éditeurs » mélange des noms.
    - `[false]` `[reject]` Le tri par taille ignore `params_b` des modèles cloud — `compareValues` passe à la valeur suivante quand les deux `size_bytes` sont nuls (`x === y`), et un groupe ne mélange jamais local et réseau.
    - `[low]` `[reject]` Pas de retour à l'ordre servi ; « Réinitialiser » garde le tri — un rechargement le rend ; un troisième état ajoute de la logique pour un besoin rare.
    - `[low]` `[reject]` `progress` non lié à la recherche courante (doublon de R2) — même raison.
    - `[low]` `[reject]` `done ≤ total` non imposé par le catalogue — le seul émetteur le garantit et la page borne déjà.
    - `[medium]` `[defer]` Critère 2 non éprouvé avec de vraies sondes (doublon) — même entrée différée.
    - `[medium]` `[patch]` Tris et filtres non testés (doublon) — même correctif E2E.
    - `[medium]` `[defer]` Tenue en `de` à deux largeurs (doublon de R7) — recette.
    - `[low]` `[reject]` `test_web_tokens` laisse passer des `px` (doublon de R6) — même raison.
    - `[low]` `[reject]` Boutons copiés en trois endroits, ombre pressée du secondaire — copie conforme de `llm.css:218-222` (même état pressé) ; factoriser touche `/llm` et `/rag`, hors de la story.
    - `[low]` `[reject]` `role="status"` annonce à chaque frappe — région polie, regroupée par les lecteurs d'écran ; un anti-rebond ajoute un minuteur pour un gain faible.
    - `[false]` `[reject]` `deferred-work.md` « vérifié » (doublon) — même réfutation.
    - `[false]` `[reject]` DESIGN.md dit « 4 px » alors que le jeton est `spacing.1` — `--spacing-1` vaut 4 px : la prose est juste.

## Auto Run Result

- **Résumé** : `/models` triable (boutons d'en-tête, `aria-sort`, tri dans chaque groupe, inconnus en dernier) et filtrable (hébergement, éditeur, outils, raisonnement, texte libre, compteur « n sur N », état vide avec réinitialisation) ; `/diagnostic` dit « Recherche et test des modèles en cours… » avec une barre `{done} sur {total}` alimentée par le nouvel événement `diagnostic_progress` et les champs `searching`/`progress` de `/api/diagnostic` ; les deux pages refaites sur les tokens (`pages.css`, `body.annex-page`), cartes cloud, boutons primaire et secondaire.
- **Fichiers** : `trace/catalog.py` (payload), `session/diagnostic.py` (émission pendant la recherche au lancement, sondes dédoublonnées par blob), `web/app.py` (`searching`, `progress`), `static/models.html`, `static/diagnostic.html`, `static/pages.css`, `static/app.js` (résumé au journal), `content/ui.yaml` et surcouches en/de, tests (`test_cli_diagnostic`, `test_ui_texts`, `test_web_tokens`, `test_web_app`), `tools/e2e/run_e2e.py` (+ captures 44b et 49b), DESIGN.md, EXPERIENCE.md, ARCHITECTURE-SPINE, `deferred-work.md`.
- **Revue** : 35 constats ; 9 correctifs (progression limitée à la recherche au lancement, blob Ollama sondé une fois, pluriel et texte neutre du journal, historique du flux ignoré, fenêtre 0 inconnue, E2E étendu aux filtres outils/raisonnement/éditeur et au tri à rangs, garde `bool(network)`) ; 2 entrées différées (chaîne réelle au lancement non jouée en E2E ; tenue en `de` à deux largeurs, à voir en recette) ; rejets motivés dans le journal de triage.
- **Revue de suivi recommandée** : `true` (premier passage, trois entrées `medium` corrigées, 0 `high`). Risque nommé : la fin de la recherche en direct sur `/diagnostic` (contrôle `model` reçu, `onProgress` filtré sur le direct, rechargement de la liste) n'est éprouvée par aucun test de bout en bout.
- **Vérification** : `ruff check` et `ruff format --check` propres ; `node --check app.js` ; pytest en quarts 3 503 (3 échecs Headroom hors ligne, sujet de la story 4, sans lien) + 603 + 309 (3 ignorés) + 331 ; E2E `model_catalog themes local_server` 114/114, `annex_language model_switch` 68/68 avant correctifs, `model_catalog` 54/54 et `annex_language model_switch local_server` 108/108 après.
- **Risques résiduels** : la bascule en direct de la recherche vers la liste n'est vue qu'en pytest (API) et par flux simulé.