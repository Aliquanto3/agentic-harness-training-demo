---
title: 'technical research: guardrails utilisables sur CPU pour WaveStack'
type: 'technical'
topic: 'guardrails utilisables sur CPU'
decision: 'Choisir un ou plusieurs guardrails pour la démo WaveStack, exécutables sur CPU/RAM (PC pro 16 Go, sans GPU), pédagogiques avant tout'
source: 'run (recherche web, ici)'
status: draft
preset: 'standard'
validation: 'normal'
created: '2026-10-15'
updated: '2026-10-15'
---

# Guardrails utilisables sur CPU — recherche technique

**Décision servie :** choisir, pour la démo WaveStack (SLM locaux, CPU/RAM, PC pro 16 Go, aucun GPU), un ou des guardrails illustrant la brique « sécurité / garde-fous » du harnais, sans dégrader l'expérience pédagogique par une latence ou une consommation RAM excessives.

**Avertissement méthodologique :** cette note ne contient aucun exemple de contenu dangereux réel. Les mentions de « faux positifs », « sur-blocage » ou « contenu toxique » restent génériques, sans texte d'attaque reproductible.

**Cadre de sélection (exigences) :**
- Contrainte dure : tourne sur CPU seul, empreinte RAM compatible avec un poste à 16 Go déjà occupé par un ou plusieurs SLM.
- Contrainte dure : licence permettant un usage local, pédagogique, redistribuable depuis un dépôt (pas de clé API cloud obligatoire).
- Préférence forte : prise en charge du français, au moins en filtrage d'entrée.
- Préférence : léger à installer sans droits admin (poids du modèle, dépendances C++).
- Secondaire : taux de faux positifs documenté, pour pouvoir expliquer pédagogiquement le compromis sécurité/utilisabilité.

## 1. Vue d'ensemble du paysage (2025–2026)

Le marché des « guardrails » se scinde en deux familles d'architecture, un compromis central pour un contexte CPU :
- **Classifieurs encodeurs** (BERT/DeBERTa-like) : petits (quelques Mo à quelques centaines de Mo), inférence en ~10–100 ms, usage mémoire sous 1 Go — adaptés au CPU. Exemples : Prompt Guard, Granite-Guardian-HAP.
- **Juges décodeurs / LLM** (Llama Guard, Granite Guardian 2B-8B, ShieldGemma, WildGuard, gpt-oss-safeguard) : plus précis et multi-catégories, mais plus lourds, pensés pour GPU ; les variantes quantifiées (INT4, GGUF) ramènent certaines tailles 1B dans une zone CPU-compatible [8][9].

Une nouvelle vague de modèles 2025-2026 (SGuard-v1, GLiGuard, PolyGuard, DynaGuard, WildGuard, gpt-oss-safeguard) élargit le choix mais la plupart restent récents, peu benchmarkés en CPU et/ou non spécifiquement optimisés pour le français [1].

## 2. Comparatif par outil

