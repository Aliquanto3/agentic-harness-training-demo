---
title: "E2E : options, cartes et interrupteurs de l'atelier"
type: 'chore'
created: '2026-10-01'
status: 'done'
route: 'dispatch'
baseline_commit: '11147e0b3f5cf8ecb2d12a044a02d2be341772de'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/tools/e2e/README.md'
warnings: []
deferred: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Neuf entrées « le rendu front de la story X n'est vérifié par aucun test » restent partiellement ouvertes : le parcours E2E couvre le comportement côté serveur, mais aucun contrôle ne clique l'interrupteur ou la carte qui le déclenche, ni ne lit l'état affiché (CAP-5).

**Approach:** Ajouter au parcours E2E (`tools/e2e/run_e2e.py`) un contrôle par comportement non couvert, dans les scénarios existants quand ils s'y prêtent, sinon dans un scénario nouveau court.

## Boundaries & Constraints

**Always:**
- Entrées fermées (`closed: <date> (story 5 des restes différés) — <scénario, contrôle>`), avec ce qui reste à couvrir selon le triage :
  - **E016** — clic sur une carte de connexion MCP hors tour → requête `/api/intentions/mcp_server` ; appariement des cartes ; badge « MCP » ; outils listés dans l'infobulle du nœud serveur.
  - **E017** — clic sur l'interrupteur « Lazy loading » → `/api/intentions/mcp_mode` ; carte d'étape « Chargement de la documentation » avec badge MCP.
  - **E023** — clic sur un skill de la carte → `/api/intentions/skill` ; état « chargé » du skill dans le schéma.
  - **E028** — indicateur « En attente de validation » pendant `awaiting_human` ; les trois boutons inactifs hors de cet état (le reste est couvert par `h5`).
  - **E030** — carte H5 masquée après `conversation_cleared` (Vue humain, Orchestration, cartes MCP, schéma) ; clic unique (un second clic n'envoie rien) ; réponse refusée en 409 affichée.
  - **E035** — interrupteur « Afficher les actions forcées » et sa mémorisation après rechargement ; ligne « Action forcée abandonnée ».
  - **E043** — après « Réinitialiser » : message de la barre haute, préparation du harnais gardée.
  - **E047** — « ⟲ Réinitialiser » referme les listes d'options ouvertes (`store.openExplanations` vidé).
  - **E053** — option « Afficher le raisonnement » : bloc de raisonnement masqué puis affiché dans la Vue humain et Contexte LLM.
- Chaque contrôle porte un libellé français explicite, comme les contrôles existants, et échoue si l'on retire la ligne d'`app.js` qui produit le comportement : le constater une fois à la main par entrée (noter le résultat dans Auto Run Result).
- `page.evaluate` permis pour lire l'état (`store`) quand le DOM ne suffit pas.
- Après les stories 2 et 3 (elles changent la barre haute et les actions forcées) : si D3 a changé l'interrupteur des actions forcées, E035 vérifie le nouveau rendu.

**Never:**
- Banc de test JS ou dépendance nouvelle.
- Modifier `app.js` pour faciliter un contrôle, sauf un attribut `data-*` stable si aucun sélecteur fiable n'existe.
- Délai fixe (`sleep`) : attendre un événement du flux ou un état du DOM.

</frozen-after-approval>

## Code Map

- `tools/e2e/run_e2e.py` -- seul fichier de code touché. Helpers à réutiliser : `Run.check`, `Run.poll`, `Run.set_option` (attend `bricks_changed`), `Run.open_options`, `Run.show_forced`, `Run.arm`, `Run.api` (en-tête `Origin`), `Run.reload_app`/`wait_replayed`, `_step` (dernière étape d'Orchestration par titre), `_unfold_step`, `_schema_node`. Ne pas dupliquer les contrôles des stories 2 à 4 (`s_stream_lost`, `_forced_section`, `_consulted_tools`, dépliement MCP par D3 et `prefix_not_reused` dans `s_mcp_lazy`, date du tiroir de mémoire, délégation nommée).
- `src/wavestack/web/static/app.js` (module ES : `store` et les fonctions ne sont pas globaux, donc lecture par le DOM, `localStorage` et `page.route`) -- lignes que chaque contrôle protège :
  - `setOption` : chemins `/api/intentions/mcp_server`, `mcp_mode`, `skill` (E016, E017, E023).
  - `applyEnvelope` `mcp_connect_ended` : appariement sur la plus ancienne carte non terminée du serveur (`!s.ended`) (E016) ; `connectBody` : badge `step-badge is-mcp` (E016) ; `schemaNode` : `main.schema.tools` dans l'infobulle (E016) et classe `is-loaded` d'un skill (E023).
  - `toolBody` : badge MCP d'une étape du harnais de la brique MCP (E017).
  - `applyEnvelope` `approval_requested` : `phaseLabel` « En attente de validation » (E028) ; `approvalCard` : `button.disabled = !waiting || …` (E028), garde `if (step.answering) return` (E030), `store.composerError` du refus (E030).
  - `renderSteps` : `visible(s)` des connexions après `clearedSeq` (E030, cartes MCP) ; `renderSchema` : `shownTurns().at(-1)` (E030, schéma) ; `renderChat` : tours depuis `chatFrom` (E030, Vue humain).
  - `forcedToggle` : `saveShowForced()` (E035) ; `applyEnvelope` `action_dropped` → ligne « Action forcée abandonnée » (E035).
  - `applyEnvelope` `harness_reset` : `store.topStatus` (E043, contrôle existant) ; `renderSteps` : branche `store.resetSeq !== null` de la préparation (E043) ; `resetHarness` : `store.openExplanations.clear()` (E047).
  - `renderChat` : `if (store.showReasoning)` (E053).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer les neuf entrées (lignes 77, 81, 108, 132, 141, 162, 199, 218, 246).
- `tools/e2e/README.md` -- une section « Restes différés, story 5 » qui liste les contrôles ajoutés.

## Tasks & Acceptance

**Execution:**
- [x] `tools/e2e/run_e2e.py` -- `s_mcp_full` : interrupteur du serveur `local` décoché puis recoché dans la carte MCP (requêtes `/api/intentions/mcp_server` lues par `expect_request`), nouvelle connexion appariée (« connecté », aucune « connexion… »), badge MCP de la ligne dépliée, infobulle du nœud `Glossaire WaveStack` avec ses outils ; puis « Vider la conversation » : plus aucune ligne de connexion dans Orchestration -- E016, E030.
- [x] `tools/e2e/run_e2e.py` -- `s_mcp_lazy` : interrupteur « Lazy loading » décoché puis recoché avant le premier tour (`/api/intentions/mcp_mode`, `mode` lu dans `/api/state`) ; après le tour, étape « Chargement de la documentation » dépliée avec le badge MCP -- E017.
- [x] `tools/e2e/run_e2e.py` -- `s_skills` : skill « Compte rendu de réunion » décoché puis recoché (`/api/intentions/skill`) ; nœud du schéma « Non chargé » avant, `is-loaded` et « Chargé dans la conversation » après le tour -- E023.
- [x] `tools/e2e/run_e2e.py` -- `s_h5` : indicateur « En attente de validation » (Vue humain et Orchestration) ; double clic synchrone sur « Refuser » = une seule requête ; rechargement avec `/api/state` réécrit (`state: turn`) : trois boutons inactifs ; validation déjà répondue par l'API puis clic dans la page : 409 affiché sous le champ ; « Vider la conversation » : aucune carte H5, Orchestration vide, nœud « Jours fériés » sans « Au tour » -- E028, E030.
- [x] `tools/e2e/run_e2e.py` -- `s_forced_native` : interrupteur gardé après rechargement (`localStorage`, bouton « Forcer » présent) ; action armée puis outil décoché : ligne « Action forcée abandonnée · Heure et date » -- E035.
- [x] `tools/e2e/run_e2e.py` -- `s_reload_and_reset` : serveur MCP local connecté avant les tours, liste d'options des Hooks ouverte ; après « Réinitialiser » : préparation du harnais avec le Glossaire, aucune liste d'options ouverte -- E043, E047.
- [x] `tools/e2e/run_e2e.py` -- `s_bare_llm` : « Afficher le raisonnement » décoché : aucun bloc dans la Vue humain, réflexion toujours dans Contexte LLM, choix gardé au rechargement ; recoché : bloc revenu -- E053.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- ligne `closed:` sous chacune des neuf entrées.
- [x] `tools/e2e/README.md` -- section des contrôles ajoutés.

**Acceptance Criteria:**
- Given la pile E2E sur le faux modèle, when les tranches `--only` couvrant `h5 mcp_full mcp_lazy skills` puis `forced_native bare_llm reload_and_reset programme` sont jouées, then aucun contrôle n'échoue et chaque contrôle ajouté figure dans la sortie.
- Given une ligne d'`app.js` nommée dans le Code Map retirée à la main, when le scénario qui la protège est rejoué, then au moins un contrôle ajouté échoue ; la ligne remise, il passe.
- Given `uv run ruff check tools/e2e` et `uv run ruff format --check tools/e2e`, then aucun écart.

## Implementation Notes

- Implémenté directement par l'agent de la story (mode nuit) plutôt que par un sous-agent : l'investigation était faite et l'E2E ne se joue qu'une tranche à la fois.
- Fichiers : `tools/e2e/run_e2e.py` (helpers `_show_reasoning_option`, `_awaiting_indicator`, `_approval_posts`, `_buttons_off_outside_awaiting`, `_approval_refused_409`, `_h5_cleared`, `_intention_toggle`, `_mcp_server_switch`, `_forced_kept_after_reload`, `_forced_dropped`, `_connect_local_mcp`, `_reset_keeps_prep_and_folds`), `tools/e2e/README.md`, `deferred-work.md` (neuf `closed:`). `app.js` inchangé.
- Surprise : `app.js` est chargé en module (`type="module"`), donc ni `store` ni aucune fonction n'est joignable par `page.evaluate` ; tout passe par le DOM, `localStorage`, les requêtes et `page.route`.
- Défaut du parcours trouvé à la première tranche : le contrôle existant de `mcp_full` « Forcer l'appel · local__define_term » échouait (bouton absent). Depuis D3 (story 3), « Afficher les actions forcées » déplie la liste MCP au rendu suivant ; `Run.open_options` cliquait parfois juste après ce rendu et la repliait. Corrigé dans le helper (vérifie l'ouverture, reclique sinon) ; ce n'est pas un défaut d'`app.js` (course de quelques millisecondes, sans effet pour un utilisateur).
- `_intention_toggle` rend la raison au lieu de lever quand aucune requête ne part : le contrôle étiqueté échoue lisiblement.
- Sous Windows, la sortie redirigée vers un fichier demande `PYTHONIOENCODING=utf-8` (noté dans le README).

### Auto Run Result

Mutations faites à la main dans `app.js`, rejouées, puis défaites (`git checkout`) ; chaque contrôle visé a échoué :

| Entrée | Ligne retirée ou neutralisée | Contrôle en échec |
|---|---|---|
| E016 | branche `mcp` de `setOption` | « l'interrupteur du serveur poste `/api/intentions/mcp_server` » (scénario arrêté : aucun `bricks_changed`, avant `_intention_toggle` tolérant) |
| E016 | `&& !s.ended` de `mcp_connect_ended` | « la nouvelle connexion … reçoit sa propre fin » (« connexion… » : 1) |
| E016 | badge de `connectBody` | « la ligne de connexion dépliée porte le badge « MCP » » |
| E016 | `main.schema.tools` dans `schemaNode` | « l'infobulle du nœud du serveur liste ses outils » |
| E017 | branche `mcp_mode` de `setOption` | « l'interrupteur « Lazy loading » poste … » (aucune requête) |
| E017 | badge MCP de `toolBody` | « l'étape « Chargement de la documentation » porte le badge » |
| E023 | branche `skills` de `setOption` | « l'interrupteur du skill poste … » (aucune requête) |
| E023 | `classList.toggle("is-loaded")` | « après le tour, le nœud du skill est marqué chargé » |
| E028 | `phaseLabel` d'`approval_requested` | « indicateur « En attente de validation » » (montre « Envoi du contexte… ») |
| E028 | `!waiting ||` de `approvalCard` | « hors `awaiting_human`, … trois boutons inactifs » (actifs) |
| E030 | `if (step.answering) return;` | « deux clics sur « Refuser » n'envoient qu'une réponse » (2 requêtes) |
| E030 | `store.composerError` du refus | « réponse refusée par la session (409) affichée » |
| E030 | `store.chatFrom = …` de `conversation_cleared` | « après « Vider la conversation », aucune carte H5 … » (cartes 5, étapes 10, appels 2) |
| E030 | `shownTurns()` → `store.turns` dans `renderSchema` | « le schéma ne dit plus l'état du tour masqué » |
| E030 | `&& visible(s)` de `connections` (`renderSteps`) | « la connexion MCP d'après le tour est masquée » |
| E035 | `saveShowForced()` du changement | « gardé après rechargement » (`localStorage` nul, case décochée) |
| E035 | `action_dropped` d'`applyEnvelope` | « ligne « Action forcée abandonnée · Heure et date » » |
| E043 | branche `store.resetSeq !== null` de la préparation | « la préparation du harnais garde la connexion MCP » |
| E043 | `store.topStatus = resetStatusText()` | contrôle existant « message « WaveStack réinitialisé : LLM nu. » » |
| E047 | `store.openExplanations.clear()` | « « Réinitialiser » referme les listes d'options ouvertes » (1 ouverte) |
| E053 | `if (store.showReasoning)` → `if (true)` | « décoché, plus de bloc dans la Vue humain » et « gardé au rechargement » |
| E028 (revue) | ligne de la décision dans `approvalCard` | « la carte répondue affiche « Décision : Refusé » » et « … Annulé : tour arrêté » |
| E016 (revue, rejoué) | branche `mcp` de `setOption`, `_intention_toggle` final | « l'interrupteur du serveur poste `/api/intentions/mcp_server` » (contrôle étiqueté, puis exception sur `mcp_connect_ended`) |

Tranches propres (faux modèle, réseau coupé, une à la fois), après les correctifs de revue : `h5 mcp_full mcp_lazy skills` 63 réussies, 0 échec ; `forced_native bare_llm reload_and_reset programme` 73 réussies, 0 échec ; `hooks caveman data_flows network_tools soc` (non-régression de `Run.open_options`) 80 réussies, 0 échec. Avant la revue : `stream_lost global_memory subagent native_tools` 106 réussies, 0 échec (contrôles des stories 2 à 4).

## Spec Change Log

- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : point d'arrêt 1 de bmad-build, « Approve and continue » ; la spec respecte CAP-5, la contrainte « pas de banc JS » et le triage (E016, E017, E023, E028, E030, E035, E043, E047, E053). Spec d'environ 2 900 tokens, sous le seuil de 4 000 du projet : pas de découpage.

## Review Triage Log

Passe 1 (2026-10-02), trois couches : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Couche | Constat | Verdict | Preuve / suite |
|---|---|---|---|---|
| 1 | BH, EC, VG | `Run.open_options` rend la main sans rien dire si la liste reste repliée après trois essais | low | Vrai ; correctif direct : `AssertionError` qui nomme la carte (patch). La stabilité après le retour : course non montrée, rejetée. |
| 2 | BH | `_show_reasoning_option` peut laisser `wavestack.showReasoning = "0"` si le rechargement lève | medium | Vrai : même page pour tous les scénarios. `try/finally` qui recoche (patch). |
| 3 | BH, EC | écouteur `request` de `_approval_posts` jamais retiré si `ev.wait` lève | low | Vrai ; `try/finally` (patch). |
| 4 | EC | une requête du second clic encore en file quand l'écouteur est retiré : faux succès possible | medium | Vrai en principe : `ev.wait` est du Python pur, sans pompe des événements Playwright. Aller-retour `page.evaluate("() => 0")` avant le retrait (patch). |
| 5 | BH | `MutationObserver` jamais déconnecté | low | Sans effet observable (la page est rechargée par les scénarios suivants) ; rejeté. |
| 6 | BH | interrupteurs MCP, lazy, skill non remis en cas d'échec | low | Chaque scénario relance le sien, qui règle les briques ; rejeté. |
| 7 | BH | `route: 'dispatch'` contredit « implémenté directement » | false | `route` est le chemin du plan (spec complète), pas l'exécutant. |
| 8 | BH | mutation E016 `mcp_server` jouée avant le `_intention_toggle` tolérant | low | Vrai ; rejouée, contrôle étiqueté en échec (Auto Run Result). Pas de script de mutations : rejeté (la spec demande un constat à la main). |
| 9 | BH | aucune preuve que le reste du parcours passe avec le nouvel `open_options` | low | Tranche `hooks caveman data_flows network_tools soc` jouée : 80/0. |
| 10 | BH, VG | fermeture de 8c (E030) : « le reste couvert par `h5` » faux (libellé, focus, trace sans bouton, puce liée, filet rouge H1) | medium | Vérifié par VG (aucun contrôle). Hors du périmètre gelé : ligne `closed:` réécrite et entrée nouvelle dans `deferred-work.md` (defer). |
| 11 | VG | fermeture de E028 : la décision affichée après résolution n'est lue par aucun contrôle | medium | Vrai. `_card_decision` (« Décision : Refusé », « Décision : Annulé : tour arrêté », boutons retirés), mutation vérifiée (patch). |
| 12 | BH | contrôle du 409 : « déjà reçu une réponse » commun à `unknown` et `answered` | low | Vrai ; texte complet de `session.approval.answered` (patch). Lecture depuis `messages.yaml` : le parcours est en `fr` comme les autres contrôles ; rejeté. |
| 13 | BH, EC | `_buttons_off_outside_awaiting` peut passer sans réécriture ou sur une carte répondue | low | Vrai en principe ; l'état réécrit est noté et la carte doit être sans « Décision » (patch). |
| 14 | EC | `route.fetch()` qui lève : rechargement bloqué | low | Panne bruyante (délai de `wait_replayed`) ; rejeté. |
| 15 | EC | `r.api` qui lève dans le gestionnaire de route : requête de la page jamais relâchée | low | `try/finally` autour de `route.continue_()` (patch). |
| 16 | EC | `window.__composerReasons` absent après un rechargement : `TypeError` | low | `|| []` (patch). |
| 17 | EC | `_intention_toggle` dit « aucune requête » alors que la requête est partie (seul `bricks_changed` manque) | low | Libellé corrigé : « pas de requête … suivie de bricks_changed » (patch). |
| 18 | EC | nœud du serveur, étape lazy ou nœud du skill absents : attente de 30 s puis exception | false | Échec bruyant sur une situation que le parcours n'atteint pas ; comportement correct. |
| 19 | EC | `set_option(False)` qui lève après `arm`, hors du `try` de `_forced_dropped` | low | Déplacé dans le `try` (patch). |
| 20 | BH, EC | `_connect_local_mcp` : MCP allumé dans `reload_and_reset`, attentes de 45 s, serveur qui démarre plus tard | low | Les contrôles existants passent (73/0) ; brique et serveurs démarrés par la même intention ; rejeté. |
| 21 | EC | `_connect_local_mcp` : refus non 2xx de l'API rendu opaque | low | Panne bruyante ; rejeté. |
| 22 | BH | E030 côté MCP : vérifie toutes les étapes, pas la seule ligne du Glossaire | false | « Aucune étape » inclut cette ligne, et la mutation `visible(s)` le fait échouer. |
| 23 | BH | comparaison chaînée `mode_off != "lazy" == mode_on` | low | Juste mais peu lisible ; écrite en deux comparaisons (patch). |
| 24 | BH | `_forced_kept_after_reload` suppose l'interrupteur allumé par `_forced_section` | low | `r.show_forced(True)` explicite (patch). |
| 25 | BH | « Chaque contrôle échoue sa ligne d'`app.js` retirée » : tournure fautive | low | Remplacée partout par « échoue si l'on retire sa ligne d'`app.js` » (patch). |

## Design Notes

- `app.js` est un module : aucune fonction globale à appeler. Les états hors DOM se lisent par `localStorage` (actions forcées, raisonnement), les requêtes par `page.expect_request`/`page.on("request")`, et deux états difficiles à atteindre par le vrai serveur passent par `page.route` : `/api/state` réécrit pour rendre une validation en attente hors `awaiting_human` (E028) ; `/api/intentions/approval` qui répond d'abord par l'API, puis laisse partir la requête de la page, pour obtenir un vrai 409 (E030).
- Le 409 peut être effacé par le `session_state` `idle` qui suit : un `MutationObserver` posé avant le clic note chaque texte de `#composer-reason`.
- Le double clic synchrone (`b.click(); b.click()` dans `evaluate`) vise le même nœud : le second appel n'est arrêté que par la garde `step.answering`, pas par un bouton désactivé.

## Verification

**Commands:**
- `uv run ruff check tools/e2e` -- expected: aucun écart.
- `uv run ruff format --check tools/e2e` -- expected: aucun écart.
- `MSYS_NO_PATHCONV=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only h5 mcp_full mcp_lazy skills` -- expected: 0 échec.
- `MSYS_NO_PATHCONV=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only forced_native bare_llm reload_and_reset programme` -- expected: 0 échec.
- `MSYS_NO_PATHCONV=1 uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only hooks caveman data_flows network_tools soc` -- expected: 0 échec (non-régression de `Run.open_options`).
