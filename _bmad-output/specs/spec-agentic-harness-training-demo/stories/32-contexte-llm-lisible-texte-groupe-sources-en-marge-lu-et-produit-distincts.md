---
title: 'Contexte LLM lisible : texte groupé, sources en marge, lu et produit distincts'
type: 'feature'
created: '2026-09-28'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/22-retours-de-recette-briques-volets-et-tiroirs.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/33-contrastes-et-code-couleur-par-discipline.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/34-vue-liee-au-survol-et-lecture-guidee-des-volets.md'
  - '{project-root}/tools/e2e/README.md'
warnings:
  - oversized
deferred: []
---

<intent-contract>

## Intent

**Problem:** Contexte LLM montre seulement le dernier appel du tour, en une boîte par segment : le texte lu n'est plus d'un seul tenant, les JSON sont illisibles sur une ligne, et rien ne sépare ce que le modèle a lu de ce qu'il a produit. Un tour avec outil (deux appels) ne se lit pas comme une suite : on ne voit ni ce que le premier appel a lu, ni ce qui est nouveau au second (le résultat d'outil réinjecté).

**Approach:** La session ajoute à chaque charge de contexte des **sections** : des segments consécutifs de même source, avec leurs tokens. Elle y ajoute aussi la **part déjà lue** à l'appel précédent du même contexte dans le tour (AD-1 : l'interface n'additionne rien). L'interface affiche chaque appel du tour, numéroté, en deux temps :
- ce qui a été **lu** : texte continu, source en marge, « déjà lu » replié, « nouveau » mis en avant ;
- ce qui a été **produit** : réflexion, réponse et appels d'outil, sur un fond propre.

Deux bascules s'ajoutent : « Texte exact » (brut, sans habillage) et, en mode chat, « Corps JSON ». Les JSON sont indentés, colorés et repliables, en JS natif.

## Boundaries & Constraints

**Always:**
- `uv`, `ruff` et `pytest` (CLAUDE.md). Code et identifiants en anglais, textes d'interface en français.
- **Exactitude.** « Texte exact » est la concaténation des `segments[].text` de l'appel, c'est-à-dire le prompt envoyé (AD-4). En mode chat, c'est `body`. Il s'affiche octet pour octet, en `textContent`. La lecture groupée ne fait que mettre en forme (indentation des JSON, décodage des chaînes JSON en mode chat) : aucun texte n'y manque ni n'y est ajouté hors habillage.
- **AD-1 / AD-2.** Les sections, leurs tokens, `seen_segments` et `seen_tokens` sont calculés par la session. Les tokens d'un appel viennent de `model_call_ended` (`prompt_tokens`, `evaluated_tokens`, `output_tokens`). Pas de retokenisation, pas de somme dans le navigateur. Compter les éléments d'une liste reçue reste permis.
- **Sections calculées par une seule fonction**, appelée par `gauge()`, pour que `context_rendered`, `context_preview` et `context_reconciled` les portent (AD-9). `context_reconciled` garde le `seen_segments` de son `context_rendered`.
- **Couleurs.** Uniquement des variables de `tokens.css`, déclarées dans le frontmatter de DESIGN.md avec la même valeur (story 33 interdit `#hex`, `rgb(` et `hsl(` dans `app.css` et `app.js`). Contrastes AA ajoutés au test de story 33. Discipline des sections portée par `data-discipline` (story 33) ; la pastille de type garde `GROUP_COLORS`.
- **Ne rien casser des stories livrées.** Rester compatible avec :
  - « Comparer » (`renderCompare`, `compareCell`, `brickGroups`), inchangé ;
  - les onglets « Agent principal » / « Sous-agent subN » (story 22) et « Voir le contexte du sous-agent » ;
  - la ligne `.ctx-total` (« Tour N · … », source du total) et le bandeau du mode chat ;
  - le badge et le texte « avant compression » (story 20) ;
  - la liaison au survol et la sélection de story 34, livrée avant celle-ci. Chaque `.ctx-section` reçoit, par `setLinks`, l'union des `brick` et `component` de ses segments, plus `call:{id}` de **son** appel. Elle garde `tabindex="0"` et la sélection au clic, à Entrée ou à Espace. Les blocs produits portent `call:{id}`, et la réflexion porte aussi `reasoning`.
  - le numéro « 2 » et le sous-titre du volet (story 34) ;
  - le Mode projection (story 34) : les tailles passent par les jetons `--typography-*`, jamais en px bruts.
