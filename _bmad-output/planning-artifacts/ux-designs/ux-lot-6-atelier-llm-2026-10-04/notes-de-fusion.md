---
title: Notes de fusion — lot 6, Atelier LLM (la boucle du modèle)
created: 2026-10-05
branch: feat/lot-6-atelier-llm-2026-10-04
baseline_commit: 370bb36d762c23e5f4af66168316104f5d738ecc
spec: ../../../implementation-artifacts/spec-lot-6-atelier-llm-boucle-du-modele.md
---

# Notes de fusion du lot 6

## Fichiers propres à l'Atelier LLM (sans risque de conflit attendu)

- `src/wavestack/web/static/llm.html`, `llm.js`, `llm.css` : sections 1 et 2 remplacées par les
  trois étapes (`#stage-input`, `#stage-transfo`, `#stage-output`), sections suivantes
  renumérotées 4 à 7.
- `src/wavestack/session/llm_lab.py` : textes `stages`, `classify_header`,
  `architecture_from_header`, `read_architecture` (cache chemin + mtime), `STEP_LIMIT`,
  paramètre `architecture=` de `dimensions_payload`, `figures_text.max_id`.
- `content/llm_lab.yaml` et `content/i18n/{en,de}/llm_lab.yaml` : bloc `stages`, renvois de
  section mis à jour (section 5 → 6, « section 2 » → « étape 3 »).
- `tests/test_llm_lab.py` : tests ajoutés en fin de fichier.

## Fichiers carrefour touchés

