---
idea: WaveStack V2 — modules de formation vendus, construits sur le démonstrateur
status: hardened
date: 2026-09-25
source: ../../specs/spec-agentic-harness-training-demo/SPEC.md (non-objectifs V2)
---

# WaveStack V2 — idée éprouvée

## Ce qu'est la V2

- Un **approfondissement pédagogique** pour une nouvelle audience : les équipes techniques (d'où viennent les erreurs) et la gouvernance technique (méthodes FinOps/GreenOps, cyber, conformité).
- **Ordre** : consultants Wavestone d'abord, puis équipes de gouvernance des clients.
- **On vend des modules construits sur WaveStack.** On ne vend pas le logiciel. La démo client de type UJ-4 marche déjà en V1, c'est un produit dérivé.
- **Un module** = un scénario WaveStack + des slides récap à emporter (c'est là que se trouve la méthode actionnable).

## Principes verrouillés

- **Diagnostiquer dans le contexte, pas dans la réponse.** On montre l'erreur par des mesures d'avant génération : extraits retrouvés, rang du bon extrait face à une réponse attendue connue, position dans le contexte, tokens. La qualité de la réponse finale reste secondaire (SM-C1). SLM sur CPU et 4 Go maintenus.
- Un **petit jeu de questions avec réponses attendues** sur le corpus, limité à des questions de démonstration pour ne pas devenir un banc d'essai.
- **Deux routages.**
  - *Par coût (FinOps/GreenOps)* : décision et tokens réels, plus une estimation d'ordre de grandeur de ce qu'aurait coûté le même tour chez un fournisseur cloud. Prix datés et sourcés, présentés comme une hypothèse.
  - *Par spécialité* : progression en trois échelons. Classifieur à étiquettes fixes (type BERT) → encodeur programmable (DeBERTa zero-shot aujourd'hui) → SLM utilisé comme juge. Message clé : où vit la règle, qui la modifie, qui l'audite.
- **Modèle de décision : même règle que Headroom.** La V2 nomme la catégorie, Decision 1.0 (vLLM SR) est le candidat. Test préalable : CPU sous Windows sans admin, RAM, latence, code relu et figé. **Au 2026-09-25, il échoue** (ni GGUF ni ONNX, pas de chemin CPU fourni).
- **Jamais deux modèles génératifs chargés en même temps** : on décharge puis recharge, avec un message qui prévient de l'attente. Les classifieurs coexistent avec le SLM (NFR-2 à reformuler en « génératifs »).
- **Autres fonctions V2**
  - Multi-agent collaboratif = module (multiplication des tokens, perte d'information entre agents).
  - Indexation de documents propres = gardée, avec un exercice où le participant écrit ses questions de contrôle.
  - Format chat compatible OpenAI = fonction d'appui, pas un module.
- **Dépôt privé** : GitHub privé, puis GitLab interne. Licences compatibles avec la redistribution et contenu non confidentiel restent exigés.
- **Chez le client** : par défaut, démo sur le poste du consultant. La remise du code se négocie au cas par cas.
- **Déclenchement de la V2** (défini maintenant) :
  1. La V1 tient au pilote : SM-1 et SM-3 à leur cible, SM-6 sans repli forcé.
  2. Il y a une demande : *N* profils techniques ou gouvernance demandent un approfondissement, ou une practice ou un client demande un module.
  3. Avant toute présentation client : validation Wavestone de l'usage en clientèle.

## Rejeté

- **Reprendre la liste V2 du SPEC telle quelle** : ces fonctions ont été reportées parce qu'elles alourdissaient la V1, pas parce qu'elles servaient la cible.
- **Grossir le modèle ou passer par un fournisseur externe** pour rendre visible la dégradation de la réponse : cela casse les 4 Go et l'argument de souveraineté.
- **Modèle d'image** : trop lourd, et il ne sert aucune audience visée.
- **Arch-Router-1.5B** : sa licence exige une licence commerciale DigitalOcean.
- **Dépôt public servant de vitrine**.

## Ouvert jusqu'à la session pilote

- La valeur de *N* et les seuils de la condition 2. **Il faut ajouter une question « envie d'approfondir » au questionnaire du pilote.**
- Les cibles de SM-2 à SM-7 (déjà ouvertes dans le SPEC).
- Remettre ou non un zip au client pour les modules pratiques : dépend de SM-5 (réussite de l'installation) et des négociations.
- Garder ou non l'exercice de restitution (« votre message à la direction en 3 phrases ») comme indicateur de l'hypothèse « comprendre → savoir expliquer ».
- Quels modules V2 construire en premier : selon ce que demandent les participants du pilote.
- macOS et Linux (NFR-6), déjà ouvert.

## Points fragiles connus

- GreenOps : l'énergie consommée dans le cloud n'est pas publiée, donc la comparaison énergie reste une hypothèse affichée comme telle.
- La grille de prix publics vieillit vite.
- Decision 1.0 est trop récent. gliformer-base-v1 est à surveiller.

## À corriger dans la V1 (hors V2, par un correct course)

- NFR-10, NFR-11 et CAP-37 supposent un dépôt GitHub public, alors qu'il est privé.
