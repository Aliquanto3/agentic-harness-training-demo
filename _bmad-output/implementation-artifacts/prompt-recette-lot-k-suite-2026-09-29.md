# Prompt pour le Claude Code du PC cible : recette de la suite du lot K (2026-09-29)

À coller tel quel dans Claude Code sur le PC cible, depuis le dossier du dépôt. Il couvre les
quatre corrections de `spec-lot-k-suite-contre-verification-2026-09-29.md` (K1, K2, K3, K7 de
la contre-vérification de `resultats-lot-k-2026-09-29.md`), et rien d'autre.

---

Tu vas vérifier sur ce poste la suite du lot K de WaveStack. Travaille en français.

## Contexte

- Poste : Windows 11, PowerShell 5.1, sans droits d'administrateur, CPU seul, 16 Go ; 2B intégré,
  fenêtre 4 096.
- Dépôt : branche `claude/lot-k-recette-pc`, commits `e4da3d3` (K1, barre haute), `0bc5f56`
  (K2, prompts), `9bca13d` (K3, consignes), `e103b5e` (K7, icône), puis le commit de
  documentation ; teste la tête de la branche.
- Attendus détaillés : section « À vérifier sur PC » de
  `_bmad-output/implementation-artifacts/spec-lot-k-suite-contre-verification-2026-09-29.md`.

## Règles

1. Ne modifie rien du dépôt ni du dossier de données réel : tout lancement de WaveStack passe
   par `WAVESTACK_DATA_DIR` vers un dossier jetable (celui de la séance précédente convient).
2. Outlook et Teams fermés pendant les tours du 2B.
3. Consigne au fil de l'eau dans
   `_bmad-output/implementation-artifacts/resultats-lot-k-suite-2026-09-29.md` (ce fichier seul,
   pas de commit) : point, geste, attendu, obtenu, OK / KO / non fait, moyen. Si un point échoue,
   décris l'anomalie et propose un correctif sans l'appliquer.

## Étapes

1. **Tests automatiques** : `git fetch`, `git checkout --detach origin/claude/lot-k-recette-pc`,
   `uv sync --extra compression`, `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run pytest -q`, puis `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python
   tools/e2e/run_e2e.py` (0 FAIL, dont `[linked_view]` à 853 × 433 et 911 × 512), puis
   `git restore tools/e2e/screenshots`.
2. **K1, zoom 150 % émulé** : Playwright (Chromium puis Edge), viewport 853 × 433 et 911 × 512,
   normal puis « Mode projection », après un tour qui appelle la Calculatrice (nœud Calculatrice,
   « — » de Contexte LLM) : barre sur une ligne, « Réinitialiser » entier dans la barre et la
   fenêtre, `document.scrollingElement.scrollWidth − clientWidth` ≤ 1, panneau « Fenêtre ▾ »
   ouvert entier ; le bouton de projection montre « Aa ». Contrôle aussi 1 024 × 700 (légende
   visible, non recouverte) et 1 280 × 720 (puce « · lié » entière). Captures.
3. **K1, vrai zoom d'Edge** : fenêtre de 1 280 × 650, Ctrl + molette à 150 % puis 125 % : mêmes
   attendus (à la main, captures).
4. **K2, IAM** : « Métier IAM », prompt 1, « Vider la conversation », prompt 2, sans secours
   d'abord : deux liens learn.microsoft.com **en tête** de chaque réponse, réponse en 5 lignes
   environ, tour `completed` (pas `limit`), aucun `context_overflow`.
5. **K2, Souveraineté p1 sans secours** : prompt 1 seul ; note ce que fait le 2B (appel ou non,
   `outbound_request`) ; si la recherche part, trois jeux au plus, chacun commençant par son lien
   data.gouv.fr, tour `completed`. Puis le secours « Forcer l'appel · datagouv__search_datasets »
   (préréglage « cybersécurité »), « Rejouer le dernier prompt » : mêmes critères de longueur et
   de liens.
6. **K2, SOC p2** : « Métier SOC », prompt 1 (secours « Alertes SIEM (SOC) » si besoin), prompt 2
   (secours « Comptes à privilèges (SOC, confidentiel) » si besoin) : `hook_decided h1 block`,
   réponse qui propose de transmettre à un **analyste SOC habilité** (ni « Démonstrateur » ni
   personne inventée).
7. **K3, « Lazy loading »** : prompt 1 sans secours : note l'appel de `load_tool_doc`, si
   `local__define_term` est appelé ou non, et la réponse ; puis le secours « Forcer l'appel ·
   local__define_term » (préréglage « MCP »), « Armer », « Rejouer le dernier prompt » : appel
   `trigger user`, réponse « Model Context Protocol ».
8. **K3, consignes** : relis les consignes de « Lazy loading » et « Métier Souveraineté » dans
   l'application : ce qu'on observe, pourquoi, et « Forcer l'appel » présenté comme la
   démonstration ; dis si elles collent à ce que fait le 2B aux étapes 5 et 7.
9. **K7, icône** : Edge, profil neuf : aucune erreur 404 sur `/favicon.ico` en console ; icône
   violette « W » dans l'onglet de `/`, `/diagnostic`, `/models`, `/llm`.
10. **Synthèse** : tableau des quatre points (OK / KO / non fait), mesures clés, anomalies avec
    correctif proposé, et ce qui reste à la main pour Anaël.
