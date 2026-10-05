---
title: 'Correction D du 2026-10-05 — Atelier LLM : premier pas automatique sans tirage montré, texte de l''INPUT sans écart'
type: 'bugfix'
created: '2026-10-05'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-c-2026-10-05-atelier-llm-input-output-jamais-vides.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/mockups/llm-loop.html'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Deux défauts de `/llm` vus en recette pilotée après la correction C. (1) Local, GGUF chargé, session au repos : le pas automatique du premier chargement tire un token, mais la carte « Token tiré » dit à la fois « aucun token tiré pour l'instant » et « derniers tirages : ↵↵ », la légende des Logits « Candidats du token tiré par le moteur : « ↵↵ » » et le pas 1 de l'OUTPUT « Le modèle n'a encore rien choisi ». (2) Cloud : à l'étape 1 de l'INPUT (texte d'un bloc), l'exemple « Hello, how are you » s'affiche « Hello , how are you » : un écart avant la virgule (fr et de aussi).

**Approach:** (1) Option « lecture des probabilités » : le pas automatique sert seulement à lire les candidats réels ; la page ne montre aucun tirage (ni puce, ni « derniers tirages », ni légende ou ligne marquée du token tiré, « Ajouter à la suite » grisé), seul « 🎲 Tirer le token suivant » tire un token visible. Plus généralement, la légende « Candidats du token tiré par le moteur » et la ligne `is-chosen` d'un pas ne s'affichent que lorsque la puce du token tiré est montrée (un réglage bougé les efface avec elle, comme dans la maquette). (2) Cause : chaque colonne de l'INPUT est une grille `justify-items: center` dont la largeur est celle de sa ligne la plus large ; à l'étape 1, la puce et l'identifiant sont masqués (`visibility: hidden`) mais gardent leur largeur, si bien qu'un morceau étroit (« , », « ? ») est centré dans une colonne plus large. Correctif CSS : tant que l'INPUT n'est pas découpé (`:not(.is-cut)`), les lignes masquées ne comptent pas dans la largeur (`max-width: 0`) ; les colonnes ont la largeur de leur texte, le texte se lit d'un bloc, les espaces viennent des tokens (« ␣how »).

**Décisions prises en autonomie (Anaël injoignable, option recommandée) :**
- Option « lecture » plutôt que « tirage » pour le pas automatique : la maquette ne tire rien avant le clic sur « Tirer », l'EXPERIENCE.md ouvre l'OUTPUT sur les Logits (« Le modèle n'a encore rien choisi »), la spec C voulait des « valeurs réelles sans clic » (les barres), pas un tirage, et son point ouvert (« rien ne dit que ce premier pas est automatique ») disparaît : rien n'est présenté comme tiré.
- Après un tirage montré, bouger un réglage garde « derniers tirages : … » à côté de « aucun token tiré pour l'instant » : c'est la règle de la maquette (`drawnIndex = null`, historique gardé) ; seuls la légende et le marquage du token tiré partent avec la puce.
- Pas automatique fini sur une fin sans token ou sur le token de fin : retour à l'exemple, sans phrase « Le moteur a tiré son token de fin » (rien n'est montré tiré) ; une erreur ou un arrêt gardent leur statut habituel.
- Correctif d'écart en CSS seulement (aucun texte ni token d'exemple n'avait d'espace en trop) : vaut pour fr, en, de et pour un vrai découpage.

## I/O & Edge-Case Matrix

