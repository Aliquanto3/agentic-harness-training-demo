---
title: 'Story 1 : politique d''autorisation par outil MCP et journal de sécurité'
type: 'feature'
created: '2026-10-16'
status: 'review'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '6268ac1'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/mcp-tools.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-2, CAP-3. Aucun outil MCP ne porte de niveau de risque ni de règle d'autorisation ; un refus n'est visible nulle part ; aucun journal de sécurité n'existe. Fondation des stories 3 (GitHub), 5 (garde-fous) et 10 (page Sécurité).

**Approach:**
- `wavestack.mcp.policy.ToolPolicy` : risque (fixe) et règle (autoriser/demander/refuser, modifiable) par outil exposé (`{server}__{tool}`) ; défauts validés dans `mcp-tools.md` (`local__list_terms`, `local__define_term` : faible, autoriser) ; un outil non listé reste faible/autoriser par défaut, pour que les stories 2 et 3 n'aient qu'à ajouter leur propre entrée.
- `wavestack.mcp.security_log.SecurityJournal` : journal en mémoire (500 entrées au plus), `record(source, name, decision, reason_text)` — interface d'ajout simple, pour que la story 5 (garde-fous) y écrive sans dépendre de ce module. Jamais de secret dedans (rien de secret n'y est jamais passé).
- Application de la politique dans le flux réel de l'Atelier MCP (`AppSession._mcp_lab_tool_call`, le seul point d'exécution d'un `tools/call` de l'atelier, à la main ou par le modèle) : `deny` n'exécute jamais l'outil (texte de refus réinjecté au modèle, qui le restitue) ; `ask` fait attendre l'appel (sondage du jeton d'annulation toutes les 0,5 s) jusqu'à `answer_mcp_authorization` (« Autoriser une fois » / « Refuser »), sans modale, visible comme étape « à décider » puis comme refus/exécution dans la Séquence (réutilise le mécanisme existant `error_kind`/`error_text` d'un échec d'échange, déjà affiché par la Séquence).
- API : `POST /api/intentions/mcp_tool_rule`, `POST /api/intentions/mcp_tool_authorize`, `GET /api/security_journal` (JSON), `GET /api/security_journal.csv` (téléchargement) — lues plus tard par le bouton Journal (story 9) et la page Sécurité (story 10), sans construire ces deux écrans ici.
- Front (`mcp.js`/`mcp.html`) : sélecteur de règle (3 segments, réutilise `segmented()`) et niveau de risque sous l'outil choisi dans « Serveurs et outils » ; bandeau non modal « à décider » avec deux boutons quand la règle est Demander.

**Décisions (prises par Claude, sans effet sur le contrat) :**
- Le journal est un module neuf (`wavestack/mcp/security_log.py`), pas une extension du journal d'audit H2 existant (`hooks.py`, `content/hooks.yaml`) : objets différents (décisions d'autorisation et de garde-fou, pas l'historique complet d'un tour), et H2 est hors périmètre de cette story.
- Risque fixe par outil (jamais réglable) ; seule la règle se règle depuis l'interface, conformément à CAP-2 et à `mcp-tools.md`.
- Attente de l'« ask » par sondage toutes les 0,5 s du jeton d'annulation, pas par une attente composite événement+annulation : suffisant pour une seule demande en attente à la fois (démo), pas pour plusieurs requêtes concurrentes.
- Pas de puce de couleur dédiée au risque (status-chip du DESIGN) : un simple texte (« Risque : faible ») suffit à cette story ; la pastille colorée reste un raffinement possible des stories 9/10.
- Le bouton « Télécharger le journal (CSV) » n'est pas posé sur `/mcp` : l'orchestrateur a dit que l'écran de téléchargement visible revient à la story 10 (page Sécurité) ; cette story expose seulement la route.

## Boundaries & Constraints

**Always:**
- Libellés en fr, en, de (`content/messages.yaml`, `content/ui.yaml`, et leurs surcouches `content/i18n/{en,de}/`).
- Aucun secret dans le journal de sécurité.
- Un refus (`deny`) ou un refus après « ask » n'exécute jamais l'outil réel.

