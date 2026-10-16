---
id: SPEC-wavestack-v1-1-vague-1
companions: [brownfield.md]
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# WaveStack V1.1, vague 1 : installation en une commande et lisibilité de l'atelier

## Why

Douleur constatée par un collègue testeur : il a lancé les commandes PowerShell du README dans CMD, et le scan de tous les GGUF du poste a figé son PC. Il a aussi trouvé le menu des modèles et le panneau Séquence peu lisibles. WaveStack doit pouvoir être installé et essayé par d'autres sans accompagnement, sur un PC pro sans droits admin. C'est la priorité de la V1.1, avant l'ouverture aux RSSI (vague 2).

## Capabilities

- **CAP-1**
  - **intent:** Un testeur Windows installe WaveStack avec une seule commande, `install.bat` (double-clic ou CMD) ou `install.ps1` (via `irm | iex`), qui installe uv, le projet et le modèle Qwen par défaut, puis lance l'appli.
  - **success:** Sur un compte Windows sans droits admin et sans uv, une seule commande mène à la page WaveStack ouverte avec Qwen sélectionnable ; relancer l'installeur ne retélécharge ni le projet ni le modèle.
- **CAP-2**
  - **intent:** Un testeur macOS ou Linux obtient le même résultat avec `install.sh`.
  - **success:** Sur macOS ou Linux sans uv, une commande mène à l'appli lancée avec Qwen.
- **CAP-3**
  - **intent:** Le README met l'installeur en premier, et chaque bloc de commandes manuelles précise qu'il se lance dans PowerShell, pas dans CMD.
  - **success:** README de 100 lignes au plus, `tests/test_docs_links.py` vert, première commande = installeur, chaque bloc manuel précédé de « dans PowerShell (pas CMD) ».
- **CAP-4**
  - **intent:** Au démarrage, WaveStack ne lit que son dossier de modèles et les chemins explicites. La recherche ailleurs sur le disque (cache Hugging Face, LM Studio) ne se fait qu'à la demande, via « Ajouter d'autres modèles ».
  - **success:** Un test montre qu'au démarrage aucun dossier hors `models_dir` et chemins explicites n'est parcouru, et que le bouton fait apparaître les modèles trouvés ailleurs.
- **CAP-5**
  - **intent:** Dans le menu des modèles de l'atelier, on distingue d'un coup d'œil les modèles locaux (🏠) et cloud (☁️).
  - **success:** Dans Edge, chaque option porte l'emoji de son hébergement, et les deux groupes ont des fonds différents, contrastés en thème clair et sombre.
- **CAP-6**
  - **intent:** Le panneau Séquence peut s'agrandir pour suivre l'enchaînement des appels.
  - **success:** Sur les pages MCP et RAG, un bouton agrandit le panneau à la quasi-totalité de la fenêtre, et Échap ou le même bouton le referme.

## Constraints

- Aucun droit administrateur : uv et l'appli s'installent dans le profil de l'utilisateur.
- Hors d'un clone ou d'un zip, le code s'installe dans un dossier visible : `Documents\WaveStack` sous Windows (chemin réel du dossier Documents, éventuellement redirigé), `~/Documents/WaveStack` sous macOS et Linux. Depuis un clone ou un zip, l'installation se fait sur place.
- Documents est souvent synchronisé par OneDrive sur un PC pro : l'environnement virtuel, les caches et les modèles n'y vont pas. Relancer l'appli plus tard reste une commande ou un double-clic.
- Les installeurs respectent le proxy d'entreprise comme décrit dans `docs/installation.md` et reprennent l'URL Qwen actuelle du README, sans créer une deuxième source de vérité.
- README : vitrine Windows de 100 lignes au plus, sans ancre contenant « -- » (GitLab). Le détail va dans `docs/`.
- Code en anglais ; textes d'interface en français, avec surcouche en et de sous `content/i18n/`.
- Exécution autonome en 2 lanes sur des fichiers disjoints, fusion automatique sur `main` après relecture et tests verts. Le dépôt est public : chaque fusion publie.
- Poste de 16 Go : une seule suite pytest à la fois, découpée en quarts ; E2E en série, par tranches de 4 à 6 scénarios.

## Non-goals

- Hébergement web avec API gratuites (à trancher en vague 2).
- Installeur graphique (.msi, .exe) ou signé.
- Changement du modèle par défaut.
- Refonte de l'onglet MCP, guardrails, FinOps, vues RSSI et apprenants (vague 2).

## Success signal

Un collègue qui n'a jamais vu WaveStack l'installe seul, sur son PC pro sans droits admin, avec la commande du README, et discute avec Qwen sans que son poste rame.

## Assumptions

- Ollama reste détecté au démarrage : c'est un appel HTTP local bon marché, pas un parcours de disque.
- Edge et Chrome affichent sous Windows les fonds colorés des `<option>` natives ; ailleurs, l'emoji suffit.
- Les modèles du RAG restent téléchargés au premier usage, comme aujourd'hui.
