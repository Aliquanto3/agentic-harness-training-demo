# Guide de test sur le PC cible : palier 2 (stories 12 à 21)

Pour récupérer la branche du palier 2 et la tester fonctionnellement sur le PC professionnel
(Windows 11, sans droits administrateur, CPU seul). Les commandes sont en PowerShell et se
lancent depuis la racine du clone. Sources : `README.md`, `weekend-report-2026-09-26.md`
(sections 3 et 4), stories 12 à 21, `tools/bench/README.md`, `tools/e2e/README.md`.

## 0. En bref

- **Durée** : environ 1,5 jour, en deux séances.
  - Séance 1 (3 à 4 h) : sections 1 à 4 (code, installation, tests, bancs, modèles, index).
  - Séance 2 (5 à 7 h) : section 5 (six modules, soit 5 h 15 de programme, puis les scénarios
    métier et les modèles). Un tour chargé peut dépasser 100 s (story 9 : 20 à 30 tokens/s
    en lecture du contexte).
- **À avoir sous la main** :
  - le proxy ouvert vers `pypi.org`, `files.pythonhosted.org`, `abetlen.github.io`,
    `github.com`, `huggingface.co`, `*.hf.co`, `learn.microsoft.com` et `mcp.data.gouv.fr` ;
    en option, `api.groq.com`, `api.mistral.ai`, `fr.wikipedia.org` et
    `calendrier.api.gouv.fr` ;
  - les GGUF Qwen3.5-2B Q4_K_M amont (unsloth) et Qwen3.5-4B, dans
    `%LOCALAPPDATA%\WaveStack\models` ;
  - environ 4 Go libres : 2,1 Go pour le banc, 121 Mo pour l'embedding, 438 Mo pour le
    reranker, 285 Mo pour l'extra `compression`, plus Chromium pour l'E2E (taille à
    vérifier) ;
  - en option : des clés Groq et Mistral, Ollama, et `llama-server.exe` (llama.cpp) ;
  - Teams et Edge fermés pendant les mesures : ils saturaient la RAM à la story 9.
- **Ordre** : 1 → 2 → 3 → 4, avec les bancs avant de lancer WaveStack. Ensuite 5, dans
  l'ordre des modules, puis le métier et les modèles. Enfin 6 et 7.
- **Revenir en arrière** : ne fusionnez rien avant la section 7. `git switch main`, puis
  `uv run wavestack`, resynchronisent sur le `uv.lock` de `main`. Le palier 2 enrichit le
  dossier de données (`probed_models`, `selected_model`, `memory.json`) : sauvegardez-le
  d'abord.

```powershell
$d = "$env:LOCALAPPDATA\WaveStack"
New-Item -ItemType Directory -Force "$d\sauvegarde-palier-1" | Out-Null
Copy-Item "$d\settings.json", "$d\api_keys.json", "$d\memory.json" "$d\sauvegarde-palier-1\" -ErrorAction SilentlyContinue
```

## 1. Récupérer le code

```powershell
cd C:\chemin\vers\agentic-harness-training-demo
git status                                   # l'arbre doit être propre
git fetch origin
git switch claude/dreamy-cerf-gdjtee         # crée la branche locale qui suit origin
# Si Git ne la crée pas tout seul :
git switch -c claude/dreamy-cerf-gdjtee --track origin/claude/dreamy-cerf-gdjtee
git log --oneline -1
```

- [ ] HEAD attendu : `705e0e2 docs: rapport du week-end, palier 2 (stories 12 à 21)`, ou un
  commit plus récent s'il ajoute ce guide. La référence est le dernier commit de la PR #1.
- Zip, sans Git : sur GitHub, choisissez la branche, puis « Code » → « Download ZIP ». Avec
  le navigateur connecté, l'adresse directe est
  `https://github.com/Aliquanto3/agentic-harness-training-demo/archive/refs/heads/claude/dreamy-cerf-gdjtee.zip`.
  Un zip ne permet pas de committer le `uv.lock` régénéré : préférez le clone.

## 2. Installer

