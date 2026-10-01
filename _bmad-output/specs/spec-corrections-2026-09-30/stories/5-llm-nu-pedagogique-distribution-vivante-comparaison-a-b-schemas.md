---
title: 'LLM nu pédagogique : distribution vivante, comparaison A/B, schémas'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_revision: '14353f65b9a95215aed95bf221698c0a57beb683'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/ecrans-lots-2-a-4.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred:
  - 'E2E : redessin des barres au curseur avec un moteur en processus factice (logits scriptés) ; la pile E2E ne sait pas substituer LlamaCppEngine comme FakeReranker, couvert par tests/test_llm_lab.py (route, oracle, matrice).'
  - summary: >-
      La logique de page de la distribution vivante et du schéma de fenêtre (barres redessinées au curseur, puce qui choisit le token, remplissage proportionnel, réserve qui croît) n'est pilotée par aucun test.
    evidence: |-
      Revue du 2026-10-01 (IA1, IA5, VG5, BH11) : l'E2E n'a pas de moteur en processus, seule la branche « indisponible » est vue. Faisable sans moteur : `page.route` simulant `/api/llm_lab` (distribution.tokens > 0, candidates.available) et `/api/llm_lab/distribution`, puis des `llm_token` rejoués ; à lancer avec l'accord d'Anaël (E2E).
    location: >-
      src/wavestack/web/static/llm.js (fetchDistribution, renderDistribution, renderWindow, windowToken) ; tools/e2e/run_e2e.py
    severity: medium
  - summary: >-
      Comparaison A/B : « Arrêter » de la page jamais pressé (arrêt testé par session.stop()) et jamais de comparaison avec un modèle cloud.
    evidence: |-
      Revue du 2026-10-01 (IA3, BH10) : `test_compare_route_refused_outside_idle_validated_and_stopped_whole` arrête par `session.stop()` pendant A ; aucun test d'arrêt pendant B ni de comparaison cloud (`_lab_cloud_call` deux fois). Test unitaire possible avec `Provider` de test_cloud ; tranche E2E `llm_screen` pour le bouton.
    location: >-
      tests/test_llm_lab.py ; tools/e2e/run_e2e.py (_lab_compare)
    severity: medium
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

## Spec Change Log

- 2026-10-01, implémentation (agent, non vérifiée : ni pytest ni E2E lancés, PC partagé ; seuls `ruff`, `node --check` et un import ont tourné). Décisions prises sans question :
  - **Un seul commit** pour les trois incréments, à la demande de l'orchestrateur (la spec en demandait un par incrément). Reprise d'un premier passage interrompu (c577c47) : backend, contenus et HTML venaient de lui ; front (`llm.js`, `llm.css`), tests, E2E et documents ajoutés ensuite.
  - **Pénalités** : vérifié dans `llama_cpp` 0.3.35 installé, `Llama.generate` a `repeat_penalty` 1, `frequency_penalty` et `presence_penalty` 0 et `typical_p` 1 par défaut, et `LlamaCppEngine.complete` ne passe que température, top-k, top-p et min-p : les candidats bruts sont justes, rien à dire dans la page (noté dans `models/candidates.py`).
  - **Top-k au-delà des 100 lus** (seulement si le vocabulaire en a moins de 100, la borne étant 100) : `distribution` le traite comme désactivé, sur tout le vocabulaire (`tail` compris).
  - **Mémoire** : clé `index` de `llm_token`, gardée avec le moteur qui l'a lue (un changement de modèle la rend caduque, `lab_state().distribution.tokens` vaut alors 0) ; une génération sans candidats l'efface aussi. La route rend aussi `kept_count` et `tokens` ; `index` hors plage : 404 lisible (`session.llm_lab.distribution.out_of_range`).
  - **Page, distribution** : dix barres au plus, puis « Reste du vocabulaire » ; anti-rebond de 80 ms, un ticket par requête (la dernière envoyée gagne) ; la page ne demande la distribution que si la session garde quelque chose (`distribution.tokens` ou un `llm_token` avec candidats), pour éviter un 404 dans la console ; serveur et cloud : `candidates.reason_text`. Le clic sur une puce garde l'encart des candidats (story 29) et choisit aussi le token de la section 2.
  - **A/B** : les événements de A remplissent la colonne A et aussi les sections 4 à 6 et les puces de la section 5 (pour choisir un token de la distribution, qui est celle de A) ; ceux de B ne remplissent que la colonne B. Réglages B au premier affichage : ceux du harnais à température 1,2, gardés par le navigateur (`wavestack.llm.sampling_b`). Si « Arrêter » survient pendant A, B émet seulement `llm_generation_ended{status: cancelled}` (sans `llm_generation_started`), et la session revient en `idle` une fois.
  - **Schéma de la fenêtre** en section 4 ; `llm_generation_started` gagne `usable` et `figures_text.window` ; largeurs posées en CSS (`flex-grow`, `calc`) à partir des valeurs reçues.
  - **E2E** : `_distribution_unavailable` (cloud A, llama-server), `_lab_questions_and_window`, `_lab_compare` (capture `64-llm-nu-comparaison`, numéro choisi hors de 60 à 62 réservés) ; le contrôle « l'atelier refuse un envoi » est fait pendant A, en supposant que le faux llama-server laisse le temps de l'appel (risque de course si la génération est très rapide).
  - Variables des textes en français (`{gardes}`, `{lus}`, `{reste}`, `{texte}`, `{fenetre}`, `{utilisables}`), comme le reste de `llm_lab.yaml`.

