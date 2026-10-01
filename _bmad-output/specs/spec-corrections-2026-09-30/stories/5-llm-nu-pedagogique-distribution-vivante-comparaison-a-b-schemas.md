---
title: 'LLM nu pédagogique : distribution vivante, comparaison A/B, schémas'
type: 'feature'
created: '2026-10-01'
status: 'in-progress'
baseline_revision: '14353f65b9a95215aed95bf221698c0a57beb683'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/ecrans-lots-2-a-4.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Sur `/llm`, la section 2 (échantillonnage) n'a que des curseurs : le stagiaire ne voit pas ce que la température, top-k, top-p et min-p font aux candidats. Il ne peut pas comparer deux réglages sur la même invite. Les autres sections n'ont pas de schéma de la fenêtre ni les questions qu'elles traitent (CAP-5 de `SPEC.md`).

**Approach:** Trois incréments livrables, dans cet ordre, chacun commité : (1) distribution vivante, recalculée **par le serveur** (AD-1 : le front ne calcule aucune probabilité) à chaque réglage, à partir des probabilités du modèle gardées en mémoire de session pour la dernière génération ; (2) comparaison A/B par une intention qui enchaîne deux générations sous le même verrou `llm_lab` ; (3) questions du stagiaire par section et schéma de la fenêtre glissante.

## Boundaries & Constraints

