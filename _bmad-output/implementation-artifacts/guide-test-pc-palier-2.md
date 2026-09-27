# Guide de test sur le PC cible : palier 2 (stories 12 à 21, lots A à G)

Pour récupérer la branche du palier 2 et la tester fonctionnellement sur le PC professionnel
(Windows 11, sans droits administrateur, CPU seul). Les commandes sont en PowerShell et se
lancent depuis la racine du clone. Sources : `README.md`, `weekend-report-2026-09-26.md`
(sections 3 et 4), stories 12 à 21, `plan-corrections-palier-2.md` (test du 2026-09-27, lots A
à I), `spec-lot-*.md`, `tools/bench/README.md`, `tools/e2e/README.md`.

Cette version prépare la séance qui suit le test du 2026-09-27 : elle vérifie d'abord, point
par point, les corrections des lots A à G (section 5), puis reprend le parcours complet. Ce que
le plan range dans « Ce qui marche déjà » n'est pas re-testé en détail : parcourez-le.

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
    `calendrier.api.gouv.fr` ;
  - les GGUF Qwen3.5-2B Q4_K_M amont (unsloth) et Qwen3.5-4B, dans
    `%LOCALAPPDATA%\WaveStack\models` ;
  - environ 4 Go libres : 2,1 Go pour le banc, 285 Mo pour l'extra `compression`, plus
    Chromium pour l'E2E ; les modèles d'embedding et de reranker sont déjà en place depuis le
    2026-09-27 ;
  - en option : des clés Groq et Mistral, Ollama (`qwen3.5:2b`, `llama3.2:3b`), et
    `llama-server.exe` (llama.cpp) ;
  - **Edge, Outlook et Teams fermés pendant les mesures** : ils saturaient la RAM à la story 9,
    et Edge ouvert a faussé la mesure de Skills le 2026-09-27 (compression mémoire de Windows
    ≈ 1 Go).
- **Ordre** : 1 → 2 → 3 → 4 → 5, avec les bancs avant de lancer WaveStack. Ensuite 6, dans
  l'ordre des modules, puis le métier et les modèles, et 7. La séance s'arrête à « Où
  consigner » (section 8) : la fusion attend le lot H.
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
git switch claude/dreamy-cerf-gdjtee
git pull                                     # la branche locale existe depuis le 2026-09-27
git log --oneline -12
```

- [ ] HEAD : `docs: rapport des corrections du palier 2 (lots A à G et I)` ou plus récent.
  En dessous, du plus récent au plus ancien : `cb3a20e` (correctif de deux textes du code,
  suite des lots A et E), `e2b399c … (lot I)`, puis `2abad49 … (lot G)`, `515c858 … (lot F)`, `12faad6 … (lot E)`, `8afb1d5 … (lot D)`,
  `dc193ca … (lot C)`, `0f54120 … (lot B)`, `7b22faf … (lot A)` et `373d30a … (lot 0)`. La
  référence est le dernier commit de la PR #1.
- Zip, sans Git : sur GitHub, choisissez la branche, puis « Code » → « Download ZIP ». Avec
  le navigateur connecté, l'adresse directe est
  `https://github.com/Aliquanto3/agentic-harness-training-demo/archive/refs/heads/claude/dreamy-cerf-gdjtee.zip`.

## 2. Installer

Validé le 2026-09-27 : `uv lock` inchangé, `uv sync --extra compression`, aucun blocage
AppLocker ni WDAC. Les lots A à I n'ont touché ni `pyproject.toml` ni `uv.lock`.

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

## 3. Vérifications automatiques rapides

```powershell
uv run pytest -q
```