## Review Triage Log

### 2026-10-01 — Review pass
- verdicts: 35 findings — high 0, medium 9, low 23, false 3, maybe-false 0
- findings:
  - `[medium]` `[defer]` IA1 : le cœur de l'expérience (curseurs → barres, puce → token, `p` fixe, `p_sampled` mobile) n'est testé nulle part de bout en bout — groupé avec VG5, différé (voir `deferred`).
  - `[medium]` `[patch]` IA2 : oracle seulement sur un vocabulaire de 8 (tail ≈ 0) — groupé avec VG3 : `test_distribution_top_p_counts_the_tail_when_top_k_is_off` ajouté.
  - `[medium]` `[defer]` IA3 : « Arrêter » de la page jamais pressé, comparaison cloud jamais faite ; A et B indistinguables — la partie A/B est corrigée par VG2 ; arrêt par la page et cloud différés (voir `deferred`).
  - `[low]` `[reject]` IA4 : la route rend le 404 générique sur serveur ou cloud — la page ne l'appelle jamais dans ce cas (`fetchDistribution` s'arrête sur `candidates.available` faux et affiche `candidates.reason_text`) ; la corriger ajoute une branche pour un appelant qui n'existe pas.
  - `[low]` `[defer]` IA5 : remplissage proportionnel et croissance de la réserve non testés — logique de page, groupé avec VG5 ; les couloirs « raisonnement puis réponse » sont gardés (`laneToken` toujours appelé pour A et « Générer »).
  - `[low]` `[reject]` IA6 : incréments non commités séparément, défauts `llama_cpp` vérifiés en lecture — décision consignée au Spec Change Log, sans effet sur le code livré.
  - `[medium]` `[patch]` VG1 : distribution caduque après changement de modèle non testée — `test_a_switch_of_model_makes_the_kept_distribution_stale` ajouté (fabrique `Tracker`, A puis B, `tokens` 0 et `DistributionMissing`).
  - `[low]` `[patch]` VG2 : le test de comparaison ne distinguait pas A de B — A « Oui », B « Non! » ; la distribution est celle de A (`token_text` « O » puis « i »), les tokens de B n'ont pas de candidats.
  - `[medium]` `[patch]` VG3 : branche top-p avec `tail` non nulle jamais exercée — oracle sur 300 logits (tête piquée, traîne plate), top-k 0, top-p 0,75 : mêmes `kept` sur les 100 lus, mêmes `p_sampled`, et la coupe tomberait parmi les cinq premiers sans la traîne.
  - `[medium]` `[patch]` VG4 : `Fragment.top` du vrai moteur jamais vérifié — `test_fragments_carry_the_most_probable_tokens` ajouté à `tests/test_engine_candidates.py`, **non lancé** (charge `tiny-llama.gguf` en processus : accord d'Anaël requis).
  - `[medium]` `[defer]` VG5 : logique de page de la distribution non pilotée par un test — différé (voir `deferred`), à faire par `page.route` sans moteur.
  - `[low]` `[patch]` VG6 : B tournait avec les candidats (softmax plein vocabulaire, 5 candidats par token au journal, inutiles) — `_run_compare` lance B sans candidats ; vérifié par `engine.candidates` dans le test de comparaison.
  - `[low]` `[reject]` BH1 : B tourne encore si A a échoué — l'échec de B est alors dit dans sa colonne, exact ; une erreur moteur peut être passagère ; sauter B ajouterait un statut et une branche pour un double message sans dommage.
  - `[low]` `[patch]` BH2 : « le tirage se fait entre eux » faux quand aucun filtre ne coupe — `kept_text` réécrit sans cette affirmation (fr, en, de).
  - `[low]` `[patch]` BH3 : « 100 » écrit en dur dans `tail_help_text` — variable `{lus}` (nombre de candidats lus, servi par la route) en fr, en, de.
  - `[low]` `[patch]` BH4 : le schéma dit « tokens » pour des fragments (serveur, cloud) — `window.output_fragments_text` ajouté (modèle pydantic, fr, en, de), choisi par `store.gen.fragments` ; la moitié « ≈ » est fausse : `figures_text.prompt_tokens` porte déjà « ≈ » quand `exact` est faux.
  - `[low]` `[reject]` BH5 : la distribution ne marque pas le candidat tiré — l'en-tête nomme le token (`distribution.token_text`), et un tiré hors des 100 a une probabilité négligeable ; un champ `chosen` et son rendu sont une fonction de plus.
  - `[low]` `[reject]` BH6 : après rechargement, la distribution revient sans les puces — vrai (le flux reprend à `seq`), mais les barres restent justes ; seule l'invite à cliquer une puce est sans objet, et la corriger demande une branche et un texte de plus.
  - `[low]` `[patch]` BH7 : « invite » et « prompt » mélangés — « invite » remplacé par « prompt » dans les deux textes nouveaux.
  - `[false]` `[reject]` BH8 : question sur les tokens spéciaux en section 1 — la section 1 montre et explique les tokens spéciaux (`tokenization.special_text`, « un marqueur du gabarit »).
  - `[low]` `[patch]` BH9 : les deux pourcentages d'une ligne sans nom accessible — chaque valeur précédée de son nom de colonne en texte masqué (`.llm-sr-only`, `llm.css`).
  - `[medium]` `[patch]` BH10 : tests manquants (top-p avec tail, modèle changé, arrêt pendant B, cloud) — groupé avec VG1 et VG3 (ajoutés) ; arrêt pendant B et cloud différés avec IA3.
  - `[medium]` `[defer]` BH11 : pas d'E2E positif des barres ni de capture — groupé avec VG5.
  - `[low]` `[patch]` BH12 : ARCHITECTURE-SPINE se contredit sur l'état du navigateur — phrase de l'écran corrigée (brouillon et réglages), paragraphe « État du navigateur » complété (`wavestack.llm.prompt`, `.sampling`, `.sampling_b`).
  - `[low]` `[patch]` BH13 : la fin de A écrit « Réponse terminée. » sous « Générer » pendant B — le statut de « Générer » est vidé au début et à la fin de A (la comparaison a le sien).
  - `[low]` `[reject]` BH14 : softmax plein vocabulaire calculé deux fois par token — une exponentielle vectorisée sur ~150 000 flottants, négligeable devant un token sur CPU ; fusionner les deux fonctions toucherait l'oracle.
  - `[false]` `[reject]` BH15 : B = A sans le dire quand le modèle ne règle pas la température — `samplingRow` désactive le réglage et affiche sa raison (`sampling-row-reason`) dans les réglages B comme en section 2 ; l'absence de remise à zéro n'est pas un défaut.
  - `[low]` `[patch]` BH16 : « Libre » sert d'infobulle à la part du prompt — la part remplie du prompt a sa propre infobulle (`window.prompt_text`) ; le dépassement borné à 100 % n'est pas un défaut (le prompt trop long n'est pas envoyé, la légende et l'erreur le disent).
  - `[low]` `[reject]` EC1 : = BH1, même raison.
  - `[low]` `[patch]` EC2 : `renderDistributionIdle` n'invalidait pas le ticket — `store.dist.ticket += 1` : une réponse en vol ne redessine plus d'anciennes barres.
  - `[low]` `[reject]` EC3 : `pending.compare` bloqué si la fin de B n'arrive pas — le flux reprend à `Last-Event-ID` (pas de trou) et `_run_compare` émet la fin de B sur tous ses chemins sauf une émission qui lève ; garde pour un cas non démontré.
  - `[low]` `[reject]` EC4 : émission levée de la fin annulée de B — même cas que EC3.
  - `[low]` `[patch]` EC5 : « Générer » après une comparaison laissait les colonnes A/B — masquées au `llm_generation_started` d'une génération hors comparaison.
  - `[low]` `[reject]` EC6 : course E2E si le faux llama-server finit A et B avant l'envoi — le prompt de 230 caractères donne ~70 morceaux à 20 ms par génération (≈ 3 s pour A et B), l'envoi part dès le début de A ; risque faible, garde non justifiée.
  - `[false]` `[reject]` EC7 : une génération sans candidats efface la mémoire — voulu par la spec (« une nouvelle efface l'ancienne ») et dit par `distribution.empty_text`.

### 2026-10-01 — Follow-up review pass
- verdicts: 3 findings — high 0, medium 0, low 3, false 0, maybe-false 0
- findings:
  - `[low]` `[patch]` 404 possible pendant un chargement de modèle ou entre le début d'une génération et son `llm_generation_started` (`store.dist.tokens` encore positif, la session ayant déjà lâché la mémoire) : erreur réseau dans la console — `llm.js` remet `store.dist.tokens` à 0 et affiche le repos sur `model_load_started` et sur un `session_state` `llm_lab` ou `model_load`.
  - `[low]` `[patch]` « Token {index} de la dernière génération » faux après une comparaison (la mémoire est celle de A) — `distribution.token_text` dit « (A pour une comparaison) » en fr, en, de.
  - `[low]` `[patch]` Schéma de la fenêtre sur serveur ou cloud : la barre de sortie se remplissait en fragments rapportés à une réserve comptée en tokens (sous-estimée d'un facteur 2 à 5) — barre laissée vide quand `store.gen.fragments`, seul le nombre de fragments est dit.
- Revue de suivi : convergée (aucun `high`), `followup_review_recommended: false`. Vérifié : `pytest tests/test_llm_lab.py` 60 passés ; E2E rejoué (voir l'état de la nuit).

## Auto Run Result

- **Changement** : distribution vivante calculée par le serveur (`candidates.distribution`, mémoire de session des 100 premiers candidats, route `POST /api/llm_lab/distribution`), comparaison A/B (`llm_compare`, `llm{n}.a` puis `.b` sous un seul état `llm_lab`), questions par section et schéma de la fenêtre.
- **Correctifs de revue** (2026-10-01, session de suite) : `app_session.py` (B sans candidats) ; `llm.js` (ticket invalidé au repos, noms accessibles des valeurs, `{lus}`, infobulle du prompt, fragments, colonnes A/B masquées par « Générer », statut de « Générer » vidé pendant A) ; `llm.css` (`.llm-sr-only`) ; `llm_lab.py` et `llm_lab.yaml` fr/en/de (`kept_text`, `tail_help_text`, `output_fragments_text`, « prompt ») ; ARCHITECTURE-SPINE ; tests `test_llm_lab.py` (VG1, VG2, VG3, VG6) et `test_engine_candidates.py` (VG4).
- **Bilan** : 17 lignes corrigées (entrées `medium` : VG1, VG3 avec IA2, VG4, BH10 ; le reste `low`), 5 différées (2 entrées `deferred`), 13 rejetées (3 `false`, 10 `low` avec leur raison ci-dessus).
- **Revue de suivi recommandée** : oui. Risque nommé : la logique de page (barres redessinées, colonnes A/B, schéma) n'a jamais tourné dans un navigateur avec des données positives, et le test VG4 du vrai moteur n'a pas été lancé.
- **Vérification** : `ruff check` et `ruff format --check` OK ; `node --check llm.js` OK ; `pytest tests/test_llm_lab.py tests/test_i18n.py tests/test_ui_texts.py tests/test_web_tokens.py tests/test_annex_language.py` : 284 passés, 1 désélectionné (marqueur `model`). **Non lancés** (accord d'Anaël requis) : `tests/test_engine_candidates.py` (modèle synthétique en processus) et l'E2E `--only llm_screen bare_llm annex_language`.
- **Risques résiduels** : statut laissé `in-review` jusqu'à l'E2E ; course de l'E2E `_lab_compare` (EC6) jugée faible.
- **Vérification avec processus** (2026-10-01, accord d'Anaël) : `tests/test_engine_candidates.py` 4/4 (dont VG4) ; E2E `llm_screen bare_llm` sans échec (84 vérifications avec `annex_language`, dont la comparaison A/B, capture `64-llm-nu-comparaison`).