| Fichier | Nature | Contenu |
| --- | --- | --- |
| `src/wavestack/session/app_session.py` | ajouts, deux retouches | `llm_step`, `_engine_vocab` (ajoutés avant `_lab_release`) ; `_run_lab` gagne `continuation` et `max_tokens` (défauts neutres) ; `_lab_dimensions` passe `architecture=` ; `llm_distribution` renvoie `dropped_by` ; imports `Sequence`, `dropped_by`. Suite de la revue (pas sans gabarit) : `_run_lab` gagne `raw: bool = False` (la branche locale appelle `_step_context` au lieu de `render_context`, sans raisonnement ; `continuation` n'est plus lu qu'avec `raw`, le bloc `replace(rendered, …)` a disparu) ; `llm_step` passe `raw=True` ; `_step_context` ajouté avant `_lab_release` ; `_step_bos`, `_step_bos_text` ajoutés après `_lab_tokenized`, qui renvoie `bos_token`. |
| `src/wavestack/web/app.py` | ajouts, une ligne retouchée | `LlmStepIntention`, `POST /api/intentions/llm_step` (après `llm_compare`) ; la ligne `from typing import Any, Literal` devient `from typing import Annotated, Any, Literal` (conflit d'une ligne si un autre lot touche cet import). |
| `src/wavestack/trace/catalog.py` | ajouts | `LlmArchitecture`, champ `LlmDimensions.architecture` (défaut `None`) ; suite de la revue : champ `LlmTokenizedPayload.bos_token` (défaut `None`). |
| `src/wavestack/models/engine.py` | ajouts (suite de la revue) | `VocabTokenizer.adds_bos()` (id du BOS si `llama_vocab_get_add_bos`, sinon `None`) après `is_eog` ; `LlamaCppEngine.adds_bos()` qui délègue, après `tokenize`. |
| `src/wavestack/models/candidates.py` | refactorisation locale | `_cuts` extrait de `distribution` (même règle), `dropped_by` ajouté. Comportement de `distribution` inchangé (tests oracle verts). |
| `content/messages.yaml` + en + de | ajouts | `session.llm_lab.step.too_many`, `session.llm_lab.step.out_of_vocabulary`. |
| `src/wavestack/web/static/diagram.js` | ajout d'option | `createStepper(host, { onShow, liveText })` : deux lignes touchées (la signature et le texte du bouton de droite, `liveText \|\| t("common.diagram.live")`). Rétrocompatible. |
| `tools/e2e/run_e2e.py` | ajouts seuls | `s_llm_loop`, `_LoopLab`, fonctions `_llm_loop_*` (dont `_llm_loop_cloud`, la ligne « Cloud » de la matrice), imports `llm_lab` et `dropped_by`, entrée `("llm_loop", s_llm_loop)` après `llm_live`. `s_llm_screen` et `s_llm_live` inchangés. |
| `tests/test_web_tokens.py` | retouche | Le glob `*/DESIGN.md` trouvait aussi le DESIGN.md delta du lot 6 ; il ne garde plus que le DESIGN.md qui déclare `colors:`. |

## Conflits probables

- **Lot 3** (modèles servis, `models/servers.py`) : le lot 6 laisse l'architecture d'un modèle
  servi à `unknown` (EXPERIENCE.md, Open Questions). Après la fusion du lot 3, brancher
  `read_architecture` sur le chemin du GGUF du serveur dans `_lab_dimensions`. Les deux lots
  touchent `app_session.py` près de `_lab_dimensions` et `_candidates_info` : conflit textuel
  possible, sans conflit de sens.
- **Lots 3, 4, 5** : `tests/test_web_tokens.py` casse dès qu'un deuxième DESIGN.md arrive sous
  `ux-designs/`. Si un autre lot l'a corrigé autrement, garder une seule correction.
- **Lots 4 et 5** (ateliers MCP et RAG sur le schéma commun) : s'ils ajoutent aussi une option
  à `createStepper`, fusionner les déstructurations à la main (`{ onShow, liveText, … }`).
- **Tous les lots** : `app.py`, `catalog.py` et `messages.yaml` reçoivent des ajouts en fin de
  sections propres aux ateliers ; conflits de voisinage seulement. `run_e2e.py` : la liste
  `SCENARIOS` est un point de conflit fréquent (une ligne ajoutée après `llm_live`).

## Sections UX à reverser après la fusion du lot 3

Dans le DESIGN.md principal :
- les composants `llm-stage`, `llm-stage-tag(-illustrative)`, `llm-stage-link`,
  `llm-input-column`, `llm-transfo-canvas`, `llm-layer-stack`, `llm-output-part`,
  `llm-output-bars`, `llm-banner` (frontmatter et section Components du delta) ;
- la règle « chaque carte tient entière dans l'écran à 1366 × 768 ».

Dans l'EXPERIENCE.md principal :
- l'arborescence de `/llm` (sections 1 à 7) ;
- les composants « Puce de token » (section 1), « Schéma de vectorisation », « Réglages
  d'échantillonnage » et « Distribution vivante » à remplacer par INPUT, TRANSFORMATION, OUTPUT ;
- l'intention `llm_step` (pas à pas réel) et le bandeau D4.

## Écarts et points à connaître

- Plus de 64 ajouts : 409 avec la raison (la session), comme le veut la matrice de la spec ;
  `LlmStepIntention` ne plafonne la requête qu'à 1 024 ids. La page grise « Tirer » avant.
- Les compteurs de l'INPUT restent ceux de la session (le texte découpé) ; les tokens ajoutés
  apparaissent en colonnes « produit » sans changer les compteurs (AD-1).
- Après un rechargement de la page, la distribution gardée par la session est présentée comme
  celle de la dernière génération même si elle vient d'un pas (la session ne dit pas laquelle).
- Le motif « une couche sur n » de la pile vient de `attention_interval` (lu, ou déduit d'un
  `head_count_kv` par couche parfaitement régulier) ; sinon toutes les couches sont dessinées
  pleines et le bandeau prend la variante sans intervalle.
- `tests/test_docs_links.py::test_readme_is_a_short_onboarding_page` échoue déjà au commit de
  base (README de 121 lignes) : hors périmètre du lot 6.

## Captures E2E

Seules les captures des scénarios de l'Atelier LLM sont commitées : `52`, `53`, `54`, `64`,
`65`, `annex-language-de-llm-*` (la page a changé) et les nouvelles `70-` à `74-llm-boucle-*`.
Les captures des autres scénarios, régénérées par la passe complète, sont restées à leur
version du commit de base : ce sont des binaires que chaque lot régénère, source de conflits
sans valeur.

## Vérification au commit

- `ruff` propre ; `pytest` : 5 485 réussis, 1 échec préexistant (`test_readme_is_a_short_onboarding_page`,
  README de 121 lignes au commit de base, non touché).
- E2E de l'Atelier LLM (`llm_loop`, `llm_screen`, `llm_live`) : 81/81.
- Passe E2E complète : 6 échecs, aucun dans l'Atelier LLM, tous préexistants :
  - `mcp_full`, mode cloud (arbres JSON des descriptions d'outils) : échoue de même au commit de
    base `370bb36` (vérifié dans un checkout temporaire, supprimé ensuite) ;
  - `annex_language` et `backend_language` sur `/rag` et `/diagnostic` (5 vérifications) : passent
    quand ces scénarios tournent seuls ; ils échouent après les scénarios qui laissent des
    messages français dans le journal (dépendance d'ordre).
- Appli réelle (`--port 8426`, modèle choisi inchangé : un Qwen3 dense) : vraies dimensions, pas de
  bandeau, un token tiré par le moteur en 1,3 s, chaque étape dans l'écran à 1600 × 1000 et
  1366 × 768. En-tête du vrai Qwen3.5-2B : `hybrid`, une couche sur 4, 2 têtes K/V.

## Décision d'Anaël (2026-10-05) : le pas lit le texte de l'INPUT

Spec : `spec-lot-6-pas-de-l-output-lit-le-texte-de-l-input.md`. Option B retenue : le pas se
fait **sans gabarit de chat**. Le moteur lit les identifiants mêmes de l'INPUT (`tokenize`, comme
`llm_tokenize`), précédés du BOS quand le modèle le demande (Gemma, Llama ; pas Qwen), puis les
tokens ajoutés ; le token tiré prolonge le texte. « Générer » garde le gabarit. Côté page :
`#token-bos` (phrase de l'INPUT qui nomme le BOS, `stages.input.bos_text`) et `#llm-step-raw`
(phrase de l'OUTPUT, `stages.output.raw_text`) ; `stages.output.end_text` réécrit (« le texte
s'arrête là »). Un modèle qui raisonne toujours tire son pas sans raisonnement.
