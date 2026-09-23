# Veille : paysage et contraintes techniques (2026-09-22)

Synthèse produite par un sous-agent de recherche web pendant la phase Discovery du PRD. Les chiffres sont indicatifs et issus en partie de sources secondaires.

## 1. Outils comparables et manque à combler
- **Visualiseurs des internes du LLM.** Transformer Explainer, AnimatedLLM et LLM Visualizer montrent l'intérieur du modèle (tokens, attention), mais jamais le harnais qui l'entoure.
- **Cours et notebooks.** Microsoft AI Agents for Beginners est lié à Azure et au cloud. Le HF Agents Course (smolagents) fonctionne en local mais reste orienté code, sans vue visuelle pas à pas. Le cours DeepLearning.AI sur LangGraph est dans le même cas.
- **Playgrounds.** LangGraph Studio, OpenAI Playground et la démo Mem0 s'adressent aux développeurs, montrent une seule fonctionnalité ou demandent le cloud.
- **Manque identifié.** Aucun outil ne réunit, dans une même interface locale :
  - l'activation des briques une à une, en partant du LLM nu ;
  - l'affichage du contexte réel envoyé au modèle, avec le décompte des tokens ;
  - un fonctionnement sur CPU, hors ligne ;
  - une interface en français, pensée pour une formation animée.

  Les notions de skills, hooks et sous-agents sont particulièrement rares dans le matériel pédagogique existant.

## 2. Inférence CPU sans droits admin (Windows)

| Option | Sans admin ? | Remarques |
|---|---|---|
| llama-cpp-python | Oui | Wheel CPU précompilée, compatible `uv`, aucun compilateur requis. |
| llama.cpp `llama-server` | Oui | Distribué en zip. Les .exe non signés peuvent être bloqués par SmartScreen ou AppLocker. |
| Ollama | Oui | Installation par utilisateur dans `%LOCALAPPDATA%`. Quelques problèmes signalés à l'exécution sans droits admin. |
| LM Studio | Oui | Installation par utilisateur. Application graphique sous licence propriétaire. |
| llamafile | Oui | Très souvent signalé par les antivirus. |

- **Piste avancée par la veille :** llama-cpp-python comme moteur, tout en Python. Ollama et LM Studio deviennent des moteurs optionnels, branchés derrière un adaptateur compatible OpenAI.
- **Petits modèles (4B paramètres ou moins) avec appel d'outils et raisonnement :**
  - Qwen3.5 0.8B, 2B et 4B, sortis en mars 2026 : appel d'outils natif, raisonnement activable ou non ;
  - Qwen3-4B ;
  - Gemma 4 E2B et E4B : parseur d'appels d'outils défaillant dans Ollama, llama.cpp recommandé à la place ;
  - SmolLM3-3B : appel d'outils plus faible ;
  - Phi-4-mini, 3.8B : pas de bascule native vers un mode raisonnement ;
  - Llama 3.2 1B et 3B : pas de mode raisonnement.
- **Débit sur CPU (quantification Q4, portable récent) :**
  - modèles de 3 à 4B : environ 8 à 15 tokens/s ;
  - modèles de 0.8 à 2B : environ 20 à 40 tokens/s (estimation).
  - Le traitement du prompt est lent. Le contexte RAG et les schémas d'outils ajoutent plusieurs secondes avant le premier token. Cela plaide pour la gamme 0.8 à 2B en démo.
- **Mémoire vive :** 8 Go suffisent pour un modèle de 2B ou moins. Viser 16 Go pour un modèle de 4B.

## 3. Headroom et Caveman
- **Headroom** (chopratejas / Headroom Labs, licence Apache-2.0) est une couche locale de compression du contexte. Elle compresse ce qui entre dans le modèle : sorties d'outils, JSON, code, morceaux RAG, historique.
  - Mécanismes : un routeur par type de contenu ; CacheAligner, qui préserve le cache KV ; CCR, qui permet au modèle de récupérer les originaux.
  - Formes disponibles : bibliothèque Python (`headroom-ai`, fonction `compress()`), proxy ou MCP.
  - Gain annoncé : 60 à 95 % de tokens en moins, selon l'éditeur.
  - https://github.com/chopratejas/headroom
- **Caveman** (JuliusBrussee, skill sous licence MIT, proxy sous licence BSL-1.1) est un skill qui fait répondre le modèle en style télégraphique. Il comporte les niveaux lite, full et ultra.
  - Gain annoncé : environ 65 %.
  - Mesure de JetBrains : environ 52 % de tokens de sortie en moins par réponse, mais environ 8,5 % seulement sur l'ensemble des tâches, sans perte de qualité.
  - https://github.com/juliusbrussee/caveman
- **Intérêt pédagogique :** Caveman réduit la **sortie** du modèle et agit par le prompt (brique skill ou prompt système). Headroom réduit l'**entrée** (context engineering, middleware du harnais). En local, le bénéfice se mesure en latence, pas en coût.

## 4. Pièges sur un poste d'entreprise verrouillé
- **Proxy TLS (type Zscaler).**
  - uv : option `--system-certs` ou variable `SSL_CERT_FILE`.
  - Ollama : variable `HTTPS_PROXY`.
  - requests et Hugging Face : variable `REQUESTS_CA_BUNDLE`.
- **Téléchargement des modèles bloqué.** Prévoir une voie hors ligne :
  - un fichier GGUF prérécupéré, sur clé USB ou partage réseau ;
  - `HF_HUB_OFFLINE=1` ;
  - une vérification de somme de contrôle.
- **SmartScreen, AppLocker ou antivirus.** Ils bloquent les .exe non signés. Les wheels Python pures exécutées par un interpréteur autorisé sont le plus sûr.
- **Réseau.** Écouter sur `127.0.0.1` uniquement : c'est ce qui évite l'invite du pare-feu, qui exige des droits admin. Rendre le port configurable.
- **Divers :**
  - ranger les modèles hors de OneDrive ;
  - Git peut être absent du poste : proposer un zip GitHub ;
  - la politique d'exécution PowerShell peut bloquer le script d'installation : `uv.exe` autonome ;
  - mesurer tôt avec `llama-bench` sur un portable d'entreprise représentatif.
