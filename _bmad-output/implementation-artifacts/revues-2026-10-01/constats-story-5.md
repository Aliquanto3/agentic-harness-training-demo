# Constats de revue, story 5 (LLM nu), quatre relecteurs — à trier

Working tree : `C:\Users\anael.yahi\Documents\GitHub\wt-story5`, commit cb46afc, baseline 14353f6.
Lignes « d.N » = lignes du diff `git -C ..\wt-story5 diff 14353f6 cb46afc -- . ':!_bmad-output/specs'` (à régénérer, non commité).

## Intent Alignment (IA)
- IA1. Le cœur de l'expérience stagiaire (curseurs qui redessinent les barres, puce qui choisit le token, lignes écartées grisées, `p` fixe et `p_sampled` mobile, pas d'erreur console) n'est testé nulle part de bout en bout : l'E2E n'a pas de moteur en processus ; seule la branche « indisponible » est vue.
- IA2. Oracle : comparaison `distribution` vs `candidates_from_logits` seulement sur un vocabulaire de 8 (tail ≈ 0) ; le cas tail > 0 avec top-k off et top-p actif n'est pas comparé à l'oracle.
- IA3. A/B : « Arrêter » de la page jamais pressé (arrêt testé par `session.stop()` seulement) ; jamais avec un modèle cloud ; « la distribution vivante porte sur A » non distinguable (A et B produisent « Oui »).
- IA4. Indisponible sur serveur/cloud : la route rend le 404 générique « Générez d'abord… », pas la raison spécifique (la page montre la raison, l'API non).
- IA5. Schéma de fenêtre : remplissage proportionnel et croissance de la réserve non testés ; voies « raisonnement puis réponse » existantes non vérifiées comme conservées.
- IA6. Processus : incréments non commités séparément ; vérification des défauts `llama_cpp` seulement en docstring.

## Verification Gap (VG)
- VG1. [patch] Distribution caduque après changement de modèle (`kept[0] is not self._engine`, app_session.py ~7995/8006) non testée ; `booted_session` réutilise le même moteur. Test : fabrique qui crée un nouveau `FakeEngine` par chargement, générer, `select_model`, `join`, puis `lab_state()["distribution"] == {"tokens": 0}` et `llm_distribution(0, …)` lève `DistributionMissing`.
- VG2. [patch] « La distribution vivante est celle de A » : test `test_compare_runs_a_then_b_under_one_state` ne distingue pas A de B (même sortie). Utiliser `FakeEngine(outputs=["Oui", "Non!"], …)` et vérifier `llm_distribution(0, SCREEN)["token_text"] == "O"`.
- VG3. [patch] Branche top-p avec tail non nulle (`base = sum(values) + tail`, candidates.py ~156) jamais exercée ; ajouter un oracle sur quelques centaines de logits (tête piquée, longue traîne plate), `Sampling(1.0, 0, 0.8, 0.0)`.
- VG4. [patch] `Fragment.top` du vrai moteur (`engine.py` ~374/377/400) jamais vérifié ; ajouter `test_fragments_carry_the_most_probable_tokens` dans `tests/test_engine_candidates.py` (tiny-llama.gguf synthétique) : `top` a `{p, texts, tail}`, longueurs `min(TOP, vocab)`, `p` décroissant, `tail ≈ 1 − sum(p)`, branche stop comprise.
- VG5. [defer] Logique de page de la distribution vivante non pilotée par un test (pas de moteur en processus en E2E ; il faudrait des `page.route` simulant `/api/llm_lab` et `/api/llm_lab/distribution`).
- VG6. B tourne avec `candidates=True` sans mémoire : softmax plein vocabulaire et 5 candidats par token au journal, inutiles (CPU).

## Blind Hunter (BH)
- BH1. B tourne encore si A a échoué (prompt trop long, erreur moteur) : `_run_compare` ne saute B que si `cancel.cancelled` → erreur doublée.
- BH2. `kept_text` « le tirage se fait entre eux » faux quand aucun filtre ne coupe (top-k 0, top-p 1, min-p 0 : le vrai tirage couvre tout le vocabulaire).
- BH3. « 100 » en dur dans `tail_help_text` (3 langues) et EXPERIENCE.md, alors que `TOP = 100` est une constante : passer en paramètre.
- BH4. Schéma de fenêtre : « tokens » alors que `llm_token` est un fragment sur llama-server/Ollama/cloud ; `prompt_tokens` sans « ≈ » quand `exact` est faux.
- BH5. La distribution ne marque pas le candidat effectivement tiré (pas de `chosen`) ; s'il est hors des 100, il manque sans avertissement.
- BH6. Après rechargement : la distribution revient mais pas les puces ; le texte invite à cliquer une puce absente.
- BH7. Français : « invite » et « prompt » mélangés ; unifier sur « prompt ».
- BH8. Question de la section 1 sur les tokens spéciaux du gabarit, alors que la section 1 tokenise sans gabarit.
- BH9. Accessibilité : les deux pourcentages d'une ligne n'ont pas de nom accessible (en-têtes `aria-hidden`).
- BH10. Tests manquants : top-p avec tail (= VG3), modèle changé (= VG1), « Arrêter » pendant B après A, comparaison cloud.
- BH11. Pas d'E2E positif des barres ni de capture `distribution-bars`/`window-diagram` (= VG5).
- BH12. ARCHITECTURE-SPINE se contredit sur l'état du navigateur (« le brouillon est la seule chose gardée » puis réglages B gardés) ; paragraphe « État du navigateur » à mettre à jour (`wavestack.llm.sampling_b`).
- BH13. Pendant une comparaison, la fin de A écrit « Réponse terminée. » sous « Générer » (`#generate-status`) alors que B tourne.
- BH14. Softmax plein vocabulaire calculé deux fois par token (`read_logits` appelle `candidates_from_logits` puis `top_from_logits`).
- BH15. Réglages B sans remise à zéro ; si le modèle ne règle pas la température, B = A sans le dire.
- BH16. Schéma de fenêtre : `free_text` « Libre » sert d'infobulle à la part du prompt ; prompt > usable borné à 100 %, le dépassement n'est pas montré.

## Edge Case Hunter (EC)
- EC1. (= BH1) B après échec de A.
- EC2. `renderDistributionIdle` n'invalide pas le ticket : une réponse en vol redessine d'anciennes barres (llm.js ~506-531, 828). Garde : `store.dist.ticket += 1`.
- EC3. Si la fin de B n'arrive pas (émission ratée, trou SSE), `pending.compare` reste bloqué et les boutons restent désactivés jusqu'au rechargement ; garde : à `session_state` idle, vider `pending.compare`.
- EC4. Si l'émission du `llm_generation_ended` annulé de B lève, la page ne voit jamais B finir.
- EC5. Un « Générer » simple après une comparaison laisse les anciennes colonnes A/B visibles (masquer `#compare-lanes` quand la requête n'est pas une voie de comparaison).
- EC6. E2E `run_e2e.py` ~7664 : si le faux llama-server finit A et B avant l'envoi, l'envoi passe (200) et lance un vrai tour.
- EC7. (faible) La mémoire n'existe qu'avec « Montrer les tokens candidats » ; une génération sans cette option efface la précédente.