- Ancrer le code sur les symboles : les stories 33, 23 et 34 déplacent les lignes.
- Mettre à jour EXPERIENCE.md, DESIGN.md, la spine (AD-4, AD-9) et SPEC.md (CAP-2). Ajouter les vérifications au parcours E2E et mettre les captures à jour.

**Never:**
- Aucune dépendance nouvelle : pas de bibliothèque JSON, de coloration ni de framework. Aucun vrai modèle dans le conteneur : faux moteur et faux fournisseurs de `tests/`, faux serveurs de `tools/e2e` (faux cloud, faux llama-server avec le gabarit Qwen3.5).
- Pas de nouvel événement ni de changement d'API HTTP ; seulement des champs optionnels, avec une valeur par défaut, dans `ContextWindowPayload`.
- Ne pas toucher la jauge, l'Orchestration ni la Vue humain, sauf les liens vers l'onglet du sous-agent déjà existants.
- Hors périmètre : mode sombre (story 31, mais les jetons doivent être prêts), détail de la jauge, recherche dans le contexte.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Sources simples | `[template, system_prompt, template, user_message, template]` | 5 sections, une par segment | — |
| Gabarit entre même source | `[template, tool_catalog(tools, calc), template "\n", tool_catalog(tools, clock), template]` | 3 sections ; celle du milieu couvre 3 segments, `template_tokens` = tokens du `"\n"` | — |
| Même type, autre brique | `tool_catalog(tools)` puis `tool_catalog(mcp)` | deux sections | — |
| Libellé propre | segment « Gabarit appliqué chez le fournisseur (estimé) » (mode chat) | section à lui, avec ce libellé | — |
| Somme | toute charge | Σ `sections.tokens` = `used` ; `estimated` si un segment l'est | — |
| Premier appel du tour | pas d'appel précédent dans ce contexte | `seen_segments = seen_tokens = 0`, aucune section `seen` | — |
| Appel après outil | appel 2 : segments de l'appel 1, puis sortie du modèle et résultat d'outil | `seen_segments` = longueur du préfixe commun (`kind`, `brick`, `component`, `text`) ; les sections ne chevauchent jamais cette frontière | — |
| Sous-agent | appels `sub1.c1`, `sub1.c2` | préfixe comparé à l'appel précédent du **même** contexte | — |
| Mode chat réconcilié | `context_reconciled` de l'appel 2 | mêmes `seen_segments` et découpage, tokens recalés | — |
| JSON invalide ou tronqué | texte `{"a": ` | affiché en texte brut | aucune exception |
| Relance après coupe du raisonnement | un appel, `reasoning_cut` au milieu | un seul appel affiché ; la note du harnais entre réflexion et réponse | — |
| Contexte dépassé | dernier appel sans `model_call_ended` | son « Produit » dit « Aucun appel : contexte dépassé. » | — |

</intent-contract>

## Code Map

- `src/wavestack/context/window.py` -- `gauge()`, fonction unique des charges (AD-9). Story 33 y ajoute `discipline_of`, `tokens_by_brick` et `categories`. Y ajouter `seen: int = 0`, puis appeler une nouvelle fonction pure `context_sections(segments, labels, categories, seen)`, qui renvoie `sections`, `seen_segments` et `seen_tokens`. Y ajouter aussi `seen_prefix(previous, current) -> int`.
- `src/wavestack/context/segments.py` -- `Segment` (dont `label_fr` propre), `SegmentKind`, `SegmentLabels` (`kinds`, libellés de `content/labels/segment_kinds.yaml`).
- `src/wavestack/context/render.py` -- `_attribute` (segments ordonnés et disjoints, gabarit compris), `RenderedContext`, `RenderedChat`, `render_chat_body` (segment fournisseur sans texte, en dernier), `with_total`. Le décodage `\n` est sûr, car les fragments non gabarit du mode chat sont toujours à l'intérieur d'une chaîne JSON (sentinelles).
- `src/wavestack/trace/catalog.py` -- `SegmentPayload`, `BreakdownItem`, `BrickTokens`, `ContextWindowPayload` (et `ContextReconciledPayload`), `Discipline`, `ModelCallEndedPayload` (`raw_output`, `reasoning`, `text`, `tool_calls`, `prompt_tokens`, `evaluated_tokens`, `output_tokens`, `usage_source`), `ReasoningCutPayload`.
- `src/wavestack/session/app_session.py` -- à modifier :
  - `_render` et `_render_chat` : les deux appels à `gauge()` ;
  - `_chat_gauge`, qui refait la charge pour `context_reconciled`, dans le code du mode chat qui émet `"context_reconciled"` ;
  - `_categories` ;
  - la boucle du tour principal, autour de `journal.emit("context_rendered", payload)` : `previous`, `_check_reuse` et `call_id = f"{turn_id}.main.c{n}"` ;
  - `_run_subagent`, même émission, contexte `sub{n}`.
