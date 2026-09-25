---
title: 'Scénarios par brique, programme, réinitialisation'
type: 'feature'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'ec58d52d112b6f5947b5459633973122fe6e827d'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le formateur règle chaque brique à la main avant chaque démonstration et improvise ses prompts ; entre deux sessions, rien ne ramène WaveStack à son état de départ sans le relancer (CAP-40, CAP-41, FR-38, FR-39). Clôture du palier 1.

**Approach:** Un fichier `content/scenarios.yaml` (AD-19), validé par un modèle pydantic, déclare le programme en modules et un scénario par brique construite (stories 1 à 9b), plus « Où vont mes données ? ». Un sélecteur dans la barre haute lance un scénario en un clic : configuration des briques appliquée, conversation vidée, prompts suggérés au-dessus du champ de saisie. Un bouton « Réinitialiser » ramène à l'état de lancement (LLM nu, aucun tour).

## Boundaries & Constraints

**Always:**
- Schéma d'un scénario (AD-19) : `title_fr`, `description_fr` (consigne de déroulé, 1 à 3 phrases), `bricks` (briques voulues), `tools`, `mcp_servers`, `skills`, `hooks` (sous-options activées ; absentes = valeurs de lancement), `mcp_lazy` (faux par défaut), `prompts` (au moins un), `expects_overflow` (faux par défaut). Programme : liste ordonnée de modules `{title_fr, duration_min (30 à 60), scenarios}`, puis une liste `transverse`. Tout identifiant (brique, outil, serveur, skill, hook, scénario) est vérifié au chargement ; un fichier invalide donne `harness_error` et un programme vide, jamais un plantage.
- Chaque scénario déclare sa configuration complète, pas un écart : lancer le premier scénario d'un module donne les briques des modules précédents déjà actives (FR-38).
- Programme livré, dans l'ordre de FR-38 limité aux briques construites :
  - Module 1 « Du LLM nu au harnais » : LLM nu (« Quelle heure est-il ? »), Mémoire courte, Prompt système.
  - Module 2 « Outils » : Outils natifs, Outils réseau.
  - Module 3 « MCP » : Documentation complète (local + data.gouv.fr), Lazy loading.
  - Module 4 « Skills et hooks » : Skills, Caveman, Hooks.
  - Transverse : « Où vont mes données ? » (UJ-4 : outils locaux actifs, la consigne fait activer MCP local puis public).
