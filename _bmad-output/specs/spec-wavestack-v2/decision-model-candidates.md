# Modèles de décision : échelons, candidats et test préalable

Sources : forge du 2026-09-25 ; relevés sur le PC cible du 2026-10-03, story 6 puis story 7 ([rapport](../../implementation-artifacts/rapport-test-prealable-modeles-de-decision.md), JSON dans `tools/bench/results/2026-10-02-pc-cible-v2s6/` et `tools/bench/results/2026-10-03-pc-cible-v2s7/`) ; pages Hugging Face lues le 2026-10-03. À revérifier à chaque mesure : ce domaine change en quelques semaines.

## Échelle du routage par spécialité

| Échelon | Où vit la règle | Qui la modifie | Candidat au 2026-10-03 |
|---|---|---|---|
| 1. Classifieur à étiquettes fixes (type BERT) | Dans les poids | Celui qui ré-entraîne le modèle | Aucun retenu ; nvidia/prompt-task-and-complexity-classifier à surveiller |
| 2. Encodeur programmable | Dans le texte des critères, lisible et auditable | Celui qui écrit les critères | `deberta_xsmall` par défaut ; mDeBERTa retenu ; `deberta_base` et MiniLM multilingue seulement RAG éteint ; Decision 2.0 Kai écarté sur le PC cible ; tev1 0.8B (Ollama) à mesurer (story 8) |
| 3. SLM utilisé comme juge | Dans le prompt | Celui qui écrit le prompt | Le SLM actif, critères dans le prompt, sortie contrainte |

L'échelon 3 est le plus souple, mais aussi le plus lent (4,7 s de médiane par décision sur le PC cible) et le moins prévisible. Il ne charge aucun modèle de plus : c'est le repli de toute la catégorie.

## Critères du test préalable

Même règle que Headroom (story 12). Un candidat est **retenu** s'il passe tous les critères sur le PC cible :

1. **CPU sous Windows 11, sans droits admin** : roues précompilées, sans compilation ni exécutable à installer (aucune ligne « Building … » dans la sortie de `uv`).
2. **RAM** : pic de RSS mesuré avec le SLM par défaut chargé, ≤ 4 096 Mo (NFR-2), en créneau non génératif du `LoadRegistry`. Le budget complet ajoute l'embedding et le reranker V1 (1 170 Mo).
3. **Latence** d'une décision : médiane ≤ 1 000 ms et maximum ≤ 3 000 ms (seuils validés par Anaël le 2026-10-03). Le SLM juge n'a pas de seuil : il sert de référence au repli.
4. **Hors ligne** : aucune tentative réseau sous la garde d'AD-15.
5. **Code relu et figé** : commit du modèle et versions des paquets consignés par le banc, pas de `trust_remote_code` exécuté sans relecture.
6. **Licence** compatible avec une remise du code à des clients (NFR-10).

Un échec sur la RAM, la latence, le hors-ligne ou une licence interdite donne **écarté**. Un échec non bloquant (torch chargé, licence non déclarée ou à relire) donne **à surveiller**, avec ce qui manque. Pour un candidat retenu, on reporte dans la story qui l'intègre le commit et les versions consignés dans le JSON du banc.

## Candidats

Mesures du 2026-10-03. RAM : pic total, SLM compris, puis RAM ajoutée par le candidat, puis total avec le RAG V1. Latence : médiane / maximum.