```powershell
$env:UV_SYSTEM_CERTS = "1"     # derrière le proxy : certificats du système (README), valable pour ce terminal
uv lock
git diff --stat uv.lock
uv lock --check
```

Les entrées `sqlite-vec` et `headroom-ai` du verrou, et leurs 39 dépendances, ont été
écrites à la main : l'index abetlen était injoignable depuis le conteneur. `uv lock` les
recalcule.
- [ ] Si `git diff` est vide, le verrou est confirmé.
- [ ] S'il ne l'est pas, **c'est attendu** : committez la version produite par `uv lock`.

```powershell
git add uv.lock
git commit -m "build: uv.lock régénéré par uv lock sur le PC cible"
git push
uv sync                          # socle, sans Headroom
uv sync --extra compression      # ajoute headroom-ai 0.38.0 (environ 40 paquets, 285 Mo)
```

Attention : un `uv sync` sans `--extra compression` retire Headroom, alors que `uv run …` le
garde. Relancez `uv sync --extra compression` après chaque mise à jour.

**AppLocker et WDAC.** Plusieurs binaires natifs non signés sont installés sous `.venv\`
(chemins exacts à vérifier) : `_core*.pyd` et `ast-grep.exe` (headroom-ai), l'extension
sqlite-vec et les DLL de llama.cpp. Au lancement, un blocage se voit ainsi :
- [ ] la carte Compression est indisponible et en donne la raison ;
- [ ] la carte RAG affiche « sqlite-vec ne se charge pas ».

Sans droits d'administrateur, il n'y a pas de contournement : notez le fichier bloqué et
demandez une exception au support.

## 3. Vérifications automatiques rapides

```powershell
uv run pytest -q
```

- [ ] Attendu : **770 réussis, 5 sautés**, résultat revérifié sous Linux. Tout échec propre
  à Windows (chemins, fins de ligne, sockets) est un écart à remonter.

Tests `model`, facultatifs, avec un vrai GGUF (adaptez le nom du fichier) :

```powershell
$env:WAVESTACK_TEST_GGUF = "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf"
uv run python -m pytest -m model tests/test_probe.py tests/test_render_reference.py
```

**Parcours E2E Playwright**, facultatif : il rejoue l'interface avec un faux modèle.
Chromium s'installe dans le profil (`%LOCALAPPDATA%\ms-playwright`), **sans droits
d'administrateur**. Les hôtes de téléchargement de Playwright sont à faire autoriser par le
proxy (liste à vérifier).

```powershell
uv run --with playwright==1.56.0 playwright install chromium
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only programme soc iam sovereignty
```

- [ ] Attendu : 327 vérifications et 0 échec. Une ligne `KNOWN [Ax]` n'est pas un échec. Le
  parcours n'a **jamais tourné sous Windows** (à vérifier). Si Chromium ne s'installe pas,
  sautez cette étape : la section 5 ne dépend pas d'elle.

## 4. Préparer les modèles et les données

### 4.1 Bancs de la story 12 (WaveStack arrêté)

```powershell
uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom --json | Out-File -Encoding utf8 bench-headroom.json
uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download --json | Out-File -Encoding utf8 bench-embed.json
```

`embed --download` télécharge environ 2,1 Go dans `~\.cache\wavestack-bench` ;
`--models-dir D:\modeles` en choisit un autre. Si le proxy bloque, copiez les GGUF dans
`<models-dir>\<propriétaire>__<dépôt>\<fichier>`, puis relancez sans `--download`. Sous
Windows, `strace` n'existe pas : le banc ne voit que la garde Python, c'est normal.
- [ ] Headroom : verdict « RETENU », RSS ajouté (≈ 130 Mo attendus, seuil 300), aucune
  tentative réseau, pas de torch.
- [ ] `granite107m_q8` : recall@1 ≥ 0,75, MRR, RSS ajouté ≤ 600 Mo, temps par élément,
  `pooling_gguf` (2 = CLS).
- [ ] `bgererank_m3_q4km` : MRR égal ou meilleur, RSS ajouté ≤ 800 Mo.
- [ ] Les replis fastembed (`fe_minilm_multi`, `fe_mmarco_rerank`) finissent « mesuré ».
- Où reporter :
  - le verdict et les deux JSON dans la section « Verdict » de la story 12 ;
  - les RSS dans `measured_rss_mb` de `[rag.embedding]` et `[rag.reranker]`, et dans
    `[compression] cost_mb` s'il diffère.

  Si le banc recommande un autre modèle, remontez-le sans modifier `wavestack.toml` : il
  faudrait changer les dimensions, les préfixes et l'index.

### 4.2 Modèles d'embedding et de reranker

- **Par l'interface** (vrai test du téléchargement) : sur la carte RAG, cliquez « Télécharger
  le modèle d'embedding (≈ 121 Mo) ». Cochez ensuite « Reranking » et cliquez « Télécharger
  le modèle de reranking (≈ 438 Mo) ». Le sha256 de chaque fichier apparaît dans le Journal
  des événements (« effect_applied », effet `model_download`).
- **À la main**, en reprenant les fichiers du banc :

```powershell
$m = "$env:LOCALAPPDATA\WaveStack\models"; $b = "$HOME\.cache\wavestack-bench"
New-Item -ItemType Directory -Force "$m\embedding", "$m\reranker" | Out-Null
Copy-Item "$b\bartowski__granite-embedding-107m-multilingual-GGUF\granite-embedding-107m-multilingual-Q8_0.gguf" "$m\embedding\"
Copy-Item "$b\gpustack__bge-reranker-v2-m3-GGUF\bge-reranker-v2-m3-Q4_K_M.gguf" "$m\reranker\"
Get-ChildItem "$m\embedding\*.gguf", "$m\reranker\*.gguf" | ForEach-Object {
  "{0}  {1} octets  {2}" -f $_.Name, $_.Length, (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower() }
```

- [ ] Tailles attendues : 121 020 096 octets (embedding) et 438 376 864 octets (reranker).
  Un fichier d'une autre taille est refusé.
- [ ] **WaveStack arrêté**, reportez chaque sha256 dans le champ `sha256` de `files`, dans
  `[rag.embedding]` et dans `[rag.reranker]` de `wavestack.toml`.
- [ ] Dans chaque `url`, remplacez `resolve/main` par le commit du dépôt Hugging Face : c'est
  le champ `sha` de
  `https://huggingface.co/api/models/bartowski/granite-embedding-107m-multilingual-GGUF`,
  ou de `…/api/models/gpustack/bge-reranker-v2-m3-GGUF` (méthode Hugging Face, hors dépôt).
- Faites-le **avant** de construire l'index. L'index retient le sha256 de son modèle : un
  sha256 déclaré différent rend la brique indisponible.

### 4.3 Index RAG

L'index se construit depuis la carte RAG (« Construire l'index », avec une progression et
« Arrêter ») ou par le script :

