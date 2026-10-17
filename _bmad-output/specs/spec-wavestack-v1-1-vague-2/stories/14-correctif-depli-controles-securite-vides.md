---
title: 'Correctif (14) : les dépliés des contrôles actifs de la page Sécurité ne sont jamais vides'
type: 'bugfix'
created: '2026-10-17'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '7239117'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sur `/security`, dans l'état capturé pour le GIF (dossier de données neuf, garde-fous
non installés, GitHub non connecté, aucun événement de séance), la ligne « Autorisations des
outils » (résumé « 5 · 2 sur demande ») se déplie sur un corps vide : `security.js` appelait
`kv([])` pour ce contrôle, l'API `/api/security` ne renvoyant que des compteurs
(`tool_rules: {count, ask_count, deny_count}`), jamais la liste des outils eux-mêmes. Deux autres
contrôles se dépliaient aussi sur un corps vide selon l'état : « Hooks » (aucun hook actif) et un
garde-fou installé mais désactivé (`mode: "off"`, `install_text: null`), tous deux à cause d'une
condition JS qui n'affichait rien hors de ces deux cas précis. La liste blanche réseau, elle,
affichait une valeur vide (sans texte explicatif) quand `cfg.allowed_hosts` est vide (aucun
modèle cloud actif). Le contrat (`ux/EXPERIENCE.md`, « dépliez pour voir le réglage exact » ; la
maquette vague 2, écran Sécurité) demande que chaque dépli dise le réglage exact et, pour un
contrôle non installé ou non connecté, quoi faire.

**Approach:** Côté serveur, `_security_controls` (`app_session.py`) renvoie en plus, pour
« Autorisations des outils », la liste de chaque outil local avec sa règle effective
(`tools: [{id, label_text, rule}]`) et le compte `allow_count`, en plus des compteurs existants.
Côté page, `security.js` : le dépli des autorisations liste chaque outil et sa règle puis le lien
« Régler dans MCP » (texte déjà utilisé sous la matrice) ; le dépli d'un garde-fou montre toujours
soit la raison d'installation (déjà le cas), soit le mode courant, puis un lien « Modifier dans la
brique Garde-fous, page d'accueil » ; le dépli des hooks liste tous les hooks (actif/inactif), pas
seulement les actifs ; le dépli de la liste blanche réseau affiche un texte explicatif quand la
liste est vide. Textes nouveaux en fr/en/de sous `security.controls.*`.

## Boundaries & Constraints

**Always:**
- Les 4 autres contrôles (toxicité, données personnelles, injection, connexion GitHub) déjà
  non vides restent inchangés dans leur logique ; seule la condition d'affichage est généralisée
  pour ne jamais produire un corps sans texte.
- Chaque nouveau texte existe en français, anglais et allemand (`content/ui.yaml`,
  `content/i18n/{en,de}/ui.yaml`).
- Aucune donnée dupliquée : la liste des outils locaux est lue sur `ToolPolicy` (comme le reste
  de `_security_controls`), jamais une copie figée.

**Never:** pas de nouveau contrôle, pas de changement du résumé replié (badge) des contrôles déjà
corrects, pas de changement de `security.html` (motif disclosure-row inchangé), pas de retouche à
`docs/` ni `README.md` (une autre tâche en cours).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Autorisations des outils | Politique par défaut (5 outils locaux) | Dépli : 5 lignes outil → règle, puis « Régler dans MCP » | N/A |
| Garde-fous non installés | `_guardrails_missing` renseigné | Dépli : raison d'installation + lien | N/A (déjà correct avant le correctif) |
| Garde-fou installé, mode désactivé | `installed=True`, `mode="off"` | Dépli : « Mode : Désactivé » + lien vers la brique | Avant le correctif : corps vide |
| Hooks, aucun actif | `_hooks_enabled` vide | Dépli : les N hooks, chacun « inactif » | Avant le correctif : corps vide |
| Hooks, certains actifs | ex. 3 actifs sur 4 | Dépli : les 4 hooks avec leur état | N/A |
| Liste blanche réseau vide | `cfg.allowed_hosts == []` | Dépli : texte expliquant l'absence de restriction | Avant le correctif : valeur vide |
| Liste blanche réseau renseignée | hôtes configurés + hôtes des modèles cloud actifs | Dépli : liste des domaines | N/A |
| GitHub non connecté / connecté | `status` variable | Dépli : droits + serveur (+ expiration si connecté) | N/A (déjà correct avant le correctif) |