- `src/wavestack/web/static/app.js` -- à modifier :
  - réducteurs : `case "context_rendered"`, `"context_reconciled"`, `"model_call_ended"` et `"reasoning_cut"` du réducteur principal ; les mêmes dans `applySubEnvelope`. Chaque appel est déjà une étape `{type: "call", id, context, ended}` de `turn.steps` ou de `sub.steps`. Une `reasoning_cut` suit son appel dans `steps`. `lastCall` ;
  - rendu : `renderContext`, `renderContextBody` (dernier contexte seulement, `ctx-banner`, `ctx-total`, `ctx-compressed-total`, raisonnement, `ctx-raw`), `appendSegments` (une boîte par segment, `data-discipline`, `--segment-color`, `compressed_from` et `textBefore`), `renderSubContext`, `ctxViewSwitch` (onglets, story 22), `reasoningBlock` et `store.openReasoning` ;
  - aides : `approx`, `approxTotal`, `fmt`, `seconds`, `turnName`, `shownTurns`, `brickName`, `GROUP_COLORS`, `formatCall`, `showSubContext`, `loadShowReasoning` (modèle de mémorisation `localStorage` avec try/catch) ;
  - à ne pas modifier : `renderCompare`, `compareCell`, `brickGroups`.
  - Pour éviter une reconstruction inutile, suivre le modèle de `renderSchema`, qui compare une clé `JSON.stringify`.
- `src/wavestack/web/static/app.css` -- `.ctx-total`, `.ctx-segment*`, `.ctx-raw`, `.ctx-heading`, `.ctx-banner`, `.ctx-view-switch`, `.ctx-view-button`, `.ctx-compressed*`, `.reasoning-block`. `tokens.css` pour les jetons.
- `tests/test_turn.py` -- tests de `gauge()` (story 33). Tours à outil : `tests/test_tools.py` (faux moteur local), `tests/test_cloud.py` (faux fournisseur, deux `context_rendered` et un `context_reconciled`), `tests/test_subagent.py`. `tests/test_web_tokens.py` : jetons et contrastes (story 33).
- `tools/e2e/run_e2e.py` -- vérifications de Contexte LLM à adapter :
  - `s_native_tools` (mode chat, `get_datetime`) ;
  - `s_bare_llm` (« [raisonne] », `.ctx-total`) ;
  - `s_disciplines`, qui cherche `#ctx .ctx-segment` avec `(system_prompt)` ;
  - `s_subagent` (onglets) ;
  - `s_rag`, qui attend 4 `.ctx-segment-label` « Extraits RAG (rag) » ;
  - `s_compression` (un `.ctx-compressed-badge`, un « Texte avant compression ») ;
  - `s_local_server` (Qwen3.5 local, outil, jointure des segments = prompt) ;
  - `s_linked_view` (story 34), qui attend « au moins un `.ctx-segment` » et « chaque `.ctx-segment` affiché » éclairés ;
  - `_first_turn_after`.
- Story 34, par symbole : `setLinks`, `applyLinks`, `select`, `setSelection`, `clearSelection` et `store.gauge.callId`.
  Aides : `r.fake_calls()`, `r.ev.since`, `r.shot`, `r.shot_element`, `r.token_color`, `r.css`.

## Tasks & Acceptance

