---
title: 'Lazy loading MCP : documentation chargée à la demande du modèle'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '202452b1e123edc9e266d6317ebeffaf9bde3c03'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** En documentation complète, chaque outil MCP entre dans la variable `tools` avec toute sa documentation : data.gouv.fr dépasse la fenêtre par défaut, et rien ne montre l'autre voie, où le harnais ne charge une documentation que lorsque le modèle la demande (CAP-22, FR-21).

**Approach:** Une bascule « Lazy loading » dans la carte MCP. En lazy loading, les outils MCP sortent de `tools` ; un méta-outil du harnais, `load_tool_doc`, les liste à raison d'une ligne par outil dans sa description. Sa réponse apporte la documentation de l'outil demandé, qui devient appelable dans le même tour, puis entre dans `tools` aux tours suivants (AD-25, AD-23, AD-4). La brique `mcp`, le registre, l'exécuteur et les connexions de la story 6 sont réutilisés tels quels.

## Boundaries & Constraints

**Always:**
- AD-25 : `load_tool_doc(tool: string)` a la source `harness`, appartient à la brique `mcp` (composant `core.harness`) et passe par l'exécuteur unique. Il n'est dans `tools` qu'en lazy loading, et seulement si au moins un outil MCP disponible n'est pas encore chargé. Sa description se compose d'une phrase d'introduction, puis d'une ligne par outil MCP disponible non chargé : `- {nom exposé} : {première ligne de sa description, coupée à 120 caractères avec « … »}`. Chaque ligne est un segment `tool_catalog` distinct, attribué à `mcp` et au composant `mcp.{server}` de l'outil.
- AD-4 : la réponse de `load_tool_doc` est la définition JSON de l'outil, celle que `tools` porterait. C'est un segment `tool_catalog` (brique `mcp`, composant du serveur), jamais compressible. Aux tours suivants, l'historique garde à sa place le talon « Documentation de « X » chargée. », de type `history`. La définition entre dans `tools` au tour suivant, pas pendant le tour : le préfixe du tour reste réutilisé.
- AD-23 : le méta-outil n'écrit aucun état ; il renvoie l'effet `ToolDocLoaded{tool}` (`session/effects.py`), que la session applique.
- Même tour : l'exécuteur et l'analyseur d'appels tiennent pour documentés les outils du `TurnState` et ceux de `loaded_in_turn`.
- Appel d'un outil MCP disponible dont la documentation n'est pas chargée : refusé avant tout envoi, rien ne part vers le serveur, et l'erreur est réinjectée : « La documentation de « X » n'est pas chargée : appelle d'abord load_tool_doc avec tool="X". » Le refus compte comme un essai, comme tout appel refusé (5a).
- « Vider la conversation » décharge toutes les documentations. Une documentation chargée d'un serveur décoché ou indisponible est ignorée tant que le serveur ne revient pas.
- La bascule est une intention de classe (a) : elle prend effet au tour suivant, avec « Prend effet au prochain tour », et l'aperçu de la jauge montre aussitôt l'écart de tokens entre les deux modes (FR-21). La bascule ne recontacte aucun serveur.
- Carte de dépassement : quand les descriptions d'outils sont la cause et que le mode est documentation complète, la piste proposée est de passer la carte MCP en lazy loading ou de désactiver un serveur.
- UX : interrupteur « Lazy loading » dans la carte MCP, sous la liste des serveurs ; étape « Chargement de la documentation » dans Orchestration, avec le badge MCP.

**Décisions (2026-09-24) :**
- À l'activation de la brique, le mode par défaut est la documentation complète. C'est l'ordre du programme (PRD : « documentation complète, puis lazy loading ») et le comportement livré en story 6.
- Le mode s'applique à tous les serveurs MCP, le serveur local compris (FR-21 : « toutes les descriptions d'outils MCP »).
- Recharger une documentation déjà chargée renvoie « La documentation de « X » est déjà chargée. », en `tool_result` : son contenu n'est pas compté deux fois.
- Un nom inconnu passé à `load_tool_doc` est une erreur réinjectée qui liste les outils chargeables.

