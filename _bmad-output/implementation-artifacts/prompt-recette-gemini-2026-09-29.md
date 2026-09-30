# Prompt pour le Claude Code du PC cible : recette de l'endpoint Gemini (2026-09-29)

À coller tel quel dans Claude Code sur le PC cible, depuis le dossier du dépôt. Il couvre
`spec-endpoint-gemini-ai-studio.md` (entrée cloud Gemini, raisonnement activable, signatures de
pensée), et rien d'autre. Ce poste a la clé AI Studio ; le poste de développement ne l'a pas :
tout ce qui suit n'a été vérifié que contre un faux fournisseur.

---

Tu vas vérifier sur ce poste l'endpoint Gemini (Google AI Studio) de WaveStack. Travaille en
français.

## Contexte

- Poste : Windows 11, PowerShell 5.1, sans droits d'administrateur, CPU seul, 16 Go.
- Dépôt : branche `main` (lot Gemini fusionné) ; teste sa tête.
- Attendus détaillés : `_bmad-output/implementation-artifacts/spec-endpoint-gemini-ai-studio.md`
  (matrice des cas, critères d'acceptation, « Design Notes »).
- Entrée livrée (`wavestack.toml`, `[[cloud.models]]` `id = "gemini"`) : `gemini-3.5-flash-lite`,
  clé par `GEMINI_API_KEY`. Raisonnement `think_tags`, balises `<thought>` / `</thought>` ;
  allumé : `extra_body.google.thinking_config = {thinking_level: "low", include_thoughts: true}` ;
  éteint : `reasoning_effort: "minimal"`. `tool_call_extra` : la signature de contournement
  `skip_thought_signature_validator`, pour les seuls appels fabriqués par le harnais (actions
  forcées).
- Formes relevées par une sonde de l'API réelle le 2026-09-29, que le code et le faux
  fournisseur de l'E2E reproduisent ; la recette les confirme dans l'application :
  - `extra_body` avec `include_thoughts` et `reasoning_effort: "minimal"` acceptés ;
  - pensée dans `content`, `<thought>` et la pensée dans des fragments marqués
    `extra_content.google.thought`, `</thought>` dans le fragment suivant, non marqué, avec le
    début de la réponse ;
  - appel d'outil en un fragment, sans `index`, `finish_reason: "stop"` ; rejoué sans
    signature : 400 au corps en tableau JSON ; avec `skip_thought_signature_validator` : 200 ;
  - `usage` sur chaque fragment ; `completion_tokens` sans les tokens de réflexion, que
    `total_tokens` compte (WaveStack affiche `total − prompt` en tokens produits).

## Règles

1. **La clé.** Chaque appel PowerShell de Claude Code est un processus neuf : une variable
   posée par Anaël dans son propre terminal ne l'atteint jamais, et une clé tapée dans la
   conversation finit dans la transcription. Donc :
   - Anaël écrit la clé **une fois**, lui-même, hors de Claude Code, dans un fichier **hors du
     dépôt** : `$env:USERPROFILE\.wavestack\gemini.key` (jamais versionné, jamais copié ailleurs) ;
   - toute commande qui en a besoin la lit **dans le même appel PowerShell** :
     `$env:GEMINI_API_KEY = (Get-Content -Raw "$env:USERPROFILE\.wavestack\gemini.key").Trim()` ;
   - tu n'affiches, ne recopies ni ne cites jamais la clé ni un morceau ; ni `setx`, ni
     `api_keys.json`, ni saisie au diagnostic pendant cette recette. Si le fichier manque,
     arrête-toi et demande-le à Anaël, sans lui demander la clé.
2. **Lancement.** Ne modifie rien du dépôt ni du dossier de données réel. WaveStack se lance
   avec l'outil PowerShell en `run_in_background`, dans un seul appel qui pose, dans l'ordre :
   la clé (règle 1, sauf à l'étape 2), `$env:WAVESTACK_DATA_DIR = "$env:TEMP\wavestack-gemini"`
   (dossier jetable), `$env:BROWSER = "cmd /c rem"` (aucun navigateur ne s'ouvre), puis
   `uv run wavestack --port <port libre> *> "$env:TEMP\wavestack-gemini\wavestack.log"`. Prends
   un port libre (par exemple 8431 si `Test-NetConnection 127.0.0.1 -Port 8431` échoue) et
   attends `GET /api/health` avant d'agir ; arrête le processus entre deux étapes.
3. Les replis se font dans le `settings.json` de ce dossier jetable, jamais dans
   `wavestack.toml` ni dans le code. `settings.json` fusionne avec `wavestack.toml` par `id`,
   champ par champ ; `null` ne retire qu'une clé de premier niveau de `reasoning.on` ou
   `reasoning.off` (par exemple `"extra_body": null`), rien de plus profond.
4. Consigne au fil de l'eau dans
   `_bmad-output/implementation-artifacts/resultats-recette-gemini-2026-09-29.md` (ce fichier
   seul, pas de commit) : point, geste, attendu, obtenu, OK / KO / non fait, moyen. Si un point
   échoue, décris l'anomalie et propose un correctif sans l'appliquer au code.

## Étapes

0. **Garde-fou** : après le `git checkout` de l'étape 1, vérifie que `wavestack.toml` du commit
   testé contient `id = "gemini"` (`Select-String -Path wavestack.toml -Pattern '^id = "gemini"'`).
   Sinon, arrête tout : ce n'est pas le bon commit.
1. **Tests automatiques** : `git fetch`, `git checkout --detach origin/main`,
   `uv sync --extra compression`, `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run pytest -q` (tout vert), puis `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0
   python tools/e2e/run_e2e.py` : 0 FAIL, dont `[gemini_shape]` et `[model_catalog]` (groupe
   « Réseau · Gemini (Google) »). Puis `git restore tools/e2e/screenshots`. Ces tests n'appellent
   pas Google : ils valident le code contre un faux Gemini.
2. **Sans clé** : lance WaveStack (règle 2) sans poser `GEMINI_API_KEY`
   (`Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue` dans le même appel). Sur `/models` et dans le
   sélecteur de la barre haute : « RÉSEAU · Google AI Studio · gemini-3.5-flash-lite » dans le
   groupe « Réseau · Gemini (Google) », raisonnement « activable », indisponible, raison donnée
   (clé API). Arrête WaveStack.
3. **Avec la clé** : relance WaveStack (règle 2), la clé lue dans le fichier dans le même
   appel.
   Au diagnostic, la ligne Gemini dit « Clé fournie par la variable GEMINI_API_KEY » et
   `generativelanguage.googleapis.com` fait partie des hôtes autorisés (ligne réseau du
   diagnostic ou `/api/diagnostic`). Clique sur « Tester » : deux appels, le second rejoue la
   signature du premier (`outbound_request.body` du 2e appel : `tool_calls[0].extra_content.google.thought_signature`
   présent), résultat « Test réussi » avec l'appel d'outil reçu. Si c'est un 400, note le message
   du fournisseur mot pour mot.
4. **Choisir Gemini** dans le sélecteur (avertissement confirmé), puis le scénario
   « Outils natifs » et ses trois prompts (« Quelle heure est-il ? », « Combien font 1234
   multiplié par 5678 ? », « Lis le fichier recette_crepes.txt et donne-moi la liste des
   ingrédients. »), **raisonnement éteint**, puis « Vider la conversation » et les trois mêmes
   prompts **raisonnement allumé**. Pour chaque tour, relève dans le journal (`/api/stream`,
   rejoué en entier à la connexion ; l'API n'a pas de route `/api/events`) :
   - `outbound_request.body` de chaque appel : éteint, `reasoning_effort: "minimal"`, sans
     `extra_body`, `max_tokens` 512 ; allumé, `extra_body…include_thoughts: true`, sans
     `reasoning_effort`, `max_tokens` 1 536 ; au 2e appel, l'appel d'outil rejoué avec son
     `extra_content` ;
   - `model_call_ended` : `reasoning` (vide éteint, rempli allumé), `text` (sans balise
     `<thought>`), `tool_calls[].extra_content` (signature présente), `raw_output` (la forme
     réelle des deltas : **recopie un extrait** qui montre où arrive la pensée),
     `stop_reason`, `usage_source` (`api` attendu), `output_tokens` (`total_tokens −
     prompt_tokens` du fournisseur, réflexion comprise : raisonnement allumé, nettement plus
     que le texte visible) ;
   - la carte Raisonnement (réglable, sans verrou) et la Vue humain (réflexion à part, réponse
     sans balise) ; statut du tour `completed`, aucun `harness_error`.
   Joue aussi une **action forcée** (« Forcer l'appel » sur la Calculatrice, « Armer », puis un
   prompt) : le corps porte `extra_content.google.thought_signature =
   "skip_thought_signature_validator"` sur l'appel fabriqué, et Google l'accepte.
5. **Tableau `/models`** relu avec la clé : ligne Gemini disponible (ou « actif »), éditeur
   « Gemini (Google) », raisonnement « activable », fenêtre, outils « oui ».
6. **Fuite de clé** : cherche la clé dans le journal (`/api/stream` enregistré dans un fichier
   du dossier jetable), dans `wavestack.log` et dans `audit.log` du dossier jetable, ainsi que
   ses **4 premiers** et ses **4 derniers** caractères : zéro occurrence de la clé entière
   attendue. Fais la recherche par un script PowerShell qui lit la clé dans le **même fichier**
   (`$env:USERPROFILE\.wavestack\gemini.key`) et n'affiche que les nombres d'occurrences par
   fichier et par morceau, jamais la clé ni ses morceaux. Une occurrence d'un morceau de 4
   caractères n'est pas forcément une fuite :
   - les clés AI Studio commencent toutes par `AIza` ou `AQ.` : ce préfixe peut se trouver
     ailleurs ;
   - la signature `thought_signature` (base64) est renvoyée telle quelle à Gemini, donc
     présente en clair dans `context_rendered.body` et `outbound_request.body` (le corps tracé
     est les octets envoyés) ; 4 caractères de la clé peuvent y tomber par hasard.
   Dans ces deux cas, rapporte l'occurrence par son contexte (l'événement, le champ, les
   caractères voisins, sans le morceau lui-même) : c'est une coïncidence, pas une fuite. Toute
   autre occurrence est une anomalie.
7. **Replis si besoin** (dans `settings.json` du dossier jetable, WaveStack arrêté, puis relancé
   et l'étape 4 rejouée pour le cas concerné) :
   - pensée ailleurs qu'entre `<thought>` : autres balises
     `{"cloud": {"models": [{"id": "gemini", "reasoning": {"tags": ["<…>", "</…>"]}}]}}`, ou
     `"format": "field"` si elle arrive dans `reasoning` / `reasoning_content` ;
   - `extra_body` refusé (400) : `"reasoning": {"on": {"extra_body": null,
     "reasoning_effort": "low"}}` (raisonnement actif mais invisible) ;
   - `minimal` refusé, ou modèle indisponible : `"model": "gemini-3.6-flash"` (accepte
     `minimal` ; 0,75 $ / 3,75 $, puis 1,50 $ / 7,50 $ au 2027-01-01).
   Note pour chaque repli ce qui a changé dans le corps et dans `model_call_ended`.
8. **Synthèse** dans `resultats-recette-gemini-2026-09-29.md` : tableau des étapes (OK / KO /
   non fait), la forme réelle du raisonnement et des signatures (extraits de `raw_output`, sans
   clé), les replis appliqués et leur `settings.json` exact, les coûts observés si la console
   les montre, les anomalies avec correctif proposé, et ce qui reste à la main pour Anaël
   (par exemple reporter un repli dans `wavestack.toml`).
