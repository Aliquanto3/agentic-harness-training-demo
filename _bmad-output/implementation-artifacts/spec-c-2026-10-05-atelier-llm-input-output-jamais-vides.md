---
title: 'Correction C du 2026-10-05 — Atelier LLM : INPUT et OUTPUT jamais vides'
type: 'bugfix'
created: '2026-10-05'
status: 'done'
baseline_commit: 'd239b094e8b10bebdae0f13d878532dea1626d34'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-lot-6-atelier-llm-boucle-du-modele.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/mockups/llm-loop.html'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sur `/llm`, la maquette validée montre dès l'ouverture le découpage progressif de l'INPUT (◀ ▶) et, dans l'OUTPUT, les graphiques Logits et Tirage qui suivent température, top-k, top-p et min-p. L'application n'affiche que des données réelles : pas de colonnes sans tokenisation exacte, pas de barres avant un pas avec candidats, réglages grisés en cloud. Avec un modèle cloud (cas d'Anaël : Gemma chez Google AI Studio), ou en local avant deux clics, les deux étapes restent vides.

**Approach:** « Exemple étiqueté » (décision d'Anaël). (a) Moteur local en processus (tokenizer exact, candidats disponibles), session au repos : au chargement, la page fait découper le texte du champ puis tirer un premier pas, pour des valeurs réelles sans clic. (b) Sinon (cloud, serveur, ou avant tout pas réel) : la session sert un exemple, des tokens et identifiants d'exemple pour l'INPUT (`stages.transfo.example_tokens` + identifiants) et une distribution d'exemple pour l'OUTPUT (nouveau bloc `stages.output.example`, six mots, probabilités, reste du vocabulaire), passée par les mêmes `candidates.distribution`/`dropped_by` côté Python (AD-1). Le badge passe de « Réel » à « Exemple ». Les réglages de l'OUTPUT sont modifiables partout et bougent les barres de l'exemple ; la raison du fournisseur reste dite pour le tirage réel. En cloud, l'estimation « ≈ N tokens » du texte tapé reste à côté de l'exemple, qui ne se présente pas comme le découpage du modèle.

**Décisions prises en autonomie (Anaël injoignable, option recommandée) :**
- Exemple de l'OUTPUT cohérent avec celui de l'INPUT : les candidats qui suivent les tokens d'exemple déjà livrés (« Bonjour, comment allez-vous » en fr, « Hello, how are you », « Guten Tag, wie geht »), pas « Le chat dort sur le » de la maquette.
- Découpage et pas automatiques seulement pour le moteur en processus (tokenizer exact et candidats disponibles), une fois par chargement, session `idle` sans raison, aucun texte encore découpé ; le pas automatique n'a lieu que si la session ne garde aucune distribution (une génération précédente reste montrée) ; le texte est celui du champ (brouillon ou texte par défaut) ; l'étape OUTPUT reste au pas 1.
- Les réglages B de la comparaison (section 6) restent grisés en cloud : ils ne pilotent aucun graphique.
- Un réglage non pris par le fournisseur garde sa raison, suivie de « il ne bouge que l'exemple ».

## Boundaries & Constraints

**Always:** AD-1 : la page ne calcule aucune probabilité ni chance et ne tire aucun token ; l'exemple de l'OUTPUT est calculé par la session (`candidates.distribution`, `dropped_by`) ; textes dans `content/llm_lab.yaml` + `content/i18n/{en,de}/llm_lab.yaml` (parité) ; ids et classes existants conservés (`#token-chips .token-chip`, `#distribution-body`, `#distribution-empty`, `#distribution-bars .dist-row`, `#logits-bars`, `.sampling-row-reason`…) ; le tirage réel envoie toujours `samplingToSend()` (valeurs du harnais pour un réglage non pris) ; jetons de `tokens.css` seulement ; dans `app_session.py`, seulement la partie Atelier LLM.

**Never:** modifier `tokens.css`, `models/candidates.py`, la partie clé API/chargement cloud ou rag d'`app_session.py`, `app.js`, `rag.js`, `rag/lab.py` ; présenter l'exemple comme lu dans le modèle ; tirer automatiquement hors moteur en processus ; lancer un serveur sur 8420 ou charger un GGUF réel ; pousser, fusionner.

## I/O & Edge-Case Matrix

| Scénario | État | Attendu | Erreur |
|----------|------|---------|--------|
| Local en processus, 1er chargement | `idle`, tokenizer exact, candidats dispo, rien de gardé | `llm_tokenize` puis `llm_step` envoyés une fois ; colonnes et barres réelles, badges « Réel » | pas refusé : statut d'erreur habituel, l'exemple reste |
| Local, session occupée ou distribution gardée | état ≠ `idle`, ou `distribution.tokens > 0` | rien d'automatique ; barres gardées réelles, sinon exemple | — |
| Cloud, 1er chargement | tokenizer approché, candidats indisponibles | INPUT : 5 colonnes d'exemple, badge « Exemple », note ; OUTPUT : barres d'exemple, badge « Exemple », raison du fournisseur | — |
| Cloud, texte découpé | `exact = false` | colonnes d'exemple + « ≈ N tokens » + note « pas le découpage du modèle » | — |
| Cloud, réglage non pris | `supported[top_k]` = raison | curseur actif, barres d'exemple redessinées (« écarté (top-k) »), raison visible ; « Générer » envoie la valeur du harnais | — |
| Serveur (llama-server) | tokenizer exact, candidats indisponibles | INPUT exemple puis réel après « Découper » ; OUTPUT exemple + raison | — |
| Route d'exemple | `POST /api/llm_lab/example_distribution` | même forme que `/distribution` + `example: true`, `token_text: null`, en tout état, sans modèle | contenu invalide : 404 ; bornes : 422 |
| Pas réel puis « Ajouter à la suite » | distribution oubliée | OUTPUT repasse à l'exemple, badge « Exemple » | — |

</frozen-after-approval>

## Code Map

- `src/wavestack/session/llm_lab.py` -- `TransfoStage` (l.~338) : `example_ids: list[int]`, validateur « même longueur qu'`example_tokens` » ; `InputStage` (l.~260) : `example_tag_text`, `example_text`, `example_cloud_text` ; `OutputStage` (l.~369) : `example: OutputExample` (nouveaux `ExampleCandidate {text, p}` et `OutputExample {tag_text, note_text, unsupported_text, candidates (6, décroissants), tail}`, somme + reste ≈ 1).
- `src/wavestack/session/app_session.py` -- `llm_distribution` (l.~8854) : ajoute `"example": False` ; nouvelle `llm_example_distribution(sampling)` juste après : contenu via `_lab_content()`, `distribution(...)` et `dropped_by(...)` déjà importés ; `DistributionMissing` si contenu illisible.
- `src/wavestack/web/app.py` -- `LlmExampleDistributionRequest {sampling}` après `LlmDistributionRequest` (l.~227) ; route `POST /api/llm_lab/example_distribution` après `/api/llm_lab/distribution` (l.~524), 404 sur `DistributionMissing`. Chemin distinct : les `page.route("**/api/llm_lab/distribution")` des E2E ne l'interceptent pas.
- `src/wavestack/web/static/llm.html` -- tags `#input-tag`, `#output-tag` (sans `data-text`) ; `<p class="llm-note" id="token-example" hidden>` après `#token-bos`.
- `src/wavestack/web/static/llm.js` -- `inputExample()` + `renderInput` (l.~294 : colonnes d'exemple `is-example`, badge, note, compteurs inchangés) ; `transfoModel` (l.~460) prend les `example_ids` ; `samplingRow` (l.~964) : champs compacts jamais `disabled`, raison + `unsupported_text` ; `renderDistributionIdle` (l.~1107) → demande l'exemple (`fetchExample`, même `ticket`, valeurs brutes des curseurs) ; `renderDistribution` (l.~1179) : mode exemple (badge, légende des Logits sur les tokens d'exemple, pas de `is-chosen` ni de puce marquée, `#distribution-empty` = `note_text` + raison ou `distribution.empty_text`) ; `autoStart()` appelée dans `main()` avant `streamEvents`, reprise dans `renderTokenized` (`store.auto`), `stepEvent` ne déplace pas l'étape OUTPUT pour le pas automatique ; `applyEnvelope` (`session_state` `llm_lab`) n'efface pas les barres pendant notre propre pas.
- `src/wavestack/web/static/llm.css` -- `.llm-stage-tag.is-example` (comme `is-illustrative`), colonnes `is-example` en pointillés.
- `content/llm_lab.yaml`, `content/i18n/{en,de}/llm_lab.yaml` -- clés ci-dessus.
- `tests/test_llm_lab.py` -- tests en fin de fichier.
- `tools/e2e/run_e2e.py` -- `_llm_loop_cloud` (l.~12749), `_llm_loop_output` (l.~12988, 13062), `_LoopLab.tokenize` (compte les appels), nouveau `_llm_loop_first_load` ; vérifications de l'ancien état vide à mettre à jour : `_llm_screen` (l.~11778, 11812), `_distribution_unavailable` (l.~12011), `_llm_live` (l.~12426).
- `_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/EXPERIENCE.md` (l.~106-109, 154-160) et `notes-de-fusion.md`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/session/llm_lab.py` + les trois `llm_lab.yaml` -- modèles et textes d'exemple -- l'exemple vient du contenu.
- [x] `src/wavestack/session/app_session.py`, `src/wavestack/web/app.py` -- `llm_example_distribution` et sa route -- AD-1.
- [x] `src/wavestack/web/static/llm.html`, `llm.js`, `llm.css` -- exemple étiqueté, curseurs actifs, démarrage automatique.
- [x] `tests/test_llm_lab.py` -- contenu valide (3 langues, ids alignés, 6 candidats), exemple = `distribution`/`dropped_by` pour plusieurs réglages, en cloud, sans modèle et hors `idle`, route 200/422, `example` faux sur `/distribution`.
- [x] `tools/e2e/run_e2e.py` -- scénarios ci-dessus.
- [x] `EXPERIENCE.md`, `notes-de-fusion.md` -- états « avant toute tokenisation », « serveur ou cloud », flux 2, fichiers carrefour.

**Acceptance Criteria:**
- Given un modèle cloud, when `/llm` s'ouvre, then l'INPUT montre 5 colonnes d'exemple que ◀ ▶ découpent pas à pas, l'OUTPUT montre Logits et Tirage d'exemple, badges « Exemple », et bouger top-k redessine les barres.
- Given un moteur en processus simulé au repos, when `/llm` s'ouvre, then sans clic les colonnes réelles et les barres réelles du pas apparaissent, badges « Réel ».
- Given la suite E2E LLM (`llm_loop`, `llm_screen`, `llm_live`), when elle tourne, then tout passe sans erreur JavaScript.

## Implementation Notes

- Point d'arrêt 1 (approbation de la spec) : « Approve and continue » pris en autonomie, Anaël injoignable (travail en sous-agents parallèles).
- Step-03 : implémenté directement par l'agent qui a fait l'investigation, sans sous-agent d'implémentation (machine partagée de 16 Go avec deux autres agents ; contexte déjà chargé).
- Fin de ligne : `sed -i` avait passé `llm.html` en LF, ce qui cassait `test_every_page_opens_on_the_same_shared_bar` ; CRLF rétabli.
- Distribution déjà gardée par la session : rien d'automatique (ni découpage ni pas), comme le dit la matrice ; les barres réelles restent.
- Hauteur à 1366 × 768 (règle du DESIGN.md du lot 6) : en cloud, l'exemple ajoutait ~110 px à l'OUTPUT (802 px). Corrigé sans toucher au réel (761 px) : la note de l'exemple et la raison des candidats passent sous le graphique du Tirage (`#distribution-note`, place libre à côté des réglages), la raison n'est plus répétée dans `#llm-step-status` (le titre de « Tirer » la garde), les raisons des réglages de l'OUTPUT passent en taille « label », `unsupported_text` raccourci (« Il ne bouge que l'exemple. »). Cloud : 756 px. Vérifié par un E2E (`_llm_loop_example`).
- Découpage ou pas automatique refusé (409) : `store.auto` revient à `null`, le statut d'erreur habituel s'affiche, l'exemple reste.
- E2E : les vérifications de l'ancien état vide (graphiques masqués, top-k grisé en cloud, aucune colonne en cloud, raison sous « Tirer ») sont réécrites pour le nouvel état ; captures `75-llm-boucle-premier-chargement`, `76-llm-boucle-exemple-cloud` ajoutées, captures LLM 52-54, 64, 65, 70-74 régénérées.

- Vérification finale : ruff propre (src, tests, run_e2e) ; pytest `test_llm_lab`, `test_i18n`, `test_web_app`, `test_ui_texts`, `test_web_tokens`, `test_annex_language` : 348 réussis ; E2E `llm_loop llm_screen llm_live` en une passe : 109/109. Une passe antérieure de `llm_screen` a échoué une fois sur l'attente d'un `llm_token` du faux llama-server (20 s, machine chargée par deux autres agents), puis a réussi seule et dans la passe finale. Suite complète et `annex_language` non lancées (consigne : machine partagée).
- Point ouvert pour Anaël : à chaque ouverture de `/llm` avec un GGUF chargé au repos, la page fait tirer un token (coût CPU d'un pas, quelques secondes) ; rien ne dit à l'écran que ce premier pas est automatique. Correction E du 2026-10-05 : ce premier pas ne tire plus de token, la session lit seulement les candidats du token suivant (coût CPU d'une évaluation, sans tirage) ; la page dit « Le moteur lit les probabilités du token suivant, sans en tirer… » pendant la lecture.

## Spec Change Log

## Review Triage Log

Revue (step-04, 3 relecteurs : blind, edge-case, verification-gap) : 21 constats, aucun intent_gap ni bad_spec ; 13 corrigés par patch, 8 rejetés. Point d'arrêt de revue tranché en autonomie (option recommandée : appliquer les patchs).

| # | Source | Constat | Verdict | Preuve | Route |
| --- | --- | --- | --- | --- | --- |
| 1 | blind, edge, verif | Pas fini sans token (fin, erreur, Arrêter, texte modifié) : les anciennes barres restent « Réel » | medium | branche `session_state` `llm_lab` + pas en attente ne redessine plus ; `llm_generation_ended` ne redessinait rien | patch (retour à l'exemple ; E2E `_llm_loop_end`) |
| 2 | edge | Minuterie d'un curseur en attente au début du pas : clignotement vers l'exemple | low | `scheduleDistribution` → `fetchDistribution` avec `tokens = 0` | patch (`clearTimeout`) |
| 3 | edge | Découpage automatique échoué par `harness_error` : `store.auto` reste « tokenize », un découpage manuel tire un pas | low | branche `harness_error` sans remise à zéro | patch |
| 4 | edge | Un `llm_tokenized` d'un autre onglet consomme le démarrage automatique | low | possible mais rare ; la correction ajoute un état (id attendu) | rejet |
| 5 | edge | Contenu illisible : `[]` vrai, badge « Exemple » sur zéro colonne | low | `inputExample` | patch |
| 6 | edge | `example_tokens` vide accepté par le validateur | low | `_ids_match_tokens` | patch (+ test) |
| 7 | blind | Rechargement avec distribution gardée : état mixte non décrit | low | INPUT exemple, OUTPUT réel ; conforme à la matrice | patch (ligne d'état dans EXPERIENCE.md) |
| 8 | blind | En mode exemple, « probabilité du modèle », `kept_text` parlent comme du réel | low | badge « Exemple » et note sous le graphique ; des variantes ajouteraient textes et branches | rejet |
| 9 | blind | Allemand : légende « , wie geht », candidat « ␣'s » | low | `slice(-3)`, `" 's"` | patch (texte d'exemple entier, `'s`) |
| 10 | blind | Raison de « Tirer » seulement dans le `title` d'un bouton grisé | low | statut vidé quand la note la dit | patch (`aria-describedby` vers la note) |
| 11 | blind | Note `role="status"` réécrite à chaque curseur | low | `textContent` réassigné | patch (`setNote` si le texte change) |
| 12 | blind | Spec en retard sur le code (Code Map, journal vide) | low | correction = éditer la spec | rejet (écarts dans les Implementation Notes) |
| 13 | blind, verif | Tests manquants : route sans modèle, ids négatifs, bornes de `p` et `tail`, tolérance | low | tests absents | patch (tests ajoutés) |
| 14 | verif, blind | E2E : session occupée, pas automatique refusé, llama-server sans démarrage automatique | medium | aucun scénario | patch (`_llm_loop_first_load`, `_llm_screen`) |
| 15 | verif | Branche « pas de clignotement » jamais exécutée | medium | aucun `session_state` simulé | patch (`_llm_loop_end` envoie `llm_lab` puis `idle`) |
| 16 | blind | Attentes fixes dans les E2E (1,5 s, 0,6 s) | low | prouver une absence demande une attente ; usage du fichier | rejet |
| 17 | blind | Commandes de vérification trop étroites | low | correction = éditer la spec ; suites plus larges lancées (Verification ci-dessous) | rejet |
| 18 | blind | Le pas automatique n'est pas signalé, coût CPU à chaque visite | false | voulu par la décision (a) d'Anaël ; laissé en point ouvert | rejet |
| 19 | blind | Colonnes d'exemple et produites : même bordure pointillée | low | `dashed` des deux côtés | patch (`dotted` pour l'exemple) |
| 20 | blind | 404 pour un contenu illisible | low | même correspondance que `/distribution`, la page l'affiche | rejet |
| 21 | blind | Restes : `#token-empty`, citation incomplète, « ci-contre », 6 en dur | low | `#token-empty` reste le repli sans contenu ; citation corrigée ; le reste cosmétique | patch (citation) / rejet (le reste) |

## Design Notes

L'exemple de l'OUTPUT passe par une route à part plutôt que par un drapeau de `/distribution` : les E2E qui simulent `/distribution` (`_LiveLab`, `_LoopLab`) et la mémoire de la session restent inchangés, et la page demande l'exemple seulement quand rien de réel n'est montrable. Valeurs envoyées pour l'exemple : celles des curseurs (bornées), pas `samplingToSend()`, sinon un réglage non pris en cloud ne bougerait rien.

## Verification

**Commands:**
- `uv run ruff check` et `uv run ruff format --check` sur les fichiers touchés -- aucun écart
- `uv run pytest -q tests/test_llm_lab.py tests/test_i18n.py` -- tout vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only llm_loop llm_screen llm_live` -- tout vert