**Never:** pas d'action forcée « Charger la documentation » ni de rejeu (story 9) ; pas de `remember`, `load_skill` ni `delegate` ; pas d'autre effet que `ToolDocLoaded` dans `effects.py` ; pas d'ajout de définition à `tools` pendant un tour ; pas de reconnexion des serveurs au changement de mode ; le front ne calcule aucun état (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Bascule | Lazy loading coché, serveur local disponible | Aperçu : `tools` contient `load_tool_doc` et plus `local__*` ; une ligne `tool_catalog` par outil, attribuée à `mcp.local` ; moins de tokens qu'en documentation complète | N/A |
| Chargement | Le modèle appelle `load_tool_doc(tool="local__define_term")` | Étape « Chargement de la documentation » ; réponse `tool_catalog` (brique `mcp`, composant `mcp.local`) | Nom inconnu : erreur réinjectée listant les outils |
| Même tour | Puis `local__define_term(term="MCP")` au même tour | Accepté, arguments typés selon son schéma, résultat réinjecté | N/A |
| Tour suivant | Nouveau message | `local__define_term` dans `tools`, sa ligne retirée de `load_tool_doc`, talon `history` à la place de la réponse | N/A |
| Non documenté | Appel de `local__list_terms` sans chargement | Refusé, aucun envoi au serveur, erreur réinjectée | Compte comme un essai |
| Déjà chargé | `load_tool_doc` sur un outil déjà chargé | Réponse courte « déjà chargée », en `tool_result` | N/A |
| Tout chargé | Tous les outils disponibles chargés | `load_tool_doc` absent de `tools` | N/A |
| Vider | « Vider la conversation » | Plus aucune documentation chargée ; aperçu mis à jour | N/A |
| Serveur retiré | Serveur d'un outil chargé décoché | Son outil disparaît de `tools` ; il revient avec le serveur | N/A |
| Dépassement | data.gouv.fr en documentation complète, fenêtre 4 096 | La cause propose de passer la carte MCP en lazy loading | Appel non envoyé |
| Lazy + data.gouv.fr | Même configuration en lazy loading | Pas de dépassement : seulement 10 lignes courtes | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/context/segments.py` (L33) : `Part` est un NamedTuple `(kind, text, brick, component, group)`. Ajouter `Joined(parts: tuple[Part, ...], sep: str)`.
- `src/wavestack/context/render.py` : dans `prepare` (L243-253), un `Joined` donne le texte `sep.join(textes)` au rendu envoyé et `sep.join(textes marqués)` au rendu d'attribution. Les séparateurs vont à `template`. Chaque ligne a son propre `group` (le nom exposé de l'outil), sinon `_merge_groups` (L188) les fusionne. `_locate_in_order` (L171) fonctionne déjà part par part. Le gabarit Qwen fait `tojson` : `\n` est échappé de la même façon dans les deux rendus.
- `src/wavestack/session/effects.py` (nouveau) : `ToolDocLoaded(BaseModel){kind: Literal["tool_doc_loaded"], tool: str}` et `Effect = ToolDocLoaded`, union à un seul membre, extensible (AD-23).
- `src/wavestack/tools/registry.py` (L31-52) : `ToolSpec` reçoit `brick: str | None = None`, que la brique prend en priorité sur `component.split(".")[0]`. `run` peut renvoyer `ToolReply(text, effects)` (NamedTuple dans `effects.py`). `add` (L92-113) écarte une spec sans `description` qui n'est pas dans `content/tools.yaml` : le méta-outil fournit la sienne. La description est construite à chaque tour (voir `_tool_definitions`).
- `src/wavestack/tools/executor.py` : `check(call, enabled, loadable=())` (L45) renvoie le message « documentation non chargée » quand `call.name` est dans `loadable` mais pas dans `enabled`. `run(call, cancel, effects: list | None = None)` (L82) déballe un `ToolReply`, ajoute ses effets à `effects` et renvoie le texte comme avant.
- `src/wavestack/session/app_session.py` :
  - État : `_mcp_lazy: bool = False` et `_loaded_docs: set[str]` (la conversation, AD-17). `set_mcp_mode(lazy)` est une intention de classe (a) : l'ajouter au tuple `_sent`/`_pending_ids` (L221-226, L330-343, L798-804), puis émettre `bricks_changed` et l'aperçu. `_emit_bricks` (L406) ajoute `mode: "full"|"lazy"` au payload de la brique `mcp`. `_tool_options` (L359) et `set_tool` (L831) écartent la source `harness`.
  - `TurnState` (L153) reçoit `loadable: tuple[str, ...]`, les outils MCP disponibles non chargés. `build_turn_state` (L601) : en documentation complète, rien ne change ; en lazy loading, `tools` reçoit les outils MCP disponibles déjà chargés, plus `load_tool_doc` si `loadable` n'est pas vide.
  - Le méta-outil est enregistré une fois au démarrage, à côté des outils natifs (L209) ; son `run` lit le registre et renvoie `ToolReply`.
  - `_tool_definitions` (L709) : pour `load_tool_doc`, la description est un `Joined` construit depuis `state.loadable` ; ailleurs, la brique vient de `spec.brick or component.split(".")[0]`.
  - Boucle `_turn` (L1083) : un `loaded_in_turn: set[str]` par tour. `check(call, state.tools + tuple(loaded_in_turn), loadable=state.loadable)`. La brique suit `spec.brick` (L1155). Après `run`, la session applique les effets : `_loaded_docs.add`, `loaded_in_turn.add`. L'étape outil de `load_tool_doc` reçoit `"kind": "tool_catalog"` et `"stub"`.
  - `_call_model` (L1331) : `schemas` couvre aussi `loaded_in_turn` ; la liste d'outils passée est complétée en conséquence.
  - `_step_messages` (L636) : `step.get("kind", TOOL_RESULT)` pendant le tour, `step["stub"]` s'il existe dans l'historique.
  - `clear_conversation` (L1029) vide aussi `_loaded_docs`. `_OVERFLOW_CAUSES_FR[TOOL_CATALOG]` (L96) : texte choisi selon `_mcp_lazy`, avec la piste du lazy loading en documentation complète.
- `content/bricks/mcp.yaml` : `explanation_fr` complétée par les deux modes et l'écart de tokens. `content/mcp.yaml` : `lazy_label_fr`, et les textes de `load_tool_doc` (`label_fr` « Chargement de la documentation », phrase d'introduction, description du paramètre `tool`).
- `src/wavestack/web/app.py` (L201-208, sur le modèle de `mcp_server`) : `POST /api/intentions/mcp_mode {lazy: bool}`.
- `src/wavestack/web/static/app.js` : `brickOptions` (L412-446) ajoute l'interrupteur quand `brick.id === "mcp"`, et `setOption` (L448) l'envoie vers `/mcp_mode`. `toolCard` (L810) affiche le badge MCP quand la source commence par `mcp`, ou quand elle vaut `harness` pour la brique `mcp`.
- `tests/test_mcp_lazy.py` (nouveau) : réutilise `mcp_session`, `enable`, `wait_for`, `loop`, `web` de `tests/test_mcp.py` (L62-182), `call` et `_segments` de `tests/test_tools.py`, et `_run` de `tests/test_turn.py`. Serveur local réel et `McpWeb` pour data.gouv.fr ; `FakeEngine` avec des sorties scriptées.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/context/segments.py`, `context/render.py` -- `Joined` et son rendu avec sentinelles -- AD-4
- [x] `src/wavestack/session/effects.py`, `tools/registry.py`, `tools/executor.py` -- `ToolDocLoaded`, `ToolReply`, `ToolSpec.brick`, `check(loadable)`, effets de `run` -- AD-23, AD-25
- [x] `src/wavestack/session/app_session.py`, `content/bricks/mcp.yaml`, `content/mcp.yaml` -- mode, méta-outil, `loadable`/`loaded_in_turn`, talon, déchargement, cause de dépassement -- AD-4, AD-17, AD-25
- [x] `src/wavestack/web/app.py`, `static/app.js` -- intention `mcp_mode`, interrupteur, badge -- AD-1, AD-18
- [x] `tests/test_mcp_lazy.py` -- les 11 lignes de la matrice ; avec `Joined` sur le gabarit Qwen et `FakeEngine`, aucun `harness_error` d'attribution et une somme des tokens égale au total. Le test `model` de `tests/test_render_reference.py` prévoit déjà le cas « `load_tool_doc` avec deux serveurs » (AD-4) : y ajouter ce cas.

