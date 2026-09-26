---
title: 'Mémoire globale'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_revision: '505ee9ffb4a2a7572e3d032c554f91bf1b327df5'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
warnings: [oversized]
deferred: []
---

<intent-contract>

## Intent

**Problem:** Rien ne survit d'une conversation à l'autre : le formateur ne peut pas montrer qu'un harnais retient des informations, les réinjecte, et que ce « souvenir » n'est qu'un fichier local que le modèle écrit par un outil (CAP-13, FR-12, CAP-8, CAP-41).

**Approach:** Brique `global_memory` (context engineering) : les entrées de `memory.json` (dossier de données) sont lues au début du tour, figées dans le `TurnState` et rendues en segments `global_memory` dans le message système. Le modèle écrit par le méta-outil `remember` ; l'utilisateur force « Écrire en mémoire » (actions armées de la story 9), consulte, modifie et efface dans un tiroir d'édition. Toute écriture est un effet `MemoryWrite` appliqué par la session seule. La réinitialisation restaure la mémoire de démonstration de `content/`.

## Boundaries & Constraints

**Always:**
- Format de `memory.json` (AD-20) : liste `{id, text, created_at, source: model|user|demo}`, chemin résolu par `config.memory_path()` seul, écrit de façon atomique (fichier temporaire puis `os.replace`) par la session seule.
- AD-23 : `MemoryWrite{op: add|replace|delete, entry_id, text}` rejoint l'union `Effect`. Un seul applicateur de session applique une liste d'effets dans l'ordre sur une copie, écrit le fichier une fois, puis émet un `effect_applied{effect: memory_write, op, entry_id, text}` par effet (portée `brick = global_memory`, `component = file.memory`) et un `memory_changed`. Échec d'écriture : `harness_error` en français, mémoire inchangée. `source` : `model` ou `user` selon le `trigger` de la portée pour `remember`, `user` pour le tiroir, `demo` pour la restauration.
- AD-4, AD-17 : `TurnState` porte les textes de la mémoire lus par `build_turn_state` (envoi, rejeu, aperçu) ; brique effective et mémoire non vide → un `Joined` dans le message système après `system_prompt` et avant `skill_catalog` : une introduction (lue par le modèle, dans `content/`) puis une ligne `- {texte}` par entrée, segments `global_memory`, brique `global_memory`, composant `file.memory`. Une écriture pendant le tour n'entre pas dans le message système de ce tour ; seule la réponse d'outil la montre. Le rejeu lit la mémoire courante.
- AD-25 : `remember(text)` (source `harness`, brique `global_memory`, composant `core.harness`) ajoute une entrée ; sa réponse est un `tool_result` de la brique `global_memory`, sans talon. Offert dans `tools` seulement si la brique est effective et le modèle a un `tool_call_parser`. Refus réinjectés (`ToolError`) : texte vide après `strip`, plus de 300 caractères, mémoire pleine (20 entrées). Texte déjà présent (comparaison sans casse ni blancs de bord) : réponse « déjà en mémoire », aucun effet.
- Forcé (AD-3, story 9) : `arm(kind="memory", target="remember", args={"text"})`, texte validé à l'armement (422 sinon) ; consommé par `remember` via `_consume_armed`, `trigger = user`. Abandonné (`action_dropped`) si la brique n'est pas effective ou si `remember` n'est pas dans `state.tools` (modèle sans parseur).
- La brique n'exige aucune capacité : sans parseur, elle reste disponible (injection et tiroir), sa carte l'explique par un `note_fr`.
- Tiroir, intention de classe (b) `POST /api/intentions/memory {op: replace|delete|clear, entry_id?, text?}` : 409 hors `idle` ou mémoire illisible, 404 entrée inconnue, 422 texte invalide (mêmes règles que `remember`) ; `clear` = un `delete` par entrée. Puis `context_preview`.
- `memory.json` absent au lancement : mémoire de démonstration en mémoire vive, fichier non écrit. Illisible ou invalide : `harness_error`, brique indisponible avec la raison, fichier jamais réécrit hors réinitialisation.
- Réinitialisation (CAP-41) : un `delete` par entrée puis un `add` par entrée de démonstration (ids `demo1`…), `source = demo`, par le même applicateur ; une mémoire illisible redevient disponible si l'écriture réussit. Lancer un scénario, « Vider la conversation » et le rejeu ne touchent pas la mémoire.
- Schéma : composant `global_memory.memory` (`kind: memory`, arêtes vers `core.harness` et `file.memory`) ; nœud `file.memory` avec le chemin en `detail_fr` ; un clic dessus ouvre le tiroir.
- Front (AD-1) : `memory_changed{entries, path}` projeté, repris par `/api/state` ; étape `remember` d'Orchestration avec badge de déclenchement et l'entrée écrite ; puce « Armé : Écrire en mémoire… ». Textes d'EXPERIENCE.md (mémoire vide, modification non enregistrée), `edit-drawer` de DESIGN.md, contrôles au clavier avec nom accessible.
- Scénario `global_memory` dans `content/scenarios.yaml`, module 1 après `system_prompt` (ordre de FR-38) : briques `short_memory`, `system_prompt`, `global_memory` ; un prompt qui demande de retenir une préférence, puis un prompt qui s'en sert ; la consigne dit de forcer « Écrire en mémoire » si le modèle n'écrit pas, de vider la conversation avant le second prompt et d'ouvrir le tiroir. Mémoire de démonstration : 2 ou 3 entrées fictives et non confidentielles (NFR-11).