**Execution:**
1. `src/wavestack/trace/catalog.py` -- Ajouter `ContextSection{start: int, end: int, kind: str, label_fr: str, brick: str | None, discipline: Discipline, tokens: int, template_tokens: int, estimated: bool, seen: bool}`. `start` et `end` sont des index dans `segments`, `end` exclu. Ajouter à `ContextWindowPayload` : `sections: list[ContextSection] = []`, `seen_segments: int = 0` et `seen_tokens: int = 0`. Raison : AD-2, la forme est dans le catalogue ; les valeurs par défaut gardent les journaux anciens valides.
2. `src/wavestack/context/window.py` -- Écrire `seen_prefix` et `context_sections` selon la matrice et les Design Notes, puis les brancher dans `gauge(…, seen=0)`. Raison : AD-1 et AD-9.
3. `src/wavestack/session/app_session.py` -- Dans la boucle principale et dans `_run_subagent`, garder les segments de l'appel précédent du même contexte **dans le tour**, calculer `seen_prefix` et le passer à `gauge()` par `_render` et `_render_chat`. Garder la valeur avec l'objet rendu, pour que `_chat_gauge` la redonne à `context_reconciled`. Raison : « déjà lu » et « nouveau » viennent de la session.
4. `tests/test_turn.py` (ou `tests/test_context_sections.py`) et `tests/test_tools.py`, `tests/test_cloud.py`, `tests/test_subagent.py` -- Tests unitaires de chaque ligne de la matrice : Σ = `used`, absorption, libellé propre, frontière `seen`. Tests d'intégration :
   - appel 1 : `seen_segments == 0` ;
   - appel 2 d'un tour à outil, en local et en chat : `seen_segments > 0`, et une section `tool_result` non vue ;
   - `context_reconciled` : même `seen_segments` que son `context_rendered` ;
   - appel 2 du sous-agent : `seen_segments > 0` ;
   - `"".join(texts)` inchangé.
   Raison : verrouiller le contrat.
5. `DESIGN.md` (frontmatter et prose) puis `src/wavestack/web/static/tokens.css`, `tests/test_web_tokens.py` -- Ajouter les jetons de la note de conception, les paires de contraste et les composants `context-call`, `context-section`, `produced-block`, `json-tree`. Raison : AD-18, story 33, story 31.
6. `src/wavestack/web/static/app.js` -- Remplacer le rendu du dernier contexte par la **suite des appels** du contexte affiché, principal ou onglet du sous-agent (`renderCalls(owner)`, partagé par `renderContextBody` et `renderSubContext`) :
   - en tête : onglets (story 22), bascule d'affichage, bandeau du mode chat, `.ctx-total` (dernier appel, texte inchangé), total sans compression ;
   - un `section.ctx-call` par appel, `data-call-id`, titre « Appel {i} sur {n} » ;
   - ligne de chiffres « Lu : {prompt_tokens} tokens · évalués : {evaluated_tokens | « non communiqué »} · produits : {output_tokens} », avec « ≈ » si `usage_source === "estimate"`. En cours : « Lu : {approxTotal}{used} tokens · en cours ».
   Raison : point (4).
7. `app.js` (lecture groupée) -- Bloc « Lu » :
   - Si `seen_segments > 0`, un `details.ctx-seen`, fermé par défaut, résumé « Déjà lu à l'appel précédent · {k} sections · {seen_tokens} tokens », qui contient les sections `seen`. L'état ouvert est mémorisé par clé d'appel, comme `openReasoning`.
   - Puis les autres sections, en lignes `.ctx-section` sur une grille à deux colonnes :
     - marge : trait de couleur `data-discipline`, pastille de type, étiquette « {label_fr} · {brickName(brick) | « hors brique »} · {≈}{tokens} tokens », avec « · n segments » si n > 1 et « dont n de gabarit » si `template_tokens` ;
     - texte : un `pre` continu, un `span.ctx-seg[data-segment-id]` par segment, avec `title` « {label} · n tokens ».
   - Ligne `is-new` et badge « Nouveau » si `seen_segments > 0` ; aucun badge au premier appel.
   - Segment compressé : badge et « Texte avant compression » dans sa section.
   - Clés de liaison et focus de story 34 sur la ligne (voir Boundaries). Une étape « Appelle le modèle » d'un appel ancien éclaire désormais les sections de cet appel.
   Sous 28rem de volet, l'étiquette passe au-dessus du texte (requête de conteneur). Raison : point (1).
