---
title: 'Suites de la recette PC du 02/10 : Markdown dans la Vue humain, attente du diagnostic (R1), réponse d''erreur tracée (R2), barre basse en mode focus'
type: 'bugfix'
created: '2026-10-02'
status: 'done'
route: 'dispatch'
baseline_commit: '94a5bbf9399975539856497a098086d5842bca0a'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/resultats-test-pc-2026-10-02.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La recette PC du 02/10 a laissé trois points ouverts, plus un quatrième à vérifier. (1) La Vue humain affiche la réponse finale en Markdown brut (« *   **January 1st:** … »). (2) R1 : `/diagnostic` reste vide, sans texte d'attente, tant que `GET /api/diagnostic` n'a pas répondu (9,9 s au premier lancement), et rien ne permet d'en trouver la cause. (3) R2 : un refus HTTP d'un modèle cloud (429 de Mistral) ne laisse dans le journal que `stop_reason: "error"`, sans statut ni en-têtes de quota. Vérification préalable, **confirmée** par Playwright à 1280×672, 1440×900 et 1280×624 : Orchestration agrandie (⛶), un `scrollIntoView` vers le bloc « Données sortantes », la molette ou la touche Fin font défiler toute la page, et la barre basse remonte au milieu de la fenêtre. Cause : en mode focus, `.right` passe en colonne sans `min-height: 0`, ne rétrécit pas et déborde du `body`, qui fait 1 165 px de haut. Injecter `body.focus-mode .right { min-height: 0; }` suffit : plus aucun défilement de la page, et la barre reste en place dans les trois tailles.

**Approach:** Un petit rendu Markdown maison, en module ES embarqué, appliqué à la seule réponse finale de la Vue humain. Un texte d'attente traduit dans les trois sections du diagnostic, et une mesure de durée côté serveur, écrite dans les logs. Un nouvel événement `outbound_response`, émis par la fabrique HTTP à côté de `outbound_request`, pour toute réponse d'erreur venue d'hors de la boucle locale. Enfin, la règle CSS du mode focus.

## Boundaries & Constraints

**Always:**
- **Rendu Markdown maison, en DOM.** Le rendu est construit uniquement avec `createElement`, `textContent` et `createTextNode`. Jamais de `innerHTML`, `outerHTML`, `insertAdjacentHTML` ni `document.write` dans le module : le HTML écrit par le modèle s'affiche comme du texte.
- **Sous-ensemble rendu :**
  - paragraphes, avec un saut de ligne simple rendu par `<br>` ;
  - gras (`**x**`, `__x__`) et italique (`*x*`, `_x_`), le soulignement seulement en bordure de mot, pour que `snake_case` reste intact ;
  - listes à puces (`-`, `*` ou `+`, suivis d'une ou plusieurs espaces) et numérotées (`1.` ou `1)`, avec l'attribut `start`), imbriquées selon l'indentation ;
  - titres `#` à `######`, rendus par `h3` à `h6` (`#` donne h3, `##` donne h4, au-delà h5 puis h6), pour rester sous les titres des volets ;
  - code en ligne ;
  - blocs de code délimités par trois accents graves ou trois tildes. Un bloc encore ouvert pendant le streaming va jusqu'à la fin du texte.
  - Les échappements par antislash donnent le caractère seul.
