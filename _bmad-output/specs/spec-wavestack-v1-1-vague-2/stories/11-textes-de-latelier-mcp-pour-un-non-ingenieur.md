---
title: 'Story 11 : textes de l''atelier MCP pour un non-ingénieur'
type: 'content'
created: '2026-10-16'
status: 'done'
route: 'dispatch'
review_loop_iteration: 1
baseline_commit: '4d5442b'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-10 (partie 2). Les textes de l'atelier MCP (`content/mcp_lab.yaml`), de la brique MCP (`content/bricks/mcp.yaml`), des serveurs MCP (`content/mcp.yaml`, `content/mcp_local/`) et du bloc `mcp.*` de `content/ui.yaml` (règles, autorisations, GitHub) sont écrits pour un public d'ingénieur. Lus seuls par un RSSI ou un consultant non développeur, plusieurs termes techniques (MCP, serveur, hôte, bac à sable, JSON-RPC, HTTP, OAuth, jeton) restent sans glose à leur première apparition sur la page.

**Approach:**
- Relecture exhaustive, ligne à ligne, des fichiers du périmètre, avec le regard d'un RSSI qui ouvre l'atelier MCP ou la brique MCP seul, sans avoir lu les autres pages (méthode de la story 8, dont le second avis a jugé la première passe trop légère : chaque fichier est relu comme une page autonome, pas seulement par recoupement avec les autres).
- Un terme technique reste permis s'il est expliqué en une phrase simple (parenthèse courte) à sa première apparition dans chaque fichier pris isolément ; le détail complet (schéma, exemple, analogie du restaurant) peut rester plus bas sur la même page, sans duplication. Le vocabulaire du glossaire du PRD (brique, tour, contexte, harness engineering, lazy loading…) est repris tel quel.
- Les ajouts sont des gloses courtes entre parenthèses, jamais une réécriture du fond : le sens, les clés YAML, les `{placeholders}` et le nombre de paragraphes/puces restent identiques dans les trois langues (fr, en, de), pour ne pas casser `tests/test_i18n.py` (même structure) ni le validateur pydantic `McpLabContent`.
- `content/mcp_local/glossary.yaml` (le glossaire servi par le serveur MCP local) définit déjà « MCP », « serveur MCP » et les autres notions du démonstrateur : fichier de référence, non modifié. `content/mcp_local/primitives.yaml` et `content/mcp_local/tools.yaml` sont des descriptions déjà claires (dont les trois nouveaux outils de la story 2 : `system_info`, `create_path`, `take_screenshot`) : non modifiés.

**Décisions (prises par Claude, sans effet sur le contrat) :**
- Termes glosés à leur première apparition, par fichier :
  - `content/bricks/mcp.yaml` : « MCP » (Model Context Protocol) et « méta-outil load_tool_doc », dans `explanation_text`.
  - `content/mcp_lab.yaml` : « MCP », « hôte » et « serveur » dans `intro_text` ; « bac à sable » dans `intro_text` (sens : un espace d'essai sans effet réel, distinct du bac à sable d'écriture de `create_path`/`take_screenshot`, hors périmètre de ce fichier) ; « HTTP » dans `servers_help_text` ; « JSON-RPC » dans `call_help_text` (sa première apparition réelle dans le fichier, avant la section `columns`, où le terme est réemployé sans re-glose).
  - `content/ui.yaml` (bloc `mcp.github`) : « OAuth » et « jeton » dans `intro` et `expired_text`.
