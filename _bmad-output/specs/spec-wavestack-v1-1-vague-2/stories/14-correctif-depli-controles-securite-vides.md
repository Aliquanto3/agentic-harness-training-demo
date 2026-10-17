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
« Autorisations des outils », la liste de chaque outil **local et GitHub** avec sa règle
effective (`tools: [{id, label_text, rule}]`, le compte `allow_count`, et `network_rule` /
`network_label_text` pour la ligne data.gouv.fr/Microsoft Learn, qui n'a pas de tool nommé un par
un). Côté page, `security.js` : le dépli des autorisations groupe la liste par serveur (« Sur ce
poste », data.gouv.fr/Microsoft Learn, « GitHub » avec « Toute autre écriture : Refuser ») puis le
lien « Régler dans MCP » ; le dépli d'un garde-fou montre toujours soit la raison d'installation
(déjà le cas), soit le mode courant, puis un lien « Modifier dans la brique Garde-fous, page
d'accueil » ; le dépli des hooks liste tous les hooks (actif/inactif), avec un texte s'il n'y en a
aucun ; le dépli de la liste blanche réseau affiche un texte explicatif quand la liste est vide.
Deux outils locaux de même libellé (« Glossaire » pour `list_terms` et `define_term`) sont
distingués. Textes nouveaux en fr/en/de sous `security.controls.*`.

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
| Autorisations des outils | Politique par défaut (5 locaux + 6 GitHub) | Dépli : 3 groupes (Sur ce poste, data.gouv.fr/Microsoft Learn, GitHub + « Toute autre écriture : Refuser »), puis « Régler dans MCP » | N/A |
| Règle réglée dans MCP | `set_rule("github__list_issues", "deny")` | La règle du dépli change en même temps que la matrice (même source) | N/A |
| Garde-fous non installés | `_guardrails_missing` renseigné | Dépli : raison d'installation + lien | N/A (déjà correct avant le correctif) |
| Garde-fou installé, mode désactivé | `installed=True`, `mode="off"` | Dépli : « Mode : Désactivé » + lien vers la brique | Avant le correctif : corps vide |
| Hooks, aucun actif | `_hooks_enabled` vide | Dépli : les N hooks, chacun « inactif » | Avant le correctif : corps vide |
| Hooks, certains actifs | ex. 3 actifs sur 4 | Dépli : les 4 hooks avec leur état | N/A |
| Liste blanche réseau vide | `cfg.allowed_hosts == []` | Dépli : texte expliquant l'absence de restriction | Avant le correctif : valeur vide |
| Liste blanche réseau renseignée | hôtes configurés + hôtes des modèles cloud actifs | Dépli : liste des domaines | N/A |
| GitHub non connecté / connecté | `status` variable | Dépli : droits + serveur (+ expiration si connecté) | N/A (déjà correct avant le correctif) |

</frozen-after-approval>

## Code Map

- `src/wavestack/session/app_session.py` -- `_security_controls(rows, matrix)` : `tool_rules`
  gagne `allow_count`, `tools` (liste `{id, label_text, rule}` sur les outils `local__*` et
  `github__*`, ces derniers absents avant le correctif) et `network_rule`/`network_label_text`
  (la ligne `network` de la matrice, réutilisée, jamais dupliquée). `security_state` lui passe
  désormais `matrix` en plus de `rows`.
- `src/wavestack/web/static/security.js` -- `renderControls` : dépli des autorisations groupé par
  serveur (« Sur ce poste », data.gouv.fr/Microsoft Learn, « GitHub » + « Toute autre écriture »),
  lien `security.matrix.settle_link` vers `/mcp` ; dépli d'un garde-fou (corps jamais vide : raison
  ou mode courant, + lien vers `/`) ; dépli des hooks (tous les hooks, texte si la liste est vide) ;
  dépli de la liste blanche réseau (texte si vide). Nouvelles fonctions `link`, `ruleText`
  (factorisée avec `renderMatrix`), `groupHeading`.
