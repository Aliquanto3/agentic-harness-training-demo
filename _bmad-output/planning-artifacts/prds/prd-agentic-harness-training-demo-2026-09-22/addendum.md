# Addendum au PRD : WaveStack

Contenu destiné à `bmad-ux` et `bmad-architecture`. Rien ici n'engage le périmètre, qui est fixé par `prd.md`.

Les pistes techniques déjà recensées sont dans l'addendum du brief, à lire en complément :
- le repo de référence wavelocalai ;
- les patterns à réutiliser ;
- NiceGUI ou Streamlit : tranché le 2026-09-23 (architecture) — FastAPI, SSE et JS natif ;
- ChromaDB ou sqlite-vec : tranché le 2026-09-23 (architecture) — sqlite-vec.

La veille complète est dans `research-landscape.md`.

## Pistes pour l'architecture

### Moteur d'inférence

La veille propose llama-cpp-python. Une wheel CPU précompilée s'installe par `uv`, sans compilateur ni exécutable à signer. C'est le moteur par défaut le plus sûr sur un poste verrouillé.
- Ollama ou llama-server, déjà lancés sur le poste, viendraient en option (FR-34), via leur point d'entrée natif en texte brut uniquement (`raw` chez Ollama, `/completion` chez llama-server), sans adaptateur de chat ni compatible OpenAI en V1. Ce mode laisse WaveStack appliquer lui-même le gabarit.
- L'addendum du brief jugeait Ollama plus simple : tranché le 2026-09-23 (architecture) — llama-cpp-python en processus par défaut.

### Modèles candidats (2B au plus par défaut)

- Qwen3.5 en 0.8B ou 2B : appel d'outils natif et raisonnement activable.
- Autres pistes :
  - Gemma 4 E2B, dont le parseur d'outils est plus fiable via llama.cpp que via Ollama ;
  - Llama 3.2 1B, sans raisonnement ;
  - IBM Granite, suggéré par l'utilisateur.
- Prévoir un registre des capacités par modèle (FR-33).

### Mesure précoce

Lancer `llama-bench` sur le poste de référence (HP EliteBook, i5 vPro, 16 Go, Windows 11). Objectif : valider NFR-1 et NFR-2 avant de figer le modèle par défaut.

### Budget mémoire (NFR-2 : 4 Go au plus, cible 2 à 3 Go)

Ordres de grandeur, à confirmer par la mesure :
- un modèle de 2B quantifié en 4 bits pèse environ 1,5 Go. S'y ajoute le cache KV, qui croît avec la taille du contexte ;
- le modèle d'embedding et le reranker du RAG doivent rester petits : candidats de 639 Mo et 438 Mo via llama-cpp-python (repli sur fastembed), pour un plafond cumulé de l'ordre de 1,1 Go, vérifié par le budget mémoire ;
- le sous-agent réutilise le modèle déjà chargé, avec un second contexte : pas de second modèle en mémoire ;
- charger chaque composant à l'activation de sa brique, pas au démarrage ;
- plafonner la taille de contexte du modèle, ce qui borne aussi le cache KV.

### Headroom (FR-31)

Bibliothèque Python `headroom-ai`, sous licence Apache-2.0. Sa fonction `compress()` s'insère dans le harnais, avant l'appel au modèle.

### Caveman (FR-25)

Seul le skill, sous licence MIT, est à reprendre. Le proxy, sous licence BSL-1.1, est à éviter (NFR-10).

### MCP local (FR-19)

Serveur Python en stdio, lancé par le harnais. L'addendum du brief confirme qu'il fonctionne sans droits admin ni WSL. Éviter les serveurs Node/npx.

### MCP public (FR-20)

Serveurs testés le 22/09/2026 : tous en Streamable HTTP, tous accessibles en anonyme.

| Serveur | Endpoint | Outils | Poids des descriptions | Prompt de démo |
|---|---|---|---|---|
| data.gouv.fr (retenu) | `https://mcp.data.gouv.fr/mcp` | 10 | environ 2 900 tokens | « Quels jeux de données publics existent sur la cybersécurité ? » |
| Microsoft Learn (retenu) | `https://learn.microsoft.com/api/mcp` | 3 | environ 1 250 tokens | « Comment déployer une stratégie d'accès conditionnel Entra ID ? » |
| AWS Knowledge | `https://knowledge-mcp.global.api.aws` | 5 | environ 2 000 tokens | « Bedrock est-il disponible dans la région Paris ? » (angle souveraineté) |
| DeepWiki | `https://mcp.deepwiki.com/mcp` | 3 | environ 400 tokens | « Explique l'architecture du dépôt python-sdk de MCP » |
| Hugging Face | `https://huggingface.co/mcp` | 4 en anonyme | environ 5 000 tokens | « Trouve un SLM de moins de 2B pour CPU » |

