---
title: 'Skills, dont Caveman : catalogue et chargement progressif visible'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: 'c0d240632012b49c52fe8507eb8a7b5fedf0b95d'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Rien ne montre encore ce qu'est un skill ni en quoi il diffère d'un outil, d'un serveur MCP ou d'un prompt système : un paquet d'instructions dont seuls le nom et la description occupent le contexte tant que le modèle ne le déclenche pas (CAP-24 à CAP-26, FR-23 à FR-25).

**Approach:** Une brique « Skills » avec plusieurs skills de démonstration, dont Caveman, activables un à un. Le catalogue (une ligne par skill) entre dans le message système ; le méta-outil du harnais `load_skill` charge le contenu d'un skill, qui répond à l'appel pendant le tour puis rejoint le message système aux tours suivants (AD-4, AD-23, AD-25). Le mécanisme de `load_tool_doc` (story 6b) est repris tel quel : effet typé, talon dans l'historique, déchargement avec la conversation.

## Boundaries & Constraints

**Always:**
- AD-19 : un skill est un fichier `content/skills/{id}/SKILL.md`, en français, avec un en-tête YAML `name` (l'id, celui que reçoit `load_skill`), `label_fr` et `description`, puis le corps. Un fichier absent ou invalide rend la brique indisponible avec sa raison, jamais un plantage.
- AD-4, catalogue : tant qu'au moins un skill activé n'est pas chargé, le message système porte, après le prompt système, une phrase d'introduction puis une ligne par skill activé non chargé : `- {name} : {description}`. Chaque ligne est un segment `skill_catalog` distinct (brique `skills`, composant `skills.{id}`). Sans la brique « Prompt système », le message système ne contient que les segments des skills.
- AD-25 : `load_skill(skill: string)` a la source `harness`, appartient à la brique `skills` (composant `core.harness`), passe par l'exécuteur unique, et n'est dans `tools` que si le catalogue n'est pas vide. Sa réponse est le corps du skill : un segment `skill_body` (brique `skills`, composant `skills.{id}`), jamais compressible. Aux tours suivants, l'historique garde à sa place le talon « Skill « X » chargé. » (`history`), et le corps entre dans le message système, après le catalogue, en `skill_body`. Rien n'est ajouté au message système pendant le tour.
- AD-23 : le méta-outil n'écrit aucun état ; il renvoie l'effet `SkillLoaded{skill_id}`, que la session applique.
- Recharger un skill déjà chargé renvoie « Le skill « X » est déjà chargé. » en `tool_result`. Un nom inconnu ou d'un skill désactivé est une erreur réinjectée qui liste les skills chargeables.
- Sous-options : un interrupteur par skill, tous activés à l'activation de la brique ; intention de classe (a), avec « Prend effet au prochain tour ». Un skill chargé puis désactivé sort du contexte et y revient s'il est réactivé. « Vider la conversation » décharge tous les skills.
- La brique demande la capacité `tool_call_parser` (AD-6), ne dépend d'aucune autre brique, catégorie `context`, hébergement local.
- Caveman : version française simplifiée, un seul niveau : réponses télégraphiques sans formules de politesse, remplissage ni précautions oratoires, en gardant chiffres, termes techniques, noms propres et code exacts. Attribution au skill Caveman original (licence MIT) dans un fichier voisin non chargé en contexte ; jamais le proxy BSL-1.1 (NFR-10).
- Schéma : un nœud `skill` par skill activé, local, relié au harnais ; son infobulle donne la description et l'état « chargé » / « non chargé », comme un serveur MCP liste ses outils (FR-3).
- Un skill qui s'appuie sur des outils les nomme dans sa description et son corps ; le harnais ne l'impose pas. Si l'outil est éteint, l'appel échoue comme tout appel refusé, et l'échec est visible.
- UX : étape « Chargement du skill » dans Orchestration, avec le badge « Skill » et le badge « Déclenché par le modèle » (`trigger-badge-model`), qui s'ajoute aussi à « Chargement de la documentation ». Les tokens de sortie de chaque appel restent affichés : c'est la comparaison de FR-25.

**Décisions (2026-09-24) :**
- Quatre skills simples, dans cet ordre : `caveman` (Caveman), `meeting_minutes` (« Compte rendu de réunion » : décisions, actions, responsables ; propose `read_file` sur `notes_reunion.txt`), `pirate` (« Pirate » : parler de pirate, contenu intact), `explain_like_ten` (« Explication pour un enfant de 10 ans » : reformulation simple avec une analogie). Les ids suivent la convention anglaise `snake_case` ; les libellés et contenus sont en français.
- Deux skills outillés s'y ajoutent, en fin de liste : `budget_review` (« Point budget » : `read_file` sur `confidentiel/budget_projet.txt`, puis `calculator` pour le total et la part de chaque poste, rendu en tableau ; hors ligne, il servira de cible au hook H1 en story 8) et `working_days` (« Jours ouvrés » : `get_datetime`, puis `public_holidays` pour l'année, puis `calculator` pour compter les jours ouvrés d'une période ; `public_holidays` est un outil réseau, désactivé par défaut). Chaque corps décrit les étapes dans l'ordre et les outils à activer.

**Never:** pas d'action forcée « Déclencher le skill » ni de rejeu (story 9) ; pas de ressources annexes chargées par un skill (un skill = un fichier) ; pas de niveaux lite/ultra pour Caveman ; pas d'autre effet que `SkillLoaded` ajouté à `effects.py` ; pas de modification du message système pendant un tour ; le front ne calcule aucun état (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Activation | Brique « Skills » cochée | Aperçu : une ligne `skill_catalog` par skill dans le message système, `load_skill` dans `tools` ; carte « Skills : N activés sur N » ; un nœud `skill` par skill | N/A |
| Sans prompt système | Brique « Prompt système » éteinte | Message système fait des seuls segments des skills | N/A |
| Chargement | Le modèle appelle `load_skill(skill="caveman")` | Étape « Chargement du skill » avec badges ; réponse `skill_body` (composant `skills.caveman`) ; l'appel suivant du tour répond en style télégraphique | Nom inconnu : erreur réinjectée listant les skills chargeables |
| Tour suivant | Nouveau message | Corps de Caveman dans le message système en `skill_body`, sa ligne retirée du catalogue, talon `history` à la place de la réponse ; nœud « chargé » | N/A |
| Déjà chargé | `load_skill` sur un skill chargé | « Le skill « X » est déjà chargé. », en `tool_result` | N/A |
| Tout chargé | Tous les skills activés chargés | Plus de catalogue ni de `load_skill` ; tous les corps dans le message système, dans l'ordre du registre | N/A |
| Désactivé | Caveman chargé puis décoché | Corps et ligne absents au tour suivant ; revient s'il est recoché | N/A |
| Vider | « Vider la conversation » | Plus aucun skill chargé ; catalogue complet ; aperçu et schéma mis à jour | N/A |
| Contenu invalide | `SKILL.md` sans `description` | Brique indisponible avec la raison ; le reste fonctionne | `harness_error` tracé |
| Brique éteinte | Brique cochée puis décochée | Rendu octet pour octet identique au LLM nu | N/A |

</frozen-after-approval>

## Code Map

- `content/skills/{id}/SKILL.md` (nouveaux, un par skill décidé), `content/skills/caveman/NOTICE.md` (attribution et texte MIT du dépôt JuliusBrussee/caveman, récupéré verbatim si le réseau le permet). `content/skills.yaml` (nouveau, sur le modèle de `content/mcp.yaml`) : `catalog_intro`, et `load_skill: {label_fr: "Chargement du skill", description, skill}`. `content/bricks/skills.yaml` : carte (`category_fr: context engineering`), explication : skill face à outil, MCP et prompt système, chargement progressif, comparaison des tokens de sortie avec et sans Caveman.
- `src/wavestack/skills.py` (nouveau, sur le modèle de `mcp/servers.py` L41-80) : `SkillText{name, label_fr, description, body}`, `SkillsContent`, `load_skills_content(ids)` qui lit `skills.yaml` et le `SKILL.md` de chaque id (en-tête entre `---`, `yaml.safe_load`). Lève sur un fichier absent ou invalide.
- `src/wavestack/bricks/registry.py` : brique `skills` (category `context`, `capabilities=["tool_call_parser"]`), un `Component(id="skills.{id}", kind="skill", hosting="local_file", edges_to=["core.harness"])` par skill.
- `src/wavestack/session/effects.py` : `SkillLoaded{kind: "skill_loaded", skill_id}` ; `Effect = ToolDocLoaded | SkillLoaded` (discriminé par `kind`).
- `src/wavestack/trace/catalog.py` : `ArchitectureNode.kind` reçoit `"skill"`, plus `loaded: bool | None` et `detail_fr: str | None`. `tests/test_trace_architecture.py` L70 prend `"skill"` comme type inconnu : prendre un autre type.
- `src/wavestack/session/app_session.py` :
  - `_load_content` (L550) : charge `SkillsContent` quand `skills` est déclarée ; échec → `_content_errors["skills"]`.
  - État : `_skills_enabled: set[str]` (tous au départ), `_loaded_skills: set[str]` (conversation, AD-17). `_sent` (L250, L875) reçoit les skills activés ; `_pending_ids` (L360) marque `skills` quand ils changent. `_emit_bricks` (L417) : options de `skills` sur le modèle de `_mcp_options`. `_drawn_components` (L270) : seulement les skills activés. `_emit_architecture` : un nœud `skill` reçoit `loaded` et `detail_fr`.
  - `TurnState` (L169) : `skills: tuple[str, ...]` (chargés et activés, dans l'ordre du registre) et `skill_catalog: tuple[str, ...]` (activés non chargés). `build_turn_state` (L643) les remplit si `skills` est effective, et ajoute `load_skill` à `tools` si `skill_catalog` n'est pas vide.
  - `_messages` (L727) devient une méthode d'instance ou reçoit les textes : le message système reçoit, après le prompt système, l'introduction et une `Part(SKILL_CATALOG, …, "skills", "skills.{id}")` par ligne, puis une `Part(SKILL_BODY, body, "skills", "skills.{id}")` par skill chargé. L'introduction : `Part(SKILL_CATALOG, intro, "skills", "core.harness")`.
  - `_harness_tools` (L937) : ajoute `load_skill` (`brick="skills"`, `label_fr`), sur le modèle de `load_tool_doc` ; `_load_skill(skill)` sur le modèle de `_load_tool_doc` (L961) renvoie `ToolReply(body, (SkillLoaded(skill_id=skill),))`.
  - `_turn` (L1314) : dispatch des effets par type ; `_apply_skill_loaded` sur le modèle de `_apply_doc_loaded` (L1327) : `kind: SKILL_BODY`, `brick: "skills"`, `component: "skills.{id}"`, `stub`, puis `_emit_architecture`. `harness_brick` (L1249) : première brique effective parmi `tools`, `mcp`, `skills`.
  - `set_skill(skill_id, enabled)` sur le modèle de `set_tool` (L908). `clear_conversation` (L1157) vide `_loaded_skills` et réémet le schéma.
- `src/wavestack/web/app.py` (L196-218) : `POST /api/intentions/skill {skill, enabled}`, 404 si inconnu.
- `src/wavestack/web/static/app.js` : `brickOptions` (L418) : nom « Skills » ; `setOption` (L468) : `/api/intentions/skill`. `BRICK_ICONS` (L1051) : `skills`. `toolCard` (L829) : badge « Skill » quand `step.brick === "skills"`, badge « Déclenché par le modèle » pour toute source `harness`. `renderSchema` (L1234) : infobulle et état d'un nœud `skill` (`detail_fr`, « chargé »).
- `tests/test_skills.py` (nouveau) : `FakeEngine` à sorties scriptées, `QWEN`, `call`, `_segments` de `tests/test_tools.py`, `_run` de `tests/test_turn.py`, et les aides `preview`/`exact` de `tests/test_mcp_lazy.py` (L36-43).

## Tasks & Acceptance

**Execution:**
- [x] `content/skills/**`, `content/skills.yaml`, `content/bricks/skills.yaml` -- les skills décidés, textes du méta-outil, carte -- AD-19, FR-23, FR-25
- [x] `src/wavestack/skills.py`, `bricks/registry.py`, `session/effects.py`, `trace/catalog.py` -- chargeur, brique, `SkillLoaded`, nœud `skill` -- AD-12, AD-23
- [x] `src/wavestack/session/app_session.py` -- état, `TurnState`, message système, `load_skill`, effet, sous-options, déchargement -- AD-4, AD-17, AD-25
- [x] `src/wavestack/web/app.py`, `static/app.js` -- intention `skill`, carte, badges, nœud -- AD-1, AD-18
- [x] `tests/test_skills.py` -- les 10 lignes de la matrice, avec pour chaque rendu une somme des tokens égale au total et aucun `harness_error` d'attribution

**Acceptance Criteria:**
- Given la brique activée, when Caveman est chargé au tour 1, then la jauge du tour 2 montre plus de tokens `skill_body` et une ligne `skill_catalog` de moins, écart visible au survol.
- Given la même question posée avec et sans Caveman chargé, when on compare les étapes de réponse dans Orchestration, then chacune affiche ses tokens de sortie.
- Given la brique activée, when on ouvre Contexte LLM, then catalogue et corps sont colorés comme descriptions d'outils et de skills, et attribués à la brique Skills.

## Implementation Notes

- Le catalogue est un `Joined` (introduction puis une ligne par skill, séparées par `\n`) placé dans le contenu du message système ; `render_context` accepte désormais un `Joined` dans le contenu d'un message (un mot changé : `prepare` au lieu de `add`). Avec le gabarit Qwen3.5, le bloc `tools` précède le contenu du message système : le catalogue reste bien après le prompt système.
- Les skills sont tous activés au démarrage de la session, comme les outils hors ligne ; décocher puis recocher la brique garde les choix, comme pour les outils et les serveurs MCP.
- Le talon d'historique nomme le skill par son libellé (« Skill « Caveman » chargé. ») ; « déjà chargé » et l'erreur de nom inconnu utilisent l'id, celui que le modèle a écrit.
- `SKILLS` (ordre du registre) vit dans `bricks/registry.py` ; `load_skills_content` lit un `SKILL.md` par composant déclaré.
- Nœud `skill` : état « chargé » / « non chargé » sous le libellé et dans l'infobulle, avec la description ; classe `is-loaded` (bordure violet foncé).

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 29 constats) :

- [VG1] Un appel refusé ou mal formé avec la seule brique Skills n'a aucun test d'attribution. Pré-vérifié. -> P1 `patch`.
- [EC6/BH13/VG-autre] Un `load_skill` refusé par `check()` (argument manquant) est attribué à `tools` ou `mcp` quand ces briques sont actives : l'ordre fixe de `harness_brick` ignore l'outil nommé. `low`, confirmé (`spec` vaut None dès que `check` échoue, L1285). Correction directe : prendre la brique de l'outil nommé s'il existe. -> P1 `patch`.
- [BH1] `test_skill_intention_http` : la dernière assertion ne peut pas échouer (les options ne portent que des ids de skill). `low`, confirmé. -> P2 `patch`.
- [BH2] Les deux `ValueError` de `skills.py` (en-tête absent, `name` différent de l'id) n'ont aucun test. `low`, confirmé. -> P3 `patch`.
- [BH3] Les corps chargés se suivent sans nom dans le message système : ni le modèle ni la salle ne savent quel texte vient de quel skill. `low`, confirmé (`_system_parts`, un `Part` nu par corps). -> P4 `patch`.
- [BH4] `budget_review` dépasse la borne de 6 appels : `load_skill`, `read_file`, total, trois pourcentages, réponse = 7. `medium`, confirmé (`tools.max_calls = 6`, `wavestack.toml` L34) : le tour finit en `limit` avant le tableau. -> P5 `patch`.
- [BH5a] `working_days` n'appelle `public_holidays` que pour une année : une période à cheval sur deux années perd des fériés. `low`, confirmé ; correction de contenu. -> P6 `patch`.
- [BH5b] `working_days` fait compter les jours de semaine par le modèle. `low`, rejeté : aucun outil ne compte les jours d'un calendrier, et la qualité des réponses passe après la pédagogie (CLAUDE.md).
- [BH6] `meeting_minutes` se contredit (« exactement trois rubriques », puis « Présents » ; « Commence par » en étape 3). `low`, confirmé. -> P7 `patch`.
- [BH7] Les descriptions de `meeting_minutes`, `budget_review` et `working_days` ne disent pas quand charger le skill, alors que le modèle ne lit qu'elles pour décider. `medium`, confirmé. -> P8 `patch`.
- [BH8] `pirate` impose deux formules en plus puis « pas plus de phrases que la réponse normale ». `low`, confirmé. -> P9 `patch`.
- [BH10] L'explication de la brique ne dit pas qu'un skill chargé est payé à chaque tour ni comment retrouver l'état « sans ». `low`, confirmé ; une phrase. -> P10 `patch`.
- [BH11] `NOTICE.md` ne date pas la récupération du texte de licence. `low`, confirmé. -> P11 `patch`.
- [BH14] Badge « 🤖 Déclenché par le modèle » : DESIGN.md demande une icône puce, et l'emoji est lu par les lecteurs d'écran. `low`, confirmé (DESIGN.md L552). -> P12 `patch`.
- [VG2] L'exigence `tool_call_parser` de la brique n'est vérifiée par aucun test sur la vraie déclaration. Pré-vérifié ; même écart pour `tools` et `mcp`, mécanisme testé de façon générique. -> `defer`.
- [VG3] Le basculement d'un skill dans le front n'a aucun test automatique. Pré-vérifié ; le dépôt n'a aucun banc de test JS (même écart qu'en 5b, 6, 6b). -> `defer`.
- [EC1] `_load_skill` lit l'état courant des skills, pas le `TurnState` : une bascule en plein tour prend effet dans le tour. `low`, rejeté : même choix qu'en 6b (BH3), la bascule en plein tour est rare et la correction passe l'état du tour au méta-outil.
- [EC2] Un skill chargé l'est dès l'effet, même si le tour s'arrête ensuite. `low`, rejeté : même choix qu'en 6b (EC3), visible dans la jauge au tour suivant.
- [EC3/EC8/BH9] Skill désactivé : le talon « Skill « X » chargé. » reste dans l'historique. `low`, rejeté : le talon relate un événement passé et vrai ; la matrice ne parle que du corps et de la ligne du catalogue, tous deux absents (testé). Le masquer demande un rendu conditionnel de l'historique.
- [EC4] Un nom passé avec une majuscule ou des espaces est refusé. `low`, rejeté : l'erreur réinjectée liste les noms exacts, comme `load_tool_doc`.
- [EC5] Une description multiligne ou très longue casserait le catalogue. `low`, rejeté : les descriptions sont des contenus du dépôt, toutes sur une ligne.
- [EC7] `_apply_skill_loaded` diffère de `_apply_doc_loaded` (pas de `loaded_in_turn`, émet le schéma). `false` : un skill n'a pas d'appel à rendre possible dans le tour, et le nœud doit passer à « chargé ».
- [BH12] `_sent` est un tuple positionnel de 6 éléments. `low`, rejeté : risque seulement pour le développeur, et la correction est un remaniement.

Groupes routés en `patch` : P1 à P12 ; `defer` : VG2, VG3 ; aucun `intent_gap` ni `bad_spec`, pas de retour en arrière.

## Design Notes

Le préfixe (contrôle d'ajout seul, AD-4) impose le même partage qu'en 6b : le message système se rend avant tout, y ajouter le corps en plein tour ferait relire tout le contexte (`prefix_not_reused`). Le corps entre donc en réponse d'outil pendant le tour, et dans le message système au tour suivant. Différence avec 6b : le catalogue des skills vit dans le message système (`skill_catalog`, emplacement stable d'AD-4), pas dans la description du méta-outil ; `load_skill` garde une description courte et fixe.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks (if no CLI):**
- `uv run wavestack` : activer « Outils » et « Skills » ; poser une question, noter les tokens de sortie ; vider, demander « Réponds en mode caveman : … » ; suivre le chargement dans Orchestration, comparer les tokens de sortie ; vérifier le nœud « chargé » dans le schéma.