- Caveman : skills actifs, Caveman compris ; la consigne dit d'envoyer le prompt, d'armer « Déclencher le skill » Caveman, de rejouer (9b) puis d'ouvrir « Comparer ».
- Hooks (UJ-2) : outils avec `read_file`, hooks H1 et H2 seuls (H3 retiré, il pousse le SLM au refus) ; prompt suggéré de lecture de `confidentiel/budget_projet.txt` ; la consigne renvoie au forçage de `read_file` (préréglage « Fichier sensible ») si le modèle n'appelle pas l'outil, et à la bande des points d'accroche du schéma (8e).
- Lancer un scénario et réinitialiser sont des intentions de classe (b) : refusées hors `idle` avec la raison, 409 comme `send`. Scénario inconnu : 404.
- Configuration de lancement = celle de `AppSession.__init__` (aucune brique, sous-options par défaut, prompt système par défaut, aucune action armée). Réinitialiser l'applique, vide la conversation (comme « Vider la conversation ») et désactive le scénario actif. Lancer un scénario = vider la conversation, appliquer la configuration de lancement puis celle du scénario. Dans les deux cas, un seul `bricks_changed`, un seul `architecture_changed`, un aperçu ; les serveurs MCP se connectent ou se ferment selon l'écart (AD-15).
- Événements (AD-2) : `scenario_changed {program, active}` émis au démarrage, au lancement et à la réinitialisation, repris par `/api/state` ; `harness_reset {}` à la réinitialisation. Le journal côté serveur n'est jamais tronqué.
- Front, à `harness_reset` : Vue humain, Contexte LLM et Orchestration reviennent à « Aucun tour » (textes de l'état « Aucun tour », pas celui de « Conversation vidée ») ; la préparation du harnais garde les lignes de connexion MCP d'avant la réinitialisation (sauf celles déjà masquées par un « Vider la conversation »), et les connexions suivantes s'y ajoutent (décision du 2026-09-25) ; le journal des événements affiché repart de zéro (titre et compte compris) ; comparaison fermée ; message discret « WaveStack réinitialisé : LLM nu. » ; volets et taille de texte inchangés.
- Sélecteur : `<select>` natif dans la barre haute, un `optgroup` par module (« Module 1 · Du LLM nu au harnais · 45 min ») puis « Transverse » ; option vide « Choisir un scénario » ; choisir une option lance le scénario ; l'option affichée suit `active`. Désactivé hors `idle`, avec la raison en infobulle. « ⟲ Réinitialiser » à l'extrémité droite de la barre, sans confirmation, même règle d'activation.
- Vue humain, scénario actif : titre et consigne sur une ligne au-dessus du champ, puis une puce par prompt suggéré ; un clic remplit le champ sans envoyer (UJ-2). `expects_overflow` affiche « Ce scénario fait déborder le contexte : c'est voulu. ».
- Textes en français ; contrôles atteignables au clavier avec un nom accessible.

**Never:** mémoire globale, raisonnement, RAG, sous-agent, compression (non construits) ; scénarios métier FR-40 (palier 2) ; déroulé pas à pas automatisé ; nouvelle dépendance ; toucher au rejeu, au forçage ou au schéma au-delà de ce qui précède.

## I/O & Edge-Case Matrix

| Scénario | État | Comportement attendu |
|---|---|---|
| Lancer « Hooks » | LLM nu, deux tours | Conversation vidée ; briques et sous-options = celles du scénario ; `scenario_changed.active = "hooks"` ; prompts affichés. |
| Lancer un module | aucune brique | Le premier scénario du module 3 active mémoire courte, prompt système, outils et MCP. |
| Scénario après réglages manuels | prompt système modifié, Caveman armé | Prompt par défaut, rien d'armé, config du scénario seule. |
| Réinitialiser | scénario MCP actif, tours, prompt modifié | Aucune brique, sous-options et prompt de lancement, rien d'armé, historique vide, rien à rejouer, serveurs fermés ; `active = null` ; `/api/state` le reflète. |
| Journal serveur | après réinitialisation | `events_since(0)` contient toujours les événements d'avant. |
| Hors idle | tour en cours | 409 avec la raison, rien ne change. |
| Contenu invalide | brique inconnue dans un scénario | `harness_error` au démarrage, programme vide, sélecteur sans scénario, l'application démarre. |

</frozen-after-approval>

## Code Map

- `content/scenarios.yaml` (nouveau) -- programme et scénarios ; ids de `bricks/registry.py` (`short_memory`, `system_prompt`, `tools`, `mcp`, `skills`, `hooks` ; `SKILLS`, `HOOKS`), outils de `content/tools.yaml`, serveurs `local`/`datagouv`/`mslearn`.
- `src/wavestack/scenarios.py` (nouveau) -- `ScenarioContent`, `load_scenarios(known)` sur le modèle de `hooks.py:62-90` (`yaml.safe_load`, `model_validate`, contrôle croisé des ids → `ValueError`), `config.content_dir()` (`config.py:180`).
- `src/wavestack/session/app_session.py` :
  - `__init__` 293-367 : extraire la configuration de lancement (`_wanted`, `_custom_prompt`, `_tools_enabled` 315, `_mcp_enabled` 324, `_mcp_lazy` 329, `_skills_enabled` 333, `_hooks_enabled` 336) dans une fonction réutilisée par la réinitialisation ; `_sent` (351) revient à cette configuration.
  - `_load_content` 770-850 : un bloc `try` de plus pour les scénarios, `_error(...)` (685) en cas d'échec.
  - `emit_initial` 376 : émettre `scenario_changed`.
  - `clear_conversation` 1653 : réutiliser son corps (vidage + `_last = None`) pour la réinitialisation et le lancement.
  - Nouveaux `launch_scenario(id)` et `reset()` : sous le verrou, contrôle `idle` (`_refusal_reason` 1666), application, `_armed.clear()` + `_emit_armed` (1354) ; puis `_mcp_connect`/`_mcp_disconnect` (1617) sur l'écart des serveurs connectés, `_emit_bricks`, `_emit_architecture`, `_emit_preview` une fois. Ne pas passer par `set_*` (un événement par appel).
- `src/wavestack/trace/catalog.py` -- `ScenarioChangedPayload`, `HarnessResetPayload`, entrées de `PAYLOAD_MODELS` (371-404).
- `src/wavestack/web/app.py` -- `POST /api/intentions/scenario {scenario_id}` et `/api/intentions/reset` sur le modèle de `clear_conversation` (333-340) ; `KeyError` → 404 (243-250) ; `/api/state` (150-181) ajoute `scenario_changed`.
- `src/wavestack/web/static/index.html` -- barre haute 12-27 : `<select id="scenario-picker">` après le titre, `#reset-button` en dernier, `#top-status` (`aria-live`) ; Vue humain 75-78 : `#scenario-guide` et `#suggested-prompts` avant `#armed-chips`.
- `src/wavestack/web/static/app.js` :
  - `applyEnvelope` : `scenario_changed` → `store.scenarios`; `harness_reset` sur le modèle de `conversation_cleared` (163-168), plus `store.logFrom = store.journal.length`, remise à zéro de `eventLog` (2681).
  - `syncLogGroups` 2683 et `renderJournal` 2750 : partir de `store.logFrom`.
  - Préparation du harnais : `connections()` dans `renderSteps` 2167 filtre aujourd'hui `afterTurn === store.chatFrom` ; après une réinitialisation, la préparation prend aussi les connexions d'avant (`afterTurn <= chatFrom`, toujours après `clearedSeq`), sans changer le cas « Vider la conversation » ; texte vide 2195-2201 : texte « Aucun tour » après une réinitialisation.
  - `renderComposer` 1140-1180 : activation du sélecteur et du bouton ; `postIntention` 1182 ; branchements dans `boot()` (~3309).
- `src/wavestack/web/static/app.css` -- sélecteur, bouton à droite, puces de prompt sur le modèle de `.armed-chips-row`, jetons de DESIGN.md.
- Tests : `tests/fake_engine.py` (`FakeEngine`, `booted_session` 85), `tests/test_bricks.py` (`_client` 36, `_latest` 32, `test_clear_conversation_*` 160-190), boucle MCP `tests/test_mcp.py:63`.

## Tasks & Acceptance

**Execution:**
- [x] `content/scenarios.yaml` -- programme et 11 scénarios ci-dessus, consignes et prompts en français.
- [x] `src/wavestack/scenarios.py` -- modèle et chargeur.
- [x] `src/wavestack/trace/catalog.py` -- deux événements.
- [x] `src/wavestack/session/app_session.py` -- configuration de lancement factorisée, `launch_scenario`, `reset`, chargement et émission.
- [x] `src/wavestack/web/app.py` -- deux routes, `/api/state`.
- [x] `src/wavestack/web/static/index.html`, `app.js`, `app.css` -- sélecteur, réinitialisation, consigne et prompts suggérés, journal affiché depuis la réinitialisation.
- [x] `tests/test_scenarios.py` (nouveau) -- une ligne de la matrice par test ; le vrai `content/scenarios.yaml` se charge et chaque scénario se lance sur `FakeEngine` (serveurs publics non contactés en test) ; routes 200, 404, 409.

**Acceptance Criteria:**
- Given un scénario lancé, when la page est rechargée, then le sélecteur, la consigne et les prompts suggérés réapparaissent (projection du journal, AD-1).
- Given une réinitialisation, when la page est rechargée, then les volets montrent « Aucun tour » et le journal des événements affiché ne contient que ce qui suit la réinitialisation.
- Given une puce de prompt suggéré, when on clique, then le champ est rempli et rien n'est envoyé.

## Implementation Notes

- Le programme livré compte 11 scénarios (3 + 2 + 2 + 3 + 1 transverse), soit la liste de « Always » ; le « 12 » de la tâche `content/scenarios.yaml` ne correspond à aucune entrée supplémentaire.
- Lancer un scénario émet `conversation_cleared` (même corps que « Vider la conversation ») ; la réinitialisation émet `harness_reset` à la place, pour que le front revienne à « Aucun tour » et garde les connexions MCP.
- `scenario_changed` est émis à la construction de `AppSession` (`emit_initial`, sans appelant, n'est pas modifié) ; `/api/state` en reprend le dernier.
- `_apply_launch_config` exclut aussi les outils MCP des sous-options d'outils, car le registre en contient au moment d'une réinitialisation.

## Spec Change Log

## Review Triage Log

Passe 1 (2026-09-25) — relecteurs : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| VG1 / BH8 | `mcp_lazy` d'un scénario jamais vérifié | low | Gap pré-vérifié : supprimer l'affectation passe tous les tests. | patch |
| VG2 / BH8 | Connexion MCP au lancement jamais testée | medium | Gap pré-vérifié : seule la déconnexion est espionnée. | patch |
| VG3 | Contrôle des entrées du programme absentes de `scenarios` non testé | medium | Gap pré-vérifié : sans lui, `payload()` lève `KeyError` hors du `try`, dans `__init__`. | patch |
| VG4 | Rendu front de la réinitialisation et du sélecteur sans test automatique | medium | Gap pré-vérifié : aucun banc de test JS, même écart que 5b à 9b. | defer |
| VG-autre / BH10a | `visible()` masque encore les connexions d'avant un « Vider » qui précède la réinitialisation | false | Conforme à la décision figée : « sauf celles déjà masquées par un « Vider la conversation » ». | rejeté |
| EC1 / BH2 | Relancer un scénario MCP ne réessaie pas un serveur tombé | false | EXPERIENCE.md (serveur public indisponible) : « Pas de nouvel essai sans redémarrer WaveStack : c'est accepté ». | rejeté |
| EC2 | Une brique absente du registre rejette tout le fichier | low | Le registre est fixe dans le code ; cas jamais rencontré, correctif = validation par scénario. | rejeté |
| EC3 / BH6 | Scénario listé deux fois ou jamais listé, sous-options sans leur brique | low | Erreurs de contenu absentes du fichier livré ; correctif = contrôles en plus. | rejeté |
| EC4 / BH5 | Message « WaveStack réinitialisé » affiché indéfiniment | low | `topStatus` n'est remis à `null` qu'au lancement d'un scénario. Correction d'une ligne sur `turn_started`. | patch |
| EC5 | Scénario toujours affiché après un réglage manuel | false | Voulu : les consignes demandent d'activer des briques à la main (« Où vont mes données ? ») ; « l'option affichée suit `active` ». | rejeté |
| EC6 | Prompt vide dans le YAML | low | Absent du contenu livré ; contrainte en plus pour un cas d'auteur. | rejeté |
| EC7 | Puce cliquée pendant un tour : champ désactivé réécrit | low | Sans effet visible ni perte : le champ est vide pendant un tour ; correctif = état en plus. | rejeté |
| BH1a | `<select>` sous Windows : flèches sur la liste fermée lancent un scénario à chaque touche | low | Réel sous Chromium Windows ; Alt+Bas ouvre la liste sans lancer ; l'animateur utilise la souris ; correctif = bouton « Lancer », qui change l'UX figée. | rejeté |
| BH1b | Réinitialisation sans confirmation | false | Décision figée et FR-39 (« en un geste », « sans confirmation »). | rejeté |
| BH3 | `expects_overflow` de `mcp_full` non vérifié | maybe-false | Dépend de la documentation réelle de data.gouv.fr et de la fenêtre ; à trancher au test manuel sur le PC cible. Si faux : medium. | defer |
| BH4 | Scénarios réseau sans repli hors ligne dans la consigne | low | Consignes MCP muettes sur l'absence de réseau ; correction de texte. | patch |
| BH7 | Caveman et Hooks sans les briques précédentes | false | Voulu : seul le premier scénario d'un module est cumulatif (spec, exemple Hooks des Design Notes). | rejeté |
| BH9 | Valeurs de lancement encore posées dans `__init__` avant `_apply_launch_config` | low | Vérifié (`_wanted` 296, `_mcp_lazy` 324) ; suppression directe. | patch |
| BH10b | `harness_reset` sans résumé dans le journal | low | Vérifié dans `eventSummary` ; ajout d'un cas. | patch |
| BH11 | Le programme n'expose pas les briques de chaque scénario | false | Hors intention : la spec ne demande que titre, consigne et prompts. | rejeté |
| BH12 | Fichier de spec absent du diff | false | Voulu : le diff de revue ne porte que sur `content`, `src`, `tests`. | rejeté |

## Design Notes

Un scénario déclare sa configuration complète plutôt qu'un écart au précédent : le fichier se lit scénario par scénario, et « démarrer un module directement » ne demande aucun calcul. Le prix est la répétition des briques d'un scénario à l'autre, acceptable pour une douzaine d'entrées.

```yaml
hooks:
  title_fr: Hooks
  description_fr: >-
    Envoyez le prompt, puis regardez la bande « Points d'accroche » du schéma …
  bricks: [short_memory, system_prompt, tools, hooks]
  tools: [get_datetime, read_file]
  hooks: [h1, h2]
  prompts: ["Lis le fichier confidentiel/budget_projet.txt et résume-le."]
```

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run python -m pytest` -- expected: tout passe
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks:**
- `uv run wavestack` : lancer « LLM nu », cliquer le prompt suggéré, envoyer ; lancer le module 3 (briques des modules 1 et 2 actives) ; lancer « Hooks » et vérifier le blocage H1 ; réinitialiser (Aucun tour, journal affiché vide, message) ; recharger la page.