**Never:** nouvelle dépendance ; nouveau `SegmentKind` ; ajout d'entrée depuis le tiroir (l'utilisateur écrit par l'action forcée) ; écriture de `memory.json` par un autre module que la session ; disponibilité par mode `forced` sans parseur ni rendu en injection (reportés depuis la story 9) ; propager `global_memory` aux premiers scénarios des modules suivants (story 21) ; raisonnement, RAG, sous-agent.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu | Erreur |
|---|---|---|---|
| Injection | brique active, 3 entrées démo | 1er appel : segments `global_memory` entre `system_prompt` et `skill_catalog`, somme = total ; aperçu idem | — |
| Écriture par le modèle | le modèle appelle `remember` | `tool_started`/`tool_ended` `trigger = model`, fichier écrit, `effect_applied` puis `memory_changed` ; entrée absente du système de ce tour, présente au tour suivant | — |
| Écriture forcée | « Écrire en mémoire » armé | avant l'appel c1, `trigger = user`, `source = user` | — |
| Refus de `remember` | texte vide, > 300 caractères, mémoire pleine | erreur française réinjectée, aucun effet | `ToolError` |
| Doublon | texte déjà présent | « déjà en mémoire », aucun effet | — |
| Sans parseur | modèle sans `tool_call_parser` | injection et tiroir actifs, `remember` absent de `tools`, `note_fr` ; forcé → `action_dropped` | — |
| Tiroir | replace, delete, clear en `idle` | fichier, `effect_applied`, `memory_changed`, aperçu | 409 / 404 / 422 |
| Échec d'écriture | dossier en lecture seule | `harness_error`, mémoire inchangée ; pour `remember`, la réponse réinjectée devient l'erreur | pas de plantage |
| Fichier invalide | `memory.json` non JSON | `harness_error`, brique indisponible avec raison, fichier intact | — |
| Réinitialisation | entrées modifiées ou fichier invalide | mémoire = démonstration, écrite ; brique disponible | — |
| Rejeu | t1 a écrit une entrée | le tour rejoué voit l'entrée dans le message système | — |

</intent-contract>

## Code Map

