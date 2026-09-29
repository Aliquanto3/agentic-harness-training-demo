---
title: 'Retours de recette : briques, volets et tiroirs'
type: 'bugfix'
created: '2026-09-28'
status: 'done'
baseline_revision: '9187b55d436693884ce7ef240e26a6a405a6e845'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/retours-recette-palier-2-2026-09-28.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/tools/e2e/README.md'
warnings:
  - oversized
deferred:
  - summary: >-
      Raison d'une sous-option grisée inaccessible au clavier (interrupteur `disabled`, raison en `title`).
    evidence: |-
      markParentOff pose disabled, qui sort l'interrupteur de l'ordre de tabulation ; aria-description mal pris en charge par Narrateur.
    location: >-
      src/wavestack/web/static/app.js (markParentOff)
    severity: low
  - summary: >-
      Onglets du Contexte LLM sans navigation aux flèches (motif ARIA tablist incomplet).
    evidence: |-
      Décision par défaut de la spec ; les lecteurs d'écran annoncent « onglet » et les flèches ne font rien.
    location: >-
      src/wavestack/web/static/app.js (ctxViewSwitch)
    severity: low
  - summary: >-
      Identifiant de journal t{n} lisible seulement au survol du titre de tour.
    evidence: |-
      title sur un span de l'en-tête Orchestration ; aucun texte équivalent au clavier.
    severity: low
  - summary: >-
      Règles de numérotation « Tour N » non testées après changement de modèle et après rechargement suivant un vidage.
    evidence: |-
      Le parcours E2E ne vérifie « Tour 1 » qu'après Réinitialiser et Vider la conversation.
    severity: low
  - summary: >-
      Boutons Forcer (documentation MCP, skill…) actifs quand leur brique est éteinte.
    evidence: |-
      Hors périmètre par décision de la story ; même confusion que X1.
    severity: low
  - summary: >-
      Frontmatter des composants de DESIGN.md en retard sur la prose (croix du tiroir, consigne repliée, onglets, ligne d'état).
    evidence: |-
      Seuls button-danger et brick-toggle.parent-off ont été ajoutés au frontmatter.
    severity: low
---

<intent-contract>

## Intent

**Problem:** La recette du 2026-09-28 (C1, M1, M3, M6, X1) relève huit défauts d'interface : Raisonnement enfoui au 4e rang, sous-options (Reranking, Lazy loading, interrupteurs d'outils, serveurs, skills, hooks) actives et violettes alors que la brique parente est éteinte, consigne du scénario qui mange la Vue humain, tiroir de la mémoire sans croix et boutons de fin hors de vue et indistincts, « Enregistrer » du prompt système muet, « Annuler » d'un formulaire forcé sans effet, bascule de contexte du sous-agent peu lisible, numéro de tour qui continue après « Vider la conversation » / « Réinitialiser ».

**Approach:** Corrections d'affichage seulement : réordonner la déclaration des briques, dériver l'état « parente éteinte » des cartes déjà envoyées par `bricks_changed`, revoir trois éléments d'interface (consigne, tiroir mémoire, tiroir prompt système), corriger la sentinelle de `renderBricks`, passer la bascule en onglets et calculer un numéro de tour par conversation côté affichage. Le harnais, ses événements et ses identifiants ne changent pas.

## Boundaries & Constraints

**Always:**
- Textes d'interface en français ; code et identifiants en anglais ; `uv`, `ruff`, `pytest` (CLAUDE.md).
- L'état affiché vient des événements (AD-1) : « brique parente éteinte » = `!(brick.always_fr || (brick.wanted && brick.available))`, calculé sur la carte reçue.
- Identifiants `t{n}` inchangés et uniques pour la session (journal, traces, `step_id`) ; le numéro affiché « Tour N » est le rang du tour depuis le dernier `conversation_cleared` ou `harness_reset`.
- Couleurs par tokens existants de `tokens.css` (`--color-danger`, `--color-muted`, `--color-ink`…) ; aucun token nouveau (le test `tests/test_web_tokens.py` les compare à DESIGN.md).
- Mettre à jour EXPERIENCE.md et DESIGN.md pour chaque comportement décrit qui change ; ajouter au parcours E2E (`tools/e2e/run_e2e.py`) une vérification par point d'interface ; mettre à jour les captures touchées.
- Ne casser aucune story livrée : `uv run pytest -q` complet vert, parcours E2E sans FAIL.

