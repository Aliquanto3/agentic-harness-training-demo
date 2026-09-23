# Agentic Harness Training Demo

Démonstrateur pédagogique local qui montre, brique par brique, ce qu'un harnais ajoute à un LLM : raisonnement, mémoire, prompt système, outils, RAG, MCP, skills, hooks et sous-agents.

## Contraintes
- Des SLM locaux qui tournent sur CPU/RAM, sans GPU. La qualité des réponses est secondaire, la pédagogie passe avant.
- Backend en Python. Le front peut utiliser des technologies web.
- Doit s'installer depuis GitHub sur un PC pro sans droits administrateur (objectif).
- Headroom et Caveman sont des fonctionnalités de l'application de démo, pas des outils pour le développement.

## Conventions
- Utiliser `uv` pour tout (`uv add`, `uv run`), jamais pip.
- Utiliser `ruff` pour le lint et le formatage, `pytest` pour les tests.
- Code et identifiants en anglais. Textes d'interface et contenus pédagogiques en français.
- Le processus de développement suit la méthode BMAD, dont la configuration est dans `_bmad/`.