**Always:**
- **(1) Source** : moteur en processus seulement (`LlamaCppEngine`, là où `candidates_from_logits` a les logits). Pendant une génération avec candidats, la session garde **en mémoire** (pas dans le journal) pour chaque token généré les `p` (softmax à T = 1) des 100 premiers candidats, leur texte et `tail = 1 − Σp` ; seulement la dernière génération (une nouvelle efface l'ancienne). Serveur et cloud : la distribution est indisponible avec la raison déjà servie (`candidates.reason_text`).
- **(1) Calcul** : une fonction pure `distribution(top_p_values, tail, sampling)` à côté de `candidates_from_logits` (même ordre que le moteur : top-k, top-p sur les probabilités renormalisées des gardés, min-p relatif au maximum, au moins un gardé, T = 0 → le premier à 1, sinon softmax de `log p / T` sur les gardés). Rendu : pour chaque candidat `{text, p, kept, p_sampled}` et la masse `tail` (« reste du vocabulaire », approximative, dite telle). Les tests existants de `candidates_from_logits` servent d'oracle : sur les mêmes logits, les deux fonctions donnent les mêmes `kept` et `p_sampled` pour les 5 premiers.
- **(1) Route de lecture** `POST /api/llm_lab/distribution {index, sampling}` (lecture, acceptée dans tout état, bornes de `SAMPLING_BOUNDS`) → `{index, token_text, candidates:[…], tail, sampling}` ou 404 lisible (« Générez d'abord un texte avec un modèle local. », par `msg()`) si rien n'est gardé. `index` = position du token dans la dernière génération ; défaut 0.
- **(1) Page** : section 2 montre les barres des candidats du token choisi (par défaut le premier ; un clic sur un token de la section 5 le choisit), avec la probabilité du modèle (`p`, fixe) et la chance d'être tiré (`p_sampled`, qui bouge), les écartés grisés ; chaque mouvement de curseur redemande la distribution (anti-rebond ≤ 100 ms, la dernière réponse gagne). Barres en tokens de `tokens.css` (principes `dataviz` : une teinte, étiquettes directes, pas de légende séparée).
- **(2) A/B** : intention `llm_compare {prompt, sampling_a, sampling_b, reasoning, candidates}` acceptée en `idle` seulement ; elle garde l'état `llm_lab` pendant les deux générations, séquentielles (moteur local comme cloud), `request_id` `llm{n}.a` puis `llm{n}.b`. La page affiche deux colonnes côte à côte (réglages résumés en tête), remplies par `request_id`. « Arrêter » arrête la comparaison entière. La distribution vivante porte sur la génération A.
- **(3)** Chaque section a une liste « Les questions que vous vous posez » (`sections.{id}.questions_text: list[str]` dans `content/llm_lab.yaml` et ses surcouches, champ ajouté au modèle pydantic) ; schéma de la fenêtre glissante dans la section 4 ou 5 à partir de `reserve`, `usable`, `prompt_tokens` de `llm_generation_started` (valeurs reçues, aucun calcul) ; les couloirs réflexion puis réponse existants gardés.
- Textes nouveaux en `fr`, `en`, `de` (`llm_lab.yaml`, `ui.yaml` section `llm`, `messages.yaml` pour la route). DESIGN.md (`sampling-controls`, nouveau `distribution-bars`, `compare-lanes`) et EXPERIENCE.md (`llm-screen`) mis à jour ; ARCHITECTURE-SPINE : route de lecture, intention `llm_compare`, rappel qu'AD-1 est tenu (calcul serveur).
- Vérifier dans `llama_cpp` (source installée) que le moteur n'applique pas de pénalité de répétition ni de typical-p par défaut qui rendrait les candidats bruts faux ; si c'est le cas, le dire dans la page et le noter (pas de correctif du moteur ici).

**Never:**
- Calculer une probabilité dans le JS ; mettre les 100 candidats dans les événements du journal.
- Lire `logprobs`/`n_probs` des serveurs ou du cloud (hors périmètre).
- Des générations parallèles.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| T = 1, filtres ouverts | top_k 0, top_p 1, min_p 0 | `p_sampled` = `p / (1 − tail)` pour chaque candidat, `tail` affiché | — |
| T = 0 | température 0 | premier candidat gardé à 100 %, autres 0 | — |
| top-k 3 | `top_k = 3` | 3 gardés, les autres `kept = false` | — |
| Rien gardé en mémoire | aucune génération locale | 404 lisible, la page dit quoi faire | pas d'erreur console |
| Serveur ou cloud actif | modèle non en processus | section 2 : raison d'indisponibilité | — |
| A/B refusée | état ≠ `idle` | 409 avec la raison, rien ne démarre | — |
| Arrêt pendant A/B | « Arrêter » pendant A | ni A ni B ne continue, retour à `idle` | — |

</intent-contract>

## Code Map

- `src/wavestack/models/candidates.py:28-81` -- `candidates_from_logits(logits, sampling, chosen_id, n=5)` : `p` softmax T=1 sur tout le vocabulaire, `kept` (top-k, top-p renormalisé `searchsorted(cum, top_p, 'left')+1`, min-p `logit >= max + ln(min_p)`), `p_sampled` softmax de `logits/T` sur les gardés ; à étendre : top 100 `p` + `tail`, et `distribution(...)` pure.
- `src/wavestack/models/engine.py` -- `Sampling` l.23-31, `DEFAULT_SAMPLING` l.36, `SAMPLING_BOUNDS` l.38-43 ; `LlamaCppEngine.complete(..., sampling, candidates)` l.332-378, `_candidates` l.380-395 (`llama_get_logits_ith(ctx,-1)`) ; `Fragment.candidates` l.73-75.
- `src/wavestack/session/app_session.py` -- `CANDIDATES = 5` l.323 ; `lab_state()` l.7590-7609 ; `llm_generate` l.7849-7883 (refus hors `idle`, `state="llm_lab"`) ; `_candidates_info` l.7892-7903 ; `_run_lab` l.7905-8106 (`llm_generation_started` avec `reserve`, `usable`, `prompt_tokens` l.8005-8017 ; `llm_token` l.7938) ; `_lab_cloud_call` l.8108-8148 ; `_save_main_state`/`_lab_restore` l.8031, 8150 ; fil unique l.726.
- `src/wavestack/trace/catalog.py` -- `SamplingTrace` l.355, `LlmGenerationStartedPayload` l.1057, `LlmCandidate` l.1084, `LlmTokenPayload` l.1097, `LlmGenerationEndedPayload` l.1111.
- `src/wavestack/web/app.py:167-183,351-384` -- `SamplingIntention`, `LlmGenerateIntention`, routes du LLM nu.
- `src/wavestack/session/llm_lab.py` -- `_Strict` l.33, `LabSections` l.42, `LabContent` l.175-191, `load_lab_content(lang)` l.201 ; `content/llm_lab.yaml` (sections l.17-51, candidates l.170-183) et `content/i18n/{en,de}/llm_lab.yaml`.
- `src/wavestack/web/static/llm.html` -- sections `#sec-tokenization` l.66-86 (schéma d'embedding existant), `#sec-sampling` l.88-97, `#sec-loading`, `#sec-reading` l.110-122, `#sec-generation` l.124-148, `#sec-reasoning` l.150-165, `#candidates-popover` l.168-172.
- `src/wavestack/web/static/llm.js` -- `renderDiagram` l.233-304, `renderSampling` l.364-427 (gestionnaires `input` l.397-409 : point d'accroche du redessin), `samplingToSend` l.436, génération l.568-595, `showCandidates` l.725-784, `applyEnvelope` l.795-864 (routage par `request_id`), `streamEvents` l.867-914, `refresh` l.916-951 ; `llm.css:643-750` (barres de candidats).
- `content/ui.yaml:852-875` (section `llm`) ; `content/messages.yaml:448-451` (raisons d'indisponibilité des candidats).
- `tests/test_llm_lab.py` -- oracle des candidats l.672-719, l.721, l.740, l.757 ; `tests/fake_engine.py:100-146` (candidats scriptés, sans logits : ajouter des logits scriptés).
- `tools/e2e/run_e2e.py:7315-7619` -- `s_llm_screen`/`_llm_screen` (cloud A puis faux llama-server ; aucune voie E2E n'a de moteur en processus), `_candidates_unavailable` l.7592, `_set_lab_sampling` l.7609, `_lab_generate` l.7619 ; `tools/e2e/wavestack_e2e.py:30` (précédent : `FakeReranker` substitué dans la pile).
- DESIGN.md l.1032-1039 ; EXPERIENCE.md l.35, 141-147, 224 ; ARCHITECTURE-SPINE AD-1 l.75-85, l.120, 137, 144, 231-232, 504, 529-535.

## Tasks & Acceptance

**Execution (incrément 1, puis 2, puis 3 ; chacun complet et testé avant le suivant) :**
- `src/wavestack/models/candidates.py` -- top 100 + `tail`, `distribution()` pure.
- `src/wavestack/session/app_session.py`, `src/wavestack/web/app.py` -- mémoire de la dernière génération, route `/api/llm_lab/distribution` ; intention `llm_compare`.
- `src/wavestack/web/static/llm.html`, `llm.js`, `llm.css` -- barres vivantes, choix du token, colonnes A/B, questions, schéma de fenêtre.
- `src/wavestack/session/llm_lab.py`, `content/llm_lab.yaml` et surcouches, `content/ui.yaml` et surcouches, `content/messages.yaml` et surcouches.
- `tests/test_llm_lab.py`, `tests/fake_engine.py` -- `distribution()` contre l'oracle et la matrice ; route (404, bornes, index hors plage) ; mémoire effacée par une nouvelle génération ; `llm_compare` (deux `request_id`, verrou tenu entre A et B, refus hors `idle`, arrêt).
- `tools/e2e/run_e2e.py` -- `_llm_screen` : A/B sur le faux llama-server (deux colonnes remplies, `request_id` a puis b) ; distribution : message d'indisponibilité sur serveur et cloud. Si la pile E2E peut substituer un moteur en processus factice avec des logits (comme `FakeReranker`), l'E2E vérifie aussi le redessin des barres au curseur ; sinon le noter en `deferred`.
- DESIGN.md, EXPERIENCE.md, ARCHITECTURE-SPINE -- mis à jour.

**Acceptance Criteria:**
- Given une génération avec un modèle local en processus, when le stagiaire baisse top-k de 20 à 3 en section 2, then trois barres restent actives, les autres grisées, et les chances affichées se renormalisent, sans nouvelle génération.
- Given `/llm` au repos, when le stagiaire lance « Comparer » avec deux températures, then deux réponses apparaissent côte à côte, l'une après l'autre, et l'atelier est refusé pendant ce temps.

## Design Notes

- Calcul serveur plutôt que JS : AD-1 reste vrai, une seule implémentation des filtres (Python, déjà testée), et l'aller-retour local coûte quelques millisecondes.
- Mémoire de session plutôt que journal : 100 candidats × 1 536 tokens pèseraient ~9 Mo d'événements par génération.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `node --check src/wavestack/web/static/llm.js` -- expected: aucune erreur.
- `uv run pytest -q tests/test_llm_lab.py tests/test_i18n.py tests/test_ui_texts.py tests/test_web_tokens.py tests/test_annex_language.py` -- expected: tout passe.
- E2E (orchestrateur) : `--only llm_screen bare_llm annex_language` -- expected: 0 échec.
