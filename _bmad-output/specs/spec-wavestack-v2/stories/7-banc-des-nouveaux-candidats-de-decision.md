---
title: 'V2 (7/7) : banc des nouveaux candidats de décision'
type: 'feature'
created: '2026-10-03'
status: 'done'
baseline_commit: 'b53b054dd145bcbd3a2713282f269955606a7fcb'
route: 'dispatch'
review_loop_iteration: 0
size: 'S à M, plus un relevé manuel sur le PC cible'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/decision-model-candidates.md'
  - '{project-root}/_bmad-output/implementation-artifacts/rapport-test-prealable-modeles-de-decision.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

> Permise avant le pilote, comme la story 6 : c'est un banc, pas une fonction (décision d'Anaël du 2026-10-03). Elle ne livre aucune fonction.

## Intent

**Problème :** Le relevé du 2026-10-03 retient `deberta_xsmall` à l'échelon 2. Mais les DeBERTa sont entraînés en anglais, et face aux prompts français leur accord indicatif sur la spécialité reste faible (7 à 11/20). Trois candidats sont arrivés depuis, et aucun n'a été mesuré :
- Decision 2.0 Kai 0.6B, successeur de Decision 1.0 ;
- mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 ;
- multilingual-MiniLMv2-L6-mnli-xnli.