- [ ] Attendu sous Windows, avec l'extra `compression` : **934 réussis, 3 sautés,
  6 désélectionnés** (937 tests collectés hors `model`). Les 3 sauts attendus :
  - `test_an_index_replaced_during_the_session_is_read_again[replaced-while-open]` et
    `test_an_index_replaced_with_the_reranker_loaded_closes_it[replaced-while-open]` :
    « Windows refuse de remplacer un fichier qu'une connexion tient ouvert ». Leur variante
    `[connection-closed-first]` doit passer : ce sont les 2 échecs du 2026-09-27 (lot G) ;
  - `test_the_simulated_windows_rules_refuse_replacing_an_open_index` : « simulation sans
    /proc : sous Windows, le système applique ses règles ».
- Les 4 tests Headroom (dont le test hors ligne du lot F) et les 3 tests propres à Windows
  (`ProactorEventLoop`, chemin `C:/Windows/win.ini`) tournent. Sans l'extra, ces 4 tests
  sont sautés (« … (extra) absent ») : 930 réussis, 7 sautés. Référence Linux au
  commit du lot G : 934 réussis, 3 sautés avec l'extra (les 3 tests propres à Windows), 930 et
  7 sans. Tout autre échec est un écart à remonter.
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
- Gardez ces deux variables dans ce terminal pour le test `fits` (section 4.4).

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
  RSS ajoutée au pic (`configured.rss_added_mb`) ≤ 300 Mo (107 Mo sous Linux ; 57 Mo sur ce
  poste avant le lot F). Sans `--json`, la dernière ligne dit « == Verdict Headroom : RETENU ».
- [ ] Les deux rapports portent `rss_added_method` = `pic`.
- [ ] `granite107m_q8` : `recall_at_1` ≥ 0,75, `rss_added_mb` ≈ 428 (≤ 600), `pooling_gguf`
  (2 = CLS). bge-m3 (≈ 731 Mo) et Qwen3-Embedding (≈ 900 Mo) dépassent désormais 600 Mo : leur
  verdict change, granite reste retenu (`verdict.embedding.id`).
- [ ] `bgererank_m3_q4km` : MRR égal ou meilleur, `rss_added_mb` ≈ 736 (≤ 800, de peu).
- [ ] `e5small_q8` n'est plus un candidat : `embed --only e5small_q8` affiche « Candidat
  inconnu : e5small_q8 (retiré des candidats : ne se charge pas avec llama-cpp-python
  0.3.35 …) » et sort avec le code 2.