**Acceptance Criteria:**
- Given data.gouv.fr disponible et le mode documentation complète, when on coche « Lazy loading », then la jauge « prochain tour » baisse, et l'écart porte sur les segments `tool_catalog` du serveur.
- Given un tour où le modèle charge puis appelle un outil, when on ouvre Contexte LLM, then la réponse de `load_tool_doc` est colorée comme la documentation d'outil MCP, et au tour suivant elle n'apparaît plus qu'en talon dans l'historique.
- Given le lazy loading actif, when on ouvre le détail de la jauge au survol, then chaque ligne de `load_tool_doc` est comptée dans la brique MCP.

## Implementation Notes

- Implémenté par un sous-agent (dispatch) ; j'ai relu le diff dans cette session. Vérifié : `ruff check` et `ruff format --check` propres, `node --check` propre. `pytest` : 205 passed, 2 deselected, 1 échec hors story (`test_tokens_css_matches_design_frontmatter`), dû aux tokens de la refonte « atelier de construction » ajoutés à `DESIGN.md`, modification non commitée qui ne touche pas la 6b. Test `model` sur Qwen3.5-9B (`WAVESTACK_TEST_GGUF`) avec `load_tool_doc` et deux serveurs : lancé par le sous-agent, qui rapporte qu'il passe ; non relancé dans cette session.
- Audit de la matrice : les 11 lignes sont couvertes par `tests/test_mcp_lazy.py`, tous les tests ont tourné. Le serveur local est un vrai processus enfant, data.gouv.fr est simulé par `McpWeb`.
- Ajouts hors Code Map : `ToolSpec.label_fr` (libellé « Chargement de la documentation ») ; `BrickState.mode`/`lazy_label_fr` dans `trace/catalog.py` ; `McpContent.load_tool_doc`/`lazy_label_fr` dans `mcp/servers.py`. Pour un outil du harnais, `phase_label` porte le libellé seul.
- Choix : `load_tool_doc` lit l'état courant des serveurs, pas le `TurnState` (relevé en revue, BH3, rejeté). Une documentation chargée l'est dès l'application de l'effet, même si le tour s'arrête ensuite (EC3, rejeté). La ligne coupée garde 120 caractères, suivis de « … ».
- Passe manuelle dans l'interface avec un vrai modèle non faite.
- Correctifs de revue P1 à P7 appliqués par le même sous-agent et vérifiés dans cette session (voir ci-dessus).

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 23 constats) :

