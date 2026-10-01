---
title: "Décisions d'Anaël appliquées"
type: 'feature'
created: '2026-10-01'
status: 'done'
route: 'dispatch'
baseline_commit: '2269793edb480b92807883613809b1b421ec92cf'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: ['multiple-goals']
deferred: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dix-neuf entrées de `deferred-work.md` attendent une décision d'Anaël (section « Décisions à prendre par Anaël » de `SPEC.md`, D1 à D19). Tant qu'elles restent ouvertes, le fichier ne dit pas ce qui est voulu (CAP-3).

**Approach:** Pour chaque Dn tranché (sauf D16, story 4), appliquer la décision, ou fermer l'entrée avec la décision quand elle est « non » ou « garder ». Chaque point ci-dessous ne s'applique **que si Anaël a choisi l'option indiquée** ; un autre choix est spécifié au plan à partir de sa réponse.

## Boundaries & Constraints

**Always:**
- Préalable : la réponse d'Anaël à chaque Dn est consignée (`SPEC.md` ou `.memlog.md`). Un Dn sans réponse reste ouvert, sans code.
- Fermetures sans code si la recommandation « non / garder » est suivie : **D1** (E007), **D2** (E010), **D8** (E061), **D10** (E079), **D12** (E081), **D13** (E087), **D14** (E088) — `resolution: décision d'Anaël du <date> — <décision>`.
- **D3 = oui** (E038) — quand « Afficher les actions forcées » passe à vrai, les listes d'options des briques qui ont un bouton « Forcer » se déplient ; l'interrupteur porte un titre de section et l'icône ✋, distinct des interrupteurs de briques. EXPERIENCE.md à jour.
- **D4 = prévenir** (E045) — la consigne de `mcp_full` (`content/scenarios.yaml` et surcouches) annonce un tour d'environ deux minutes sur un poste sans GPU et dit pourquoi.
- **D5 = oui** (E051) — sous la réponse d'un tour qui a appelé des outils, la Vue humain affiche « Outils consultés pendant ce tour : … », chaque nom lié à son étape d'Orchestration ; rien si aucun outil. EXPERIENCE.md à jour.
- **D6 = oui** (E052) — un 429 dont l'en-tête `x-ratelimit-limit-req-minute` vaut `0` donne « aucun quota actif sur ce compte : vérifiez le plan dans la console du fournisseur » ; ni attente ni nouvel essai ; section Never de `spec-11b-corrections-test-manuel-story-11.md` amendée (lecture permise pour ce message seul).
- **D7 = oui** (E060) — le tiroir de la mémoire globale affiche la date d'écriture (`created_at`) de chaque entrée, format court, fuseau du poste, langue de la session.
- **D9 = garder 300** (E062) — rien ici ; la mesure est faite par la story 7.
- **D11 = valider** (E080) et **D15 = valider** (E093) — retirer « à valider » d'AD-4 (H-1) et d'AD-21 dans ARCHITECTURE-SPINE ; fermer les entrées.
- **D17 = consigne** (E124) — la consigne du scénario Raisonnement annonce qu'un petit modèle réfléchit jusqu'au budget même pour un message simple.
- **D18 = réponses mesurées** (E126) — `tests/test_program.py` (`fits`) simule l'historique cumulé avec des réponses de la taille relevée au lot K (`resultats-lot-k-2026-09-29.md:127`, ≈ 500 tokens au plus) au lieu de la réserve ; le commentaire « deferred (spec of lot K) » est retiré.
- **D19 = accepter** (E139) — commentaire dans `wavestack.toml` et README : `hosting_text` et `notes_text` sont saisis par l'opérateur et affichés tels quels, dans toutes les langues.
- Tout texte nouveau en `fr`, `en`, `de`.

**Never:**
- Appliquer un Dn sans réponse d'Anaël, ou une option qu'il n'a pas choisie.
- Toucher à D16 / E121 (story 4) ou à la mesure de D9 (story 7).
- Changer le comportement de H1, H5, du budget de raisonnement ou de `MAX_CHARS`.

</frozen-after-approval>

## Code Map

Préalable vérifié : `SPEC.md:67-89`, « Tranchées le 2026-10-01 : Anaël suit les dix-neuf recommandations » ; chaque Dn de la colonne « Décision » est l'option ci-dessus.