**Never:**
- Aucune dépendance nouvelle ; aucun vrai modèle dans le conteneur (doublures du dépôt : faux moteur, faux serveurs `tools/e2e`, GGUF synthétiques, faux fournisseurs).
- Ne pas changer l'API HTTP, les charges des événements, `_rerank_availability`, ni l'acceptation des intentions par la session (une sous-option reste réglable par l'API brique éteinte).
- Pas de regroupement des briques en deux familles ni de refonte visuelle (stories 33 et 34), pas de lecture du contexte revue (story 32).
- Ne pas toucher aux boutons Forcer ni au bouton « Télécharger » du reranker, hors bug « Annuler ».

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Parente éteinte | Carte RAG `wanted:false`, `rerank.enabled:true` | Interrupteur Reranking coché mais grisé (fond `--color-muted`), désactivé ; infobulle « Activez la brique RAG pour régler cette option. » | Aucun appel API possible depuis l'interface |
| Parente indisponible | Carte `wanted:true`, `available:false` (ex. outils sans parser) | Sous-options grisées ; infobulle = `reason_fr` de la brique | — |
| Raisonnement imposé | `always_fr` non vide | Brique considérée active : sous-options (s'il y en a) actives | — |
| Parente rallumée | `bricks_changed` avec `wanted:true` | Sous-options de nouveau actives, état coché conservé | — |
| MCP éteint, lazy | Carte MCP `wanted:false`, `mode:"lazy"` | Résumé « Serveurs : n activés sur m · brique éteinte », grisé ; interrupteur Lazy loading désactivé | — |
| Consigne courte | Description tenant en ≤ 3 lignes | Aucun bouton « Afficher plus » | — |
| Consigne longue | `soc` (1 276 caractères) | 3 lignes puis « Afficher plus » (`aria-expanded=false`) ; clic : texte entier, « Réduire » | Nouveau scénario : repli |
| Prompt inchangé | Texte du tiroir = `system_prompt.text` | « Enregistrer » désactivé | — |
| Enregistrement OK | Texte modifié puis « Enregistrer » | Ligne `role=status` « Prompt système enregistré. », bouton de nouveau désactivé | Échec : alerte existante, pas de confirmation |
| Annuler / re-clic | Formulaire forcé ouvert, clic « Annuler » ou re-clic sur son bouton | Formulaire fermé, focus sur le bouton Forcer | — |
| Tours après remise à zéro | t1, t2, t3 puis « Réinitialiser », puis un envoi | Orchestration « Tour 1 » ; journal `turn_id:"t4"` | — |

</intent-contract>

## Code Map

- `src/wavestack/bricks/registry.py:33-228` -- `BRICKS` ; `reasoning` en 4e (l. 72-85, commentaire compris). L'ordre ne sert qu'à l'affichage : `bricks_changed` (`app_session.py:1234`), nœuds de `architecture_changed` (l. 954-960), ordre de chargement du contenu (l. 1782). Le contexte ne parcourt pas `BRICKS` ; les scénarios (FR-38) portent leurs propres listes (`content/scenarios.yaml`, `tests/test_program.py:171-173`).
- `src/wavestack/session/app_session.py:669, 3266-3267, 4316, 4427-4467` -- `self._turns` et `turn_id = f"t{n}"`, jamais remis à zéro par `clear_conversation` ni `reset`/`_reconfigure` : à garder.
- `src/wavestack/session/app_session.py:2266-2295, 2303-2324` -- `_rerank_availability` (vrai quand RAG non voulu) et `_rerank_card` : à ne pas changer, l'interface combine avec l'état de la carte.
- `src/wavestack/web/static/app.js:809-833` -- `renderedForceUi`, `forceUiChanged` (met `null`), garde de `renderBricks` : `null === null` quand `store.forceForm` redevient `null`, donc pas de reconstruction. Sites : bouton Forcer l. 1209-1211, `cardForce` l. 1228-1231, « Annuler » l. 1343-1348, préréglage l. 1301-1306.
- `src/wavestack/web/static/app.js:862-932` -- boucle des cartes (`always`, `is-active`) ; appels de `rerankParts` (l. 887) et `brickOptions` (l. 897).
- `src/wavestack/web/static/app.js:1008-1044` -- `rerankParts` (désactivé seulement si `!available && !enabled`).
- `src/wavestack/web/static/app.js:1060-1114` -- `brickOptions` : résumé (l. 1070-1075), interrupteurs (l. 1078-1097), Lazy loading (l. 1102-1113).
- `src/wavestack/web/static/app.js:1473-1515, 5204-5210` -- tiroir du prompt système : `drawerAlert`, `openDrawer`, `closeDrawer`, `saveSystemPrompt`, liaisons.
- `src/wavestack/web/static/app.js:1545-1690, 5213-5223` -- mémoire globale : `memoryAlert`, `askClearMemory`, `openMemoryDrawer`, `closeMemoryDrawer`, `renderMemoryDrawer` (boutons d'entrée l. 1649-1665), liaisons.
- `src/wavestack/web/static/app.js:2228-2282` -- `renderScenarioControls` : consigne (`guide.replaceChildren(strong, description)` l. 2269-2270), `renderedGuide`.
- `src/wavestack/web/static/app.js:66-68, 286-288, 2417-2432, 2518-2539, 3650-3657` -- `store.ctxView`, `turn_started`, `renderContextBody`, `ctxViewSwitch` (boutons `aria-pressed`), `showSubContext`.
- `src/wavestack/web/static/app.js:804, 2571, 3940-3960` -- `shownTurns`, `turnName` (« Tour » + rang depuis le lancement), titre des groupes d'Orchestration (`Tour ${index + 1}`, `index = store.chatFrom + i`).
- `src/wavestack/web/static/index.html:48-81, 108` -- tiroirs `#edit-drawer`, `#memory-drawer` ; `<p id="scenario-guide">`.
- `src/wavestack/web/static/app.css:30-70, 1588-1628, 1694-1725, 1849-1985, 2705-2724, 2916-2945` -- relief des boutons, `.brick-toggle`, options, tiroirs et mémoire, consigne, `.ctx-view-*`.
- `tools/e2e/run_e2e.py` -- `Run.set_option` (l. 236-247 : attend un interrupteur cliquable), `s_bare_llm` (l. 315), `s_system_prompt` (l. 383), `s_subagent` (l. 900-920 : `role=button` et `aria-pressed` à migrer), `s_global_memory` (l. 1310), `s_rag_rerank` (l. 1690), `s_reload_and_reset` (l. 2084), `s_programme`.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/bricks/registry.py` -- déplacer la déclaration `reasoning` (et son commentaire) en tête de `BRICKS` -- demande 2 de la recette.
- `tests/test_bricks.py` -- ajouter : premier élément de `bricks_changed.bricks` = `reasoning`, ensemble des ids inchangé ; et `turn_id` strictement croissant (`t1`, `t2`, puis `t3` après `clear_conversation`, `t4` après `reset`) avec le faux moteur -- verrouille l'ordre et l'invariant du journal.
- `src/wavestack/web/static/app.js` (bug Annuler) -- `forceUiChanged` affecte une sentinelle unique (ex. `const STALE = Symbol("stale")`) au lieu de `null` -- `null === null` court-circuitait la reconstruction.
- `src/wavestack/web/static/app.js` (sous-options) -- calculer `parentOff` par carte ; le passer à `rerankParts` et `brickOptions` : interrupteurs (options, Reranking, Lazy loading) `disabled`, classe `is-parent-off` sur la ligne, `title` et `aria-description` = `reason_fr` de la brique si indisponible, sinon « Activez la brique {label_fr} pour régler cette option. » ; résumé `· brique éteinte` à la place du mode -- M3, X1.
- `src/wavestack/web/static/app.js` + `index.html` + `app.css` (consigne) -- `#scenario-guide` devient un `div` : texte limité à 3 lignes (`-webkit-line-clamp: 3`), bouton « Afficher plus » / « Réduire » (`aria-expanded`, `aria-controls`) affiché seulement si le texte déborde (mesure après rendu et au redimensionnement du volet) ; repli à chaque changement de scénario -- C1.
- `index.html` + `app.js` + `app.css` (tiroir mémoire) -- en-tête avec titre et croix « × » (`aria-label` « Fermer la mémoire globale », même chemin que `closeMemoryDrawer()`) ; zone centrale seule défilante ; pied fixe contenant alerte, choix « dirty » / « clear » et barre « Tout effacer » (classe `danger`) + « Fermer » (secondaire) ; « Oui, tout effacer » en `danger` ; « Enregistrer » et « Supprimer » d'entrée en actions compactes sans relief, distinctes -- C1.
- `index.html` + `app.js` + `app.css` (prompt système) -- `#drawer-save` désactivé tant que le texte = `store.bricks.system_prompt.text` (ouverture, saisie, après enregistrement, à chaque `bricks_changed`) ; `<p id="drawer-status" role="status">` affiche « Prompt système enregistré. » après succès (« Prompt par défaut rétabli. » après « Rétablir »), effacé à la saisie suivante ou à la fermeture -- M1.
- `src/wavestack/web/static/app.js` + `app.css` (Contexte LLM) -- `ctxViewSwitch` : `role="tablist"` (« Contexte affiché »), onglets `role="tab"` `aria-selected`, libellés « Agent principal » puis « Sous-agent {contextId} » (ex. « Sous-agent sub1 »), style d'onglet (soulignement `--color-primary`) ; `store.ctxView = null` à chaque `turn_started` -- M6.
- `src/wavestack/web/static/app.js` (tours) -- `turnName` et le titre des groupes d'Orchestration utilisent le rang dans `shownTurns()` (`i + 1`) ; l'identifiant `t{n}` en infobulle du titre (« Identifiant du tour dans le journal : t4 ») -- question C1.
- `_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md` -- mettre à jour `brick-card` (l. 130 : ordre, sous-options brique éteinte), `edit-drawer` (l. 133), `turn-rail` (l. 140 : Tour N par conversation), `suggested-prompt-chip`/consigne (l. 138), « Sous-agent au travail » (l. 181 : onglets) -- comportements décrits modifiés.
- `.../DESIGN.md` -- ajouter le composant `button-danger` (fond `surface-raised`, bordure 2 px `danger`, texte `ink`, sans relief ; variante confirmée : fond `danger`, texte `ink`) -- blanc sur `#FF2A49` ne tient pas 4,5:1, encre oui (≈ 5,4:1).
- `tools/e2e/run_e2e.py` -- vérifications ci-dessous ; adapter `s_subagent` aux onglets et tout `set_option` appelé brique éteinte (allumer la brique d'abord) ; captures `02`, `04`, `17`, `19-sous-agent`, `20`, `21`, `25` réécrites -- preuve sur la surface la plus externe.

**Acceptance Criteria:**
- Given WaveStack lancé en LLM nu, when le panneau des briques s'affiche, then la première `article.brick-card` porte « Raisonnement ».
- Given la brique RAG éteinte et Reranking coché (scénario `rag_rerank` puis RAG éteint), when on lit la carte RAG, then `input[data-focus-key="option:rag:rerank"]` est désactivé, son fond calculé n'est pas `--color-primary`, et la ligne a un `title` qui contient « Activez la brique RAG » ; brique rallumée, l'interrupteur redevient actif.
- Given la brique MCP éteinte au lancement (LLM nu) avec mode lazy, when on déplie ses options, then l'interrupteur Lazy loading et ceux des serveurs sont désactivés et le résumé contient « brique éteinte » ; idem pour une option d'outils, de skills et de hooks brique éteinte.
- Given le scénario `soc` lancé, when on mesure `#scenario-guide`, then le texte fait au plus 3 × sa hauteur de ligne (+1 px), « Afficher plus » est visible ; clic : `aria-expanded="true"`, texte plus haut, « Réduire » ; le champ `#composer-input` et la dernière bulle restent visibles dans le volet.
- Given le tiroir de la mémoire ouvert avec au moins 6 entrées (fenêtre 1600 × 1000), when rien n'a défilé, then la croix, « Tout effacer » et « Fermer » sont dans la zone visible (`boundingBox` dans le tiroir) ; la croix ferme le tiroir ; « Tout effacer » a la classe `danger` et une bordure calculée de la couleur danger, différente de celle d'« Enregistrer » d'une entrée.
- Given le tiroir du prompt système ouvert, when le texte est inchangé, then `#drawer-save` est désactivé ; after une saisie puis « Enregistrer », then `#drawer-status` contient « Prompt système enregistré » et `#drawer-save` est de nouveau désactivé.
- Given « Afficher les actions forcées » et le formulaire « Déléguer au sous-agent » ouvert, when on clique « Annuler », then `.force-form` n'existe plus et le bouton a `aria-expanded="false"` ; rouvert puis re-clic sur « Déléguer au sous-agent » : fermé aussi.
- Given un tour avec délégation, when Contexte LLM s'affiche, then un `role=tablist` montre « Agent principal » (`aria-selected="true"`) et « Sous-agent sub1 » ; clic sur ce dernier : contexte du sous-agent ; au tour suivant, « Agent principal » est de nouveau sélectionné.
- Given trois tours puis « Réinitialiser » et un nouvel envoi, when on lit Orchestration, then le groupe s'intitule « Tour 1 » avec l'infobulle « … t4 », et le `turn_started` du journal porte `turn_id` `t4` ; même chose après « Vider la conversation ».

## Spec Change Log

## Review Triage Log

### 2026-09-28 — Review pass
- verdicts: 27 findings — high 0, medium 4, low 19, false 1, maybe-false 0 (+ 3 écarts descriptifs de l'auditeur d'intention, sans défaut : 12 lignes max dépliée, message « Prompt par défaut rétabli », `t{n}` en infobulle — lecture (b) défendable, rejetés)
- findings:
  - `[low]` `[patch]` (vérif.) `turnName` du Contexte LLM non vérifié à « Tour 1 » après remise à zéro — assertion `#ctx .ctx-total` « Tour 1 · » ajoutée dans `_first_turn_after`.
  - `[low]` `[patch]` (vérif.) branche « brique voulue mais indisponible » non testée — assertion Reranking désactivé + `title` = `reason_fr` à l'étape « index absent » de `s_rag`.
  - `[low]` `[patch]` (vérif.) confirmation « Prompt par défaut rétabli » non testée — clic `#drawer-reset` vérifié dans `s_system_prompt`.
  - `[low]` `[patch]` (vérif.) repli de la consigne au changement de scénario non testé — dépliage puis nouveau scénario vérifié.
  - `[medium]` `[patch]` (blind) `#drawer-status` masqué puis rempli dans le même tick : lecteurs d'écran muets — région vivante toujours présente, seul le texte change.
  - `[medium]` `[patch]` (blind + edge) focus perdu quand « Enregistrer » se désactive — focus ramené dans la zone de texte.
  - `[low]` `[defer]` (blind) raison d'une sous-option grisée inaccessible au clavier (`disabled` sort du Tab) — passer à `aria-disabled` demande des gardes ; hors du « survol » demandé.
  - `[low]` `[patch]` (blind) état coché grisé quasi invisible (opacité 0,4 + gris) — opacité pleine pour les interrupteurs « brique éteinte ».
  - `[low]` `[defer]` (blind) onglets sans navigation aux flèches — décision par défaut de la spec ; à reprendre avec le motif ARIA complet.
  - `[false]` `[reject]` (blind) la note « Échap absent du code » de la spec est fausse — vrai constat (Échap existe, l. ~5356) mais la correction serait une édition de la spec ; consigné ici : Échap ferme déjà les deux tiroirs.
  - `[low]` `[defer]` (blind) `t{n}` seulement au survol, pas au clavier — lien journal ↔ « Tour N » à rendre textuel plus tard.
  - `[low]` `[defer]` (blind) règles de numérotation non testées (changement de modèle, rechargement après vidage).
  - `[low]` `[patch]` (blind) test du tiroir mémoire ne prouve pas le défilement — assertion `scrollHeight > clientHeight`.
  - `[low]` `[patch]` (blind) deux boutons rouges pendant la confirmation — « Tout effacer » désactivé pendant la confirmation.
  - `[low]` `[defer]` (blind) boutons Forcer actifs brique éteinte — hors périmètre par décision, à traiter avec la story 27 / suivante.
  - `[low]` `[patch]` (blind + edge) repli « Activez la brique » pour une brique indisponible sans raison — message neutre « indisponible ».
  - `[low]` `[patch]` (blind) capture numérotée 25 en double — renumérotée.
  - `[low]` `[defer]` (blind) frontmatter de DESIGN.md en retard sur la prose (composants tiroir, onglets, consigne).
  - `[low]` `[patch]` (blind) `s_reload_and_reset` masque un échec de mise en place — assertion `len(past_ids) == 3`.
  - `[low]` `[reject]` (blind) repli de `turnName` en français bancal (« Rejeu du t3 ») — cas improbable (rejeu d'un tour effacé), correction non triviale.
  - `[medium]` `[patch]` (edge) pied du tiroir mémoire débordant à 150 % — hauteur max et défilement du pied.
  - `[low]` `[patch]` (edge) consigne repliée à chaque `scenario_changed` même scénario — repli seulement si l'id change.
  - `[low]` `[reject]` (edge) focus perdu si « Réduire » disparaît au redimensionnement — rare, garde supplémentaire non justifiée.
  - `[low]` `[patch]` (edge) `_parent_off_at_launch` laisse MCP en lazy sur exception — `try/finally`.
  - `[medium]` → regroupé ci-dessus (focus « Enregistrer », blind + edge : une seule racine).
  - `[low]` → regroupé ci-dessus (repli `parentOffReason`, blind + edge).
  - `[low]` `[reject]` (intention) consigne dépliée plafonnée à 12 lignes — ajout défendable qui sert l'intention (ne plus cacher prompt et réponse).

## Design Notes

Sentinelle : `const STALE = Symbol("stale"); function forceUiChanged() { renderedForceUi = STALE; scheduleRender(); }` — aucune valeur de `store.forceForm` ne vaut `STALE`, la garde échoue donc toujours après un changement.

Numéro de tour : `const turnNumber = (turn) => { const i = shownTurns().indexOf(turn); return i < 0 ? null : i + 1; };` puis `turnName = (t) => turnNumber(t) ? \`Tour ${turnNumber(t)}\` : t.id`. Après rechargement, `chatFrom` est reconstruit par le rejeu du journal : la numérotation reste identique.

Le calcul « parente éteinte » reste dans l'interface plutôt que dans `_rerank_availability`, car cette disponibilité sert aussi au nœud du schéma et au message « Reranking demandé mais non appliqué » : la changer modifierait le harnais.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, nouveaux tests de `tests/test_bricks.py` compris
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; nouvelles vérifications PASS ; captures de `tools/e2e/screenshots/` réécrites (02, 04, 17, 19-sous-agent, 20, 21, 25)

**Manual checks (if no CLI):**
- Relire les captures : Raisonnement en tête, Reranking gris brique RAG éteinte, consigne sur 3 lignes, pied du tiroir mémoire visible, onglets du Contexte LLM.

## Décisions prises par défaut

- Correction limitée à l'interface ; `_rerank_availability` et les événements inchangés : la story dit « sans changer le comportement du harnais ».
- Parente « éteinte » inclut « voulue mais indisponible » ; l'infobulle donne alors la raison de la brique : même effet pour l'utilisateur (l'option ne s'applique pas).
- Sous-option grisée garde son état coché : le choix de l'utilisateur est retrouvé au rallumage, comme aujourd'hui côté session.
- Raison au survol par `title` sur la ligne (et `aria-description` sur l'interrupteur) ; pas de ligne de texte supplémentaire, pour ne pas charger les cartes.
- Boutons Forcer et « Télécharger » du reranker inchangés brique éteinte : hors des points relevés.
- Résumé MCP brique éteinte : « · brique éteinte » à la place du mode, pour ne plus laisser croire que le lazy loading agit (X1).
- « Afficher plus » seulement si le texte déborde ; repli à chaque nouveau scénario ; état non mémorisé par le navigateur.
- Croix ajoutée au seul tiroir de la mémoire (demande C1) ; `Échap`, décrit dans EXPERIENCE.md mais absent du code, reste hors périmètre (noté comme écart).
- Style destructif = bordure danger et texte encre (contraste), fond danger pour la confirmation ; nouveau composant `button-danger` dans DESIGN.md, sans token nouveau.
- Entrées de la mémoire : « Enregistrer » et « Supprimer » en actions compactes sans relief, hauteur mini `hit-target-min` conservée.
- « Rétablir le prompt par défaut » confirme par « Prompt par défaut rétabli. » ; message effacé à la saisie ou à la fermeture.
- Onglets du Contexte LLM affichés seulement quand le tour montré a un contexte de sous-agent (comme la bascule actuelle) ; libellé = identifiant `sub{n}` de la session ; retour à « Agent principal » à chaque nouveau tour ; pas de navigation aux flèches (tous les onglets restent dans l'ordre de tabulation).
- Numéro de tour calculé côté affichage depuis `chatFrom` (aucune charge d'événement nouvelle) ; `t{n}` en infobulle pour relier au journal. Le changement de modèle, qui ne vide pas la conversation, ne remet pas le numéro à 1.
- Ordre du schéma : le nœud Raisonnement suit le nouvel ordre de `BRICKS` ; accepté (affichage seulement).

## À vérifier sur PC

- **Geste** : Edge, lancer WaveStack (`uv run wavestack`), regarder le panneau des briques ; éteindre RAG avec « Reranking » coché ; déplier MCP brique éteinte ; survoler « Reranking » et « Lazy loading ». — **Attendu** : Raisonnement en tête ; interrupteurs gris, raison en infobulle. — **Critère** : infobulle visible en moins de 2 s de survol, sous Edge et Chrome. — **Moyen** : Claude in Chrome ou à la main.
- **Geste** : lancer « Métier SOC » dans le sélecteur de scénario, texte à 125 % puis 150 % (« Aa »), cliquer « Afficher plus » puis « Réduire ». — **Attendu** : 3 lignes, bouton présent, la réponse d'un tour reste lisible. — **Critère** : au moins 2 bulles visibles au-dessus du champ sur l'écran du poste, sans défilement de la page. — **Moyen** : à la main (œil humain).
- **Geste** : scénario « Mémoire globale », « Modifier la mémoire », ajouter des entrées jusqu'à 8 par « Écrire en mémoire ». — **Attendu** : croix en haut à droite, pied « Tout effacer » (rouge) / « Fermer » visible sans défiler. — **Critère** : les deux boutons visibles à 100 % et 150 % de taille de texte ; distinction jugée évidente par Anaël. — **Moyen** : à la main.
- **Geste** : « Modifier le prompt », ne rien changer, puis modifier et « Enregistrer ». — **Attendu** : bouton gris puis confirmation « Prompt système enregistré. ». — **Critère** : confirmation lue par le lecteur d'écran de Windows (Narrateur) — **Moyen** : à la main.
- **Geste** : avec Qwen3.5-4B (tool parser), scénario « Sous-agent », « Afficher les actions forcées », « Déléguer au sous-agent », « Annuler », puis armer et envoyer. — **Attendu** : le formulaire se ferme ; après le tour, onglets « Agent principal » / « Sous-agent sub1 ». — **Critère** : fermeture immédiate (< 0,5 s) ; onglet principal sélectionné par défaut. — **Moyen** : Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`) ou Claude in Chrome.
- **Geste** : envoyer trois messages, « Réinitialiser », renvoyer un message ; puis « Vider la conversation » et renvoyer. — **Attendu** : Orchestration « Tour 1 » à chaque fois, infobulle t4 puis t5 ; journal des événements en t4, t5. — **Critère** : numéro affiché = 1, `turn_id` unique. — **Moyen** : script `AppSession` pour les `turn_id`, à la main pour l'affichage.

## Auto Run Result

Statut : done (2026-09-28, exécution de nuit pilotée par l'orchestrateur ; les sous-agents ne pouvant pas lancer de sous-agents, l'orchestrateur a mené les étapes 1 à 4 lui-même).

**Changement :** les huit défauts d'interface de la recette (C1, M1, M3, M6, X1) sont corrigés côté affichage : Raisonnement en tête des briques ; sous-options grisées et désactivées brique éteinte ou indisponible, raison au survol ; consigne limitée à 3 lignes avec « Afficher plus » ; tiroir mémoire avec croix, pied fixe et « Tout effacer » destructif ; « Enregistrer » du prompt système désactivé tant que rien ne change, avec confirmation annoncée ; « Annuler » des actions forcées réparé (sentinelle `STALE`) ; onglets « Agent principal » / « Sous-agent » ; « Tour N » qui repart de 1 après vidage ou réinitialisation (`t{n}` gardé au journal, en infobulle).

**Fichiers :** `src/wavestack/bricks/registry.py` (ordre), `src/wavestack/web/static/app.js`, `app.css`, `index.html` (interface), `tests/test_bricks.py` (2 tests), `tools/e2e/run_e2e.py` et `tools/e2e/README.md` (contrôles E2E), `DESIGN.md` et `EXPERIENCE.md` (comportements), captures E2E.

**Revue :** 27 constats — 15 corrigés (4 medium, 11 low), 6 différés (frontmatter `deferred`), 5 rejetés (1 false, 4 low peu probables ou défendables), voir le triage. Revue de suivi recommandée : false (aucun high ; les medium corrigés sont locaux et couverts par l'E2E).

**Vérification :** `uv run ruff check .` et `ruff format --check .` verts ; `uv run pytest -q` : 937 passés, 3 ignorés ; parcours E2E complet : 392 PASS, 0 FAIL.

**Risques résiduels :** lecture par Narrateur de la ligne d'état et des raisons (à vérifier sur PC) ; tailles de texte 125 et 150 % non testées automatiquement.
