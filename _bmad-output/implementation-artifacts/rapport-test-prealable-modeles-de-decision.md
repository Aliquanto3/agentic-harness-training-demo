# Rapport : test préalable des modèles de décision (V2, story 6, CAP-6)

> **État au 2026-10-01 : squelette.** Le banc est prêt et testé. Aucune mesure n'a encore été faite : aucun modèle téléchargé, aucune mesure réelle. Les mesures et les verdicts viennent du relevé d'Anaël sur le PC cible. Une mesure faite ailleurs (conteneur de développement, autre poste) porte la mention « indicatif, hors PC cible » et ne vaut pas verdict.

- Story : [6-test-prealable-des-modeles-de-decision.md](../specs/spec-wavestack-v2/stories/6-test-prealable-des-modeles-de-decision.md)
- Candidats et critères : [decision-model-candidates.md](../specs/spec-wavestack-v2/decision-model-candidates.md). Ce fichier se met à jour par un nouveau passage de bmad-spec, à partir de ce rapport, jamais à la main.
- Banc : `tools/bench/v2s6_decision_bench.py`, testé par `tests/test_v2s6_decision_bench.py`.

## Relevé

| Champ | Valeur |
|---|---|
| Poste | _à remplir : modèle, processeur, RAM (le banc affiche plateforme, cœurs et RAM)_ |
| Système | _à remplir : Windows 11, session sans droits admin_ |
| SLM par défaut chargé pendant la mesure | _à remplir : fichier GGUF_ |
| Date du relevé | _à remplir_ |
| Version du banc | _à remplir : commit du dépôt_ |

## Ce que mesure le banc

Chaque mesure tourne dans un processus enfant neuf. Il installe la garde réseau du projet (AD-15) avant tout import tiers, retire les variables de proxy et consigne chaque tentative réseau. Il charge ensuite le SLM par défaut avec les réglages du moteur de WaveStack (fenêtre `[context] window` de `wavestack.toml`, threads par défaut), et lui fait produire un token pour que ses poids soient en mémoire comme pendant un tour. Il lit alors la RSS de base, charge le candidat, fait une décision d'échauffement non chronométrée par tâche, puis chronomètre 40 décisions. Le JSON consigne aussi le commit du dépôt, l'empreinte du banc, la version de llama-cpp-python, la version de Windows et la présence de droits admin.

**Entrées.** Vingt prompts fixes, tirés des prompts suggérés des scénarios V1 (`content/scenarios.yaml`), chacun dans deux tâches :

- **coût** : `simple` ou `complexe` ;
- **spécialité**, sur quatre critères écrits : `securite`, `documents`, `recherche`, `general`.

Le texte des critères est dans `TASKS` du banc. Il sert d'hypothèse NLI à DeBERTa et de prompt au SLM juge ; GLiFormer reçoit des libellés courts. Chaque prompt porte une étiquette attendue, écrite par l'agent et discutable. L'accord avec elle est affiché à titre indicatif et ne compte pas comme critère : les candidats sont entraînés en anglais, face à des prompts français.

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

Tout ok : **retenu**. Le SLM juge n'a pas de seuil de latence : il est la référence du repli, avec le verdict « repli (référence) » s'il décide hors ligne dans le budget de RAM. Les seuils de latence ont été fixés en mode nuit, le 2026-10-01 ; Anaël les valide ou les corrige au vu du relevé.

**Épinglage.** Le téléchargement suit `main`, et les commandes `--with` ne fixent pas de version : le banc épingle par ce qu'il consigne. Pour un candidat retenu, le commit et les versions du JSON sont ceux à reporter dans `decision-model-candidates.md`, puis dans la story qui l'intègre.

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

`--download` télécharge seulement les fichiers nécessaires, dans `~/.cache/wavestack-bench/hf`, par le proxy du poste et le magasin de certificats du système. La mesure se fait ensuite hors ligne, sur le commit téléchargé, qui est consigné. Relancer sans `--download` pour remesurer. Si `uv` ne résout pas un `--with`, par exemple si `fast-gliner` n'est pas publié sur PyPI, noter l'erreur dans la colonne « Raison » : le candidat reste « à surveiller ».

