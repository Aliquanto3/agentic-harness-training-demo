---
title: 'WaveStack V1.1 vague 1 (2/5) : README et docs d''installation orientés testeur'
type: 'feature'
created: '2026-10-15'
status: 'review'
baseline_commit: '3a8427a40a1ac128fd4aa6e16af2f6a34aa21f57'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-1/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-1/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-1/stories/1-installeurs-en-une-commande.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-3. Le README mettait les commandes PowerShell manuelles avant l'installeur de
la story 1, sans jamais dire qu'elles se tapent dans PowerShell et non dans CMD — la douleur
d'origine du testeur. CAP-4 (démarrage sans scan et bouton « Ajouter d'autres modèles ») n'est
implémentée que par la lane B (story 4) : cette story en documente le comportement cible, décrit
dans `SPEC.md`, sans toucher au code.

**Approach:** Le README met l'installeur (`irm … install.ps1 | iex`, ou `install.bat`) en
premier, avant l'étape manuelle ; chaque bloc de commandes Windows manuelles est précédé de
« dans PowerShell (pas CMD) ». `docs/installation.md` gagne une section « Installeur en une
commande » avant le pas à pas Windows, avec les mêmes précisions PowerShell/CMD, et sa section
« Premier lancement et diagnostic » décrit désormais le démarrage qui ne lit que le dossier des
modèles et les chemins explicites (Ollama excepté, détecté par un appel réseau local bon
marché), et le bouton « Ajouter d'autres modèles… » qui lance la recherche dans le cache
Hugging Face et LM Studio à la demande.

## Boundaries & Constraints

**Always:**
- Dans le README, la première commande montrée est l'installeur ; les étapes manuelles
  viennent après et restent utilisables seules.
- Chaque bloc de commandes manuelles visant Windows (uv, clone, modèle) est introduit par
  « dans PowerShell (pas CMD) » ou équivalent.
- L'URL `irm` du README et de `docs/installation.md` pointe vers le fichier brut du dépôt GitHub
  public (`raw.githubusercontent.com/Aliquanto3/agentic-harness-training-demo/main/...`), sans
  inventer d'autre hôte.
- Le README garde l'URL et le nom de fichier Qwen en clair (`tests/test_installers.py` les
  compare à `install.ps1`/`install.sh` : une seule source de vérité, pas de régression dessus).
- README de 100 lignes au plus, aucune ancre contenant « -- », `tests/test_docs_links.py` vert.
- La description de CAP-4 s'appuie sur `SPEC.md` (dossier des modèles, chemins explicites,
  Ollama au démarrage ; cache Hugging Face et LM Studio seulement à la demande), pas sur le code
  de la lane B (non encore écrit au moment de cette story).

**Never:**
- Pas de modification de `install.bat`/`install.ps1`/`install.sh` ni de `tests/test_installers.py`
  (story 1, déjà revue).
- Pas de modification de `models/discovery.py`, `app.js` ni d'un autre fichier de la lane B
  (story 4) : CAP-4 n'est que documentée ici.
- Pas de nouvelle surcouche i18n : `README.md` et `docs/*.md` n'en ont pas sous `content/i18n/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Lecture du README | Testeur presse de démarrer | Première commande = l'installeur (`irm \| iex`) | — |
| Bloc manuel Windows | Testeur ouvre CMD par réflexe | Le texte juste avant le bloc dit « dans PowerShell (pas CMD) » | — |
| URL Qwen désynchronisée | URL différente entre README et `install.ps1`/`.sh` | `tests/test_installers.py` échoue | AssertionError au test |
| Lien ou ancre cassés | Lien relatif ou ancre absente dans README/docs | `tests/test_docs_links.py` échoue | AssertionError au test |
| CAP-4 non encore codée | Lecteur de `docs/installation.md` avant la story 4 | Texte décrit le comportement cible (lu depuis SPEC.md), sans détail d'implémentation | — |

## Code Map