**Approche :** CAP-6. Le banc de la story 6 s'étend à ces trois candidats, avec les mêmes critères, seuils, prompts et enfant de mesure. Leur verdict s'ajoute au rapport du test préalable. Ollama 0.35 et ses modèles de décision sont hors de cette story (décision d'Anaël du 2026-10-03 : story 8 à part, sur tev1 0.8B seul).

## Boundaries & Constraints

**Always :**
- Mêmes critères et seuils que la story 6 (`decision-model-candidates.md`) :
  - pic de RSS ≤ 4 096 Mo avec le SLM chargé, et total avec le RAG V1 donné à part ;
  - latence médiane ≤ 1 000 ms et maximum ≤ 3 000 ms ;
  - aucune tentative réseau ;
  - licences, torch, commit et versions consignés.
- mDeBERTa et MiniLM passent par le décodage NLI existant (`nli_onnx`) : ONNX Runtime et `tokenizers`, sans torch. Leurs fichiers ONNX :
  - mDeBERTa : `onnx/model_quantized.onnx`, 339 Mo ;
  - MiniLM : `onnx/model.onnx`, 428 Mo. MiniLM est une architecture XLM-R, sans `token_type_ids`.
  - Les deux modèles ont trois classes NLI (`entailment`, `neutral`, `contradiction`).
- Decision 2.0 Kai (`vllm-sr/Decision-2.0-Kai-0.6B`) :
  - Avant toute exécution, l'agent relit le code fourni par le dépôt au commit téléchargé (`modeling_decision2.py`, `pipeline_decision2.py`, `configuration_decision2.py`, `decision2/`) et consigne son sha. La mesure tourne ensuite hors ligne, sur ce commit.
  - Interface : `system_one` avec une question `choice` par tâche, dont les critères sont les textes de `TASKS`.
  - Verdict au mieux « à surveiller » : torch et `trust_remote_code`.
- Garde-fou de mémoire (décision d'Anaël du 2026-10-03) : un fil de l'enfant lit la RSS toutes les 0,5 s. Au-delà de 4 096 Mo, il écrit son JSON (RSS à l'arrêt, tentatives réseau) et arrête le processus. Verdict « écarté (RAM) », sans latence ni accord. Vaut pour tous les candidats.
- Les verdicts, mesures, commits et versions vont dans `rapport-test-prealable-modeles-de-decision.md`, avec le PC et la date du relevé. `decision-model-candidates.md` se met ensuite à jour par un passage de bmad-spec.

**Never :**
- Une dépendance ajoutée au projet, ou un fichier modifié sous `src/wavestack/`.
- Exécuter le code distant de Decision 2.0 sans l'avoir relu et épinglé.
- Dupliquer le banc : on étend `v2s6_decision_bench.py` et son test.
- Plus d'une mesure à la fois sur le PC cible : il est partagé, avec 16 Go.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Sortie attendue |
|---|---|---|
| Encodeur multilingue mesuré | `measure mdeberta` ou `measure minilm_multi`, avec `--download` et `--slm` | Mesures et verdict, comme `deberta_xsmall` |
| Modèle ONNX sans `token_type_ids` | MiniLM (XLM-R) | Entrées filtrées par les noms de la session, sans erreur |
| Decision 2.0 mesuré | `measure decision20` avec le commit relu | Mesures ; verdict « à surveiller » au mieux (torch, `trust_remote_code`) |
| Commit de Decision 2.0 différent de celui relu | Instantané présent ≠ sha consigné | Pas de mesure ; statut « code non relu à ce commit » |
| Paquet de mesure absent | Sans les `--with` requis | « non mesuré (absent : <module>) » avec la commande |
| Budget de RAM dépassé en cours de mesure | RSS de l'enfant > 4 096 Mo | Enfant arrêté ; « écarté (RAM) » avec la RSS à l'arrêt |

</frozen-after-approval>

## Code Map

- `tools/bench/v2s6_decision_bench.py` (on l'étend, rien n'est copié) :
  - `Candidate` et `CANDIDATES` : modèle des entrées `deberta_xsmall` et `nvidia`. `doc_name` = début de la première cellule de sa ligne dans `decision-model-candidates.md`.
  - `_load_nli` : réutilisé tel quel pour les deux encodeurs. Il lit déjà `pad_token_id` dans `config.json` (0 pour mDeBERTa, 1 pour MiniLM) et filtre les entrées par `session.get_inputs()`.
  - `_snapshot`, `snapshot_present`, `download_candidate` : suivent `main` avec `allow_patterns` ; à étendre pour une révision épinglée et un instantané complet.
  - `decision_verdict`, critère `pinned` : le libellé dit déjà « pas de trust_remote_code ».
  - `command_for`, `print_list`, `LOADERS`, `_default_runner`, `_measure_child`.
  - `s12` (`story12_bench.py`) : garde, RSS (`_rss_mb`, `_peak_rss_mb`), `_run_child` (lit la dernière ligne JSON de la sortie), `classify_license`, `HEAVY_MODULES`.
- `tests/test_v2s6_decision_bench.py` :
  - Faux injectés (`_FakeLlama`, `monkeypatch.setitem(bench.LOADERS, ...)`, `_measured`, `_status`, `_fake_snapshot`).
  - `test_every_row_of_the_candidates_doc_has_a_candidate` **échoue déjà** sur l'arbre actuel. bmad-spec a porté le document à 12 lignes, dont trois qui commencent par l'id entre accents graves (`` `deberta_xsmall` ``).
- `_bmad-output/implementation-artifacts/rapport-test-prealable-modeles-de-decision.md` : commandes, lignes du tableau, Suite.
- Faits lus sur Hugging Face le 2026-10-03 :
  - **mDeBERTa** (`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`) : MIT. `config.json`, `tokenizer.json` (16 Mo) et `onnx/model_quantized.onnx` à la racine ; `type_vocab_size` 0.
  - **MiniLM** (`MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`) : MIT. `config.json`, `tokenizer.json` (17 Mo) et `onnx/model.onnx` ; `max_position_embeddings` 514.
  - **Decision 2.0 Kai**, commit `881bee413681d80ebeac86afcda8b4138dae516e` (main au 2026-10-02 23:59 UTC). Faits relus par un sous-agent sur le Hub :
    - Apache-2.0 ; `Qwen3Model` de 28 couches, 597 M de paramètres, BF16 et FP32 stockés, tout en FP32 sur CPU ; contexte plafonné à 8 192 ; multilinguisme non annoncé.
    - Chargement : `AutoModel.from_pretrained(<dossier local>, trust_remote_code=True, device="cpu")`. `dtype` accepte seulement `None` ou `"auto"` ; transformers 5.x (testé en 5.17 et 5.18), torch, safetensors, huggingface_hub.
    - `verify_bundle` exige **tous** les fichiers de `MODEL_MANIFEST.json`, PNG et README compris (≈ 1,53 Go) : pas d'`allow_patterns`.
    - Les fichiers `decision2/*.py` sont copiés dans le cache des modules dynamiques de Transformers (`HF_MODULES_CACHE`). `fast.py`, `fast_kernels.py` et `shared_ctx.py` ne servent que sur GPU ou sur option, par `DECISION2_FAST`, `DECISION2_KERNELS` et `DECISION2_GRAPHS`.
    - Appel : `model.system_one(state=<texte>, questions={qid: {"type": "choice", "instructions": <non vide>, "criteria": {clé: texte}}})`. Lecture de la réponse : `["answers"][qid]["choice"]`. Une erreur arrive sous la forme `{"error": "max_length_exceeded" | "invalid_question" | "invalid_model_output"}`.
    - Ni `subprocess`, ni `eval`, ni pickle sur la voie CPU. Le seul accès réseau est un `snapshot_download`, qui n'est pas appelé pour un dossier local.

## Tasks & Acceptance

**Execution :**
- [x] `tools/bench/v2s6_decision_bench.py` :
  - Trois `Candidate` : `mdeberta`, `minilm_multi` (`nli_onnx`, `_NLI_PACKAGES`, MIT, échelon 2) et `decision20` (backend `decision20_torch`, échelon 2, Apache-2.0).
  - Pour `decision20` :
    - `--with torch --with transformers --with safetensors --with huggingface-hub` ;
    - nouveaux champs `revision` (le sha relu), `full_snapshot=True` et `trust_remote_code=True` ;
    - fichiers témoins de présence : `MODEL_MANIFEST.json`, `config.json`, `modeling_decision2.py`, `decision_head.safetensors`, `backbone/model.safetensors`.
  - Téléchargement et instantané :
    - `download_candidate` et `_snapshot` passent `revision` et omettent `allow_patterns` si `full_snapshot` ;
    - `snapshot_present` ne regarde que `snapshots/<revision>` quand elle est fixée ;
    - un helper pur liste les instantanés d'autres commits. `run_measure` en tire le statut « non mesuré : code non relu à ce commit (<sha>) ; relu : <revision> », sans lancer l'enfant.
  - Helpers purs :
    - `onnx_feeds(encs, names)` : les entrées NLI filtrées, en listes. `_load_nli` les convertit en tableaux numpy ;
    - `decision20_questions(task)` : instructions en français, critères = `{clé: crit.text}` ;
    - `decision20_label(answer)` : la clé choisie, ou `erreur : <code>`.
  - `_load_decision20` : import de transformers, puis `AutoModel.from_pretrained(<instantané épinglé>, trust_remote_code=True, device="cpu")` et une question par tâche. Il consigne la révision.
  - `_default_runner` :
    - `HF_MODULES_CACHE` = `<models_dir>/hf_modules`, pour que le module dynamique de Transformers s'écrive sous le dossier du banc ;
    - retire les variables `DECISION2_*` pour rester sur la voie CPU par défaut.
  - Critère `pinned` : KO (non bloquant) si `trust_remote_code`, avec le sha relu dans le détail.
  - `print_list` affiche, pour `decision20`, le commit relu.
  - Garde-fou de mémoire :
    - fil démon lancé au début de `_measure_child` (`s12._rss_mb`, toutes les 0,5 s) ;
    - au-delà de `RAM_BUDGET_MB`, il imprime une ligne JSON (`error: "ram_ceiling"`, `rss_at_stop_mb`, `attempts`), puis appelle `os._exit(0)`. `_run_child` lit déjà la dernière ligne JSON ;
    - `decision_verdict` en tire « écarté (RAM) » (+ suffixe indicatif hors PC cible), avec la RSS à l'arrêt dans la raison. Le seuil et la période sont injectables pour les tests.
- [x] `tests/test_v2s6_decision_bench.py` :
  - Adapter le test du document : 12 lignes ; une cellule correspond à un candidat si elle commence par son `doc_name` ou par son id entre accents graves.
  - Tester les helpers purs, ainsi que :
    - les commandes des trois candidats ;
    - le statut « code non relu à ce commit » ;
    - le verdict de `decision20` mesuré : « à surveiller » au mieux, même sans torch dans le faux rapport ;
    - `_load_decision20`, avec un faux module `transformers` injecté dans `sys.modules` ;
    - l'environnement de l'enfant (`HF_MODULES_CACHE`, `DECISION2_*` retirées) ;
    - le garde-fou de mémoire.
- [x] Relecture du code de Decision 2.0 :
  - Après `--download`, relire les fichiers locaux de `snapshots/881bee41…/` : en entier pour la voie CPU, en-têtes et points d'entrée pour `fast*` et `shared_ctx`.
  - Comparer le sha et consigner la relecture dans le rapport.
  - Si le code diffère de ce qu'a relevé le sous-agent : HALT, et le dire à Anaël.
- [x] Relevé sur le PC cible : `list`, puis une mesure à la fois, `mdeberta`, `minilm_multi`, `decision20`, dans `tools/bench/results/2026-10-03-pc-cible-v2s7/`.
- [x] `rapport-test-prealable-modeles-de-decision.md` : commandes, trois lignes de mesure, relecture de Decision 2.0, mise à jour de la Suite. Ne pas toucher à `decision-model-candidates.md`.

**Acceptance Criteria :**
- Étant donné le banc étendu, quand on lance `list` sans réseau, alors chacun des trois candidats a sa commande exacte, et `decision20` affiche son commit relu.
- Étant donné la logique pure ajoutée, quand on lance `pytest`, alors elle est couverte par des faux, sans torch, ONNX ni réseau.
- Étant donné le relevé sur le PC cible, quand le rapport est relu, alors il donne pour chaque candidat les mesures, les versions, le commit et le verdict, avec le PC et la date.

## Design Notes

- Épingler le téléchargement de Decision 2.0 au sha relu (`revision=`) plutôt que de suivre `main` : la relecture vaut pour ce commit seul. Le contrôle de commit reste pour un cache déjà rempli par un autre commit.
- Le critère `pinned` KO pour `trust_remote_code` garantit « au mieux à surveiller » sans dépendre de torch.
- Instructions de la question `choice`, alignées sur le SLM juge : « Classe la demande de l'utilisateur selon les critères. »

## Verification

**Commands :**
- `uv run ruff check tools/bench/v2s6_decision_bench.py tests/test_v2s6_decision_bench.py` et `uv run ruff format --check` sur les mêmes fichiers : sans erreur.
- `uv run pytest tests/test_v2s6_decision_bench.py -q` : tout passe, y compris le test du document.
- `uv run python tools/bench/v2s6_decision_bench.py list` : trois nouvelles entrées, sans réseau.
- Relevé sur le PC cible : une commande par candidat, telles qu'écrites dans le rapport.

## Implementation Notes

- 2026-10-03, agent :
  - **Banc.** Le banc est étendu sans copie : trois `Candidate`, de nouveaux champs (`revision`, `full_snapshot`, `trust_remote_code`), et de nouveaux helpers purs :
    - `onnx_feeds`, `decision20_questions`, `decision20_label` ;
    - `snapshot_kwargs` et `other_snapshots` ;
    - `child_env`, `ram_ceiling_report` et `start_ram_watchdog`. Ce dernier rend le fil et un `Event` d'arrêt, levé à la fin de `_measure_child`.
  - **Chargement de Decision 2.0.** `_load_decision20` refuse un instantané autre que le commit relu. Les erreurs de Decision 2.0 arrivent par question (`answers[qid]["error"]`) ; `decision20_label` les lit.
  - **Tests.** 84 tests dans `tests/test_v2s6_decision_bench.py`, tous verts (après la revue : état du garde-fou dans le JSON (`ram_watchdog`), champs partiels gardés sur un échec, épinglage du téléchargement testé). Les trois mesures sont à rejouer (empreinte du banc changée).
  - **Téléchargement sans exécution.** `measure decision20 --download` exécuterait le code du dépôt juste après l'avoir téléchargé. Le dépôt a donc d'abord été téléchargé seul, par `download_candidate`, puis relu, puis mesuré. La commande est consignée dans le rapport.
  - **Relecture.** Le code relu est conforme au relevé du sous-agent, d'où l'absence de HALT. Le sous-dossier `decision2/_vendor/dev2model/` n'avait pas été nommé par le sous-agent ; il a été lu en entier.
  - **Relevé.**
    - `mdeberta` et `minilm_multi` : « retenu » ; `minilm_multi` dépasse 4 096 Mo avec le RAG V1.
    - `decision20` : non mesuré. Le code du dépôt, au commit relu, ne charge pas sous Windows : `checkpoint_fingerprint` construit ses chemins avec `\`, donc l'identité calculée diffère de celle du manifeste. Le banc n'a rien contourné.
    - Garde-fou de mémoire : non déclenché pendant ce relevé.
  - **Laissé à Anaël** : la validation des verdicts, puis bmad-spec sur `decision-model-candidates.md`. Le banc n'est pas commité : le `bench_sha256` des JSON correspond au fichier de l'arbre de travail.

- 2026-10-03, revue (orchestrateur) :
  - 26 constats triés (voir le journal ci-dessous) : 10 corrections, 16 rejets ; ni défaut de spec ni question d'intention.
  - Corrections appliquées par l'agent d'implémentation ; `ruff` sans erreur ; 134 tests passent (`test_v2s6_decision_bench.py`, `test_story12_bench.py`).
  - Les trois mesures ont été refaites de 07 h 55 à 07 h 57, une à la fois, sans `--download`. Les JSON portent `bench_sha256` `e7f98749…`, celui du banc final, avec `ram_watchdog` `active`.
  - RAM et accords inchangés. Latences : mDeBERTa 216 / 529 ms, MiniLM 49 / 123 ms.
  - `decision20.json` consigne maintenant `torch_loaded: true` et les champs du SLM. Le rapport est à jour.

## Spec Change Log

## Review Triage Log

| # | Source | Constat | Verdict | Preuve | Suite |
|---|---|---|---|---|---|
| 1 | aveugle | Accord coût de mDeBERTa (4/20) : défaut du banc ? | false | `entailment_index` lit `id2label` (0 = entailment pour mDeBERTa) ; l'argmax des logits d'implication est la règle du pipeline HF ; même décodage que `deberta_xsmall` (12/20) ; erreurs : 10 « simple → complexe », 6 « complexe → simple » (4 complexes justes) : biais vers « complexe », pas une inversion du décodage | rejeté |
| 2 | aveugle | Un classifieur constant (MiniLM, coût) reste « retenu » | low | réel, mais l'accord n'est pas un critère : le bloc figé impose les critères de la story 6 | rejeté (l'intention l'exclut) |
| 3 | aveugle | Épinglage de Decision 2.0 par nom de dossier, pas par empreinte des fichiers | low | le téléchargement est épinglé par `revision=`, et `verify_bundle` du modèle contrôle le manifeste ; il faudrait une altération locale du cache | rejeté (improbable, ajoute un contrôle) |
| 4 | aveugle + cas limites | `c.revision` s'applique à chaque dépôt d'un candidat | low | seul `decision20` a une révision, avec un seul dépôt : défaut latent | rejeté (improbable, restructure `repos`) |
| 5 | aveugle + cas limites | Le garde-fou se coupe en silence sur toute exception, et le JSON ne dit pas s'il était actif | medium | `watch()` fait `return` sur toute exception de `read()` ; aucun champ dans le JSON ; la phrase « non déclenché » du rapport n'est pas vérifiable | patch |
| 6 | aveugle + cas limites | RSS = ensemble de travail sous Windows, échantillonnage de 0,5 s : le rapport promet trop (« ne le fait plus basculer en mémoire virtuelle ») ; code de sortie 0 | low | la formulation du rapport (ligne 47) est trop forte ; la RSS reste la mesure du critère RAM (cohérence avec la story 6) ; `_run_child` lit le JSON quel que soit le code de sortie | patch (texte du rapport seul) |
| 7 | aveugle | `decision20.json` n'a ni `torch_loaded` ni les champs du SLM, alors que le rapport affirme « torch chargé avant l'échec » | medium | vérifié : `torch_loaded` vaut `None` ; le chemin d'erreur de `_measure` et de `run_measure` ne garde que l'erreur et les tentatives | patch (garder les mesures partielles, puis remesurer) |
| 8 | aveugle | Verdict du JSON (« non mesuré ») ≠ lecture proposée dans le rapport | false | le rapport dit « lecture proposée, à valider par Anaël » ; le JSON garde le verdict du banc | rejeté |
| 9 | aveugle | `repo_commit` b53b054 avec un arbre modifié | low | `bench_sha256` relie déjà chaque JSON au fichier exact ; les correctifs changent le banc, donc remesure après correction | traité par la remesure |
| 10 | aveugle | La couverture de la relecture est surestimée | low | le rapport dit « en-têtes et points d'entrée » pour `fast*` et `shared_ctx`, comme le demandait la spec | rejeté |
| 11 | aveugle | Texte du rapport périmé (« tous entraînés en anglais », virgule, ligne Decision 1.0) | low | lignes 31, 145 et 152 du rapport | patch (texte) |
| 12 | aveugle | Correctif amont du défaut Windows ? | low | Hub : dernière mise à jour le 2 octobre, `881bee41…` est toujours `main` | patch (une phrase dans le rapport) |
| 13 | aveugle | « sans token_type_ids » attribué à MiniLM seul | low | `mdeberta.json` : `onnx_inputs` = `attention_mask`, `input_ids` | patch (docstring, note, commentaire) |
| 14 | aveugle | Le test du document ne vérifie qu'un sens | low | amélioration de test, aucun défaut | rejeté |
| 15 | aveugle | Raison « None Mo » si `rss_at_stop_mb` manque | false | `ram_ceiling_report` met toujours le champ ; une ligne tronquée n'est pas du JSON valide pour `_run_child` | rejeté |
| 16 | aveugle | Le patch omet des fichiers | false | choix de la mise en revue : la spec est le fichier de constats, les autres ne sont pas de cette story | rejeté |
| 17 | écarts de vérif. | Aucun test ne vérifie que `download_candidate` transmet l'épinglage | medium | constat déposé : seul `snapshot_kwargs` est testé | patch |
| 18 | écarts de vérif. | Test « silencieux dans le budget » dépendant du fil | low | `stop.set()` peut précéder toute lecture | patch |
| 19 | écarts de vérif. + cas limites | Instantané relu incomplet + autre commit : statut « code non relu » trompeur | low | combinaison d'un téléchargement interrompu et d'un autre commit en cache | rejeté (improbable) |
| 20 | écarts de vérif. | Clause de commit sans effet dans `pinned` | low | toujours masquée par `trust_remote_code` | rejeté (sans conséquence) |
| 21 | cas limites | Course : le garde-fou écrit après la ligne finale | low | il faudrait une RSS au-delà du budget à la fin seulement, ce qui donne de toute façon un KO RAM | rejeté |
| 22 | cas limites | SLM seul au-delà du budget : la faute retombe sur le candidat | low | SLM actuel ≈ 1,9 Go ; la raison dit « SLM par défaut chargé » | rejeté |
| 23 | cas limites | `say` qui lève : le fil meurt sans arrêter l'enfant | low | correction directe (`try/finally`) | patch |
| 24 | cas limites | Des décisions toutes en erreur passent pour mesurées | low | l'accord tombe à 0/20 et chaque ligne garde `erreur : <code>` : visible ; aujourd'hui inatteignable (chargement en échec) | rejeté (ajoute une garde) |
| 25 | cas limites | `revision` qui ne serait pas un sha complet | false | constante unique de 40 caractères hexadécimaux, testée | rejeté |
| 26 | cas limites | `answers` qui ne serait pas un dict : AttributeError | false | l'API rend un dict (code relu) ; une erreur bruyante est le bon comportement | rejeté |
