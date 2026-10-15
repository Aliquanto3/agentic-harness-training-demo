---
title: 'WaveStack V1.1 vague 1 (1/5) : installeurs en une commande'
type: 'feature'
created: '2026-10-15'
status: 'review'
baseline_commit: '61c3e1a7b54d15cfaa20cafffa0a0ac938674fc4'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-1/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-1/brownfield.md'
  - '{project-root}/docs/installation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-1 et CAP-2. L'installation de WaveStack est aujourd'hui une suite de
commandes PowerShell manuelles (README et `docs/installation.md`) : un testeur qui les tape
dans CMD, ou qui se trompe d'étape, peut figer son PC (scan de tous les GGUF du poste).

**Approach:** Trois installeurs à la racine (`install.bat`, `install.ps1`, `install.sh`) qui
font tout en une commande : installer `uv` si absent, récupérer le projet (sur place s'il l'est
déjà, sinon dans un dossier visible sous Documents), déposer le modèle Qwen par défaut, puis
lancer `uv run wavestack`. Idempotent : relancer l'installeur, ou le réexécuter plus tard pour
relancer l'application, ne retélécharge ni le projet ni le modèle déjà présents.

## Boundaries & Constraints

**Always:**
- `install.bat` appelle `install.ps1` via `powershell -NoProfile -ExecutionPolicy Bypass -File`.
- Le dossier Documents s'obtient par `[Environment]::GetFolderPath('MyDocuments')` (chemin réel,
  éventuellement redirigé par OneDrive), jamais `$env:USERPROFILE\Documents` en dur.
- Projet sur place quand le script est déjà dans un clone ou un zip (présence de
  `pyproject.toml` à côté de lui) ; sinon `<Documents>\WaveStack` (`~/Documents/WaveStack` sous
  macOS/Linux).
- Venv, caches `uv` et modèles toujours sous le dossier de données
  (`WAVESTACK_DATA_DIR` ou `%LOCALAPPDATA%\WaveStack` ; `~/.local/share/wavestack` ailleurs),
  jamais sous Documents : `UV_PROJECT_ENVIRONMENT` et `UV_CACHE_DIR` pointent dessus.
- Même URL et même nom de fichier Qwen que le README (`tests/test_installers.py` compare les
  deux ; pas de deuxième source de vérité).
- Idempotent : si `pyproject.toml` existe déjà dans le dossier du projet, pas de nouveau clone ;
  si le fichier du modèle existe déjà, pas de nouveau téléchargement.
- Relancer l'application plus tard est la même commande (`install.bat`/`install.ps1`/
  `install.sh`), qui saute directement au lancement une fois tout déjà en place.
- Surcharges pour les tests et les cas particuliers : `-InstallDir`/`-DataDir`/`-UvInstallDir`
  (PowerShell) et `WAVESTACK_INSTALL_DIR`/`WAVESTACK_DATA_DIR`/`WAVESTACK_UV_INSTALL_DIR`
  (bash) ; `-DryRun`/`WAVESTACK_DRY_RUN=1` n'exécute aucune commande réseau ni d'installation ;
  `-NoLaunch`/`WAVESTACK_NO_LAUNCH=1` n'ouvre pas l'application.
- Respect du proxy d'entreprise tel que documenté (`docs/installation.md`, section proxy) :
  les installeurs n'écrasent ni ne contournent `HTTPS_PROXY`, `UV_SYSTEM_CERTS` ni
  `UV_PYTHON_INSTALL_MIRROR`, laissés au réglage de l'utilisateur.

**Never:**
- Pas de modification du README ni de `docs/` (story 2).
- Pas de téléchargement réel du modèle (1,3 Go) ni d'installation réelle de `uv` pendant les
  tests : `tests/test_installers.py` n'exerce que `-DryRun` et la branche « déjà installé ».
- Jamais le dossier `Documents\WaveStack` ni `%LOCALAPPDATA%\WaveStack` réels d'Anaël pendant les
  tests ou le développement : toujours des dossiers temporaires surchargés.
- Pas de lancement réel de l'application sur le port 8420 pendant les tests.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Dossier sur place | Script lancé depuis un dossier qui contient déjà `pyproject.toml` | `InstallDir` = ce dossier, pas de clone | — |
| Dossier absent | Script lancé hors clone (ex. `irm \| iex`) | `InstallDir` = `<Documents>\WaveStack` | — |
| Projet déjà présent | `pyproject.toml` déjà dans `InstallDir` | Message « pas de nouveau clone », pas d'appel réseau | — |
| Modèle déjà présent | Fichier du modèle déjà dans `models/` du dossier de données | Message « pas de nouveau téléchargement », pas d'appel réseau | — |
| Mode à blanc | `-DryRun`/`WAVESTACK_DRY_RUN=1` | Affiche les dossiers résolus, ne crée ni ne télécharge rien | — |
| URL désynchronisée | URL du modèle différente entre README et un installeur | `tests/test_installers.py` échoue | AssertionError au test |

## Code Map

- `install.bat` (nouveau) -- délègue à `install.ps1`.
- `install.ps1` (nouveau) -- logique complète Windows : résolution des dossiers, `uv`, clone,
  téléchargement du modèle, lancement.
- `install.sh` (nouveau) -- même logique pour macOS/Linux, en bash.
- `tests/test_installers.py` (nouveau) -- URL Qwen alignée avec `README.md`, `install.bat`
  délègue bien, `bash -n` sur `install.sh`, mode à blanc et idempotence de `install.ps1`.
- `README.md` (lu, non modifié) -- source de l'URL Qwen et du dépôt Git.

## Tasks & Acceptance

- [x] Écrire `install.ps1` (résolution des dossiers, idempotence, mode à blanc, surcharges).
- [x] Écrire `install.bat` (délégation à `install.ps1`).
- [x] Écrire `install.sh` (même comportement, bash).
- [x] `tests/test_installers.py` : URL Qwen alignée avec le README, `install.bat` délègue,
  syntaxe `install.sh`, mode à blanc et idempotence de `install.ps1`.
- [x] `uv run pytest -q --tb=short tests/test_installers.py` et `tests/test_docs_links.py` verts.
- [x] Contrôle rapide (`python .claude/cost-kit/controle_rapide.py`) vert.

**Non vérifié dans cette story** (hors poste Windows de développement) : exécution réelle de
`install.sh` sur macOS ou Linux, et exécution réelle de `install.bat`/`install.ps1` avec
téléchargement effectif de `uv` et du modèle sur un poste sans droits admin.

</frozen-after-approval>
