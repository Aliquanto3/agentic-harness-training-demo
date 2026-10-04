---
title: 'Lot 1 du plan de corrections du 2026-10-04 : nommage D2, Pascal, dépense sur 3 lignes, aides et replis'
type: 'chore'
created: '2026-10-04'
status: 'done'
baseline_commit: '64c660d7c45a77fb78b116c36e4d9309750a5967'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-2026-10-04.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les retours d'Anaël du 2026-10-04 sur `main` (64c660d) relèvent huit irritants rapides : onglets mal nommés (« Atelier », « LLM nu »…), persona féminine « Camille » à remplacer, dépense tassée sur deux lignes, « Actions forcées » sans aide, arbre JSON du contexte tout déplié, ligne « Préfixe non réutilisé » obscure et qui s'ouvre seule, titres du Diagnostic peu parlants, modèles du RAG absents du guide d'installation.

**Approach:** Un seul passage de build sur les huit points du lot 1 du plan, en fr/en/de, tests pytest et E2E mis à jour en même temps que le code.

## Boundaries & Constraints

**Always:**
- D2 : barre courte `Harnais · LLM · RAG · MCP · 🛠️ Diagnostic` (en `Harness · LLM · RAG · MCP · 🛠️ Diagnostics`, de `Harness · LLM · RAG · MCP · 🛠️ Diagnose`). Titres complets dans `<title>` (« WaveStack — … ») et `h1` : « Atelier Harnais », « Atelier LLM », « Atelier RAG », « Atelier MCP », « Diagnostic et modèles » (en « Harness workshop », « LLM workshop », « RAG workshop », « MCP workshop », « Diagnostics and models » ; de « Harness-Werkstatt », « LLM-Werkstatt », « RAG-Werkstatt », « MCP-Werkstatt », « Diagnose und Modelle »).
- Décision : le `h1` des ateliers garde son sous-titre après le titre complet (« Atelier LLM : l'intérieur du modèle », « Atelier RAG : l'architecture RAG à manipuler », « Atelier MCP : le protocole à manipuler »).
- Décision : « Modèles » quitte la barre (cinq onglets, comme D2) ; la page `/models` reste servie, son onglet courant est « 🛠️ Diagnostic », et la page Diagnostic gagne un lien vers `/models` jusqu'à la fusion du lot 3.
- Décision : l'index n'a pas de `h1` ; on en ajoute un « Atelier Harnais » masqué visuellement (`.sr-only`), pour ne pas prendre de hauteur à l'écran principal ni en projection.
- Décision : « LLM nu » qui nomme l'écran `/llm` devient « Atelier LLM » (contenus, messages, journal, docs) ; « LLM nu » qui nomme le concept (aucune brique active : scénarios, réinitialisation, `no_brick`, glossaire MCP) reste. Cela s'écarte du plan pour `messages.yaml:114`, qui nomme l'écran.
- Camille → Pascal partout (contenus fr/en/de, tests, E2E), accordé au masculin (« consultant », « Berater »).
- Textes d'interface en fr dans `content/`, surcouches en/de complètes (mêmes clés).

**Never:**
- Pas de fusion Diagnostic/Modèles (lot 3), pas de redirection `/models`, pas de logo.
- Pas de route `/docs` : les messages citent le guide en chemin texte (`docs/installation.md`, section « Modèles du RAG »).
- Ne pas toucher au calcul du cache (`_check_prefix`, `_check_reuse`, `_diverging_cause`), seulement à la charge utile de l'événement et à son affichage.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Dépense payante | appels cloud > 0, mode GreenOps | 3 lignes : « Dépense estimée » / `💰 ~x $ + y $` / `🍃 a–b g CO₂e`, à 1600, 1440 et 1280 px, normal et projection | `title` = `aria-label` = phrases complètes |
| Appels locaux seuls | aucun appel payant | 2 lignes : « Empreinte estimée » / `🍃 a–b g CO₂e` | pas de « · » en tête |
| Préfixe non réutilisé | événement `prefix_not_reused` en dernier pas d'un tour en direct | ligne « Cache non réutilisé », figure `cause · N tokens relus`, repliée ; dépliée seulement au clic | cause inconnue : figure sans cause |
| JSON du contexte | ouverture d'un bloc du Contexte LLM | racine ouverte (clés visibles), sous-nœuds repliés ; un clic ouvre et l'état survit au rendu suivant | remis à zéro avec les autres replis |