```powershell
uv run python scripts/build_rag_index.py
uv run python -m pytest -m model tests/test_rag.py tests/test_rag_rerank.py
```

- [ ] Le script doit afficher 8 documents, 29 extraits, 384 dimensions, le sha256 et la
  durée. Notez aussi la mémoire et tout verrou de fichier.
- [ ] Les deux tests `model` passent : le document des mots de passe arrive en premier.
- **Committer `data/rag_index.sqlite` ?** Git ne l'ignore pas.
  - Pour : une installation neuve n'a rien à construire, et
    `test_shipped_index_matches_the_corpus` le vérifie à chaque `pytest`.
  - Contre : c'est un binaire à reconstruire après tout changement du corpus, de
    `chunk_max_chars` ou du modèle. Relevez sa taille avant de décider.

### 4.4 Instantanés des serveurs MCP publics

```powershell
uv run python scripts/snapshot_mcp.py
uv run pytest -s tests/test_program.py -k fits
```

- [ ] Le script affiche « datagouv : N outils enregistrés dans … », la même ligne pour
  `mslearn`, et écrit `content/mcp_snapshots/`. En cas d'échec, il donne la raison.
- [ ] Le test `fits` passe avec les vrais outils ; sinon, notez le scénario qui déborde.
  Committez `content/mcp_snapshots/`.

## 5. Parcours fonctionnel

