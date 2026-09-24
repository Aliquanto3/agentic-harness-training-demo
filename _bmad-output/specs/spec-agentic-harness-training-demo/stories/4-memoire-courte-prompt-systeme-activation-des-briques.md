---
title: 'Mémoire courte, prompt système, activation des briques'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: 'd2f5161919e1066230529c1372a512464c62581b'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le panneau des briques est un texte d'attente et chaque tour n'envoie que le dernier message : pas d'historique, pas de prompt système, rien à activer (CAP-5, CAP-6, CAP-11, CAP-12).

**Approach:** Poser le contrat de brique (AD-12) avec deux premières briques, `short_memory` (context engineering) et `system_prompt` (prompt engineering), activables depuis des cartes qui expliquent ce qu'elles ajoutent. La session garde l'historique des tours `completed`, le fige au début du tour par `build_turn_state` (AD-17) et injecte l'historique et le prompt système selon l'état effectif `wanted ∧ available`, calculé en un seul point.

## Boundaries & Constraints

**Always:**
- AD-12 : chaque brique déclare `id`, catégorie, dépendances (`requires`), capacités exigées, `network`, `contributes_to`, composants `{id: "{brick}.{component}", kind, hosting, edges_to}`. Unicité des identifiants vérifiée au chargement. `available` + `reason_fr` calculés dans une seule méthode de la session ; état effectif `wanted ∧ available`. Toutes briques éteintes = tour identique au LLM nu (même prompt, octet pour octet).
- AD-17 : `build_turn_state(origin_turn=None)` renvoie un `TurnState` figé (historique de la branche active, prompt système, briques effectives). Seul un tour `completed` entre dans l'historique : message utilisateur, texte et raisonnement de l'assistant. L'historique est enregistré même brique éteinte ; l'activer plus tard réinjecte les tours déjà faits.
- AD-4 : historique en `history` (`brick = short_memory`), re-rendu par le gabarit à chaque appel ; prompt système en `system_prompt` dans le message système. Somme des segments = total, inchangé.
- AD-3 : basculer une brique et enregistrer le prompt système sont de classe (a), acceptés même pendant un tour, effet au tour suivant ; « Vider la conversation » est de classe (b), 409 hors `idle`. Chaque changement émet un nouveau `context_preview` (AD-9) et, pour les briques, `architecture_changed` : un composant est dessiné dès que sa brique est `wanted`.
- AD-19 : explications des briques (2-3 phrases, catégorie, hébergement) dans `content/bricks/*.yaml`, prompt système par défaut dans `content/prompts/system.md`, validés par pydantic ; fichier invalide = `harness_error`, pas de plantage.
- UX : carte de brique (nom, interrupteur, puce de catégorie, étiquette d'hébergement, explication dépliable, « Prend effet au prochain tour » tant qu'aucun tour n'a suivi le changement) ; tiroir d'édition du prompt système (Enregistrer, Rétablir le prompt par défaut, Fermer/`Échap`, alerte si modification non enregistrée) ; bouton « Vider la conversation » dans l'en-tête de la vue humain.

**Décisions (2026-09-24) :**
- Spec gardée entière malgré sa taille (~2 900 tokens) : les deux briques partagent contrat et aperçu.
- Pas de persistance : `wanted` et prompt système modifié vivent en mémoire de la session ; chaque lancement repart en LLM nu avec le prompt par défaut. Rien n'est écrit dans `settings.json`.
- Le panneau ne montre que les briques construites (ici deux) ; il grandit story après story.

**Never:**
- Pas de rejeu, d'actions armées, de méta-outils ni de disponibilité par mode (`model`/`forced`/`injection`) : stories 5 et 9. Pas de mémoire globale ni d'autre brique.
- Le front ne calcule ni disponibilité, ni état effectif, ni contexte (AD-1).
- Une brique n'importe jamais une autre brique.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| LLM nu | Deux tours, briques éteintes | 2e tour : segments `user_message` + `template` seuls | N/A |
| Mémoire courte | `short_memory` activée, 2e tour | Segments `history` du 1er tour, total qui grossit | N/A |
| Tour non terminé | 1er tour `cancelled`/`overflow`/`error`/`limit` | N'entre pas dans l'historique | N/A |
| Prompt système | Brique activée, texte modifié puis enregistré | Tour suivant : segment `system_prompt` avec le nouveau texte ; aperçu mis à jour | N/A |
| Bascule pendant un tour | `wanted` changé en état `turn` | Accepté ; le tour en cours garde son `TurnState` | N/A |
| Vider | `idle` | Historique vide, bulles effacées, briques et prompt inchangés | 409 + raison hors `idle` |
| Contenu invalide | YAML de brique ou prompt illisible | Brique indisponible avec sa raison, application utilisable | `harness_error` |

</frozen-after-approval>

## Code Map

- `src/wavestack/bricks/` (nouveau) -- `contract.py` : modèles pydantic `BrickDeclaration`, `Component`, `BrickContent` ; `registry.py` : déclarations des deux briques et vérification d'unicité des ids (composants + nœuds réservés `core.*`, `file.*`). Pas d'import entre briques.
- `src/wavestack/session/app_session.py` -- `_render(message, call_id)` (L188-212) est le seul constructeur de messages, codé en dur à un message utilisateur (L197) : le faire partir d'un `TurnState`. `_run_turn` (L263), `finally` L277-284 : ajouter le tour à l'historique si `completed`. `_call_model` (L313) ne renvoie qu'un statut : il doit aussi rendre texte et raisonnement. `_emit_preview` (L214) n'est appelé qu'au boot : l'appeler après chaque changement, via l'executor (thread unique). Nœuds fixes `_CORE_HARNESS`/`_CORE_MODEL` (L30-47) et `_emit_architecture` (L117) : dériver les nœuds et arêtes des briques `wanted`. Nouvelles méthodes : `set_brick(id, wanted)`, `save_system_prompt(text | None)`, `clear_conversation()` (lève `SendRefused` hors `idle`), `build_turn_state`, `_availability`.
- `src/wavestack/context/render.py` -- `render_context(engine, template, messages, …)` (L188) accepte déjà plusieurs messages de `list[Part]` et le rôle `system` : réutiliser tel quel.
- `src/wavestack/trace/catalog.py` -- `ArchitectureNode.kind` (L49) : ajouter `brick` ; nouveaux `kind` : `bricks_changed{bricks: [{id, label_fr, category, category_fr, hosting_fr, explanation_fr, wanted, available, reason_fr, pending}], system_prompt{text, is_default}}` et `conversation_cleared`. `Envelope` intouchée. Valider que `ArchitectureEdge.from_`/`to` visent un nœud de la liste (item différé de la story 2).
- `src/wavestack/web/app.py` -- routes POST `/api/intentions/brick` `{brick, wanted}`, `/system_prompt` `{text: str | null}` (null = défaut), `/clear_conversation` (409 via `SendRefused`, comme `/send` L128). `/api/state` (L87) : ajouter le dernier `bricks_changed` avec `_latest`.
- `src/wavestack/web/static/{index.html,app.js,app.css}` -- remplacer le texte d'attente (index.html L37-41) par les cartes ; tiroir d'édition ; bouton « Vider la conversation » (en-tête L47-53) ; `conversation_cleared` masque les bulles antérieures. Réutiliser `el()` (L243), `postIntention` (L370), `GROUP_COLORS` (L28, `system_prompt` et `history` déjà présents), jetons `--color-state-*` et `--spacing-brick-panel-width`. Styles `brick-card`, `category-chip`, `hosting-tag-local`, `edit-drawer` selon DESIGN.md.
- `content/bricks/{short_memory,system_prompt}.yaml`, `content/prompts/system.md` (nouveaux) -- chargeur calqué sur `load_labels()` (segments.py L63) et `AppSession._load_labels` (L175, `harness_error` + repli).
- `tests/fake_engine.py` -- `booted_session`, `FakeEngine.calls` ; `tests/test_turn.py` -- `_run(session, message)` (L23), client HTTP (L192-214) : à réutiliser.

## Tasks & Acceptance

**Execution:**
- [x] `trace/catalog.py` -- nœud `brick`, `bricks_changed`, `conversation_cleared`, validation des arêtes -- AD-2, AD-12
- [x] `bricks/` + `content/bricks/`, `content/prompts/` -- contrat, deux déclarations, contenus -- AD-12, AD-19
- [x] `session/app_session.py` -- disponibilité au point unique, `TurnState`, historique, intentions, aperçu, schéma -- AD-3, AD-4, AD-12, AD-17
- [x] `web/app.py` -- trois routes, `/api/state` étendu -- AD-3, AD-18
- [x] `web/static/*` -- cartes, tiroir, vider, bulles effacées -- AD-1, CAP-5/6
- [x] `tests/` -- les 7 lignes de la matrice ; LLM nu identique octet pour octet à la story 3 (`FakeEngine.calls`) ; dépendance manquante → indisponible avec raison (brique factice) ; ids de composants en double refusés ; arête vers un nœud absent refusée ; 409 de `clear_conversation`

**Acceptance Criteria:**
- Given l'application démarrée, when on regarde le panneau des briques, then chaque carte montre son explication, sa catégorie et son lieu d'hébergement, en français.
- Given la mémoire courte activée et trois tours terminés, when on regarde le compteur de tokens d'entrée, then il augmente d'un tour à l'autre.
- Given une brique activée, when on regarde le schéma d'architecture, then son composant apparaît, relié au harnais.

## Implementation Notes

- Implémenté par un sous-agent (dispatch), diff relu dans cette session. `ruff check`, `ruff format --check` : propres. `pytest` : 81 passed, 2 deselected (tests `model`).
- Audit de la matrice I/O : les 7 lignes sont couvertes par `tests/test_bricks.py` et passent (le tour annulé a son propre test). L'effacement des bulles reste à vérifier à la main (projection front de `conversation_cleared`).
- Vérification dans Chrome par le sous-agent, avec le moteur factice (pas de vrai GGUF) : tokens d'entrée 57 → 161 → 324 sur trois tours, tiroir, vider, schéma ; aucune erreur console.
- Choix de l'implémentation : prompt vide ou blanc enregistré = retour au défaut ; interrupteur d'une brique voulue mais indisponible toujours actif (pour pouvoir l'éteindre) ; carte de dépassement qui nomme l'historique comme cause et propose de vider ; 404 sur une brique inconnue ; nœuds de brique sur une seconde rangée du schéma, avec arêtes et styles réseau/indisponible (item différé de la story 2).
- `ponytail:` raisonnement passé en `reasoning_content` : compté `template` si un gabarit le garde (Qwen3.5 l'efface) ; étiquette d'hébergement toujours locale côté front jusqu'à la première brique réseau.
- Items différés de la story 2 résolus : validation des arêtes (`ArchitectureChangedPayload`) et schéma qui ignorait `hosting`/`available`.
- Correctifs de revue G1 à G7 appliqués par le même sous-agent (`pending` calculé contre la configuration figée au dernier envoi, arêtes limitées aux nœuds dessinés, cause du dépassement par segment le plus lourd, émissions après chargement, BOM, focus clavier et tiroir `role=dialog`). `pytest` final : 87 passed, 2 deselected ; `ruff` propre. Nouvelle passe navigateur sur le focus non faite.

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 29 constats) :

- [VG1] `bricks_changed` émis au boot jamais vérifié sans bascule préalable — `medium`, pré-vérifié (grep `bricks_changed` dans `tests/`). → G1 `patch`.
- [VG3] Garde « pas de moteur » de `_emit_preview` jamais vérifiée (bascule en mode serveur seul) — `low`, pré-vérifié, test d'une ligne. → G1 `patch`.
- [BH10a] Raison « capacité manquante » de `_availability` non testée — `medium`, confirmé (aucune brique ne déclare de capacité, aucun test). → G1 `patch`.
- [VG2/EC10/BH1] Cause du dépassement mal attribuée : prompt système long accusé d'être le message ; message trop long accusé d'être l'historique dès que la mémoire est active ; branche historique non testée — `medium`, confirmé (`_emit_overflow` ne regarde que la présence d'un segment `history`). → G2 `patch`.
- [VG-autre/EC11] `_boot` émet cartes et schéma avant `self._caps = caps` (L247-261) et jamais après : disponibilité par capacité périmée après un changement de modèle — `low`, latent (aucune brique ne déclare de capacité), correction directe (deux appels déplacés). → G3 `patch`.
- [EC3/BH2] `edges_to` vers un nœud non dessiné (nœud réservé `file.*` jamais émis, composant d'une brique non voulue) : le validateur d'`ArchitectureChangedPayload` lève dans `set_brick` → 500, contraire à AD-16 — `medium`, confirmé ; latent aujourd'hui, atteint dès H2 → `file.audit` (story 8). → G4 `patch`.
- [EC8/EC9/BH6] `pending` est un drapeau « modifié depuis » : activer puis désactiver avant un tour, enregistrer un texte identique ou modifier le prompt brique éteinte affichent « Prend effet au prochain tour » sans rien qui change — `low`, confirmé (`set_brick` L473, `save_system_prompt` L483), rencontré en démonstration. → G5 `patch`.
- [EC13] `system.md` enregistré avec BOM : U+FEFF envoyé en tête du prompt (ni `strip()` ni la normalisation AD-4 ne l'enlèvent) — `low`, correction directe (`utf-8-sig`). → G6 `patch`.
- [EC14/BH7] Focus clavier perdu après chaque bascule (`renderBricks` reconstruit tout le volet) — `medium`, confirmé ; accessibilité clavier exigée par EXPERIENCE.md. → G7 `patch`.
- [BH8] Tiroir sans `role="dialog"`, cartes dessous atteignables au Tab, focus non rendu au bouton « Modifier le prompt » à la fermeture — `low`, confirmé ; corrections directes d'attributs. → G7 `patch`.
- [EC1] Cycle dans `requires` → `RecursionError` — `low`, rejeté : exige une déclaration fautive écrite dans le code, la garde ajoute des branches.
- [EC2] `requires` vers une brique non déclarée → raison qui nomme une brique inexistante — `low`, rejeté (même raison).
- [EC4] `send` bloqué en `turn` si `build_turn_state`/`_emit_bricks` lèvent — `low`, rejeté : aucune de ces fonctions ne lève avec des briques déclarées valides.
- [EC5/EC6/BH4] Fenêtres de course entre `build_turn_state` et la remise à zéro de `pending`, et entre les deux prises du verrou de `build_turn_state` — `low`, rejeté : exige deux intentions à la microseconde près, un seul présentateur. G5 réécrit de toute façon la gestion de `pending`.
- [EC7/BH5] Instantanés `bricks_changed` émis hors verrou, ordre inversé possible entre deux intentions simultanées — `low`, rejeté (même raison).
- [EC12] `build_turn_state(origin_turn)` inconnu → historique entier en silence — `low`, rejeté : aucun appelant avant le rejeu (story 9).
- [EC15] Tiroir ouvert signalé « non enregistré » si un autre onglet change le prompt — `low`, rejeté (un seul onglet en démonstration).
- [BH9] Bascule refusée sans message (404, réseau) — `low`, rejeté : le 404 n'est pas atteignable depuis l'interface, la carte revient à l'état reçu.
- [BH10b] Raisonnement stocké et renvoyé en `reasoning_content` non testé — `low`, rejeté : Qwen3.5 l'efface, déjà signalé par un commentaire `ponytail:`.
- [BH10c] Tests absents pour cycles, `requires` inconnu, `origin_turn` — rejetés avec EC1, EC2, EC12. `_run` importé de `test_turn` — `low`, rejeté (cosmétique).
- [BH11a] `hosting_fr` en YAML redondant avec `Component.hosting`, étiquette toujours locale côté front — `low`, rejeté : latent jusqu'à la première brique réseau (story 5), déjà signalé `ponytail:`.
- [BH11b] `BrickState.category` redéclare le `Literal` au lieu d'importer `Category` — `false` : le spine interdit à `trace` d'importer un module du projet.
- [VG-autre] `emit_initial` sans appelant, l'appel `_emit_bricks()` ajouté y est mort — `low`, rejeté : code mort antérieur à la story, sans effet.

Groupes routés en `patch` : G1 (tests), G2 (cause du dépassement), G3 (émissions après chargement), G4 (arêtes non dessinées), G5 (`pending`), G6 (BOM), G7 (accessibilité du panneau) ; aucun `intent_gap` ni `bad_spec`, pas de loopback.

## Design Notes

Hébergement : les deux composants sont `local_process` (historique en mémoire du harnais, prompt tenu par la session même si son défaut vient d'un fichier du dépôt). `pending` vaut vrai entre un changement et le `turn_started` suivant ; il est calculé par la session. Les deux briques n'ont ni dépendance ni capacité exigée : la disponibilité reste un seul point de calcul, testé par une brique factice, prêt pour la story 5.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)

**Manual checks (if no CLI):**
- `uv run wavestack` : deux tours en LLM nu, puis activer la mémoire courte (aperçu qui grossit, segment « Historique »), activer et modifier le prompt système (segment « Prompt système » au tour suivant), vider la conversation, puis tout éteindre : retour au segment unique « Message et gabarit ».
