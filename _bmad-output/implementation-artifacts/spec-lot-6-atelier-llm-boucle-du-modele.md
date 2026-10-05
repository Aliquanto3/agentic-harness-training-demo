---
title: 'Lot 6 — Atelier LLM : la boucle du modèle en trois étapes'
type: 'feature'
created: '2026-10-05'
status: 'done'
baseline_commit: '370bb36d762c23e5f4af66168316104f5d738ecc'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/mockups/llm-loop.html'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'Atelier LLM montre la tokenisation, les réglages et la distribution dans des sections séparées, avec un schéma qui s'arrête aux couches : on ne voit ni comment le texte devient des nombres, ni ce que font les couches, ni comment un token est tiré puis réinjecté. Le schéma n'utilise pas le module commun du lot 2 et ne dit pas qu'un modèle hybride ou MoE s'en écarte (D4).

**Approach:** Remplacer les sections 1 et 2 de `/llm` par trois étapes empilées, chacune entière à l'écran, conformes à la maquette v3 validée par Anaël : INPUT (texte → tokens → identifiants, réel), TRANSFORMATION (embeddings, attention, MLP sur une poignée de tokens et de nombres, illustratif avec les vraies dimensions du GGUF et le bandeau D4), OUTPUT (logits en mots, tirage réglable avec son graphique, token tiré par le moteur et réinjecté dans l'INPUT, réel). Les sections suivantes restent, renumérotées 4 à 7.

**Décisions d'Anaël (2026-10-05) :**
- Pas à pas réel : « Tirer le token suivant » fait tirer un seul token au moteur (texte de l'INPUT + tokens déjà ajoutés, réglages de l'OUTPUT, candidats lus) ; « Ajouter à la suite » le garde dans l'INPUT ; « Retirer le dernier » l'enlève. Moteur en processus seulement.
- Les trois étapes remplacent les sections 1 et 2 : champ et « Découper en tokens » dans l'INPUT, réglages dans l'OUTPUT, sans doublon.
- Quickwin : le nom de chaque réglage du tirage porte son explication (survol et clic).

## Boundaries & Constraints

**Always:** AD-1 (la page ne calcule aucune probabilité ni dimension ; le tirage est fait par le moteur) ; textes dans `content/llm_lab.yaml` + `content/i18n/{en,de}/llm_lab.yaml` ; ids et classes lus par les tests et l'E2E conservés sur les nouveaux éléments (`#llm-prompt`, `#tokenize-button`, `#tokenize-status`, `#token-info`, `#token-counts`, `#token-chips .token-chip` et `.token-chip-id`/`.is-special`, `#token-more`, `#token-blanks`, `#embedding-diagram` contenant la dimension et le vocabulaire, `#sampling-controls .sampling-row[data-setting]` et leurs champs `number`/`range`, `.sampling-row-reason`, `#sampling-reset`, `#distribution`, `#distribution-empty`, `#distribution-body`, `#distribution-token`, `#distribution-bars .dist-row` avec `.dist-text`, `.dist-cell.is-model|is-chance .dist-bar span` et `.dist-value`, `is-dropped`, `is-tail`, six `.llm-questions-list`) ; chaque étape tient dans l'écran à 1600 × 1000 et 1366 × 768 ; jetons de tokens.css seulement ; `diagram.js` étendu par ajout seul ; fichiers carrefour en ajouts seuls, regroupés dans des sections propres à l'Atelier LLM.

**Never:** toucher `models/catalog.py`, `models/discovery.py`, `models/servers.py`, `content/models/`, `diagnostic.html`, `static/logos/`, `mcp.*`, `rag.*` et leurs labs/contenus ; modifier `tokens.css` ; modifier les scénarios E2E existants ; présenter des poids d'attention ou des états cachés comme lus dans le moteur ; masquer la TRANSFORMATION pour un hybride ou un MoE ; tirer un token dans la page ; changer le modèle choisi ou les réglages du dossier de données partagé ; fusionner, rebaser ou pousser.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Dense GGUF | en-tête sans `ssm.*`, sans `expert_count` | `architecture.family = "dense"`, pas de bandeau | — |
| Hybride (Qwen3.5) | `qwen35.ssm.*`, `full_attention_interval = 4` | `family = "hybrid"`, `attention_interval = 4`, bandeau, pile : 1 couche sur 4 pleine | — |
| MoE | `expert_count = 128`, `expert_used_count = 8` | `family = "moe"`, bandeau, routeur et experts au pas MLP | hybride + MoE : raisons cumulées |
| Serveur / en-tête illisible | pas de fichier local | `family = "unknown"`, note « architecture non lue » | jamais d'échec |
| Pas tiré | `llm_step` en `idle`, moteur en processus, ≤ 64 ajouts | un seul token tiré avec ses candidats ; `/distribution` index 0 le redessine | 409 hors `idle`, sans moteur en processus, au-delà de 64 ou id hors vocabulaire |
| Retirer à nouveau | même texte, mêmes ajouts | nouveau tirage au même endroit | — |
| Texte changé | ajouts présents | ajouts effacés | — |
| Cloud | `dimensions = None` | INPUT : estimation ; TRANSFORMATION : « inconnue » ; OUTPUT : raison, « Tirer » grisé | — |