- `src/wavestack/config.py:450` -- ajouter `memory_path()` à côté d'`audit_path()` ; écriture atomique sur le modèle de `write_api_key` (437-446).
- `src/wavestack/memory.py` (nouveau) -- sur le modèle de `skills.py`/`scenarios.py` : `MemoryEntry`, `MemoryContent` (texte du nœud, introduction, textes de `remember`, entrées de démonstration), `load_memory_content()`, `read_memory(path)` (lève sur fichier invalide), `write_memory(path, entries)`, constantes 20 entrées / 300 caractères.
- `content/memory/memory.yaml`, `content/bricks/global_memory.yaml` (nouveaux) -- textes en français ; modèle : `content/skills.yaml` (bloc `load_skill`), `content/bricks/system_prompt.yaml`.
- `src/wavestack/bricks/registry.py:31` -- `BrickDeclaration(id="global_memory", category="context", ...)` juste après `system_prompt` (ordre du panneau = FR-38) ; `file.memory` est déjà réservé (9-19).
- `src/wavestack/session/effects.py:66` -- `MemoryWrite` dans l'union `Effect`.
- `src/wavestack/session/app_session.py` :
  - `TurnState` 252-268 : champ `memory` ; `build_turn_state` 1068-1106 : textes + `REMEMBER` dans `tools` (après `load_skill`) si brique effective et `self._caps.tool_call_parser`.
  - `_system_parts` 1183-1215 : `Joined` mémoire entre prompt système et catalogue de skills (modèle : le catalogue 1199-1210).
  - `_load_content` 943-1023 : contenu mémoire + lecture de `memory.json` → `_content_errors["global_memory"]` ; `__init__` 315-417 : état `_memory`, émission initiale de `memory_changed` (comme `_load_scenarios` 1912).
  - `_harness_tools` 1628-1654 : `ToolSpec` de `remember` (modèle `load_skill` 1636-1653) ; `_remember` sur le modèle de `_load_skill` 1692-1705 (lit, n'écrit rien, renvoie `ToolReply`).
  - `_apply_effects` 2283-2293 : cas `MemoryWrite` → applicateur unique (source depuis `current().trigger`), échec → `content` remplacé par l'erreur.
  - `arm` 1537-1582 (branche `memory`), `_armed_call` 2375-2381, `_armed_unavailable` 2383-2418.
  - `_turn` 2141-2143 : ajouter `global_memory` au repli `harness_brick`.
  - `_emit_architecture` 547-574 : entrée `file.memory` dans `files` ; `_emit_bricks` 732-782 : `note_fr` de la carte.
  - `reset` 1962-1964 / `_reconfigure` 1966-1992 : restauration après l'émission de `harness_reset`, `launch_scenario` inchangé ; nouvelles méthodes `edit_memory(op, entry_id, text)` (classe b, `SendRefused` / `KeyError` / `ValueError`).
- `src/wavestack/trace/catalog.py` -- `MemoryEntryState`, `MemoryChangedPayload` ; `EffectAppliedPayload` 360-367 (`memory_write`, `op`, `entry_id`, `text`) ; `ArmedActionState.kind` 400 (`memory`) ; `BrickState.note_fr` 256-273 ; `PAYLOAD_MODELS` 446-481.
- `src/wavestack/web/app.py` -- `ArmIntention.kind` 95 ; `MemoryIntention` + `POST /api/intentions/memory` sur le modèle de `clear_conversation` 414-421 et `scenario` 423-432 ; `/api/state` 186-223 : `memory_changed`.
- `src/wavestack/web/static/index.html:46-59` -- second `aside.edit-drawer#memory-drawer` (liste, alerte, « Tout effacer », « Fermer », choix enregistrer/abandonner).
- `src/wavestack/web/static/app.js` -- `applyEnvelope` 146 : `memory_changed` → `store.memory` ; `effect_applied` 320-324 : aiguiller sur `p.effect` (`memory_write` → dernière étape d'outil `remember` du tour) ; `renderBricks` 491-603 : « Modifier la mémoire » (modèle 590-598) et force « Écrire en mémoire » au niveau de la carte (formulaire à un champ, `FORCE_LABELS` 665, `armAction` 861) ; tiroir sur le modèle de `openDrawer`/`closeDrawer` 972-1015 (`Échap` 3571) ; `turnRows` 2016-2030 : icône 💾 pour `remember` ; `BRICK_ICONS` 3017 ; `schemaNode` 3358 : clic sur `file.memory` ; `KIND_LABELS` 2787 et `eventSummary` 2832 ; boot : `/api/state.memory_changed`.
- `src/wavestack/web/static/app.css` -- styles des entrées du tiroir sur `.edit-drawer`, jetons de DESIGN.md (`segment-global-memory`, `GROUP_COLORS` 76-78 déjà prêt).
- `content/scenarios.yaml:8-11` -- scénario `global_memory` dans le module 1 (60 min).
- Tests : `tests/fake_engine.py` (`booted_session`), `tests/test_skills.py` (`skills_session`, `since`, `nodes`, `card`), `tests/test_tools.py` (`QWEN`, `call`, `_segments`), `tests/test_forced.py`, `tests/test_bricks.py` (`_client`, `HEADERS`), `tests/test_scenarios.py:35` (11 → 12 scénarios). `conftest.py` isole le dossier de données par test.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/config.py`, `src/wavestack/memory.py`, `content/memory/memory.yaml`, `content/bricks/global_memory.yaml` -- chemin, modèles, lecture/écriture atomique, contenus -- AD-19, AD-20.
- [x] `src/wavestack/session/effects.py`, `src/wavestack/trace/catalog.py`, `src/wavestack/bricks/registry.py` -- contrat d'abord : effet, événements, brique -- AD-2, AD-12, AD-23.
- [x] `src/wavestack/session/app_session.py` -- état et chargement, `TurnState`, rendu, `remember`, applicateur, forçage, tiroir, réinitialisation, schéma, carte -- AD-3, AD-4, AD-17, AD-25.
- [x] `src/wavestack/web/app.py` -- route `memory`, `kind: memory`, `/api/state` -- AD-18.
- [x] `src/wavestack/web/static/index.html`, `app.js`, `app.css` -- tiroir, carte, forçage, étape, schéma, journal -- EXPERIENCE.
- [x] `content/scenarios.yaml`, `tests/test_scenarios.py` -- scénario `global_memory`, décompte mis à jour -- FR-38.
- [x] `tests/test_global_memory.py` (nouveau) -- une ligne de la matrice par test, avec `remember` et le forçage sur `QWEN` ; routes 200/404/409/422 ; rendu local et chat (`_system_parts` partagé) ; clé `source` et `effect_applied.component = file.memory`.

**Acceptance Criteria:**
- Given la brique active et une entrée écrite, when WaveStack est relancé (nouvelle `AppSession` sur le même dossier), then l'entrée est dans le tiroir et dans le message système du premier tour.
- Given une page rechargée, when la mémoire a changé, then le tiroir et la carte reflètent le dernier `memory_changed` (AD-1).
- Given une écriture par le modèle ou forcée, when on ouvre son étape dans Orchestration, then elle porte « Déclenché par le modèle » ou « Forcé par l'utilisateur » et le texte écrit.
- Given le tiroir ouvert avec une entrée modifiée non enregistrée, when on ferme par `Échap`, then « Modification non enregistrée. Enregistrer ou abandonner ? » s'affiche.
- Given la mémoire vide, when on ouvre le tiroir, then « Aucune information en mémoire globale. Le modèle peut en écrire, ou vous pouvez forcer une écriture. » s'affiche.
- Given la brique voulue, when on regarde le schéma, then le nœud « Mémoire globale » est dans le bac Fichiers de la zone Poste de travail, relié au harnais.

## Spec Change Log

## Review Triage Log

### 2026-09-26 — Review pass
Passe unique faite par l'agent d'implémentation (pas d'outil de sous-agent dans cette exécution) ; une revue indépendante suivra.
- verdicts: 5 findings — high 0, medium 0, low 3, false 1, maybe-false 1
- findings:
  - `[low]` `[patch]` Les messages de `check_text` tutoyaient le modèle (« écris… », « Résume-le… ») alors qu'ils reviennent aussi à l'utilisateur en 422 (tiroir, armement) — messages rendus neutres (`src/wavestack/memory.py`).
  - `[low]` `[patch]` Aucun test ne couvrait l'abandon d'une écriture forcée quand la brique est éteinte (ligne « Forcé » de la spec) — ajout de `test_forced_write_is_dropped_when_the_brick_is_off`.
  - `[low]` `[reject]` Deux intentions (b) concurrentes (réinitialisation et suppression depuis deux onglets) pourraient faire lever `KeyError` dans `apply_writes` et un 500 sur la réinitialisation — improbable en démonstration, la correction ajouterait une garde ; la suppression concurrente, elle, finit déjà en 404.
  - `[false]` Un `memory_changed` rejoué au chargement de la page pourrait écraser le tiroir ouvert — faux : `renderMemoryDrawer` ne fait rien tant que le tiroir est caché, et garde les brouillons (`store.memoryDrafts`) quand il est ouvert.
  - `[maybe-false]` `[reject]` Un échec d'`os.replace` laisse `memory.tmp` dans le dossier de données — sans effet sur la lecture (seul `memory.json` est lu) ; à vérifier seulement si un antivirus Windows verrouille le fichier ; au pire `low`.

## Design Notes

L'applicateur unique prend une liste pour que « Tout effacer » et la restauration n'écrivent le fichier qu'une fois, tout en gardant un `effect_applied` par effet (AD-23). Esquisse :

```python
def _apply_memory(self, writes: list[MemoryWrite], source: str) -> str | None:
    entries = apply_writes(list(self._memory), writes, source, now())  # pure, in memory.py
    try:
        memory.write_memory(config.memory_path(), entries)
    except OSError as exc:
        self._error("La mémoire globale n'a pas pu être écrite.", exc, "Elle reste inchangée.")
        return "Erreur : la mémoire globale n'a pas pu être écrite."
    ...  # self._memory = entries; one effect_applied per write; memory_changed
```

`replace` garde `id` et `created_at`, passe `source` à `user`.

## Hypothèses à valider

- H1 : le tiroir n'ajoute pas d'entrée ; l'utilisateur écrit par « Écrire en mémoire » (cycle complet du harnais, badge « Forcé par l'utilisateur »). EXPERIENCE.md ne liste que consulter, modifier, supprimer, tout effacer.
- H2 : `remember` n'ajoute qu'une entrée ; le modèle ne modifie ni ne supprime (ops `replace`/`delete` réservées au tiroir et à la restauration).
- H3 : bornes de 20 entrées et 300 caractères, constantes du code, pour tenir la fenêtre de 4 096 tokens.
- H4 : sans parseur, la brique reste disponible (injection et tiroir) ; le forçage est abandonné plutôt que rendu en injection, la disponibilité par mode étant reportée depuis la story 9.
- H5 : `memory.json` absent → démonstration en mémoire vive, sans écriture ; invalide → brique indisponible, fichier protégé jusqu'à une réinitialisation, qui l'écrase.
- H6 : la réinitialisation passe par des `MemoryWrite` (`delete` puis `add`, `source = demo`) pour garder un seul chemin d'écriture (AD-23).
- H7 : « Tout effacer » sans confirmation, comme la réinitialisation ; la démonstration se restaure par « Réinitialiser ».
- H8 : pas de marque « Prend effet au prochain tour » pour un changement de contenu de la mémoire (comme un skill chargé) ; seul l'interrupteur la déclenche.
- H9 : le scénario `global_memory` rejoint le module 1 (durée portée à 60 min) ; les premiers scénarios des modules 2 à 4 n'activent pas encore la mémoire globale, ce cumul revenant à la story 21. La story 13 (raisonnement), rédigée en parallèle, touche le même module : fusion à surveiller.
- H10 : doublon détecté sans casse ni blancs de bord ; l'id d'une nouvelle entrée est `m` + 8 caractères hexadécimaux aléatoires.
- H11 (implémentation, remplace la première moitié de H9) : la story 13 a été fusionnée avant l'implémentation, et sa revue a rendu les scénarios cumulatifs (le premier scénario d'un module active les briques des modules précédents, en-tête de `content/scenarios.yaml`, CAP-40). Placer `global_memory` dans le module 1 aurait obligé à l'ajouter aux premiers scénarios des modules 2 à 5, ce que la section Never interdit (report à la story 21). Le scénario ouvre donc, comme `reasoning`, son propre module « Mémoire globale » (30 min) en fin de programme, avec les briques de tous les modules précédents (MCP en lazy loading) ; le module 1 reste à 45 min. La place définitive suivra l'ordre de FR-38 à la story 21.
- H12 (implémentation) : le nœud `file.memory` s'intitule « Mémoire globale » (critère d'acceptation), le chemin de `memory.json` en info-bulle ; la puce du harnais porte aussi « Mémoire globale » (icône 💾).
- H13 (implémentation) : `memory_changed` porte aussi `error_fr` (fichier illisible), pour que le tiroir et la carte se désactivent sans recalcul côté front (AD-1).
- H14 (implémentation) : un échec d'écriture depuis le tiroir renvoie 500 avec la raison en français (en plus du `harness_error`) ; la spec ne fixait que 409, 404 et 422.
- H15 (implémentation) : les messages de refus du texte (vide, plus de 300 caractères) sont neutres, car ils vont au modèle (`remember`) comme à l'utilisateur (tiroir, armement) ; « Écrire en mémoire » s'arme depuis la carte, formulaire à un champ « Texte », et la puce se lit « Armé : Écrire en mémoire (début du texte…) ».

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucune erreur
- `uv run python -m pytest` -- expected: tout passe
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks (if no CLI):**
- `uv run wavestack` avec Qwen : lancer le scénario « Mémoire globale », faire écrire le modèle (sinon forcer), vider la conversation et vérifier que l'information revient par le message système ; modifier et effacer dans le tiroir ; réinitialiser et retrouver la démonstration ; cliquer le nœud `memory.json`.

## Auto Run Result

Status: done

**Résumé :** brique `global_memory` (catégorie context, composant `global_memory.memory`, nœud `file.memory`). `memory.json` (dossier de données, `config.memory_path()`) est lu au lancement : absent → mémoire de démonstration en mémoire vive, illisible → `harness_error` et brique indisponible jusqu'à « Réinitialiser ». Les textes sont figés dans `TurnState.memory` et rendus en segments `global_memory` entre le prompt système et le catalogue de skills (local et chat, `_system_parts` partagé). Méta-outil `remember` (offert si la brique est effective et le modèle a un parseur), refus réinjectés (vide, > 300, 20 entrées), doublon sans effet. Effet `MemoryWrite` appliqué par un applicateur unique (`_apply_memory`) : écriture atomique, un `effect_applied` par effet (`file.memory`), un `memory_changed`, échec → `harness_error` et réponse réinjectée remplacée. Action forcée `memory` (« Écrire en mémoire »), tiroir `POST /api/intentions/memory` (replace, delete, clear ; 409/404/422/500), restauration de la démonstration à la réinitialisation. Front : carte (compte, note sans parseur, forçage, « Modifier la mémoire »), tiroir d'édition au clavier, étape 💾 d'Orchestration avec badge et entrée écrite, clic sur le nœud du schéma, journal. Scénario `global_memory` dans un module « Mémoire globale » en fin de programme (H11).

**Fichiers :**
- `src/wavestack/memory.py` (nouveau) — format de `memory.json`, contenus, lecture, écriture atomique, validation, application pure des écritures.
- `content/memory/memory.yaml`, `content/bricks/global_memory.yaml` (nouveaux) — textes du harnais, de `remember`, démonstration fictive, carte.
- `src/wavestack/config.py` — `memory_path()`.
- `src/wavestack/session/effects.py` — `MemoryWrite` dans l'union `Effect`.
- `src/wavestack/bricks/registry.py` — brique `global_memory` après `system_prompt`.
- `src/wavestack/trace/catalog.py` — `memory_changed`, `effect_applied` `memory_write`, `kind: memory`, `note_fr`.
- `src/wavestack/session/app_session.py` — chargement, disponibilité, `TurnState`, rendu, `remember`, applicateur, forçage, tiroir, réinitialisation, schéma, carte.
- `src/wavestack/web/app.py` — route `memory`, `kind: memory`, `/api/state.memory_changed`.
- `src/wavestack/web/static/index.html`, `app.js`, `app.css` — tiroir, carte, forçage, étape, schéma, journal.
- `content/scenarios.yaml` — module et scénario « Mémoire globale ».
- `tests/test_global_memory.py` (nouveau, 19 tests), `tests/test_bricks.py`, `tests/test_scenarios.py` — matrice, acceptation, comptes.

**Revue :** 5 constats ; 2 corrigés (`low`), 2 rejetés (1 `low` improbable, 1 `maybe-false` au pire `low`), 1 `false`. Rien de reporté. Corrections par verdict : high 0, medium 0, low 2.

**Suivi de revue recommandé :** false (aucun correctif `high`, moins de deux `medium`). Une revue indépendante est de toute façon prévue par l'orchestrateur, cette passe ayant été faite sans sous-agent.

**Vérification :** `uv run ruff check .` (vert), `uv run ruff format --check .` (vert), `node --check src/wavestack/web/static/app.js` (vert), `uv run pytest -q` : 427 réussis, 3 sautés. Audit de la matrice : chaque ligne couverte par un test de `tests/test_global_memory.py` (injection, écriture par le modèle, forcée, trois refus, doublon, sans parseur, tiroir, échec d'écriture, fichier invalide, réinitialisation, rejeu), tous exécutés et verts.

**Risques résiduels :**
- Front non testé automatiquement (pas de tests JS dans le projet) : tiroir, forçage depuis la carte, étape d'Orchestration et clic du nœud sont à vérifier à la main.
- Qwen sur CPU peut ne pas appeler `remember` de lui-même, surtout avec toutes les briques du scénario cumulatif actives : le forçage est la voie de secours prévue.
- Scénario placé en fin de programme (H11) plutôt qu'au module 1 : à trancher à la story 21.
