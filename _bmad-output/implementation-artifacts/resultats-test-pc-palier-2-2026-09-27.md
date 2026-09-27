# Résultats du test sur PC cible : palier 2, corrections des lots A à G et I (2026-09-27, soir)

Poste : Windows 11 Enterprise 10.0.26200, PowerShell, sans droits administrateur, CPU seul,
16 Go. Branche `claude/dreamy-cerf-gdjtee`. Guide suivi : `guide-test-pc-palier-2.md`
(sections 0 à 4, et ce qui se mesure sans interface de la section 5). Consigné au fil de l'eau
par Claude Code ; aucun code source modifié.

## Section 0 et 1 : sauvegarde et code

| Commande | Attendu (guide) | Obtenu | Statut |
|---|---|---|---|
| Copie `settings.json`, `api_keys.json`, `memory.json` dans `%LOCALAPPDATA%\WaveStack\sauvegarde-palier-2` | copie de l'état palier 2 | 3 fichiers copiés (7 704, 235, 481 octets) | OK |
| `git status` | arbre propre, rien sous `tools/e2e/screenshots` | propre ; branche locale en retard de 2 commits | OK |
| `git fetch origin` ; `git merge --ff-only origin/claude/dreamy-cerf-gdjtee` (équivaut à `git pull`) | HEAD = `2f43f8f docs: rapport des corrections du palier 2 (lots A à G et I)` ou plus récent | HEAD = `2f43f8f`, puis `cb3a20e`, `e2b399c`, `2abad49`, `515c858`, `12faad6`, `8afb1d5`, `dc193ca`, `0f54120`, `7b22faf`, `373d30a` | OK |
| Modèles dans `%LOCALAPPDATA%\WaveStack\models` | 2B, 4B, embedding, reranker | `Qwen3.5-2B-Q4_K_M.gguf` (1 280 835 840), `Qwen3.5-4B-Q4_K_M.gguf` (2 740 937 888), `embedding\granite-embedding-107m-multilingual-Q8_0.gguf` (121 020 096), `reranker\bge-reranker-v2-m3-Q4_K_M.gguf` (438 376 864) | OK (tailles de 4.2 conformes) |

État de `probed_models` avant le premier lancement : 2B `rss_bytes` 1 146 068 992,
`kv_bytes_per_token` 49 152, sans `probe_version` ; 4B `rss_bytes` 2 880 712 704,
`kv_bytes_per_token` 131 072, sans `probe_version`.

## Section 2 : installation et premier lancement