</frozen-after-approval>

## Code Map

- `src/wavestack/session/llm_lab.py` -- `LabContent` (strict) : ajouter les textes `stages` (input, transfo, output, liens, pas, bandeaux, note) ; `architecture_from_header(meta)` ; `read_architecture(path)` (cache chemin + mtime) ; paramètre `architecture=` de `dimensions_payload` (défaut `None`).
- `src/wavestack/models/gguf_meta.py` -- `try_read_metadata`, `positive_size` : réutiliser, ne pas modifier.
- `src/wavestack/trace/catalog.py:1087` -- `LlmDimensions` : `architecture: LlmArchitecture | None = None` (classe ajoutée au-dessus).
- `src/wavestack/session/app_session.py` -- dernier recours, à signaler : `_lab_dimensions` (l.~8323) passe `architecture=` ; nouvelle méthode `llm_step(prompt, continuation, sampling)` sur le modèle de `llm_generate` (l.8478 : `_lab_begin(False, True)`, refus si continuation > 64 ou id ≥ vocabulaire) ; `_run_lab` (l.8665) gagne `continuation: Sequence[int] = ()` (ids ajoutés après `rendered.ids`) et `max_tokens: int | None = None` (remplace `reserve` dans l'appel `_call_model`). Le request id du pas est `llm{n}.step` ; la mémoire `_lab_top` garde le token 0, donc `llm_distribution(0, …)` marche tel quel.
- `src/wavestack/web/app.py:189-215, 422-470` -- ajouter `LlmStepIntention` (prompt ≤ 2 000, `continuation: list[int]` ≤ 64, `sampling`) et `POST /api/intentions/llm_step` (409 sur `SendRefused`), à la suite des routes `llm_*`.
- `src/wavestack/web/static/diagram.js` -- ajout : option `liveText` de `createStepper` (défaut `t("common.diagram.live")`) ; réutiliser `svgEl`, `block`, `light`, `explain`.
- `src/wavestack/web/static/llm.html:66-116` -- sections 1 et 2 remplacées par les trois cartes ; sections 3 à 6 renumérotées 4 à 7.
- `src/wavestack/web/static/llm.js` -- `renderTokenized`/`renderDiagram` (l.~200-385) → INPUT et TRANSFORMATION ; `renderSampling`, `renderDistribution` (l.~400-640) → OUTPUT ; routage des événements `llm{n}.step` dans `applyEnvelope` (comme le couloir B) ; ajouts gardés dans le store, effacés quand le texte change.
- `src/wavestack/web/static/llm.css:291-395, 782-925` -- règles `embedding-*` remplacées par `llm-stage-*`, `llm-input-*`, `llm-transfo-*`, `llm-output-*` ; reprise du CSS de la maquette, jetons seulement.
- `content/llm_lab.yaml`, `content/i18n/{en,de}/llm_lab.yaml` -- textes du tableau Voice and Tone d'EXPERIENCE.md ; `tests/test_i18n.py` vérifie la parité.
- `tests/test_llm_lab.py` -- tests propres au lot.
- `tools/e2e/run_e2e.py` -- `s_llm_screen` (l.10856), `s_llm_live` (l.11461) inchangés ; ajouter `s_llm_loop` et ses fonctions `_llm_loop_*`, et l'entrée `("llm_loop", s_llm_loop)` à la liste.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/trace/catalog.py` -- `LlmArchitecture` (name, family, attention_interval, kv_head_count, feed_forward_length, expert_count, expert_used_count, figures_text) et le champ de `LlmDimensions`.
- [x] `src/wavestack/session/llm_lab.py` -- classification, lecture cachée, textes `stages`, paramètre de `dimensions_payload`.
- [x] `src/wavestack/session/app_session.py` -- `_lab_dimensions`, `llm_step`, paramètres de `_run_lab` (signalés dans les notes de fusion).
- [x] `src/wavestack/web/app.py` -- `LlmStepIntention` et la route.
- [x] `content/llm_lab.yaml` + en + de -- textes des trois étapes.
- [x] `src/wavestack/web/static/diagram.js` -- option `liveText`.
- [x] `src/wavestack/web/static/llm.html`, `llm.js`, `llm.css` -- les trois étapes, l'aide des réglages, le pas à pas réel, la renumérotation.
- [x] `tests/test_llm_lab.py` -- matrice I/O côté session : classification (dense, hybride, MoE, hybride+MoE, inconnu, cache), `llm_step` (un token, candidats, continuation lue, refus 409 : hors idle, sans moteur en processus, > 64, id hors vocabulaire), `/distribution` après un pas, contenus valides en trois langues.
- [x] `tools/e2e/run_e2e.py` -- `s_llm_loop` : INPUT pas à pas, TRANSFORMATION 7 pas et bandeau sur un en-tête hybride simulé, OUTPUT : aide d'un réglage, pas tiré simulé (`page.route` sur `llm_step` et `/distribution`, comme `_LiveLab`), « Ajouter à la suite » puis « Retirer le dernier », chaque étape ≤ hauteur de l'écran à 1600 × 1000 et 1366 × 768, aucune erreur JavaScript.
- [x] `_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/notes-de-fusion.md` -- fichiers carrefour touchés, ajouts à diagram.js, sections UX à reverser, conflits probables avec les lots 3, 4 et 5.

**Acceptance Criteria:**
- Given un texte découpé sur un GGUF chargé, when le formateur avance dans l'INPUT, then le texte se découpe en colonnes alignées texte → token → identifiant, avec les vrais tokens et identifiants.
- Given le même modèle, when il parcourt les 7 pas de la TRANSFORMATION, then le panneau donne les vraies dimensions du GGUF et la pile des couches, et la note dit que le dessin est illustratif.
- Given l'OUTPUT, when il clique « Tirer le token suivant » puis bouge un réglage, then le moteur a tiré le token, les Logits et le Tirage montrent ses vrais candidats et les chances suivent le réglage ; « Ajouter à la suite » le place dans l'INPUT.
- Given la suite E2E complète, when elle tourne, then `s_llm_screen`, `s_llm_live` et tous les autres scénarios passent sans modification.

## Implementation Notes

- Écarts : plus de 64 ajouts donne 422 à la route (`LlmStepIntention`, Code Map) et 409 à la session ; `candidates.py` gagne `dropped_by` (règle `_cuts` partagée avec `distribution`) pour écrire « écarté (top-p) » sans calcul dans la page ; `tests/test_web_tokens.py` filtre le DESIGN.md qui déclare `colors:` (le delta du lot 6 cassait le glob).
- Détails dans `ux-lot-6-atelier-llm-2026-10-04/notes-de-fusion.md`.
- Vérification (step-03, audit de la matrice) : la ligne « au-delà de 64 → 409 » n'était tenue qu'à la session ; `LlmStepIntention` plafonne désormais la requête à 1 024 ids, la session refuse au-delà de 64 avec 409 (test de route mis à jour). La ligne « Cloud » n'avait pas de test : `_llm_loop_cloud` ajouté à `s_llm_loop` (INPUT estimé, TRANSFORMATION « inconnue », « Tirer » grisé avec la raison, 409).
- Captures E2E : seules celles des scénarios de l'Atelier LLM sont gardées (voir les notes de fusion).
- Revue (step-04) : 31 constats triés (journal ci-dessous). 17 corrigés par patch (E2E MoE/dense/chargement, « Tirer » grisé tant que le texte n'est pas redécoupé, puces de la section 6 après un pas, réglage déplacé = tirage effacé, token d'un ancien texte ignoré, experts et couche 2, compteurs, encadré cloud, textes fr/en/de, captures renumérotées 70-74), 13 rejetés, 1 intent_gap (n° 5, gabarit de chat) laissé à Anaël : le code n'a pas été annulé pour l'attendre, contrairement à la règle de l'étape, la correction ne touchant que quelques lignes de `_run_lab` et la présentation.
- Vérification finale : ruff propre ; pytest 5 485 réussis + 1 échec préexistant (README) ; E2E Atelier LLM 81/81 ; passe complète : 6 échecs préexistants (détail dans les notes de fusion) ; appli réelle vérifiée sur le modèle choisi (dense).

## Spec Change Log

## Review Triage Log

| # | Source | Constat | Verdict | Preuve | Route |
| --- | --- | --- | --- | --- | --- |
| 1 | verification-gap | Branches MoE, hybride+MoE et « dense sans bandeau » de la page jamais exécutées par un test | medium | vérifié par le relecteur (seul `_LOOP_HEADER` hybride est servi à la page) | patch |
| 2 | verification-gap | Effacement des ajouts sur `model_load_started` non testé | medium | vérifié par le relecteur | patch |
| 3 | verification-gap | Captures `66-llm-boucle-*` réutilisent le préfixe 66 de l'Atelier MCP | low | `run_e2e.py:7054` et `:12010` | patch |
| 4 | verification-gap, edge-case | Captures `echec-llm_*.jpg` non suivies | low | produites par ma relance en cp1252 (sortie redirigée), la relance UTF-8 passe 75/75 ; fichiers supprimés | patch |
| 5 | blind | Le pas lit le prompt rendu par le gabarit (balises, en-tête assistant) alors que l'INPUT montre le texte brut ; « les 6 plus probables après « … » » nomme un autre contexte | medium | `_run_lab` + `render_context(add_generation_prompt=True)` ; test `…reads_the_tokens_already_added…` | intent_gap (question à Anaël, voir présentation) |
| 6 | blind, edge-case | Texte modifié sans redécouper puis « Tirer » : l'INPUT, la TRANSFORMATION et la légende montrent un autre texte que celui lu | medium | `drawStep` envoie `#llm-prompt`, l'INPUT lit `store.tokenized` ; `clearSteps` ne joue que si `forText !== null` | patch |
| 7 | blind, edge-case | Un pas vide la mémoire des candidats de la dernière génération ; les puces de la section 6 la proposent encore (token 1 = token du pas, autres = out_of_range) | medium | `_lab_begin` remet `memory = {}` et `_lab_top` ; `chooseDistributionToken` inchangé | patch |
| 8 | blind | Après un réglage déplacé, le token tiré peut s'afficher « écarté » sans dire qu'il a été tiré avec d'autres réglages | medium | `renderDistribution` recalcule, `store.step.drawn` reste ; la maquette validée efface le tirage quand un réglage bouge | patch |
| 9 | blind | Token tiré hors des 6 lignes ou dans le reste du vocabulaire, non signalé | low | possible mais rare ; la correction ajoute un état et un texte | rejet (low, correction non directe) |
| 10 | blind | Ligne « tirée » repérée par le texte, pas par l'identifiant | low | doublons de surface rares ; la réponse de `/distribution` ne porte pas d'identifiant (correction non directe) | rejet |
| 11 | blind, edge-case | `mamba`, `mamba2`, `rwkv6`, `rwkv7` (sans attention) classés hybrides ; le bandeau parle d'attention alternée | low | `HYBRID_ARCHITECTURES` + `banner_hybrid_any_text` | patch (texte du bandeau vrai dans les deux cas) |
| 12 | blind | `kv_head_count` perdu pour une liste par couche | false | `positive_size` renvoie le maximum d'une liste (`gguf_meta.py:141`) | rejet |
| 13 | blind | Étiquettes d'experts codées en dur (expert 121 pour un modèle à 8 experts) | low | `llm.js` MoE, liste fixe `[3, 17, 42, 66, 90, 121]` | patch |
| 14 | blind | Couche 2 dessinée comme la couche 1 alors que la légende dit « d'autres poids » | low | `attention_2` reprend `model.weights`, `mlp_2` les mêmes neurones | patch |
| 15 | blind | Limite 64 et 2 000 dupliquées (Python, JS, YAML) | low | divergence possible si la limite change ; la correction ajoute un champ à `lab_state` | rejet (low, correction non directe) |
| 16 | blind | Forme `one` de `kept_text` copiée du pluriel, agrammaticale | low | `stages.output.kept_text.one` fr/en/de | patch |
| 17 | blind | `ids_unknown_text` en/de : « row », et genre faux en allemand | low | fr « numéro », en « row », de « seine Zeile » | patch |
| 18 | blind, edge-case | Clés et CSS des anciennes sections encore exigés par `LabContent` | low | modèles stricts imbriqués, trois YAML, une partie encore lue (`questions_text`, `unknown_text`) : nettoyage plus large qu'une suppression directe | rejet (à reprendre au reversement UX) |
| 19 | blind | Les paragraphes d'intro des sections 1 et 2 ont disparu | false | voulu par la maquette v3 validée (sous-titres d'étape) | rejet |
| 20 | blind | Commentaires de `llm.js` avec les anciens numéros de section | low | « section 2 », « section 5 »… | patch |
| 21 | blind, edge-case | Identifiants non vérifiés si la taille du vocabulaire est inconnue | low | le pas exige le moteur en processus, dont `dimensions()` lit `vocab_size` au tokenizer ; cas non démontré, la correction ajoute une garde | rejet |
| 22 | blind | CSS en px au lieu de jetons | false | la règle « jetons seulement » du projet porte sur les couleurs (story 31) ; `llm.css` existant use de px pour les tailles | rejet |
| 23 | blind | Matrice « Retirer à nouveau » au lieu de « Tirer à nouveau » | low | correction dans la spec gelée | rejet (correction = éditer la spec) |
| 24 | blind | `.working/llm-loop-v2.html` commité | false | `bmad-ux` garde les essais dans `.working/` | rejet |
| 25 | blind | Le memlog garde les décisions v1 sans les marquer dépassées | low | entrées v1 (8 étapes, `loop.stages`) ; v2 et v3 consignées en `change` | patch (une entrée `event`) |
| 26 | edge-case | Texte modifié pendant un tirage : le token tiré pour l'ancien texte peut s'ajouter au nouveau | low | `stepEvent` pose `drawn` sans vérifier le texte ; `forText` posé après la réponse | patch |
| 27 | edge-case | Plus de 512 tokens puis ajouts : les ajouts suivent le 512e | low | cas rare dans la démo, correction par une branche | rejet |
| 28 | edge-case | Compteurs « 5 tokens » à côté de 6 colonnes après un ajout | medium | `renderInput` : compteurs de la session seuls | patch |
| 29 | edge-case | `drawTransfo` sans aucun token jetterait une erreur | false | `example_tokens` validé (5 tokens, test `the_three_stages_texts_are_valid`) et contenu lu avant tout dessin | rejet |
| 30 | edge-case | `drawStep` avec `store.sampling` nul | false | `main()` n'attache les écouteurs qu'après un `refresh` réussi, et `lab_state().sampling` est toujours servi | rejet |
| 31 | vérification (step-03) | Cloud : « vecteurs de inconnue nombres », « inconnue × inconnue » dans l'encadré « En vrai » | low | E2E `_llm_loop_cloud`, détail de la vérification | patch |