- `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- `security.controls.*` : `allow_count`,
  `hook_active`, `hook_inactive`, `hooks_empty`, `guardrail_mode_label`, `change_in_bricks` (texte
  allemand corrigé : « Schutzmechanismen », le nom de la brique), `network_whitelist_empty`,
  `group_local`, `group_github`, `github_write_other`.
- `content/messages.yaml`, `content/i18n/{en,de}/messages.yaml` -- `security.tools.local__list_terms`
  et `local__define_term` distingués (« Glossaire : liste des termes » / « Glossaire : définition »).
- `tests/test_security_page.py` -- test API `tool_rules` (groupes local+GitHub, 11 outils, règle
  réglée dans MCP reflétée) et assertions non vacueuses sur les garde-fous/hooks.
- `tools/e2e/run_e2e.py` -- `s_security_page` : déplie les 7 contrôles et vérifie qu'aucun corps
  n'est vide, avant le flux existant (fusion refusée, CSV) ; la ligne « fusion de PR » du journal
  est maintenant cherchée sous `#sec-journal` (évite un conflit avec le texte du même outil dans
  le dépli des autorisations).

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
  tests/test_ui_texts.py tests/test_i18n.py` : tous verts (10, 27, 42, 137 tests), les deux
  passes (avant et après le second avis).
- `python .claude/cost-kit/controle_rapide.py` : propre (ruff check + format).
- `node --check src/wavestack/web/static/security.js` : propre.
- E2E (`--channel msedge --only security_page bar_panels`) : 37 vérifications réussies, 0 échec,
  les 7 contrôles vérifiés non vides dans l'état par défaut (garde-fous non installés, GitHub non
  connecté), les 11 outils (local + GitHub) visibles groupés. `settings.json`/`memory.json`
  sauvegardés puis restaurés à chaque passe ; captures d'écran restaurées à l'état du dépôt après
  coup.

## Spec Change Log

- 2026-10-17 : second avis — élargissement de « Autorisations des outils » aux outils GitHub
  (groupés), libellés distincts pour les deux outils du glossaire, texte allemand de
  `change_in_bricks` corrigé, texte explicite si la liste des hooks est vide.

## Review Triage Log

Second avis (1 passe) :

- [MEDIUM] « Autorisations des outils » ne listait que les outils `local__*` ; la matrice et
  « Quels outils peuvent écrire ? » comptent aussi GitHub et les serveurs publics, incohérent avec
  le résumé replié. → corrigé : `tool_rules.tools` couvre local + GitHub (11 outils, cohérent avec
  les décomptes du résumé), groupés par serveur côté page, avec la ligne `network` de la matrice
  réutilisée pour data.gouv.fr/Microsoft Learn ; test qui règle un outil GitHub dans MCP et vérifie
  qu'il apparaît avec sa règle.
- [MEDIUM] `tests/test_security_page.py` : `g["install_text"] or g.get("mode")` ne pouvait pas
  échouer, et `all(... for h in hooks)` passait sur une liste vide. → corrigé : assertions par
  branche (garde-fou non installé/en erreur exige `install_text` ; sinon le mode doit être un des
  modes offerts) et `assert controls["hooks"]`/`assert controls["guardrails"]` avant les `all(...)`.
- [LOW] `local__list_terms` et `local__define_term` partageaient le libellé « Glossaire ». →
  distingués (« Glossaire : liste des termes » / « Glossaire : définition », fr/en/de).
- [LOW] `security.controls.change_in_bricks` en allemand ne nommait pas la brique. → corrigé avec
  le nom allemand de la brique (`content/i18n/de/bricks/guardrails.yaml` : « Schutzmechanismen »).
- [LOW] Hooks : corps vide si la liste est vide. → texte `security.controls.hooks_empty` en repli.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_security_page.py tests/test_web_app.py tests/test_ui_texts.py tests/test_i18n.py` -- expected: tous verts
- `python .claude/cost-kit/controle_rapide.py` -- expected: aucune erreur
- `PYTHONUTF8=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only security_page bar_panels` -- expected: 0 échec