Edge, Outlook et Teams fermés (confirmé par l'utilisateur avant le premier lancement). Ollama
tourne en arrière-plan (port 11434), sans modèle chargé (`ollama ps` vide).

| Commande | Attendu (guide) | Obtenu | Statut |
|---|---|---|---|
| `$env:UV_SYSTEM_CERTS = "1"` ; `uv lock --check` | passe | « Resolved 91 packages in 5ms », code 0 | OK |
| `uv sync --extra compression` | Headroom installé | « Checked 90 packages », code 0 (déjà en place) | OK |
| Premier lancement : `uv run python <scratchpad>\launch_nobrowser.py` (appelle `wavestack.cli.main` avec `webbrowser.open` neutralisé, pour ne pas ouvrir Edge), puis arrêt du processus | le 2B est resondé une fois, quelques dizaines de secondes de plus | lanceur démarré à 20:59:31 ; entrée du 2B réécrite à 21:00:04,7 (`probed_at`) : **≈ 33 s** du démarrage à la fin de la sonde, imports compris (première observation de `probe_version` 2 à 25,4 s après le début de la surveillance). Pic de RSS d'un processus Python pendant la sonde : 1 990 Mo | OK |
| `probed_models` du 2B dans `settings.json` | `probe_version` 2, `rss_bytes`, `kv_bytes_per_token`, `probe_window` 4 096, `rss_eval_tokens` | `probe_version` 2, `rss_bytes` 2 025 000 960 (1 931 Mo ; 1 093 Mo avant le lot E), `kv_bytes_per_token` 49 152, `probe_window` 4 096, `rss_eval_tokens` 512 | OK |
| `GET /api/diagnostic` (au lieu de la page) | prêt | `ready: true`, `blocking_checks` vide | OK |
| `GET /api/state` : cartes Compression et RAG (au lieu de l'interface) | Compression disponible ; RAG sans « sqlite-vec ne se charge pas » | `compression` : `available: true`, `reason_fr: null` ; `rag` : `available: true`, `reason_fr: null` | OK |
| Mémoire de WaveStack après le lancement, 2B chargé, aucun tour | — | processus 2472 : 1 183 Mo (pic 1 271 Mo, privé 2 390 Mo) ; RAM libre du poste 6 053 / 16 064 Mo | relevé |

Remarque : le 4B garde son entrée d'avant le lot E (sans `probe_version`) ; il sera resondé
au moment du choix (comportement prévu).

## Section 3 : vérifications automatiques

| Commande | Attendu (guide) | Obtenu | Statut |
|---|---|---|---|
| `uv run ruff check .` | propre | « All checks passed! » | OK |
| `uv run ruff format --check .` | propre | « 138 files already formatted » | OK |
| `uv run pytest -q -rs` (sans `WAVESTACK_TEST_*`) | 934 réussis, 3 sautés, 6 désélectionnés | **934 passed, 3 skipped, 6 deselected in 706.02s (0:11:46)** | OK |
| Raisons des 3 sauts | 2 × « Windows refuse de remplacer… », 1 × « simulation sans /proc… » | `test_rag_rerank.py:579` et `test_rag_review.py:340` : « Windows refuse de remplacer un fichier qu'une connexion tient ouvert » ; `test_rag_review.py:503` : « simulation sans /proc : sous Windows, le système applique ses règles » | OK |
| Contrôle ciblé (`-rA -k …`) | variantes `[connection-closed-first]`, test hors ligne de Headroom et tests Windows réussis | réussis : `test_an_index_replaced_with_the_reranker_loaded_closes_it[connection-closed-first]`, `test_an_index_replaced_during_the_session_is_read_again[connection-closed-first]`, `test_headroom_makes_no_network_attempt_at_import_nor_compression`, `test_guard_blocks_under_proactor_event_loop`, `test_guard_blocks_the_real_mcp_client_under_proactor_event_loop` | OK |
| `WAVESTACK_TEST_GGUF` = 2B, `WAVESTACK_TEST_MODELS_DIR` = dossier des modèles ; `uv run pytest -q -m model -rA --durations=0` | 6 réussis | **6 passed, 937 deselected in 80.92s**. Durées : `test_real_gguf_reuses_its_cache_between_two_turns` 34,6 s ; `test_probe_real_gguf_loads_successfully` 22,1 s ; `test_real_gguf_state_restored_after_a_divergent_prompt` 6,8 s ; embedding 5,5 s ; reranker 4,6 s ; `test_real_gguf_passes_checks_4_and_6` 3,7 s | OK |
| Preuves du lot A | second tour : moteur n'évalue que les nouveaux tokens (±1) ; état restauré sur le modèle hybride | les deux tests réussissent (les assertions sont `abs(evaluated_tokens − nouveaux) ≤ 1`, sans `prefix_not_reused`). Valeurs chiffrées relevées à l'étape 5 (le test ne les affiche pas) | OK |

### Test `fits` avec le vrai tokenizer (section 4.4)

`uv run pytest -s -rA tests/test_program.py -k fits` (dans le même terminal, `WAVESTACK_TEST_GGUF`
posée) :

```
>           assert measured["mcp_full"][0] > 2800, measured["mcp_full"]
E           AssertionError: (2572, 3584, 52)
E           assert 2572 > 2800
tests\test_program.py:409: AssertionError
FAILED tests/test_program.py::test_every_scenario_fits_the_default_window_with_its_first_prompt
================ 1 failed, 11 deselected, 2 warnings in 13.80s ================
```

**KO**, mais sur le garde-fou final, pas sur un débordement : la boucle a vérifié chaque
scénario (verdict `None` pour tous) avant d'échouer sur l'assertion « la documentation complète,
3 204 tokens sur le PC cible, n'est pas sous-estimée ». Pour lire le tableau que le test
n'imprime qu'en cas de succès, rejeu par un fichier jetable hors dépôt
(`<scratchpad>\fitsprobe\test_fits_probe.py`, qui appelle le test et lit ses variables locales
après l'échec ; `-p conftest` garde le dossier de données isolé) :

```
scénario        utilisé / utilisables  marge  place
  bare_llm          37 / 3584  marge  3547
  reasoning         38 / 2560  marge  2522
  short_memory      37 / 3584  marge  3547
  system_prompt     77 / 3584  marge  3507
  global_memory    254 / 3584  marge  3330
  native_tools     493 / 3584  marge  3091
  network_tools    746 / 3584  marge  2838  1200
  rag             1074 / 3584  marge  2510
  rag_rerank      1074 / 3584  marge  2510
  mcp_full        2572 / 3584  marge  1012  52
  mcp_lazy        1458 / 3584  marge  2126  52
  skills          1613 / 3584  marge  1971
  caveman          473 / 3584  marge  3111
  hooks            224 / 3584  marge  3360
  subagent        1651 / 3584  marge  1933
  compression     1454 / 3584  marge  2130
  data_flows       702 / 3584  marge  2882  1200
  soc              159 / 3584  marge  3425
  iam              836 / 3584  marge  2748  1200
  sovereignty      490 / 3584  marge  3094  1200
  outils de datagouv : instantané
  outils de mslearn : instantané
```

Cause probable : le test démarre la session sur un modèle cloud (`boot_cloud(mistral)`) et
compte avec le tokenizer du GGUF le texte des segments **du rendu chat**. Le 3 204 de référence
a été lu dans la jauge **en mode local**, où le gabarit Qwen3.5 écrit les enveloppes et la
description des outils (bloc `<tools>` en JSON) : plus long. Le seuil 2 800 a donc été calibré
sur une autre mesure que celle que le test fait avec le vrai tokenizer (à 2 car./token, le test
passe sous Linux). À confirmer à l'étape 5 en lisant la jauge de `mcp_full` en mode local.
Avertissement annexe, sans effet sur le verdict : `UnicodeEncodeError: 'charmap' codec can't
encode character 'Ċ'` dans le rappel de journal de llama-cpp-python (console cp1252).

### Parcours E2E

| Commande | Attendu (guide) | Obtenu | Statut |
|---|---|---|---|
| `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` (Chromium déjà installé : `chromium-1194`, `chromium-1208`) | 0 échec sur ce poste connecté ; ≈ 356 avec l'extra | **356 vérifications réussies, 0 en échec, 0 anomalies connues**, en 291 s, code 0. `public_holidays` : « Service injoignable (ConnectError) : le poste n'a pas accès à calendrier.api.gouv.fr. » (réseau coupé par le lanceur, comme prévu). 5 `harness_error` voulus par le parcours (429, 500, flux cassé, 401, téléchargement d'embedding) ; console du navigateur : 4 `Failed to load resource` (ERR_FAILED, ERR_CONNECTION_RESET, 2 × ERR_CONNECTION_REFUSED), attendus avec le réseau coupé | OK |
| `git restore tools/e2e/screenshots` | arbre propre | 25 captures réécrites, restaurées ; reste seulement ce fichier de résultats | OK |

## Section 4.1 : bancs de la story 12 (WaveStack arrêté)

Les JSON sont écrits dans le dossier temporaire de la session (et non à la racine du dépôt,
pour garder l'arbre propre) : `bench-headroom.json`, `bench-embed.json`.

| Commande | Attendu (guide) | Obtenu | Statut |
|---|---|---|---|
| `uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom --json` | `verdict.retained` True ; `network` True sans `openaipublic.blob.core.windows.net` ; `no_torch` True ; `configured.rss_added_mb` ≤ 300 | 18 s, code 0. `retained` **True**, `rss_added_method` `pic`, `configured.rss_added_mb` **84** (pic 121 Mo, 37 Mo avant import ; comptage `gpt-4`). Critères : `network` True (« 0 hôte(s) Python, natif non observé (strace absent) »), `no_torch` True, `budget` True (« 84 Mo ajoutés au pic »), `license` True (64 paquets), `adoption` True. `configured.attempts` vide. `openaipublic.blob.core.windows.net` n'apparaît que dans la variante témoin `naive` (sans les variables hors ligne), ce qui est le contrôle négatif voulu | OK |
| `uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download --json` | `rss_added_method` `pic` ; granite retenu, recall@1 ≥ 0,75, ≈ 428 Mo ≤ 600, pooling 2 ; bge-m3 ≈ 731 et Qwen3-Embedding ≈ 900 au-dessus de 600 ; reranker MRR égal ou meilleur, ≈ 736 ≤ 800 | 98 s, code 0 (cache du banc déjà présent, 2 056 Mo). `rss_added_method` **pic** ; verdict : embedding `granite107m_q8`, reranker `bgererank_m3_q4km`, tous deux « mesuré ». Tableau ci-dessous | OK |
| `uv run python tools/bench/story12_bench.py embed --only e5small_q8` | « Candidat inconnu : e5small_q8 (retiré…) », code 2 | « Candidat inconnu : e5small_q8 (retiré des candidats : ne se charge pas avec llama-cpp-python 0.3.35 (PC cible, 2026-09-27)) », code 2 | OK |

| id | rôle | recall@1 | MRR | RSS ajoutée au pic (Mo) | pooling GGUF |
|---|---|---|---|---|---|
| granite107m_q8 | embedding | 0,9 | 0,95 | 428 | 2 (CLS) |
| bgem3_q4km | embedding | 1,0 | 1,0 | 731 | 2 |
| qwen3emb06_q8 | embedding | 1,0 | 1,0 | 899 | 3 |
| bgererank_m3_q4km | reranker | 0,9 | 0,95 | 736 | — |
| fe_minilm_multi | embedding | 0,9 | 0,95 | 542 | — |
| fe_mmarco_rerank | reranker | 0,9 | 0,95 | 404 | — |

**Règle « nettement »** (écart de plus de 20 % ou de plus de 50 Mo ; nouvelle valeur = mesure
+ 30 %, arrondie à la dizaine). Valeurs **proposées, non écrites** :
- `measured_rss_mb` de l'embedding : 430 → mesure 428 (−0,5 %) : inchangé.
- `measured_rss_mb` du reranker : 740 → mesure 736 (−0,5 %) : inchangé.
- `[compression] cost_mb` : 130 → mesure 84, écart de 46 Mo (sous 50) mais de 35 % (au-delà
  de 20 %) : **nettement**. Proposition : 84 × 1,3 = 109,2, soit **110**.

## Étape 5 : mesures sans interface (script jetable)

Script `<scratchpad>\measure_session.py`, hors dépôt : il pilote une `AppSession` dans le
processus, avec le vrai `Qwen3.5-2B-Q4_K_M.gguf` sur le moteur intégré, abonne un relevé au
journal (`model_call_ended`, `prefix_not_reused`, `reasoning_cut`…) et échantillonne la RSS
(processus + enfants) et la charge CPU du poste. `WAVESTACK_DATA_DIR` pointe vers une copie
jetable du dossier de données (`settings.json`, `memory.json`, et `models` en jonction vers le
vrai dossier) : le dossier réel n'est pas modifié. WaveStack arrêté, llama-server jamais lancé.
Journaux d'événements complets : `<scratchpad>\events-*.jsonl`.

Conditions : Outlook et Teams fermés. **Edge** : ouvert en arrière-plan depuis 20:58:59
(≈ 900 Mo) pendant les mesures jusqu'à 21:45 ; fermé par l'utilisateur à 21:47, il s'est
relancé seul à 21:47:59 avec `--no-startup-window` (≈ 1 Go, démarrage anticipé du poste). Les
mesures suivantes sont donc faites avec Edge en arrière-plan.

### Lot A : deux tours de `native_tools` (critère : `prompt_ms` du 1er appel du 2e tour < 3 s)

Démarrage du 2B : 4,3 s, RSS 1 258 Mo. Jauge avant envoi : 724 / 3 584.

| Tour | Appel | `prompt_ms` | `prompt_tokens` | `evaluated_tokens` | sortie | Remarque |
|---|---|---|---|---|---|---|
| t1 « Quelle heure est-il ? » | 1 (appel de `get_datetime`) | 24 421 | 729 | 729 | 13 | premier tour : tout le contexte |
| t1 | 2 (réponse) | 1 774 | 788 | 46 | 24 | « Il est actuellement dimanche 27 septembre 2026 à 21:31:47. » |
| t2 « Combien font 1234 multiplié par 5678 ? » | 1 (appel de `calculator`) | **1 117** | 844 | **32** | 33 | aucun `prefix_not_reused` |
| t2 | 2 (réponse) | 859 | 902 | 25 | 25 | « 1234 multiplié par 5678 donne 7 006 652. » |

Tour 1 : 30,4 s ; tour 2 : 8,8 s. Pic RSS : 2 052 Mo. **OK** : 1,1 s pour 3 s visées (23 s le
2026-09-27) ; le moteur n'évalue que 32 tokens sur 844.

Même paire que `test_real_gguf_reuses_its_cache_between_two_turns`, après « Vider la
conversation » : t1 relit tout (`prefix_not_reused`, cause `reset`, 729 tokens, attendu après
un vidage) ; **t2 « Et quel jour sommes-nous ? » : `evaluated_tokens` 21**, `prompt_ms` 730,
`prompt_tokens` 829, soit exactement 829 − (788 + 20) = 21 nouveaux tokens.

### Jauge de `mcp_full` en mode local (contre-mesure de l'échec du test `fits`)

`mcp_full` (serveurs `local` et `datagouv` connectés, `ok`) : **3 204 / 3 584**, identique au
relevé du 2026-09-27. `mcp_lazy` : 1 699 / 3 584. Le test `fits` compte 2 572 et 1 458 : il
sous-estime le mode local d'environ 20 % (rendu chat compté avec le tokenizer local). La
cause probable de l'échec du test `fits` est confirmée.

### Lot C : prompt du train (critère : une réponse en moins de 120 s)

| Passage | Budget | Durée du tour | Raisonnement coupé | Sortie | Débit | Réponse | Statut |
|---|---|---|---|---|---|---|---|
| 1 (Edge en arrière-plan) | 1 024 | **134,2 s** | oui, à 1 024 (réserve de réponse 509) | 1 136 tokens | 9 tokens/s | 17:50, juste | KO |
| 2 (budget posé dans le `settings.json` jetable) | 768 | 331,3 s | oui, à 769 | 955 | 3 tokens/s | 17 h 50 | invalide : poste chargé par un autre programme |
| 3 (rejeu, Edge relancé en arrière-plan) | 768 | **111,2 s** | oui, à 768 (réserve 765) | 974 | 9 tokens/s | 17 h 50, juste | OK (marge de 9 s) |
| 4 (rejeu, clé retirée) | 1 024 | **126,8 s** | oui, à 1 024 | 1 186 | 9 tokens/s | 17 h 50, juste | KO |

Charge CPU pendant les passages 3 et 4 : 74 % et 67 % au total, dont 26 % et 17 % pris par
d'autres programmes. Premier token : 2 s ; réflexion ≈ 9,5 tokens/s (et non 11 comme supposé
au lot C) : 1 024 tokens prennent ≈ 108 s, plus ≈ 13 à 22 s de réponse. Un seul « Appel au
modèle terminé » par tour, comme attendu.

Second message après le passage 1, « Et avec 10 minutes de retard ? » : `prefix_not_reused`,
cause `history`, 3 tokens communs sur 1 188 : le scénario Raisonnement n'active que la brique
Raisonnement, **sans la mémoire courte**, donc l'échange précédent n'est pas renvoyé (le
message du harnais le dit : « mémoire courte éteinte »). Le coût est nul (19 tokens), mais
l'attendu de la section 5.3 du guide (« aucune étape Préfixe non réutilisé ») ne peut pas être
tenu dans ce scénario : écart du guide, pas du code. Le modèle répond sans contexte
(« Pourriez-vous préciser dans quel contexte… »), après une réflexion elle aussi coupée à
1 024 : tour de 165,9 s.

### Lot A : deux tours avec le raisonnement (scénario « Mémoire courte », brique Raisonnement allumée)

| Tour | `prompt_ms` | `prompt_tokens` | `evaluated_tokens` | Raisonnement | Durée | Réponse |
|---|---|---|---|---|---|---|
| t1 « Bonjour, je m'appelle Camille. » | 1 134 | 19 | 23 | coupé à 1 024 | 115,8 s | « Bonjour ! Je suis ravi de vous rencontrer… » |
| t2 « Comment je m'appelle ? » | **681** | 1 082 | **22** | coupé à 1 024 | 113,2 s | « Je suis une intelligence artificielle, donc je n'ai pas de nom humain… » |

Jauge avant t2 : 1 076 / 2 560 (la réflexion du t1 est comptée dans l'historique, attendu).
**Aucun `prefix_not_reused` au t2** : les blancs autour de `</think>` écrits par le harnais
prolongent bien le cache (l'hypothèse de la section 5.1 ne se réalise pas). **OK.**
Constat pédagogique, pas un défaut du lot A : même sur « Bonjour », la réflexion du 2B va
jusqu'au budget, donc chaque tour avec raisonnement dure ≈ 115 s ; et au t2 le modèle ne
retrouve pas le prénom (sa réflexion, coupée, hésitait encore).

### Lot A : sous-agent, RAG éteint (critère : premier token de chaque quiz < 15 s)

Scénario « Sous-agent », brique RAG éteinte avant le premier prompt. Jauge avant envoi :
1 320 / 3 584. Le modèle délègue de lui-même (`delegate`, tâche « Lis le fichier
guide_harnais.md et rends-en un résumé en cinq points. ») : pas d'action forcée.

| Étape | Contexte | `prompt_ms` | `prompt_tokens` | `evaluated_tokens` | Sortie |
|---|---|---|---|---|---|
| appel de `delegate` | main | 46 136 | 1 365 | 1 365 | 43 |
| appel de `read_file` | sub1 | 12 846 | 419 | 419 | 28 |
| résumé du guide | sub1 | 63 376 | 2 293 | 1 846 | 245 |
| présentation du résumé (après restauration) | main | 8 365 | 1 671 | **263** | 234 |
| quiz 1 (bornes) | main | **4 057** | 2 007 | 102 | 276 |
| quiz 2 (économie) | main | **3 368** | 2 383 | 100 | 202 |
| quiz 3 (débordement) | main | **3 575** | 2 684 | 99 | 186 |

`subagent_ended` : `state_saved_bytes` **37 537 394 (35,8 Mo)**, `state_restore_ms` **20**,
`context_tokens` 2 293, `kept_tokens` 1 828, `result_tokens` 245, `saved_tokens` 1 583, 2
appels, 106,7 s. **Aucun `prefix_not_reused`** sur toute la phase. Tour de délégation :
191,6 s ; quiz : 36,7 s, 25,4 s, 24,5 s. Pic RSS 2 209 Mo. **OK** : 3,4 à 4,1 s pour 15 s
visées (68 à 99 s le 2026-09-27).

### Sous-agent, RAG allumé (tel que livré ; consigné pour D5, lot H)

Jauge avant envoi : 1 895 / 3 584. Délégation spontanée ; `state_saved_bytes` de `sub1`
44 136 626 (42,1 Mo), restauré en 13 ms ; au retour, 315 tokens évalués sur 2 259.

| Tour | 1er appel : `prompt_ms` | évalués / prompt | `prefix_not_reused` | Durée du tour |
|---|---|---|---|---|
| délégation | 69 787 | 1 900 / 1 900 | — (premier tour) | 223,1 s |
| quiz 1 | **86 670** | 2 566 / 2 566 | `history`, 1 312 communs sur 2 511 | 122,0 s |
| quiz 2 | **91 461** | 2 838 / 2 838 | `history`, 2 049 communs sur 2 689 | 212,4 s |
| quiz 3 | **114 026** | 3 323 / 3 323 | `history` | 285,7 s |

Comme annoncé par la décision par défaut du lot A, chaque tour relit tout le contexte (extraits
RAG retirés de l'historique) : 87 à 114 s, soit pire que le 2026-09-27 (68 à 99 s), le
contexte étant plus long. Le critère de 15 s n'est pas tenu RAG allumé, par conception (D5).
Constat pour le lot H : RAG allumé, **le modèle redélègue chaque quiz** (« Réponds à la
question du quiz… ») au lieu de répondre avec le résumé ; les sous-agents, sans la
conversation, lisent `notes_reunion.txt` ou demandent la question (« Je ne vois pas de quiz dans
les fichiers disponibles… »). Au quiz 2, trois délégations successives. Pic RSS 2 698 Mo. RAG
éteint, le modèle répondait directement.

### Lot B : scénarios qui débordaient (critère : aboutir sans débordement avec le 2B)

Phase `scen:` du script : chaque scénario lancé, puis ses prompts dans l'ordre (réseau réel du
poste ; `data_flows` : brique MCP et serveurs `local` + `datagouv` activés à la main, comme sa
consigne). Aucun `context_overflow` sur toute la phase.

| Scénario, prompt | Jauge avant envoi | Outils appelés | Borne (`tool_ended.truncated`) | Dernier prompt | Durée | Statut |
|---|---|---|---|---|---|---|
| `mcp_lazy` 1 « Que veut dire MCP ? » | 1 699 / 3 584 | aucun | — | 1 640 | 62,2 s | OK, mais réponse inventée (« Machine Learning Control Platform ») |
| `mcp_lazy` 2 « qualité de l'air » | 1 772 / 3 584 | aucun (`prefix_not_reused`, `history`) | — | 1 642 | 69,7 s | OK, répond depuis les extraits RAG d'Exemplia |
| `sovereignty` 1 (data.gouv.fr) | 675 / 3 584 | `load_tool_doc`, puis rien | — | 1 073 | 58,6 s | OK, mais liste inventée sans recherche (H5) |
| `sovereignty` 2 (Microsoft Learn) | 1 269 / 3 584 | `microsoft_docs_search` (+ `load_tool_doc`) | **1 153 tokens sur 4 352** | 2 920 | 157,1 s | OK |
| `iam` 1 (MFA) | 1 062 / 3 584 | aucun | — | 1 094 | 58,9 s | OK, sans Microsoft Learn |
| `iam` 2 (PIM) | 1 320 / 3 584 | aucun | — | 1 348 | 57,1 s | OK ; sortie coupée à 512 (`output_truncated`, `limit`) |
| `data_flows` 1 (qualité de l'air) | 934 / 3 584 | `load_tool_doc`, `datagouv__search_datasets` | **1 141 tokens sur 2 438** | 2 607 | 142,8 s | OK, vrais jeux de données |

**OK sur le critère** : les quatre scénarios aboutissent sans débordement (le 2026-09-27 :
`mcp_lazy` 4 680, `data_flows` 5 605, `iam` 6 864). Les deux résultats réellement longs sont
bornés sous 1 200 tokens. Mais le 2B n'a pas appelé d'outil dans `mcp_lazy` ni dans `iam` : la
borne n'y a pas été éprouvée, et la jauge « ≈ 3 380 avant le second prompt de `mcp_lazy` » ne
s'est pas produite (1 772). À rejouer à la main si l'on veut voir la coupe dans ces deux
scénarios (actions forcées).

### Lot D : Wikipédia et outils réseau

`network_tools` 1 : `public_holidays` (2026), `ok` en 201 ms, liste juste. `network_tools` 2 :
`wikipedia_summary` (`Mont-Saint-Michel`), **`ok` en 165 ms**, résumé de l'article (« Le
Mont-Saint-Michel est une commune française située dans la Manche en Normandie… ») : plus de
403. **OK.** L'User-Agent n'est pas visible dans le journal : à lire dans « Données sortantes »
à la main. Au 2e prompt, 29 tokens évalués sur 1 452 (cache réutilisé).

### `soc` (cause d'un débordement)

Prompt 1 : le modèle demande `alerts_siem.log` (faute de frappe), refus clair « Fichier absent :
« alerts_siem.log ». Fichiers disponibles : alertes_siem.log, … », puis il propose
`journal_serveur.log`. Prompt 2 : lecture de `journal_serveur.log`, prompt de 2 684 tokens,
**pas de débordement** cette fois (3 586 / 3 584 le 2026-09-27), donc la « cause juste » n'a
pas pu être vérifiée ; H1 n'a pas été sollicité. Constat pour le lot H (D6) : le scénario ne
se déroule pas comme prévu avec le 2B.

### Lot E : sonde du 4B et refus par le budget de 4 096 Mo

Geste reproduit : 2B actif (scénario « LLM nu », un tour, brique RAG éteinte), puis
`DiagnosticSession.select_model(4B, hot=True)` et `DiagnosticSession.switch(...)`, le chemin
de l'intention `select_model` de l'interface.

- Entrée du 4B avant : ancienne sonde (`rss_bytes` 2 880 712 704, sans `probe_version`) : le
  contrôle préalable avec l'ancienne estimation laisse passer, le 2B est libéré, le 4B resondé.
- Durée : libération + sonde **≈ 53 s** (16,9 s → 70,4 s), retour au 2B 2,9 s, total
  `duration_ms` 56 877. Pic RSS (processus + enfants) 3 951 Mo.
- Entrée du 4B après : `probe_version` 2, `rss_bytes` **4 468 621 312 (4 262 Mo)**,
  `kv_bytes_per_token` 131 072, `probe_window` 4 096, `rss_eval_tokens` 512.
- Message (`harness_error`) : « Le modèle dépasse le budget mémoire une fois mesuré. » ; cause :
  « **Changement refusé : Qwen3.5-4B-Q4_K_M demande environ 4,4 Go ; WaveStack occupe 118 Mo
  sans le modèle actif, pour un budget de 4,0 Go.** Choisissez un modèle plus petit. » ; effet :
  « Retour au modèle précédent : Qwen3.5-2B-Q4_K_M. »
- `model_load_ended` : `status` `restored`, « Qwen3.5-2B-Q4_K_M est de nouveau actif ».

**OK** : 4B refusé par le budget de 4 096 Mo (N5), mémoire de WaveStack en Mo (118 Mo, pas
« 0,0 Go »), 2B de nouveau actif. Écart mineur : la sonde du 4B prend ≈ 53 s, au-delà des
15 à 30 s annoncés par le rapport (lot E).


### Nettoyage

Jonction `<scratchpad>\wsdata\models` retirée (`cmd /c rmdir`, le dossier réel des modèles est
intact). Dossier réel : seul `settings.json` a été réécrit, à 21:00:14, par la sonde du 2B au
premier lancement ; `memory.json` est inchangé. L'entrée du 4B y reste donc l'ancienne : le
choisir dans l'interface déclenchera la nouvelle sonde (≈ 53 s), ce qui laisse le temps de
tester « Arrêter » (E4). Aucun commit, aucun push. Mesures finies à 22:45 environ.

## Synthèse

### a) Par lot : vérifié automatiquement

| Lot | Vérification | Mesure | Critère du plan | Statut |
|---|---|---|---|---|
| A | tests `model` (cache entre deux tours, état restauré sur le modèle hybride) | 6 réussis ; 2e tour : 21 tokens évalués = nouveaux tokens exacts | ±1 | OK |
| A | 2e tour de `native_tools`, 1er appel | `prompt_ms` 1 117, 32 évalués sur 844, pas de relecture | < 3 s | OK |
| A | deux tours avec raisonnement (Mémoire courte) | 2e tour : 681 ms, 22 évalués sur 1 082, pas de relecture | pas de « Préfixe non réutilisé » | OK |
| A | quiz du sous-agent, RAG éteint | 4,1 / 3,4 / 3,6 s ; état 35,8 Mo restauré en 20 ms | < 15 s | OK |
| A | quiz du sous-agent, RAG allumé | 86,7 / 91,5 / 114,0 s, relecture `history` à chaque tour | (D5 : hors critère par décision) | consigné |
| B | `mcp_lazy`, `sovereignty`, `iam`, `data_flows` | aucun débordement ; bornes 1 153 / 4 352 et 1 141 / 2 438 | aboutir sans débordement ; N ≤ 1 200 | OK (borne non éprouvée dans `mcp_lazy` et `iam` : pas d'appel d'outil) |
| B | test `fits` avec le tokenizer du 2B | tous les scénarios tiennent ; garde-fou `mcp_full` 2 572 ≤ 2 800 | test vert | KO (défaut du test) |
| B | cause juste d'un débordement (`soc`) | pas de débordement cette fois (2 684) | message « résultats d'outils » | non fait |
| C | prompt du train, budget 1 024 | 134,2 s et 126,8 s, coupe à 1 024, 17 h 50 juste | < 120 s | KO |
| C | prompt du train, budget 768 (réglage jetable) | 111,2 s, coupe à 768, 17 h 50 juste | < 120 s | OK |
| D | Wikipédia | `wikipedia_summary` `ok` en 165 ms, contenu de l'article | plus de 403 | OK |
| D | E2E sur le poste connecté | 356 réussies, 0 échec | 0 échec | OK |
| E | sonde du 2B au lancement | ≈ 33 s ; `probe_version` 2, RSS 1 931 Mo | entrée complète | OK |
| E | 4B : sonde et refus | sonde ≈ 53 s ; RSS 4 262 Mo ; « demande environ 4,4 Go ; WaveStack occupe 118 Mo… budget de 4,0 Go » ; 2B restauré | refus par 4 096 Mo, Mo sous 1 Go | OK |
| F | banc `headroom` | RETENU ; 84 Mo au pic ; aucune tentative réseau (`configured`) | ≤ 300 Mo, réseau `True` | OK |
| F | banc `embed` | granite 428 Mo, reranker 736 Mo ; `e5small_q8` refusé code 2 | ≤ 600 / ≤ 800 | OK |
| F | test hors ligne de Headroom | réussi | réussi | OK |
| G | `pytest -q` sous Windows | 934 / 3 sautés / 6 désélectionnés, raisons conformes | 934 / 3 | OK |
| G | tests `model` du RAG | réussis (5,5 s et 4,6 s) | réussis | OK |
| I | nombres du guide (934 / 3, 6 tests `model`, 0 échec E2E) | conformes | — | OK |

### b) Tests manuels restants

Ordre du guide (5, puis 6, puis 7), sans ce que le script a couvert. Avant : Outlook et Teams
fermés, Edge quitté depuis la zone de notification (il se relance seul), `uv run wavestack`.

1. **5.1 Mémoire globale figée (N1)** : scénario « Mémoire globale », prompt 1, 2e tour, puis
   « Vider la conversation » et prompt 2, puis modifier et effacer une entrée. Attendu : pas de
   « Préfixe non réutilisé » au 2e tour ; entrée aussitôt dans le tiroir, dans le message
   système seulement après le vidage ; modification appliquée aussitôt. 10 min. Retour : OK/KO,
   capture de Contexte LLM avant et après le vidage.
2. **5.3 Scénario Raisonnement dans l'interface** : carte (« Budget de réflexion : 1 024
   tokens… 512 tokens pour la réponse ») ; prompt du train. Attendu : étape « Raisonnement
   coupé », bulle non vide, un seul « Appel au modèle terminé ». Critère < 120 s (KO mesuré à
   1 024). 5 min. Retour : capture d'Orchestration et durée.
3. **5.4 User-Agent** : « Outils réseau », prompt 2, « Données sortantes ». Attendu : contact
   de `[net] contact` dans l'User-Agent. 3 min. Retour : capture.
4. **5.5 « Arrêter » pendant un chargement (E4)** : brique RAG éteinte, choisir le 4B (sonde
   ≈ 53 s), cliquer « Arrêter » pendant le chronomètre. Attendu : « Arrêt demandé… », puis
   « Chargement arrêté : Qwen3.5-2B-Q4_K_M est de nouveau actif. » Puis rechoisir le 4B jusqu'au
   bout : refus affiché avec 4,4 Go / 118 Mo / 4,0 Go. 6 min. Retour : délai entre le clic et
   l'arrêt, capture du refus.
5. **5.5 E5** : `llama3.2:3b` (Ollama) dans « Outils natifs ». Attendu : encadré « Brique du
   scénario indisponible avec ce modèle : Outils… ». 3 min. Retour : capture.
6. **5.5 E6** : le blob Ollama refusé le 2026-09-27, choisi comme fichier. Attendu : raison en
   français (« llama-cpp-python 0.3.35 ne sait pas charger ce fichier… »), 2B gardé. 2 min.
   Retour : capture. En option, `olmo-3:7b` : ≈ 200 Mo, pas « 0,0 Go ».
7. **5.6 Compression** : l'étape « Compression (Headroom) » garde l'erreur du journal. 5 min.
   Retour : capture.
8. **5.7 Script pendant une session** : un tour du scénario RAG, puis
   `uv run python scripts/build_rag_index.py` dans un 2e terminal. Attendu : « L'index est
   ouvert par un autre programme… », code 1. 3 min. Retour : sortie et `$LASTEXITCODE`.
9. **5.5 E1 llama-server sans `-c`**, puis **`-c 4096` et N6** (WaveStack arrêté sur un modèle
   cloud ou petit avant de lancer llama-server ; jamais le 2B chargé en même temps). Attendu :
   ≈ 5 Go et l'avertissement « relancez-le avec `-c 4096` », puis plus d'avertissement et une
   RSS de llama-server proche du diagnostic. Pour N6 : 2e tour de `native_tools` et quiz du
   sous-agent, RAG éteint puis allumé. 30 min. Retour : les deux RSS, le texte de
   l'avertissement, les `prompt_ms`.
10. **M1** (LLM nu, raisonnement replié et « Afficher le raisonnement », « Comparer », mémoire
    courte, prompt système pirate, tiroir et « Réinitialiser » de la mémoire globale, D11 avec
    mémoire pleine). 30 min. Retour : OK/KO par point, jauge D11.
11. **M2** : Orchestration (demande, exécution, réinjection), nœud en zone Réseau, « Données
    sortantes ». 10 min. Retour : OK/KO.
12. **M3 RAG et Reranking** : Exemplia inconnue puis 14 caractères ; « Recherche RAG » ;
    « 3 gardés sur 8 », un rang qui change, case décochée. 20 min. Retour : durée des 8 passes,
    RSS ajoutée (≤ 800 Mo).
13. **M4** : `mcp_full` (jauge 3 204 déjà mesurée) : envoyer le prompt, durée du tour ; Lazy
    loading : chargement de la documentation, et une action forcée data.gouv.fr pour voir
    « Résultat tronqué… » (le 2B n'appelle pas d'outil de lui-même). 15 min. Retour : durée,
    capture de la coupe.
14. **M5** : Skills (outil appelé, durée sans Edge : H2, H6), Caveman, Hooks H1. 20 min.
    Retour : outil, durée, OK/KO.
15. **M6** : sous-agent (bascule principal / `sub1`, second robot, taille de `sub1`) ;
    Compression (avant / après, perte au 2e prompt, « Retrieve more », H4). 20 min. Retour :
    captures, tokens avant / après.
16. **Transverses** : Données (seul data.gouv.fr franchit la frontière), SOC (« Journal
    d'audit » ; le modèle trouve-t-il `alertes_siem.log`, H1 et escalade), IAM, Souveraineté
    (deux flux), NFR-2 toutes briques. 25 min. Retour : pic RSS, comportements.
17. **Modèles** : changement à chaud vers un modèle qui tient (chronomètre, conversation
    gardée, rejeu, « Comparer ») ; Ollama `qwen3.5:2b` (tour, « transparence réduite »,
    `ollama ps` vide) ; Groq et Mistral si clés ; relance. 30 min. Retour : OK/KO, deux comptes
    de l'alerte.
18. **Section 7** : D2 (reranker renommé), D3 (serveurs seuls), D9 (Mistral `resend`). 25 min.
    Retour : OK/KO et message affiché, code d'erreur pour D9.

Total estimé : ≈ 4 h 30.

### c) Décisions

- **N6** : garder le moteur intégré par défaut. Les critères du lot A sont tenus sans
  llama-server (1,1 s ; 3,4 à 4,1 s). Reste à mesurer llama-server `-c 4096` pour comparer,
  surtout RAG allumé (87 à 114 s par quiz avec le moteur intégré).
- **Budget de raisonnement** : 1 024 ne tient pas (127 à 134 s) ; 768 tient (111 s, marge de
  9 s, avec 17 à 26 % du CPU pris par d'autres programmes). Proposition : 768, ou 640 pour de
  la marge.
- **F2** : `[compression] cost_mb` 130 → proposition **110** (84 Mo mesurés, écart de 35 %).
  `measured_rss_mb` 430 et 740 inchangés.
- **D2, D3, D9** : aucune mesure possible sans l'interface, ni sans quota Mistral.

### d) Anomalies

1. Test `fits` avec `WAVESTACK_TEST_GGUF` : échec du garde-fou `mcp_full` > 2 800 (2 572).
   Cause : le test compte le rendu **chat** (session cloud) avec le tokenizer local ; la jauge
   locale réelle vaut 3 204 (mesurée). Le test sous-estime le mode local d'environ 20 %, donc
   son verdict est trop indulgent pour le 2B.
2. Guide 5.3 : « aucune étape Préfixe non réutilisé » au second message du scénario
   Raisonnement est impossible, car la mémoire courte y est éteinte (cause `history`).
3. Lot C : débit de réflexion ≈ 9,5 tokens/s et non 11 ; le budget de 1 024 dépasse 120 s.
   Le 2B va au budget même sur « Bonjour » : chaque tour avec raisonnement dure ≈ 115 s.
4. Sous-agent RAG allumé : relecture complète à chaque quiz (87 à 114 s), et le modèle
   redélègue chaque quiz avec une tâche sans contexte (lot H, D5).
5. Lazy loading : charger une documentation change le message système, donc le tour suivant
   relit tout (`sovereignty` 2 : cause `system`, 1 259 tokens relus, 46,7 s).
6. Premiers tours des scénarios chargés : 1er appel à 46 s (`subagent`) et 56 s (`mcp_lazy`)
   à ≈ 30 tokens/s, au-delà de la cible NFR-1 de 30 s au plus chargé.
7. Sonde du 4B ≈ 53 s, contre 15 à 30 s annoncés au lot E.
8. Edge se relance seul en arrière-plan (`--no-startup-window`, ≈ 1 Go) après fermeture :
   le guide devrait le signaler pour les mesures.
9. `UnicodeEncodeError` (cp1252) dans le rappel de journal de llama-cpp-python pendant le test
   `fits` : cosmétique.
10. Comportement du 2B pour le lot H : `mcp_lazy` et `iam` sans appel d'outil (réponse
    inventée sur MCP) ; `sovereignty` 1 sans recherche après `load_tool_doc` (H5) ; `soc` :
    nom de fichier mal orthographié, pas de débordement ni d'escalade (D6).
