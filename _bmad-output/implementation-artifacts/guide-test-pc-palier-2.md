# Guide de test sur le PC cible : palier 2, recette suivante (commit de la nuit du 2026-09-28)

Pour récupérer la branche du palier 2 et la tester fonctionnellement sur le PC professionnel
(Windows 11, sans droits administrateur, CPU seul). Les commandes sont en PowerShell et se
lancent depuis la racine du clone. Sources : `README.md`, `weekend-report-2026-09-26.md`
(sections 3 et 4), stories 12 à 21, `plan-corrections-palier-2.md` (test du 2026-09-27, lots A
à I), `retours-recette-palier-2-2026-09-28.md` (recette du 2026-09-28), `spec-lot-*.md`,
`tools/bench/README.md`, `tools/e2e/README.md`.

Cette version prépare la recette qui suit celle du 2026-09-28. Elle vise le commit de la nuit du
2026-09-28 (branche `claude/lucid-cori-1rkbjf`, stories 22 à 34) et reprend les tests du cahier
`cahier-recette-palier-2.html` : les corrections des lots A à G (section 5), puis le parcours
complet (section 6) et les décisions (section 7). Chaque test du cahier a désormais un geste pas
à pas ; les tests restés « non faits » le 2026-09-28 faute de consigne claire (D11 et
« Réinitialiser » du module 1, M3, M6, X1, X3, D1, D2m, Z1, Z2) sont réécrits ici avec le même
geste que dans le cahier. llama-server s'installe sans droits d'administrateur (section 2.1).

**Hors de ce guide** : les nouveautés des stories 22 à 34 (volets, briques, données sortantes,
sélecteur de modèles, fenêtre de contexte, scénarios, mode sombre, écrans « LLM nu » et « Atelier
RAG »…) ne sont pas détaillées ici ni dans le cahier. Les stories 22 à 27 et 31 à 34 ont déjà
leur cahier, `cahier-recette-nuit-2026-09-28.html` (publié :
https://claude.ai/artifact/7Er6qrF3fcLtTsMoY6meLf). Le prompt
`_bmad-output/implementation-artifacts/prompt-test-pc-2026-09-29.md` couvre toute la nuit (il
remplace `prompt-test-pc-intermediaire-2026-09-29.md`) : le Claude Code du PC vérifie ce qu'il
peut, puis génère le cahier de ce qui reste. Ce guide ne corrige que les attentes des tests
existants que ces stories ont changées.

## 0. En bref

- **Durée** : environ 1,5 jour, en deux séances.
  - Séance 1 (4 à 5 h) : sections 1 à 5 (code, installation, tests, bancs, modèles, puis
    vérification des corrections A à G).
  - Séance 2 (5 à 7 h) : section 6 (six modules, soit 5 h 15 de programme, puis les scénarios
    métier et les modèles). Avant le lot A, un tour chargé dépassait 100 s (relecture de tout
    le contexte à ≈ 35 tokens/s) ; la section 5 dit si c'est corrigé.
- **À avoir sous la main** :
  - le proxy ouvert vers `pypi.org`, `files.pythonhosted.org`, `abetlen.github.io`,
    `github.com`, `huggingface.co`, `*.hf.co`, `learn.microsoft.com` et `mcp.data.gouv.fr` ;
    en option, `api.groq.com`, `api.mistral.ai`, `fr.wikipedia.org` et
    `calendrier.api.gouv.fr` ; pour llama-server, facultatif (section 2.1) : `api.github.com`,
    `objects.githubusercontent.com` et `release-assets.githubusercontent.com` ;
  - les GGUF Qwen3.5-2B Q4_K_M amont (unsloth) et Qwen3.5-4B, dans
    `%LOCALAPPDATA%\WaveStack\models` ;
  - environ 4 Go libres : 2,1 Go pour le banc, 285 Mo pour l'extra `compression`, plus
    Chromium pour l'E2E ; les modèles d'embedding et de reranker sont déjà en place depuis le
    2026-09-27 ;
  - en option : des clés Groq et Mistral, Ollama (`qwen3.5:2b`, `llama3.2:3b`), et
    `llama-server.exe` (llama.cpp). Le 2026-09-28, llama-server n'était pas installé (C9 et C10
    KO) : il s'obtient sans droits d'administrateur, section 2.1 ;
  - **Edge, Outlook et Teams fermés pendant les mesures** : ils saturaient la RAM à la story 9,
    et Edge ouvert a faussé la mesure de Skills le 2026-09-27 (compression mémoire de Windows
    ≈ 1 Go). Edge se relance seul en arrière-plan après sa fermeture (`--no-startup-window`,
    ≈ 1 Go, constaté le 2026-09-27 au soir) : quittez-le depuis l'icône de la zone de
    notification et vérifiez avec `Get-Process msedge`.
- **Ordre** : 1 → 2 → 3 → 4 → 5, avec les bancs avant de lancer WaveStack. Ensuite 6, dans
  l'ordre des modules, puis le métier et les modèles, et 7. La séance s'arrête à « Où
  consigner » (section 8). Les résultats du 2026-09-28 sont rappelés dans le cahier, test par
  test (« Déjà mesuré » : « Le 28/09 : … ») ; le filtre « À faire » du cahier suffit pour s'y
  retrouver.
- **Fusion** : elle attendait le lot H. Le lot H est livré (story 27 : scénarios et consignes
  revus) ; reste à vérifier sur PC son effet réel sur le 2B (tests N27 du cahier de la nuit, et
  H1 à H6 en section 7), puis les critères A à G de la section 5. La fusion ne se fait qu'après
  (section 8).
- **Repères de l'interface** (commit de la nuit) : la barre haute porte, de gauche à droite, le
  sélecteur de scénario (« Choisir un scénario », groupes « Module N · titre · durée » puis
  « Transverses et métier »), la jauge, « Fenêtre 4 096 ▾ », « Volets ▾ », l'indicateur du
  modèle, « Changer de modèle… » (suivi de « Charger » une fois un modèle choisi), « Mode
  projection », « LLM nu », « Atelier RAG », le sélecteur de thème et « ⟲ Réinitialiser ». Le
  Panneau des briques est à gauche (interrupteur « Afficher les actions forcées » en haut) ;
  à droite, les volets numérotés 1 Vue humain (« Rejouer le dernier prompt », « Vider la
  conversation »), 2 Contexte LLM (« Comparer »), 3 Orchestration (avec, en bas, « Journal des
  événements (N) ») et 4 Schéma d'architecture.
- **Revenir en arrière** : `git switch main`, puis `uv run wavestack`, resynchronisent sur le
  `uv.lock` de `main`. Le dossier de données contient déjà les données du palier 2
  (`probed_models`, `selected_model`, `memory.json`) : pour revenir au palier 1, restaurez la
  sauvegarde prise avant le test du 2026-09-27, `sauvegarde-palier-1`, WaveStack arrêté.
  Prenez aussi, avant cette séance, une copie de l'état actuel, `sauvegarde-palier-2` : elle
  sert à défaire les manipulations des sections 5 à 7.

```powershell
$d = "$env:LOCALAPPDATA\WaveStack"
# Copie de l'état actuel (palier 2), avant la séance :
New-Item -ItemType Directory -Force "$d\sauvegarde-palier-2" | Out-Null
Copy-Item "$d\settings.json", "$d\api_keys.json", "$d\memory.json" "$d\sauvegarde-palier-2\" -ErrorAction SilentlyContinue
# Retour au palier 1, WaveStack arrêté, après git switch main :
Copy-Item "$d\sauvegarde-palier-1\*" "$d\" -Force
```

## 1. Récupérer le code

```powershell
cd C:\chemin\vers\agentic-harness-training-demo
git status                                   # rien sous tools/e2e/screenshots, sinon :
git restore tools/e2e/screenshots            # captures réécrites par le parcours précédent
git status                                   # l'arbre doit être propre
git fetch origin
git switch claude/lucid-cori-1rkbjf          # branche de la nuit du 2026-09-28
git pull
git log --oneline -12
```

- [ ] HEAD : le dernier commit de la nuit du 2026-09-28 (rapport de la nuit, ou la story 28
  « guide de test et cahier de recette corrigés »), ou plus récent. En dessous, les commits
  des stories 22 à 34, dont `69f0cf3` (Atelier RAG, story 30), `e42ce11` (écran « LLM nu »,
  story 29) et `175eb5a` (mode sombre, story 31). La branche du 2026-09-27
  (`claude/dreamy-cerf-gdjtee`) n'est plus celle à tester.
- Les stories 22 à 34 se vérifient avec le prompt `prompt-test-pc-2026-09-29.md` (section
  « Hors de ce guide » plus haut) ; ce guide et le cahier reprennent les tests du 2026-09-28.
- Zip, sans Git : sur GitHub, choisissez la branche, puis « Code » → « Download ZIP ». Avec
  le navigateur connecté, l'adresse directe est
  `https://github.com/Aliquanto3/agentic-harness-training-demo/archive/refs/heads/claude/lucid-cori-1rkbjf.zip`.

## 2. Installer

Validé le 2026-09-27 : `uv lock` inchangé, `uv sync --extra compression`, aucun blocage
AppLocker ni WDAC. Depuis, la story 30 a ajouté l'extra facultatif `rag-alt` (FAISS et LanceDB,
pour l'écran « Atelier RAG ») : il relève du prompt des stories 22 à 34, pas de ce guide.

```powershell
$env:UV_SYSTEM_CERTS = "1"     # derrière le proxy : certificats du système (README), valable pour ce terminal
uv lock --check
uv sync --extra compression    # headroom-ai 0.38.0 (environ 40 paquets, 285 Mo)
```

- [ ] `uv lock --check` passe.

**Premier lancement**, puis arrêt avant les sections 3 et 4 (les bancs se lancent WaveStack
arrêté) :

```powershell
uv run wavestack          # Ctrl+C pour l'arrêter une fois les points ci-dessous relevés
```

- [ ] Sonde du lot E (E2) : le 2B enregistré est resondé une fois, ce premier lancement prend
  quelques dizaines de secondes de plus (relevez la durée). Ensuite, dans `settings.json`, son
  entrée de `probed_models` porte `probe_version` 2, `rss_bytes`, `kv_bytes_per_token`,
  `probe_window` (4 096) et `rss_eval_tokens`.