- Context7 est écarté : il répond en anonyme, mais ses en-têtes annoncent une clé d'API facultative. Sans clé, des limites de débit sont probables.
- Vigilance sur data.gouv.fr : sa gestion de session (`Mcp-Session-Id`) a renvoyé une erreur sur une notification sans session. Prévoir un test de fumée au démarrage et un repli sur le serveur MCP local.
- Charger plusieurs serveurs d'un coup dépasse le contexte d'un SLM de 2B. Par exemple, data.gouv.fr, Hugging Face et AWS pèsent ensemble environ 10 000 tokens. C'est une démonstration spectaculaire de l'intérêt du lazy loading (FR-21).

### Outils réseau (FR-13)

API publiques sans clé, qui répondaient toutes le 22/09/2026 :
- jours fériés : `https://calendrier.api.gouv.fr/jours-feries/metropole/{année}.json` ;
- Wikipedia : `https://fr.wikipedia.org/api/rest_v1/page/summary/{titre}`.

Autres candidates :
- communes : `geo.api.gouv.fr` ;
- géocodage : `data.geopf.fr/geocodage`, qui remplace l'API Adresse ;
- taux de change BCE : `api.frankfurter.dev` ;
- météo : Open-Meteo. Il n'est gratuit que pour un usage non commercial, ce qui pose question pour une démo client (NFR-10).

Pistes cyber pour la V2 : le catalogue CISA KEV et NVD, sans clé mais à débit bridé. Un gros résultat d'outil, filtré puis compressé, illustrerait bien Headroom.

Lecture d'une page web (UJ-6, UJ-7). La page doit rester courte : le sous-agent la traite en entier sur CPU, sous la borne de 30 s de NFR-1. Mesures du 23/09/2026 sur la version Markdown des pages de la documentation d'Anthropic (URL suffixée par `.md`) :
- glossaire, `https://docs.claude.com/en/docs/about-claude/glossary.md` : 9 Ko, 1 400 mots, environ 2 000 tokens. Candidat retenu : court, et son contenu (fenêtre de contexte, tokens, RAG, MCP) sert le propos ;
- vue d'ensemble du prompt engineering : 2,7 Ko, trop court pour montrer une économie ;
- vue d'ensemble de l'appel d'outils (tool use) : 38 Ko, environ 10 000 tokens, trop long ;
- hooks de Claude Code et article « Building effective agents » : plus de 200 Ko, hors de portée.

Points de vigilance :
- la documentation d'Anthropic a déjà changé d'adresse (docs.anthropic.com, puis docs.claude.com, puis platform.claude.com) : le scénario teste l'adresse au démarrage, comme les serveurs MCP publics ;
- la page est lue en direct, jamais copiée dans le dépôt (droits d'auteur, NFR-10 et NFR-11). Le repli hors ligne est un long fichier rédigé pour le dossier de démonstration ;
- c'est un outil réseau : le hook de validation humaine (H5) s'y applique.

### Poste verrouillé

- Proxy TLS : `uv --system-certs` et `SSL_CERT_FILE`.
- Voie hors ligne : fichier GGUF sur un partage et `HF_HUB_OFFLINE=1` (FR-34).
- Écoute sur `127.0.0.1`, port configurable.
- Modèles rangés hors de OneDrive.
- Distribution en archive zip si Git est absent.

### Dépôt public (NFR-10, NFR-11)

- Ajouter un fichier de licence au dépôt.
- Vérifier la licence de chaque modèle proposé au téléchargement :
  - Llama 3.2 (Llama Community License) et Gemma (Gemma Terms of Use) ont des conditions propres, à relire avant de les proposer ;
  - Qwen et Granite sont a priori sous Apache-2.0, à vérifier pour chaque version.
- Le corpus RAG de démonstration doit être libre de droits, par exemple des textes publics sous licence ouverte.

## Pistes pour l'UX

- L'addendum du brief propose trois pistes :
  - fusionner les vues LLM et harnais ;
  - faire de la vue LLM une extension de la vue humain ;
  - ajouter un onglet RAG dédié.

  **Tranché le 2026-09-23** : cinq volets masquables (§4.1 du PRD).
- Le compteur de tokens par segment (FR-30) peut servir de fil visuel commun à tous les volets.
- Jauge de remplissage du contexte (FR-41) : Anaël cite comme référence la commande `/context` de Claude Code. Cette commande montre une grille de la fenêtre et la part de chaque source : prompt système, outils, messages, espace libre.
- Le code couleur « local / réseau » du schéma d'architecture (FR-3) porte le message sur la souveraineté. Il doit être immédiatement lisible, y compris en projection (NFR-9).