- Où reporter : les deux JSON et le verdict dans la section « Verdict » de la story 12.
  `measured_rss_mb` (430 et 740 aujourd'hui) et `[compression] cost_mb` (130) ne changent que
  si la mesure s'en écarte nettement, c'est-à-dire de plus de 20 % ou de plus de 50 Mo : la
  nouvelle valeur est alors la mesure plus 30 %, arrondie à la dizaine (section 5.6).

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
Depuis le lot B, le test `fits` compte avec le vrai tokenizer quand `WAVESTACK_TEST_GGUF` est
posée (sinon à 2 caractères par token) et réserve la place d'un premier résultat borné.

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
  - Hypothèse : les blancs réels autour de `</think>` peuvent différer de ceux du gabarit ; la
    relecture serait alors signalée avec la cause « historique ». Notez-le.
- [ ] **Sous-agent** (décision N2) : scénario « Sous-agent », délégation puis trois quiz,
  deux fois : d'abord tel que livré (RAG allumé), puis relancé avec la brique RAG éteinte
  avant le premier prompt.
  - Attendu : la ligne « Délégation au sous-agent » affiche « état sauvegardé : N Mo, restauré
    en N s » ; RAG éteint, au premier appel principal après le retour, pas de « Préfixe non
    réutilisé ».
  - **Critère du plan : premier token de chaque quiz sous 15 s** (68 à 99 s le 2026-09-27).
    Relevez `prompt_ms` dans les deux passages. RAG allumé, chaque tour relit tout le contexte
    par conception (« Préfixe non réutilisé », cause historique : extraits RAG retirés, voir
    l'hypothèse ci-dessous), ce que le lot A ne corrige pas : l'acceptation du lot A se juge
    RAG éteint, et le RAG dans ce scénario relève de D5, au lot H. Décision prise par défaut, à
    confirmer.
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
  vont mes données ? » (`data_flows`, MCP activé à la main avec le serveur local puis
  data.gouv.fr, comme le dit sa consigne), « Métier IAM » (`iam`) et « Métier Souveraineté »
  (`sovereignty`, les deux prompts).
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

- [ ] **Carte Raisonnement** (modèle local) : « Budget de réflexion : 1 024 tokens ; au-delà,
  le harnais ferme la réflexion et garde 512 tokens pour la réponse. »
- [ ] **Scénario Raisonnement**, prompt du train (réponse juste : 17 h 50).
  - Attendu : une réponse dans la bulle. Si la réflexion atteint le budget, Orchestration
    montre l'étape « Raisonnement coupé » (« Raisonnement coupé par le harnais à N tokens… »),
    puis la réponse ; un seul « Appel au modèle terminé ».
  - **Critère : une réponse, même courte, en moins de 120 s** (137 s et bulle vide le
    2026-09-27).
  - Envoyez ensuite un second message (par exemple « Et avec 10 minutes de retard ? ») :
    aucune étape « Préfixe non réutilisé » (la réflexion coupée, sa fermeture et la réponse
    prolongent le cache).
  - Hypothèse : à ≈ 11 tokens/s, 1 024 tokens de réflexion prennent ≈ 90 s. Au-delà de 120 s,
    WaveStack arrêté, baissez le budget dans `settings.json`
    (`{"reasoning": {"budget_tokens": 768}}`, borné de 128 à 1 408), rejouez et notez la valeur
    qui tient.

### 5.4 Lot D : User-Agent et parcours E2E

- [ ] **Wikipédia** : scénario « Outils réseau », second prompt (Mont-Saint-Michel).
  - Attendu : `wikipedia_summary` ou `fetch_page` renvoie le contenu de l'article, plus de 403
    « Please respect our robot policy ». L'User-Agent porte le contact de `[net] contact`.
- [ ] **E2E sur ce poste connecté** : 0 échec (section 3).

### 5.5 Lot E : modèles, mémoire, refus, arrêt

- [ ] **llama-server sans `-c`** (E1). Arrêtez d'abord WaveStack (Ctrl+C). Attention :
  llama-server sans `-c` réserve ≈ 5 Go ; à côté de WaveStack qui tient le 2B, le total peut
  dépasser la RAM du poste. Pour cette mesure, choisissez dans WaveStack un petit modèle ou un
  modèle cloud avant de l'arrêter (le dernier chargé revient au lancement), puis lancez
  llama-server, puis WaveStack :

```powershell
llama-server -m "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf" --port 8080 -np 1
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
    « 0,0 Go ») ; le 2B reste ou redevient actif.
  - Critère : le 4B est refusé par le budget de 4 096 Mo, qui ne change pas (N5) : 4,27 Go
    mesurés après 3 000 tokens le 2026-09-27, et la sonde compte désormais les poids, le cache
    de toute la fenêtre et les tampons de calcul (3,4 Go estimés avant le lot E). Relevez
    l'estimation affichée, et si le 4B a été resondé, la durée de la sonde.
  - Hypothèse : l'estimation du 4B n'a été vérifiée qu'avec une RSS injectée.
- [ ] **« Arrêter » pendant un chargement** (E4), sur le chargement d'un GGUF, assez long pour
  cliquer : la sonde d'un fichier jamais sondé, ou le 4B avec un budget relevé (section 6,
  « Changement à chaud »). Pendant le chronomètre de chargement, cliquez « Arrêter ». Un
  modèle Ollama ne charge côté WaveStack que son tokenizer, trop vite pour cliquer :
  facultatif.
  - Attendu : « Arrêt demandé, effectif à la fin de l'étape en cours » dans la barre haute,
    puis l'issue « Chargement arrêté : {modèle précédent} est de nouveau actif. » L'arrêt
    n'agit qu'à la fin de l'étape en cours (libération, sonde ou chargement).
- [ ] **Briques indisponibles** (E5) : `llama3.2:3b` via Ollama, scénario « Outils natifs ».
  - Attendu : sous la consigne, « Brique du scénario indisponible avec ce modèle : Outils : Le
    modèle chargé n'offre pas l'appel d'outils (aucun format d'appel connu pour cette famille
    de modèle) : choisissez un autre modèle. »
- [ ] **Fichier incompatible** (E6) : choisissez le blob Ollama refusé le 2026-09-27 comme un
  fichier.
  - Attendu : « llama-cpp-python 0.3.35 ne sait pas charger ce fichier (architecture non prise
    en charge, fichier incomplet ou abîmé). Choisissez un autre modèle, ou servez-le avec Ollama
    ou llama-server. » Le message brut de llama.cpp n'est plus qu'un détail technique ; le
    modèle précédent reste actif.
- [ ] Refus chiffré d'un modèle Ollama trop gros (`olmo-3:7b` le 2026-09-27), si vous l'avez :
  WaveStack occupe ≈ 200 Mo sans le modèle actif (et non « 0,0 Go »).

### 5.6 Lot F : Headroom hors ligne et banc

- [ ] Banc `headroom` : « RETENU », aucune tentative réseau (section 4.1).
- [ ] `test_headroom_makes_no_network_attempt_at_import_nor_compression` a tourné et réussi
  dans `uv run pytest -q` (section 3).
- [ ] Banc `embed` mesuré au pic : granite ≈ +428 Mo, reranker ≈ +736 Mo (section 4.1).
- [ ] Scénario « Compression du contexte » : l'étape « Compression (Headroom) » garde l'erreur
  du journal, comme le 2026-09-27 (le changement de comptage ne doit rien casser).
- Hypothèse : `[compression] cost_mb` reste à 130 (décision par défaut du lot F : 99 à 107 Mo
  au pic sous Linux avec `gpt-4`). Reportez la RSS ajoutée du banc sous Windows ; si elle
  s'écarte de 130 de plus de 20 % ou de plus de 50 Mo, la nouvelle valeur est la mesure plus
  30 %, arrondie à la dizaine (section 4.1).

### 5.7 Lot G : tests sous Windows et tests `model`

- [ ] `uv run pytest -q` : 934 réussis, 3 sautés, les deux tests G1 compris (section 3).
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

**Module 1 : Du LLM nu au harnais**
- [ ] **LLM nu** : « Quelle heure est-il ? » → heure inventée ou aveu. Premier token en
  moins de 10 s.
- [ ] **Raisonnement** (story 13, lot C), sur le prompt du train (réponse juste : 17 h 50) :
  - raisonnement replié dans la Vue humain, bloc « Raisonnement du modèle » dans Contexte LLM,
    réserve de 1 536 tokens dans la jauge, 2 560 utilisables ;
  - « Afficher le raisonnement » décoché : la bulle ne garde que le texte ;
  - brique éteinte, « Rejouer le dernier prompt », puis « Comparer » : moins de sortie ;
  - une réponse en moins de 120 s, coupe éventuelle visible (section 5.3).
- [ ] **Mémoire courte** : le prénom revient ; brique éteinte, le rejeu l'oublie.
- [ ] **Prompt système** : « … comme un pirate. », puis rejeu : la réponse change.
- [ ] **Mémoire globale** (story 14, lot A) :
  - premier prompt : appel de `remember` et écriture de `memory.json` (sinon « Afficher les
    actions forcées », puis « Écrire en mémoire ») ;
  - « Vider la conversation », puis second prompt : la préférence revient par le message
    système (pas avant : décision N1) ;
  - « Modifier la mémoire » (modifier, effacer), clic sur le fichier dans le schéma, puis
    « Réinitialiser » : la démonstration revient ;
  - D11 : jauge avec une mémoire pleine.

**Module 2 : Outils**
- [ ] **Outils natifs** : Orchestration montre la demande, l'exécution et la réinjection.
- [ ] **Outils réseau** : nœud en zone Réseau ; « Données sortantes » = texte exact envoyé ;
  Wikipédia répond (lot D).

**Module 3 : RAG**
- [ ] **RAG** (story 15) : la carte ne dit pas « sqlite-vec ne se charge pas ».
  - Brique éteinte, premier prompt : Exemplia est inconnue.
  - Brique rallumée, rejeu, « Comparer » : la réponse donne 14 caractères.
  - « Recherche RAG » : requête, extraits, scores et durée. Survolez l'index dans le schéma.
- [ ] **RAG avec reranking** (story 16), sur l'hôtel à Paris :
  - l'étape « Reranking » affiche « 3 gardés sur 8 », l'ordre avant et après, et deux scores ;
  - au moins un extrait change de rang (constaté le 2026-09-27) ;
  - relevez la durée des 8 passes et le RSS ajouté (au plus 800 Mo) ;
  - case décochée : « Prend effet au prochain tour », et plus d'étape au rejeu.

**Module 4 : MCP**
- [ ] **MCP en documentation complète**, point critique : la jauge avant envoi (3 204 / 3 584
  le 2026-09-27, RAG éteint). Relevez la durée du tour. En cas de débordement, le noter pour
  décider : `expects_overflow`, ou mémoire globale éteinte.
- [ ] **Lazy loading** : jauge bien plus légère, RAG rallumé ; deux prompts sans débordement
  (lot B) ; chargement de la documentation dans Orchestration.

**Module 5 : Skills et hooks**
- [ ] **Skills** : la jauge grandit au chargement du skill ; notez l'outil appelé
  (`load_skill` ou `load_tool_doc`, lot H) et la durée du tour (248 s le 2026-09-27, sous
  pression mémoire).
- [ ] **Caveman** : « Déclencher le skill » sur Caveman, puis rejeu et « Comparer » : moins de
  sortie.
- [ ] **Hooks** : H1 bloque `confidentiel/budget_projet.txt` (bande « Points d'accroche »),
  au besoin avec le forçage « Fichier sensible ».

**Module 6 : Sous-agent et compression**
- [ ] **Sous-agent** (story 19, lot A) :
  - le modèle délègue-t-il, ou lit-il le guide lui-même ? Sinon, forcez « Déléguer au
    sous-agent » avec « Résumer le guide du harnais » ;
  - dépliez « Délégation au sous-agent » (économie de tokens, état sauvegardé) ;
  - Contexte LLM bascule entre le contexte principal et `sub1` ; un second robot apparaît ;
  - notez la taille de `sub{n}` (au plus 4 096 − 512) et tout « Préfixe non réutilisé » ;
  - finissez par les trois quiz (premier token, section 5.1).
- [ ] **Compression** (story 20) :
  - brique éteinte, le journal entre en entier ; rallumée, rejeu et « Comparer » ;
  - « Compression (Headroom) » : tokens avant et après, erreur gardée ; dans Contexte LLM,
    « compressé » et le total « Sans compression » ;
  - le second prompt (lot 12) montre la perte ;
  - aucun appel « Retrieve more », et le scénario tient-il sans compression ?

**Transverses et métier**
- [ ] **Où vont mes données ?** : seul le flux vers data.gouv.fr franchit la frontière ;
  lazy loading actif au lancement.
- [ ] **SOC** (D6) :
  - premier prompt : un seul incident, `adm.leroy`, avec l'accès initial à 02:14,
    l'élévation à 02:15, l'antivirus arrêté à 02:21 et 2,3 Go exfiltrés à 02:40 ; H2
    journalise ;
  - second prompt : H1 bloque l'inventaire des comptes à privilèges ; l'agent escalade-t-il ?
  - clic sur « Journal d'audit » dans le schéma.
- [ ] **IAM** : accès conditionnel avec MFA pour les administrateurs, PIM juste-à-temps, liens
  Microsoft Learn ; résultats bornés (lot B).
- [ ] **Souveraineté** : les « Données sortantes » de chaque appel montrent deux flux ; le
  modèle reste local. Le modèle appelle-t-il la recherche (lot H) ?
- [ ] **NFR-2 global** : pic toutes briques actives (3 314 Mo le 2026-09-27 : 2B, embedding
  et reranker), sous le plafond de 4 096 Mo.

**Modèles**
- [ ] **Changement à chaud** (story 17, lot E) :
  - après un tour avec le 2B : « Changer de modèle… » → 4B → « Charger » : refus chiffré
    (section 5.5), le 2B reste ou redevient actif. Pour utiliser le 4B, il faut relever le
    budget : WaveStack arrêté, `{"memory": {"budget_mb": 5120}}` dans `settings.json` (JSON).
    C'est un écart à N5 (le budget par défaut reste 4 096 Mo) : les mesures suivantes ne valent
    plus pour le budget par défaut ; retirez la clé ensuite ;
  - avec un modèle qui tient dans le budget (le 2B après un modèle Ollama, par exemple) :
    chronomètre, envoi désactivé, conversation gardée, ligne « Modèle : … », rejeu par le
    nouveau modèle, « Comparer » par modèle ;
  - un fichier incompatible ramène au modèle précédent, avec une explication en français.
- [ ] **llama-server** (story 18, lot E), lancé **avant** WaveStack, toujours avec `-c 4096` :

```powershell
llama-server -m "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf" --port 8080 -np 1 -c 4096
```

  - Le diagnostic affiche « Local », l'adresse, la mémoire et « Choisir », sans avertissement
    de contexte. Un tour avec `get_datetime` montre « Local · llama-server » et le robot hors du
    cadre Harnais.
  - RSS attendue : celle du processus `llama-server` (commande de mesure ci-dessus), proche de
    la mémoire affichée au diagnostic (fichier de 1,28 Go plus le cache de 4 096 tokens), et
    bien en dessous des 5 137 Mo mesurés sans `-c`. Relevez les deux chiffres.
  - Pour N6 : second tour de `native_tools` (`prompt_ms`) et quiz du sous-agent avec ce
    serveur.
- [ ] **Ollama**, avec `ollama serve` lancé avant WaveStack :
  - `qwen3.5:2b` est accepté et un tour aboutit (comme le 2026-09-27, avec l'Ollama du
    poste). Avec un Ollama trop ancien pour servir `qwen35`, le modèle est accepté aussi, puis
    le premier tour échoue sur une erreur brute « HTTP 500 » d'Ollama, sans raison en français
    ni retour au modèle précédent (écart noté dans `deferred-work.md`). Seul un tokenizer que
    llama-cpp-python ne sait pas lire est refusé au chargement, avec la raison et le modèle
    précédent gardé ;
  - un tour : notez toute alerte « transparence réduite » et ses deux comptes ;
  - « Arrêter » pendant le chargement (section 5.5) ;
  - `ollama ps` est vide après un changement de modèle et après la fermeture de WaveStack,
    sauf pour un modèle chargé par un autre programme.
- [ ] **Groq et Mistral avec le raisonnement** (story 13) : saisissez la clé au diagnostic
  (« Enregistrer la clé », « Tester »), ou faites `setx GROQ_API_KEY …` puis ouvrez un
  nouveau terminal. Scénario Raisonnement :
  - Groq : « Toujours active pour ce modèle », 2 464 tokens utilisables ;
  - Mistral : `reasoning_effort` vaut `high` brique allumée, `none` brique éteinte, dans les
    « Données sortantes » ;
  - Mistral : un 429 au **premier** appel de « Tester » (premier envoi de la séance) signale
    un quota épuisé, pas un espacement trop court. Lisez d'abord le message du fournisseur dans
    le Journal des événements (capacité saturée ou quota), puis vérifiez le quota dans la
    console Mistral ;
  - D9, avec un quota disponible : WaveStack arrêté, mettez
    `{"cloud": {"models": [{"id": "mistral", "reasoning": {"resend": true}}]}}` dans
    `settings.json`, puis jouez un tour avec outil et un second tour. Un 400 veut dire refus.
- [ ] **Relance** : Ctrl+C, puis `uv run wavestack` ; le dernier modèle chargé revient.

## 7. Décisions à trancher pendant le test

Le détail est dans `plan-corrections-palier-2.md` et `weekend-report-2026-09-26.md`
(section 3). D1 (compression en cours de tour), D4 (4 096 Mo, N5) et N1 à N5 sont tranchées.

| # | Défaut appliqué | À observer |
|---|---|---|
| N6 | Moteur intégré (llama-cpp-python) par défaut ; llama-server conseillé si le lot A ne suffit pas (il réutilisait son cache : 0,8 à 1,3 s au lieu de 23 s) | Critères du lot A (section 5.1) avec le moteur intégré, puis avec llama-server `-c 4096` |
| D2 | Sans reranker, seule la sous-option est indisponible | Sans le fichier du reranker (procédure ci-dessous), le RAG simple reste utilisable |
| D3 | Serveurs seuls : « Choisissez un modèle servi » | Lancement sans GGUF ni clé, avec seulement Ollama ou llama-server (procédure ci-dessous) |
| D9 | Mistral : raisonnement non renvoyé (`resend = false`) | Avec un quota disponible, `resend: true` accepté ou refusé (400) |
| F2 | `[compression] cost_mb` = 130 | RSS ajoutée du banc `headroom` sous Windows (section 5.6) |

D5 et D6 passent au lot H ; D7 à D18 se confirment en passant (par exemple D11 : jauge avec
une mémoire globale pleine, section 6).

**D2**, WaveStack arrêté, puis relancé ; défaire à la fin :

```powershell
$m = "$env:LOCALAPPDATA\WaveStack\models\reranker"
Rename-Item "$m\bge-reranker-v2-m3-Q4_K_M.gguf" "bge-reranker-v2-m3-Q4_K_M.gguf.bak"
# … lancement, scénario « RAG avec reranking » : sous-option indisponible, RAG simple utilisable …
Rename-Item "$m\bge-reranker-v2-m3-Q4_K_M.gguf.bak" "bge-reranker-v2-m3-Q4_K_M.gguf"
```

**D3**, WaveStack arrêté, Ollama ou llama-server lancé ; défaire à la fin, WaveStack arrêté,
depuis `sauvegarde-palier-2` (section 0) :

```powershell
$d = "$env:LOCALAPPDATA\WaveStack"
New-Item -ItemType Directory -Force "$d\models-de-cote" | Out-Null
Move-Item "$d\models\*.gguf" "$d\models-de-cote\"
Move-Item "$d\api_keys.json" "$d\models-de-cote\" -ErrorAction SilentlyContinue
$s = Get-Content "$d\settings.json" -Raw | ConvertFrom-Json
$s.PSObject.Properties.Remove("selected_model")
$s | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 "$d\settings.json"
# … lancement : le diagnostic bloque avec « Choisissez un modèle servi » …
Move-Item "$d\models-de-cote\*.gguf" "$d\models\"
Copy-Item "$d\sauvegarde-palier-2\settings.json", "$d\sauvegarde-palier-2\api_keys.json" "$d\" -Force -ErrorAction SilentlyContinue
```

Les variables `GROQ_API_KEY` et `MISTRAL_API_KEY` fournissent aussi une clé : pour D3, lancez
WaveStack depuis un terminal où elles sont vides (`$env:GROQ_API_KEY = ""`, de même pour
Mistral).

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