</frozen-after-approval>

## Code Map

Front : `src/wavestack/web/static/` (abrégé `static/`).

- `static/{index,llm,rag,mcp,diagnostic,models}.html` -- barre `nav.site-nav[data-i18n-links]` (l.20-26 ; diagnostic 142-148 ; models 79-85), `aria-current` sur l'onglet de la page ; `<title data-i18n=…>` l.8 (index sans data-i18n) ; `h1` llm:55, rag:55, mcp:59, diagnostic:175, models:112 ; `h2` diagnostic:184 (`candidates_title`), :204 (`cloud_title`).
- `static/i18n.js:111-121` -- `LINK_NAMES` et réécriture du texte des liens depuis `common.links.<name>` ; retirer `/models` de la barre mais garder la page fonctionnelle.
- `static/llm.js:174-177`, `rag.js:695`, `mcp.js:625` -- écrasent `h1` et `document.title` depuis `title_text` des YAML d'atelier.
- `content/ui.yaml` -- `common.links` 74-84 (`home`, `llm`, `rag`, `mcp`, `diagnostic`, `models`, `*_title`) ; `llm.page_title` 900, `rag.page_title` 928, `mcp.page_title` 954, `diagnostic.page_title/title/candidates_title/cloud_title` 1019-1022, `models.page_title` 1082 ; écran LLM : 712-716, 746, 771 ; NE PAS toucher 112-113, 795, 873. En/de : `content/i18n/{en,de}/ui.yaml` (décalage d'environ −9 lignes).
- `content/{llm,rag,mcp}_lab.yaml` -- `title_text` (l.5, 5, 6 ; en/de l.4) ; commentaire l.1 de `llm_lab.yaml`.
- `content/messages.yaml` -- écran LLM : 69, 114, 446-447, 456, 488-490 (+ en/de) ; `session.rag_lab.embedding_absent` 507 et `reranker_absent` 515 (en 503/510, de 505/513) : ajouter le renvoi au guide.
- Camille : `content/scenarios.yaml:97`, `content/memory/memory.yaml:37-39`, `content/i18n/en/{scenarios.yaml:65,memory/memory.yaml:30-32}`, `content/i18n/de/{scenarios.yaml:70,memory/memory.yaml:30-32}`, `tests/test_global_memory.py:24-28,205,255-271` (« Consultante. »), `tests/test_e2e_fake_openai.py:120,125`, `tests/test_i18n.py:552-583`, `tests/test_subagent.py:109,124`, `tools/e2e/run_e2e.py:564,569,5503,5524,5579,5584,8394,8467,8470`.
- `static/app.js:2406-2453` `renderConsumption` (label / `#consumption-money` / `#consumption-footprint`, séparateur « · » à retirer) ; `fitFootprint` 2459-2478, `topBarFits` 2480-2491, `footprintOptional`, `footprintFitKey` et leurs appels 1102, 2618, 7468, 7508-7511 : à retirer. `static/index.html:235` `#consumption` ; `static/app.css:4836-4858`.
- `static/app.js:1628-1659` `forcedToggle` ; modèle d'aide `app.js:1291-1319` (`button.brick-help[popovertarget]`, `div.brick-explanation[popover]`, ancrage CSS, `store.openBrickHelp`/`reopenPopovers` pour survivre au rendu) ; CSS `app.css:2317-2372` (`.brick-help` est `absolute` dans `.brick-card` : prévoir une variante en ligne dans le titre) ; `force-section` CSS 2650-2710.
- `static/app.js:98-103` (`store.jsonClosed`), 3589-3591 (`clearCtxFolds`), 4203-4227 (`jsonTree`/`jsonNode`, chemin racine `json:${key}`, enfants `/…`).
- `static/app.js:5473-5484` (ligne préfixe), 5983-5989 et 6055 (ligne courante dépliée en direct : `row.sticky || (o.live ? isCurrent : …)`) ; `src/wavestack/session/app_session.py:7528` et `:7605` (charges utiles `prefix_not_reused`) ; `ui.yaml:581-582` (`main.orch.rows.prefix`, `common_tokens`), 688 (`main.log.hook_decisions.prefix_not_reused`).
- `docs/installation.md` -- sommaire 9-16, nouvelle section après « ## Le modèle local » (142-154) ; données : `wavestack.toml` `[rag.embedding]` 86-105, `[rag.reranker]` 107-124, `[rag_lab]` 126-141 ; `scripts/build_rag_index.py` (`--download` ne prend que l'embedding, `--lang`, `--model`) ; `pyproject.toml` extra `rag-alt` ; fastembed hors pyproject (`docs/guide.md:349-355`).
- Docs à renommer : `README.md:20-21,69` (+ l.25 lien vers la section), `docs/installation.md:163,176`, `docs/guide.md:13-15,28-33,213-215,263-265,358-360,410-411,462,528`, `docs/modeles.md:41,425,448,514,517`. Garder README 3, 9, 11, 70 et guide 68 (concept).

## Tasks & Acceptance

**Execution:**
- [x] `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- `common.links` (barre D2, `*_title` reformulés « Atelier LLM : … »), `page_title` des cinq pages et de l'index (nouvelle clé `main.page_title`), `diagnostic.title` « Diagnostic et modèles », titres 💻/☁️, libellés écran LLM, `main.orch.rows.prefix` « Cache non réutilisé » et `again_tokens` « {tokens} tokens relus », `main.force.help_label`/`help_text` (« Le harnais déclenche lui-même l'outil, sans laisser le modèle décider. »), `diagnostic.models_link`, `main.consumption.*` si besoin -- D2, points 3, 4, 6, 7.
- [x] Les six pages HTML et `static/i18n.js` -- barre à cinq liens, emoji 🛠️, `aria-current` (« 🛠️ Diagnostic » sur `/models`), `<title>` data-i18n, `h1` sr-only à l'index, lien `/models` dans `diagnostic.html` -- D2.
- [x] `content/{llm,rag,mcp}_lab.yaml` et surcouches -- `title_text` commençant par le titre complet -- D2.
- [x] `content/messages.yaml` et surcouches -- écran « Atelier LLM » ; renvoi `docs/installation.md` (section « Modèles du RAG ») dans `embedding_absent` et `reranker_absent` -- D2, point 8.
- [x] Fichiers Camille listés au Code Map -- Pascal, accord masculin -- point 2.
- [x] `static/app.js`, `static/index.html`, `static/app.css` -- dépense sur 3 lignes (`💰`, `🍃`), retrait de `fitFootprint`/`topBarFits` ; « ? » d'aide à côté du titre « Actions forcées » sur le modèle `.brick-help` + popover, rouvert après rendu ; JSON replié sauf racine (ensemble des chemins inversés par l'utilisateur, remis à zéro par `clearCtxFolds`) ; ligne préfixe : titre et figure `cause · N tokens relus`, jamais dépliée automatiquement comme ligne courante -- points 3 à 6.
- [x] `src/wavestack/session/app_session.py` -- ajouter `again_tokens` (tokens relus) aux deux charges utiles `prefix_not_reused` (`len(ids) - common` en tour, `again` sinon) -- point 6.
- [x] `docs/installation.md` (+ sommaire), `README.md`, `docs/guide.md`, `docs/modeles.md` -- section « Modèles du RAG » (embedding Granite 121 Mo, reranker BGE 438 Mo, dossiers `models/embedding|reranker/`, téléchargement depuis la carte RAG ou copie hors ligne, index livrés et `scripts/build_rag_index.py --download --lang`, `uv sync --extra rag-alt`, fastembed facultatif) ; renommages -- points 1, 8.
- [x] `tests/test_ui_texts.py:206-235`, `tests/test_llm_lab.py:100,284,416,818-825`, `tests/test_turn_cache.py` (si charge utile assertée), tests Camille, `tools/e2e/run_e2e.py` (ordre de barre 2341, 6318-6336, 9309-9392, 9510, 10450-10476, 11331-11364, 829-840 JSON, 10005-10203 dépense, 7253 si texte changé) -- adapter ; ajouter une vérif E2E de l'aide « Actions forcées » et du repli JSON des sous-nœuds ; un test pytest de `again_tokens`.

**Acceptance Criteria:**
- Given n'importe quelle page en fr, en ou de, when elle s'affiche, then la barre montre exactement les cinq onglets D2 dans l'ordre et l'onglet de la page porte `aria-current`.
- Given `/llm`, `/rag`, `/mcp`, `/diagnostic`, `/`, when la page est chargée, then `document.title` est « WaveStack — <titre complet> » et le `h1` commence par ce titre.
- Given l'atelier, when on clique sur le « ? » d'« Actions forcées », then une bulle affiche le texte d'aide, ancrée au bouton, et reste ouverte après un nouveau rendu.
- Given le scénario mémoire, when il tourne, then l'assistant connaît « Pascal », consultant en cybersécurité, et aucun « Camille » ne reste hors de `_bmad-output/`.
- Given `docs/installation.md`, when on suit la section « Modèles du RAG », then on sait où poser les deux GGUF, comment les télécharger et reconstruire un index.

## Implementation Notes

- Branche `fix/lot-1-quick-wins-2026-10-04` depuis `64c660d`. `store.jsonClosed` devient `store.jsonToggled` (chemins inversés par l'utilisateur ; racine ouverte, sous-nœuds repliés). Ligne préfixe : drapeau `quiet`, `o.currentSticky` renommé `o.currentApart` (sticky ou quiet). `again_tokens` ajouté aussi à `PrefixNotReusedPayload` (`trace/catalog.py`). `llm.js` n'écrase plus `document.title`.
- Couverture de la matrice : dépense 3 lignes et empreinte seule (E2E `_gemini_costs`, `_session_footprint`, `_local_footprint`) ; préfixe (E2E `_cache_not_reused` dans `s_local_server`, faux llama-server, cause `system` ; pytest `test_turn_cache`, `test_tools`) ; JSON (E2E `_read_and_produced`). Le cas « cause inconnue » n'est pas productible une fois `llm` libellé : chaque valeur de `PrefixCause` a son libellé.
- Messages en/de : la doc n'existe qu'en français, ils citent la section « Modèles du RAG » (in French / auf Französisch).
- Écarts connus : `tests/test_docs_links.py::test_readme_is_a_short_onboarding_page` échouait déjà au commit de base (README de 120 lignes pour 100), 121 lignes maintenant ; E2E `annex_language` passe seul, échoue joué juste après `rag rag_rerank rag_lab` (textes français de ces scénarios, aucun texte du lot), non rejoué au commit de base. E2E lancé avec `--channel msedge` (Chromium de Playwright absent). Captures E2E régénérées.
- Revue (passe 1) : 21 constats ; 7 corrigés (figure sans « 0 tokens relus », cause `llm` libellée, pluriel `again_tokens`, commentaires, `h1` dans `<main>`, sélecteur `:scope > summary`, `tools/e2e/README.md`), 2 différés (barre sous 1280 px non mesurée ; README > 100 lignes, rouge dès la base), 12 rejetés (journal ci-dessous).
- Vérification finale : `ruff check` et `ruff format --check` propres ; `node --check` (app.js, i18n.js, llm.js) sans erreur ; aucun « Camille » hors `_bmad-output/` ; pytest en quatre quarts : 5 465 passés, 11 sautés, 1 échec (`test_readme_is_a_short_onboarding_page`, préexistant). E2E (`--channel msedge`, `PYTHONUTF8=1`) : diagnostic, bare_llm, short_memory, native_tools, disciplines, themes, forced_native, global_memory, mcp_lab, model_switch, reasoning_dropped, local_server, gemini_shape, priced_estimate, model_catalog, llm_screen, ui_language : 439 PASS, 0 FAIL ; `rag rag_rerank rag_lab` : 98 PASS, 0 FAIL (`rag_lab` seul échoue faute du modèle d'embedding factice que `rag` télécharge : dépendance d'ordre). Captures E2E remises à l'état de la base.


## Spec Change Log

## Review Triage Log

Passe 1 (Blind Hunter BH, Edge Case Hunter EC, Verification Gap VG).

| # | Constat | Verdict | Preuve | Suite |
|---|---|---|---|---|
| EC2/BH1a | « 0 tokens relus » quand `again_tokens` vaut 0 (branche `in_cache`) | medium | `app_session.py` : `if not again` émet `in_cache` avec `again = 0` ; `app.js` affiche alors « 0 tokens relus », contraire au titre | patch |
| BH1b | Sur un modèle hybride, la figure sous-estime les tokens relus | low | la session ne sait pas si le moteur est hybride (le message le dit au conditionnel) ; corriger demande une détection | rejeté |
| EC1 | Cause `llm` sans libellé dans `main.orch.prefix_causes` : la figure perd sa cause | low | `PrefixCause` contient `llm`, `ui.yaml` n'a pas la clé ; défaut ancien, exposé par la nouvelle figure | patch |
| EC3 | « 1 tokens relus » : pas de pluriel | low | `again_tokens` sans `one`/`other` ; correction directe | patch |
| BH4 | Commentaires périmés (`index.html` au-dessus de `#consumption`, `store.openBrickHelp`) | low | décrivent l'empreinte en fin de 2e ligne et des ids de briques seulement | patch |
| BH14 | `h1.sr-only` hors de `<main>` | low | `index.html` : h1 avant `<main class="layout">` ; `.sr-only` est `absolute`, le déplacer ne touche pas la grille | patch |
| EC5 | Sélecteur `inner.locator("> summary")` | low | `run_e2e.py:926` ; le fichier utilise `:scope > summary` ailleurs (l.1039) | patch |
| BH7 | `tools/e2e/README.md` décrit encore « Modèles » courant, « LLM nu », « Atelier RAG », arbre JSON tout ouvert | low | lignes 402, 456, 483-490, 550-555 non mises à jour | patch |
| BH3/EC6 | Sans `fitFootprint`, la barre peut déborder sous 1280 px | maybe-false | l'E2E vérifie 1600, 1440, 1280 px en normal et projection (comme avant) ; sous 1280 px, à mesurer | defer (medium non vérifié) |
| VG1 | `test_readme_is_a_short_onboarding_page` rouge (121 > 100) | low | déjà rouge au commit de base (120 lignes) | defer |
| BH2a | `again_tokens` obligatoire mais garde `== null` en JS | low | branche défensive inoffensive | rejeté |
| BH2b | `common_tokens` n'est plus affiché | false | décision du plan (« Cache non réutilisé : N tokens relus ») ; le message garde le nombre commun | rejeté |
| BH5 | `aria-current="page"` sur Diagnostic depuis `/models` | low | rare (lecteur d'écran sur `/models`), correction CSS + tests, page fusionnée au lot 3 | rejeté |
| BH6 | Emoji dans les textes accessibles | false | emoji imposés par D2 et le point 7 (bloc figé) | rejeté |
| BH8 | « LLM nu » a deux sens | false | décision du bloc figé (concept gardé, écran renommé) | rejeté |
| BH9 | Texte d'aide « Actions forcées » incomplet | false | texte fixé par le plan et le bloc figé | rejeté |
| BH10 | Renvoi à la doc en chemin texte | false | bloc figé : pas de route `/docs`, chemin texte | rejeté |
| BH11 | Section « Modèles du RAG » sans commande sha256 ni coût mémoire | low | complément utile, pas un défaut ; l'`url` est bien dans la section | rejeté |
| BH12 | `<title>` et h1 de `/llm` de deux sources | low | D2 : `<title>` depuis `llm.page_title` | rejeté |
| BH13 | Pas de « tout déplier » pour le JSON | false | repli par défaut voulu (point 5) | rejeté |
| EC4 | `inset: auto` annule le repli hors ancrage CSS | low | les aides des cartes dépendent déjà de l'ancrage ; cible Edge/Chrome | rejeté |

## Design Notes

Ligne préfixe : le rapport d'enquête montre qu'en direct la dernière ligne du dernier tour est dépliée d'office (`app.js:6055`), d'où l'impression qu'elle « paraît dépliée » quand l'événement est le plus récent. Correctif : un drapeau de ligne (p. ex. `quiet: true`) exclu du dépliage automatique, sans toucher au suivi de la ligne courante.

## Verification

**Commands:**
- `uv run ruff check src tests tools ; uv run ruff format --check src tests tools` -- expected: aucun écart
- `node --check src/wavestack/web/static/app.js src/wavestack/web/static/i18n.js` -- expected: aucune erreur
- `uv run pytest -q tests/test_ui_texts.py tests/test_llm_lab.py tests/test_turn_cache.py tests/test_i18n.py tests/test_global_memory.py tests/test_subagent.py tests/test_e2e_fake_openai.py tests/test_web_app.py` -- expected: tout passe
- pytest en quatre quarts des `tests/test_*.py` triés, un à la fois -- expected: tout passe
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only <scénarios touchés>` (diagnostic, bare_llm, short_memory, global_memory, llm_screen, langues, FinOps/GreenOps, MCP/RAG lab pages, contexte JSON) -- expected: 0 FAIL
- `rg -i camille --glob '!_bmad-output/**'` -- expected: aucune occurrence
