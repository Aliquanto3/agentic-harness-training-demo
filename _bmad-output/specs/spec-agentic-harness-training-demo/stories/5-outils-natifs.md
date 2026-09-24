---
title: 'Outils natifs (5a) : cycle d''appel et outils hors ligne'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '5a054744ffdfa266fda7360b2393f8d6ebac9719'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le modèle ne peut qu'écrire du texte : il ne sait ni l'heure, ni calculer juste, ni lire un fichier, et rien ne montre comment un harnais lui donne des outils (CAP-14 à CAP-16).

**Approach:** Une brique `tools` (harness engineering) dont chaque outil est une sous-option activable : `get_datetime`, `calculator`, `read_file` (confiné à `content/demo_files/`). Un registre et un exécuteur uniques (AD-14), un analyseur des appels selon le format de la famille (AD-6), une boucle bornée dans la session (AD-10). Le volet Orchestration montre les 5 étapes de chaque appel et chaque échec.

## Boundaries & Constraints

**Always:**
- AD-14 : le `ToolRegistry` seul attribue les noms exposés ; chaque outil déclare `source = native`, `hosting`, `component`, `network`, `reads_local_path`. Tout appel passe par un exécuteur unique ; appel mal formé, outil inconnu ou désactivé, arguments invalides = événement + réaction, jamais d'exception.
- Confinement toujours actif : `read_file` résout le chemin et refuse tout ce qui sort de `content/demo_files/` ; la calculatrice évalue par `ast` avec liste blanche d'opérateurs (jamais `eval`), exposant borné. Un test par cas.
- AD-10 : 6 appels au modèle par tour, dont 2 nouveaux essais après appel mal formé ; au-delà `limit_reached{limit}` puis `turn_ended{status: limit}`.
- AD-4 : descriptions dans la variable `tools` en segments `tool_catalog` (un par outil) ; sortie du modèle réinjectée en `assistant_turn`, résultats en `tool_result` ; les morceaux de gabarit enclavés entre deux textes d'un même outil ou d'un même appel lui sont attribués ; somme = total. Un tour `completed` entre dans l'historique avec ses appels et résultats (`history`). Entre deux appels d'un tour, contrôle d'ajout seul : `prefix_not_reused` sinon.
- AD-6 : la brique exige `tool_call_parser` ; sans lui, indisponible avec une raison en français nommant l'appel d'outils.
- AD-16 : une erreur d'exécution devient `tool_ended{status: error}`, réinjectée au modèle ; le tour continue.
- AD-19 : descriptions des outils (vues par le modèle) et libellés en français dans `content/`, validés par pydantic.
- UX : sous-options dépliables dans la carte avec `hosting-tag-local` ; bornes affichées sur la carte ; `harness-event` rouge pour un appel mal formé (sortie brute, partie fautive, réaction).

**Décisions (2026-09-24) :**
- Story scindée : outils réseau, fabrique AD-15 et données sortantes en 5b (voir `deferred-work.md`).
- Bornes affichées seulement ; réglables dans `wavestack.toml` (`[tools] max_calls = 6`, `max_retries = 2`).
- Activer la brique active les outils hors ligne ; les outils réseau (5b) seront désactivés par défaut.

