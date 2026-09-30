---
title: 'R0 : /api/health avec dossier et commit, CLI « déjà lancée depuis … »'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_revision: '1a0f08cc1b6bde47e0c1c3a477931a3eb8c90dfe'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-corrections-2026-09-30/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Le 2026-09-30, un serveur lancé depuis un autre working tree occupait le port 8420 ; `wavestack` a ouvert le navigateur dessus sans rien dire, et quatre « bugs » n'étaient que ce décalage. Rien ne dit quel dossier ni quel commit sert la page (CAP-1 de `SPEC.md`).

**Approach:** `GET /api/health` rend en plus le dossier du projet et le commit courant (ou `null`). Quand le CLI réutilise une instance saine, il imprime une ligne « déjà lancée depuis {dossier} ({commit}) » par `msg()`, et une seconde ligne d'avertissement si ce dossier n'est pas le sien.

## Boundaries & Constraints

**Always:**
- Réponse de `/api/health` : `{"status": "ok", "version": …, "root": str(config.repo_root()), "commit": "<sha court>" | null}`. Les clés existantes restent.
- Commit lu une seule fois, à la création de l'app, par `git rev-parse --short HEAD` dans `repo_root()` avec un délai court (2 s). Git absent, dossier sans `.git` (archive zip), délai dépassé ou sortie vide : `null`, jamais d'exception ni de message.
- CLI : `_existing_instance_healthy` rend le corps JSON de la réponse (ou `None`) au lieu d'un booléen ; `main` s'en sert pour imprimer, avant d'ouvrir le navigateur, `msg("cli.already_running", lang, root=…, commit=…)`. Commit `null` : variante sans commit (`cli.already_running_no_commit`). Si `root` diffère de `str(config.repo_root())` du processus qui lance (comparaison de chemins résolus, insensible à la casse sous Windows) : ligne supplémentaire `cli.other_tree` qui dit que l'instance vient d'un autre dossier, et comment la remplacer (l'arrêter, ou relancer avec `--port`).
- Une ancienne instance dont `/api/health` n'a pas `root` (version d'avant) : la ligne dit qu'elle est lancée depuis un dossier inconnu (`cli.already_running_unknown`) et `cli.other_tree` s'imprime aussi.
- Nouvelles clés dans `content/messages.yaml` (français), `content/i18n/en/messages.yaml` et `content/i18n/de/messages.yaml` (le terminal est en anglais, mais les trois fichiers ont la clé).
- Le comportement actuel ne change pas : même page ouverte (`/` si prête, sinon `/diagnostic`), code de sortie 0 ; port pris par un autre programme : message `cli.port_taken` et code 1.

