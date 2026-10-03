# Rapport : test préalable des modèles de décision (V2, stories 6 et 7, CAP-6)

> **État au 2026-10-03 : relevé fait sur le PC cible** (lancé par Anaël le 02/10 au soir, joué par l'agent). Quatre candidats mesurés ; gliformer (voie torch) interrompu faute de mémoire, gliformer ONNX non installable sans compilateur. Seuils de latence et décision validés par Anaël le 2026-10-03 ; story 6 `done`.
>
> **Story 7, même jour (07 h 55 à 07 h 57, joué par l'agent, après les corrections de la revue) :** mDeBERTa et MiniLM multilingues mesurés, tous deux « retenu » ; Decision 2.0 Kai non mesuré : son code, relu au commit épinglé, refuse de charger le modèle sous Windows (contrôle d'identité, voir « Relecture du code de Decision 2.0 ») : **écarté sur le PC cible au commit relu** (décision d'Anaël du 2026-10-03), à réessayer si le code est corrigé. Verdicts de mDeBERTa et MiniLM validés par Anaël ; `decision-model-candidates.md` mis à jour par bmad-spec le même jour.

- Stories : [6-test-prealable-des-modeles-de-decision.md](../specs/spec-wavestack-v2/stories/6-test-prealable-des-modeles-de-decision.md), [7-banc-des-nouveaux-candidats-de-decision.md](../specs/spec-wavestack-v2/stories/7-banc-des-nouveaux-candidats-de-decision.md)
- Candidats et critères : [decision-model-candidates.md](../specs/spec-wavestack-v2/decision-model-candidates.md). Ce fichier se met à jour par un nouveau passage de bmad-spec, à partir de ce rapport, jamais à la main.
- Banc : `tools/bench/v2s6_decision_bench.py`, testé par `tests/test_v2s6_decision_bench.py`.

## Relevé

| Champ | Valeur |
|---|---|
| Poste | HP EliteBook x360 1030 G8, Intel Core i5-1145G7 (8 fils), 16 064 Mo de RAM |
| Système | Windows 11 Entreprise (10.0.26200), session sans droits admin (lu par le banc : `admin: false`), proxy Zscaler |
| SLM par défaut chargé pendant la mesure | `Qwen3.5-2B-Q4_K_M.gguf` (`%LOCALAPPDATA%\WaveStack\models`), fenêtre de 4 096, llama-cpp-python 0.3.35 ; RSS avec le SLM : ≈ 1 938 Mo |
| Date du relevé | 2026-10-03, de 00 h 44 à 00 h 57 (Decision 1.0 : 2026-10-02) ; story 7 : 2026-10-03, de 07 h 55 à 07 h 57, une mesure à la fois (premier passage de 07 h 05 à 07 h 12, refait après les corrections de la revue : mêmes RAM et accords) |
| Version du banc | commit `7315647` ; empreinte du banc dans chaque JSON (`bench_sha256`) ; résultats dans `tools/bench/results/2026-10-02-pc-cible-v2s6/` |
| Version du banc (story 7) | banc étendu, commité après le relevé (`repo_commit` b53b054 dans les JSON, arbre modifié) : `bench_sha256` `e7f987490657412977922db3a82c35085ab9b527735a48a50a7362aa7a4e6758`, identique dans les trois JSON et égal à l'empreinte du banc du commit `82e41fb` tel qu'extrait sous Windows (fins de ligne CRLF, `core.autocrlf=true` ; le blob git, en LF, a une autre empreinte) ; garde-fou de mémoire `active` dans les trois (`ram_watchdog`) ; résultats dans `tools/bench/results/2026-10-03-pc-cible-v2s7/` ; même SLM, RSS avec le SLM ≈ 1 938 Mo |

## Ce que mesure le banc

Chaque mesure tourne dans un processus enfant neuf. Il installe la garde réseau du projet (AD-15) avant tout import tiers, retire les variables de proxy et consigne chaque tentative réseau. Il charge ensuite le SLM par défaut avec les réglages du moteur de WaveStack (fenêtre `[context] window` de `wavestack.toml`, threads par défaut), et lui fait produire un token pour que ses poids soient en mémoire comme pendant un tour. Il lit alors la RSS de base, charge le candidat, fait une décision d'échauffement non chronométrée par tâche, puis chronomètre 40 décisions. Le JSON consigne aussi le commit du dépôt, l'empreinte du banc, la version de llama-cpp-python, la version de Windows et la présence de droits admin.

**Entrées.** Vingt prompts fixes, tirés des prompts suggérés des scénarios V1 (`content/scenarios.yaml`), chacun dans deux tâches :

- **coût** : `simple` ou `complexe` ;
- **spécialité**, sur quatre critères écrits : `securite`, `documents`, `recherche`, `general`.

Le texte des critères est dans `TASKS` du banc. Il sert d'hypothèse NLI à DeBERTa et de prompt au SLM juge ; GLiFormer reçoit des libellés courts. Chaque prompt porte une étiquette attendue, écrite par l'agent et discutable. L'accord avec elle est affiché à titre indicatif et ne compte pas comme critère : les prompts sont en français, et les candidats de la story 6 sont entraînés en anglais (mDeBERTa et MiniLM, ajoutés par la story 7, sont multilingues).

**Critères et verdict.** Un critère est **ok**, **KO** ou **non vérifiable par le banc** :

| Critère | Mesure | Si KO |
|---|---|---|
| CPU sous Windows 11, sans droits admin | Windows 11 et session sans droits admin, lus par le banc ; roues précompilées à vérifier à l'œil (voir plus bas) | non vérifiable (verdict « indicatif ») hors Windows 11 ou en session admin |
| RAM | pic de RSS du processus, SLM compris, ≤ 4 096 Mo (NFR-2) ; RSS ajoutée par le candidat = pic − base. Le détail ajoute, pour information, l'embedding et le reranker V1 (1 170 Mo mesurés par la story 12) | **écarté** |
| Latence | médiane ≤ 1 000 ms et maximum ≤ 3 000 ms par décision | **écarté** |
| Hors ligne | aucune tentative réseau sous la garde, au chargement comme aux décisions | **écarté** |
| Code relu et figé | commit du modèle (dossier `snapshots/<sha>`) et versions des paquets consignés ; aucun `trust_remote_code` | à surveiller |
| Licences (NFR-10) | licence du modèle et des paquets ajoutés au projet | interdite : **écarté** ; non déclarée ou à vérifier : à surveiller |
| Sans torch | `torch` chargé pendant la mesure | à surveiller |

Tout ok : **retenu**. Le SLM juge n'a pas de seuil de latence : il est la référence du repli, avec le verdict « repli (référence) » s'il décide hors ligne dans le budget de RAM. Les seuils de latence ont été fixés en mode nuit, le 2026-10-01, et validés par Anaël au vu du relevé, le 2026-10-03.

**Garde-fou de mémoire (story 7).** Dès son démarrage, l'enfant lit sa RSS toutes les 0,5 s dans un fil démon. Au-delà de 4 096 Mo, il écrit sa dernière ligne JSON (`error: "ram_ceiling"`, RSS à l'arrêt, tentatives réseau) et s'arrête aussitôt. Le verdict est alors « écarté (RAM) », sans latence ni accord. Le fil échantillonne la RSS (sous Windows, l'ensemble de travail) toutes les 0,5 s : une grosse allocation peut dépasser le seuil entre deux lectures. Le garde-fou limite donc la pression sur le PC cible partagé (16 Go), où gliformer a fait tomber la RAM le 03/10, sans la garantir. Le JSON de l'enfant consigne son état (`ram_watchdog` : actif, ou inactif avec la raison, budget et période).

