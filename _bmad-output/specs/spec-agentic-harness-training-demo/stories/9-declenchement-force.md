---
title: 'Déclenchement forcé'
type: 'feature'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '945aee0f4bc85f073120d855d1ff6d11b25e8449'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Un SLM faible ne déclenche pas toujours l'action que la démonstration attend (lire le fichier sensible pour montrer H1, charger une documentation MCP, déclencher Caveman) : la démonstration échoue sans que l'animateur puisse la rattraper (CAP-8, FR-42, CR-2).

**Approach:** Depuis le panneau des briques, l'utilisateur arme une action (AD-3). Le tour suivant la consomme après `on_user_message` et avant le premier appel au modèle, par l'exécuteur unique, hooks compris, avec `trigger = user` (AD-25). Orchestration affiche « Forcé par l'utilisateur » sur la ligne d'étape. Le rejeu (CAP-7) est reporté en story 9b.

## Boundaries & Constraints

**Always:**
- Seule la `Session` tient la liste des actions armées ; arm et disarm sont de classe (a), acceptés à tout moment. Le front projette la liste depuis un événement rejouable, jamais depuis un calcul local (AD-1).
- Consommation dans l'ordre d'armement, hors budget d'appels (AD-10) ; un échec d'action forcée (blocage H1, erreur d'outil) est réinjecté comme pour le modèle et ne compte pas dans les nouveaux essais.
- Rendu dans le contexte : un message assistant avec l'appel d'outil puis sa réponse, placés après le message de l'utilisateur ; segments attribués à la brique de l'action (outils, skills, mcp), pas à `core.model`.
- Le tour prend la liste armée au moment de l'envoi. En fin de tour, quel que soit le statut, seules ces actions sont retirées : une action armée pendant le tour attend le tour suivant (classe a).
- Une action dont la cible n'est plus disponible à la consommation (brique ou sous-option décochée, skill déjà chargé, serveur non connecté) est abandonnée avec `action_dropped{armed_id, reason_fr}`, sans bloquer le tour.
- Les événements d'un appel décidé par le modèle portent `trigger = model`, ceux d'une action forcée `trigger = user`. Le badge du front lit `envelope.trigger`, plus `source`.
- Décision (Anaël, 2026-09-25) : actions forçables au palier 1 = appel d'un outil natif avec ses arguments, « Charger la documentation » d'un outil MCP en lazy loading, « Déclencher le skill ». `remember` et `delegate` naîtront avec leurs briques (palier 2) en réutilisant ce mécanisme ; pas d'appel forcé d'un outil MCP.
- Décision (Anaël, 2026-09-25) : arguments d'un outil forcé = formulaire, un champ par paramètre (description du paramètre en aide), prérempli par un préréglage choisi dans une liste ; préréglages déclarés dans `content/tools.yaml` (`presets: [{label_fr, args}]`), dont « Fichier sensible » → `confidentiel/budget_projet.txt` pour `read_file`. Un outil sans paramètre s'arme sans formulaire.
- Décision (Anaël, 2026-09-25) : les boutons « Forcer » sont masqués par défaut, les SLM étant censés déclencher seuls. Un interrupteur unique en tête du panneau des briques, « Afficher les actions forcées », les montre ; son état est mémorisé par le navigateur comme la configuration des volets. Les puces « Armé : … » et les badges restent toujours visibles.
- Libellés d'EXPERIENCE.md : puce « Armé : … » au-dessus du champ de saisie et sur la carte de brique (clic = désarmer) ; `force-button` et `trigger-badge-user` de DESIGN.md (contour encre, icône main) ; textes en français.

**Never:** rejeu, branche, badge « Rejeu », comparaison de tours (story 9b) ; disponibilité par mode `forced` sans parseur (AD-6, reportée) ; nouvelle dépendance ; nouveau `SegmentKind` ; toucher au redimensionnement (8f) ou à la disposition du schéma (8e).

## I/O & Edge-Case Matrix

| Scénario | État | Comportement attendu |
|---|---|---|
| Lecture forcée du fichier sensible | `read_file` armé sur `confidentiel/budget_projet.txt`, H1 actif | Avant le premier appel au modèle : `before_tool`, H1 bloque, refus réinjecté ; ligne d'étape « Forcé par l'utilisateur » ; le modèle répond ensuite. |
| Skill forcé | « Déclencher le skill » Caveman | `load_skill` exécuté, `SkillLoaded` appliqué, `skill_body` attribué à skills ; le modèle répond en Caveman dès ce tour. |
| Documentation MCP forcée | lazy loading, un outil de serveur connecté | `load_tool_doc`, `ToolDocLoaded` ; l'outil est appelable par le modèle dans le même tour. |
| Deux actions armées | outil puis skill | Consommées dans cet ordre, avant l'appel c1 ; le budget de 6 appels reste entier. |
| Cible devenue indisponible | skill décoché après armement | `action_dropped` avec la raison ; le tour continue. |
| Armée pendant un tour | arm en état `turn` | Pas consommée par le tour en cours ; toujours armée après `turn_ended`. |
| Arrêt ou limite | tour `stopped`/`limit` | Les actions prises à l'envoi sont retirées ; la puce disparaît. |
| Cible inconnue | arm d'un outil inexistant | 404 avec détail en français ; rien n'est armé. |

</frozen-after-approval>

## Code Map

- `src/wavestack/session/app_session.py` : `send()` (1105-1132) prend la liste armée avec `_sent` ; setters de classe (a) (`set_skill` 1171) comme modèle pour `arm`/`disarm` ; `_turn` (1585-1712) : consommer avant la boucle `for n` (1601), avec `check` (1661), `_run_tool` (1714, déjà prévu pour « the forced action »), étapes assistant et outil dans `steps`, effets via un utilitaire extrait de 1698-1702 ; envelopper la dispatch du modèle (1629) dans `scoped(trigger="model")` ; `finally` de `_run_turn` (1559-1583) : retirer les actions prises, émettre la liste. `_step_messages` (877-924) : une étape assistant peut porter `brick`/`component`. `_emit_bricks` (574-624) et `_tool_options` (505-565) : ajouter aux options d'outil leurs `parameters` (nom → description) et `presets`. Méta-outils : `_harness_tools` (1215), `_load_skill` (1279), `_load_tool_doc` (1263).
- `content/tools.yaml` et `src/wavestack/tools/registry.py` (`ToolText` 61-63, chargement 67-75) : champ facultatif `presets: [{label_fr, args}]`, validé par pydantic (clés d'`args` = paramètres déclarés).
- `src/wavestack/session/effects.py:32` : ajouter `ArmConsumed{armed_id}` à l'union.
- `src/wavestack/trace/catalog.py` : `armed_actions_changed{actions: [{armed_id, kind, brick, target, args, label_fr}]}` et `action_dropped{armed_id, reason_fr}` dans `PAYLOAD_MODELS` (336-366) ; `BrickOption` (192) : `parameters`, `presets`.
- `src/wavestack/web/app.py` : `POST /api/intentions/arm {kind: tool|skill|tool_doc, target, args}` et `/disarm {armed_id}` (modèle de 196-298, `KeyError` → 404) ; `/api/state` (137-166) : dernier `armed_actions_changed`.
- `src/wavestack/web/static/app.js` : `applyEnvelope` (125-313) garde `trigger` sur l'étape `tool_started` (208-224) et `store.armed` ; `renderBricks`/`brickOptions` (419-530) : interrupteur « Afficher les actions forcées » en tête de `#bricks` (mémorisé en `localStorage` avec try/catch, comme `loadPaneLayout`/`savePaneLayout` 1898-1925), bouton Forcer, formulaire à préréglages, puce ; `renderComposer` (766-781) et `index.html` (73-83) : rangée de puces au-dessus de `form#composer` ; `postIntention` (783) ; `turnRows` (1271-1287), `stepNode` (1393-1462) : badge sur la ligne ; `toolBody` (939-975) : badge selon `trigger` ; ligne pour `action_dropped`.
- `src/wavestack/web/static/app.css` : `.force-button`, `.armed-chip`, `.trigger-badge-user` (à côté de `.trigger-badge-model` 621), zone de grille de `.turn-step-line` (~929).
- Tests : `tests/test_tools.py` (`tool_session`, `call`, `_segments`), `tests/test_skills.py` (`skills_session`), `tests/test_mcp_lazy.py` (`lazy_session`), `tests/test_hooks.py` (`hooks_session`), `tests/test_bricks.py` (`_client`, `HEADERS`), `tests/fake_engine.py`.

## Tasks & Acceptance

**Execution:**
- [x] `session/effects.py`, `trace/catalog.py`, `tools/registry.py`, `content/tools.yaml` -- `ArmConsumed`, deux événements, `parameters` et `presets` (au moins « Fichier sensible » pour `read_file`) -- contrat d'abord.
- [x] `session/app_session.py` -- `arm`/`disarm`, prise à l'envoi, consommation, attribution, `trigger`, retrait en fin de tour, abandon -- AD-3, AD-25.
- [x] `web/app.py` -- routes et `/api/state` -- AD-18.
- [x] `web/static/app.js`, `app.css`, `index.html` -- interrupteur masqué par défaut, Forcer, formulaire prérempli, puces, badge sur la ligne et dans le corps, ligne d'abandon -- EXPERIENCE.
- [x] `tests/test_forced.py` (nouveau) -- une ligne de la matrice par test, plus rendu du contexte (appel après le message utilisateur, brique attribuée) et `trigger = model` sur un appel décidé par le modèle.

**Acceptance Criteria:**
- Given une action forcée, when le tour s'exécute, then l'étape suit tout le cycle (`before_tool`, exécution, `after_tool`, réinjection) et Orchestration affiche « Forcé par l'utilisateur » sur sa ligne ; un appel du modèle affiche « Déclenché par le modèle ».
- Given une première visite, when le panneau des briques s'affiche, then aucun bouton Forcer n'est visible ; l'interrupteur les montre, et son état survit au rechargement.
- Given un rechargement de la page, when une action est armée, then la puce réapparaît (projection du journal).
- Given le clavier, when on tabule, then Forcer, les champs, « Armer » et chaque puce sont atteignables, avec un nom accessible (« Désarmer … »).

## Implementation Notes

- `BrickOption` gagne aussi `tools` (serveurs MCP) : la liste des outils dont « Charger la documentation » peut charger la documentation, calculée par la session ; le bouton n'apparaît qu'en lazy loading.
- Arguments d'un outil forcé : les champs du formulaire sont du texte, convertis par la session selon le schéma de l'outil (`convert_value`, ex-`_convert` du parseur) ; des arguments invalides donnent 422 avec le détail français, une cible inconnue 404.
- Badge sur la ligne : chaque étape d'outil porte « Déclenché par le modèle » ou « Forcé par l'utilisateur » (`envelope.trigger`) ; une décision de hook `before_tool`/`after_tool` sur une action forcée porte « Forcé par l'utilisateur » (cas d'H1 qui bloque : il n'y a pas d'étape d'outil).
- Le bouton Forcer reste actif même si la brique ou l'option est éteinte : la session abandonne l'action à la consommation, avec la raison (`action_dropped`).

## Spec Change Log

## Review Triage Log

Passe 1 (2026-09-25) — relecteurs : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| BH1 / EC1 | Nombre d'actions armées illimité, hors budget d'appels | low | Réel, mais l'animateur arme à la main en salle, poste local mono-utilisateur ; le correctif ajoute un réglage et une garde. Hors budget : voulu (AD-10). | rejeté |
| BH2 | Désarmer pendant un tour retire la puce alors que le tour exécute l'action | low | La consommation a lieu dès le début du tour, avant le premier appel : le clic arrive presque toujours après ; correctif = nouvelle branche 409. | rejeté |
| BH3 / EC7 | Préréglages validés contre les descriptions YAML, pas contre le schéma de l'outil ni les types | low | Seul un auteur de contenu peut le déclencher, les préréglages livrés sont justes ; correctif = validation croisée registre/contenu. | rejeté |
| BH4 | La liste armée est prise deux fois (`build_turn_state` et `send`), la seconde écrase la première | low | `build_turn_state` capture `armed` hors du verrou de `send` : la story 9b, qui réutilise cette fonction pour le rejeu, lirait une liste prise au mauvais moment. Correctif = suppression. | patch |
| BH5 | `ArmConsumed` n'est pas produit par un outil ni tracé en `effect_applied` | false | AD-23 range `ArmConsumed` parmi les effets et la spec demande de l'ajouter à l'union ; la session l'applique elle-même, conformément à AD-3. | rejeté |
| BH6 | Après rechargement, la ligne d'abandon perd le libellé | false | Au démarrage, le front rejoue le journal depuis 0 : l'`armed_actions_changed` qui précède l'abandon remplit `armedLabels` avant l'`action_dropped`. | rejeté |
| BH7 | Même icône ✋ pour « Forcé par l'utilisateur » et pour H5 | low | Un appel réseau forcé soumis à H5 montre deux mains de sens différents sur deux lignes voisines ; correctif = changer un caractère. | patch |
| BH8 / EC5 | Focus perdu après désarmement (puce de carte ; dernière puce du champ de saisie pendant un tour) | low | `renderBricks` cherche la clé de la puce disparue et ne trouve rien ; `renderComposer` retombe sur un champ désactivé pendant le tour. Parcours clavier courant. | patch |
| BH9 | Champs vides envoyés en `""` | low | Chaque outil n'a qu'un paramètre, obligatoire ; `""` donne un résultat ou une erreur réinjectée visible. | rejeté |
| BH10 | Forcer accepté sur une option décochée, abandonné au tour | false | Comportement voulu : ligne de la matrice « Cible devenue indisponible » ; la raison s'affiche dans Orchestration. | rejeté |
| BH12 / EC4 | Erreur d'armement en tête du panneau non annoncée et jamais effacée | low | `<p class="force-error">` sans `role="alert"`, remis à zéro seulement par un armement sans formulaire. Correctif direct. | patch |
| BH13 | Libellés bruts (`local__define_term`) et non tronqués | low | Cosmétique ; le nom `serveur__outil` est celui qu'enseigne la brique MCP ; troncature = logique en plus. | rejeté |
| BH14 / EC6 | Liste d'outils MCP par préfixe, sélection périmée si le serveur change pendant que le formulaire est ouvert | low | Il faut une reconnexion du serveur pendant la saisie ; correctif = garde. | rejeté |
| BH15 | Préréglage « . » de `read_file` douteux ; année 2026 figée | false / low | La description de l'outil dit « Indiquer « . » comme chemin pour lister les fichiers » ; l'année figée est un contenu de démonstration. | rejeté |
| EC2 | Arrêt pendant la consommation : les actions non tentées disparaissent sans trace | low | Il faut arrêter pendant la validation H5 d'une action forcée alors qu'une autre attend ; rare, correctif = boucle d'événements en plus. | rejeté |
| EC3 | Double clic sur Forcer ou Armer pendant la requête : action armée deux fois | low | Aucun verrou pendant le `POST` ; un double clic en salle est courant, `get_datetime` s'exécuterait deux fois. Correctif = désactiver le bouton pendant la requête. | patch |
| EC8 | Un appel du modèle bloqué par H1 n'a pas de badge « Déclenché par le modèle » | low | `forcedHook` ne rend un badge que pour `trigger = user` ; asymétrie avec l'appel forcé bloqué. Correctif direct. | patch |
| VG1 | Conversion `"2026"` → entier à l'armement non testée | medium | Écart vérifié par la couche (gap pré-vérifié). | patch |
| VG2 / BH11 | Raisons d'abandon autres que « skill décoché » non testées | medium | Gap pré-vérifié : `_armed_unavailable` est la seule garde contre un outil décoché. | patch |
| VG3 | Refus d'armer un outil MCP ou du harnais en `tool` non testé | medium | Gap pré-vérifié. | patch |
| VG4 | Champ `tools` des options MCP jamais vérifié | medium | Gap pré-vérifié : sans lui, « Charger la documentation » disparaît. | patch |
| VG5 | Validateur des préréglages non testé | low | Gap pré-vérifié. | patch |
| VG6 / BH11 | Arrêt pendant une action forcée (H5 en attente) non testé | medium | Gap pré-vérifié. | patch |
| VG7 / BH11 | Rendu front (badges, puces, formulaire) sans test automatique | medium | Aucun banc de test JS, même écart que 5b à 8f. | defer |

## Verification

**Commands:**
- `uv run ruff check .` et `uv run python -m pytest` -- expected: tout passe
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks:**
- `uv run wavestack` avec Qwen : armer la lecture du fichier sensible avec H1 actif, Caveman, une doc MCP en lazy loading ; recharger la page avec une action armée ; désarmer.