- `_bmad-output/implementation-artifacts/deferred-work.md` -- entrées C par leur `summary` (les numéros de ligne de `triage.md` ont glissé) : E007 « Détail de la jauge » (l. 31), E010 « Repli hors ligne de `fetch_page` » (44), E038 « L'interrupteur « Afficher les actions forcées » » (168), E045 « Le tour du scénario « MCP en documentation complète » dépasse » (199), E051 « Aucune attribution visible » (225), E052 « Mistral répond 429 » (229), E060 « Le tiroir de la mémoire globale n'affiche pas » (263), E061 « Aucun ajout d'entrée depuis le tiroir » (267), E062 « Une mémoire globale pleine » (271), E079 « AD-13 : `transform_context` » (349), E080 « H-1 de la story 20 » (353), E081 « `compress()` de Headroom » (357), E087 « SOC : le garde-fou » (386), E088 « IAM et Souveraineté sans réseau » (390), E093 « AD-21 amendé » (412), E124 « Avec le 2B, le raisonnement » (562), E126 « Le test `fits` ne simule que l'échange précédent » (569, pas l'entrée close de la l. 450), E139 « L'avertissement et le bandeau d'un modèle cloud » (623). E121 (l. 549) n'est pas touchée.
- `src/wavestack/web/static/app.js` -- D3 : `forcedToggle()` (l. 1582), `brickOptions()` (l. 1481 ; clé d'ouverture `options:${brick.id}` dans `store.openExplanations`), `forceButton()` (l. 1626 : `null` sans libellé `FORCE_LABELS[brick.id]`, et pour MCP hors lazy sauf `option.calls`), appel dans `renderBricks()` (l. 1148). D5 : `renderChat()` (l. 2933, bulle `.bubble-model` reconstruite à chaque rendu, focus rendu par `data-focus-key`), `turn.steps` (étape `type === "tool"`, `started.tool`, `started.source`), clé de ligne d'Orchestration `${turn.id}:${i}` (`stepRows`, l. 5062), `toolLabel()` (l. 4833), `stepLinks()` (l. 5049), modèle d'ouverture `revealOutbound()` (l. 5711 : volet Orchestration montré, tour déplié, vue figée, `userOpen`, `selected`, `renderSteps`). D7 : `renderMemoryDrawer()` (l. 2090, en-tête `memory-entry-head`), `dateTimeFormat` déjà importé de `i18n.js` (locale `fr-FR`/`en-GB`/`de-DE`, fuseau du navigateur).
- `src/wavestack/web/static/app.css` -- `.force-toggle` (l. 2525), `.brick-group-title` (l. 2307) à réutiliser pour le titre ; `.memory-entry-head` / `.memory-entry-source` (l. 2826-2839).
- `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- `main.force` (l. 162), `main.memory` (l. 193), `main.chat` ; parité stricte des clés et variables (`tests/test_ui_texts.py`), guillemets “…” / „…“ en `en` / `de`, « Sie ».
- `src/wavestack/models/openai_chat.py` -- `_refused()`, branche 429 (l. 488-526) ; `_text`, `_error`, `_BACK_TO_LOCAL_FR` ; docstring de `pace()` (l. 201) inchangée (l'espacement ne lit toujours pas les en-têtes).
- `content/messages.yaml` (+ `en`, `de`) -- `models.openai_chat.quota_refused` (l. 1148) : nouvelle clé voisine ; parité stricte (`tests/test_backend_messages.py`, `tests/test_i18n.py`).
- `tests/test_cloud.py` -- modèle : `test_unknown_quota_names_the_three_scopes` (l. 861), `_cloud_session`, `Provider`, `_turn`, `_of`.
- `_bmad-output/implementation-artifacts/spec-11b-corrections-test-manuel-story-11.md` -- l. 63 et Never l. 80.
- `content/scenarios.yaml` (+ `en`, `de`) -- `reasoning.description_text` (l. 70-80), `mcp_full.description_text` (l. 189-204).
- `ARCHITECTURE-SPINE.md` -- AD-4, l. 212 (« *Décision provisoire, à valider (story 20, H-1)…* ») ; AD-21, l. 607 (« *Décision provisoire, à valider (story 16, hypothèse 1)…* »). Ne pas toucher l. 289 (story 24, hors périmètre) ni l. 481/854.
- `tests/test_program.py` -- commentaire l. 76-84, docstring l. 604-609, boucle l. 663-682 (`history = prompt + kept + reserve + EXCHANGE_TEMPLATE`).
- `wavestack.toml` (`[cloud]`, l. 238-242) et `README.md` (« Ajouter un modèle », l. 832-860).
- `EXPERIENCE.md` -- l. 161 (bouton Forcer), l. 162 (tiroir d'édition, mémoire globale), l. 165 (messages de la Vue humain).
- `tools/e2e/run_e2e.py` -- `s_forced_native` (l. 3701), `s_global_memory` (l. 3800, tiroir l. 3892-3903), `Run.show_forced` (l. 303), `_step` (l. 2191).

## Tasks & Acceptance

**Execution:**
- [x] `app.js`, `app.css`, `ui.yaml` ×3 -- D3 : l'interrupteur devient une section titrée (« Actions forcées », titre au style des titres de groupe), l'icône ✋ devant son libellé, dans un cadre qui le distingue des cartes ; au passage à vrai, ajouter `options:{id}` à `store.openExplanations` pour chaque brique dont la liste porte au moins un bouton Forcer (même règle que `forceButton`, appels MCP compris) -- les boutons sont dans la liste qu'on vient d'ouvrir.
- [x] `app.js`, `app.css`, `ui.yaml` ×3 -- D5 : dans la bulle du modèle, après le texte et les notes, une ligne « Outils consultés pendant ce tour : » suivie d'un bouton par étape d'outil du tour (hors outils du harnais `load_skill`, `load_tool_doc`, `remember` ; la délégation au sous-agent comprise), nommé par `toolLabel`, porteur de `stepLinks` ; un clic ouvre et sélectionne l'étape dans Orchestration (fonction tirée de `revealOutbound`) et la fait défiler à l'écran. Aucune ligne sans étape d'outil.
- [x] `app.js`, `app.css`, `ui.yaml` ×3 -- D7 : dans `memory-entry-head`, un `<time datetime="{created_at}">` au format court de la langue (`dateStyle` et `timeStyle` courts), à côté de l'origine ; rien si la date est illisible.
- [x] `openai_chat.py`, `messages.yaml` ×3 -- D6 : 429 et `x-ratelimit-limit-req-minute` égal à `0` → message `models.openai_chat.no_quota`, indices réduits au retour au modèle local, `retry_after_s` et `quota_scope` nuls ; tout autre 429 inchangé.
- [x] `tests/test_cloud.py` -- D6 : le 429 sans quota de la sonde du 2026-09-26 (corps et en-têtes) donne le message, ni « Attendez », ni `min_interval_s`, une seule requête ; un en-tête non nul garde l'ancien message ; message vérifié en `en` et `de`.
- [x] `spec-11b-…md` -- D6 : l. 63 et Never amendées (lecture de `x-ratelimit-limit-req-minute` permise pour ce message seul, D6 du 2026-10-01).
- [x] `scenarios.yaml` ×3 -- D4 et D17 : une phrase dans chaque consigne.
- [x] `tests/test_scenarios.py` -- D4 et D17 : les consignes des trois langues portent l'annonce (durée de `mcp_full`, réflexion jusqu'au budget).
- [x] `ARCHITECTURE-SPINE.md` -- D11, D15 : les deux mentions deviennent « Décision validée par Anaël le 2026-10-01 (… D11 / D15) ».
- [x] `tests/test_program.py` -- D18 : réponses à la taille mesurée (`MEASURED_ANSWERS = (500, 250)`) au lieu de la réserve ; l'historique cumule chaque échange (`prompt + kept + answer + EXCHANGE_TEMPLATE`) au tokenizer du GGUF, l'échange précédent seul à l'estimation de 2 caractères par token (voir Spec Change Log) ; commentaire et docstring réécrits, « deferred » retiré.
- [x] `wavestack.toml`, `README.md` -- D19 : commentaire et phrase.
- [x] `EXPERIENCE.md` -- D3, D5, D7.
- [x] `tools/e2e/run_e2e.py` -- contrôles écrits, non lancés : D3 dans `s_forced_native` (liste « Outils » ouverte sans clic après l'interrupteur, titre et ✋ présents), D5 dans `s_forced_native` (ligne et bouton « Calculatrice » sous la réponse, clic → étape dépliée ; « Bonjour » sans outil → aucune ligne), D7 dans `s_global_memory` (chaque entrée du tiroir porte un `time` dont `datetime` vaut `created_at` de `memory.json`).
- [x] `deferred-work.md` -- `resolution:` pour D1, D2, D8, D9, D10, D12, D13, D14 ; `closed: 2026-10-01 (story 3 des restes différés) — <preuve>` pour D3, D4, D5, D6, D7, D11, D15, D17, D18, D19. E121 intacte.

**Acceptance Criteria:**
- Given les 18 entrées C hors E121, when on lit `deferred-work.md`, then chacune porte `closed:` ou `resolution:` qui cite sa décision.
- Given un modèle cloud qui répond 429 avec `x-ratelimit-limit-req-minute: 0`, when un tour part, then `harness_error` dit « aucun quota actif sur ce compte : vérifiez le plan dans la console du fournisseur », sans indice d'attente ni d'espacement, et une seule requête est partie.
- Given `tests/test_program.py` sans `WAVESTACK_TEST_GGUF`, when le test `fits` tourne, then chaque prompt tient avec l'échange précédent à réponse mesurée ; avec `WAVESTACK_TEST_GGUF` (PC, story 7), avec l'historique cumulé à réponses mesurées.

## Implementation Notes

- Implémenté directement par l'agent de la session (mode nuit) plutôt que par un sous-agent : les contraintes du poste (pytest ciblé seulement, ni serveur, ni E2E, ni modèle réel) ne sont pas dans la spec, et un sous-agent neuf aurait pu lancer la suite complète.
- D3 : `optionForceLabel` extrait de `forceButton` (même règle, sans créer de bouton) ; `hasOptionForce` s'en sert. Titre de section en classe propre `.force-section-title` : l'E2E `disciplines` lit les titres des deux groupes par `.brick-group-title`.
- D5 : `consultedTools`, `consultedLine`, `revealStep` (après `renderChat`) ; libellé de la délégation : `main.orch.sub.title`.
- D6 : `_no_quota(response)` avant la branche 429 ; `pace()` ne lit toujours aucun en-tête.
- D7 : `memoryDate()` ; le `<time>` est placé dans la même `span` que l'origine (« démonstration · 01/10/2026 22:41 »), l'en-tête gardant ses deux blocs.
- D18 : à 500 tokens par réponse, le test cumulé déborde en mode estimation (`subagent` p3 : 1 848 × 1,1 + 1 752 > 3 584) ; avec les tailles relevées par échange (500 puis 250), encore p4 (1 848 × 1,1 + 1 824). L'estimation à 2 caractères par token compte le contexte de `subagent` 40 % trop haut (1 848 contre 1 326 exact). D'où le partage : cumul au tokenizer du GGUF, échange précédent seul en estimation. Mesures du mode estimation : `subagent` historique 1 138 / 324 / 330 ; cumul simulé 1 792, soit ≈ 3 118 / 3 584 au compte exact de 1 326 (la jauge réelle lisait 2 997).
- Tests lancés : `test_cloud`, `test_content_language`, `test_program` (168 passés) ; `test_ui_texts`, `test_backend_messages`, `test_i18n`, `test_scenarios` (3 319 passés) ; `test_web_tokens` (19 passés) ; `ruff check .` et `ruff format --check .` propres ; `node --check app.js` sans erreur. Contrôles E2E écrits, non joués (mode nuit).

## Spec Change Log

- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : spec approuvée (option « Approve and continue ») ; elle suit les décisions D1 à D19 consignées dans `SPEC.md`. Choix produits non couverts par les décisions, pris au plus prudent et réversible : (1) D5 ne liste que les outils dont le résultat informe la réponse (natifs, MCP, délégation au sous-agent), pas `load_skill`, `load_tool_doc` ni `remember` ; un nom par étape ; (2) D3 déplie les listes au seul passage à vrai, l'animateur peut les replier ; (3) D7 : date et heure courtes. Taille au-dessus de 1 600 tokens, sous 4 000 : pas de question (fait persistant du projet).
- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : D18 appliqué en deux modes (cumul au tokenizer du GGUF, échange précédent seul en estimation à 2 caractères par token), parce que le cumul déborde en estimation pour une raison qui n'est pas l'historique (contexte de `subagent` compté 40 % trop haut). Réponses mesurées par échange (500 puis 250) plutôt qu'une taille unique de 500 : « la taille relevée au lot K ». Tâche et critère d'acceptation amendés en conséquence (hors bloc gelé). Réversible : une ligne de `test_program.py`.

## Review Triage Log

| # | Couche | Constat | Verdict | Preuve / suite |
|---|---|---|---|---|
| 1 | aveugle, cas limites | D5 liste un outil en erreur, refusé ou en cours | medium | `consultedTools` ne filtrait que `type` et `started` ; corrigé (patch) : `ended.status === "ok"` seulement. |
| 2 | aveugle, cas limites | D3 ne déplie pas après rechargement (interrupteur mémorisé), après « Réinitialiser », ni pour des appels MCP arrivés ensuite | low | Réel, mais l'intention dit « passe à vrai » et l'animateur qui a déjà allumé l'interrupteur connaît les boutons ; le correctif ajoute un état (`forcedUnfolded`). Rejeté (low, correctif non direct) ; signalé comme choix de nuit dans l'entrée E038. |
| 3 | aveugle, écarts de vérification | `closed:` sur D3, D5, D7 avec des contrôles E2E non joués | medium | Contraire à « une entrée n'est fermée qu'avec sa preuve » ; corrigé (patch) : `resolution: … preuve E2E en attente`, fermeture sur le résultat de la batterie finale. |
| 4 | aveugle, écarts de vérification, cas limites | D18 affaiblit le test par défaut (réponse 500/250 au lieu de la réserve en estimation) | medium | Vrai pour p3 et suivants ; corrigé (patch) : en estimation, échange précédent à la réserve comme avant. |
| 5 | écarts de vérification | D18 : cumul vérifié seulement avec `WAVESTACK_TEST_GGUF` | medium (non vérifié) | Le mode exact demande le 2B sur le PC ; reporté (defer) : nouvelle entrée de `deferred-work.md`, et E126 passe en `resolution:` qui se ferme sur ce passage (story 7). |
| 6 | aveugle | Ligne D19 collée à l'entrée suivante sans ligne vide | false | Préexistant : l'entrée E139 et la suivante n'étaient déjà séparées par aucune ligne vide ; l'insertion n'a rien changé à la séparation. |
| 7 | aveugle | D1 non reporté dans EXPERIENCE.md et DESIGN.md (`context-gauge-detail` toujours à construire) | low | Réel ; corrigé (patch) : les deux mentions disent « abandonné (D1) ; ne pas construire » (frontmatter de DESIGN.md non touché). |
| 8 | aveugle | Ligne « Bouton Forcer » d'EXPERIENCE.md sans les outils ni « Forcer l'appel » | low | Réel ; corrigé (patch) : emplacements et libellés complétés, section « au-dessus des deux groupes de cartes ». |
| 9 | aveugle | D17 généralise un constat sur un modèle à tout petit modèle ; « le tour reste long » sans dire « raisonnement allumé » | false | Texte de la décision D17 (« un petit modèle réfléchit même pour rien ») ; dans ce scénario la brique Raisonnement est allumée. |
| 10 | aveugle | D4 : « relit » faux au premier tour ; deux minutes valent pour le modèle local seulement | low | Réel ; corrigé (patch) : « lit d'abord », « avec le modèle local » (fr, en, de). |
| 11 | aveugle | Blocs YAML non réenroulés après l'insertion | low | Cosmétique, correction directe (patch) : lignes réenroulées dans `mcp_full` (fr, en, de) et `reasoning` (de). |
| 12 | aveugle | `no_quota` : virgule entre deux propositions | low | Correction directe (patch) : « {provider} refuse l'appel. Aucun quota actif sur ce compte : vérifiez… » (et en, de) ; la phrase de la décision est gardée. |
| 13 | aveugle | Le test D4/D17 passe par `localized_path` au lieu de `config.content_file` ; mots trop génériques | low | Correction directe (patch) : `config.content_file`. Mots génériques : faux (chaque liste combine des expressions propres à la phrase). |
| 14 | aveugle | « Bonjour » sans outil instable avec un vrai modèle | false | L'E2E joue le faux modèle (`tools/e2e/fake_openai.py`), qui n'appelle aucun outil sur « Bonjour ». |
| 15 | aveugle | Choix produits de nuit non signalés là où Anaël relira | low | Correction directe (patch) : chaque entrée D3, D5, D7 dit « Choix de nuit, à confirmer par Anaël : … ». |
| 16 | aveugle | Section Verification sans `test_global_memory.py` ni quarts | false | Le correctif serait d'éditer la spec de cette story (rejeté par règle) ; D7 ne touche aucun code Python de la mémoire. |
| 17 | aveugle | D19 : commentaire du TOML et README divergents ; changement de langue en séance oublié | low | Correction directe (patch) : le TOML renvoie à `settings.json` (même id), les deux disent « même après un changement de langue en cours de séance ». |
| 18 | aveugle | Outil appelé plusieurs fois : noms répétés indiscernables | low | Rare en démonstration ; le correctif ajoute une numérotation (branches). Rejeté (low) ; signalé comme choix de nuit dans E051. |
| 19 | écarts de vérification | Filtre du harnais, délégation et dépliement MCP sans contrôle | medium | Lacune vérifiée ; corrigé (patch) : contrôles E2E dans `s_global_memory` (aucune ligne après `remember` forcé), `s_subagent` (délégation nommée), `s_mcp_lazy` (liste MCP dépliée). Écrits, non joués. |
| 20 | écarts de vérification | `revealStep` et un clic direct sur une délégation pourraient lier des éléments différents | false | `delegateRow` ne pose pas `links` : `turnRows` lui donne `stepLinks(step)`, les mêmes clés que `revealStep`. |
| 21 | cas limites | Clic perdu sur un lien d'outil pendant un tour (bulles reconstruites à chaque rendu) | medium | Réel : `renderChat` recrée chaque bulle ; corrigé (patch) : action au `pointerdown` de la souris, comme `selectOnActivate`, au `click` pour clavier et tactile. |
| 22 | cas limites | `created_at` sans heure ni décalage, écrit à la main, lu en UTC | low | Le harnais écrit toujours l'ISO complet avec décalage (`memory.py:150`) ; cas d'une édition manuelle ; garde supplémentaire. Rejeté (low). |

## Design Notes

- D3 : déplier, c'est écrire les clés `options:{id}` dans `store.openExplanations` au clic sur l'interrupteur, puis reconstruire (`renderedBricks = null`) ; aucun état neuf. Une brique sans bouton dans sa liste (Forcer porté par la carte : mémoire globale, sous-agent) n'est pas concernée.
- D5 : la ligne est dans la bulle (pas un `.bubble` à part : les contrôles E2E comptent les bulles). Les boutons portent `data-focus-key` `tools:{turn}:{i}` pour que le focus survive à la reconstruction de la bulle.
- D18 : 500 puis 250 = les réponses relevées au lot K (470, puis 245, 223, 213 tokens) arrondies vers le haut ; le résultat d'outil gardé reste borné comme avant (quiz inchangés).

## Verification

**Commands:**
- `uv run ruff check <fichiers touchés>` et `uv run ruff format --check <fichiers touchés>` -- expected: aucun écart.
- `uv run pytest -q tests/test_cloud.py tests/test_ui_texts.py tests/test_backend_messages.py tests/test_i18n.py tests/test_scenarios.py tests/test_content_language.py` -- expected: tout passe.
- `uv run pytest -q tests/test_program.py` -- expected: tout passe (2 caractères par token, sans GGUF).
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur de syntaxe.

**Manual checks (if no CLI):**
- E2E (avec l'accord d'Anaël, batterie finale) : tranches `forced_native`, `global_memory`, `cloud`, `ui_language` -- 0 échec, contrôles D3, D5, D7 compris.