**Épinglage.** Le téléchargement suit `main`, et les commandes `--with` ne fixent pas de version : le banc épingle par ce qu'il consigne. Seule exception, Decision 2.0 Kai : son téléchargement et sa mesure sont épinglés au commit dont le code a été relu (`revision`). Si le cache ne contient qu'un autre commit, le banc ne lance pas l'enfant et répond « non mesuré : code non relu à ce commit ». Pour un candidat retenu, le commit et les versions du JSON sont ceux à reporter dans `decision-model-candidates.md`, puis dans la story qui l'intègre.

**Budget complet.** NFR-2 compte toutes les briques actives. Le banc mesure le SLM et le candidat. Le détail du critère RAM ajoute, pour information, l'embedding et le reranker V1 : un candidat qui tient seul mais dépasse 4 096 Mo avec le RAG suppose que le routage se démontre RAG éteint. C'est à trancher au passage de bmad-spec.

**Roues précompilées.** Python ne voit pas si `uv` a compilé un paquet. À la première commande de chaque candidat, vérifier dans la sortie de `uv` qu'aucune ligne « Building … » n'apparaît. Sinon, noter le paquet dans la colonne « Raison » : le critère 1 échoue.

## Commandes du relevé (PowerShell, depuis la racine du dépôt)

Une seule fois, avant les mesures :