- `README.md` (modifié) -- installeur en premier, blocs manuels marqués PowerShell/CMD,
  mention du démarrage sans scan et du bouton « Ajouter d'autres modèles ».
- `docs/installation.md` (modifié) -- nouvelle section « Installeur en une commande », blocs
  Windows marqués PowerShell/CMD, « Premier lancement et diagnostic » réécrit pour CAP-4.
- `docs/modeles.md` (lu, non modifié) -- la description du dédoublonnage par éditeur restait
  correcte, pas de changement nécessaire.
- `tests/test_docs_links.py`, `tests/test_installers.py` (lus, non modifiés) -- gardes déjà en
  place, revérifiées contre les nouveaux textes.

## Tasks & Acceptance

- [x] Réordonner le README : installeur d'abord, étapes manuelles ensuite, marquées PowerShell/CMD.
- [x] Ajouter au README la mention du démarrage sans scan et du bouton « Ajouter d'autres modèles ».
- [x] `docs/installation.md` : section « Installeur en une commande », blocs Windows marqués
  PowerShell/CMD, réécriture de « Premier lancement et diagnostic » pour CAP-4.
- [x] `uv run pytest -q --tb=short tests/test_docs_links.py tests/test_installers.py` vert.
- [x] Contrôle rapide (`python .claude/cost-kit/controle_rapide.py`) vert.

**Non vérifié dans cette story** : CAP-4 n'est pas encore codée (story 4, lane B) ; le texte
décrit le comportement cible de `SPEC.md`, à revérifier contre le comportement réel une fois
cette story livrée.

</frozen-after-approval>

## Revue


Revue Opus du 2026-10-15 (commit 82ae19c), comportement CAP-4 vérifié sur `feat/v1-1-4-decouverte-ciblee`.

- high | second avis 1-2 | corrigé | CAP-4 alignée sur la PR #36 : Ollama (appel HTTP et `~/.ollama/models`) lu au démarrage, « Ajouter d'autres modèles… » en fin du menu des modèles de l'Atelier Harnais, fichiers listés sans sondage, sondage au choix.
- medium | second avis 3 | corrigé | `docs/installation.md` plaçait le bouton sur la page de diagnostic : il est dans le menu de l'atelier (`app.js`, `PICK_SEARCH_MORE`).
- medium | revue | corrigé | le README disait que `irm … | iex` installe « sur place » dans un clone : sous `iex`, `$PSScriptRoot` est vide, il installe toujours dans `Documents\WaveStack` (vérifié en mode à blanc). Seul `install.bat` installe sur place.
- medium | revue | corrigé | la dernière sous-section annonçait « une dizaine de minutes après ce clic » : le bouton ne sonde rien, l'attente vient d'Ollama au démarrage.
- medium | second avis 4 | corrigé | consigne proxy du README déplacée avant la commande `irm`.
- medium | second avis 5 | corrigé | `raw.githubusercontent.com` et `codeload.github.com` ajoutés à la liste du proxy.
- medium | second avis 6 | corrigé | options PowerShell : depuis un clone (`.\install.ps1`, `install.bat`) ou par `& ([scriptblock]::Create((irm <url>))) -DryRun` (forme vérifiée en local) ; variables bash devant `bash`.
- medium | second avis 7 | corrigé | `| sh` remplacé par `| bash` (le script exige bash : `set -o pipefail`, shebang bash).
- low | second avis 8 | corrigé | avec 1-2.
- low | second avis 9 | rejeté | `docs/modeles.md` (llama-server) hors du périmètre de la story (blocs d'installation uv, clone, modèle) et non modifié par le commit.
- low | second avis 10 | corrigé | « zip décompressé » précisé ; le README disait déjà « depuis un clone ou un zip ».
- reporté | `irm … | iex` de bout en bout sur un poste vierge derrière le proxy d'entreprise : non lancé (réseau et installation réels). À vérifier à la première passe testeur.