**Never:** toucher `src/wavestack/guardrails/` (n'existe pas encore, lane B), le panneau des briques (Harnais), ni `web/static/app.js` (lane C).

## Code Map

- `src/wavestack/mcp/policy.py` (nouveau) -- `ToolPolicy` : `risk_of`, `default_rule`, `rule_of`, `set_rule` ; défauts `_DEFAULTS` par nom exposé, repli `_FALLBACK = ("low", "allow")`.
- `src/wavestack/mcp/security_log.py` (nouveau) -- `SecurityJournal` : `record`, `entries`, `denied_count`, `to_csv` ; `_KEPT = 500`.
- `src/wavestack/trace/catalog.py` -- `McpLabErrorKind` + `"policy_denied"` ; `McpLabTool` + `risk`/`rule` ; nouveaux `McpLabAuthorizationRequestedPayload`/`ResolvedPayload`, ajoutés à `PAYLOAD_MODELS`.
- `src/wavestack/mcp/lab.py` -- `KINDS` + les deux nouveaux kinds (pour `last_session` au rechargement).
- `src/wavestack/session/app_session.py` -- état (`_mcp_policy`, `_security_journal`, `_mcp_authorizations`) ; `set_mcp_tool_rule`, `answer_mcp_authorization`, `_await_mcp_authorization`, `security_journal_entries/denied_count/csv` ; `_mcp_lab_tool_call` applique la règle avant `conn.call_result` ; `_mcp_lab_after` ne ferme plus la connexion sur `policy_denied` ; `_mcp_lab_weights` ajoute `risk`/`rule` par outil listé.
- `src/wavestack/web/app.py` -- `McpToolRuleIntention`, `McpAuthorizationIntention`, les quatre routes ; import `Response`.
- `content/messages.yaml` (+ i18n en/de) -- `session.mcp_lab.policy_denied(_by_user)`, `policy_allowed(_once)` ; `web.unknown.mcp_tool_rule/mcp_authorization`.
- `content/ui.yaml` (+ i18n en/de) -- `mcp.error_kinds.policy_denied`, `mcp.policy.*`, `mcp.authorize.*`, `mcp.security_journal.download` (texte prêt pour la story 10).
- `src/wavestack/web/static/mcp.js`/`mcp.html`/`mcp.css` -- `renderToolPolicy` (risque + sélecteur de règle sous l'outil choisi), bandeau `#mcp-authorize` (deux boutons), `pendingAuthorization()`, `KINDS`/`NO_REPLY_KINDS` + les deux nouveaux kinds.

## Tasks & Acceptance

**Execution:**
- [x] `policy.py`, `security_log.py` et leurs tests unitaires.
- [x] `catalog.py`, `lab.py` : nouveaux kinds et champs.
- [x] `app_session.py` : enforcement, attente de décision, accès au journal.
- [x] `app.py` : quatre routes.
- [x] Textes fr/en/de.
- [x] `mcp.js`/`mcp.html`/`mcp.css` : sélecteur de règle, risque, bandeau de décision.
- [ ] E2E `s_mcp_lab_page`, `s_mcp_lab` (non lancés par le développeur, consigne de l'orchestrateur).

**Acceptance Criteria:**
- Given la règle de `local__define_term` sur Refuser, when on l'appelle dans l'Atelier MCP (à la main ou par le modèle), then l'outil n'est pas exécuté (rien n'est envoyé au serveur), la Séquence montre le refus et sa raison, le modèle reçoit un texte d'erreur qu'il restitue, et la connexion reste ouverte.
- Given la règle sur Demander, when on appelle l'outil, then l'appel attend ; `answer_mcp_authorization("allow_once")` l'exécute, `"deny"` le refuse ; les deux décisions rejoignent le journal.
- Given un outil non listé dans `mcp-tools.md`, then son risque et sa règle par défaut sont faible/autoriser.
- Given des décisions enregistrées, when on lit `GET /api/security_journal` ou `.csv`, then elles apparaissent horodatées, avec leur source, leur nom, leur décision et leur raison, sans secret.

## Implementation Notes

- Point d'application unique : `AppSession._mcp_lab_tool_call`, déjà le seul chemin d'exécution d'un `tools/call` de l'atelier (à la main ou « par le modèle », `mcp{n}.t1`) — pas de duplication entre les deux modes d'appel.
- Le refus réutilise le mécanisme existant de la Séquence pour un échange en échec (`error_kind`/`error_text`, `markFailed` côté front) : aucun nouveau motif visuel à construire, seulement un nouveau `error_kind` (`policy_denied`) ajouté à la liste déjà gérée par le front (`mcp.error_kinds.*`, `NO_REPLY_KINDS`).
- `_mcp_lab_after` fermait la connexion sur tout statut différent de `ok` hors `jsonrpc_error` : `policy_denied` y est ajouté à l'exemption, sinon chaque refus aurait fermé la connexion de l'atelier (contraire au flux 1 de `EXPERIENCE.md`, qui enchaîne plusieurs essais sur la même connexion).
- `McpLabTool.risk`/`rule` sont calculés à chaque connexion (`_mcp_lab_weights`) : un changement de règle ne demande pas de reconnexion, `rule_of` est relu à l'appel suivant.
- Testé : `uv run pytest -q --tb=short tests/test_mcp_policy.py tests/test_mcp_lab_policy.py tests/test_mcp_policy_http.py` (17 tests, neufs) et la suite existante `tests/test_mcp.py tests/test_mcp_lab.py tests/test_mcp_lazy.py tests/test_mcp_snapshot.py` (93 tests) pour vérifier l'absence de régression — tous verts.

## Spec Change Log

## Review Triage Log

(pas encore de relecture)

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_mcp_policy.py tests/test_mcp_lab_policy.py tests/test_mcp_policy_http.py` -- 17 passés.
- `uv run pytest -q --tb=short tests/test_mcp.py tests/test_mcp_lab.py tests/test_mcp_lazy.py tests/test_mcp_snapshot.py` -- 93 passés (pas de régression).
- `python .claude/cost-kit/controle_rapide.py` -- à relancer juste avant le commit (lint/format).
- E2E (non lancé par le développeur, consigne de l'orchestrateur) : `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only mcp_lab_page,mcp_lab`.

## Revue

(pas encore de relecture)