- `content/mcp.yaml` (définition des serveurs, `sends_text: "… avec votre jeton de connexion"`) et `content/mcp_local/tools.yaml` (documentation des outils, lue par le modèle) : laissés en l'état, déjà en langage clair ou déjà couverts par la glose de `ui.yaml` sur la même page.
- Les libellés courts (`tags`, `chips`, `outcomes`, `error_kinds` de `ui.yaml`) ne portent pas de glose : ce sont des étiquettes d'état, pas des phrases ; leur détail est ailleurs sur la page (Séquence, volet Orchestration), conformément au motif « dépli sur place » de `ux/EXPERIENCE.md`.
- « portée », « 403 » et « liste blanche » (cités par l'orchestrateur comme termes à surveiller) n'apparaissent dans aucun fichier du périmètre : rien à faire sur ces termes.

## Boundaries & Constraints

**Always:**
- Contenu seulement : `content/mcp_lab.yaml`, `content/mcp.yaml`, `content/bricks/mcp.yaml`, le bloc `mcp.*` de `content/ui.yaml`, et leurs surcouches `content/i18n/{en,de}/` aux mêmes chemins. Mêmes clés, même nombre de paragraphes et de puces, mêmes `{placeholders}` dans les trois langues. Guillemets de la langue (« » en français, “ ” en anglais, „ " en allemand).
- Vocabulaire du glossaire du PRD repris tel quel ; vouvoiement, phrases courtes, pas de point d'exclamation (Voice and Tone, `ux/EXPERIENCE.md`).

**Never:** `content/mcp_local/*.yaml` (déjà des définitions ou des descriptions claires, non retouchées) ; les blocs hors `mcp.*` de `content/ui.yaml` ; aucun fichier Python ou JS.

## Code Map

- `content/bricks/mcp.yaml` (+ i18n en/de) — glose de « MCP » et du « méta-outil load_tool_doc ».
- `content/mcp_lab.yaml` (+ i18n en/de) — `intro_text` : glose de « MCP », « hôte », « serveur », « bac à sable » ; `servers_help_text` : glose de « HTTP » ; `call_help_text` : glose de « JSON-RPC ».
- `content/ui.yaml` (+ i18n en/de), bloc `mcp.github` — `intro` : glose d'« OAuth » ; `expired_text` : glose de « jeton ».

## Tasks & Acceptance

**Execution:**
- [x] Relecture exhaustive des fichiers du périmètre (`mcp_lab.yaml`, `mcp.yaml`, `bricks/mcp.yaml`, `mcp_local/*.yaml`, bloc `mcp.*` de `ui.yaml`), repérage des termes non expliqués à leur première apparition dans chaque fichier pris isolément.
- [x] Gloses ajoutées en fr, répercutées en en et de, mêmes clés et mêmes `{placeholders}`.
- [x] Tests ciblés.

**Acceptance Criteria:**
- Given un RSSI qui ouvre seul la brique MCP, when il lit « Un serveur MCP… », then la phrase dit ce que signifie MCP sans qu'il ait besoin de le chercher ailleurs.
- Given l'atelier MCP, when l'intro cite « hôte », « serveur » et « bac à sable », then chacun porte une glose d'une proposition à sa première apparition dans le fichier.
- Given la connexion GitHub de l'atelier MCP, when le texte cite OAuth et le jeton, then chacun est expliqué en une phrase simple, sans dupliquer l'explication déjà donnée par les droits acceptés affichés à l'écran.
- Given les mêmes fichiers en anglais et en allemand, then ils portent les mêmes clés, le même nombre de paragraphes/puces et les mêmes `{placeholders}` qu'avant la story, avec la même glose traduite.

## Implementation Notes

- Risque assumé, signalé à l'orchestrateur : `content/mcp_lab.yaml` nomme les méthodes JSON-RPC littérales (`tools/list`, `resources/read`, `initialize`…) dans l'analogie du restaurant et dans `methods.*` ; elles ne sont pas glosées une à une (chacune est déjà traduite en langage simple dans la même phrase, ex. « La carte, s'il vous plaît » pour `tools/list`), ce qui satisfait l'esprit du critère sans glose séparée.
- `content/mcp.yaml` garde « jeton de connexion » sans parenthèse : le terme est déjà glosé juste au-dessus sur la même page atelier, dans le bloc GitHub de `ui.yaml` ; une seconde glose aurait dupliqué l'explication.
- Testé : `uv run pytest -q --tb=short tests/test_i18n.py` (137 passés), `tests/test_ui_texts.py` (39 passés), `tests/test_mcp_lab.py` (38 passés), `tests/test_backend_messages.py` (voir Verification) — aucune régression de structure ni de nombre de paragraphes/puces.

## Spec Change Log

## Review Triage Log

(à compléter par le second avis et la revue)

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_i18n.py` -- 137 passés.
- `uv run pytest -q --tb=short tests/test_ui_texts.py` -- 39 passés.
- `uv run pytest -q --tb=short tests/test_mcp_lab.py` -- 38 passés.
- `uv run pytest -q --tb=short tests/test_backend_messages.py` -- voir sortie de la commande, rapportée au second avis.
- `python .claude/cost-kit/controle_rapide.py` -- silencieux (aucune erreur de lint/format).
- E2E : non lancé (consigne de l'orchestrateur, contenu seul) ; `mcp_lab_page,mcp_lab` à rejouer si un relecteur veut confirmer le rendu visuel des textes modifiés.

## Revue

Revue du 2026-10-16 (Opus), après rebase sur `origin/main` (998729f). Corrections en fr, en et de, avec les mêmes clés et les mêmes `{placeholders}`. Aucun fichier Python ou JS touché.

- MEDIUM, second avis : « primitives » (`methods.initialize`). Corrigé : « (ses types de services : outils, ressources, prompts) ».
- MEDIUM, second avis : « jeton » glosé seulement à l'expiration. Corrigé : glose dans `mcp.github.intro` (toujours visible dans le bloc GitHub) et dans `servers.github.sends_text` de `mcp.yaml` (détails du serveur). `error.network` est couvert par l'intro.
- MEDIUM, second avis : « schéma » de l'outil. Corrigé dans `tools_help_text` et `call_help_text` (la liste de ses paramètres et de leur type).
- MEDIUM, second avis : « JSON » dans `mcp.call.invalid_json`. Corrigé sans toucher le message, que `run_e2e.py` vérifie tel quel : glose dans `call_help_text`, affiché au-dessus des champs, et dans `context_help_text`.
- MEDIUM, second avis : « SLM local » en titre de colonne. Corrigé dans le dépli `columns.model.explain_text` (petit modèle de langage sur ce poste). `sub_text` reste vide : le JS le remplace par le nom du modèle.
- MEDIUM, second avis : « stdio (processus enfant) », « entrée et sortie standard ». Corrigé dans `servers_help_text` et `transports.stdio.explain_text`.
- MEDIUM, second avis : « token » des compteurs. Corrigé dans `tools_help_text`, l'aide du volet qui affiche les poids.
- MEDIUM, second avis : « fenêtre utile », « réserve de sortie » (`mcp.arrow.not_sent`, `mcp.arrow.cut`). Corrigé par une parenthèse dans le message.
- LOW, second avis : load_tool_doc dans `tools_help_text`. Corrigé.
- LOW, second avis : « garde réseau ». Corrigé dans `servers_help_text` ; `error_kinds.guard_blocked` reste une étiquette courte.
- LOW, second avis : « poignée de main » en titre. Corrigé en tête de `phases.connect.why_text`, le dépli sous le titre. `handshake_help_text` n'est rendu par aucun écran : non retouché.
- LOW, second avis : gabarit, POST, flux d'événements, API. Corrigés (`context_help_text`, `transports.streamable_http`, `servers.datagouv.source_explain_text`, `before.captions`). « REST » retiré du libellé `before.integrations.datagouv` (« son propre format »), sans perte de sens.
- LOW, second avis : sigles MFA, PIM, IAM, Entra ID des préréglages (`call_presets` de `mcp.yaml`). Rejeté : `content/scenarios.yaml` et `tests/test_program.py` citent les libellés mot pour mot, et « Entra ID » fait partie de la requête envoyée à Microsoft Learn. Les gloser sort du périmètre de la story ; à reprendre avec les scénarios IAM et Souveraineté si besoin.
- LOW, second avis : « erreur JSON-RPC », « isError », « blocs de contenu ». Corrigé dans `methods.tools/call`.
- LOW, revue : anglais de `call_help_text` (« a JSON-RPC (…) result »). Corrigé en « a JSON-RPC result (…) ».
- Info, revue : `tests/test_program.py` a 2 tests en échec (`mcp_full` déborde la fenêtre, snapshot GitHub en `KeyError`), aussi avec le contenu d'`origin/main`. Préexistant, hors story, non corrigé.

Tests passés : `test_i18n` 137, `test_ui_texts` 39, `test_mcp_lab` 38, `test_backend_messages` 3699. Le contrôle rapide ne signale rien. E2E à rejouer : `mcp_lab_page,mcp_lab`, pour le rendu des gloses ; aucun texte vérifié à l'identique n'a changé.
