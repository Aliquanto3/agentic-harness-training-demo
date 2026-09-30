---
title: 'Gemma 4 via Google AI Studio : une entrée cloud gratuite, déclarée sans mentir'
type: 'feature'
created: '2026-09-30'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le plan de corrections du 2026-09-30 (lot 1) constate que Google AI Studio ne sert dans WaveStack que `gemini-3.5-flash-lite`, alors que l'éditeur `gemma` existe déjà dans `content/models/publishers.yaml` et que la clé sert aussi deux modèles Gemma 4 ouverts, gratuits, avec outils et raisonnement. Un modèle ouvert servi hors du poste, gratuit, est un cas pédagogique à part entière (« ce modèle tourne hors de votre poste », sans prix, avec ses conditions).

**Approach:** Déclarer une entrée `[[cloud.models]] id = "gemma"` dans `wavestack.toml`, sur le même `base_url`, la même clé (`GEMINI_API_KEY`) et le même contournement de signature que Gemini, construite sur les faits relevés sur l'API réelle le 2026-09-30 ; documenter l'entrée dans le README ; mettre à jour les tests et les attentes E2E qui énumèrent les préréglages cloud. Aucun changement de code Python.

**Décisions prises avec Anaël le 2026-09-30 :**
- Modèle par défaut `gemma-4-26b-a4b-it` (MoE, 4 B actifs) ; `gemma-4-31b-it` (dense) documenté en secours dans le commentaire, comme le secours 3.6 de Gemini.
- `training = "no"`, `trial = true`, entrée active (renégocié après la revue, le 2026-09-30). Deux clauses EEE des conditions Gemini API (relues le 2026-09-30) : (1) pour un utilisateur de l'EEE, de Suisse ou du Royaume-Uni, les règles de données de l'offre payante (rien ne sert à améliorer les produits) s'appliquent à tous les services, quota gratuit compris ; (2) « You may use only Paid Services when making API Clients available to users in the EEA… », et Gemma n'a pas d'offre payante (page tarifaire : « Free of charge » / « Not available », « Used to improve products : Yes » hors clause 1). La note dit donc : usage personnel de la clé sur son poste, pas une mise à disposition ; règles de données de l'offre payante pour l'EEE ; même clé que Gemini.
- La note Gemini garde « offre payante obligatoire », avec la clause 2 citée exactement (client d'API) et la clause 1 en complément. Le reste de l'entrée Gemini ne bouge pas.
- Branche `feat/gemma-ai-studio`, PR courte vers `main`.

**Faits relevés sur l'API réelle (endpoint OpenAI, 2026-09-30, sept appels gratuits) :**
- Liste `openai/models` : `gemma-4-26b-a4b-it` et `gemma-4-31b-it` ; fiche native : 262 144 tokens en entrée, 32 768 en sortie, `thinking: true`, `generateContent` seulement.
- Outils : appel reçu en un fragment avec `extra_content.google.thought_signature`, comme Gemini (les deux modèles). Le contournement `skip_thought_signature_validator` reste à confirmer par « Tester » et une action forcée.
- Raisonnement : le modèle réfléchit **par défaut**, et la pensée est **visible par défaut** dans `content`, entre `<thought>` et `</thought>`, en fragments marqués `extra_content.google.thought = true` (même sans `include_thoughts`). `reasoning_effort = "minimal"` l'éteint (0 token de réflexion). `thinking_level`, `thinking_budget` et `reasoning_effort = "medium"` sont refusés (400 « not supported for this model »). `include_thoughts = true` seul est accepté.
- `usage` : `total_tokens` compte la réflexion, `completion_tokens` non (même lecture que Gemini).

</frozen-after-approval>

## Spec Change Log

- 2026-09-30, après la revue : le relecteur a relevé que le commentaire Gemini de `wavestack.toml` cite une seconde clause EEE (« only Paid Services when making API Clients available to users in the EEA »), absente de mon premier relevé des conditions. Vérifiée sur ai.google.dev le jour même. Anaël a renégocié la décision : entrée active, note honnête sur les deux clauses, Gemini de nouveau « obligatoire ». KEEP : `training = "no"` reste fondé sur la clause 1.

## Implementation Notes

- **Fichiers touchés :** `wavestack.toml` (entrée `gemma` après `gemini`, note EEE de Gemini reformulée), `README.md` (titre et intro de « Modèle cloud », clé partagée, paragraphe Gemini corrigé, paragraphe Gemma, FinOps « — », GreenOps), `tests/test_cloud.py` (listes d'ids, deux tests Gemma), `tests/test_model_catalog.py` et `tools/e2e/run_e2e.py` (groupe « Réseau · Gemma (Google) » avant Gemini, ligne du tableau), `tests/test_greenops.py` (EcoLogits connaît `gemma-4-26b-a4b-it` hors ligne). Aucun code Python de `src/` modifié.
- **Décision prise seul :** le raisonnement « allumé » envoie `include_thoughts = true` seul (accepté par l'API, explicite, et distinct du corps « éteint ») ; `always = false` puisque `minimal` éteint réellement la réflexion. Réserve de sortie inchangée (1 536 tokens allumé, 512 éteint) : la réflexion réelle tient dans 200 à 600 tokens.
- **Surprise :** une clé saisie au diagnostic est rangée par `id` d'entrée (`api_keys.json`) : celle de Gemini ne sert pas à Gemma. `GEMINI_API_KEY` sert aux deux. Phrase ajoutée au README.
- **Surprise :** le sélecteur lit « 26B » dans le nom du modèle (paramètres totaux, pas actifs) : exact pour un MoE 26B-A4B, laissé tel quel.
- **Vérification :** `ruff check` et `ruff format --check` OK ; `pytest` en deux moitiés : 723 + 501 passés (9 sautés) ; E2E `--only model_catalog` : 0 FAIL, ligne Gemma et groupes vérifiés ; captures restaurées.
- **Recette réelle (2026-09-30, clé de l'utilisateur, ~10 appels gratuits, jamais affichée) :** « Tester » réussit (appel `get_datetime` reçu) ; raisonnement allumé : 593 caractères de pensée sur le train, réponse « 17 h 25 » ; outils : `calculator` avec signature rejouée, tour `completed` ; raisonnement éteint : 0 caractère de pensée, `get_datetime` appelé ; empreinte GreenOps estimée (valeur ponctuelle, architecture publiée) ; aucun coût FinOps ; clé absente du journal et des fichiers (entière, 4 premiers, 4 derniers caractères).

## Review Triage Log

Revue 1 (2026-09-30, relecteur à l'aveugle, 11 constats). Chacun vérifié dans les fichiers.

| # | Constat | Verdict | Preuve et suite |
|---|---------|---------|-----------------|
| 1 | Commentaire Gemini du toml contredit par la note (clause EEE) | medium | Le commentaire citait une seconde clause (« only Paid Services when making API Clients available… ») absente de mon relevé ; vérifiée sur ai.google.dev. Décision renégociée avec Anaël (voir Spec Change Log) ; commentaire, notes et README réécrits sur les deux clauses ; patch |
| 2 | `tools/e2e/README.md` et commentaire de `run_e2e.py` sans Gemma | low | Vrai ; patch |
| 3 | Secours 31B sans `impacts` | low | Vrai : l'empreinte serait celle du 26B ; recette complète en commentaire et dans le README ; patch |
| 4 | Corps « brique éteinte » de Gemma non testé | low | Vrai ; test miroir ajouté (`minimal`, sans `extra_body`, 512, signature rejouée) ; patch |
| 5 | `trial = true` sans test d'affichage | low | Vrai ; assertion sur `disclosure.trial` de `/api/diagnostic` (Gemma vrai, Gemini faux) ; patch |
| 6 | Note Gemini reformulée sans test | low | Vrai ; assertion « obligatoire » et « EEE » ; patch |
| 7 | « 26B » (total) ni vérifié ni expliqué | low | Vrai ; taille « 26 B » vérifiée dans l'E2E, phrase « 26 milliards au total, 4 actifs » dans le README ; patch |
| 8 | README muet sur ce que la brique allumée envoie | low | Vrai ; phrase ajoutée ; patch |
| 9 | Rien sur les 429 de Gemma | low | Vrai ; phrase ajoutée (quota gratuit non publié, `min_interval_s`) ; patch |
| 10 | Indice « même clé » seulement dans le README | low | Vrai : une clé saisie sur la ligne Gemini laisse Gemma désactivé ; ajouté à `notes_fr` (repris dans l'avertissement) ; patch |
| 11 | Lignes du README au-delà de 100 caractères | low | Les lignes ajoutées sont refluées ; celles qui restent longues (paragraphe Gemini, 143 et 176) préexistent, hors de ce lot ; patch partiel |

Après correctifs : `ruff` OK ; `test_cloud`, `test_model_catalog`, `test_recette_docs` : 186 passés ; E2E `--only model_catalog` : 32 PASS, 0 FAIL.