Les fichiers JSON de `$OUT` se versionnent, comme ceux de la story 12 (`tools/bench/results/`).

## Mesures et verdicts

| Candidat | Échelon | RAM pic total / ajoutée (Mo) | Latence médiane / max (ms) | Réseau | Paquets ajoutés (licences) | torch | Révision, `trust_remote_code` | Accord indicatif (coût, spécialité) | Verdict | Raison |
|---|---|---|---|---|---|---|---|---|---|---|
| SLM juge | 3 | | | | aucun | | GGUF local, sans objet | | | |
| `deberta_xsmall` (MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33, MIT) | 2 | | | | | | | | | |
| `deberta_base` (MoritzLaurer/deberta-v3-base-zeroshot-v2.0, MIT) | 2 | | | | | | | | | |
| `nvidia` (prompt-task-and-complexity-classifier, NVIDIA Open Model License) | 1 | | | | | | | coût seul (étiquettes fixes) | | |
| `gliformer` (knowledgator/gliformer-base-v1, Apache-2.0) | 2 | | | | | | | | | |
| `gliformer_onnx` (talmago/gliformer-base-v1-onnx, licence non déclarée) | 2 | | | | | | | | | |

**Verdicts sans mesure :**

| Candidat | Verdict | Raison |
|---|---|---|
| Decision 1.0 (vLLM Semantic Router) | _relevé à faire (commande 1)_ | Au 2026-09-25 : ni GGUF ni ONNX, ROCm seul. Eos, Sol, Nox et Lux (sur Qwen3.5) sont génératifs : jamais classifieurs coexistants. |
| Llama-Guard-3-1B | écarté | Génératif : jamais classifieur coexistant (règle d'un seul modèle génératif, NFR-2). Il ne servirait qu'en remplaçant le SLM (CAP-9). |
| Qwen3Guard-Gen-0.6B | écarté | Même raison. |
| Arch-Router-1.5B | écarté | Licence commerciale DigitalOcean exigée : incompatible avec NFR-10 (forge du 2026-09-25). |

## Points à surveiller au relevé

- **Langue.** Tous les candidats mesurés sont entraînés en anglais (cartes Hugging Face). Un accord faible sur les prompts français ne change pas le verdict, mais il oriente le passage de bmad-spec : une variante multilingue serait-elle à ajouter aux candidats ?
- **Licence nvidia.** Le banc classe la NVIDIA Open Model License comme compatible, d'après `decision-model-candidates.md` (« usage commercial autorisé »). Ses clauses (attribution, garde-fous) restent à relire pour une remise du code à des clients (NFR-10) avant tout « retenu ». La carte ne cite comme matériel pris en charge que des GPU NVIDIA sous Ubuntu : la voie CPU sous Windows n'est pas annoncée par l'éditeur.
- **nvidia.** Le banc reproduit le code de la carte, relu, sans `trust_remote_code`. La dorsale est construite depuis la configuration de `microsoft/deberta-v3-base`, et les poids viennent du `model.safetensors` du classifieur. Le JSON consigne `load_warnings` : un nombre de clés manquantes différent de zéro signale un écart avec la carte.
- **gliformer.** La voie officielle charge torch : elle sera au mieux « à surveiller ». Seule la conversion ONNX tierce l'évite, mais sa licence n'est pas déclarée.

## Décision

_À remplir après le relevé : le candidat de chaque échelon, ou le repli sur le SLM juge (la leçon « où vit la règle » reste intacte avec le repli)._

## Suite

1. Remplir les tableaux à partir des fichiers JSON de `$OUT`, et compléter le relevé (poste, date).
2. Lancer bmad-spec sur `spec-wavestack-v2` pour mettre à jour `decision-model-candidates.md` (état et date de chaque candidat).
3. Remplacer l'entrée « Test préalable du modèle de décision » du « Deferred » d'`ARCHITECTURE-SPINE.md` par le verdict.
4. Passer la story 6 à `done`.