**Never:**
- Pas d'outil réseau ni de modification de `net/` (5b). Pas de hooks, méta-outils, actions forcées, rejeu (stories 8, 9), ni MCP (story 6).
- Le front ne calcule ni disponibilité, ni contexte (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Cycle complet | Modèle appelle `calculator(expression="12*37")` | `tool_catalog` au contexte, `tool_started`/`tool_ended{ok}`, `tool_result` « 444 » au 2e appel, réponse finale, `completed` | N/A |
| Deux outils | Heure puis calcul dans un tour | 3 appels au modèle, 2 étapes d'outil | N/A |
| Mal formé | Balise `<tool_call>` illisible | `tool_call_malformed{raw, fragment, reaction: retry}`, erreur réinjectée, nouvel appel | 3e échec : `limit_reached{retries}`, `limit` |
| Inconnu ou désactivé | `get_weather(...)` | Même voie, message nommant les outils disponibles | idem |
| Borne d'appels | Un appel d'outil à chaque appel | 6 appels puis `limit_reached{calls}`, `limit` | N/A |
| Évasion | `read_file(path="../../pyproject.toml")` ou absolu | Refus, `tool_ended{error}` réinjecté | Aucune lecture |
| Calcul dangereux | `__import__('os')`, `9**9**9` | Refus en français | N/A |
| Échec d'exécution | Fichier absent, division par zéro | `tool_ended{error}` réinjecté, pas compté comme essai | N/A |
| Brique éteinte | Brique off ou tous outils off | Tour identique au LLM nu, octet pour octet | N/A |
| Modèle sans parseur | Famille inconnue | Brique indisponible avec raison | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/tools/` (nouveau) -- `registry.py` (`ToolSpec`, `ToolRegistry`, définitions JSON pour la variable `tools`), `native.py` (trois outils ; `read_file` via `config.content_dir()/"demo_files"` et `Path.resolve().is_relative_to`), `parser.py` (formats `qwen3_coder` `<tool_call><function=…><parameter=…>` et `hermes` `<tool_call>{json}</tool_call>` ; valeurs converties selon le schéma), `executor.py` (validation, `tool_started`/`tool_ended`, `CancelToken`). N'importe pas `bricks`.
- `src/wavestack/session/app_session.py` -- `_turn` (L572) devient la boucle bornée ; `_call_model` (L606) remplit `model_call_ended.tool_calls` ; `_messages` (L395) ajoute les messages du tour (`assistant` avec `tool_calls`, `tool`) et l'historique étendu ; `_render` (L427) passe `tools` ; `Exchange` (L93) garde les étapes intermédiaires ; `TurnState` (L103) gagne les outils effectifs ; `_pending_ids`/`_sent` (L204, L161) couvrent les sous-options ; `_emit_bricks`/`_emit_architecture` (L214, L175) ajoutent sous-options, bornes, nœuds `tools.{name}` et `file.demo_dir` ; `_availability` (L350) : libellé français de la capacité. Nouvelle intention `set_tool(name, enabled)`, classe (a).
- `src/wavestack/context/render.py` -- `render_context` (L188) : accepter `tools` en `Part` (sentinelles sur les chaînes de la définition, étape 3) et les valeurs de `tool_calls` ; fusion des morceaux de gabarit enclavés par groupe. Rendu des messages existants inchangé.
- `src/wavestack/models/capabilities.py` -- `tool_call_parser` (L21) déjà posé ; `ChannelSplitter` (L69) : canal `tool_call` pour `<tool_call>…</tool_call>`.
- `src/wavestack/trace/catalog.py` -- nouveaux `kind` : `tool_started{tool, arguments, phase_label}`, `tool_ended{status, result, error_fr, duration_ms}`, `tool_call_malformed{raw, fragment, detail_fr, reaction}`, `limit_reached{limit}`, `prefix_not_reused{common_tokens}` ; `BrickState` + `options`, `limits_fr` ; `ArchitectureNode.kind` + `tool`, `file`.
- `src/wavestack/bricks/registry.py` -- brique `tools` (`category=harness`, `capabilities=["tool_call_parser"]`, un composant par outil, `tools.read_file` → `file.demo_dir`).
- `src/wavestack/web/app.py` -- POST `/api/intentions/tool` `{tool, enabled}` (404 si inconnu), calqué sur `/brick`.
- `src/wavestack/web/static/app.js` -- `renderBricks` (L274) : sous-options ; `renderSteps` (L605) : étapes description / demande / exécution / réinjection / réponse et `harness-event`. `GROUP_COLORS` (L31) couvre déjà `tool_catalog`/`tool_result`.
- `content/tools.yaml`, `content/bricks/tools.yaml`, `content/demo_files/` (nouveaux) -- descriptions, libellés, 2-3 fichiers texte en français dont un sous-dossier `confidentiel/` (cible H1, story 8).
- `wavestack.toml` -- section `[tools]`.
- `tests/fake_engine.py` -- `FakeEngine` : sorties scriptées par appel et `architecture` réglable ; tests d'outils sur le gabarit `tests/fixtures/qwen3_5_chat_template.jinja` (architecture `qwen35` → `qwen3_coder`).

## Tasks & Acceptance

**Execution:**
- [x] `trace/catalog.py` -- nouveaux `kind` et champs -- AD-2
- [x] `tools/`, `content/tools.yaml`, `content/demo_files/` -- registre, trois outils, analyseur, exécuteur, confinement -- AD-14, AD-19
- [x] `context/render.py`, `models/capabilities.py` -- `tools` et `tool_calls` attribués, canal `tool_call` -- AD-4, AD-6
- [x] `bricks/registry.py`, `content/bricks/tools.yaml`, `session/app_session.py`, `wavestack.toml` -- brique, sous-options, boucle bornée, historique, `prefix_not_reused`, schéma -- AD-3, AD-10, AD-12, AD-17
- [x] `web/app.py`, `web/static/*` -- intention `tool`, sous-options, 5 étapes, échecs -- AD-1, AD-18
- [x] `tests/` -- les 10 lignes de la matrice ; analyseur des deux formats ; attribution (somme = total, un `tool_catalog` par outil) ; outil inconnu au 404

**Acceptance Criteria:**
- Given la brique outils activée avec un modèle Qwen3.5, when on demande « combien font 12 × 37 ? », then le volet Orchestration montre les 5 étapes et la réponse cite 444.
- Given la brique outils activée, when on regarde la jauge, then le catalogue d'outils y apparaît en « Descriptions d'outils » avec ses tokens.
- Given un appel mal formé, when le tour se poursuit, then l'échec, la partie fautive et la réaction du harnais sont visibles, et WaveStack reste utilisable.

## Implementation Notes

- Implémenté par un sous-agent (dispatch), diff relu dans cette session. `ruff check`, `ruff format --check` : propres. `pytest` : 110 passed, 2 deselected (tests `model`) ; `tests/test_tools.py` : 23 tests, aucun sauté.
- Audit de la matrice I/O : les 10 lignes sont couvertes par `tests/test_tools.py` sur le gabarit Qwen3.5 (cycle, deux outils, mal formé ×3 → `retries`, inconnu/désactivé, borne de 6 appels, évasion ×3, calculs dangereux, erreurs d'exécution non comptées, brique éteinte octet pour octet, modèle sans parseur).
- Vérification dans Chrome par le sous-agent avec le moteur factice : 5 étapes, carte rouge avec fragment surligné, jauge « Descriptions d'outils », nœuds d'outils et « Fichiers de démonstration ». Aucun vrai modèle lancé (seul le 9B est présent sur D:).
- Choix de l'implémentation : `Part.group` pour la fusion des morceaux enclavés ; ordre des clés de définition (nom en premier, description en dernier) pour que presque tout le catalogue soit attribué à l'outil ; `read_file(".")` liste les fichiers ; calculatrice accepte × ÷ et la virgule décimale ; `limit_reached` et `prefix_not_reused` portent un `message_fr`.
- Risques signalés : `<tool_call>` peut être un token spécial du GGUF réel (neutralisé dans une sortie mal formée réinjectée, puis `prefix_not_reused`) ; `prefix_not_reused` compare à `tokenize(raw_output)`, pas aux ids générés ; arguments non textuels comptés `template` ; l'étape « Réinjection » compte tous les `tool_result` de l'appel.
- Correctifs de revue G1 à G11 appliqués par le même sous-agent (tests d'arrêt, dernier appel, bornes configurées, `<think>` ouvrant, arête ; bornes plancher ; raisonnement non doublé ; textes ; fragment source ; sous-options conservées ; constante unique ; tests POSIX ; ton rouge ; virgule refusée ; nœud fichier). `pytest` final : 114 passed, 2 deselected ; `ruff` propre. Nouvelle passe navigateur non faite ; vérification avec un vrai Qwen3.5 toujours à faire.

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 36 constats) :

- [VG1] Arrêt pendant un tour avec outils jamais testé (`result is None`, contrôle d'annulation après les outils) — `medium`, pré-vérifié. → G1 `patch`.
- [VG2] Réaction d'un appel refusé au dernier appel permis (`n == max_calls`) non testée — `low`, pré-vérifié. → G1 `patch`.
- [VG3/BH16c] Section `[tools]` de la configuration jamais lue par un test (défauts identiques au toml) — `medium`, pré-vérifié. → G1 `patch`.
- [VG4/BH16b] `<think>` ouvrant depuis le canal texte avec les balises d'outil non testé — `low`, pré-vérifié. → G1 `patch`.
- [VG5] Arête `tools.read_file → file.demo_dir` non vérifiée — `low`, pré-vérifié. → G1 `patch`.
- [BH7/EC1] `max_calls <= 0` ou `max_retries < 0` non bornés : tout tour, même LLM nu, finit en `limit` sans appel — `low`, confirmé (`config._int`), correction directe `max(1, …)`/`max(0, …)`. → G2 `patch`.
- [BH2/EC2] Branche mal formée : `content = out.raw` contient déjà le raisonnement et `reasoning` est aussi passé, rendu deux fois par le gabarit Qwen — `low`, confirmé ; peu probable tant que `enable_thinking=False` (L623), correction par suppression. → G3 `patch`.
- [BH4] Détail de l'analyseur sans point final : « …mal fermée Corrige l'appel » réinjecté — `low`, confirmé (`executor.reject`). → G4 `patch`.
- [BH14] Libellés de borne « appels mal formés » alors que le compteur inclut outils inconnus et arguments invalides — `low`, confirmé. → G4 `patch`.
- [VG-autre2] Carte « erreur réinjectée, puis arrêt » alors que le tour s'arrête sans rappeler le modèle — `low`, confirmé (`_turn` rend `limit` juste après). → G4 `patch`.
- [BH5/VG-autre3] Fragment d'un appel refusé = repr Python (`calculator({'expression': …})`), jamais trouvé dans la sortie brute : la carte ne surligne rien — `low`, confirmé (`_turn` L912, `malformedCard`). → G5 `patch`.
- [BH8/VG-autre1] Réactiver la brique réactive les outils que l'utilisateur avait éteints (`set_brick` réécrit `_tools_enabled`) — `low`, confirmé ; la décision « activer la brique active les outils hors ligne » est un défaut, satisfait en l'initialisant une fois. → G6 `patch`.
- [BH11] Balises `<tool_call>` définies deux fois (`parser.py`, `capabilities.py`) — `low`, correction directe (import). → G7 `patch`.
- [BH13/EC7/EC12] Tests d'évasion `C:/Windows/win.ini` et `..\..\` propres à Windows : échec sous POSIX (le code reste sûr : « Fichier absent ») — `low`, confirmé (`PurePosixPath('C:/…').anchor == ''`). → G8 `patch`.
- [BH17] `limit_reached{retries}` affiché en violet (info) alors que DESIGN.md veut le rouge pour un échec — `low`, confirmé. → G9 `patch`.
- [EC4] `calculator("1,000*3")` rend `3` : la virgule décimale donne un faux résultat « exact » — `medium`, confirmé à l'exécution. → G10 `patch`.
- [EC9] Nœud `file.demo_dir` dessiné disponible alors que la brique est indisponible — `low`, confirmé (`_emit_architecture`), atteignable avec un modèle non Qwen. → G11 `patch`.
- [BH1] `<tool_call>` écrit dans le raisonnement exécuté quand même — `low`, rejeté : `enable_thinking=False` (L623), pas de raisonnement avant la brique raisonnement (palier 2) ; la garde ajoute une branche.
- [BH3] Au dernier appel permis, les outils s'exécutent puis `limit_reached{calls}` — `false` : c'est l'ordre du déroulé du spine (exécution, puis « Borne d'appels atteinte ? »).
- [BH6] `read_file` sans plafond de taille ni gestion non-UTF-8 — `low`, rejeté : `demo_files/` est un contenu du dépôt, en UTF-8 et court.
- [BH9] Écart silencieux entre `tools.yaml` et les `ToolSpec` — `low`, rejeté : défaut de développeur, garde ajoutant des branches.
- [BH10] Surface spéculative (`source`, `hosting`, `reads_local_path`, statuts `blocked|limit|overflow`, `sub_calls`) — `false` : exigée par AD-14 et le catalogue d'AD-2.
- [BH12/EC6] Produit de puissances au-delà de 4 300 chiffres → `ValueError` enrobée ; `1e308*10` → `inf` — `low`, rejeté : entrée improbable, message déjà en français (enveloppe de l'exécuteur), garde supplémentaire.
- [BH15] Raisonnement du tour compté `template` — `low`, rejeté : raisonnement désactivé ; déjà signalé `ponytail:` (story 4).
- [BH16a/d] Boucle complète au format `hermes`, test unitaire de `_merge_groups` — `low`, rejetés : la boucle ne dépend que du nom d'analyseur, testé ; la fusion est couverte par le test d'attribution.
- [EC3] Appels complets puis sortie coupée dans le canal texte : `tool_calls` listés mais non exécutés — `low`, rejeté : exige 512 tokens de texte après un appel, que le gabarit interdit ; garde supplémentaire.
- [EC5] `(-8)**(1/3)` rend un complexe — `low`, rejeté : improbable, résultat affiché sans plantage.
- [EC8] Un outil qui rend `None` pris pour une annulation — `low`, rejeté : aucun outil ne rend `None` (contrat `Callable[..., str]`).
- [EC10] `toolCard` affiche `blocked|limit|overflow` comme erreur d'exécution — `false` : aucun de ces statuts n'est émis dans cette story (hooks en story 8).
- [EC11] Repli `_locate_in_order` si un gabarit rend `tools` après les messages — `low`, rejeté : exige un gabarit inhabituel et l'échec du contrôle 4.

Groupes routés en `patch` : G1 (tests), G2 (bornes), G3 (raisonnement doublé), G4 (textes), G5 (fragment), G6 (sous-options), G7 (balises), G8 (tests POSIX), G9 (ton), G10 (virgule), G11 (nœud fichier) ; aucun `intent_gap` ni `bad_spec`, pas de loopback.

## Design Notes

Réactions (AD-14) : erreur d'analyse, outil inconnu/désactivé ou arguments invalides = « nouvel essai » (erreur réinjectée en réponse d'outil, compte un essai) ; 3e échec = arrêt. Une erreur d'exécution n'est pas un essai. Une sortie coupée dans le canal `tool_call` suit la voie de l'appel mal formé (AD-9). `get_datetime` rend l'heure locale du poste (`datetime.now().astimezone()`), sans fuseau à choisir.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)

**Manual checks (if no CLI):**
- `uv run wavestack` avec Qwen3.5 : activer la brique outils, demander l'heure, un calcul, puis le contenu d'un fichier de démonstration ; vérifier les 5 étapes, la jauge et le schéma ; désactiver un outil et vérifier l'erreur réinjectée quand le modèle l'appelle.