| Outil / modèle | Licence | Taille | RAM estimée (CPU) | Latence CPU | Français | Faux positifs connus |
|---|---|---|---|---|---|---|
| **Llama Prompt Guard 2 — 22M** | Gated, licence Meta (Llama 4 Community selon une source tierce — à vérifier sur la fiche HF officielle avant usage) [2] | ~70M paramètres (nommage "22M" trompeur), base DeBERTa-xsmall | Quelques centaines de Mo | ~92 ms/texte annoncé par un tiers (non vérifié par Meta), -75 % vs la variante 86M [2] | Entraîné surtout anglais ; la 86M couvre aussi des attaques non-anglaises, pas la 22M [2] | Détecteur d'injections/jailbreaks, pas de chiffre de FP publié dans les sources trouvées |
| **Llama Prompt Guard 2 — 86M** | Idem, licence à confirmer | ~86M / 0,3B selon la source (incohérence HF à vérifier) | ~1 Go | Signalé « lent » sur CPU par un guide tiers [2] | Couvre attaques EN + non-EN | Idem, pas de chiffre trouvé |
| **Llama Guard 3-1B-INT4** | Licence Meta Llama (gated) | ~440 Mo (quantifié 4 bits poids / 8 bits activations) [3] | &lt;1 Go | ≥30 tokens/s, TTFT ≤2,5 s sur CPU mobile grand public (papier Meta, ExecuTorch+XNNPACK) [3] | Couvre FR parmi 7 langues non-anglaises testées par Meta (FR, DE, HI, IT, PT, ES, TH) [6] | Sur Llama Guard (taille non précisée) : 1,83 % de rejets sur prompts bénins (1805 prompts), 2,20 % sur OR-Bench — hausse du taux de faux refus de +27 % sur FR vs +95 % sur EN quand utilisé en filtrage [3][5][6] |
| **Llama Guard 3-1B (standard, GGUF)** | Licence Meta Llama (gated) | FP16 ≈3 Go ; Q8 ≈1,6 Go ; Q4_K_M ≈0,9 Go (chiffres communautaires non officiels) [3] | ~1–3 Go selon quantification | Non mesuré dans les sources trouvées | Idem ci-dessus (même famille) | Idem |
| **NeMo Guardrails (NVIDIA)** | Apache 2.0 (+ un second tag « Other/Proprietary » sur PyPI, contenu non vérifié) [4] | Paquet léger (wheel ~5 Mo sur une version 2025), mais orchestre des modèles tiers (donc le vrai poids dépend du modèle branché) [4] | Dépend du modèle branché ; le paquet lui-même est léger | Nettement plus lent sur CPU que GPU sur le test « jailbreak heuristic » NVIDIA (~2000–3200 unités CPU vs ~115–157 GPU, unité non confirmée) [4] | Heuristique « longueur/perplexité » documentée **anglais uniquement**, plus de faux positifs attendus en non-anglais ; fonctions multilingues récentes sans confirmation explicite du FR [4] | Alerte officielle NVIDIA : forte hausse des faux positifs si utilisé en non-anglais |
| **Microsoft Presidio (+ extension `presidio-fr`)** | MIT | Dépend des modèles NLP branchés (spaCy FR, ex. `fr_core_news_*`, quelques centaines de Mo) | Modéré (spaCy CPU) | Non chiffré ; spaCy CPU est généralement rapide (dizaines de ms/texte) mais non mesuré ici | Pas nativement optimisé FR ; extension tierce `presidio-fr` (MIT) ajoute NIR, SIREN/SIRET, n° fiscal, plaque, passeport [7] | Benchmark tiers (non officiel, 30/09/2026, synthétique) : Presidio + presidio-fr + spaCy FR seul → précision 0,730 (921 fausses détections) ; combiné à un second modèle (nym) + regex → précision 0,978 (92 fausses détections) [7] |
| **Granite-Guardian-HAP-38M (IBM)** | Apache 2.0 (famille Granite, à confirmer sur la fiche modèle) | 38M paramètres | Très faible (&lt;500 Mo) | Le plus rapide de la gamme IBM, explicitement visé CPU/sans GPU/AIU par IBM [9] | Toxicité uniquement, modèle anglais ; couverture FR non documentée dans les sources trouvées | Classifieur binaire toxicité seul — pas de couverture jailbreak/PII |
| **Granite Guardian 3.1-2B / 3.2-3B-A800M** | Apache 2.0 (à confirmer) | 2–3B | Faible à modérée en quantifié, mais aucun chiffre CPU trouvé | Non mesuré sur CPU dans les sources trouvées (déploiements documentés en vLLM/GPU) [9] | Non documenté spécifiquement | Granite-Guardian-3.3-8B : 81,0 % d'exactitude sur un comparatif cité (vs 62,4 % pour ShieldGemma-2B) — mais version 8B, pas la 2-3B [9] |
| **ShieldGemma (texte, 2B/9B/27B)** | Licence Gemma ouverte | 2B minimum | GPU visé en pratique ; pas de chiffre CPU trouvé | Non mesuré CPU | Non documenté FR spécifiquement | 62,4 % d'exactitude sur le comparatif cité ci-dessus, plus faible que Granite Guardian 8B [9] |
| **SGuard-v1 (Samsung SDS, 2026)** | Non vérifiée dans les sources trouvées | 2 modèles de 2B (contenu + jailbreak) | Non documenté CPU | Non documenté | Couvre 12 langues selon l'annonce du projet (FR probable mais non confirmé nommément) [1] | Trop récent, pas de benchmark indépendant trouvé |
| **GLiGuard (Fastino, mai 2026)** | Non vérifiée | 300M, architecture encodeur | Potentiellement CPU-compatible (classe encodeur) mais aucun chiffre trouvé | Non documenté | Non documenté | Trop récent pour un retour d'usage |
| **gpt-oss-safeguard (OpenAI, 2026)** | Apache 2.0 | 20B / 120B | Hors budget CPU/16 Go dans les deux tailles | Non pertinent ici | Non documenté | Juge « à politique libre », mais hors gabarit pour la démo |