| Scénario | État | Attendu | Erreur |
|----------|------|---------|--------|
| Local, 1er chargement, pas automatique | `llm_token` du pas automatique | barres réelles, badge « Réel », OUTPUT au pas 1 ; « aucun token tiré pour l'instant », pas de « derniers tirages », `#distribution-token` vide, aucune ligne `is-chosen`, « Ajouter » grisé | pas refusé : statut d'erreur, l'exemple reste |
| Puis « Tirer » au clic | `llm_token` manuel | puce, « derniers tirages : … », légende du token tiré, ligne `is-chosen`, OUTPUT au pas 3 | — |
| Puis un réglage bougé | puce effacée | barres redemandées ; légende vide, aucune ligne `is-chosen` ; « derniers tirages » gardé | — |
| INPUT pas 1, exemple cloud ou découpage exact « Hello, how are you? » | `:not(.is-cut)` | chaque morceau collé au suivant (aucun écart avant « , » ni « ? ») | — |
| INPUT pas 2 et 3 | `.is-cut` | colonnes écartées de 26 px, largeur des puces et identifiants (inchangé) | — |

</frozen-after-approval>

## Implementation Notes

- Route `oneshot` (aucun intent gap, rien d'irréversible, 4 fichiers). Les deux défauts sont gardés dans une seule spec, à la demande ; le point « multi-objectif » de step-01 est tranché en « Keep all goals », Anaël injoignable.
- Défaut 1, `src/wavestack/web/static/llm.js` : `stepEvent` (`llm_token`) ne remplit ni `step.drawn` ni `step.history` quand `store.auto === "step"` ; `llm_generation_ended` garde les barres du pas automatique (`(!auto && !drawn) || !dist.tokens`) et n'écrit aucun statut de fin pour lui ; `renderDistribution` calcule `chosen` (null en exemple, ou pour un pas sans puce montrée) qui commande `#distribution-token` et `is-chosen` ; nouvelle `unmarkStepToken()` appelée par `clearDrawn` et au `llm_generation_started` d'un pas (légende et marquage effacés tout de suite, sans attendre les barres redemandées).
- Cause exacte de « aucun token tiré » + « derniers tirages : ↵↵ » non reproduite sans GGUF réel : seul `clearDrawn` (un réglage bougé) vide la puce en gardant l'historique ; avec l'option « lecture », le pas automatique ne remplit plus ni l'une ni l'autre, quel que soit l'enchaînement.
- Défaut 2, `src/wavestack/web/static/llm.css` : premier essai avec `max-width: 0` seul, encore 5,7 px d'écart mesurés : le padding (`--spacing-2`) et la bordure de la puce masquée gardaient sa largeur. Ajout de `padding-inline: 0` et `border-inline-width: 0` sur les lignes masquées tant que l'INPUT n'est pas découpé. Aucun texte d'exemple n'avait d'espace en trop : rien à changer dans les trois `llm_lab.yaml`.
- E2E (`tools/e2e/run_e2e.py`) : `_llm_loop_first_load` vérifie que le pas automatique ne montre rien de tiré, puis qu'un pas au clic montre puce, « derniers tirages », légende et ligne marquée ; `_llm_loop_output` vérifie qu'un réglage bougé efface légende et marquage en gardant « derniers tirages » ; nouveau `_llm_loop_gaps` (découpage exact simulé de « Hello, how are you? ») et contrôle des écarts dans `_llm_loop_example` (exemple cloud fr) avec `_SEG_GAPS_JS`. Le correctif CSS ne dépend pas de la langue : en et de ne sont pas rejoués en E2E.
- `EXPERIENCE.md` du lot 6 : état « Premier chargement », composants INPUT et « OUTPUT · Token tiré » mis à jour.
- Fins de ligne : `sed -i` de Git Bash passe les fichiers en LF ; CRLF rétabli dans la copie de travail de `llm.js` et `run_e2e.py`.
- Vérification : avant le correctif CSS, l'E2E échouait sur les deux contrôles d'écart (`[5.7, 5.8, 0, 0, 2.3]`, `[6.7, 6.8, 0, 0]`) ; ensuite `llm_loop` 67/67, `llm_screen llm_live` 62/62 ; pytest `test_llm_lab`, `test_ui_texts`, `test_i18n`, `test_web_app`, `test_web_tokens` : 318 réussis, 1 désélectionné ; ruff propre sur `run_e2e.py`.
- Après la revue (patchs ci-dessous) : `--only llm_loop llm_screen llm_live` en une passe, 114/114 ; seule entrée console, le 409 attendu du pas refusé. Une passe intermédiaire a cassé les trois scénarios (`shown` déjà déclaré dans `renderDistribution`), renommé en `named`.
- Captures : seules les captures LLM (52-54, 64, 65, 70-76) sont gardées ; `01-diagnostic…` restaurée, `01b-diagnostic-cartes.jpg` et les `echec-*.jpg` supprimées.
- Point ouvert pour Anaël : le pas automatique reste un vrai `llm_step` côté session (un token est tiré par le moteur et le journal du Harnais le montre) ; la page le présente comme une lecture des probabilités. Un mode « candidats seuls » de la session l'éviterait (hors de cette correction, qui ne touche pas `app_session.py`).
- Les colonnes passent d'un coup de la largeur du texte à celle des puces au pas 2 (la `column-gap` reste animée) : écart assumé par rapport à la maquette, dont les colonnes ont déjà la largeur des puces au pas 1.

## Review Triage Log

Revue (Blind Hunter, sous-agent sans contexte) : 15 constats ; 6 corrigés par patch, 9 rejetés. Point d'arrêt de revue tranché en autonomie (option recommandée : appliquer les patchs).

| # | Constat | Verdict | Preuve / raison | Route |
| --- | --- | --- | --- | --- |
| 1 | Rechargement avec distribution gardée : `source` vaut « generation », la légende nomme le token du pas automatique et marque sa ligne | medium | `refresh()` ne remet pas `source` ; `chosen` ne filtrait que `step` | patch (`named` : une génération n'est nommée que si sa puce de section 6 existe) |
| 2 | L'E2E de rechargement ne vérifie ni légende ni marquage | medium | même cause | patch |
| 3 | Le pas automatique reste un vrai tirage côté session, montré par le journal du Harnais | low | `llm_step` inchangé | rejet (dit en point ouvert ; correction côté session hors périmètre) |
| 4 | Spec inachevée | false | route `oneshot` : sections réduites par le gabarit ; notes et vérification remplies ensuite | rejet |
| 5 | EXPERIENCE.md : ligne « OUTPUT · Logits » et ligne de rechargement non mises à jour | low | texte | patch |
| 6 | Branches de fin du pas automatique (token de fin, aucun token) sans E2E | low | rare (token de fin en premier) ; demande un nouveau faux flux | rejet |
| 7 | « Tirer » au clic testé après un pas automatique refusé seulement | low | même chemin de code (`auto` nul) | rejet |
| 8 | La mesure d'écart inclut le `padding: 0 1px` des morceaux | false | padding de la maquette, 2 px entre deux morceaux quels qu'ils soient ; l'écart corrigé venait de la largeur de la colonne | rejet |
| 9 | Contenu masqué de largeur 0 qui déborde : défilement horizontal possible | low | `visibility: hidden` compte dans le débordement | patch (`overflow: hidden`) |
| 10 | Largeur des colonnes qui saute au pas 2 | low | cosmétique | rejet (noté ci-dessus) |
| 11 | Captures du diagnostic dans le lot | low | — | patch (restaurées, non commitées) |
| 12 | en et de non rejoués ; `len(gaps) == 4` en dur | low | correctif CSS indépendant de la langue | patch (compte tiré du contenu) / rejet (en, de) |
| 13 | Deux classes (`is-cut`, `show-tokens`) pour un même état | low | `showInputStep` les bascule ensemble | patch (règle sur `:not(.show-tokens)`, comme la règle de visibilité) |
| 14 | Priorité d'opérateurs de `chosen` peu lisible | low | — | patch (réécrit avec `named`) |
| 15 | Le badge « Réel · probabilités et tirage » sans tirage montré | false | le badge décrit l'étape, pas un tirage fait | rejet |