| Candidat | Échelon | Licence | Mesures | État au 2026-10-03 |
|---|---|---|---|---|
| SLM juge (Qwen3.5-2B Q4_K_M, sortie contrainte par GBNF) | 3 | celle du SLM V1 | 2 080 / +143 Mo ; 4 708 / 7 157 ms | **Repli (référence)** : hors ligne, dans le budget. |
| `deberta_xsmall`, MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33 (ONNX quantifié, 87 Mo), commit `262ae02f29173eec1c250f90804dc7edc677dcff` | 2 | MIT | 2 285 / +346 Mo (3 455 avec le RAG V1) ; 107 / 253 ms | **Retenu, candidat par défaut** : le seul qui tient le budget avec le RAG V1. Paquets : onnxruntime 1.30.0, tokenizers 0.23.2, huggingface-hub 1.33.0. |
| `deberta_base`, MoritzLaurer/deberta-v3-base-zeroshot-v2.0 (ONNX, 739 Mo), commit `8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8` | 2 | MIT | 3 162 / +1 225 Mo (**4 332** avec le RAG V1) ; 501 / 1 241 ms | **Retenu, RAG éteint seulement** : il dépasse NFR-2 avec le RAG V1. Il départage mieux les spécialités que xsmall (11/20 contre 7/20, accord indicatif). |
| Decision 2.0 Kai 0.6B, vllm-sr/Decision-2.0-Kai-0.6B (2026-09-28, sur Qwen3-0.6B-Base, non génératif, contexte de 8 192), commit relu `881bee413681d80ebeac86afcda8b4138dae516e` | 2 | Apache-2.0 | non mesuré : `ValueError` d'identité au chargement | **Écarté sur le PC cible au commit relu** (critère 1, décision d'Anaël du 2026-10-03) : son code (`checkpoint_fingerprint`, `decision2/_vendor/dev2model/infer.py`) hache des chemins en `\` sous Windows et refuse de charger le modèle. Réessai consigné dans `deferred-work.md` si un commit amont corrige : relecture du nouveau commit, puis mesure (≈ 2,4 Go en FP32 avec torch, dépassement de NFR-2 probable). Passe par `trust_remote_code` et torch : au mieux « à surveiller ». |
| `mdeberta`, MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 (ONNX quantifié, 339 Mo), commit `b5113eb38ab63efdd7f280f8c144ea8b13f978ce` | 2 | MIT | 2 720 / +781 Mo (3 889 avec le RAG V1) ; 216 / 529 ms | **Retenu**, sans remplacer `deberta_xsmall` comme défaut (décision d'Anaël du 2026-10-03) : il tient le budget avec le RAG V1, mais son accord indicatif est plus faible (4/20 et 6/20 contre 12/20 et 7/20). Mêmes paquets que les DeBERTa anglais. |
| `minilm_multi`, MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli (XLM-R, ONNX fp32, 428 Mo), commit `0a71e92a985b6e1ad1828cf67ce9c459639c1dca` | 2 | MIT | 3 005 / +1 067 Mo (**4 175** avec le RAG V1) ; 49 / 123 ms | **Retenu, RAG éteint seulement** (décision d'Anaël du 2026-10-03) : il dépasse NFR-2 avec le RAG V1, et prend plus de RAM que mDeBERTa (ce n'est pas une option légère). Le plus rapide, mais sa décision de coût est dégénérée (« complexe » pour les 20 prompts). |
| nvidia/prompt-task-and-complexity-classifier, commit `fea1121511eafabaf7dd6fc66863dcb04f74defb`, dorsale microsoft/deberta-v3-base | 1 | NVIDIA Open Model License | 3 640 / +1 701 Mo (4 810 avec le RAG V1) ; 437 / 711 ms ; chargement en 29 s | **À surveiller** : torch chargé ; étiquettes fixes, adaptées au routage par coût. Les clauses de la licence (attribution, garde-fous) sont à relire pour une remise à des clients. La carte n'annonce que des GPU NVIDIA sous Ubuntu. |
| Decision 1.0 (vLLM Semantic Router, 2026-09-22) : Kai et Lex 0.6B (encodeurs) ; Eos, Sol, Nox, Lux (génératifs, sur Qwen3.5) | 2 | Apache-2.0 | non mesuré (relevé du 2026-10-02) | **À surveiller** : chemin CPU désormais annoncé par Transformers, avec `trust_remote_code`, en FP32 et avec torch ; ni GGUF ni ONNX (≈ 2,3 Go de safetensors). Remplacé par Decision 2.0 comme candidat suivi. Les variantes génératives tombent sous la règle d'un seul modèle génératif. |
| gliformer-base-v1 (Knowledgator), voie officielle (torch) et ONNX tiers (talmago/gliformer-base-v1-onnx) | 2 | Apache-2.0 ; ONNX tiers sans licence déclarée | voie torch : mesure interrompue à ≈ 4 491 Mo de RSS | **Écarté sur le PC cible** : la voie torch dépasse 4 096 Mo sans même le RAG (RAM, mesure indicative) ; la voie ONNX demande `fast-gliner` 0.3.1, sans roue Windows, dont la compilation Rust échoue (critère 1). |
| Llama-Guard-3-1B | volet cyber | Licence Llama 3.2 | — | **Écarté** : génératif, jamais classifieur coexistant ; il ne servirait qu'en remplaçant le SLM (CAP-9). |
| Qwen3Guard-Gen-0.6B | volet cyber | Apache-2.0 | — | **Écarté** : même raison. |
| Arch-Router-1.5B | — | Licence commerciale DigitalOcean exigée | — | **Rejeté** (forge du 2026-09-25, NFR-10). |

**À mesurer (story 8) : tev1 0.8B**, de Together AI.
- **Modèle.** Qwen3.5 affiné, tag Ollama `tev1:0.8b` (≈ 800 Mo), servi par Ollama 0.35 sur `/v1/systemone` : questions à choix, vrai/faux ou rubrique, réponses avec probabilités. Lu sur ollama.com le 2026-10-03.
- **Déjà connu.**
  - Modèle causal (en chat ordinaire, il répond en prose) : il est génératif au sens de la règle d'un seul modèle génératif. Son verdict reste donc au mieux « à surveiller » tant que cette règle n'est pas revue (décision d'Anaël du 2026-10-03).
  - La licence des poids n'est pas déclarée : seuls les scripts d'entraînement sont sous MIT. À établir avant tout verdict (NFR-10).
  - Seul l'anglais est testé par l'éditeur.
- **Ce que la mesure doit couvrir.** Le modèle tourne dans le processus Ollama, hors de l'enfant de mesure : la RAM compte les deux processus, et le hors-ligne se vérifie aussi côté serveur.
- **Écartés sans mesure.** Les autres modèles de décision d'Ollama 0.35 sortent du budget avec le SLM chargé : tev1 4B (≈ 4,5 Go), Nimble 9B, Clef 27B et Clef Flash 9B.

## Langue

Les prompts sont en français. Les candidats de la story 6 sont entraînés en anglais : 12 à 13/20 d'accord sur le coût, 7 à 11/20 sur la spécialité. Les variantes multilingues mesurées par la story 7 ne font pas mieux : mDeBERTa 4/20 et 6/20, MiniLM 10/20 (toujours « complexe ») et 8/20. L'étiquette attendue est écrite par l'agent et se discute ; l'accord n'est pas un critère du test préalable. Il reste un signal à reprendre avant toute story de routage par spécialité (CAP-8) : critères mieux écrits, ou autre catégorie de modèle.