- [VG1] Le test du badge « Prend effet au prochain tour » après une bascule de mode ne peut pas échouer : la brique n'a jamais été envoyée, `pending` est vrai de toute façon. Constat pré-vérifié. → P1 `patch` (test entre deux tours).
- [VG2] La cause de dépassement en lazy loading n'est vérifiée par aucun test. Constat pré-vérifié. → P2 `patch`.
- [BH2/EC5] `_emit_overflow` lit le mode courant, pas celui qu'a figé l'envoi. Une bascule entre l'envoi et le rendu donne un conseil contraire au contexte réellement rendu. `low`, confirmé ; la correction est directe (`_sent[4]`). → P2 `patch`.
- [VG3/BH9] Le refus de `set_tool("load_tool_doc")` n'est vérifié par aucun test. Constat pré-vérifié. → P3 `patch`.
- [BH8] Le typage des arguments au même tour n'est pas testé : avec un argument texte, retirer `loaded_in_turn` des schémas passerait inaperçu. `medium`, confirmé (seul `term="MCP"` est testé). → P4 `patch`.
- [BH10/EC6] Un outil sans description donne la ligne `- nom : `. `low`, confirmé ; la correction est directe. → P5 `patch`.
- [BH4] L'interrupteur est dans le `<details>` replié : la carte fermée ne montre pas le mode. `low`, confirmé ; une ligne dans le résumé. → P6 `patch`.
- [BH11] L'explication de la brique ne dit pas pourquoi la documentation n'entre dans `tools` qu'au tour suivant, ni comment elle se décharge. `low`, confirmé ; contenu pédagogique, une phrase. → P7 `patch`.
- [VG4] Le rendu front (interrupteur, `setOption("mcp_mode")`, carte d'étape du harnais) n'est vérifié par aucun test automatique. `medium`, même écart qu'en 5b et 6 : le dépôt n'a aucun banc de test JS. → `defer`.
- [EC4] Au rejeu (`origin_turn`), `_loaded_docs` garderait les documentations chargées après le point de branchement. `low`, le rejeu n'existe pas encore (story 9). → `defer` vers la story 9.
- [BH1] Dépassement dû aux seuls outils natifs, MCP éteint : le message propose le lazy loading. `low`, rejeté : le catalogue natif ne dépasse pas la fenêtre par défaut, et la correction ajoute une condition.
- [BH3/EC1] `load_tool_doc` vérifie la liste d'outils du moment, pas `state.loadable` : un serveur connecté en plein tour rend chargeable un outil absent de la description. `low`, rejeté : le modèle devrait deviner le nom, et le serveur est déjà connecté par l'utilisateur ; il faudrait passer l'état du tour au méta-outil.
- [EC2] Un outil listé dont le serveur tombe en plein tour reçoit « aucun outil MCP disponible ne s'appelle… ». `low`, rejeté : le message reste juste (l'outil n'est plus disponible).
- [EC3] Une documentation chargée reste chargée après un tour arrêté, en limite ou en dépassement, sans talon dans l'historique. `low`, rejeté : l'effet est bien appliqué par la session ; au tour suivant, la documentation figure dans `tools`, donc visible dans la jauge. Ne l'appliquer qu'au tour terminé demande de faire remonter l'état jusqu'à `_run_turn`.
- [BH5] Les documentations chargées survivent à un aller-retour lazy → complète → lazy. `low`, rejeté : elles suivent la conversation, dont les talons de l'historique témoignent (AD-17).
- [BH6] Le test de troncature (`<= 150`) ne fixe pas `DOC_LINE_MAX`, et la ligne compte 120 caractères plus « … ». `low`, rejeté : qualité de test ; « coupée à 120 caractères avec « … » » admet cette lecture.
- [BH7] Le critère d'acceptation sur l'écart de la jauge n'est vérifié que par `used`. `low`, rejeté : le même test vérifie l'attribution des lignes à `mcp.local`.
- [BH12] `set_mcp_mode` n'émet pas `architecture_changed`. `false` : les nœuds `mcp_server` et leurs outils (`_emit_architecture`, L1085) ne dépendent pas du mode, et `load_tool_doc` n'est pas un nœud.
- [EC7] « Registre et exécuteur réutilisés tels quels », alors que leurs contrats changent. `false` : les ajouts ont des valeurs par défaut rétrocompatibles, et la Code Map les liste.

Groupes routés en `patch` : P1 à P7 ; `defer` : VG4, EC4 ; aucun `intent_gap` ni `bad_spec`, pas de retour en arrière.

## Design Notes

Le préfixe (AD-4, contrôle d'ajout seul) impose le partage même tour / tours suivants : `tools` se rend avant les messages. Y ajouter une définition en plein tour invaliderait tout le cache et produirait `prefix_not_reused`. La documentation n'entre donc qu'en réponse d'outil pendant le tour.

```python
# _tool_definitions, description de load_tool_doc
Joined((Part(TOOL_CATALOG, intro, "mcp", "core.harness", "load_tool_doc"),
        *(Part(TOOL_CATALOG, line(n), "mcp", spec(n).component, n) for n in state.loadable)),
       sep="\n")
```

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks (if no CLI):**
- `uv run wavestack` : brique MCP, data.gouv.fr coché, envoyer un message (dépassement) ; cocher « Lazy loading » et comparer la jauge ; demander « Que veut dire MCP ? » et suivre le chargement puis l'appel ; vider la conversation.