Sources numérotées en section 4.

## 3. Recommandation classée pour la démo WaveStack

1. **Granite-Guardian-HAP-38M (IBM, Apache 2.0)** — le choix le plus sûr pour une démo CPU : explicitement conçu pour tourner sans GPU, empreinte minimale, licence permissive, facile à faire tenir dans le budget RAM avec un SLM déjà chargé. Limite pédagogique honnête : ne couvre que la toxicité, pas les injections de prompt ni les PII — à présenter comme « un guardrail parmi d'autres », pas une solution complète. Aucune donnée FR trouvée : à tester avec quelques prompts français neutres avant de s'y appuyer dans la démo.
2. **Llama Guard 3-1B-INT4 (Meta)** — le meilleur compromis couverture/poids si la démo veut montrer un guardrail multi-catégories (pas seulement toxicité) et illustrer le compromis sécurité/faux refus avec des chiffres officiels Meta (y compris pour le français, chiffré par Meta lui-même). Contrepartie : licence gated Meta à faire valider (conditions d'usage/redistribution), et l'effet de filtrage en français reste nettement plus faible qu'en anglais d'après les propres chiffres de Meta (38 % de réduction de violation en FR vs 75 % en EN) — bon point pédagogique à exposer tel quel.
3. **Microsoft Presidio + extension `presidio-fr` (MIT)** — pertinent si la démo veut illustrer un guardrail de nature différente (détection de PII plutôt que de contenu dangereux), avec une vraie prise en charge française via l'extension communautaire. À calibrer (seuils de confiance) car le benchmark tiers trouvé montre une précision faible en configuration par défaut (0,73) et un besoin de combinaison de modèles pour descendre les faux positifs. Licence la plus simple du lot (MIT).
4. **Llama Prompt Guard 2 (22M puis 86M)** — utile en complément pour illustrer spécifiquement la détection d'injections de prompt/jailbreak, mais à placer après les trois précédents : couverture française non garantie, licence gated à vérifier précisément (sources contradictoires sur la version de licence Llama applicable), et le point de latence CPU du modèle 86M vient d'une seule source tierce non vérifiée.
5. **NeMo Guardrails (NVIDIA, Apache 2.0)** — à écarter comme moteur principal pour cette démo CPU : c'est un framework d'orchestration (rails programmables), pas un modèle léger, et NVIDIA documente lui-même une latence CPU nettement supérieure au GPU sur son test de référence, plus un avertissement explicite de hausse des faux positifs en non-anglais sur l'heuristique de base. Il resterait intéressant pédagogiquement pour montrer *la notion* de rails programmables (pas pour l'exécution en continu sur le poste).
6. **ShieldGemma / Granite Guardian 2B+ / familles 2025-2026 (SGuard-v1, GLiGuard, PolyGuard, DynaGuard, gpt-oss-safeguard)** — à ne pas retenir maintenant : soit hors gabarit CPU/16 Go (8B-120B), soit trop récentes pour disposer d'un retour CPU ou français indépendant. À revoir dans un futur rafraîchissement de cette recherche (fraîcheur recommandée ≤ 6 mois sur ce terrain qui évolue vite).

**Hedge de réversibilité :** démarrer avec Granite-Guardian-HAP-38M (le moins coûteux à essayer), garder Llama Guard 3-1B-INT4 en option de bascule si la démo a besoin de couvrir plus de catégories de risque — les deux sont interchangeables derrière une même interface d'appel, ce qui limite le coût de changement d'avis.

## 4. Sources