8. `app.js` (JSON, JS natif) -- Écrire `jsonTree(value, key)` : arbre de `details` et `summary` par objet ou tableau, ouvert par défaut ; clés, chaînes et littéraux dans les classes `.json-key`, `.json-string` et `.json-literal` ; l'état replié est gardé par clé. Écrire aussi `jsonSpans(text)` : objets ou tableaux non vides, équilibrés, sensibles aux chaînes, acceptés par `JSON.parse`, le premier gagnant, jamais imbriqués. Chaque bloc JSON a un bouton « Texte exact » qui montre la sous-chaîne envoyée.
   - En local, `jsonSpans` s'applique au texte exact de l'appel. Les sections qu'un même JSON touche se fusionnent en une ligne, dont la marge empile leurs étiquettes. Exemple : `<tools>` du gabarit Qwen3.5. Aucune fusion à travers la frontière `seen`, où le JSON reste en texte.
   - En mode chat, un fragment non gabarit est décodé pour l'affichage (`JSON.parse('"' + t + '"')`, texte brut si l'analyse échoue), puis passé à l'arbre s'il est lui-même du JSON, comme un résultat d'outil ou des arguments. Les sections de syntaxe JSON (gabarit) s'affichent en `ink-soft`.
   - Mémoriser les calculs par charge (`WeakMap`) ; reconstruire le volet seulement quand ce qu'il montre change, en gardant le focus et le défilement.
   Raison : point (2).
9. `app.js` (produit) -- Bloc « Produit par le modèle », après le « Lu » de chaque appel. Il vient de `ended`, ou des deltas en cours pour le dernier appel :
   - `div.ctx-produced.is-reasoning` : étiquette « Réflexion », `reasoningBlock(…, "ctx:{callId}")` replié ;
   - puis la note de `reasoning_cut`, s'il y en a une ;
   - `div.ctx-produced.is-answer` : « Réponse », `pre` ;
   - `div.ctx-produced.is-tool-call` : « Appel d'outil », `jsonTree({name, arguments})`, `arguments` décodé s'il est une chaîne JSON.
   Chaque bloc porte l'étiquette encre « Produit par le modèle ». Entre deux appels, une ligne du harnais : « Le harnais exécute {outils} ; le résultat est lu à l'appel {i+1}. » Pour une délégation, ajouter un bouton qui appelle `showSubContext`. Raison : point (3).
10. `app.js` (bascule) -- `div[role=group][aria-label="Affichage du contexte"]`, boutons `aria-pressed` : « Lecture groupée » (défaut), « Texte exact », et « Corps JSON » en mode chat seulement. Le choix est mémorisé par le navigateur (`wavestack.ctxMode`, try/catch) ; « Corps JSON » retombe sur « Lecture groupée » hors mode chat.
    - « Texte exact » : pour chaque appel, `pre.ctx-exact` (jointure des segments, ou `body`), puis `pre.ctx-raw` (`raw_output`, ou les deltas en cours). Aucune couleur ni marge. Le texte lu des appels antérieurs au dernier est dans un `details` fermé.
    - « Corps JSON » : `jsonTree(JSON.parse(body))` par appel.
    Raison : point (1), « Texte exact ».
11. `src/wavestack/web/static/app.css` -- Styles `.ctx-call`, `.ctx-view-mode`, `.ctx-section` (grille, trait `--segment-color` et discipline), `.is-new`, `.ctx-seen`, `.ctx-seg`, `.ctx-produced` (fond `produced-soft`, trait `ink`, étiquette sur `ink`, texte `on-ink`), `.is-reasoning` (fond `reasoning-soft`), `.json-*`, `.ctx-between`. Variables seulement. Raison : DESIGN.md.
12. EXPERIENCE.md, spine, SPEC.md, `tools/e2e/README.md` -- Mettre à jour :
    - EXPERIENCE.md : table des volets (Contexte LLM), description du volet, `reasoning-block`, `context-segment` (qui devient `context-section`), nouveaux `context-call` et `produced-block`, Streaming, « Modèle cloud actif » (trois affichages) et « Sous-agent au travail » ;
    - spine : AD-4 (sections et « déjà lu » calculés par la session, jointure = texte exact) et AD-9 (`sections`, `seen_segments`, `seen_tokens` par la fonction unique) ;
    - SPEC.md : succès de CAP-2 (« chaque appel du tour : ce qu'il a lu, puis ce qu'il a produit ») ;
    - README : scénarios et captures.