**Never:**
- Aucune dépendance nouvelle (pas de GitPython) ; aucun appel à git à chaque requête.
- Ne pas tuer ni relancer l'instance existante.
- Aucun texte en dur dans `cli.py` (contrôle statique de `test_backend_messages.py`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Même dossier | instance saine, `root` identique, commit `abc1234` | « already running from {root} (abc1234) », navigateur ouvert, code 0 | — |
| Autre dossier | `root` différent | la ligne précédente + la ligne `cli.other_tree` | — |
| Sans git | `git` introuvable ou pas de `.git` | `/api/health` → `commit: null` ; CLI : variante sans commit | exception avalée |
| Ancienne instance | corps sans `root` | `cli.already_running_unknown` + `cli.other_tree` | — |
| Corps illisible | 200 mais pas du JSON | traité comme ancienne instance (dossier inconnu) | — |

</intent-contract>

## Code Map

- `src/wavestack/web/app.py:288` -- route `health()` dans `create_app` ; y ajouter `root` et `commit` calculés une fois à la création de l'app.
- `src/wavestack/config.py:50` -- `repo_root()` : racine du dépôt (où vit `wavestack.toml`).
- `src/wavestack/cli.py:103` -- `_existing_instance_healthy(port) -> bool` : à faire rendre le corps (`dict | None`) ; `main()` (ligne ~150) l'utilise dans la branche `reserved is None` ; `TERMINAL_LANGUAGE = "en"`, `msg` déjà importé.
- `src/wavestack/session/diagnostic.py:83` -- exemple d'appel `subprocess` avec délai dans le projet.
- `content/messages.yaml:1073` -- section `cli` (`description`, `port_help`, `port_taken`) ; `content/i18n/en/messages.yaml:155` et `content/i18n/de/messages.yaml` -- surcouches.
- `tests/test_cli_launch.py` -- tests de `main` avec `monkeypatch` de `_try_reserve_port`, `_existing_instance_healthy`, `_existing_instance_ready` ; `_Answer` pour simuler `urlopen`.
- `tests/test_cli_diagnostic.py:53` -- `test_health_endpoint`.
- `tests/test_i18n.py` -- parité de `messages.yaml` (sous-ensemble pour en/de tant que la story 7 n'est pas faite).

## Tasks & Acceptance

**Execution:**
- `src/wavestack/web/app.py` -- fonction `_git_commit(root)` (subprocess, délai 2 s, toute erreur → `None`) et `health()` enrichi -- CAP-1.
- `src/wavestack/cli.py` -- `_existing_instance_health(port) -> dict | None` (remplace `_existing_instance_healthy`, corps JSON ou `{}` si 200 illisible, `None` si injoignable) ; impression des lignes avant l'ouverture du navigateur -- CAP-1.
- `content/messages.yaml`, `content/i18n/en/messages.yaml`, `content/i18n/de/messages.yaml` -- clés `cli.already_running`, `cli.already_running_no_commit`, `cli.already_running_unknown`, `cli.other_tree` -- trois langues.
- `tests/test_cli_launch.py` -- les tests existants suivent le renommage ; un test par ligne de la matrice (sortie capturée par `capsys`).
- `tests/test_cli_diagnostic.py` -- `test_health_endpoint` vérifie `root` et `commit` (chaîne ou `None`) ; test où `_git_commit` échoue (`FileNotFoundError`, `TimeoutExpired`) → `None`.

**Acceptance Criteria:**
- Given WaveStack lancé depuis ce dépôt, when `GET /api/health`, then la réponse contient `root` égal au dossier du dépôt et `commit` égal à `git rev-parse --short HEAD`.
- Given une instance saine sur le port, when `uv run wavestack` depuis un autre dossier, then le terminal dit d'où elle a été lancée et qu'elle vient d'un autre dossier, et le navigateur s'ouvre comme avant.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q tests/test_cli_launch.py tests/test_cli_diagnostic.py tests/test_backend_messages.py tests/test_i18n.py tests/test_web_app.py` -- expected: tout passe.

## Spec Change Log

## Review Triage Log

### 2026-10-01 — Review pass
- verdicts: 20 findings — high 0, medium 1, low 13, false 0, maybe-false 0 (6 constats descriptifs de l'audit d'intention, rejetés)
- findings:
  - `[low]` `[patch]` (verification-gap) garde `resp.status != 200` jamais testée — test `_Answer(…, status=204)` → `None` ajouté.
  - `[low]` `[reject]` (verification-gap) `test_health_endpoint` appelle git sans garde si git manque — poste de dev avec git ; correctif hors sujet.
  - `[low]` `[reject]` (intent-alignment) CLI en anglais et non « dans la langue de la session » de CAP-1 — la story et `invoke_dev_with` fixent le terminal en anglais (Langues 5) ; les trois langues ont les clés.
  - `[low]` `[reject]` (intent-alignment) dossier et commit non affichés dans la page — le critère de succès de CAP-1 vise `/api/health` et le CLI ; la page n'est pas demandée.
  - `[low]` `[reject]` (intent-alignment) aucun test de bout en bout entre serveur et CLI — contrat vérifié de chaque côté ; recette manuelle en phase 3.
  - `[low]` `[reject]` (intent-alignment) tests dans `test_cli_diagnostic.py` et non `test_web_app.py` — « ou équivalent » ; le test de santé y vivait déjà.
  - `[low]` `[reject]` (intent-alignment) « dossier courant » lu comme `repo_root()` et non `os.getcwd()` — la story fixe `repo_root()`.
  - `[low]` `[reject]` (intent-alignment) `other_tree` imprimé quand le dossier est inconnu — prescrit par la matrice de la story.
  - `[medium]` `[patch]` (edge-case) `http.client.HTTPException` (BadStatusLine, IncompleteRead) non attrapée : le CLI plante face à un programme étranger — ajoutée aux exceptions de `_existing_instance_health` et `_existing_instance_ready`, test ajouté.
  - `[low]` `[patch]` (edge-case) lecture du corps non bornée — `resp.read(65536)`.
  - `[low]` `[reject]` (edge-case) `UnicodeEncodeError` à l'impression d'un chemin exotique sur une sortie redirigée — même risque que tous les `print` existants, cas rare.
  - `[low]` `[patch]` (edge-case, avec l'affirmation associée) `.git` testé hors du `try` — déplacé dans le `try`.
  - `[low]` `[reject]` (edge-case) `GIT_DIR`/`GIT_WORK_TREE` hérités — cas rare ; filtrer l'environnement ajoute de la complexité.
  - `[medium]` `[patch]` (edge-case, affirmation) sortie « `{}` ou `None` » non tenue sur une erreur de transport — même correctif que `HTTPException`.
  - `[low]` `[reject]` (blind) `other_tree` affirme un autre dossier quand il est inconnu — prescrit par la story ; la ligne précédente dit « dossier inconnu ».
  - `[low]` `[patch]` (blind) garde non-200 non testée — même correctif que ci-dessus.
  - `[low]` `[reject]` (blind) `root` étranger imprimé tel quel (caractères de contrôle) — le terminal de l'utilisateur, cas improbable ; l'assainir ajoute une branche.
  - `[low]` `[reject]` (blind) `git rev-parse` à chaque `create_app` des tests — une vingtaine de sites, ~30 ms chacun ; aucun effet mesurable (3 288 tests en 2 min 32).
  - `[low]` `[reject]` (blind) commit sans marque « modifié » (`--dirty`) — non demandé par l'intention.
  - `[low]` `[patch]` (blind) commentaire allemand « parité » inexact — reformulé (sous-ensemble jusqu'à la story 7).
  - `[low]` `[reject]` (blind) branches non testées (`root` non chaîne, `_same_folder` en erreur…), casse POSIX, message Ctrl+C et PID — cosmétiques ou hors intention.

## Auto Run Result

- Changement : `/api/health` rend `root` et `commit` (lu une fois par `git rev-parse --short HEAD`, 2 s, `None` sans `.git` ni git) ; le CLI qui réutilise une instance imprime d'où elle a été lancée (`cli.already_running`, `…_no_commit`, `…_unknown`) et avertit si elle vient d'un autre dossier (`cli.other_tree`).
- Fichiers : `src/wavestack/web/app.py` (`_git_commit`, route), `src/wavestack/cli.py` (`_existing_instance_health`, `_same_folder`, `_say_already_running`), `content/messages.yaml` et `content/i18n/{en,de}/messages.yaml` (4 clés), `tests/test_cli_launch.py`, `tests/test_cli_diagnostic.py`.
- Revue : 7 correctifs appliqués (2 medium, 5 low, regroupés en 5 changements), 0 reporté, 13 rejetés (raisons ci-dessus).
- Revue de suivi recommandée : non (deux medium corrigés relèvent d'une même cause, l'exception de transport, désormais testée).
- Vérification : `ruff check`, `ruff format --check` OK ; 5 fichiers de tests : 3 288 passés avant correctifs, 3 290 passés après.
- Risque résiduel : pas de recette réelle à deux working trees (phase 3).