- [ ] La carte Compression est disponible et la carte RAG ne dit pas « sqlite-vec ne se
  charge pas » (sinon, blocage AppLocker ou WDAC : notez le fichier bloqué sous `.venv\` et
  demandez une exception au support).

Attention : un `uv sync` sans `--extra compression` retire Headroom, alors que `uv run …` le
garde. Relancez `uv sync --extra compression` après chaque mise à jour.

### 2.1 Installer llama-server (sans droits d'administrateur)

Pour C9, C10 et, en section 6, « llama-server » (cahier : test `P3`). Le 2026-09-28,
`llama-server` n'était pas installé : « n'est pas reconnu comme nom d'applet de commande ».
WaveStack ne l'installe pas. On prend l'archive CPU officielle de llama.cpp,
`llama-bNNNNN-bin-win-cpu-x64.zip`, publiée sur `github.com/ggml-org/llama.cpp`, décompressée
dans le profil (`%LOCALAPPDATA%\llama.cpp\<version>`, un dossier par version), et l'exécutable
se lance par son chemin complet, `$llama` : rien ne s'installe, rien ne demande d'élévation.
Même procédure que le README (« Obtenir llama-server sans droits d'administrateur »).

Dans un nouveau terminal PowerShell (Windows PowerShell 5.1 ou PowerShell 7), ligne par ligne :

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12   # PowerShell 5.1
$px = @{}   # erreur 407 : lancez la ligne « Proxy », puis reprenez ici à Invoke-RestMethod
$rel = Invoke-RestMethod -UseBasicParsing @px https://api.github.com/repos/ggml-org/llama.cpp/releases/latest
$asset = $rel.assets | Where-Object name -match '^llama-b\d+-bin-win-cpu-x64\.zip$'
if (-not $asset) { throw "Aucune archive llama-bNNNNN-bin-win-cpu-x64.zip dans la dernière release : prenez le repli b11239." }
$zip = "$env:TEMP\$($asset.name)"; $dest = "$env:LOCALAPPDATA\llama.cpp\$($rel.tag_name)"
Invoke-WebRequest -UseBasicParsing @px $asset.browser_download_url -OutFile $zip
if ($asset.digest) { if (("sha256:" + (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()) -ne $asset.digest) { throw "Empreinte SHA-256 différente de celle publiée par GitHub : archive refusée." } else { "Empreinte SHA-256 vérifiée." } }
Expand-Archive $zip -DestinationPath $dest -Force; Get-ChildItem $dest -Recurse | Unblock-File
$llama = "$dest\llama-server.exe"; & $llama --version
& $llama -m "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf" --port 8080 -np 1 -c 4096
```

- Ne lancez pas la dernière ligne ici : c'est le lancement, fait en C10 et en section 6. Ne
  lancez jamais llama-server sans `-c` quand le 2B est chargé dans WaveStack (C9 le fait
  exprès, WaveStack sur un petit modèle).
- [ ] `$asset.name` vaut `llama-bNNNNN-bin-win-cpu-x64.zip` ; « Empreinte SHA-256 vérifiée. »
  s'affiche si l'API donne l'empreinte ; l'archive est décompressée dans
  `%LOCALAPPDATA%\llama.cpp\bNNNNN` ; `& $llama --version` affiche la version, puis
  `$LASTEXITCODE` vaut 0, sans demande d'élévation. Relevez la version (bNNNNN).
- Si le téléchargement se traîne sous PowerShell 5.1 : `$ProgressPreference =
  "SilentlyContinue"`, puis relancez `Invoke-WebRequest`.
- Dans un nouveau terminal, sans rien retélécharger, retrouvez l'exécutable :

```powershell
$llama = Get-ChildItem "$env:LOCALAPPDATA\llama.cpp" -Recurse -Filter llama-server.exe | Sort-Object LastWriteTime | Select-Object -Last 1 -ExpandProperty FullName
```

Ligne « Proxy » (erreur 407 seulement) :

```powershell
$px = @{ Proxy = [System.Net.WebRequest]::GetSystemWebProxy().GetProxy("https://api.github.com"); ProxyUseDefaultCredentials = $true }
```

- **Erreur 407** (le proxy demande vos identifiants) : lancez la ligne « Proxy » ci-dessous. Elle
  calcule le proxy du système (`GetSystemWebProxy().GetProxy(…)`) et fait passer `-Proxy` et
  `-ProxyUseDefaultCredentials` à `Invoke-RestMethod` et à `Invoke-WebRequest` (par `@px`, repli
  compris) ; reprenez ensuite le bloc à `Invoke-RestMethod`.
- **Aucune archive trouvée** : le bloc s'arrête (« Aucune archive … : prenez le repli b11239. »).
- **Intégrité** : quand l'API donne l'empreinte de l'archive (champ `digest`, SHA-256), le bloc
  la compare à `Get-FileHash` et refuse une archive différente. Le repli, sans l'API, ne vérifie
  rien : comparez `(Get-FileHash $zip).Hash` à l'empreinte de la page de la release si elle
  s'ouvre.
- **`Unblock-File`** retire la marque « téléchargé depuis Internet » (Mark of the Web) que
  Windows pose sur les fichiers de l'archive. Si la politique du poste l'interdit, ou si
  SmartScreen ou AppLocker bloque l'exécutable, arrêtez-vous : « non fait (poste) », sans
  contourner.
- Sous macOS ou Linux, prenez l'archive de la même release qui correspond au système.

**Si ça bloque encore** (notez dans le cahier, test `P3`, le code d'erreur et le chemin qui a
marché) :
- **API GitHub refusée** (403, ou 407 qui persiste) : si `github.com` reste joignable, prenez la
  version fixe `b11239` (la dernière le 2026-09-28) par son adresse directe :

```powershell
$tag = "b11239"; if (-not $px) { $px = @{} }
$zip = "$env:TEMP\llama-$tag-bin-win-cpu-x64.zip"; $dest = "$env:LOCALAPPDATA\llama.cpp\$tag"
Invoke-WebRequest -UseBasicParsing @px "https://github.com/ggml-org/llama.cpp/releases/download/$tag/llama-$tag-bin-win-cpu-x64.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath $dest -Force; Get-ChildItem $dest -Recurse | Unblock-File
$llama = "$dest\llama-server.exe"; & $llama --version
```

- **GitHub entièrement bloqué** : récupérez la même archive sur un autre réseau ou un autre
  poste, ou auprès du formateur, et copiez-la dans `%TEMP%` (partage interne, OneDrive, clé
  USB). Lancez les deux premières lignes du bloc de repli, avec `$tag` égal à la version de
  l'archive copiée, sautez `Invoke-WebRequest` et reprenez à `Expand-Archive`. Aucune autre
  source : ni winget, ni Chocolatey, ni installeur, ni élévation. Sans archive, C9 et C10 sont
  « non fait (poste) » et le mode serveur se vérifie avec Ollama (section 6, « Ollama »).
- **Exécutable bloqué** (AppLocker, SmartScreen, ou « VCRUNTIME140.dll » ou « MSVCP140.dll »
  introuvable) : relevez le message exact et transmettez-le au support, sans contourner le
  blocage ; C9 et C10 passent à « non fait (poste) ».
- Gardez `llama-server.exe` avec ses DLL (dont les variantes `ggml-cpu-*`) : ne le copiez pas
  seul, et ne le décompressez pas dans `Program Files`.

## 3. Vérifications automatiques rapides

```powershell
uv run pytest -q
```

- **Compte actuel** (commit de la nuit, sous Linux, extras `compression` et `rag-alt`) : de
  l'ordre de **1 294 réussis, 3 sautés, 7 désélectionnés**. Sous Windows, les 3 sauts sont
  ceux expliqués ci-dessous. Avec seulement `--extra compression` (sans `rag-alt`), comptez
  **2 sautés de plus** : les deux variantes FAISS et LanceDB de `tests/test_rag_lab_alt.py`
  (`pytest.importorskip("faiss")`, `pytest.importorskip("lancedb")`), qui demandent l'extra
  `rag-alt` de la story 30. Le critère : aucun échec, et seuls ces sauts.
- Les comptes détaillés ci-dessous datent du 2026-09-27 (avant la nuit) ; ils gardent
  l'explication des sauts.
- [ ] Attendu sous Windows, avec l'extra `compression` : **935 réussis, 3 sautés,
  6 désélectionnés** (938 tests collectés hors `model` ; 934 avant le test du journal de
  llama.cpp ajouté au lot J, mesurés le 2026-09-27 au soir). Les 3 sauts attendus :
  - `test_an_index_replaced_during_the_session_is_read_again[replaced-while-open]` et
    `test_an_index_replaced_with_the_reranker_loaded_closes_it[replaced-while-open]` :
    « Windows refuse de remplacer un fichier qu'une connexion tient ouvert ». Leur variante
    `[connection-closed-first]` doit passer : ce sont les 2 échecs du 2026-09-27 (lot G) ;
  - `test_the_simulated_windows_rules_refuse_replacing_an_open_index` : « simulation sans
    /proc : sous Windows, le système applique ses règles ».
- Les 4 tests Headroom (dont le test hors ligne du lot F) et les 3 tests propres à Windows
  (`ProactorEventLoop`, chemin `C:/Windows/win.ini`) tournent. Sans l'extra, ces 4 tests
  sont sautés (« … (extra) absent ») : 931 réussis, 7 sautés. Référence Linux au
  commit du lot G : 934 réussis, 3 sautés avec l'extra (les 3 tests propres à Windows), 930 et
  7 sans ; un de plus depuis le lot J. Tout autre échec est un écart à remonter.
- `WAVESTACK_TEST_WINDOWS_FILES=1` ne sert qu'à simuler les règles de Windows sous Linux :
  inutile ici.

**Tests `model`**, avec les vrais fichiers (adaptez le nom du GGUF) :

```powershell
$env:WAVESTACK_TEST_GGUF = "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf"
$env:WAVESTACK_TEST_MODELS_DIR = "$env:LOCALAPPDATA\WaveStack\models"
uv run python -m pytest -m model
```

- [ ] Attendu : **6 réussis**. Sans `WAVESTACK_TEST_GGUF`, 4 sont sautés ; sans
  `WAVESTACK_TEST_MODELS_DIR`, 2, chacun avec sa raison :
  - `WAVESTACK_TEST_GGUF` : `test_probe_real_gguf_loads_successfully`,
    `test_real_gguf_passes_checks_4_and_6`, `test_real_gguf_reuses_its_cache_between_two_turns`
    (lot A : au second tour, le moteur n'évalue que les tokens nouveaux, à 1 près) et
    `test_real_gguf_state_restored_after_a_divergent_prompt` (lot A : état restauré sur le
    modèle hybride) ;
  - `WAVESTACK_TEST_MODELS_DIR` (lot G) : `test_real_embedding_model_finds_the_password_document`
    et `test_real_reranker_puts_the_password_document_first`.
- Gardez ces deux variables dans ce terminal pour le test `fits` (section 4.4). Depuis le
  lot J, avec `WAVESTACK_TEST_GGUF` posée, ce test charge le vrai modèle (≈ 20 s de plus,
  ≈ 1,3 Go) : pour un `uv run pytest -q` rapide, lancez-le dans un terminal sans ces variables.

**Parcours E2E Playwright**, facultatif : il rejoue l'interface avec un faux modèle. Chromium
s'installe dans le profil (`%LOCALAPPDATA%\ms-playwright`), sans droits d'administrateur.

```powershell
uv run --with playwright==1.56.0 playwright install chromium
uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py
git restore tools/e2e/screenshots            # le parcours réécrit les captures
```

- [ ] Attendu : **0 échec, sur ce poste connecté** (30 échecs le 2026-09-27, tous dus à
  l'hypothèse « pas d'Internet »). Depuis le lot D, le lanceur coupe lui-même le réseau
  sortant de WaveStack (proxy fermé sur la boucle locale) : `public_holidays`, Wikipédia,
  data.gouv.fr et Microsoft Learn sont tracés, puis échouent « Service injoignable », comme
  hors ligne. Sous Windows, chaque échec prend 1 à 2 s (connexion refusée retentée).
- Référence Linux avec l'extra `compression`, au commit du lot G : 356 vérifications
  réussies, 0 échec (336 sans l'extra : le scénario `compression` se saute). Le nombre peut
  varier d'un poste à l'autre ; le critère est 0 échec. Une ligne `KNOWN [Ax]` n'est pas un
  échec.
- Pour explorer à la main avec le vrai réseau : `uv run python tools/e2e/stack.py --network`.

## 4. Préparer les modèles et les données

### 4.1 Bancs de la story 12 (WaveStack arrêté)

À refaire : le lot F a changé la mesure (RSS ajoutée au pic, modèle chargé) et le comptage de
Headroom (`gpt-4`, table `cl100k_base`).

```powershell
uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom --json | Out-File -Encoding utf8 bench-headroom.json
uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download --json | Out-File -Encoding utf8 bench-embed.json
```

`embed --download` reprend les fichiers déjà présents dans `~\.cache\wavestack-bench`
(environ 2,1 Go au total). Sous Windows, `strace` n'existe pas : le banc ne voit que la garde
Python, c'est normal. Avec `--json`, le banc n'écrit pas le verdict en texte : lisez-le dans
les rapports.

```powershell
$h = Get-Content bench-headroom.json -Raw | ConvertFrom-Json
$h.verdict.retained; $h.rss_added_method; $h.configured.rss_added_mb
$h.verdict.criteria | Format-Table id, ok, detail -Wrap
$e = Get-Content bench-embed.json -Raw | ConvertFrom-Json
$e.rss_added_method; $e.verdict | Format-List
$e.results | Format-Table id, role, status, recall_at_1, mrr, rss_added_mb, pooling_gguf
uv run python tools/bench/story12_bench.py embed --only e5small_q8; $LASTEXITCODE
```

- [ ] Headroom : `verdict.retained` vaut `True` (« ÉCARTÉ » le 2026-09-27) ; critère
  `network` à `True`, sans `openaipublic.blob.core.windows.net` ; `no_torch` à `True` ;
  RSS ajoutée au pic (`configured.rss_added_mb`) ≤ 300 Mo (107 Mo sous Linux ; 84 Mo sur ce
  poste le 2026-09-27 au soir, après le lot F). Sans `--json`, la dernière ligne dit « == Verdict Headroom : RETENU ».
- [ ] Les deux rapports portent `rss_added_method` = `pic`.
- [ ] `granite107m_q8` : `recall_at_1` ≥ 0,75, `rss_added_mb` ≈ 428 (≤ 600), `pooling_gguf`
  (2 = CLS). bge-m3 (≈ 731 Mo) et Qwen3-Embedding (≈ 900 Mo) dépassent désormais 600 Mo : leur
  verdict change, granite reste retenu (`verdict.embedding.id`).
- [ ] `bgererank_m3_q4km` : MRR égal ou meilleur, `rss_added_mb` ≈ 736 (≤ 800, de peu).
- [ ] `e5small_q8` n'est plus un candidat : `embed --only e5small_q8` affiche « Candidat
  inconnu : e5small_q8 (retiré des candidats : ne se charge pas avec llama-cpp-python
  0.3.35 …) » et sort avec le code 2.
- Où reporter : les deux JSON et le verdict dans la section « Verdict » de la story 12.
  `measured_rss_mb` (430 et 740 aujourd'hui) et `[compression] cost_mb` (110 depuis le
  lot J) ne changent que si la mesure s'en écarte nettement, c'est-à-dire de plus de 20 % ou
  de plus de 50 Mo : la nouvelle valeur est alors la mesure plus 30 %, arrondie à la dizaine
  (section 5.6).

### 4.2 Modèles d'embedding et de reranker

Fait le 2026-09-27 : sha256 identiques à l'oid LFS de Hugging Face, URL épinglées sur le
commit, dans `wavestack.toml`. À parcourir seulement :
- [ ] `%LOCALAPPDATA%\WaveStack\models\embedding\granite-embedding-107m-multilingual-Q8_0.gguf`
  (121 020 096 octets) et `…\reranker\bge-reranker-v2-m3-Q4_K_M.gguf` (438 376 864 octets)
  sont présents.

### 4.3 Index RAG

L'index est livré (`data/rag_index.sqlite`, 8 documents, 29 extraits, 384 dimensions) ;
`test_shipped_index_matches_the_corpus` le vérifie à chaque `pytest`. Les tests `model` du RAG
tournent en section 3. Le comportement du script pendant une session est vérifié en
section 5.7.

### 4.4 Instantanés des serveurs MCP publics et test `fits`

Les instantanés sont committés (`content/mcp_snapshots/` : datagouv 10 outils, mslearn 3).
Depuis le lot J, quand `WAVESTACK_TEST_GGUF` est posée, le test `fits` démarre ce GGUF en mode
local et lit la jauge exacte (gabarit compris : `mcp_full` 3 204 / 3 584) ; sinon il compte à 2
caractères par token, avec un facteur de sécurité de 1,1. Il réserve la place d'un premier
résultat borné.

```powershell
uv run pytest -s tests/test_program.py -k fits    # dans le terminal de la section 3
```

- [ ] Le test passe avec le tokenizer du 2B ; sinon, notez le scénario et son verdict
  (`déborde : … > …`).

## 5. Vérifier les corrections du palier 2 (lots A à G)

Avant le parcours complet. Pour chaque lot : le geste, l'attendu et le critère d'acceptation
du plan ; « Hypothèse » signale une décision prise par défaut ou un point non vérifiable sans
ce poste. Conditions : Edge, Outlook et Teams fermés, Qwen3.5-2B sur le moteur intégré
(défaut). Bancs finis, lancez WaveStack pour toute la section :

```powershell
uv run wavestack
```

Où lire les mesures :
- **Premier token** : Journal des événements, « Appel au modèle terminé » dépliée, champ
  `prompt_ms`.
- **Tokens évalués** (lot A) : la ligne de chaque appel dans Orchestration se termine par
  « N lus · N écrits · durée · N tokens évalués » (`evaluated_tokens`) : ce que le moteur a
  réellement relu, cache exclu.
- **Relecture** : une étape « Préfixe non réutilisé » en dit la cause et le nombre de tokens
  relus. Au premier tour après un changement de scénario ou un vidage, elle est normale
  (conversation remplacée).

### 5.1 Lot A : cache du moteur entre les tours (NFR-1)

- [ ] **Deux tours de `native_tools`** : scénario « Outils natifs », premier prompt (l'heure),
  puis second (la multiplication).
  - Attendu : au premier appel du second tour, quelques dizaines de tokens évalués (pas tout
    le contexte) et aucune étape « Préfixe non réutilisé ».
  - **Critère : `prompt_ms` de cet appel sous 3 s** (23 s le 2026-09-27).
- [ ] **Mémoire globale figée par conversation** (décision N1) : scénario « Mémoire globale »,
  premier prompt (`remember`), puis un second tour.
  - Attendu : pas de « Préfixe non réutilisé » au second tour. L'entrée est dans le fichier et
    le tiroir (« Modifier la mémoire ») aussitôt, mais n'entre dans le message système (Contexte
    LLM) qu'après « Vider la conversation ». Une suppression ou une modification s'applique
    aussitôt.
- [ ] **Raisonnement gardé dans l'historique** : scénario « Mémoire courte », allumez la brique
  Raisonnement avant le premier prompt, puis jouez les deux prompts.
  - Attendu : pas de « Préfixe non réutilisé » au second tour ; la réflexion du premier tour
    est comptée dans l'historique de la jauge.
  - Vérifié le 2026-09-27 au soir (script) : pas de relecture au second tour, 22 tokens
    évalués ; les blancs autour de `</think>` prolongent bien le cache.
- [ ] **Sous-agent** (décision N2) : scénario « Sous-agent », délégation puis trois quiz,
  deux fois : d'abord tel que livré (RAG éteint : depuis la story 27, le scénario n'allume plus
  le RAG), puis relancé depuis le sélecteur de scénario avec la brique RAG allumée à la main,
  par son interrupteur dans le Panneau des briques, avant le premier prompt.
  - Attendu : la ligne « Délégation au sous-agent » affiche « état sauvegardé : N Mo, restauré
    en N s » ; RAG éteint, au premier appel principal après le retour, pas de « Préfixe non
    réutilisé ».
  - **Critère du plan : premier token de chaque quiz sous 15 s** (68 à 99 s le 2026-09-27).
    Relevez `prompt_ms` dans les deux passages. RAG allumé, chaque tour relit tout le contexte
    par conception (« Préfixe non réutilisé », cause historique : extraits RAG retirés, voir
    l'hypothèse ci-dessous), ce que le lot A ne corrige pas : l'acceptation du lot A se juge
    RAG éteint, et le RAG dans ce scénario relève de D5, au lot H. Mesuré le 2026-09-27 au
    soir : 3,4 à 4,1 s RAG éteint, 87 à 114 s RAG allumé (et redélégation de chaque quiz).
  - Relevez la taille de la copie : elle n'entre pas dans le budget mémoire (écart différé du
    lot A).
- Hypothèse (lot A) : les extraits RAG restent hors de l'historique (story 15). Dans tout
  scénario avec RAG, chaque tour affiche donc « Préfixe non réutilisé » (cause : historique,
  extraits RAG retirés) et relit tout le contexte sur Qwen3.5. C'est attendu, à revoir au
  lot H (D5).
- Si les critères ne sont pas tenus : décision N6 (section 7), en rejouant les mêmes gestes
  avec llama-server (section 6, « Modèles »).

### 5.2 Lot B : résultats d'outils bornés et cause des débordements

- [ ] **Scénarios qui débordaient** : « Lazy loading » (`mcp_lazy`, les deux prompts), « Où
  vont mes données ? » (`data_flows` : depuis la story 27, la brique MCP est allumée au
  lancement, en lazy loading, avec le serveur local et data.gouv.fr ; rien à cocher), « Métier
  IAM » (`iam`) et « Métier Souveraineté » (`sovereignty`, les deux prompts).
  - Attendu : un résultat long de data.gouv.fr ou de Microsoft Learn est coupé ; Orchestration
    affiche « Résultat tronqué par le harnais : N tokens sur M (borne [tools]
    result_max_tokens) », N ≤ 1 200 ; le modèle lit la mention de coupe à la fin du résultat.
  - **Critère : les quatre scénarios aboutissent sans débordement avec le 2B** (le
    2026-09-27 : `mcp_lazy` 4 680 / 3 584, `data_flows` 5 605, `iam` 6 864).
  - Relevez la jauge avant le second prompt de `mcp_lazy` (≈ 3 380 / 3 584 estimés, non
    couvert par le test `fits`).
- [ ] **Cause juste** : si un scénario déborde encore (par exemple `soc`, 3 586 / 3 584 le
  2026-09-27, journal lu par `read_file`, non borné par choix), le message dit « Cause : les
  résultats d'outils (fichiers lus, recherches) occupent la plus grande part du contexte… »,
  jamais « les descriptions d'outils ».
- [ ] Le test `fits` passe avec le tokenizer du 2B (section 4.4).
- Hypothèse : `data_flows` démarre en lazy loading (décision par défaut du lot B) ; sa
  consigne le dit.

### 5.3 Lot C : budget de raisonnement

- [ ] **Carte Raisonnement** (modèle local) : « Budget de réflexion : 768 tokens ; au-delà,
  le harnais ferme la réflexion et garde 768 tokens pour la réponse. » (768 depuis le lot J :
  1 024 donnait 127 à 134 s sur le prompt du train, 768 donne 111 s.)
- [ ] **Scénario Raisonnement**, prompt du train (réponse juste : 17 h 50).
  - Attendu : une réponse dans la bulle. Si la réflexion atteint le budget, Orchestration
    montre l'étape « Raisonnement coupé » (« Raisonnement coupé par le harnais à N tokens… »),
    puis la réponse ; un seul « Appel au modèle terminé ».
  - **Critère : une réponse, même courte, en moins de 120 s** (137 s et bulle vide le
    2026-09-27).
  - Un second message dans ce scénario (« Et avec 10 minutes de retard ? ») affiche « Préfixe
    non réutilisé », cause historique : la mémoire courte y est éteinte, l'échange précédent
    n'est pas renvoyé. C'est attendu. Le cache avec le raisonnement se vérifie dans « Mémoire
    courte », brique Raisonnement allumée (section 5.1) : vérifié le 2026-09-27 au soir, 22
    tokens évalués au second tour.
  - Mesure : ≈ 9,5 tokens/s de réflexion (et non 11) ; le 2B va au budget même sur « Bonjour ».
    Au-delà de 120 s, WaveStack arrêté, baissez le budget dans `settings.json`
    (`{"reasoning": {"budget_tokens": 640}}`, borné de 128 à 1 408), rejouez et notez la valeur
    qui tient.

### 5.4 Lot D : User-Agent et parcours E2E

- [ ] **Wikipédia** (C3) : scénario « Outils réseau », cliquez le second prompt suggéré
  (« Résume l'article Wikipédia sur le Mont-Saint-Michel. »), puis « Envoyer ». À la fin du
  tour, dans Orchestration, dépliez l'étape « Exécute l'outil hors du poste », puis son bloc
  « 🌐 RÉSEAU · Données sortantes » (ou cliquez le nœud de l'outil dans la zone « 🌐 RÉSEAU ·
  hors du poste » du schéma : il ouvre la même étape).
  - Attendu : `wikipedia_summary` ou `fetch_page` renvoie le contenu de l'article, plus de 403
    « Please respect our robot policy ». Depuis la story 23, le bloc montre les sections
    « Requête », « En-têtes » et « Corps » : l'en-tête `User-Agent: WaveStack/0.1
    (demonstrateur pedagogique; https://github.com/Aliquanto3/agentic-harness-training-demo)`
    se lit dans « En-têtes » (le 2026-09-28, aucun en-tête n'était affiché : KO).
- [ ] **E2E sur ce poste connecté** : 0 échec (section 3).

### 5.5 Lot E : modèles, mémoire, refus, arrêt

- [ ] **llama-server sans `-c`** (E1). Arrêtez d'abord WaveStack (Ctrl+C). Attention :
  llama-server sans `-c` réserve ≈ 5 Go ; à côté de WaveStack qui tient le 2B, le total peut
  dépasser la RAM du poste. Pour cette mesure, choisissez dans WaveStack un petit modèle ou un
  modèle cloud avant de l'arrêter (le dernier chargé revient au lancement), puis lancez
  llama-server, puis WaveStack :

```powershell
# $llama : section 2.1 (dans un nouveau terminal, la commande « retrouvez l'exécutable »)
& $llama -m "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf" --port 8080 -np 1
```

  - Attendu au diagnostic : une mémoire d'environ 5 Go, proche des 5 137 Mo mesurés alors (et
    non plus la seule taille du fichier), et l'avertissement « llama-server a été lancé avec un
    contexte de 262 144 tokens, alors que WaveStack n'en utilise que 4 096 : il réserve la
    mémoire de tout ce contexte. Arrêtez-le et relancez-le avec `-c 4096`. »
  - Si la ligne dit « sans son cache de contexte (fichier du modèle illisible depuis
    WaveStack) », le lecteur GGUF n'a pas lu le vrai fichier Qwen3.5 : écart à remonter.
  - Arrêtez WaveStack, puis llama-server (Ctrl+C dans sa fenêtre), avant de le relancer avec
    `-c 4096` (section 6, « Modèles ») : plus d'avertissement.
- [ ] **Sonde et 4B** (E2, E3, décision N5). La sonde du 2B se relève au premier lancement
  (section 2). Avec le 2B actif, **éteignez d'abord la brique RAG** : ses modèles
  d'embedding et de reranker comptent dans la mémoire de WaveStack. Choisissez ensuite le 4B.
  WaveStack contrôle le budget avec l'ancienne estimation avant de libérer le 2B et de sonder :
  le refus peut donc venir tout de suite, sans nouvelle sonde ; sinon le 4B est resondé, puis
  refusé.
  - Attendu : « Changement refusé : … demande environ … ; WaveStack occupe … sans le modèle
    actif, pour un budget de … » avec la vraie mémoire de WaveStack (en Mo sous 1 Go, jamais
    « 0 Mo » ni « 0,0 Go » : N entre 80 et 400 Mo) ; le 2B reste ou redevient actif. Depuis la
    story 24, le budget est dynamique : il vaut le budget B relevé au diagnostic au lancement
    (ligne « Budget mémoire de WaveStack : B Mo (…) », cahier P2), au plus 4 096 Mo, suivi de son
    calcul, par exemple « budget de 4,0 Go (= plafond [memory] budget_mb) », ou moins si la RAM
    disponible au lancement est faible (fermez Edge, Outlook et Teams).
  - Critère : le 4B est refusé par le budget B (au plus 4 096 Mo, N5) : 4,27 Go
    mesurés après 3 000 tokens le 2026-09-27, et la sonde compte désormais les poids, le cache
    de toute la fenêtre et les tampons de calcul (3,4 Go estimés avant le lot E). Relevez
    l'estimation affichée, et si le 4B a été resondé, la durée de la sonde.
  - Mesuré le 2026-09-27 au soir : sonde du 4B ≈ 53 s (libération du 2B comprise), RSS
    4 262 Mo, refus « demande environ 4,4 Go ; WaveStack occupe 118 Mo sans le modèle actif,
    pour un budget de 4,0 Go ». Une sonde prend 30 à 60 s selon le modèle.
- [ ] **« Arrêter » pendant un chargement** (E4, C4), sur le chargement d'un GGUF, assez long
  pour cliquer : la sonde d'un fichier jamais sondé, ou le 4B avec un budget relevé (section 6,
  « Changement à chaud »). « Changer de modèle… », le fichier, « Charger » ; pendant le
  chronomètre de chargement, dans les 5 s, cliquez « Arrêter » (à droite du champ de message,
  dans la Vue humain). Si le 4B est refusé tout de suite (sonde déjà faite, refus immédiat),
  prenez une copie du 2B jamais sondée, créée **WaveStack lancé** (le diagnostic de lancement
  sonde tout GGUF jamais sondé : ne relancez pas) et choisie à chaud :
  1. WaveStack lancé, 2B actif : premier bloc ci-dessous (copie du 2B).
  2. Dans un second onglet, http://127.0.0.1:8420/diagnostic : collez le chemin de la copie
     sous « Ou indiquez le chemin d'un fichier GGUF : », cliquez « Choisir ce fichier »
     (changement à chaud), revenez aussitôt à l'onglet de l'atelier et cliquez « Arrêter »
     dans les 5 s.
  3. WaveStack arrêté, supprimez la copie (second bloc). Si sa sonde a abouti, son entrée reste
     dans `probed_models` de `settings.json` : sans effet, elle peut rester.

  Un modèle Ollama ne charge côté WaveStack que son tokenizer, trop vite pour cliquer :
  facultatif.

```powershell
# Copier le 2B (WaveStack lancé)
$m = "$env:LOCALAPPDATA\WaveStack\models"
Copy-Item "$m\Qwen3.5-2B-Q4_K_M.gguf" "$m\Qwen3.5-2B-copie-C4.gguf"; "$m\Qwen3.5-2B-copie-C4.gguf"
# Supprimer la copie (WaveStack arrêté)
Remove-Item "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-copie-C4.gguf"
```

  - Attendu : « Arrêt demandé · Chargement du modèle … » dans la barre haute (son infobulle :
    « Un chargement du moteur en cours se termine avant l'arrêt ; une sonde est interrompue
    tout de suite. »), puis l'issue « Chargement arrêté : {modèle précédent} est de nouveau
    actif. » Depuis la story 24, une sonde s'arrête aussitôt ; un chargement dans WaveStack, à
    la fin de son étape (libération ou chargement). Le 2026-09-28 : arrêt effectif après
    ≈ 25 s, à la fin de la sonde (KO).
- [ ] **Briques indisponibles** (E5, C5) : `llama3.2:3b` via Ollama (« Changer de modèle… »,
  « Local · Ollama · llama3.2:3b … », « Charger »), puis le scénario « Outils natifs ».
  - Attendu : `llama3.2:3b` est accepté si le budget B dépasse ≈ 2,6 Go (≈ 2,3 Go au
    diagnostic, plus la marge, depuis la story 24 ; refusé à tort le 2026-09-28 : « demande
    environ 4,0 Go ») ; sinon, refus chiffré qui cite B. Sous la
    consigne, « Brique du scénario indisponible avec ce modèle : Outils : Le modèle chargé
    n'offre pas l'appel d'outils (aucun format d'appel connu pour cette famille de modèle) :
    choisissez un autre modèle. »
- [ ] **Fichier incompatible** (E6) : choisissez le blob Ollama refusé le 2026-09-27 comme un
  fichier.
  - Attendu : « llama-cpp-python 0.3.35 ne sait pas charger ce fichier (architecture non prise
    en charge, fichier incomplet ou abîmé). Choisissez un autre modèle, ou servez-le avec Ollama
    ou llama-server. » Le message brut de llama.cpp n'est plus qu'un détail technique ; le
    modèle précédent reste actif. Depuis la story 24, les accents sont justes (« abîmé »,
    « modèle ») : le 2026-09-28, la raison s'affichait « abÃ®mÃ© », « modÃ¨le ».
- [ ] Refus chiffré d'un modèle Ollama trop gros (`olmo-3:7b` le 2026-09-27), si vous l'avez :
  WaveStack occupe ≈ 200 Mo sans le modèle actif (et non « 0,0 Go »).

### 5.6 Lot F : Headroom hors ligne et banc

- [ ] Banc `headroom` : « RETENU », aucune tentative réseau (section 4.1).
- [ ] `test_headroom_makes_no_network_attempt_at_import_nor_compression` a tourné et réussi
  dans `uv run pytest -q` (section 3).
- [ ] Banc `embed` mesuré au pic : granite ≈ +428 Mo, reranker ≈ +736 Mo (section 4.1).
- [ ] Scénario « Compression du contexte » : l'étape « Compression (Headroom) » garde l'erreur
  du journal, comme le 2026-09-27 (le changement de comptage ne doit rien casser).
- `[compression] cost_mb` vaut 110 depuis le lot J (84 Mo mesurés au pic sous Windows le
  2026-09-27 au soir, plus 30 %). Si une nouvelle mesure s'en écarte de plus de 20 % ou de plus
  de 50 Mo, la nouvelle valeur est la mesure plus 30 %, arrondie à la dizaine (section 4.1).

### 5.7 Lot G : tests sous Windows et tests `model`

- [ ] `uv run pytest -q` : ≈ 1 294 réussis et 3 sautés (5 sans l'extra `rag-alt`), les deux
  tests G1 compris (section 3).
- [ ] Tests `model` du RAG avec `WAVESTACK_TEST_MODELS_DIR` : réussis (section 3).
- [ ] **Script pendant une session** : WaveStack lancé, un tour du scénario RAG (l'index est
  ouvert), puis, dans un second terminal :

```powershell
uv run python scripts/build_rag_index.py
$LASTEXITCODE
```

  - Attendu : « L'index est ouvert par un autre programme (WaveStack, un antivirus ou un outil
    de synchronisation) : il ne peut pas être remplacé. Construisez-le depuis la carte RAG, ou
    arrêtez WaveStack, puis relancez ce script. », code de sortie 1, index intact.
  - Si le script réussit (WaveStack ne tenait pas l'index), WaveStack arrêté :
    `git restore data/rag_index.sqlite`.

## 6. Parcours fonctionnel

Lancez `uv run wavestack` avec Qwen3.5-2B. Choisissez chaque scénario dans le sélecteur de
la barre haute : ses prompts apparaissent au-dessus du champ de saisie, sa consigne dans la
Vue humain. Les points validés le 2026-09-27 (plan, « Ce qui marche déjà ») se parcourent :
relevez surtout les trois mesures.

**Trois mesures par scénario** (tableau de la section 8), Edge, Outlook et Teams fermés :
- **Jauge avant envoi** (barre haute) : sur 3 584 tokens utilisables, ou **2 560 avec le
  raisonnement** (fenêtre de 4 096 moins la réserve de sortie : 512, ou 1 536 avec le
  raisonnement).
- **NFR-1, premier token** : dans le Journal des événements, dépliez « Appel au modèle
  terminé » et lisez `prompt_ms`. Recoupez avec les heures des lignes « Appel au modèle
  commencé » et « Premier token ». Cibles : moins de 10 s en LLM nu, moins de 30 s au plus
  chargé. Notez aussi les « Préfixe non réutilisé » et leur cause.
- **NFR-2, mémoire** : cible de 2 à 3 Go, plafond de 4 Go. Relevez le pic avec cette commande
  (colonne `Pic Mo`), ou dans le Gestionnaire des tâches :

```powershell
Get-Process python*, wavestack*, llama-server*, ollama* -ErrorAction SilentlyContinue |
  Select-Object Name, Id, @{n = "Mo"; e = { [math]::Round($_.WorkingSet64 / 1MB) } },
    @{n = "Pic Mo"; e = { [math]::Round($_.PeakWorkingSet64 / 1MB) } }
```

- [ ] **Programme** : le sélecteur liste « Module N · titre · durée » pour les six modules,
  puis « Transverses et métier ». Lancer directement Skills (module 5) active les briques
  des modules 1 à 4, sans le raisonnement, et restaure la mémoire de démonstration.

Chemin d'un scénario : sélecteur de scénario (barre haute) → groupe « Module N · titre ·
durée » (ou « Transverses et métier ») → le scénario. Un prompt suggéré se clique (il remplit le
champ), puis « Envoyer ». Les actions forcées apparaissent quand l'interrupteur « Afficher les
actions forcées », en haut du Panneau des briques, est activé ; désactivez-le après usage.

**Module 1 : Du LLM nu au harnais** (cahier : M1)
- [ ] **LLM nu** : « Module 1 · Du LLM nu au harnais · 60 min » → « LLM nu », prompt suggéré
  « Quelle heure est-il ? », « Envoyer » → heure inventée ou aveu. En bas d'Orchestration,
  ouvrez « Journal des événements (N) », dépliez « Appel au modèle terminé » : premier token
  (`prompt_ms`) en moins de 10 s.
- [ ] **Raisonnement** (story 13, lot C), scénario « Raisonnement », prompt du train (réponse
  juste : 17 h 50) :
  - raisonnement replié dans la Vue humain ; dans Contexte LLM, bloc « Réflexion » (« Afficher
    le raisonnement de cet appel ») ; au survol de la jauge, « Fenêtre de 4 096 tokens, dont
    1 536 réservés à la réponse : 2 560 utilisables. » ;
  - « Afficher le raisonnement » (en-tête de la Vue humain) décoché : la bulle ne garde que le
    texte ;
  - brique éteinte (interrupteur de sa carte), « Rejouer le dernier prompt », puis « Comparer »
    (en-tête de Contexte LLM) : moins de sortie ;
  - une réponse en moins de 120 s, coupe éventuelle visible (section 5.3).
- [ ] **Mémoire courte** : les deux prompts suggérés ; le prénom revient ; brique « Mémoire
  courte » éteinte, « Rejouer le dernier prompt » l'oublie.
- [ ] **Prompt système** : prompt suggéré, puis carte « Prompt système » → « Modifier le
  prompt », ajoutez « Réponds toujours en une phrase, comme un pirate. », « Enregistrer »
  (« Prompt système enregistré. » s'affiche, story 22), « Fermer », puis « Rejouer le dernier
  prompt » : la réponse change.
- [ ] **Mémoire globale** (story 14, lot A ; le détail N1 est en section 5.1, cahier C1) :
  - premier prompt : appel de `remember` et écriture de `memory.json` (sinon « Afficher les
    actions forcées », puis « Écrire en mémoire » sur la carte) ;
  - « Vider la conversation », puis second prompt : la préférence revient par le message
    système (pas avant : décision N1) ;
  - carte « Mémoire globale » → « Modifier la mémoire » (modifier, supprimer) ; fermez par
    « × » ; le nœud « Mémoire globale » du Schéma d'architecture ouvre le même tiroir.
- [ ] **« Réinitialiser »** : cliquez « ⟲ Réinitialiser », tout à droite de la barre haute. On
  revient au LLM nu, sans scénario (le sélecteur affiche « Choisir un scénario »), et la mémoire
  de démonstration est restaurée. Pour le vérifier : carte « Mémoire globale » (éteinte) →
  « Modifier la mémoire » : les trois entrées de démonstration (« L'utilisateur s'appelle
  Camille. »…, marquées « démonstration ») sont revenues ; envoyez « Bonjour » : Orchestration
  titre ce tour « Tour 1 » (story 22 ; l'identifiant `t{n}` du journal, lui, continue).
- [ ] **D11, mémoire globale pleine** (20 entrées de 300 caractères) :
  1. WaveStack arrêté (Ctrl+C), lancez le premier bloc ci-dessous, **une seule fois** : il
     sauvegarde `memory.json` en `memory.json.avant-d11` (ou note qu'il n'existait pas), refuse
     de continuer si une sauvegarde D11 existe déjà (ne le relancez pas : restaurez d'abord),
     écrit 20 entrées au format de `memory.json` (liste de `{id, text, created_at, source}`, un
     texte sur une ligne) et répond « 20 entrees ».
  2. Relancez `uv run wavestack`. Ne lancez ni le scénario « Mémoire globale » ni
     « ⟲ Réinitialiser » : ils restaurent la démonstration. Allumez la brique « Mémoire
     globale » à la main, par son interrupteur dans le Panneau des briques, puis la brique
     « Raisonnement » (le pire cas : 2 560 utilisables).
  3. Lisez la ligne d'état de la carte (« 20 entrées · N tokens »), le total de la jauge de la
     barre haute (« … / 2 560 tokens · … % ») et, au survol, son segment « Mémoire globale ».
     « Modifier la mémoire » : 20 entrées. Fermez par « × ».
  4. WaveStack arrêté, restaurez la sauvegarde (second bloc : il ne touche à rien sans
     sauvegarde D11), puis relancez.
  - Attendu : la mémoire compte ≈ 1 550 tokens (estimation du dépôt, à relever) ; la jauge
    reste sous la fenêtre utilisable, sans « contexte dépassé ».

```powershell
# Mémoire pleine (D11), WaveStack arrêté : une seule fois
$d = "$env:LOCALAPPDATA\WaveStack"
if ((Test-Path "$d\memory.json.avant-d11") -or (Test-Path "$d\memory.json.d11-sans-fichier")) { throw "Sauvegarde D11 déjà présente : restaurez d'abord (bloc « Restaurer la mémoire »), ne relancez pas ce bloc." }
if (Test-Path "$d\memory.json") { Copy-Item "$d\memory.json" "$d\memory.json.avant-d11" } else { New-Item "$d\memory.json.d11-sans-fichier" | Out-Null }
$base = "preference de test pour la jauge, memoire globale pleine : reponses courtes, sources citees, vocabulaire simple, exemples tires de la cybersecurite, pas de jargon inutile, et un resume final en trois points. "
$e = foreach ($i in 1..20) {
  $t = ("D11 entree {0:D2} : " -f $i) + $base + $base
  $t = $t.Substring(0, 300)
  if ($t.EndsWith(" ")) { $t = $t.Substring(0, 299) + "." }
  [ordered]@{ id = "d11-$i"; text = $t; created_at = "2026-09-29T09:00:00+02:00"; source = "user" }
}
[IO.File]::WriteAllText("$d\memory.json", (ConvertTo-Json @($e) -Depth 3), (New-Object Text.UTF8Encoding $false))
"$((Get-Content "$d\memory.json" -Raw | ConvertFrom-Json).Count) entrees"

# Restaurer la mémoire (D11), WaveStack arrêté
$d = "$env:LOCALAPPDATA\WaveStack"
if (Test-Path "$d\memory.json.avant-d11") { Move-Item "$d\memory.json.avant-d11" "$d\memory.json" -Force; "memory.json restauré" }
elseif (Test-Path "$d\memory.json.d11-sans-fichier") { Remove-Item "$d\memory.json", "$d\memory.json.d11-sans-fichier"; "memory.json de test retiré (il n'existait pas avant D11)" }
else { "Aucune sauvegarde D11 : rien n'est touché." }
```

Le fichier est écrit en UTF-8 sans BOM (`Set-Content -Encoding utf8` de PowerShell 5.1 en
ajoute un, que WaveStack refuse). Sans `memory.json`, WaveStack repart de la démonstration.

**Module 2 : Outils** (cahier : M2)
- [ ] **Outils natifs** : « Module 2 · Outils · 45 min » → « Outils natifs », prompt de
  l'heure : Orchestration montre « Demande un outil », « Exécute l'outil » et « Réinjecte le
  résultat ».
- [ ] **Outils réseau** : second prompt (Mont-Saint-Michel) ; nœud « Résumé Wikipédia » en zone
  « 🌐 RÉSEAU · hors du poste » ; cliquez-le : Orchestration ouvre « Exécute l'outil hors du
  poste », dont le bloc « 🌐 RÉSEAU · Données sortantes » est le texte exact envoyé
  (requête, en-têtes, corps) ; Wikipédia répond (lot D, section 5.4).

**Module 3 : RAG** (cahier : M3). Où est quoi : l'interrupteur « Reranking » est sur la carte
RAG (Panneau des briques) ; les étapes « Recherche RAG » et « Reranking » sont dans
Orchestration ; l'index est le nœud « Index RAG (rag_index.sqlite) » du Schéma d'architecture.
- [ ] **RAG** (story 15) : « Module 3 · RAG · 45 min » → « RAG » ; la carte ne dit pas
  « sqlite-vec ne se charge pas ».
  - Brique éteinte (interrupteur de la carte RAG), premier prompt : Exemplia est inconnue.
  - Brique rallumée, « Rejouer le dernier prompt », « Comparer » : la réponse donne 14
    caractères.
  - Étape « Recherche RAG » dépliée : requête, extraits, scores et durée. Survolez le nœud
    « Index RAG (rag_index.sqlite) » du schéma.
- [ ] **RAG avec reranking** (story 16), scénario « RAG avec reranking » (« Reranking » coché
  sur la carte RAG), premier prompt (hôtel à Paris) :
  - l'étape « Reranking » affiche « 3 gardés sur 8 », l'ordre avant et après, et deux scores ;
  - au moins un extrait change de rang (constaté le 2026-09-27) ;
  - relevez la durée des 8 passes et le RSS ajouté (commande de mesure avant et après ce tour,
    au plus 800 Mo) ;
  - « Reranking » décoché : la carte RAG dit « Prend effet au prochain tour », et plus d'étape
    « Reranking » au rejeu.
  - Brique RAG éteinte, l'interrupteur « Reranking » est grisé, avec l'infobulle « Activez la
    brique RAG pour régler cette option. » (violet le 2026-09-28, story 22).

**Module 4 : MCP** (cahier : M4)
- [ ] **MCP en documentation complète**, point critique : « Module 4 · MCP · 45 min » → « MCP
  en documentation complète » ; la jauge avant envoi (3 204 / 3 584 le 2026-09-27, RAG éteint).
  Relevez la durée du tour. En cas de débordement, le noter pour décider : `expects_overflow`,
  ou mémoire globale éteinte.
- [ ] **Lazy loading** : jauge bien plus légère ; premier prompt : chargement de la
  documentation dans Orchestration. Si rien n'est chargé : « Afficher les actions forcées »,
  carte MCP, dépliez « Serveurs : … », « Charger la documentation » sur « Glossaire
  WaveStack », outil `local__define_term`, « Armer », puis « Rejouer le dernier prompt ».
  Second prompt (data.gouv.fr) : si le modèle appelle la recherche, « Résultat tronqué par le
  harnais : N tokens sur M (borne [tools] result_max_tokens) », N ≤ 1 200. Un appel d'outil MCP
  ne se force pas (story 27).

**Module 5 : Skills et hooks** (cahier : M5)
- [ ] **Skills** : « Module 5 · Skills et hooks · 60 min » → « Skills » ; la jauge grandit au
  chargement du skill ; notez l'outil appelé (`load_skill` ou `load_tool_doc`) et la durée du
  tour (248 s le 2026-09-27, sous pression mémoire). Si rien n'est chargé : carte Skills,
  dépliez « Skills : … », « Déclencher le skill » sur « Compte rendu de réunion », puis
  « Rejouer le dernier prompt ».
- [ ] **Caveman** : scénario « Caveman », prompt suggéré ; « Déclencher le skill » sur
  « Caveman », « Rejouer le dernier prompt » et « Comparer » : moins de sortie.
- [ ] **Hooks** : scénario « Hooks » ; H1 bloque `confidentiel/budget_projet.txt` (bande
  « Points d'accroche » du schéma), au besoin avec « Forcer l'appel » sur « Lecture de
  fichier » (carte Outils), préréglage « Fichier sensible », « Armer », puis « Rejouer le
  dernier prompt ».

**Module 6 : Sous-agent et compression** (cahier : M6)
- [ ] **Sous-agent** (story 19, lot A), « Module 6 · Sous-agent et compression · 60 min » →
  « Sous-agent » :
  - « Afficher les actions forcées » activé, carte « Sous-agent » : « Déléguer au sous-agent »
    ouvre le formulaire, « Annuler » le ferme (ne faisait rien le 2026-09-28, story 22) ;
  - premier prompt : le modèle délègue-t-il, ou lit-il le guide lui-même (pas d'étape
    « Délégation au sous-agent ») ? Dans ce cas, « Déléguer au sous-agent », préréglage
    « Résumer le guide du harnais », « Armer », puis « Rejouer le dernier prompt » ;
  - dépliez « Délégation au sous-agent » (économie de tokens, « état sauvegardé : N Mo,
    restauré en N s ») ;
  - Contexte LLM : onglets « Agent principal » (sélectionné par défaut : le résumé seul, en
    « Résultat du sous-agent ») et « Sous-agent sub1 » (le guide entier) ; cliquez l'un puis
    l'autre. Un second robot, « Sous-agent », apparaît dans le schéma ;
  - notez la taille de `sub1` (au plus 4 096 − 512) et tout « Préfixe non réutilisé » ;
  - finissez par les trois quiz (premier token, section 5.1).
- [ ] **Compression** (story 20), scénario « Compression du contexte » :
  - brique Compression éteinte, premier prompt : le journal entre en entier ; rallumée,
    « Rejouer le dernier prompt » et « Comparer » ;
  - « Compression (Headroom) » : tokens avant et après, erreur gardée ; dans Contexte LLM,
    « compressé » et le total « Sans compression » ;
  - le second prompt (lot 12) montre la perte ;
  - aucun appel « Retrieve more », et le scénario tient-il sans compression ?

**Transverses et métier** (cahier : X1 à X4)
- [ ] **Où vont mes données ?** (X1) : « Transverses et métier » → « Où vont mes données ? ».
  Depuis les stories 22 et 27, le scénario allume la brique MCP lui-même, en lazy loading, avec
  « Glossaire WaveStack » et « data.gouv.fr » : rien à allumer ni à cocher. Carte MCP : résumé
  « Serveurs : 2 activés sur 3 · Lazy loading » (brique éteinte, il dirait « · brique
  éteinte »). Schéma : outils et « Glossaire WaveStack » dans « 🖥 Poste de travail »,
  « data.gouv.fr » dans « 🌐 RÉSEAU · hors du poste » ; décochez puis recochez « data.gouv.fr »
  dans la carte MCP : le seul flux qui franchit la frontière disparaît, puis revient. Envoyez
  le prompt, cliquez le nœud « data.gouv.fr » : Orchestration montre ses « Données
  sortantes ».
- [ ] **SOC** (D6, X2), « Métier SOC : journal d'audit et garde-fou » (consigne repliée,
  « Afficher plus ») :
  - premier prompt : un seul incident, `adm.leroy`, avec l'accès initial à 02:14,
    l'élévation à 02:15, l'antivirus arrêté à 02:21 et 2,3 Go exfiltrés à 02:40 ; H2
    journalise. Si `read_file` n'est pas appelé : « Forcer l'appel » sur « Lecture de
    fichier », préréglage « Alertes SIEM (SOC) », « Armer », « Rejouer le dernier prompt » ;
  - second prompt : H1 bloque l'inventaire des comptes à privilèges ; l'agent escalade-t-il ?
  - clic sur « Journal d'audit » dans le schéma.
- [ ] **IAM** (X3) : « Métier IAM : Entra ID avec Microsoft Learn », les deux prompts : accès
  conditionnel avec MFA pour les administrateurs, PIM juste-à-temps, liens Microsoft Learn ;
  résultats bornés (lot B). Si le modèle cherche, l'étape « Exécute l'outil hors du poste »
  montre ses « Données sortantes » vers `learn.microsoft.com`.
- [ ] **Souveraineté** (X3) : « Métier Souveraineté : où partent les requêtes ? », les deux
  prompts. Pour chaque appel, dans Orchestration, étape « Exécute l'outil hors du poste »,
  dépliez « 🌐 RÉSEAU · Données sortantes » et lisez l'hôte : `mcp.data.gouv.fr` au premier
  prompt, `learn.microsoft.com` au second (les connexions aux deux serveurs sont aussi dans le
  groupe « Préparation du harnais »). Le modèle reste local (indicateur « Local »). Si rien
  n'est chargé : « Charger la documentation » sur « data.gouv.fr » (ou « Microsoft Learn »),
  l'outil nommé par le prompt, « Armer », « Rejouer le dernier prompt ». Le modèle appelle-t-il
  la recherche (H5) ?
- [ ] **NFR-2 global** (X4) : pic toutes briques actives (3 314 Mo le 2026-09-27, 3 270 Mo le
  2026-09-28 : 2B, embedding et reranker), sous le budget B relevé au diagnostic (au plus
  4 096 Mo).

**Modèles** (cahier : C4, C9, C10, D1 à D4m)
- [ ] **Changement à chaud** (story 17, lot E ; cahier D1) :
  - après un tour avec le 2B : « Changer de modèle… » → 4B → « Charger » : refus chiffré
    (section 5.5), le 2B reste ou redevient actif. Pour utiliser le 4B, il faut relever le
    budget (`budget_mode` = `fixed`, `budget_mb` = 6144, sous `memory`) : WaveStack arrêté,
    sauvegardez `settings.json` (une seule fois), modifiez seulement ces deux valeurs par
    WaveStack lui-même (pas à la main : le Bloc-notes ou `Set-Content` de PowerShell 5.1
    peuvent ajouter un BOM), puis restaurez la sauvegarde à la fin (blocs ci-dessous). C'est un
    écart à N5 : les mesures faites avec ce budget ne valent pas pour le budget par défaut ;

```powershell
# Sauvegarder settings.json (WaveStack arrêté, une seule fois)
$d = "$env:LOCALAPPDATA\WaveStack"
if (Test-Path "$d\settings.json.avant-4b") { throw "Sauvegarde settings.json.avant-4b déjà présente : restaurez d'abord, ne relancez pas ce bloc." }
Copy-Item "$d\settings.json" "$d\settings.json.avant-4b"
# Budget fixe de 6 144 Mo, sans toucher au reste de la section memory
uv run python -c "from wavestack import config; m = config.read_settings().get('memory', {}); m.update({'budget_mode': 'fixed', 'budget_mb': 6144}); config.save_setting('memory', m); print(config.read_settings()['memory'])"
# À la fin, WaveStack arrêté : restaurer settings.json
$d = "$env:LOCALAPPDATA\WaveStack"
if (Test-Path "$d\settings.json.avant-4b") { Move-Item "$d\settings.json.avant-4b" "$d\settings.json" -Force; "settings.json restauré" } else { "Aucune sauvegarde : rien n'est touché." }
```

  - avec un modèle qui tient dans le budget, Ollama lancé : après un tour avec le 2B
    (« Outils natifs », prompt de l'heure), « Changer de modèle… » → groupe « Sur ce poste ·
    Qwen (Alibaba) » → « Local · Ollama · qwen3.5:2b … » → « Charger ». Attendu : chronomètre
    de chargement dans la barre haute et la Vue humain, « Envoyer » désactivé ; puis
    « Rejouer le dernier prompt » : conversation gardée, ligne « Modèle : … » au-dessus du
    premier tour d'Ollama, rejeu par le nouveau modèle ; « Comparer » (tour du 2B à gauche,
    celui d'Ollama à droite) affiche « Modèle : … » pour chaque tour. Retour : « Local ·
    fichier · Qwen3.5-2B-Q4_K_M.gguf … » → « Charger » ;
  - un fichier incompatible ramène au modèle précédent, avec une explication en français
    (section 5.5).
- [ ] **llama-server** (story 18, lot E ; cahier C10), lancé **avant** WaveStack, toujours
  avec `-c 4096`, par `$llama` (section 2.1) :

```powershell
& $llama -m "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf" --port 8080 -np 1 -c 4096
```

  - Le diagnostic affiche « Local », l'adresse, la mémoire et « Choisir », sans avertissement
    de contexte. Un tour avec `get_datetime` montre « Local · llama-server » et le robot hors du
    cadre Harnais.
  - RSS attendue : celle du processus `llama-server` (commande de mesure ci-dessus), proche de
    la mémoire affichée au diagnostic (fichier de 1,28 Go plus le cache de 4 096 tokens), et
    bien en dessous des 5 137 Mo mesurés sans `-c`. Relevez les deux chiffres.
  - Pour N6 : second tour de `native_tools` (`prompt_ms`) et quiz du sous-agent avec ce
    serveur : tel que livré (RAG éteint depuis la story 27), puis RAG allumé à la main.
- [ ] **Ollama** (cahier D2m) :
  1. Dans un terminal : `ollama serve` (laissez-le ouvert ; un message d'adresse déjà
     utilisée veut dire qu'Ollama tourne déjà : c'est bon). Dans un second terminal :
     `ollama ps` (en général vide).
  2. « Changer de modèle… » → « Local · Ollama · qwen3.5:2b … » → « Charger » ; « Outils
     natifs », prompt de l'heure : un tour aboutit (comme le 2026-09-27). Avec un Ollama trop
     ancien pour servir `qwen35`, le modèle est accepté aussi, puis le premier tour échoue sur
     une erreur brute « HTTP 500 » d'Ollama (écart noté dans `deferred-work.md`).
  3. En bas d'Orchestration, « Journal des événements (N) » : une ligne « Erreur du harnais »
     qui commence par « Transparence réduite : Ollama a lu … tokens de prompt, le harnais en a
     compté … » donne les deux comptes à noter. Une ligne « Cache du serveur local » n'est
     qu'une information.
  4. `ollama ps` : `qwen3.5:2b` chargé ; retour au 2B intégré : `ollama ps` vide ; rechoisissez
     `qwen3.5:2b`, un tour, Ctrl+C sur WaveStack : `ollama ps` vide (sauf un modèle chargé par
     un autre programme).
- [ ] **Groq et Mistral avec le raisonnement** (story 13 ; cahier D3m) : saisissez la clé au
  diagnostic (section « Modèles cloud » : « Enregistrer la clé », « Tester »), ou faites
  `setx GROQ_API_KEY …` puis ouvrez un nouveau terminal. « Changer de modèle… » → « RÉSEAU ·
  Groq · openai/gpt-oss-120b … » → « Choisir… » → « Utiliser ce modèle ». Scénario
  Raisonnement :
  - Groq : « Toujours active pour ce modèle », 2 464 tokens utilisables ;
  - Mistral : `reasoning_effort` vaut `high` brique allumée, `none` brique éteinte, dans les
    « Données sortantes » ;
  - Mistral : un 429 au **premier** appel de « Tester » (premier envoi de la séance) signale
    un quota épuisé, pas un espacement trop court. Lisez d'abord le message du fournisseur dans
    le Journal des événements (capacité saturée ou quota), puis vérifiez le quota dans la
    console Mistral ;
  - D9 (cahier Z3), avec un quota disponible : section 7.
- [ ] **Relance** (cahier D4m) : Ctrl+C, puis `uv run wavestack` ; le dernier modèle chargé
  revient.

## 7. Décisions à trancher pendant le test

Le détail est dans `plan-corrections-palier-2.md` et `weekend-report-2026-09-26.md`
(section 3). D1 (compression en cours de tour), D4 (4 096 Mo, N5) et N1 à N5 sont tranchées.

| # | Défaut appliqué | À observer |
|---|---|---|
| N6 | Moteur intégré (llama-cpp-python) par défaut ; llama-server conseillé si le lot A ne suffit pas (il réutilisait son cache : 0,8 à 1,3 s au lieu de 23 s) | Critères du lot A (section 5.1) avec le moteur intégré, puis avec llama-server `-c 4096` |
| D2 | Sans reranker, seule la sous-option est indisponible | Sans le fichier du reranker (procédure ci-dessous), le RAG simple reste utilisable |
| D3 | Serveurs seuls : « … choisissez un modèle servi. » | Lancement sans GGUF ni clé, avec seulement llama-server (procédure ci-dessous) |
| D9 | Mistral : raisonnement non renvoyé (`resend = false`) | Avec un quota disponible, `resend: true` accepté ou refusé (400) |
| F2 | Tranchée au lot J : `[compression] cost_mb` = 110 | — |

D5 et D6 passent au lot H ; D7 à D18 se confirment en passant (par exemple D11 : jauge avec
une mémoire globale pleine, section 6).

**D2, sans le fichier du reranker** (cahier : Z1) :
1. WaveStack arrêté (Ctrl+C), mettez le reranker de côté (premier bloc ci-dessous).
2. Relancez `uv run wavestack`, puis « Module 3 · RAG · 45 min » → « RAG avec reranking ».
3. Carte RAG (Panneau des briques) : lisez la raison sous l'interrupteur « Reranking ». Ne
   cliquez pas « Télécharger le modèle de reranking (≈ … Mo) » : il retéléchargerait le
   fichier.
4. Premier prompt suggéré, « Envoyer » ; dépliez l'étape « Recherche RAG » d'Orchestration.
5. WaveStack arrêté, remettez le fichier (second bloc), puis relancez : la raison disparaît.
- Attendu : sous « Reranking », « Indisponible : modèle absent. Le modèle de reranking … n'est
  pas sur le poste. … Le RAG fonctionne sans reranking. » ; le tour aboutit, « Recherche RAG »
  dit pourquoi le reranking n'a pas eu lieu, sans étape « Reranking » ; la brique RAG reste
  disponible (RAG simple).

```powershell
# Mettre le reranker de côté, WaveStack arrêté
$m = "$env:LOCALAPPDATA\WaveStack\models\reranker"
Rename-Item "$m\bge-reranker-v2-m3-Q4_K_M.gguf" "bge-reranker-v2-m3-Q4_K_M.gguf.bak"
# Le remettre, WaveStack arrêté
$m = "$env:LOCALAPPDATA\WaveStack\models\reranker"
Rename-Item "$m\bge-reranker-v2-m3-Q4_K_M.gguf.bak" "bge-reranker-v2-m3-Q4_K_M.gguf"
```

**D3, serveurs seuls, sans GGUF ni clé** (cahier : Z2). Rien n'est déplacé ni supprimé, aucune
variable utilisateur ni machine n'est touchée : tout se passe dans un seul terminal, sur un
dossier de données temporaire et vide (`WAVESTACK_DATA_DIR`). Il faut llama-server
(section 2.1) : WaveStack compte les fichiers d'Ollama comme des GGUF, et les rend illisibles
dès qu'on lui cache leur dossier ; sans llama-server, D3 est « non fait (poste) ».
1. **D'abord**, dans un terminal : les clés posées pour tout le poste (premier bloc). Une valeur
   affichée : notez-le ; la suite la retire seulement du terminal de WaveStack.
2. Dans un autre terminal, lancez llama-server (section 2.1, « retrouvez l'exécutable », puis
   la dernière ligne du bloc d'installation) : le 2B reste à sa place.
3. Quittez Ollama (icône de la zone de notification, « Quit Ollama »). S'il reste lancé, ses
   modèles apparaissent au diagnostic comme incompatibles (« Fichier GGUF du modèle introuvable
   dans le dossier d'Ollama (…) ») : c'est attendu.
4. WaveStack arrêté, nouveau terminal à la racine du clone : second bloc. Il retire les clés de
   ce terminal (`Remove-Item Env:GROQ_API_KEY`, idem Mistral), pointe `WAVESTACK_DATA_DIR`
   vers un dossier temporaire vide (ni `api_keys.json`, ni `settings.json`, ni modèles),
   `OLLAMA_MODELS` et `HF_HOME` vers des dossiers vides, pour ce terminal seulement, liste les
   GGUF de LM Studio, puis refuse de lancer (`throw`) si une clé est encore visible. Si des
   fichiers de LM Studio sont listés, WaveStack les proposera au lieu de demander un modèle
   servi : notez-le (« non fait (poste) »), ou lisez seulement les lignes des clés.
5. Lisez le diagnostic : « Modèles détectés », puis « Modèles cloud » (lignes Groq et Mistral).
   - Attendu : « Aucun fichier GGUF, mais un serveur local sert 1 modèle : choisissez un modèle
     servi. », avec le modèle de llama-server et « Choisir » ; pour Groq et Mistral, ni « Clé
     fournie par la variable … » ni « Clé enregistrée », mais « Ou définissez la variable
     GROQ_API_KEY, puis ouvrez un nouveau terminal. » (idem `MISTRAL_API_KEY`). Relevez le
     libellé exact.
6. **Défaire** : Ctrl+C, puis fermez ce terminal ; arrêtez llama-server. Rien à restaurer ; le
   dossier temporaire (`%TEMP%\wavestack-z2-…`) peut rester. Contrôle : dans un nouveau
   terminal, `uv run wavestack` comme d'habitude retrouve vos clés et le 2B (cahier : « Clés et
   modèles intacts après le test »).

```powershell
# 1. Clés posées pour tout le poste ? (d'abord)
[Environment]::GetEnvironmentVariable("GROQ_API_KEY", "Machine"); [Environment]::GetEnvironmentVariable("MISTRAL_API_KEY", "Machine")
```

```powershell
# 4. Nouveau terminal : WaveStack sans clé ni données
Remove-Item Env:GROQ_API_KEY, Env:MISTRAL_API_KEY -ErrorAction SilentlyContinue
$z = Join-Path $env:TEMP ("wavestack-z2-" + (Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory -Force "$z\data", "$z\ollama", "$z\hf" | Out-Null
$env:WAVESTACK_DATA_DIR = "$z\data"; $env:OLLAMA_MODELS = "$z\ollama"; $env:HF_HOME = "$z\hf"
Remove-Item Env:HF_HUB_CACHE -ErrorAction SilentlyContinue
Get-ChildItem "$HOME\.lmstudio\models", "$HOME\.cache\lm-studio\models" -Recurse -Filter *.gguf -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
if ($env:GROQ_API_KEY -or $env:MISTRAL_API_KEY) { throw "Une clé est encore visible dans ce terminal : Z2 arrêté, rien n'est lancé." }
$env:UV_SYSTEM_CERTS = "1"
uv run wavestack
```

**D9, Mistral `resend`** (cahier : Z3), avec un quota disponible : WaveStack arrêté,
sauvegardez `settings.json` (une seule fois), ajoutez seulement `reasoning.resend = true` à
l'entrée `mistral` de `cloud.models` (créée au besoin, sans toucher au reste), relancez, passez
sur Mistral, jouez un tour avec outil (« Outils natifs », prompt de l'heure) puis un second
tour. Un 400 veut dire refus. WaveStack arrêté, restaurez `settings.json`.

```powershell
# Sauvegarder settings.json (WaveStack arrêté, une seule fois)
$d = "$env:LOCALAPPDATA\WaveStack"
if (Test-Path "$d\settings.json.avant-z3") { throw "Sauvegarde settings.json.avant-z3 déjà présente : restaurez d'abord, ne relancez pas ce bloc." }
Copy-Item "$d\settings.json" "$d\settings.json.avant-z3"
# Ajouter resend
uv run python -c "from wavestack import config; s = config.read_settings(); c = s.get('cloud', {}); ms = c.setdefault('models', []); e = next((m for m in ms if m.get('id') == 'mistral'), None) or ms.append({'id': 'mistral'}) or ms[-1]; e.setdefault('reasoning', {})['resend'] = True; config.save_setting('cloud', c); print(config.read_settings()['cloud'])"
# À la fin, WaveStack arrêté : restaurer settings.json
$d = "$env:LOCALAPPDATA\WaveStack"
if (Test-Path "$d\settings.json.avant-z3") { Move-Item "$d\settings.json.avant-z3" "$d\settings.json" -Force; "settings.json restauré" } else { "Aucune sauvegarde : rien n'est touché." }
```

**Ce que le lot H attend de ce test** (scénarios et consignes, revus après ce test) :
- H1 et D5 : extraits RAG hors sujet dans `mcp_lazy`, `skills`, `subagent` et `compression`
  (scores, et le modèle s'en sert-il à tort ?) ;
- H2 : Skills, `load_skill` ou `load_tool_doc` appelé ;
- H3 et D6 : SOC, l'agent escalade-t-il après le blocage de H1 ?
- H4 : Compression brique éteinte, le modèle lit-il le journal ?
- H5 : Souveraineté, un appel de recherche réel (flux sortants) ?
- H6 : durée de Skills, mesurée cette fois sans Edge, Outlook ni Teams.

## 8. Consigner les résultats et fusionner

| Scénario ou test | OK / KO | Jauge | 1er token | RSS max | Remarque |
|---|---|---|---|---|---|
| Installation, `uv lock --check` | | | | | |
| `pytest -q`, tests `model`, E2E | | | | | |
| Bancs story 12, `fits` | | | | | |
| Lot A : `native_tools` 2e tour, mémoire, raisonnement, quiz | | | | | |
| Lot B : `mcp_lazy`, `data_flows`, `iam`, `sovereignty` | | | | | |
| Lot C : prompt du train | | | | | |
| Lot D : Wikipédia | | | | | |
| Lot E : llama-server sans `-c`, 4B, Arrêter, `llama3.2:3b`, fichier incompatible | | | | | |
| Lot F : Headroom, `cost_mb` | | | | | |
| Lot G : script pendant une session | | | | | |
| N6 : critères du lot A avec llama-server `-c 4096` | | | | | |
| Budget de raisonnement qui tient (prompt du train < 120 s) | | | | | |
| D2 (sans reranker), D3 (serveurs seuls) | | | | | |
| D9 (Mistral `resend`) | | | | | |
| F2 : RSS ajoutée par Headroom, `cost_mb` | | | | | |
| M1 LLM nu / Raisonnement / Mémoire courte / Prompt système / Mémoire globale | | | | | |
| M2 Outils natifs / réseau | | | | | |
| M3 RAG / Reranking | | | | | |
| M4 MCP complet / Lazy loading | | | | | |
| M5 Skills / Caveman / Hooks | | | | | |
| M6 Sous-agent / Compression | | | | | |
| Données / SOC / IAM / Souveraineté | | | | | |
| llama-server `-c 4096`, Ollama | | | | | |
| Groq, Mistral, relance | | | | | |

**Où consigner** :
- le tableau et les messages d'erreur dans le chat ;
- dans `_bmad-output/implementation-artifacts/plan-corrections-palier-2.md`, le résultat de
  chaque critère des lots A à G (tenu ou non, avec la mesure), les décisions N6, D2, D3, D9 et
  F2, et ce que le lot H doit traiter ;
- dans `_bmad-output/implementation-artifacts/deferred-work.md`, une entrée par nouvel écart,
  au format existant :

```yaml
- source_spec: `_bmad-output/specs/spec-agentic-harness-training-demo/stories/19-delegation-a-un-sous-agent.md`
  summary: Une phrase qui décrit l'écart.
  evidence: Test manuel du 2026-MM-JJ sur le PC cible (Qwen3.5-2B Q4_K_M, CPU) : action, observation, mesure.
```

**Fusion** : pas pendant cette séance, qui s'arrête à « Où consigner ». La fusion attend le
lot H, une fois les critères A à G tenus :
- [ ] Pousser les valeurs mesurées qui changent : `[compression] cost_mb`, `measured_rss_mb`,
  les JSON et le verdict de la story 12.
- [ ] Reporter les décisions, puis retirer les mentions « à valider » d'AD-4 et AD-21 dans le
  spine.
- [ ] Fusionner la PR #1 sur GitHub (« Merge pull request »), puis mettre `main` à jour :

```powershell
git switch main; git pull; uv sync --extra compression
```