`uv sync --all-extras` installe l'environnement complet du projet (extras compris). Les commandes de mesure ajoutent par `--with` tout ce que le cœur du projet n'a pas, y compris `tokenizers` et `huggingface-hub`, qui n'y arrivent que par l'extra `compression`. Ces paquets comptent donc dans les « paquets ajoutés ».

```powershell
uv sync --all-extras
uv run python tools/bench/v2s6_decision_bench.py list
$SLM = "<chemin du GGUF du SLM par défaut, celui que WaveStack charge>"
$OUT = "tools\bench\results\<AAAA-MM-JJ>-pc-cible-v2s6"
```

Sans `--slm`, le banc prend le seul GGUF de SLM du dossier des modèles de WaveStack (`%LOCALAPPDATA%\WaveStack\models`), hors embedding et reranking. S'il en trouve plusieurs, il les liste et s'arrête.

**1. Decision 1.0 : revérification, sans mesure.** Relever d'abord, avec la date et la source :

- la présence d'un GGUF ou d'un ONNX sur les pages Hugging Face des modèles Decision 1.0 (Kai, Lex) ;
- un chemin d'inférence CPU dans le `USAGE.md` du dépôt vLLM Semantic Router.

Puis consigner le relevé (ajouter `--gguf`, `--onnx` ou `--cpu` avec l'URL si un chemin existe) :

```powershell
uv run python tools/bench/v2s6_decision_bench.py decision10 --checked-on <AAAA-MM-JJ> --source <URL lue> --out "$OUT\decision10.json"
```

Sans aucun chemin, le verdict est « écarté sans mesure ». Avec un chemin, il est « à surveiller » : mesurer Kai ou Lex 0.6B demande une nouvelle story.

**2. SLM juge (échelon 3, référence du repli) :**

```powershell
uv run python tools/bench/v2s6_decision_bench.py measure slm_judge --slm $SLM --out "$OUT\slm_judge.json"
```

**3. DeBERTa-v3 zero-shot NLI, xsmall puis base (échelon 2)** : téléchargement de 87 Mo, puis de 747 Mo.

```powershell
uv run --with onnxruntime --with tokenizers --with huggingface-hub python tools/bench/v2s6_decision_bench.py measure deberta_xsmall --download --slm $SLM --out "$OUT\deberta_xsmall.json"
uv run --with onnxruntime --with tokenizers --with huggingface-hub python tools/bench/v2s6_decision_bench.py measure deberta_base --download --slm $SLM --out "$OUT\deberta_base.json"
```

**4. nvidia/prompt-task-and-complexity-classifier (échelon 1)** : 735 Mo de poids, plus torch.

```powershell
uv run --with torch --with transformers --with safetensors python tools/bench/v2s6_decision_bench.py measure nvidia --download --slm $SLM --out "$OUT\nvidia.json"
```

**5. gliformer-base-v1 (échelon 2), voie officielle (torch) puis ONNX tiers** : 1,06 Go de poids, puis 741 Mo.

```powershell
uv run --with gliformer --with huggingface-hub python tools/bench/v2s6_decision_bench.py measure gliformer --download --slm $SLM --out "$OUT\gliformer.json"
uv run --with fast-gliner --with huggingface-hub python tools/bench/v2s6_decision_bench.py measure gliformer_onnx --download --slm $SLM --out "$OUT\gliformer_onnx.json"
```

**6. Story 7 : mDeBERTa et MiniLM multilingues, puis Decision 2.0 Kai (échelon 2)** : téléchargement de 355 Mo, de 445 Mo, puis de ≈ 1,53 Go (dépôt complet de Decision 2.0 : `verify_bundle` exige tous les fichiers de `MODEL_MANIFEST.json`). Une mesure à la fois, `$OUT` = `tools\bench\results\2026-10-03-pc-cible-v2s7`.

```powershell
uv run --with onnxruntime --with tokenizers --with huggingface-hub python tools/bench/v2s6_decision_bench.py measure mdeberta --download --slm $SLM --out "$OUT\mdeberta.json"
uv run --with onnxruntime --with tokenizers --with huggingface-hub python tools/bench/v2s6_decision_bench.py measure minilm_multi --download --slm $SLM --out "$OUT\minilm_multi.json"
uv run --with torch --with transformers --with safetensors --with huggingface-hub python tools/bench/v2s6_decision_bench.py measure decision20 --download --slm $SLM --out "$OUT\decision20.json"
```

Pour Decision 2.0, `measure --download` exécute le code du dépôt juste après le téléchargement. Le 03/10, le dépôt a donc d'abord été téléchargé seul, au commit épinglé, sans rien exécuter, avec la fonction de téléchargement du banc. Son code a ensuite été relu, puis la commande ci-dessus a été lancée :

```powershell
uv run --with huggingface-hub python -c "import sys, json; sys.path.insert(0, 'tools/bench'); import v2s6_decision_bench as b; from pathlib import Path; print(json.dumps(b.download_candidate(b.candidate('decision20'), Path.home() / '.cache' / 'wavestack-bench'), ensure_ascii=False))"
```

`--download` télécharge seulement les fichiers nécessaires (tout le dépôt pour Decision 2.0), dans `~/.cache/wavestack-bench/hf`, par le proxy du poste et le magasin de certificats du système. La mesure se fait ensuite hors ligne, sur le commit téléchargé, qui est consigné. Relancer sans `--download` pour remesurer. Si `uv` ne résout pas un `--with`, par exemple si `fast-gliner` n'est pas publié sur PyPI, noter l'erreur dans la colonne « Raison » : le candidat reste « à surveiller ».

Les fichiers JSON de `$OUT` se versionnent, comme ceux de la story 12 (`tools/bench/results/`).

## Mesures et verdicts

| Candidat | Échelon | RAM pic total / ajoutée (Mo) | Latence médiane / max (ms) | Réseau | Paquets ajoutés (licences) | torch | Révision, `trust_remote_code` | Accord indicatif (coût, spécialité) | Verdict | Raison |
|---|---|---|---|---|---|---|---|---|---|---|
| SLM juge | 3 | 2 080 / 143 | 4 708 / 7 157 | aucune tentative | aucun | non | GGUF local, sans objet | 12/20, 7/20 | **repli (référence)** | tous les critères passent ; échauffement 9,1 s |
| `deberta_xsmall` (MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33, MIT) | 2 | 2 285 / 346 (3 455 avec l'embedding et le reranker V1) | 107 / 253 | aucune tentative | 10, dont onnxruntime 1.30.0, tokenizers 0.23.2, huggingface-hub 1.33.0 (toutes compatibles) | non | `262ae02f29173eec1c250f90804dc7edc677dcff`, pas de `trust_remote_code` | 12/20, 7/20 | **retenu** | tous les critères passent ; aucune compilation (`uv`) |
| `deberta_base` (MoritzLaurer/deberta-v3-base-zeroshot-v2.0, MIT) | 2 | 3 162 / 1 225 (**4 332** avec l'embedding et le reranker V1) | 501 / 1 241 | aucune tentative | les mêmes 10 (compatibles) | non | `8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8`, pas de `trust_remote_code` | 13/20, 11/20 | **retenu** | tous les critères passent ; avec le RAG V1, dépasse 4 096 Mo : routage à démontrer RAG éteint (bmad-spec) |
| `nvidia` (prompt-task-and-complexity-classifier, NVIDIA Open Model License) | 1 | 3 640 / 1 701 (4 810 avec le RAG V1) | 437 / 711 | aucune tentative | 21, dont torch 2.14.1, transformers 5.18.0, safetensors 0.8.0 (compatibles) | **oui** | `fea1121511eafabaf7dd6fc66863dcb04f74defb` + dorsale `microsoft/deberta-v3-base` `8ccc9b6f…` ; code de la carte reproduit, `load_warnings` 0/0 | coût 11/20 (étiquettes fixes) | **à surveiller** | torch chargé ; chargement de 29 s. Verdict recalculé le 03/10 : le banc classait `BSL-1.0` (licence Boost, dans l'expression de torch) comme Business Source License, d'où un « écarté » faux ; corrigé dans `story12_bench.classify_license`, mesures inchangées (`verdict_recomputed` dans le JSON) |
| `gliformer` (knowledgator/gliformer-base-v1, Apache-2.0) | 2 | non mesuré | — | — | gliformer et torch | (oui) | `590f9d3f…` téléchargé | — | **écarté sur le PC cible** (RAM, indicatif ; décision du 2026-10-03) | mesure interrompue par Claude Code, faute de mémoire sur le poste : le processus de mesure tenait ≈ 4 491 Mo de RSS à l'arrêt (indicatif : au-delà de 4 096 Mo) ; avertissement Windows sur les liens symboliques du cache HF (mode développeur absent) |
| `gliformer_onnx` (talmago/gliformer-base-v1-onnx, licence non déclarée) | 2 | non mesuré | — | — | `fast-gliner` 0.3.1 : aucune roue Windows ; `uv` compile depuis les sources (Rust) et échoue | — | — | — | **écarté sur le PC cible** | critère 1 KO : « Building fast-gliner==0.3.1 » puis « Failed to build » (pas de compilateur, pas de droits admin) |
| `mdeberta` (MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7, MIT ; story 7) | 2 | 2 719 / 781 (3 889 avec l'embedding et le reranker V1) | 216 / 529 | aucune tentative | les mêmes 10 que `deberta_xsmall` (compatibles) : onnxruntime 1.30.0, tokenizers 0.23.2, huggingface-hub 1.33.0 | non | `b5113eb38ab63efdd7f280f8c144ea8b13f978ce`, pas de `trust_remote_code` | 4/20, 6/20 | **retenu** (banc) | tous les critères passent, aucune compilation (`uv`) ; tient le budget avec le RAG V1 (3 889 Mo). Entrées ONNX : `input_ids`, `attention_mask`. Accord plus faible que les DeBERTa anglais : 14 « complexe » sur 20, et 11 « securite » et 8 « documents » sur 20 en spécialité ; chargement 5,9 s |
| `minilm_multi` (MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli, MIT, XLM-R ; story 7) | 2 | 3 005 / 1 067 (**4 175** avec l'embedding et le reranker V1) | 49 / 123 | aucune tentative | les mêmes 10 (compatibles) | non | `0a71e92a985b6e1ad1828cf67ce9c459639c1dca`, pas de `trust_remote_code` | 10/20, 8/20 | **retenu** (banc), RAG éteint seulement | tous les critères passent, aucune compilation ; sans `token_type_ids` (entrées filtrées par la session, sans erreur). Dépasse 4 096 Mo avec le RAG V1 : l'« option légère » ne l'est pas en RAM (ONNX fp32 de 428 Mo contre l'ONNX quantifié de mDeBERTa). Coût dégénéré : « complexe » pour les 20 prompts (10/20 = taux de base) ; spécialité 11 « securite », 6 « documents », 3 « recherche » |
| `decision20` (vllm-sr/Decision-2.0-Kai-0.6B, Apache-2.0 ; story 7) | 2 | non mesuré | — | aucune tentative | 21, dont torch 2.14.1, transformers 5.18.0, safetensors 0.8.0, huggingface-hub 1.33.0 (compatibles) | oui (`torch_loaded`, chargé avant l'échec) | `881bee413681d80ebeac86afcda8b4138dae516e` (relu, épinglé) ; `trust_remote_code` | — | **non mesuré** (banc) ; **écarté sur le PC cible au commit relu** (critère 1 ; décision d'Anaël du 2026-10-03), à réessayer si le code est corrigé (`deferred-work.md`) | le code du dépôt refuse de charger sous Windows : `ValueError('Model identity differs from the scored checkpoint')`, avant le chargement des poids (garde-fou de mémoire actif, non déclenché ; SLM chargé en 1,8 s, 1 939 Mo). Cause vérifiée : `checkpoint_fingerprint` (`_vendor/dev2model/infer.py`) écrit les chemins par `str(file.relative_to(path))`, donc `backbone\config.json` sous Windows ; l'empreinte vaut `451bac5e…` au lieu de `bb806f31…` du manifeste, qu'on retrouve avec des `/`. Défaut amont, propre à Windows. Le banc n'a pas contourné : modifier le code relu reviendrait à exécuter un code non relu. Aucune compilation (`uv`) |

**Verdicts sans mesure :**

| Candidat | Verdict | Raison |
|---|---|---|
| Decision 1.0 (vLLM Semantic Router) | **à surveiller** (`decision10.json`, relevé du 2026-10-02) | Le README de Kai 0.6B annonce désormais un chemin CPU : Transformers avec `trust_remote_code=True`, FP32, torch ; ni GGUF ni ONNX (safetensors seulement, ≈ 2,3 Go de poids). Decision 1.0 n'est plus le candidat suivi : **Decision 2.0** le remplace (Kai 0.6B sur Qwen3-0.6B-Base, 2026-09-28, Apache-2.0, non génératif, contexte de 8 192, même voie Transformers + `trust_remote_code`), ajouté aux candidats le 2026-10-03 et passé au banc par la story 7 (voir plus haut). Eos, Sol, Nox et Lux restent génératifs. |
| Llama-Guard-3-1B | écarté | Génératif : jamais classifieur coexistant (règle d'un seul modèle génératif, NFR-2). Il ne servirait qu'en remplaçant le SLM (CAP-9). |
| Qwen3Guard-Gen-0.6B | écarté | Même raison. |
| Arch-Router-1.5B | écarté | Licence commerciale DigitalOcean exigée : incompatible avec NFR-10 (forge du 2026-09-25). |

## Points à surveiller au relevé

- **Langue.** Les candidats mesurés par la story 6 sont entraînés en anglais (cartes Hugging Face). Un accord faible sur les prompts français ne change pas le verdict. Il a toutefois conduit, le 2026-10-03, à ajouter deux variantes multilingues aux candidats (mDeBERTa, MiniLM), mesurées par la story 7 : leur accord n'est pas meilleur sur ces vingt prompts.
- **Licence nvidia.** Le banc classe la NVIDIA Open Model License comme compatible, d'après `decision-model-candidates.md` (« usage commercial autorisé »). Ses clauses (attribution, garde-fous) restent à relire pour une remise du code à des clients (NFR-10) avant tout « retenu ». La carte ne cite comme matériel pris en charge que des GPU NVIDIA sous Ubuntu : la voie CPU sous Windows n'est pas annoncée par l'éditeur.
- **nvidia.** Le banc reproduit le code de la carte, relu, sans `trust_remote_code`. La dorsale est construite depuis la configuration de `microsoft/deberta-v3-base`, et les poids viennent du `model.safetensors` du classifieur. Le JSON consigne `load_warnings` : un nombre de clés manquantes différent de zéro signale un écart avec la carte.
- **gliformer.** La voie officielle charge torch : elle sera au mieux « à surveiller ». Seule la conversion ONNX tierce l'évite, mais sa licence n'est pas déclarée.

## Relecture du code de Decision 2.0 (story 7)

Relue par l'agent le 2026-10-03, sur les fichiers locaux de `~/.cache/wavestack-bench/hf/models--vllm-sr--Decision-2.0-Kai-0.6B/snapshots/881bee413681d80ebeac86afcda8b4138dae516e/`, téléchargés au commit épinglé sans rien exécuter.

- **Commit** : le dossier de l'instantané est bien `881bee413681d80ebeac86afcda8b4138dae516e`, le sha consigné dans le banc (`DECISION20_REVISION`) ; 36 fichiers.
- **Lus en entier (voie CPU)** : `modeling_decision2.py`, `configuration_decision2.py`, `pipeline_decision2.py`, `decision2/__init__.py`, `decision2/api.py`, `decision2/qwen.py`, et `decision2/_vendor/dev2model/` (`data.py`, `decision_model.py`, `infer.py`, `calibration.py`, `lora.py`, `score_bias.py`, `source.py`). Le sous-dossier `_vendor/` n'était pas nommé par le relevé du sous-agent ; il appartient bien à `decision2/` et à la voie CPU.
- **En-têtes et points d'entrée** : `decision2/fast.py`, `decision2/fast_kernels.py` (Triton) et `decision2/shared_ctx.py`. `fast.install` n'est appelé que sur un GPU CUDA ou ROCm avec poids BF16 (`qwen.py`) ; `shared_ctx` seulement si `share_context` est demandé (faux par défaut). Les variables `DECISION2_FAST`, `DECISION2_KERNELS` et `DECISION2_GRAPHS` ne font qu'**éteindre** des pièces de la voie GPU. Le banc les retire quand même de l'environnement de l'enfant.
- **Empreintes SHA-256** des fichiers de code, identiques à `MODEL_MANIFEST.json` (`verify_bundle` les contrôle aussi au chargement) : `modeling_decision2.py` `a3f700b3…`, `configuration_decision2.py` `b88ce838…`, `pipeline_decision2.py` `3393faec…`, `decision2/api.py` `10925403…`, `decision2/qwen.py` `62df8de0…`, `_vendor/dev2model/infer.py` `7bb9f3cc…`, `decision_model.py` `1ab1e49b…`.
- **Conforme au relevé du sous-agent**, rien qui impose un HALT :
  - Apache-2.0 (manifeste : poids, runtime et base Qwen3-0.6B-Base) ;
  - profil `qwen-full`, `Qwen3Model` de 28 couches, 597 103 104 paramètres chargés, en FP32 sur CPU (`model.float()`) ;
  - contexte de 8 192, sans troncature (`max_length_exceeded`) ; `dtype` limité à `None` ou `"auto"` ;
  - `verify_bundle` exige tous les fichiers du manifeste, README et PNG compris (seul `.gitattributes` est toléré) ;
  - le runtime `decision2/` est copié dans le dossier des modules dynamiques de Transformers (ici `~/.cache/wavestack-bench/hf_modules/`, par `HF_MODULES_CACHE`) ;
  - appel `system_one(state=…, questions={qid: {"type": "choice", …}})`, réponse `["answers"][qid]["choice"]` ; une erreur arrive **par question**, `answers[qid] = {"type": …, "error": <code>}` ;
  - ni `subprocess`, ni `eval`/`exec`, ni pickle ou `torch.load` ; poids lus en safetensors.
- **Réseau** : `snapshot_download` n'est appelé que pour un nom de dépôt (pas pour un dossier local) ou pour un adaptateur `qwen-adapter` (`base` vaut `null` ici). Mesure : aucune tentative réseau sous la garde.
- **Écritures sur disque** : le module dynamique ci-dessus ; une vue en liens physiques temporaire à côté du cache, seulement si l'instantané contient des liens symboliques (pas sur ce poste, faute de mode développeur).
- **Défaut sous Windows** : `checkpoint_fingerprint` (`_vendor/dev2model/infer.py`, ligne 296) écrit les chemins relatifs avec le séparateur du système. Sous Windows, l'identité calculée ne correspond donc jamais à celle du manifeste, et `qwen.py` lève `Model identity differs from the scored checkpoint`. Vérifié hors du runtime, avec les SHA-256 du manifeste : avec des `/`, on retrouve `bb806f31a14d4532a1b5e00984442128f47f46cbbc68e57e7623327c81cfb983`, l'identité du manifeste ; avec des `\`, on obtient `451bac5e…`. Le modèle ne se charge donc pas sous Windows au commit relu, quels que soient la RAM et les paquets.
- **Correctif amont** : le 2026-10-03, le Hub ne montre aucun commit après `881bee41…` (dernière mise à jour le 2026-10-02) ; pas de correctif amont à ce jour. Relire puis remesurer quand un commit le corrige.

## Décision

Validée par Anaël le 2026-10-03, au passage de bmad-spec (`decision-model-candidates.md` à jour) :

- **Échelon 2 (encodeur programmable)** :
  - `deberta_xsmall` est le **candidat par défaut**. C'est le plus léger (+346 Mo, 107 ms de médiane) et le seul qui tient le budget avec le RAG V1 (3 455 Mo).
  - `deberta_base` reste retenu, mais **seulement pour un routage démontré RAG éteint** : il monte à 4 332 Mo avec le RAG V1. Il départage mieux les spécialités (11/20 contre 7/20).
  - Accords faibles dans les deux cas (modèles anglais, prompts français) : deux variantes multilingues sont ajoutées aux candidats, mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 et multilingual-MiniLMv2-L6-mnli-xnli (option légère).
- **Decision 2.0 Kai 0.6B** est ajouté aux candidats et remplace Decision 1.0 comme candidat suivi. Il passe par `trust_remote_code` et torch, donc au mieux « à surveiller ».
- **`gliformer`** est **écarté sur le PC cible** : la voie torch dépassait déjà 4 096 Mo à l'arrêt, sans le RAG (mesure indicative), et la voie ONNX ne s'installe pas.
- **Échelon 1** : aucun candidat retenu. `nvidia` reste à surveiller (torch, chargement de 29 s, étiquettes fixes). Les clauses de sa licence restent à relire (question 6 de la spec).
- **Échelon 3 (repli)** : le SLM juge fonctionne hors ligne dans le budget (+143 Mo), mais à 4,7 s de médiane par décision.
- **Seuils de latence** (médiane ≤ 1 000 ms, maximum ≤ 3 000 ms) : tous les candidats mesurés les tiennent largement ; seul le SLM juge, qui n'a pas de seuil, les dépasse. **Validés par Anaël le 2026-10-03.**

## Suite

Les quatre étapes prévues sont faites le 2026-10-03 : tableaux remplis, `decision-model-candidates.md` mis à jour par bmad-spec, « Deferred » d'`ARCHITECTURE-SPINE.md` remplacé par le verdict, story 6 passée à `done`.

Story 7 ([7-banc-des-nouveaux-candidats-de-decision.md](../specs/spec-wavestack-v2/stories/7-banc-des-nouveaux-candidats-de-decision.md)) : banc étendu (trois candidats, épinglage de Decision 2.0, garde-fou de mémoire), relevé fait le 2026-10-03 sur le PC cible, lignes ajoutées ci-dessus. Restent :

1. **Verdicts de mDeBERTa et MiniLM validés par Anaël le 2026-10-03** :
   - `mdeberta` **retenu**, dans le budget avec le RAG V1 (3 889 Mo), mais avec un accord indicatif plus faible que `deberta_xsmall` (4/20 et 6/20 contre 12/20 et 7/20). La variante multilingue n'améliore donc pas l'accord sur ces vingt prompts et ces critères. Ne remplace pas `deberta_xsmall` comme défaut.
   - `minilm_multi` **retenu, RAG éteint seulement** (4 175 Mo avec le RAG V1). Le plus rapide (49 ms de médiane), mais sa décision de coût est dégénérée (toujours « complexe »).
   - `decision20` : **écarté sur le PC cible au commit relu**, décidé par Anaël le 2026-10-03 (critère 1 : le code du dépôt ne charge pas sous Windows). Le nouvel essai est noté dans `deferred-work.md` : un commit qui corrige `checkpoint_fingerprint` demanderait une nouvelle relecture, puis une nouvelle mesure. Le garde-fou de mémoire servira alors : 597 M de paramètres en FP32 (≈ 2,4 Go) avec le SLM (≈ 1,9 Go) dépasseraient probablement 4 096 Mo, à mesurer.
2. **bmad-spec fait le 2026-10-03** : `decision-model-candidates.md` et `SPEC.md` à jour ; story 8 ajoutée à `stories.yaml`.
3. **Story 8 de la V2** (à écrire par bmad-spec, `deferred-work.md`) : en attendant Decision 2.0, essayer un modèle de décision servi par Ollama 0.35, tev1 0.8B seul (Anaël, 2026-10-03).
4. Optionnel : signaler le défaut Windows en amont (dépôt vLLM Semantic Router), avec la ligne fautive et le correctif évident (`relative_to(path).as_posix()`).
