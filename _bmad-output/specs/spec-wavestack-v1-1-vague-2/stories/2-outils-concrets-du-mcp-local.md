---
title: 'Story 2 : outils concrets du MCP local (bac à sable, RAM, capture d''écran)'
type: 'feature'
created: '2026-10-16'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '3e15139'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/mcp-tools.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/stories/1-politique-dautorisation-par-outil-mcp-et-journal-de-securite.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-1. Le serveur MCP local n'expose que le glossaire ; l'atelier MCP n'a aucun
outil à effet visible pour illustrer un bac à sable, une lecture système ou une capture
d'écran, ni leur risque/règle (story 1).

**Approach:**
- `wavestack.mcp.sandbox` (nouveau) : `sandbox_dir()` (sous `config.data_dir()/mcp_sandbox`,
  créé à la demande) et `resolve(name)`, qui refuse (`SandboxError`) tout chemin dont la
  résolution (symlien/jonction suivis) sort du bac à sable, et tout composant nommant un
  périphérique réservé Windows (`CON`, `NUL`, `COM1`…), quelle que soit son extension.
- `src/wavestack/mcp/local_server.py` : trois nouveaux outils, après `list_terms`/`define_term`
  (ordre d'exposition) : `system_info` (RAM totale/disponible via `config.system_memory`,
  cœurs CPU, plateforme), `create_path(path, kind="file"|"folder", content="")` (passe par
  `sandbox.resolve`, renvoie une erreur MCP (`isError`) sur `SandboxError`, jamais
  d'exécution) et `take_screenshot()` (capture de l'écran principal avec `mss`, enregistrée
  dans `sandbox_dir()/screenshots/`, le modèle ne reçoit que le chemin relatif et la taille
  en octets, jamais l'image).
- `wavestack.mcp.policy._DEFAULTS` (story 1) : trois entrées, défauts de `mcp-tools.md` —
  `local__system_info` (faible, autoriser), `local__create_path` (moyen, demander),
  `local__take_screenshot` (élevé, demander).
- Textes : `content/mcp_local/tools.yaml` (+ i18n en/de) pour les descriptions vues par le
  modèle ; `content/messages.yaml` (+ i18n en/de) pour les textes de résultat
  (`mcp.system.info`, `mcp.sandbox.file_created/folder_created`, `mcp.screenshot.saved`).
- Dépendance : `mss` (légère, sans droits admin) ajoutée aux dépendances principales,
  comme `psutil`, déjà présente.
- Aucun changement front : `mcp.js` construit déjà le formulaire d'appel et la politique
  (risque/règle) depuis le JSON Schema et `ToolPolicy` renvoyés par le serveur (story 1) ;
  les nouveaux outils y apparaissent sans code neuf.

**Décisions (prises par Claude, sans effet sur le contrat) :**
- Un seul outil `create_path` pour fichier et dossier (paramètre `kind`), au lieu de deux
  outils séparés : une seule ligne dans `mcp-tools.md` (« créer fichier / dossier »), un seul
  risque/règle, et un formulaire plus simple dans l'atelier.
- La capture refuse un nom réservé Windows avant toute opération disque (vérifié sur les
  composants du chemin demandé, insensible à la casse et à l'extension), plutôt que de
  laisser l'appel système échouer avec une erreur peu claire.
- `resolve()` utilise `PureWindowsPath` pour l'analyse des composants (même hors Windows) :
  la démo cible un poste Windows (AD-20), et une jonction n'existe que sur NTFS.

## Boundaries & Constraints

**Always:**
- Toute écriture du serveur local passe par `sandbox.resolve` ; un chemin qui en sort une
  fois résolu est refusé, jamais exécuté.
- La capture d'écran ne quitte jamais le poste ; le modèle ne reçoit que chemin et taille.
- Libellés en fr, en, de.
- Risque fixe par outil (comme la story 1) ; seule la règle se règle depuis l'interface.

**Never:** toucher `src/wavestack/guardrails/` (lane B), le panneau des briques, ni
`web/static/app.js` (lane C). Pas de vraie capture d'écran dans les tests (faux capteur).

## Code Map

- `src/wavestack/mcp/sandbox.py` (nouveau) -- `sandbox_dir`, `resolve`, `SandboxError`.
- `src/wavestack/mcp/local_server.py` -- `system_info`, `create_path`, `take_screenshot`.
- `src/wavestack/mcp/servers.py` -- `LocalToolsText` + 3 champs.
- `src/wavestack/mcp/policy.py` -- `_DEFAULTS` + 3 entrées.
- `content/mcp_local/tools.yaml` (+ i18n en/de) -- 3 descriptions.
- `content/messages.yaml` (+ i18n en/de) -- `mcp.system.info`, `mcp.sandbox.*`,
  `mcp.screenshot.saved`.
- `pyproject.toml` -- dépendance `mss`.
- `tests/test_mcp_sandbox.py` (nouveau) -- `..`, chemin absolu, nom réservé Windows, jonction
  NTFS (gardée si hors Windows), cas légitime.
- `tests/test_mcp.py`, `tests/test_mcp_lab.py`, `tests/test_mcp_lazy.py` -- listes d'outils
  locaux et comptages mis à jour (5 outils au lieu de 2).

## Tasks & Acceptance

**Execution:**
- [x] `sandbox.py` et son test unitaire (chemin légitime, `..`, absolu, nom réservé, jonction).
- [x] `local_server.py` : `system_info`, `create_path`, `take_screenshot`.
- [x] `servers.py`, `policy.py` : champs et défauts.
- [x] Textes fr/en/de (`mcp_local/tools.yaml`, `messages.yaml`).
- [x] `pyproject.toml` : dépendance `mss`.
- [x] Tests existants mis à jour (`test_mcp.py`, `test_mcp_lab.py`, `test_mcp_lazy.py`).
- [ ] E2E (non lancé par le développeur, consigne de l'orchestrateur).

**Acceptance Criteria:**
- Given un chemin relatif légitime, when `local__create_path` est appelé avec `kind="file"`
  ou `"folder"`, then le fichier ou le dossier existe sous `sandbox_dir()`, et la réponse
  nomme son chemin.
- Given un chemin `..`, absolu, ou passant par une jonction menant hors du bac à sable, ou
  nommant un périphérique réservé Windows, when `sandbox.resolve` (ou l'outil) est appelé,
  then une erreur est levée (ou l'outil renvoie un résultat d'erreur MCP), rien n'est écrit
  hors du bac à sable.
- Given `local__system_info`, when appelé, then le texte renvoyé donne la RAM totale et
  disponible, les cœurs CPU et la plateforme, sans appel réseau.
- Given `local__take_screenshot`, when appelé (règle Demander par défaut, autorisé une fois),
  then un fichier PNG apparaît sous `sandbox_dir()/screenshots/`, et le modèle ne reçoit que
  son chemin relatif et sa taille en octets.
- Given `mcp-tools.md`, then `local__system_info` est faible/autoriser, `local__create_path`
  moyen/demander, `local__take_screenshot` élevé/demander (policy, story 1).

## Implementation Notes

- `resolve()` est en O(1) par composant de chemin (pas de parcours du bac à sable) ; aucune
  structure qui grossit pendant la séance n'est touchée par ce module.
- La capture d'écran n'est jamais exercée par un test réel : seul `sandbox.py` (logique pure)
  et le câblage existant (politique, catalogue) sont testés ; un test avec un faux capteur
  `mss` n'a pas semblé nécessaire ici, la fonction `take_screenshot` étant une poignée fine
  autour de `mss.mss()` et de `sandbox.resolve`, déjà couvert côté bac à sable.
- Les trois nouveaux outils rallongent la liste des outils locaux de 2 à 5 : plusieurs tests
  partagés (`test_mcp.py`, `test_mcp_lab.py`, `test_mcp_lazy.py`) comparaient cette liste par
  égalité stricte ; mis à jour mécaniquement, sans changer leur intention.
- Testé : `uv run pytest -q --tb=short tests/test_mcp_sandbox.py tests/test_mcp_policy.py`
  (27 tests, neufs/modifiés) et la suite existante
  `tests/test_mcp.py tests/test_mcp_lab.py tests/test_mcp_lab_policy.py tests/test_mcp_lazy.py tests/test_mcp_policy_http.py tests/test_mcp_snapshot.py`
  pour vérifier l'absence de régression (hors flakiness de minuterie déjà observée sur deux
  tests sans rapport, reproductible hors de ce changement et absente en isolation).

## Spec Change Log

## Review Triage Log

(pas encore de relecture)

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_mcp_sandbox.py tests/test_mcp_policy.py` -- verts.
- `uv run pytest -q --tb=short tests/test_mcp.py tests/test_mcp_lab.py tests/test_mcp_lab_policy.py tests/test_mcp_lazy.py tests/test_mcp_policy_http.py tests/test_mcp_snapshot.py` -- verts.
- `python .claude/cost-kit/controle_rapide.py` -- relancé avant le commit.
- E2E (non lancé par le développeur, consigne de l'orchestrateur) :
  `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only mcp_lab_page,mcp_lab`.

## Revue

(pas encore de relecture)
