# Modèles de décision : échelons, candidats et test préalable

Source : forge du 2026-09-25 (recherche du jour). À revérifier au moment du test : ce domaine bouge en semaines.

## Échelle du routage par spécialité

| Échelon | Où vit la règle | Qui la modifie | Candidat actuel |
|---|---|---|---|
| 1. Classifieur à étiquettes fixes (type BERT) | Dans les poids | Celui qui ré-entraîne le modèle | nvidia/prompt-task-and-complexity-classifier |
| 2. Encodeur programmable | Dans le texte des critères, lisible et auditable | Celui qui écrit les critères | DeBERTa-v3 zero-shot NLI aujourd'hui ; Decision 1.0 si son test passe un jour |
| 3. SLM utilisé comme juge | Dans le prompt | Celui qui écrit le prompt | Le SLM actif, critères dans le prompt, sortie contrainte |

L'échelon 3 est le plus souple, mais aussi le plus lent et le moins prévisible. Il ne charge aucun modèle de plus : c'est le repli de toute la catégorie.

## Critères du test préalable

Même règle que Headroom (story 12). Un candidat est **retenu** s'il passe tous les critères sur le PC cible :

1. **CPU sous Windows 11, sans droits admin** : roues précompilées, pas de compilation ni d'exécutable à installer.
2. **RAM** : mesurée avec le SLM par défaut chargé, dans le budget de NFR-2 (4 Go au plus), en créneau non génératif du `LoadRegistry`.
3. **Latence** d'une décision, mesurée sur le poste de référence.
4. **Hors ligne** : aucune tentative réseau sous la garde d'AD-15.
5. **Code relu et figé** : version épinglée, pas de `trust_remote_code` exécuté sans relecture.
6. **Licence** compatible avec une remise du code à des clients (NFR-10).

Un candidat qui échoue est **écarté** (avec la raison) ou **à surveiller** (avec ce qui manque).

## Candidats

| Candidat | Échelon | Licence | État au 2026-09-25 |
|---|---|---|---|
| Decision 1.0, vLLM Semantic Router (sorti le 2026-09-22) : Kai et Lex 0.6B (encodeurs bidirectionnels) ; Eos 0.8B, Sol 2B, Nox 4B, Lux 9B (sur Qwen3.5). Interface : état + questions + critères → Choice, Noul, Score avec distributions. | 2 | Apache-2.0 | **Échoue** : ni GGUF ni ONNX ; mesures sur AMD seulement ; le USAGE.md indique « pas de chemin d'inférence CPU/NVIDIA », ROCm seul ; code d'inférence du dépôt (`trust_remote_code`), risque de chaîne d'approvisionnement. Les variantes sur Qwen3.5 sont génératives : elles tomberaient sous la règle d'un seul modèle génératif. |
| DeBERTa-v3 zero-shot NLI, base et xsmall (MoritzLaurer) | 2 | MIT | Meilleur candidat : ONNX disponible, critères programmables à l'exécution. |
| gliformer-base-v1 (Knowledgator, 2026-09-11) | 2 | Apache-2.0 | À surveiller : ONNX tiers seulement. |
| nvidia/prompt-task-and-complexity-classifier | 1 | NVIDIA Open Model License, usage commercial autorisé | Étiquettes fixes ; adapté au routage par coût. |
| Llama-Guard-3-1B | volet cyber | Licence Llama 3.2 | Génératif : sous la règle d'un seul modèle génératif. |
| Qwen3Guard-Gen-0.6B | volet cyber | Apache-2.0 | Génératif : même remarque. |
| Arch-Router-1.5B | — | Licence d'avril 2026 : licence commerciale DigitalOcean exigée | **Rejeté** (forge). |
