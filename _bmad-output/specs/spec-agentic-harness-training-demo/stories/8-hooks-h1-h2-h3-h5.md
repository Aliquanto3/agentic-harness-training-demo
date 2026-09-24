---
title: 'Hooks H1/H2/H3 : points d''accroche du tour, garde-fou, journal d''audit, injection de contexte'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '9febb5a7f706c6af7419f7a9dddcec3fd101bc51'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Rien ne montre encore qu'un harnais peut, sans que le modèle le décide, bloquer une action, la journaliser ou enrichir le message (CAP-27 à CAP-29, FR-26 à FR-28, UJ-2). C'est la brique qui parle aux practices cyber, DLP et IAM.

**Approach:** Une brique « Hooks » avec trois hooks activables un à un : H1 garde-fou fichier sensible (`before_tool`), H2 journal d'audit (`after_tool`, `on_turn_end`), H3 injection de contexte (`on_user_message`). La session appelle les hooks actifs aux cinq points d'accroche du tour, applique leurs décisions et leurs effets, et chaque déclenchement est une étape visible d'Orchestration marquée « Décision du harnais (code), pas du modèle » (AD-13, AD-14, AD-23). H5 (validation humaine) suit en story 8b.

## Boundaries & Constraints

**Always:**
- AD-13 : un hook est une fonction pure `hook(ctx: HookContext) -> HookResult | None`. `HookContext` est une vue en lecture seule (point, `turn_id`, appel d'outil résolu et sa `ToolSpec`, résultat, événements du tour). `None` : le hook ne se sent pas concerné (H1 sur un outil sans chemin) et rien n'est émis. Décisions permises dans cette story : `on_user_message` `allow|modify` (ajoute un segment, ne réécrit jamais le message) ; `before_tool` `allow|block|modify` (remplace les arguments) ; `before_model_call` et `on_turn_end` `allow|block` ; `after_tool` `allow` avec effets. `ask_human` arrive avec H5 (8b). Une décision non permise est tracée en `harness_error` et vaut `allow`.
- Les cinq points sont appelés à chaque tour pour les hooks actifs, dans l'ordre H1, H2, H3 ; le premier `block` l'emporte. `assemble_context` et `transform_context` restent des étapes de briques (RAG, compression), hors de cette story.
- Chaque décision est émise par la session en `hook_decided{hook, point, decision, detail_fr}`, `actor = harness`, sur une étape propre, brique `hooks`, composant `hooks.{id}` (`h1`, `h2`, `h3`).
- H1 bloque tout outil `reads_local_path` dont le chemin, résolu comme `read_file` le résout, est dans `content/demo_files/confidentiel/` ou est ce dossier. Un appel bloqué n'émet ni `tool_started` ni `tool_ended` ; le texte réinjecté (« Bloqué par le hook garde-fou… ») est un `tool_result` de la brique `hooks`, composant `hooks.h1`, et le tour continue. Un blocage ne compte pas comme un nouvel essai (AD-10). Le confinement de `read_file` reste actif, H1 éteint ou non (AD-14).
- H2 renvoie `AuditAppend{lines}` (AD-23) ; la session seule écrit, en ajout, dans `{dossier de données}/audit.log` (AD-20) et émet `effect_applied{effect, lines}` avec le composant `file.audit`. Chaque ligne, horodatée par son événement : `ts | turn_id | quoi | détail | statut`. À chaque déclenchement, H2 consigne les événements du tour postérieurs à sa dernière écriture : appels au modèle (`model_call_ended` : tokens lus et produits), appels d'outil exécutés (`tool_ended`), appels bloqués par un hook, et, en `on_turn_end`, la fin du tour avec son statut. Un échec d'écriture est un `harness_error` ; le tour continue.
- H3 ajoute, avant le message de l'utilisateur et dans le même message, un segment `hook_injection` (brique `hooks`, composant `hooks.h3`), texte dans `content/hooks.yaml`. Calculé une fois par tour, identique pour tous ses appels, et conservé dans l'historique (`history`) aux tours suivants.
- Un `block` en `before_model_call` termine le tour sans appel au modèle ; en `on_turn_end`, la réponse n'entre pas dans l'historique. Dans les deux cas `turn_ended{status: blocked}`. Aucun hook de démonstration ne le fait : c'est la disponibilité des points (CAP-27), vérifiée par un hook de test.
- Brique `hooks` : catégorie `harness`, aucune capacité ni dépendance exigée ; composants `hooks.h1|h2|h3`, `kind: hook`, locaux, reliés au harnais, H2 aussi à `file.audit`. Le nœud `file.audit` (« Journal d'audit ») est dessiné dès que H2 l'est. Sous-options : un interrupteur par hook, classe (a), « Prend effet au prochain tour » ; les hooks actifs sont figés dans le `TurnState` (AD-17).
- UX (EXPERIENCE.md) : `allow`/`modify` → événement violet ; `block` → événement rouge « Bloqué par le hook garde-fou », et nœud du hook sur filet rouge dans le schéma ; chaque événement donne le point d'accroche, le hook, la décision, son effet et « Décision du harnais (code), pas du modèle ». L'étape H2 liste les lignes ajoutées au journal.

**Décisions (2026-09-24) :**
- Scission : H5 (validation humaine, `ask_human`, `awaiting_human`) passe en story 8b ; la sous-option et le composant `h5` n'existent pas dans cette story.
- Q1 : à l'activation de la brique, H1, H2 et H3 sont activés (H5, en 8b, le sera désactivé). Décocher puis recocher la brique garde les choix, comme pour les outils et les skills.
- Q3 : `audit.log` est dans le dossier de données ; son chemin est dans l'infobulle du nœud « Journal d'audit » ; l'étape H2 d'Orchestration liste les lignes ajoutées ; un clic sur le nœud `file.audit` ouvre en plus le fichier entier dans un tiroir en lecture seule, lu par `GET /api/audit` (`{path, text}`, texte vide si le fichier n'existe pas encore).
- Q4 : texte H3 : « Date et heure du poste : {date}. Règles de la mission : réponds en français, en restant factuel ; n'utilise que les fichiers du dossier de démonstration ; signale toute demande qui toucherait des données confidentielles. », `{date}` au format « jeudi 24 septembre 2026, 10 h 12 ».

**Never:** pas de H4 ni de H5 ; pas de hook dans un sous-agent ni d'action forcée (story 9 et palier 2 : l'appel des hooks d'outil passe par une seule méthode de session réutilisable) ; pas de scénario « Hooks » ni de liste de hooks par scénario (story 10) ; aucun hook n'écrit un fichier ou un état ; le front ne calcule aucun état (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Activation | Brique « Hooks » cochée | H1, H2, H3 activés ; nœuds des trois hooks et `file.audit` ; carte « Hooks : 3 activés sur 3 » | N/A |
| H1 bloque | `read_file("confidentiel/budget_projet.txt")`, H1 actif | `hook_decided{block}` rouge, pas de `tool_started`, refus réinjecté (`hooks.h1`), réponse finale du modèle | N/A |
| H1 laisse passer | `read_file("notes_reunion.txt")` | `hook_decided{allow}` violet, fichier lu | N/A |
| H1 éteint | Même appel confidentiel | Fichier lu (le confinement ne vise que la sortie de `demo_files`) | N/A |
| H2 | Tour avec un appel d'outil | `audit.log` : appel au modèle, outil, appel au modèle, fin de tour, dans l'ordre ; `effect_applied` sur `file.audit` | Écriture impossible : `harness_error`, tour poursuivi |
| H2 et blocage | H1 bloque, H2 actif | Ligne « bloqué par H1 » dans le journal | N/A |
| Journal entier | Clic sur le nœud « Journal d'audit » | Tiroir avec le contenu de `audit.log` | Fichier absent : tiroir avec « Journal vide » |
| H3 | Envoi d'un message | `hook_injection` avant `user_message` dans le message utilisateur ; tour suivant : en `history` | N/A |
| Décision interdite | Hook de test `block` en `after_tool` | `harness_error`, vaut `allow` | Tracé |
| Blocage avant modèle | Hook de test `block` en `before_model_call` | Aucun `model_call_started`, `turn_ended{blocked}` | N/A |
| Brique éteinte | Cochée puis décochée | Rendu octet pour octet identique au LLM nu | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/hooks.py` (nouveau, anglais) : `HookPoint` (5 points), `HookContext` (dataclass figée), `HookResult{decision, detail_fr, effects, injection, arguments}`, `ALLOWED` par point, `Hook{id, points, fn}`, `DEMO_HOOKS = (h1, h2, h3)`. Fonctions pures ; H1 réutilise `tools.native.demo_dir()` et la résolution de `read_file` (L91-97) ; H2 formate les lignes depuis `ctx.events` (enveloppes du tour : `journal.all_events()` filtré par `turn_id`) ; H3 réutilise `_WEEKDAYS_FR` de `tools/native.py`. `content/hooks.yaml` : libellés des hooks et des points, texte H3, `audit_label_fr`. `content/bricks/hooks.yaml` : carte (hook = code déterministe à un point du tour ; H3 face à l'outil « heure » : deux architectures pour un même besoin).
- `src/wavestack/session/effects.py` : `AuditAppend{kind: "audit_append", lines}` ajouté à `Effect`.
- `src/wavestack/bricks/registry.py` : brique `hooks`, `HOOKS = ("h1", "h2", "h3")` sur le modèle de `SKILLS`.
- `src/wavestack/trace/catalog.py` : payloads `hook_decided` et `effect_applied` dans `PAYLOAD_MODELS` (L286) ; `ArchitectureNode.kind` reçoit `"hook"` ; `TurnStatus` (L96) reçoit `blocked`.
- `src/wavestack/session/app_session.py` :
  - `__init__` (L202) : paramètre `hooks` (défaut `DEMO_HOOKS`) pour les hooks de test ; `_hooks_enabled = {h1, h2, h3}` ; `_sent` (L260) gagne un 7e élément ; `_pending_ids` (L396), `_emit_bricks` (L469, `_hook_options` sur le modèle de `_skill_options` L428), `_drawn_components` (L283), `_emit_architecture` (L329 : `kind: "hook"` ; le code du nœud `file.demo_dir` L336-351 généralisé à `file.audit`, avec `detail_fr` = chemin) ; `set_hook` sur le modèle de `set_skill` (L1029) ; `_load_content` charge `content/hooks.yaml` (échec → brique indisponible).
  - `TurnState` (L171) : `hooks: tuple[str, ...]` (actifs si la brique est effective) et `injection: str = ""` ; `Exchange` (L145) : `injection: str = ""`. `_messages` (L837) : `Part(HOOK_INJECTION, …, "hooks", "hooks.h3")` avant le message du tour, et `Part(HISTORY, …)` avant `ex.user` dans l'historique.
  - `_hook(point, state, **ctx) -> HookResult | None` : appelle les hooks actifs du point, valide, émet `hook_decided` sur une nouvelle étape, s'arrête au premier `block`. `_run_tool(call, spec, state, cancel, effects) -> str | None` extrait de `_turn` (L1461-1476) : `before_tool` (block, modify), exécuteur, `after_tool` ; c'est là que 8b branchera `ask_human` et que la story 9 passera.
  - `_run_turn` (L1346) : `on_user_message` avant `_turn` (`dataclasses.replace(state, injection=…)`), `on_turn_end` dans `finally` avant `turn_ended`. `_turn` (L1374) : `before_model_call` avant `_render` ; effets `AuditAppend` dans la boucle d'effets (L1484) via `_apply_audit(lines)`, aussi appelée pour `on_turn_end`.
- `src/wavestack/web/app.py` : `POST /api/intentions/hook {hook, enabled}` (404 si inconnu), sur le modèle de `skill` (L225) ; `GET /api/audit` → `{path, text}`.
- `src/wavestack/web/static/app.js` : `applyEnvelope` (L102) : `hook_decided` → étape `{type: "hook"}`, `effect_applied` rattache ses lignes à la dernière étape `hook` ; `renderSteps` (L930) : carte via `harnessEvent` (L778, `is-error` pour `block`) + mention de `malformedCard` (L926) ; `setOption` (L468) → `/api/intentions/hook` ; `BRICK_ICONS` (L1063) : `hooks` ; `renderSchema` (L1238-1273) : `detail_fr` dans l'infobulle de tout nœud, classe `is-blocked` sur un nœud de hook qui a bloqué dans le dernier tour, clic sur `file.audit` → tiroir (`<dialog>` en lecture seule, ou le tiroir existant du prompt système s'il se réutilise). `app.css` : `.arch-node.is-blocked` (filet `--color-state-error`).
- Tests : réutiliser `FakeEngine`, `QWEN`, `call`, `_segments` (`tests/test_tools.py`), `_run` (`tests/test_turn.py`), aides de `tests/test_skills.py` (L22-64). `config.data_dir()` pointe vers `tmp_path` (voir `tests/conftest.py`).

## Tasks & Acceptance

**Execution:**
- [x] `content/hooks.yaml`, `content/bricks/hooks.yaml` -- libellés, texte H3, carte -- AD-19, FR-27
- [x] `src/wavestack/hooks.py`, `session/effects.py`, `bricks/registry.py`, `trace/catalog.py` -- contrat de hook, trois hooks, `AuditAppend`, brique, événements -- AD-2, AD-12, AD-13, AD-23
- [x] `src/wavestack/session/app_session.py` -- points d'accroche, `_run_tool`, audit, injection, sous-options, schéma -- AD-13, AD-14, AD-17
- [x] `src/wavestack/web/app.py`, `static/app.js`, `static/app.css` -- intention `hook`, `GET /api/audit`, cartes, tiroir, schéma -- AD-1, AD-18
- [x] `tests/test_hooks.py` -- les lignes de la matrice ; chaque rendu : somme des tokens égale au total, aucun `harness_error` d'attribution

**Acceptance Criteria:**
- Given H1 actif et l'outil de lecture activé, when le modèle demande le fichier du dossier confidentiel, then Orchestration montre un événement rouge du harnais, l'outil ne s'exécute pas et la réponse finale du modèle s'affiche sans maquillage.
- Given H3 actif, when on ouvre Contexte LLM sur un appel, then l'ajout du hook est coloré « Ajout d'un hook » et attribué à la brique Hooks, distinct du message de l'utilisateur.
- Given H2 actif, when un tour se termine, then les lignes ajoutées s'affichent dans l'étape H2 et dans le tiroir du journal.

## Implementation Notes

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 34 constats) :

- [VG1/BH7a] `before_tool` `modify` (remplacement d'arguments) n'est exercé par aucun test. Pré-vérifié. -> P1 `patch`.
- [BH7b] Un hook qui lève une exception et un `content/hooks.yaml` invalide n'ont aucun test. `low`, confirmé (seuls les chemins heureux et l'échec d'écriture sont testés). -> P2 `patch`.
- [BH3] H2 et `_hook` filtrent le journal du processus par `turn_id` : plusieurs `AppSession` (tests) repartent de `t1` et H2 relit les événements d'un autre `t1`. `medium`, confirmé (`trace/journal.py` L87 : journal global jamais vidé, `tests/conftest.py` ne le remet pas à zéro ; l'ordre des tests décide). Correction directe : ne lire que les événements postérieurs au `turn_started` du tour. -> P3 `patch`.
- [VG-o1/BH2/EC4] Le message d'échec d'écriture promet une reprise « au prochain déclenchement », fausse quand l'échec a lieu en `on_turn_end`. `low`, confirmé ; correction du texte. -> P4 `patch`.
- [BH1] Le `detail_fr` de H2 dit « N lignes ajoutées » avant l'écriture, faux si elle échoue. `low`, confirmé ; correction du texte. -> P5 `patch`.
- [VG-o4/EC1] Un `block` en `on_turn_end` remplace un statut `error`, `cancelled`, `limit` ou `overflow` par `blocked`. `low`, confirmé (L1499) ; correction d'une condition. -> P6 `patch`.
- [VG-o3] L'aperçu de la jauge (`_emit_preview`) omet le segment H3, alors que chaque tour le porte. `medium`, confirmé (`build_turn_state()` laisse `injection` vide) : la jauge contredit la carte (« deux coûts en tokens »). -> P7 `patch`.
- [BH8/EC10/EC12] `GET /api/audit` ne gère que `FileNotFoundError` (500 sur un dossier, un fichier verrouillé ou non UTF-8), et `openAudit` n'examine pas `response.ok`. `low`, confirmé. -> P8 `patch`.
- [EC7] H1 annonce « lecture permise » pour un chemin qui sort du dossier de démonstration, puis `read_file` le refuse : la trace se contredit. `low`, confirmé (`guard` ne teste que le dossier confidentiel). -> P9 `patch`.
- [EC8] H1 compare les chemins en respectant la casse : sur un système de fichiers insensible à la casse (macOS), `CONFIDENTIEL/budget_projet.txt` passe le garde-fou et le fichier est lu. `medium`, confirmé (`PosixPath.is_relative_to` respecte la casse, `resolve()` ne normalise pas la casse sur macOS) ; contournement d'un garde-fou. -> P10 `patch`.
- [EC9] Les appels d'outil refusés (mal formés, inconnus, arguments invalides) n'apparaissent pas dans le journal d'audit. `low`, confirmé ; fréquent avec un SLM, et le scénario SOC veut voir les tentatives. -> P11 `patch`.
- [BH12] Les `Literal` des points et décisions sont écrits deux fois (`trace/catalog.py`, `hooks.py`) ; la story 8b devra modifier les deux pour `ask_human`. `low`, confirmé. -> P12 `patch`.
- [VG2] La reprise par H2 des lignes d'une écriture échouée dans le même tour n'a aucun test. Pré-vérifié. -> `defer`.
- [BH10] Le journal entier ne s'ouvre qu'à la souris : un nœud SVG du schéma n'a ni `tabindex` ni gestion du clavier. `low`, confirmé ; préexistant pour tous les nœuds du schéma. -> `defer`.
- [VG-o2/BH9] Le front n'affiche pas le statut de tour `blocked`. `low`, rejeté : aucun hook de démonstration ne bloque en `before_model_call` ni en `on_turn_end`, seul un hook de test y parvient.
- [BH4] Les lignes d'audit ne distinguent pas deux lancements (`t1` répété). `low`, rejeté : l'horodatage les distingue.
- [BH5/EC2/EC3/EC13] H2 et un blocage en `on_turn_end` : ordre des lignes, statut écrit avant le blocage, texte de la carte. `low`, rejetés : inatteignables avec les hooks de démonstration.
- [BH6/EC5] Plusieurs hooks qui modifient : seul le dernier compte ; arguments remplacés non revérifiés. `low`, rejetés : aucun hook livré ne remplace d'arguments.
- [BH7c] L'assertion d'ordre `kinds.index(...) - 2` dépend du gabarit. `low`, rejeté : le gabarit des tests est figé (`QWEN`).
- [BH8b/EC11] `audit.log` grandit sans limite et part entier à chaque ouverture. `low`, rejeté : volume de démonstration.
- [BH11] `budget_review` lit `confidentiel/budget_projet.txt`, que H1 bloque. `false` : voulu, la story 7 l'a écrit pour servir de cible au hook H1 (Décisions de la story 7).
- [BH13] Les identifiants d'étape des hooks (`t1.main.h1`) s'écartent de la convention `s{n}` et ressemblent aux ids des hooks. `low`, rejeté : aucun consommateur ne les lit ; la correction partage le compteur d'étapes entre `_turn` et `_run_turn`.
- [BH14] La carte de blocage répète « Bloqué par le hook garde-fou » (titre et détail). `low`, rejeté : cosmétique ; le détail est le texte réinjecté, montré tel quel.
- [BH15] Le nom du fichier de spec garde `h5`. Rejeté : la correction modifie la spec.
- [EC6] Un effet de hook autre qu'`AuditAppend` serait ignoré sans bruit. `low`, rejeté : aucun hook n'en renvoie.
- [EC14] `effect_applied` peut se rattacher à la mauvaise carte de hook. `false` : il est émis juste après le `hook_decided` du même hook, sur la même étape (`_hook`).

Groupes routés en `patch` : P1 à P12 ; `defer` : VG2, BH10 ; aucun `intent_gap` ni `bad_spec`, pas de retour en arrière.

## Design Notes

Les hooks passent par la session et non par `ToolExecutor` : `ask_human` (8b) change l'état de la session (AD-3), et l'exécuteur n'y a pas accès. `_run_tool` regroupe `before_tool`, exécution et `after_tool` en un seul chemin, celui que prendront l'action forcée et le sous-agent (AD-14). Un hook bloquant forme sa propre étape, et l'étape de l'outil n'existe pas : « l'outil ne s'allume jamais » (EXPERIENCE.md, Flow 2).

H2 est sans état : il déduit des événements du tour ce qui suit sa dernière écriture (`effect_applied` sur `file.audit`), ce qui garde le fichier dans l'ordre chronologique alors qu'il écrit à deux points d'accroche.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks (if no CLI):**
- `uv run wavestack` : activer « Outils » et « Hooks » ; demander le budget du dossier confidentiel (événement rouge, nœud H1 rouge) ; cliquer sur « Journal d'audit » ; vérifier l'ajout H3 dans Contexte LLM.
