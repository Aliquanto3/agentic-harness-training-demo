# Addendum — Démonstrateur pédagogique de harnais agentique

Contenu complémentaire au brief : détails techniques, options envisagées, et points ouverts à trancher lors des étapes suivantes (UX, architecture). Rien ici n'est un engagement de scope — voir `brief.md` pour le périmètre validé.

## Repo de référence : wavelocalai

`https://github.com/Aliquanto3/wavelocalai` — proof-of-concept Wavestone sur l'IA locale responsable (perf vs cloud, souveraineté, impact carbone), Streamlit, 4 modules (Hardware/Green IT, Inference Arena, RAG Knowledge, Agent Lab).

**Exécution SLM locale** : Ollama (SDK `ollama` + `langchain-ollama`), modèles type `qwen2.5:1.5b`, CPU-friendly par défaut, GPU détecté mais optionnel (`GPUtil`, `py-cpuinfo`).

**Patterns directement réutilisables comme inspiration** :
- Abstraction "provider" (`src/core/providers/`, interface `ILLMProvider` + factory) — pas nécessaire si le nouveau projet reste 100% local, mais le principe de factory pour changer de modèle est transposable.
- Pattern outil = fonction pure + wrapper LangChain + métadonnées UI (`src/core/agent_tools.py`) — modèle direct pour le module Outils du démonstrateur.
- RAG en stratégies interchangeables, un fichier par stratégie (`naive.py`, `hyde.py`, `self_rag.py` derrière `strategies/base.py`) — architecture qui correspond exactement au besoin "passer d'une archi RAG à l'autre" mentionné dans le brief initial (RAG avancé reste V2, mais la structure de code est réutilisable dès la V1 pour le RAG simple).

**Ce qui ne sert pas / doit être repensé** :
- Multi-agent via CrewAI : arborescence de dépendances lourde, à éviter pour un démonstrateur CPU léger.
- Pas de `uv` (pip + requirements.txt + venv) : le nouveau projet impose `uv`, la gestion de dépendances est à refaire de zéro.
- Aucun MCP, skill ou hook dans le repo : ces briques n'ont pas de précédent réutilisable, conception entièrement nouvelle.
- Providers cloud (Mistral/OpenAI/Anthropic API) hors sujet pour un outil pensé "local only".

## Recherche de marché (projets pédagogiques comparables)

Aucun projet trouvé avec une UI de démonstration à composants activables un par un comme celle envisagée — l'existant est en tutoriel Markdown/notebook progressif :
- `jungangc/agent_learning` (mirror `Haozhe-Xing/agent_learning`) — livre/tutoriel 188 pages, LLM → outils → mémoire → planning → RAG → contexte → harnais → skills → multi-agent → éval → sécurité, EN/中文.
- `agenticloops-ai/agentic-ai-engineering` — tutoriels construisant la boucle agent, l'exécuteur d'outils, la couche mémoire, le harnais d'éval, de base à avancé.
- `ps06756/build-ai-agents-from-scratch` — chapitres progressifs ajoutant mémoire, RAG, tool calling.
- `santiagomora2/learn-agentic-rag-end-to-end` — 6 leçons progressives embeddings/agents/RAG.
- `RyanAlberts/best-of-Agent-Harnesses` — liste classée de 100+ harnais agentiques, utile comme référence de paysage, pas un tutoriel.

Confirme que l'angle "UI à toggles progressifs" du projet est différenciant plutôt que redondant.

## Pistes techniques (état de l'art 2026, non engageantes — à trancher en architecture)

- **SLM CPU-friendly** : Qwen3.5 (0.8B–9B, variantes 1.5B/4B), Phi-4-mini (3.8B), Llama 3.2 (1B/3B), et les modèles **IBM Granite** (suggestion utilisateur — petites tailles CPU-friendly, disponibles via Ollama) ; format GGUF, servis via `llama-cpp-python` ou Ollama (Ollama = plus simple à opérer, cohérent avec l'approche déjà validée dans wavelocalai).
- **Frontend/backend Python sans droits admin** : Streamlit (simplicité, familier via wavelocalai) vs NiceGUI (plus de contrôle d'état, potentiellement mieux adapté à une UI en volets synchronisés avec activation/désactivation dynamique de composants).
- **RAG local sans serveur** : ChromaDB (mode embarqué, déjà utilisé dans wavelocalai) vs sqlite-vec (empreinte minimale, cohérent avec l'objectif "installable sans droits admin").
- **`uv` et MCP sans droits admin sur Windows** : confirmé faisable — `uv` s'installe et fonctionne entièrement en espace utilisateur (`%LOCALAPPDATA%`) ; un serveur MCP Python lancé via `uv run` (stdio) ne nécessite pas de droits admin ni WSL (contrainte qui concerne surtout les serveurs MCP Node/npx).

## Points ouverts (à trancher hors de ce brief)

- **Nom du projet** : pas encore choisi. Piste évoquée : passer par `bmad-brainstorming` pour un atelier de nommage dédié, à faire avant ou après la PRD selon la préférence de l'utilisateur.
- **Fusion des vues UI "LLM" et "harnais"** : le brief initial posait la question de fusionner ces deux vues, ou de faire de la vue "LLM" une extension de la vue "humain", plus un onglet dédié RAG à un moment. Décision UX à prendre dans `bmad-ux`, pas dans ce brief.
- **Liste définitive des outils de démonstration** : calcul/graphique, heure, email, recherche web, API publique, fichier local sont des exemples cités par l'utilisateur, pas un engagement de scope — à prioriser en architecture/epics.
- **Skills "amusants" (ex. Caveman)** : mentionné comme exemple de skill avec un outil de comptage de tokens avant/après ; à conserver comme piste d'illustration mais pas un engagement de scope V1.