13. `tools/e2e/run_e2e.py` -- Adapter les vérifications de la Code Map à la nouvelle structure, sans en perdre l'intention (4 extraits RAG, 1 segment compressé, filet du prompt système). Ajouter les critères ci-dessous dans `s_native_tools`, `s_bare_llm` et `s_local_server`. Dans `s_linked_view`, remplacer `.ctx-segment` par `.ctx-section`. Captures : réécrire `05`, `19-sous-agent-delegation`, `22-rag`, `23-serveur-local`, `24-compression`, `31-disciplines-contexte` et `35-vue-liee-survol`. Ajouter `40-contexte-appels-numerotes`, `41-contexte-texte-exact` et `42-contexte-corps-json`. Si les numéros 40 à 42 sont déjà pris, prendre les suivants libres.

**Acceptance Criteria:**
- Given le scénario `native_tools` (faux cloud) et « Quelle heure est-il ? », when on lit Contexte LLM, then :
  - on voit deux `.ctx-call` titrés « Appel 1 sur 2 » et « Appel 2 sur 2 » ;
  - chaque titre correspond à `/Lu : ≈? ?[\d  ]+ tokens · évalués : (non communiqué|[\d  ]+) · produits : ≈? ?[\d  ]+/` ;
  - l'appel 2 a un `details.ctx-seen` fermé, dont le résumé correspond à `/Déjà lu à l'appel précédent · \d+ sections? · [\d  ]+ tokens/` ;
  - une `.ctx-section.is-new` avec le badge « Nouveau » contient « Résultats d'outils ».
- Given le même tour, when on lit les blocs produits, then :
  - l'appel 1 a un `.ctx-produced.is-tool-call` dont l'arbre a une `.json-key` « name » et une `.json-string` « get_datetime » ;
  - l'appel 2 a un `.ctx-produced.is-answer` qui contient « D'après le résultat » ;
  - le fond calculé d'un `.ctx-produced` vaut `--color-produced-soft`, différent de celui de toute `.ctx-section` ;
  - « Produit par le modèle » est visible.
- Given le même tour, when on clique « Texte exact », then le `textContent` de chaque `pre.ctx-exact` est égal au `body` du `context_rendered` de son appel, et `json.loads` de ce texte est égal au corps reçu par le faux fournisseur (`r.fake_calls()`). When on clique « Corps JSON », then un `.json-tree` montre la clé « messages ». Un clic sur son `summary` masque ses enfants, un second les réaffiche.
- Given `bare_llm` et « Bonjour [raisonne] », when on lit l'appel, then `.ctx-produced.is-reasoning` (fond `--color-reasoning-soft`) précède `.ctx-produced.is-answer`, dont le fond est différent. `.ctx-total` commence toujours par « Tour N · ».
- Given `local_server` (faux llama-server, gabarit Qwen3.5) et un tour avec `get_datetime`, when on lit Contexte LLM, then :
  - on voit deux appels, et la ligne des descriptions d'outils de l'appel 1 contient un `.json-tree` avec la clé « parameters » ;
  - en « Texte exact », chaque `pre.ctx-exact` est égal à `"".join(segments.text)` de son `context_rendered`, déjà vérifié égal au prompt reçu ;
  - Σ `sections.tokens` = `prompt_tokens` pour chaque appel, lu dans les événements.
- Given `subagent`, when on sélectionne l'onglet « Sous-agent subN », then ses appels sont numérotés de la même façon, et son appel 2, s'il existe, replie le déjà-lu. Revenu sur « Agent principal », une ligne entre les appels propose d'ouvrir l'onglet du sous-agent.
- Given un tour rejoué, when on clique « Comparer », then la comparaison est identique à avant la story, et les E2E `s_system_prompt`, `s_caveman` et `s_rag` restent verts.
- Given le tour Wikipédia de `s_linked_view`, when on survole la dernière étape « Appelle le modèle », then les `.ctx-section` de cet appel ont `.is-linked`. When on survole la carte Outils, then au moins une `.ctx-section` a `.is-linked`.

## Spec Change Log

## Review Triage Log

## Design Notes

**Sections (session).**
- La source d'un segment est `(kind, brick)` ; un `template` n'a pas de source.
- Un segment non gabarit rejoint la section courante s'il a la même source et que seuls des `template` l'en séparent : ces gabarits sont absorbés, et leurs tokens comptent dans `template_tokens`.
- Tout gabarit non absorbé forme sa section, fusionnée avec les gabarits voisins.
- Un segment à `label_fr` propre est toujours seul.
- La frontière `seen_segments` coupe toujours.
- `label_fr` = libellé du type, ou libellé propre ; `discipline` = `discipline_of` du premier segment non gabarit ; `seen` si `end <= seen_segments`.
- `seen_prefix` compare `(kind, brick, component, text)` dans l'ordre. `seen_tokens` = Σ des tokens des segments vus.

Exemple (appel 2 d'un tour à outil, local) :
```
[0 template][1 system_prompt][2 template][3 user_message][4 template][5 assistant_turn][6 template][7 tool_result][8 template]
seen_segments = 5 → sections: 0 | 1 | 2 | 3 | 4 (seen) ‖ 5 | 6 | 7 | 8 (nouveau)
```

**Jetons à ajouter (clair).** Le contraste vaut pour les deux fonds et pour `surface-raised` :
- `produced-soft #E8EEF7` : encre 16,9, `ink-soft` 7,4 ;
- `reasoning-soft #F3EFE3` : encre 17,1, `ink-soft` 7,5 ;
- `json-key #1E3A8A` : au moins 8,7 sur chaque fond doux ;
- `json-string #7A3410` : au moins 7,6 ;
- `json-literal #0B5E73` (nombres, booléens, `null`) : au moins 6,2.