</frozen-after-approval>

## Code Map

- `src/wavestack/session/app_session.py` -- `_security_controls` (L10993) : `tool_rules` gagne
  `allow_count` et `tools` (liste `{id, label_text, rule}` par outil `local__*`, via
  `_security_label_text`).
- `src/wavestack/web/static/security.js` -- `renderControls` (L147) : dépli des autorisations
  (liste des outils + lien `security.matrix.settle_link` vers `/mcp`) ; dépli d'un garde-fou
  (corps jamais vide : raison ou mode courant, + lien vers `/`) ; dépli des hooks (tous les
  hooks, pas seulement les actifs) ; dépli de la liste blanche réseau (texte si vide). Nouvelle
  fonction `link(text, href)`.
- `content/ui.yaml`, `content/i18n/en/ui.yaml`, `content/i18n/de/ui.yaml` -- `security.controls.*` :
  `allow_count`, `hook_active`, `hook_inactive`, `guardrail_mode_label`, `change_in_bricks`,
  `network_whitelist_empty`.
- `tests/test_security_page.py` -- nouveau test API (`controls` carrying enough detail) et mise à
  jour de l'assertion existante sur la forme de `tool_rules`.
- `tools/e2e/run_e2e.py` -- `s_security_page` : déplie les 7 contrôles et vérifie qu'aucun corps
  n'est vide, avant le flux existant (fusion refusée, CSV).

## Tasks & Acceptance

**Execution:**
- [x] `app_session.py` -- `tool_rules.tools` et `allow_count`
- [x] `security.js` -- corps jamais vide pour les 7 contrôles, lien « Régler dans MCP » et lien
  vers la brique Garde-fous
- [x] textes fr/en/de sous `security.controls.*`
- [x] `tests/test_security_page.py` -- test qui échoue sur l'ancien code (`tool_rules` sans
  `tools`)
- [x] `tools/e2e/run_e2e.py` -- `s_security_page` déplie les 7 contrôles

**Acceptance Criteria:**
- Given la page Sécurité sur des données neuves (garde-fous non installés, GitHub non connecté),
  when chacun des 7 contrôles actifs est déplié, then aucun corps n'est vide.
- Given la politique MCP par défaut, when « Autorisations des outils » est déplié, then chaque
  outil local apparaît avec sa règle effective et un lien vers `/mcp`.

## Implementation Notes

- `uv run pytest -q --tb=short tests/test_security_page.py tests/test_web_app.py
  tests/test_ui_texts.py tests/test_i18n.py` : tous verts (10, 27, 42, 137 tests).
- `python .claude/cost-kit/controle_rapide.py` : propre (ruff check + format).
- `node --check src/wavestack/web/static/security.js` : propre.
- E2E (`--channel msedge --only security_page bar_panels`) : 37 vérifications réussies, 0 échec,
  les 7 contrôles vérifiés non vides dans l'état par défaut (garde-fous non installés, GitHub non
  connecté). `settings.json`/`memory.json` sauvegardés puis restaurés ; captures d'écran
  restaurées à l'état du dépôt après coup.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_security_page.py tests/test_web_app.py tests/test_ui_texts.py tests/test_i18n.py` -- expected: tous verts
- `python .claude/cost-kit/controle_rapide.py` -- expected: aucune erreur
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only security_page bar_panels` -- expected: 0 échec