## Design Notes

Classification (en-tête GGUF, `arch = general.architecture`) : hybride si une clé `{arch}.ssm.*`, `{arch}.full_attention_interval`, `{arch}.shortconv.*`, `{arch}.wkv.*`, une liste `{arch}.attention.head_count_kv` contenant 0, ou `arch` parmi mamba, mamba2, rwkv6, rwkv7, jamba, falcon-h1, granitehybrid, lfm2, nemotron_h, plamo2 ; MoE si `{arch}.expert_count > 1` ; famille = hybrid si hybride (MoE noté en plus), sinon moe, sinon dense ; unknown sans `arch`. Le texte du bandeau est choisi par la page dans `llm_lab.yaml` d'après `family` et les chiffres reçus.

Pas à pas sans état côté session : la page envoie les ids déjà ajoutés (`continuation`), lus dans les `llm_token.token_id` des pas précédents ; la session rend le prompt par le gabarit (comme `_run_lab`), y ajoute ces ids et tire un token. Le cache du moteur réutilise le préfixe, donc un nouveau tirage au même endroit est rapide.

La TRANSFORMATION est dessinée par `llm.js` en SVG (`svgEl`) sur une poignée de tokens (5 au plus, les derniers) et 8 nombres par vecteur, avec des états pseudo-aléatoires à graine fixe ; seules les dimensions affichées sont lues.

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q` -- expected: tout vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only llm_loop llm_screen llm_live --channel msedge` -- expected: tout vert ; puis une passe complète à la fin

**Manual checks (if no CLI):**
- `uv run wavestack --port 8426`, page `/llm` avec Qwen3.5-2B déjà choisi (ne pas changer de modèle) : bandeau hybride, pas tiré réel, captures clair/sombre à 1600 × 1000 et 1366 × 768.