L'étiquette « Produit par le modèle » est en `on-ink` sur `ink` (19,7). Les couleurs JSON sont des couleurs de texte seulement : elles ne reprennent aucune couleur de discipline.

**Pourquoi la fusion des lignes.** Le gabarit Qwen3.5 écrit chaque outil par `tojson`. La session n'entoure de sentinelles que les chaînes (`name` et `description`). La syntaxe JSON tombe donc dans le gabarit, et aucune section ne contient seule un schéma complet. Trouver le JSON sur le texte exact de l'appel, puis fusionner les sections qu'il touche, donne un arbre lisible sans rien retirer : la marge garde chaque source et ses tokens.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, avec les nouveaux tests de sections, de déjà-lu et de contrastes
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; les trois nouvelles captures sont écrites et les captures listées sont réécrites dans `tools/e2e/screenshots/`

**Manual checks (if no CLI):**
- Relire les captures : appels numérotés, déjà-lu replié, résultat d'outil « Nouveau », blocs produits sur leur fond, arbre JSON indenté, texte exact sans habillage.

## Décisions prises par défaut

- **Sections et tokens par section calculés par la session**, dans `gauge()` : la story veut les tokens par section, et AD-1 interdit la somme dans le navigateur.
- **Gabarit absorbé entre deux segments de même source**, compté à part (`template_tokens`). La somme des sections reste égale au total, et les descriptions d'outils forment une seule section au lieu de dix lignes.
- **Regroupement par `(kind, brick)`, pas par composant.** Tous les outils d'une brique forment une section ; le détail par segment reste au survol (`title`).
- **« Déjà lu »** : c'est le préfixe de segments identiques à l'appel précédent du **même contexte dans le même tour**, calculé par la session. Le premier appel d'un tour ne replie rien et n'a pas de badge « Nouveau ». L'historique des tours précédents n'est pas replié : la story parle des appels du tour.
- **Relance après une coupe du raisonnement** : c'est le même appel (un seul `context_rendered` et un seul `model_call_ended`). Elle est montrée comme une note du harnais dans l'appel, pas comme un appel numéroté.
- **Sortie du modèle relue** (`assistant_turn`) : elle garde le style « lu », avec son libellé « Sortie du modèle dans le tour ». Le fond « produit » est réservé à ce que l'appel lui-même a produit.
- **Détection du JSON côté interface.** C'est de la mise en forme, et le texte exact reste à un clic. Un JSON invalide reste du texte.
- **Mode chat.** La lecture groupée décode les chaînes JSON pour l'affichage. La troisième bascule, « Corps JSON », montre l'arbre du corps. « Texte exact » montre `body` tel quel.
- **Nouveaux jetons**, dont trois couleurs JSON distinctes des disciplines, pour ne pas brouiller le code couleur de story 33.
- **Bascule mémorisée par le navigateur**, comme « Afficher le raisonnement ». C'est un confort de lecture, pas un état du harnais.
- **`.ctx-total` gardé** : dernier appel, même texte. Il est lu par plusieurs E2E et par story 22.
- **« évalués »** : `evaluated_tokens`, ou « non communiqué » quand le moteur ou le fournisseur ne le dit pas. Jamais un écart calculé.
- **Texte exact des appels antérieurs replié**, pour ne pas répéter plusieurs fois un long prompt ouvert.
- **Captures 40 à 42**, après les captures 35 à 39 de la story 34.
- **Liaison par section**, pas par segment : un seul arrêt de tabulation par ligne, au lieu d'un par segment. Le segment reste identifiable par `data-segment-id` et par son infobulle.
- **Mode sombre** : les nouveaux jetons n'ont pas de jumeau sombre ici. La story 31, qui vient après, couvre tous les jetons présents dans `tokens.css` au moment de son implémentation (sa règle).

