# Prompt pour le Claude Code du PC cible : recette du lot K (2026-09-29)

À coller tel quel dans Claude Code sur le PC cible, depuis le dossier du dépôt. Il couvre les
huit corrections du lot K (`spec-lot-k-corrections-recette-pc-2026-09-29.md`), issues des
anomalies A1 à A8 de `resultats-test-pc-2026-09-29.md`, et rien d'autre.

---

Tu vas vérifier sur ce poste les huit corrections du lot K de WaveStack. Travaille en français.

## Contexte

- Poste : Windows 11, PowerShell 5.1, **sans droits d'administrateur**, CPU seul, 16 Go.
  Modèles : Qwen3.5-2B et Qwen3.5-4B (dossier des modèles de WaveStack), llama-server `b11239`
  déjà installé dans `%LOCALAPPDATA%\llama.cpp` (sinon, point 8 d'abord).
- Dépôt : branche `claude/lot-k-recette-pc`, commits `d50c1c4` (point 1) à `1297e2b` (point 8)
  et `05e83d8` (suite du point 2), puis le commit de documentation `8c7ef9e`, le commit de
  revue `bfe28eb` et le bilan `8b2cab4` ; teste la tête de la branche.
- Attendus détaillés : section « À vérifier sur PC » de
  `_bmad-output/implementation-artifacts/spec-lot-k-corrections-recette-pc-2026-09-29.md`
  (geste, attendu, critère, par point). Mesures d'avant le lot : `resultats-test-pc-2026-09-29.md`.

## Règles

1. **Ne modifie rien** du dépôt ni du dossier de données réel. Scripts hors du dépôt ; tout
   lancement de WaveStack passe par `WAVESTACK_DATA_DIR` vers une copie jetable du dossier de
   données (`settings.json` compris : le point 1 doit lire les anciennes sondes). Pour les
   modèles, un dossier de **liens physiques** (`mklink /H`), pas de jonction.
2. Ne réécris jamais `settings.json` pour corriger d'anciennes sondes (le changement de
   chemins du jetable, au point 1, n'en est pas une : aucune valeur ne change), et ne relance
   pas de sonde de tous les modèles.
3. Avant une mesure de mémoire ou de temps : Outlook et Teams fermés, état d'Edge noté.
4. llama-server toujours avec `-np 1 -c N`.
5. Consigne au fil de l'eau dans `_bmad-output/implementation-artifacts/resultats-lot-k-2026-09-29.md`
   (ce fichier seul, pas de commit) : point, geste, attendu, obtenu, OK / KO / non fait, moyen.
   Si un point échoue, décris l'anomalie et propose un correctif sans l'appliquer.

## Étapes

1. **Tests automatiques** : `git fetch`, `git checkout --detach origin/claude/lot-k-recette-pc`,
   `uv sync --extra compression`, `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run pytest -q`, puis avec `WAVESTACK_TEST_GGUF` = le 2B :
   `uv run pytest -s -rA tests/test_program.py -k fits` (tableau par prompt : note la plus petite
   marge), puis, avec `PYTHONUTF8=1` (sans lui, une sortie redirigée en cp1252 lève
   `UnicodeEncodeError` et fait échouer la suite en cascade),
   `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` (0 FAIL attendu,
   y compris `[linked_view]` aux quatre largeurs), et `git restore tools/e2e/screenshots`.
2. **Point 1 (A2)** : l'entrée ancienne doit être lue par WaveStack. Dans le `settings.json`
   **jetable** seulement, réécris les clés de `probed_models` (et la valeur `ref` de
   `selected_model`) du vrai dossier des modèles vers le dossier de liens physiques : un lien
   physique garde la taille et la date du fichier, donc les valeurs des entrées restent telles
   quelles (ne touche à aucune valeur). Vérifie ensuite, avant tout lancement, que l'entrée du
   2B stocke toujours `kv_bytes_per_token` = 49 152 (sonde d'avant le lot). Puis : empreinte du
   `settings.json` jetable ; lancement ; panneau « Fenêtre ▾ »
   du 2B : 48 / 96 / 192 Mo ; `context_window` 8 192 et mesure de RSS et mémoire privée avant et
   après un tour (≈ + 48 Mio). Budget fixe 6 144 Mo (`config.save_setting` sur le jetable), 4B,
   16 384 : accepté, hausse ≈ 384 Mio (± 30 %). Empreinte du `settings.json` jetable inchangée
   par les lectures (seuls les réglages que tu poses le changent).
3. **Point 2 (A1)** : Playwright (Chromium) puis Edge, 1 280, 1 366, 1 440, 1 600 px, normal et
   projection, geste de l'E2E (nœud Calculatrice, « — » de Contexte LLM) : puce « · lié » entière,
   `scrollWidth - clientWidth` ≤ 1, barre sur une ligne ; 1 280 × 650 aux zooms 125 et 150 % :
   légende non recouverte. Captures.
4. **Point 3 (A5)** : le 2B intégré, fenêtre 4 096. « Lazy loading » prompt 1, puis si besoin le
   secours « Forcer l'appel · local__define_term » (préréglage « MCP »), « Rejouer le dernier
   prompt ». « Métier SOC » prompts 1 et 2 (tour 1 `completed`, h1 block au tour 2). « Métier
   IAM » prompt 1, « Vider la conversation », prompt 2 (liens cités, pas de débordement).
   « Métier Souveraineté » : prompt 1, secours « Forcer l'appel · datagouv__search_datasets »
   (préréglage « cybersécurité ») si besoin, « Vider la conversation », prompt 2 (secours
   Microsoft Learn si besoin, préréglage « Journalisation des connexions admin (Souveraineté) »).
   « Sous-agent » (constat reporté de la revue) : note la jauge avant l'envoi du prompt 4, pour
   trancher le modèle d'historique du test `fits`. Relève les `outbound_request`, les
   `tool_started` (trigger), les statuts de tour et les réponses.
5. **Point 4 (A3)** : fenêtre 8 192 enregistrée, `llama-server -np 1 -c 4096` sur le 2B,
   WaveStack relancé : bouton « Fenêtre 4 096 ▾ », infobulle « …, 8 192 choisi. » ; `/diagnostic`
   et `/api/diagnostic` : conseil « relancez-le avec `-np 1 -c 8192` ». Puis llama-server
   arrêté, retour au 2B intégré et à 4 096.
6. **Point 5 (A4)** : Chromium puis Edge, « Sombre », `/diagnostic`, « Clair », « Précédent » :
   sélecteur « ☀ Clair » ; recommence avec une vraie navigation (bouton du navigateur).
7. **Point 6 (A8)** : Edge, « Sous-agent », « Afficher les actions forcées », « Déléguer au
   sous-agent » : `aria-expanded` `true` ouvert, `false` fermé (DevTools, arbre
   d'accessibilité) ; 1 280 × 650 à 100, 125 et 150 % : « Appliquer » et « Fermer » visibles
   en pied du panneau Fenêtre sans défiler.
8. **Point 7 (A7)** : « Skills », prompt suggéré : `load_skill`, aucun `read_file`, compte rendu
   de la réunion du prompt (Paul, Julie, lundi 10 h), ni Alice ni Bruno.
9. **Point 8 (A6)** : bloc « Installation » de P5 du cahier, dans un PowerShell 5.1 neuf, vers un
   dossier de test (`$dest` suffixé `-lotk`) : `$asset.name` et version affichée, code 0.
10. **Synthèse** : tableau des huit points (OK / KO / non fait), mesures clés, anomalies avec
    correctif proposé, et la liste de ce qui reste à la main pour Anaël (lecteur d'écran, vrai
    zoom d'Edge, avis sur les réponses du 2B).