Lancez `uv run wavestack` avec Qwen3.5-2B. Choisissez chaque scénario dans le sélecteur de
la barre haute : ses prompts apparaissent au-dessus du champ de saisie, sa consigne dans la
Vue humain.

**Trois mesures par scénario** (tableau de la section 7) :
- **Jauge avant envoi** (barre haute) : sur 3 584 tokens utiles, ou 3 072 avec le
  raisonnement.
- **NFR-1, premier token** : dans le Journal des événements, dépliez « Appel au modèle
  terminé » et lisez `prompt_ms`. Recoupez avec les heures des lignes « Appel au modèle
  commencé » et « Premier token ». Cibles : moins de 10 s en LLM nu, moins de 30 s au plus
  chargé.
- **NFR-2, mémoire** : cible de 2 à 3 Go, plafond de 4 Go. Relevez le maximum dans le
  Gestionnaire des tâches, ou avec cette commande :

```powershell
Get-Process python*, wavestack*, llama-server*, ollama* -ErrorAction SilentlyContinue |
  Select-Object Name, Id, @{n = "Mo"; e = { [math]::Round($_.WorkingSet64 / 1MB) } }
```

- [ ] **Programme** : le sélecteur liste « Module N · titre · durée » pour les six modules,
  puis « Transverses et métier ». Lancer directement Skills (module 5) active les briques
  des modules 1 à 4, sans le raisonnement, et restaure la mémoire de démonstration.

**Module 1 : Du LLM nu au harnais**
- [ ] **LLM nu** : « Quelle heure est-il ? » → heure inventée ou aveu. Premier token en
  moins de 10 s.
- [ ] **Raisonnement** (story 13), sur le prompt du train (réponse juste : 17 h 50) :
  - raisonnement replié dans la Vue humain, bloc « Raisonnement du modèle » dans Contexte LLM,
    réserve de 1 536 tokens dans la jauge ;
  - « Afficher le raisonnement » décoché : la bulle ne garde que le texte ;
  - brique éteinte, « Rejouer le dernier prompt », puis « Comparer » : moins de sortie ;
  - notez si le raisonnement dépasse la réserve (sortie coupée).
- [ ] **Mémoire courte** : le prénom revient ; brique éteinte, le rejeu l'oublie.
- [ ] **Prompt système** : « … comme un pirate. », puis rejeu : la réponse change.
- [ ] **Mémoire globale** (story 14) :
  - premier prompt : appel de `remember` et écriture de `memory.json` (sinon « Afficher les
    actions forcées », puis « Écrire en mémoire ») ;
  - « Vider la conversation », puis second prompt : la préférence revient par le message
    système ;
  - « Modifier la mémoire » (modifier, effacer), clic sur le fichier dans le schéma, puis
    « Réinitialiser » : la démonstration revient ;
  - D11 : jauge avec une mémoire pleine.

**Module 2 : Outils**
- [ ] **Outils natifs** : Orchestration montre la demande, l'exécution et la réinjection.
- [ ] **Outils réseau** : nœud en zone Réseau ; « Données sortantes » = texte exact envoyé.

**Module 3 : RAG**
- [ ] **RAG** (story 15) : la carte ne dit pas « sqlite-vec ne se charge pas ».
  - Brique éteinte, premier prompt : Exemplia est inconnue.
  - Brique rallumée, rejeu, « Comparer » : la réponse donne 14 caractères.
  - « Recherche RAG » : requête, extraits, scores et durée. Survolez l'index dans le schéma.
- [ ] **RAG avec reranking** (story 16), sur l'hôtel à Paris :
  - l'étape « Reranking » affiche « 3 gardés sur 8 », l'ordre avant et après, et deux scores ;
  - au moins un extrait change de rang (sinon, essayez le second prompt et notez-le) ;
  - relevez la durée des 8 passes et le RSS ajouté (au plus 800 Mo) ;
  - case décochée : « Prend effet au prochain tour », et plus d'étape au rejeu.

**Module 4 : MCP**
- [ ] **MCP en documentation complète**, point critique : la jauge avant envoi (3 018 / 3 584
  à la story 10b, alors sans la mémoire globale). Relevez la durée du tour (109 s en 10b). En
  cas de débordement, le noter pour décider : `expects_overflow`, ou mémoire globale éteinte.