- **Liens.** `[texte](url)` devient un lien `<a target="_blank" rel="noopener noreferrer">` seulement si `new URL(url)` a pour protocole `http:` ou `https:`. Sinon, la source exacte reste en texte inerte (`javascript:`, `data:`, URL relative ou invalide).
- **Streaming sans clignotement.** Le nœud rendu est mémorisé par tour (identifiant du tour et texte) : un rendu dont le texte n'a pas changé réutilise le même nœud ; un texte qui a changé est rendu à nouveau, en une seule opération synchrone dans le même `render()`.
- **Texte brut ailleurs.** Le raisonnement (Vue humain comme Contexte LLM), le Contexte LLM, Orchestration, le journal, la comparaison des tours et `announce()` (`#chat-live`) restent en texte brut.
- **Diagnostic.**
  - Une clé `diagnostic.loading` en fr, en et de, affichée dans les trois listes jusqu'à leur premier rendu.
  - Dans Contrôles, le texte disparaît à la première ligne de contrôle reçue par le flux.
  - Côté serveur, chaque appel journalise en `debug` sa durée totale et celle de chaque étape (`active_choice`, `cloud_rows`, `_models`, `shown`), plus l'attente avant le gestionnaire (mesurée par un middleware limité à cette route), le numéro de l'appel et le temps écoulé depuis la création de l'application.
  - La même ligne passe en `warning` (visible dans la console de `uv run wavestack`) quand le total atteint `SLOW_DIAGNOSTIC_S = 1.0`.