## À vérifier sur PC

- **Lecture d'un tour à outil**
  - **Geste** : sur Windows 11, dans Chrome puis Edge, lancer `uv run wavestack` (PowerShell), charger Qwen3.5-4B (GGUF) et choisir le scénario « Outils natifs ». Envoyer « Quelle heure est-il ? », puis regarder Contexte LLM.
  - **Attendu** : Appel 1 et Appel 2 ; au second, le déjà-lu est replié et le résultat d'outil marqué « Nouveau » ; réflexion, appel d'outil et réponse sur leur fond.
  - **Critère** : Anaël dit en moins de 10 s ce qui est nouveau à l'appel 2, et juge la vue plus claire que l'ancienne.
  - **Moyen** : à la main (œil humain).
- **Exactitude avec un vrai gabarit**
  - **Geste** : même tour, avec Qwen3.5-2B puis 4B, et avec Ollama. Script AppSession : lire les `context_rendered`, comparer `"".join(text)` au prompt envoyé et Σ `sections.tokens` à `prompt_tokens`. Puis, en Playwright (Chromium de `%LOCALAPPDATA%\ms-playwright`), comparer « Texte exact » à la jointure.
  - **Attendu** : égalités.
  - **Critère** : égalité octet pour octet ; écart de tokens nul.
  - **Moyen** : script AppSession et Playwright.
- **JSON des outils avec le vrai gabarit**
  - **Geste** : même tour, lecture groupée de l'appel 1.
  - **Attendu** : chaque schéma d'outil est en arbre indenté et repliable ; la marge nomme gabarit et descriptions d'outils.
  - **Critère** : autant d'arbres que d'outils décrits ; « Texte exact » d'un arbre est égal à la ligne JSON du prompt.
  - **Moyen** : Claude in Chrome ou à la main.
- **Modèle cloud réel**
  - **Geste** : avec Groq (vraie clé), faire le même tour, puis ouvrir « Corps JSON » et « Texte exact ».
  - **Attendu** : arbre lisible (messages, tools, arguments décodés) ; texte exact égal au corps envoyé.
  - **Critère** : `json.loads` du texte exact est égal au `body` de `context_rendered` ; aucune clé dans la page.
  - **Moyen** : Claude in Chrome.
- **Fluidité sur CPU**
  - **Geste** : scénario RAG et outils avec Qwen3.5-4B, contexte d'environ 3 500 tokens, trois appels, en streaming, dans Chrome et Edge. Onglet Performance des DevTools pendant la génération.
  - **Attendu** : le volet suit sans à-coups ; le défilement et les blocs dépliés restent en place.
  - **Critère** : aucune tâche longue de plus de 200 ms due au rendu de Contexte LLM ; déplié et défilement conservés.
  - **Moyen** : à la main (DevTools).
- **Coupe du raisonnement et taille de texte**
  - **Geste** : avec un budget de raisonnement bas (lot C), envoyer un prompt qui fait réfléchir longtemps, puis cliquer « Mode projection » (story 34), à 1366 × 768.
  - **Attendu** : réflexion, note « Raisonnement coupé par le harnais », puis réponse, dans un seul appel ; étiquettes de marge lisibles, sans défilement horizontal.
  - **Critère** : note placée entre les deux blocs ; aucun texte coupé.
  - **Moyen** : Claude in Chrome ou à la main.