- [ ] **Lazy loading** : jauge bien plus légère, RAG rallumé ; deux prompts ; chargement de
  la documentation dans Orchestration. Un débordement est à noter.

**Module 5 : Skills et hooks**
- [ ] **Skills** : la jauge grandit au chargement du skill.
- [ ] **Caveman** : « Déclencher le skill » sur Caveman, puis rejeu et « Comparer » : moins de
  sortie.
- [ ] **Hooks** : H1 bloque `confidentiel/budget_projet.txt` (bande « Points d'accroche »),
  au besoin avec le forçage « Fichier sensible ».

**Module 6 : Sous-agent et compression**
- [ ] **Sous-agent** (story 19) :
  - le modèle délègue-t-il, ou lit-il le guide lui-même ? Sinon, forcez « Déléguer au
    sous-agent » avec « Résumer le guide du harnais » ;
  - dépliez « Délégation au sous-agent » (économie de tokens) ;
  - Contexte LLM bascule entre le contexte principal et `sub1` ; un second robot apparaît ;
  - notez la taille de `sub{n}` (au plus 4 096 − 512) et tout `prefix_not_reused` ;
  - finissez par les trois quiz.
- [ ] **Compression** (story 20) :
  - brique éteinte, le journal entre en entier ; rallumée, rejeu et « Comparer » ;
  - « Compression (Headroom) » : tokens avant et après, erreur gardée ; dans Contexte LLM,
    « compressé » et le total « Sans compression » ;
  - le second prompt (lot 12) montre la perte ;
  - aucun appel « Retrieve more », et le scénario tient-il sans compression ?

**Transverses et métier**
- [ ] **Où vont mes données ?** : seul le flux vers data.gouv.fr franchit la frontière.
- [ ] **SOC** (D6) :
  - premier prompt : un seul incident, `adm.leroy`, avec l'accès initial à 02:14,
    l'élévation à 02:15, l'antivirus arrêté à 02:21 et 2,3 Go exfiltrés à 02:40 ; H2
    journalise ;
  - second prompt : H1 bloque l'inventaire des comptes à privilèges, et l'agent escalade ;
  - clic sur « Journal d'audit » dans le schéma.
- [ ] **IAM** : accès conditionnel avec MFA pour les administrateurs, PIM juste-à-temps, liens
  Microsoft Learn. Comparez la taille des résultats à la fenêtre.
- [ ] **Souveraineté** : les « Données sortantes » de chaque appel montrent deux flux ; le
  modèle reste local.
- [ ] **NFR-2 global** : RSS maximal toutes briques actives (estimé sous 2,2 Go hors cache KV).

**Modèles**
- [ ] **Changement à chaud** (story 17) :
  - sondez le 2B et le 4B, puis relisez `probed_models` (`rss_bytes`, `kv_bytes_per_token`)
    dans `settings.json` ;
  - après un tour avec le 2B : « Changer de modèle… » → 4B → « Charger » ;
  - attendu : pas de refus à tort (sinon, notez les chiffres), chronomètre, envoi désactivé,
    conversation gardée, ligne « Modèle : … », rejeu par le 4B, « Comparer » par modèle ;
  - un fichier incompatible ramène au modèle précédent, avec une explication.
- [ ] **llama-server** (story 18), lancé **avant** WaveStack :

```powershell
llama-server -m "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf" --port 8080 -np 1
```

  Le diagnostic doit afficher « Local », l'adresse, la mémoire et « Choisir ». Un tour avec
  `get_datetime` montre « Local · llama-server » et le robot hors du cadre Harnais.
- [ ] **Ollama**, avec `ollama serve` lancé avant WaveStack :
  - un tour : notez toute alerte « transparence réduite » et ses deux comptes ;
  - un blob `qwen35` refusé renvoie vers llama-server, et le modèle précédent reste actif ;
  - « Arrêter » pendant le chargement d'un gros modèle rend la main en moins d'une seconde ;
  - `ollama ps` est vide après un changement de modèle et après la fermeture de WaveStack,
    sauf pour un modèle chargé par un autre programme.
- [ ] **Groq et Mistral avec le raisonnement** (story 13) : saisissez la clé au diagnostic
  (« Enregistrer la clé », « Tester »), ou faites `setx GROQ_API_KEY …` puis ouvrez un
  nouveau terminal. Scénario Raisonnement :
  - Groq : « Toujours active pour ce modèle », 2 464 tokens utilisables ;
  - Mistral : `reasoning_effort` vaut `high` brique allumée, `none` brique éteinte, dans les
    « Données sortantes » ;
  - D9, facultatif : WaveStack arrêté, mettez
    `{"cloud": {"models": [{"id": "mistral", "reasoning": {"resend": true}}]}}` dans
    `settings.json`, puis jouez un tour avec outil et un second tour. Un 400 veut dire refus.
- [ ] **Relance** : Ctrl+C, puis `uv run wavestack` ; le dernier modèle chargé revient.

## 6. Décisions à trancher pendant le test

Le détail est dans `weekend-report-2026-09-26.md`, section 3.

| # | Défaut appliqué | À observer |
|---|---|---|
| D1 | Compression aussi des résultats d'outils reçus en cours de tour | Compression : gain réel, réponse encore juste |
| D2 | Sans reranker, seule la sous-option est indisponible | RAG simple utilisable sans le fichier du reranker |
| D3 | Serveurs seuls : « Choisissez un modèle servi » | Lancement avec seulement Ollama ou llama-server |
| D4 | Budget de 4 096 Mo, non contrôlé au lancement | RSS relevés ; passage du 2B au 4B |
| D5 | Raisonnement éteint après le module 1, RAG éteint dans `mcp_full`, mémoire restaurée | Jauges de `mcp_full`, `mcp_lazy`, `skills`, `subagent` |
| D6 | SOC : blocage H1, sans validation humaine H5 | La leçon « escalader » passe-t-elle par la consigne ? |

D7 à D18 se confirment en passant, dont D9 (Mistral), D11 (mémoire) et D13 (reranking).

## 7. Consigner les résultats et fusionner

| Scénario ou test | OK / KO | Jauge | 1er token | RSS max | Remarque |
|---|---|---|---|---|---|
| Installation, `uv lock`, AppLocker | | | | | |
| `pytest -q`, E2E | | | | | |
| Bancs story 12 | | | | | |
| Modèles RAG, sha256, index | | | | | |
| Instantanés MCP, `fits` | | | | | |
| M1 LLM nu / Raisonnement / Mémoire courte / Prompt système / Mémoire globale | | | | | |
| M2 Outils natifs / réseau | | | | | |
| M3 RAG / Reranking | | | | | |
| M4 MCP complet / Lazy loading | | | | | |
| M5 Skills / Caveman / Hooks | | | | | |
| M6 Sous-agent / Compression | | | | | |
| Données / SOC / IAM / Souveraineté | | | | | |
| 2B → 4B, llama-server, Ollama | | | | | |
| Groq, Mistral, relance | | | | | |

**Écarts** : collez-moi le tableau et les messages d'erreur dans le chat. Vous pouvez aussi
ajouter une entrée à `_bmad-output/implementation-artifacts/deferred-work.md`, au format
existant :

```yaml
- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/16-reranking.md`
  summary: Une phrase qui décrit l'écart.
  evidence: Test manuel du 2026-MM-JJ sur le PC cible (Qwen3.5-2B Q4_K_M, CPU) : action, observation, mesure.
```

**Fusion, une fois validé** :
- [ ] Pousser les commits des sections 2 et 4 : `uv.lock`, `wavestack.toml` (sha256,
  commits, `measured_rss_mb`), `content/mcp_snapshots/`, l'index s'il est retenu, le verdict
  de la story 12.
- [ ] Reporter D1 à D6, puis retirer les mentions « à valider » d'AD-4 et AD-21 dans le spine.
- [ ] Fusionner la PR #1 sur GitHub (« Merge pull request »), puis mettre `main` à jour :

```powershell
git switch main; git pull; uv sync --extra compression
```