- **`outbound_response`.**
  - Il est émis par un crochet `response` des deux clients de `net/factory.py` (synchrone et asynchrone), pour tout statut ≥ 400 d'un hôte hors de la boucle locale.
  - Charge utile : `origin`, `method`, `url`, `status`, `headers` (liste de `{name, value, masked}`, dans l'ordre reçu).
  - Masquage selon la même règle que `outbound_request` : nom gardé, valeur `MASKED`, sauf pour une liste fermée, `config.PUBLIC_RESPONSE_HEADERS` (`content-type`, `content-length`, `date`, `retry-after`) et les préfixes `x-ratelimit-` et `ratelimit-`.
  - L'événement a un libellé dans `main.log.kinds` (fr, en, de), une branche dans `eventSummary` (`429 · POST url · en-têtes non masqués de quota`) et une entrée dans `SUB_KINDS`.
- **Message D6 inchangé.** Le message pour un 429 avec `x-ratelimit-limit-req-minute: 0` reste le même.

**Never:**
- Pas de bibliothèque tierce, de CDN ni de dépendance réseau ou npm.
- Pas de tableaux, citations, barré, règles horizontales, images ni liens automatiques : leur source reste du texte.
- Pas d'événement de journal pour la durée du diagnostic : il polluerait le journal à chaque appel et tomberait après le `seq` de pointe lu par la route.
- Pas d'`outbound_response` pour les statuts inférieurs à 400, ni pour la boucle locale.
- `outbound_response` n'est pas affiché dans Orchestration.
- Aucun changement des messages de `_refused`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Markdown courant | `*   **Jan 1:** New Year` puis `1. a` | `ul>li>strong` puis `ol>li` | N/A |
| HTML du modèle | `<img src=x onerror=alert(1)>` | Texte visible, aucun `img` dans le DOM | N/A |
| Lien dangereux | `[clic](javascript:alert(1))` | Texte inerte, aucun `a` | N/A |
| Lien sûr | `[site](https://example.org)` | `a[href^="https:"][rel~=noopener]` | N/A |
| Bloc ouvert | `` ```py\nx = 1 `` (en cours de flux) | `pre>code` avec `x = 1` | N/A |
| Diagnostic lent | `/api/diagnostic` répond en 1,5 s | « Diagnostic en cours… » dans les 3 listes, puis remplacé | N/A |
| Refus avec quota nul | 429, `x-ratelimit-limit-req-minute: 0`, `x-request-id: abc` | `outbound_response` : 429, quota en clair, `x-request-id` masqué ; puis `model_call_ended` en erreur ; message D6 | Tour en erreur, comme avant |
| Succès ou boucle locale | 200, ou 500 sur 127.0.0.1 | Aucun `outbound_response` | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/app.js:3044` -- `renderChat` : seule ligne à changer (`el("div","bubble-text", turn.text)`). Le rendu, déclenché par `scheduleRender` (rAF), reconstruit les bulles ; mémoire à purger comme `approvalCards` (:3001). `el()` (:1088) et `reasoningBlock` (:2954) restent intacts.
- `src/wavestack/web/static/app.js:679` (`SUB_KINDS`), `:6398` (`eventSummary`, branche `outbound_request` vers :6503), `:6372` (`KIND_LABELS`).
- `src/wavestack/web/static/app.css:729` -- `.bubble` en `pre-wrap` ; il faut `white-space: normal` sur le rendu, `pre` pour les blocs de code. `:2172` : règles du mode focus.
- `src/wavestack/web/static/diagnostic.html:173/185/199` -- `#checks`, `#candidates`, `#cloud-models`. `patchList` (:290) remplace un `<li>` initial ; `renderCheck` (:302) ajoute à `checksEl`. `t()` vient de `i18n.js`.
- `src/wavestack/web/app.py:581` -- `diagnostic_state` (gestionnaire imbriqué de `create_app`), `_models` (:639), `log` (:41), middlewares (:329).
- `src/wavestack/net/factory.py:54` -- `_check_and_trace`, `_headers` (:73), `create_client` (:157), `create_async_client` (:205). `is_loopback` vient de `guard`.
- `src/wavestack/config.py:99` -- `PUBLIC_HEADERS` ; ajouter `PUBLIC_RESPONSE_HEADERS` et les préfixes de quota à côté.
- `src/wavestack/trace/catalog.py:43/52/1345` -- `OutboundHeader`, `OutboundRequestPayload`, `PAYLOAD_MODELS`.
- `src/wavestack/models/openai_chat.py:435/464/498` -- statut ≠ 200, `_refused`, `_no_quota` : ne pas modifier.
- `content/ui.yaml:1009` (`diagnostic:`) et `:659` (`main.log.kinds`), avec les surcouches `content/i18n/{en,de}/ui.yaml` (environ :998 et :650). Le test de parité est `tests/test_ui_texts.py:95`, et l'allemand doit employer la forme de politesse.
- `tools/e2e/fake_openai.py:397` -- `_script` : déclencheurs entre crochets (`[erreur429]` avec `headers`).
- `tools/e2e/wavestack_e2e.py` -- greffes réservées au parcours E2E.
- `tools/e2e/run_e2e.py` -- `s_provider_errors` (:1246), `s_panes` (:2638), `_bar_under_panes` (:2017), `SCENARIOS` (vers :11075), `_log_catalog` (:1138).
- Tests existants à étendre : `tests/test_net_factory.py` (:41, :257), `tests/test_cloud.py` (:877-920, D6), `tests/test_web_app.py` (:18-33, :125), `tests/test_e2e_fake_openai.py` (:128).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/web/static/markdown.js` -- nouveau module : `export function renderMarkdown(text)`, qui renvoie un `DocumentFragment` selon le sous-ensemble et les règles de lien ci-dessus -- rendu sûr sans dépendance.
- [x] `src/wavestack/web/static/app.js` -- importer `renderMarkdown` ; à :3044, `div.bubble-text.is-markdown`, dont l'enfant est mémorisé par tour (`Map`, purgée à chaque rendu) ; ajouter `outbound_response` à `SUB_KINDS` et à `eventSummary` -- Markdown dans la Vue humain seulement, et résumé du journal.
- [x] `src/wavestack/web/static/app.css` -- styles de `.bubble-text.is-markdown` (`white-space: normal`, marges des `p`, listes et titres, `code`, `pre` défilant) avec les jetons de `tokens.css`. Ajouter `body.focus-mode .right { min-height: 0; }` -- lisibilité, et barre basse en place.
- [x] `src/wavestack/web/static/diagnostic.html` -- `<li class="loading-note" data-i18n="diagnostic.loading">` dans les trois listes, retiré de `#checks` au premier `renderCheck` -- R1.
- [x] `content/ui.yaml`, `content/i18n/en/ui.yaml`, `content/i18n/de/ui.yaml` -- clés `diagnostic.loading` et `main.log.kinds.outbound_response` -- i18n.
- [x] `src/wavestack/web/app.py` -- un middleware horodate l'arrivée de `/api/diagnostic` ; `diagnostic_state` mesure ses étapes avec `time.perf_counter` et journalise (debug, warning au-delà de `SLOW_DIAGNOSTIC_S`) -- R1, instrumenter sans deviner.
- [x] `src/wavestack/config.py`, `src/wavestack/trace/catalog.py`, `src/wavestack/net/factory.py` -- liste blanche des en-têtes de réponse, `OutboundResponsePayload` enregistré, crochet `response` des deux clients. Le prédicat « tracé ou non » est factorisé dans `_traced(request)`, utilisé par les deux crochets -- R2.
- [x] `tools/e2e/fake_openai.py` -- déclencheurs `[markdown]` (échantillon couvrant la matrice, injections comprises) et `[quota0]` (429, `x-ratelimit-limit-req-minute: 0`, `x-ratelimit-remaining-req-minute: 0`, `x-request-id`, corps `Rate limit exceeded`) -- faux modèle.
- [x] `tools/e2e/wavestack_e2e.py` -- greffe de `factory._traced` : une requête dont le corps contient `[quota0]` est tracée malgré la boucle locale -- seul moyen de faire passer `outbound_response` par le faux modèle.
- [x] `tools/e2e/run_e2e.py` -- nouveau scénario `markdown` (rendu, injections, liens, autres vues brutes, `MutationObserver` sans perte de `.bubble-text` pendant le flux, rechargement) ; `diagnostic_wait` (`page.route` retarde `/api/diagnostic` de 1,5 s) ; `[quota0]` dans `s_provider_errors` (journal : libellé, résumé, masquage ; message D6), avec la conversation vidée après ; mode focus de chaque volet dans `s_panes` à 1280×672 et 1440×900 (défilement d'Orchestration, molette, Fin : page non défilante, barre sous les volets) -- E2E.
- [x] `tests/test_net_factory.py`, `tests/test_cloud.py`, `tests/test_web_app.py`, `tests/test_e2e_fake_openai.py` -- tests pytest de la matrice côté Python : événement et masquage (synchrone et asynchrone), absence pour 200 et pour la boucle locale, ordre dans un tour Mistral avec D6 inchangé ; journaux du diagnostic (`caplog`) ; déclencheurs du faux modèle ; garde statique : `markdown.js` sans API HTML, et `app.js` qui l'utilise pour `.bubble-text`.
- [x] `tools/e2e/README.md`, `_bmad-output/implementation-artifacts/resultats-test-pc-2026-10-02.md` (défauts fermés) et `deferred-work.md` si une entrée se ferme -- documentation.

**Acceptance Criteria:**
- Étant donné une réponse en Markdown, quand le tour se termine puis que la page est rechargée, alors la Vue humain montre le même rendu, tandis que Contexte LLM, Orchestration et le journal montrent `**` en clair.
- Étant donné le premier appel lent à `/api/diagnostic`, quand il dure plus d'1 s, alors la console de `uv run wavestack` affiche une ligne avec le total, l'attente et chaque étape en ms.
- Étant donné Orchestration agrandie à 1280×672, quand on fait défiler vers le bloc des données sortantes, alors `document.scrollingElement.scrollTop` reste à 0 et la barre basse reste sous les volets.

## Spec Change Log

- 2026-10-02 (implémentation) — Règle du mode focus restreinte à `body.focus-mode .right:has(> .pane.is-focused, > .top-row > .pane.is-focused) { min-height: 0; }`. Déclencheur : le contrôle E2E de `panes` (chaque volet agrandi) a montré qu'appliquée sans condition, la règle faisait défiler la page de 108 px avec Briques agrandi (`.right`, `flex: 1` de base 0, tombait à zéro et ses en-têtes repliés débordaient du `body`). Avec la condition, `.right` garde sa hauteur minimale automatique (les en-têtes) quand le volet agrandi est Briques. KEEP : le correctif d'Orchestration du Problem, même effet dans les trois tailles mesurées.

## Review Triage Log

Passe 1 (Blind Hunter, Edge Case Hunter, Verification Gap).

| Constat | Verdict | Preuve | Suite |
|---|---|---|---|
| Commentaire de `answerNodes` : « une sélection survit au rendu » (B, E, VG) | low | `renderChat` recrée `.bubble-model` à chaque rendu, et `append` déplace les nœuds : la sélection retombe. Ce n'est pas une régression (l'ancien code recréait le texte), mais le commentaire est faux. | patch : corriger le commentaire |
| R1 : l'attente mesurée par le middleware n'est vérifiée par aucun test (VG) | medium | Constat préalablement vérifié : la regex accepte `0 ms`, et supprimer le middleware laisse les tests verts. | patch : test avec `perf_counter` simulé, et aucune ligne pour une autre route |
| Sous-ensemble Markdown non couvert : `__x__`, `1)`, `#` en h3, paragraphe suivi de « 2026. » (VG, B) | medium | Constat préalablement vérifié : ni l'échantillon ni `_markdown_problems` ne les contiennent. | patch : étendre `MARKDOWN_SAMPLE` et les attentes |
| `emphasisAt` accepte une fermeture placée après une ligne vide d'un élément de liste (E) | low | La vérification de `\n\n` n'intervient qu'après l'essai de fermeture : `*a` + ligne vide + `b*` dans un `li` donne un `em` sur deux paragraphes. Corriger revient à déplacer la condition. | patch |
| `border-radius: var(--spacing-1)` sur `code` (B) | low | Jeton d'espacement employé comme rayon ; `pre` emploie `--rounded-sm`. | patch |
| `s_diagnostic_wait` : boucle morte, `continue_` non protégé (B, E) | low | `held[released:]` est toujours vide, et une exception sauterait `unroute`. | patch : une seule boucle sous `suppress`, `unroute` en `finally` |
| `_quota0_refusal` ne vide pas la conversation en cas d'échec (E) | low | Une exception avant `_clear_conversation` garde `[quota0]` dans l'historique : la greffe tracerait alors les appels suivants. | patch : `try/finally` |
| Test lent : vraie seconde de `sleep`, constante figée (B) | low | `time.sleep(SLOW_DIAGNOSTIC_S)` et `assert == 1.0`. | patch : baisser le seuil par `monkeypatch` |
| Rapport du 02/10 : sélecteur coupé sur deux lignes (B) | low | Le span de code est coupé par un retour à la ligne. | patch |
| Analyse quadratique des `[` et `*` non fermés, sur chaque rendu du flux (B, E) | maybe-false | Le balayage est borné par le paragraphe et les rendus sont regroupés par rAF. Il faudrait mesurer un paragraphe de 5 ko de JSON non délimité sur le PC cible. | defer (medium, non vérifié) |
| Premier `/api/diagnostic` en échec : « Diagnostic en cours… » reste affiché (B, E) | low | Avant ce changement, les listes restaient vides de la même façon ; la page relit au prochain événement (`.catch` commenté). Cas improbable, puisque la page est servie par le même serveur, et le correctif ajouterait une branche d'erreur. | rejeté |
| Contrôles sans ligne de contrôle, ou flux jamais ouvert (E) | false | Le diagnostic émet toujours ses contrôles, et le texte d'attente reste juste tant que la recherche tourne ; sans flux, toute la page est hors service. | rejeté |
| Mesure aveugle avant l'ASGI et pendant `await ready` (B, E) | low | Le relevé Resource Timing du 02/10 place les 9,9 s entre l'envoi et la réponse. Un écart entre la mesure du navigateur et celle du log désignerait lui-même un blocage en amont, et la ligne donne le temps écoulé depuis la création de l'application. | rejeté |
| Middleware exécuté sur toutes les requêtes (B) | low | Il ne fait qu'un test de chemin et n'horodate que `/api/diagnostic`, sans coût mesurable. | rejeté |
| `outbound_response` absent de l'atelier MCP et d'Orchestration (B) | false | L'intention gelée limite l'affichage au journal (`Never`). | rejeté |
| Aucun lien entre une réponse et sa requête (B) | low | Les crochets synchrones s'exécutent en séquence dans le même appel. Le correctif ajouterait un champ de charge utile. | rejeté |
| Expression régulière de quota recopiée dans `eventSummary`, résumé long (B) | low | Seuls les en-têtes non masqués sont affichés, la sûreté repose sur `masked`, et c'est un affichage seulement. | rejeté |
| Quota de Gemini dans le corps, erreurs de transport (B) | false | Hors de l'intention (statut et en-têtes). | rejeté |
| `#chat-live` lit les `**` (B) | false | L'intention gelée garde `announce()` en texte brut. | rejeté |
| Liens imbriqués : `a` dans `a` (B, E) | low | C'est réel mais rare dans une sortie de modèle, et le correctif ajouterait un paramètre. | rejeté |
| Un seul échantillon Markdown, et la garde ignore les commentaires `/** */` (B) | low | La couverture est traitée par le patch du VG ; la garde ne donnerait qu'un faux positif. | rejeté |
| Ligne de timing perdue si une étape lève (E) | low | `_models` contient ses erreurs ; une erreur d'`active_choice` donne une 500 visible. | rejeté |
| Même tour rendu deux fois (E) | false | `shownTurns()` ne contient chaque tour qu'une fois. | rejeté |
| `*` dans un span de code (E) | low | Rare, et le correctif ajouterait des sauts de plage. | rejeté |
| Tabulations dans une clôture de liste (E) | low | Rare dans les sorties de modèle. | rejeté |
| « 2026. Une année » en ligne paresseuse après une puce (E) | low | Rare, et le correctif ajouterait une branche. | rejeté |
| `sleep(0.3)` fixes dans `s_markdown` (E) | low | C'est le schéma existant (`last_answer`), stable sur les passages. | rejeté |
| Volet caché en mode focus (E) | false | `_reload_with_panes(r, None)` réaffiche tous les volets juste avant. | rejeté |
| `:has()` non pris en charge (E) | low | Edge et Chrome le prennent en charge depuis la version 105 ; le PC cible a un Edge à jour. | rejeté |
| Espaces multiples réduits hors des blocs de code (E) | low | C'est la sémantique Markdown ; un modèle met le texte aligné dans des blocs. | rejeté |
| La règle du mode focus diffère du texte de la spec (E) | false | L'écart est consigné dans le Spec Change Log, et corriger reviendrait à modifier la spec. | rejeté |
| CSS du mode focus vérifié par l'E2E seulement (VG) | false | `_focus_mode_keeps_the_page_still` s'exécute dans `panes`, joué et vert. | rejeté |

## Design Notes

**Pourquoi un rendu maison.** Une bibliothèque embarquée (marked, markdown-it) produit une chaîne HTML : il faudrait la passer par un assainisseur (DOMPurify) et maintenir deux fichiers tiers. Construire le DOM nœud par nœud rend toute injection impossible par construction, et le sous-ensemble demandé tient en environ 200 lignes.

**Pourquoi le mode focus.** Le défaut ne venait pas du défilement lui-même. `.layout` et `.top-row` portent `min-height: 0`, mais `.right` seulement `min-width: 0` : en colonne, sa hauteur minimale automatique vaut celle de son contenu (Orchestration dépliée), et le `body` (`height: 100vh`) déborde.

**Greffe E2E.** Le faux fournisseur écoute sur 127.0.0.1, que la fabrique ne trace jamais (AD-15). Plutôt que de tracer tout le faux modèle, ce qui changerait les comptes des flux de données de nombreux scénarios, `_traced` est remplacé dans le seul processus E2E, pour les seules requêtes marquées `[quota0]`.

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest tests/test_net_factory.py tests/test_cloud.py tests/test_web_app.py tests/test_e2e_fake_openai.py tests/test_ui_texts.py -q`, puis la suite en quarts -- expected: tout vert
- `PYTHONIOENCODING=utf-8 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only markdown diagnostic_wait provider_errors panes disciplines network_tools` -- expected: aucun FAIL ; puis `git checkout tools/e2e/screenshots && git clean -fd tools/e2e/screenshots`