1. Mozilla AI — GitHub issue « Tracking: integrate new open-weight guardrail models (June 2026 sweep) » : https://github.com/mozilla-ai/any-guardrail/issues/179 ; Mozilla AI blog, « Can open-source guardrails really protect AI agents? » : https://blog.mozilla.ai/can-open-source-guardrails-really-protect-ai-agents/ (accès 2026-10-15)
2. Meta, fiche modèle Llama Prompt Guard 2 : https://www.llama.com/docs/model-cards-and-prompt-formats/prompt-guard/ ; Hugging Face, meta-llama/Llama-Prompt-Guard-2-86M et -22M : https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M, https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-22M ; guide tiers (chiffres de latence non vérifiés par Meta) : https://medium.com/@sathishkumar.babu89/running-llama-prompt-guard-2-locally-a-complete-guide-to-rag-security-5bd7923c1169 (accès 2026-10-15)
3. Meta AI Research, « Llama Guard 3-1B-INT4: Compact and Efficient Safeguard for Human-AI Conversations » : https://arxiv.org/abs/2411.17713 (arXiv 2411.17713) ; QuantFactory, Llama-Guard-3-1B-GGUF : https://huggingface.co/QuantFactory/Llama-Guard-3-1B-GGUF ; Nodepedia, fiche Llama-Guard-3-1B : https://nodepedia.com/models/llama-guard-3-1b/ (accès 2026-10-15)
4. NVIDIA, documentation « Jailbreak Protection » (table de latence CPU/GPU) : https://docs.nvidia.com/nemo/guardrails/configure-guardrails/guardrail-catalog/jailbreak-protection ; dépôt GitHub NVIDIA-NeMo/Guardrails : https://github.com/NVIDIA-NeMo/Guardrails ; PyPI nemoguardrails 0.12.0 : https://pypi.org/project/nemoguardrails/0.12.0/ (accès 2026-10-15)
5. HE-Guardrail, « A Homomorphic Guardrail Against Jailbreak Attacks for Encrypted Large Language Model Inference » : https://arxiv.org/pdf/2609.21484 (chiffres de faux positifs de Llama Guard sur prompts bénins et OR-Bench) (accès 2026-10-15)
6. Meta, « The Llama 3 Herd of Models » (Table 25, taux de violation et de faux refus par langue pour Llama Guard 3) : https://arxiv.org/pdf/2407.21783 ; Llama Guard 4, fiche modèle NVIDIA Build : https://build.nvidia.com/meta/llama-guard-4-12b/modelcard ; GuardBench (EMNLP 2024) : https://aclanthology.org/2024.emnlp-main.1022.pdf (accès 2026-10-15)
7. Microsoft, Presidio FAQ (sources de faux positifs, atténuations) : https://github.com/microsoft/presidio/blob/main/docs/faq.md ; xiao98/presidio-fr (extension française, MIT, benchmark auto-publié daté 2026-09-30) : https://github.com/xiao98/presidio-fr (accès 2026-10-15)
8. Comparatif général d'architecture encodeur vs décodeur pour les guardrails : Mozilla AI, GitHub issue « Benchmark-backed model cards » : https://github.com/mozilla-ai/any-guardrail/issues/194 (accès 2026-10-15)
9. IBM Research, « How we slimmed down Granite Guardian » : https://research.ibm.com/blog/ibm-granite-guardian-5b-3b ; Hugging Face, ibm-granite/granite-guardian-hap-38m et -125m : https://huggingface.co/ibm-granite/granite-guardian-hap-38m, https://huggingface.co/ibm-granite/granite-guardian-hap-125m ; dépôt GitHub ibm-granite/granite-guardian : https://github.com/ibm-granite/granite-guardian ; Turing Post, « Guardian Models: Llama Guard, ShieldGemma & DynaGuard » (comparatif d'exactitude ShieldGemma-2B vs Granite-Guardian-3.3-8B) : https://www.turingpost.com/p/guardianmodels (accès 2026-10-15)

## 5. Limites de cette recherche

- Recherche menée en un seul passage (standard, profondeur 2), via recherche web générique uniquement — pas d'accès direct aux fiches modèles gated (Llama) ni test CPU réel sur le poste cible.
- Plusieurs chiffres de latence/taille proviennent de sources tierces non officielles (blogs, guides) signalées comme telles ; à vérifier avant tout engagement ferme.
- Aucun modèle n'a été téléchargé ni exécuté dans le cadre de cette recherche, conformément à la consigne.
- Fraîcheur : le paysage des petits guardrails évolue vite (plusieurs modèles sortis en 2026) ; recommandé de rafraîchir cette note dans 3 à 6 mois, notamment sur SGuard-v1, GLiGuard et PolyGuard dont le retour d'usage manque encore.
