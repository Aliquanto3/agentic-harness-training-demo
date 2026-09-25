---
title: 'Validation H5 dans la Vue humain, « Vider la conversation » vide aussi Contexte LLM et Orchestration'
type: 'feature'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'fef875f8f5ab90cb1ad137889c5ebbc8c3a1ea0d'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Suite de la revue de la story 8b (a6f257b). La demande de validation H5 se trouve dans Orchestration, un volet d'observation : l'utilisateur qui converse dans la Vue humain ne la voit pas, alors que c'est à lui de répondre. Et « Vider la conversation » ne vide que les bulles : Contexte LLM et Orchestration continuent d'afficher les tours d'avant.

**Approach:** Front seulement (`app.js`, `app.css`), aucun changement de backend. (1) La carte de validation interactive passe dans le fil de la Vue humain ; la carte d'Orchestration devient une trace en lecture seule. (2) Contexte LLM et Orchestration n'affichent plus que les tours postérieurs au dernier `conversation_cleared`, ce que le rejeu du journal reproduit après rechargement.

## Boundaries & Constraints

**Always:**
- Carte de la Vue humain : violette (`harness-event is-info`), dans le fil du tour concerné, sous la bulle du modèle. Contenu : titre « En attente de votre validation », libellé de l'outil, destination, données qui sortiraient (ligne `🌐 RÉSEAU méthode URL` visible, corps brut replié par défaut, `outboundPayload` réutilisé) et les trois boutons « Autoriser », « Refuser », « Autoriser et ne plus demander », actifs seulement en `awaiting_human`. Une fois résolue, les boutons laissent la place à la décision (« Autorisé », « Refusé », « Annulé : tour arrêté », « · H5 désactivé »), titre « Validation humaine ».
- Libellé de l'outil : `label_fr` de l'option de la brique « Outils » pour un outil natif ; pour un outil MCP (`serveur__outil`), « outil » suivi du libellé du serveur pris dans la brique « MCP » ; à défaut, le nom brut. Mise en forme seulement (AD-1).
- Les boutons survivent au rafraîchissement de 250 ms : un clic n'est pas perdu et le focus clavier reste sur le bouton.
- Carte d'Orchestration : même titre, point d'accroche, hook, outil, destination, aperçu (`outbound-payload` ouvert par défaut, inchangé), décision (« En attente de votre réponse dans la Vue humain » tant qu'elle n'est pas rendue) et « Décision demandée par le harnais (code), pas par le modèle ». Aucun bouton.
- Vue humain masquée pendant l'attente : la puce « + Vue humain » est marquée `is-linked`.
- Après `conversation_cleared` : Contexte LLM et Orchestration (rail d'étapes) n'affichent que les tours suivants ; sans nouveau tour, un message dit que la conversation a été vidée et que les tours précédents restent dans le journal des événements. Même rendu après rechargement (journal rejoué depuis 0). Le filet rouge d'un hook bloquant dans le schéma ne vaut plus pour un tour masqué.
- Le texte de la Vue humain après vidage (`CLEARED_FR`) renvoie au journal des événements et non plus à « la trace ».
- EXPERIENCE.md, ligne 129 (en-tête de la vue humain) et ligne 166 (validation humaine en attente), mis à jour en conséquence, avec le renvoi à la story 10 (CAP-41) pour la réinitialisation complète.

**Décisions (2026-09-25) :**
- Q1 : les cartes de connexion MCP (`offTurn`) affichées avant le vidage sont masquées aussi : Orchestration est vide après « Vider » ; la découverte reste dans le journal des événements.
- Spec gardée entière malgré sa taille (environ 2 300 tokens).

**Never:** aucun changement de backend, d'événement ni de `/api/state` ; la liste des événements (journal), la jauge, les briques et le journal d'audit H2 ne sont pas vidés ; pas de réinitialisation complète (story 10, CAP-41) ; le front ne calcule aucun état (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Attente | `approval_requested`, `awaiting_human` | Carte à boutons dans la Vue humain ; trace sans bouton dans Orchestration ; indicateur « En attente de validation » | N/A |
| Réponse | Clic « Refuser » | Les deux cartes affichent « Refusé » ; boutons retirés | Réponse non acceptée : raison sous le champ de saisie, boutons réactivés |
| Rechargement en attente | Page rechargée | Carte à boutons actifs dans la Vue humain | N/A |
| Vue humain masquée | Attente | Puce « + Vue humain » liée | N/A |
| Vider | 2 tours puis « Vider » | Vue humain, Contexte LLM, Orchestration : message de vidage ; journal des événements complet | N/A |
| Tour suivant | Vider puis envoyer | Seul le nouveau tour apparaît dans les trois volets | N/A |
| Rechargement après vidage | Page rechargée | Mêmes volets vides qu'avant | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/web/static/app.js` :
  - `store` (L14) : `chatFrom` sert déjà d'indice du premier tour affiché ; `applyEnvelope` `conversation_cleared` (L122) le règle. Réutiliser pour `renderContext` (L751, cherche le dernier tour avec `context`) et `renderSteps` (L1055, `store.turns.forEach`). `offTurn` (L216) : entrées placées par `afterTurn` ; pour masquer celles d'avant le vidage (Q1), noter le `seq` du vidage et celui de chaque entrée (`afterTurn` ne distingue pas une connexion juste avant le vidage d'une connexion juste après).
  - `renderChat` (L653) : reconstruit `#chat` à chaque rendu, y compris toutes les 250 ms pendant un tour (L1487) ; ajouter la carte après la bulle du modèle. Garder le nœud de la carte entre deux rendus tant que son état ne change pas, et restaurer le focus comme `renderBricks` (L386-392, `data-focus-key`).
  - `approvalLines` (L949) et `hookCard` (L1000) : à séparer en carte interactive (Vue humain) et trace (Orchestration). `answer` garde `step.answering` et `store.composerError`.
  - `outboundPayload` (L926) : ouvert par défaut via `store.closedPayloads` ; la carte de la Vue humain le veut replié par défaut, avec un état propre.
  - `renderChips` (L1100) : `is-linked` ; `renderSchema` (L1280) : `blocked` lit `store.turns.at(-1)`.
  - `NO_TURN_FR`/`CLEARED_FR` (L377).
- `src/wavestack/web/static/app.css` : `.harness-event` (L547), `.approval-actions` (L563), `.bubble-model` (L371). La carte du fil doit suivre la largeur des bulles.
- `_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md` L129, L166.
- Ne pas toucher : `session/app_session.py` (`clear_conversation` L1484 émet déjà `conversation_cleared` puis un `context_preview`), `web/app.py`, `trace/catalog.py`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/web/static/app.js` -- carte interactive dans `renderChat`, trace lecture seule dans `hookCard`, libellé de l'outil, puce liée, masquage des tours antérieurs au vidage dans Contexte LLM, Orchestration et schéma, textes de vidage -- AD-1
- [x] `src/wavestack/web/static/app.css` -- carte de validation dans le fil -- DESIGN.md harness-event
- [x] `EXPERIENCE.md` -- lignes 129 et 166 -- UX

**Acceptance Criteria:**
- Given H5 actif et une validation en attente, when l'utilisateur clique un bouton de la Vue humain pendant que le chronomètre tourne, then la réponse part au premier clic et Orchestration n'offre aucun bouton.
- Given deux tours puis « Vider la conversation », when on recharge la page, then Contexte LLM et Orchestration n'affichent aucun de ces tours et la liste des événements les contient toujours.

## Implementation Notes

- `renderChat` ne vide plus `#chat` : `patchChildren` remplace les enfants sans déplacer un nœud gardé ; les cartes H5 sont gardées par `approval_id` tant que leur clé (résolution, attente, réponse en cours, libellé) ne change pas. Focus restauré par `data-focus-key`, comme `renderBricks`. `answer()` ignore un second appel pendant une réponse en cours.
- Corps brut replié par défaut dans la Vue humain : `outboundPayload(request, openSet)`, état dans `store.openApprovalPayloads` ; la trace d'Orchestration garde `store.closedPayloads` (ouvert par défaut).
- Libellé MCP : « nom de l'outil (libellé du serveur) », par exemple « search (Wikipédia) » ; la trace d'Orchestration ajoute le nom brut entre parenthèses quand il diffère du libellé.
- Vidage : `store.clearedSeq` et `seq` sur chaque entrée `offTurn` ; `shownTurns()` sert à la Vue humain, à Contexte LLM, à Orchestration et au filet rouge du schéma.
- Vérification : pas de banc de test JS (même écart que les stories 5b à 8b). Les lignes de la matrice ont été vérifiées dans Chrome contre une API simulée qui rejoue des événements (hors dépôt) : attente, réponse à la souris et au clavier (un seul POST), rechargement en attente, puce liée, vidage, tour suivant, rechargement après vidage. Non vérifiés : réponse refusée (409) et filet rouge après vidage ; pas de tour réel avec un modèle.
- `uv run pytest` échoue sur ce poste (« uv trampoline failed to canonicalize script path ») : `uv run python -m pytest` passe (266 tests).

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 23 constats) :

- [BH2/EC1/VG-o1] Réponse au clavier : la carte est reconstruite avec des boutons désactivés, puis sans boutons ; `focus()` échoue et le focus tombe sur `body`. `medium`, confirmé (utilisateur au clavier qui perd sa place au moment de décider). -> P1 `patch` (carte focalisable, repli du focus sur la carte).
- [BH11] Puce « + Vue humain » marquée pendant l'attente, sans dire pourquoi. `low`, confirmé ; correction directe du titre. -> P2 `patch`.
- [BH8] « journal des événements » ne nomme aucune surface visible (la liste sous Orchestration n'a pas de titre) et se confond avec le « journal d'audit ». `low`, confirmé ; correction du texte. -> P3 `patch`.
- [VG1/VG2/VG3/BH14] Vidage (Contexte LLM, Orchestration, cartes MCP, schéma), carte H5 (clic unique, focus, trace sans bouton, libellé) et réponse refusée (409) sans aucun test automatique. Pré-vérifié : aucun banc de test JS. -> `defer`.
- [BH1] Boutons actifs sur une ancienne carte non résolue quand une autre validation attend. `false` : toute validation est résolue avant que le tour continue (`approved`, `refused`, `cancelled`, y compris par `close()`) et le flux reprend à `lastSeq` sans perte ; une seule `AppSession` par processus (`cli.py`), donc pas d'`approval_id` répété.
- [BH3] `focusKey` non échappé dans le sélecteur. `false` : les ids sont `{turn_id}.a{n}`, produits par le backend, sans guillemet ni crochet.
- [BH4] Cache `approvalCards` jamais remis à zéro quand le store est reconstruit. `false` : le store n'est jamais reconstruit ; une reconnexion reprend à `lastSeq`, un rechargement relance tout le script.
- [BH5] Sélection et ensembles de volets dépliés non purgés au vidage. `low`, rejeté : la sélection d'un tour (FR-4) n'est pas livrée ; la croissance des ensembles est négligeable.
- [BH6] Jauge incohérente après vidage. `false` : `clear_conversation` émet un `context_preview` de l'historique vide, que la jauge affiche.
- [BH7] Rejeu après vidage non défini. `false` pour ce code : le rejeu arrive en story 9.
- [BH9] DESIGN.md non mis à jour pour la carte déplacée. `low`, rejeté : la carte réutilise le composant `harness-event` déjà décrit ; le comportement est dans EXPERIENCE.md.
- [BH10] Couleur de la carte. `false` : `is-info` a la bordure `--color-primary`, le violet de charte.
- [BH12] `max-width: 85 %` dupliqué, `word-break: break-word` obsolète. `low`, rejeté : même valeur et même propriété que `.bubble`, cohérent avec l'existant.
- [BH13] `toolLabel` lève si `bricks_changed` n'a pas de `bricks`. `false` : `BricksChangedPayload.bricks` est obligatoire.
- [BH15] La ligne 129 d'EXPERIENCE.md ressemble à une note d'implémentation. `low`, rejeté : le renvoi à la story 10 est demandé par l'intention.
- [EC2] Focus sur un `summary` (aperçu, raisonnement) perdu au rafraîchissement. `low`, rejeté : la carte gardée n'est pas déplacée, son `summary` garde le focus ; les bulles étaient déjà reconstruites avant la story.
- [EC3] Mode focus sur un autre volet pendant l'attente : pas de puce. `low`, rejeté : cas rare, Échap sort du mode focus, la trace d'Orchestration renvoie à la Vue humain ; la correction ajoute une branche.
- [EC4] Connexion MCP commencée avant le vidage et finie après : carte masquée. `low`, rejeté : fenêtre de quelques secondes, le résultat reste dans la liste des événements ; la correction ajoute une condition.
- [EC5] Contexte LLM affiche « Conversation vidée » pendant la préparation du tour suivant. `low`, rejeté : transitoire (jusqu'au `context_rendered`) ; aucun texte de remplacement n'est plus juste.

Groupes routés en `patch` : P1 à P3 ; `defer` : VG1-VG3 ; aucun `intent_gap` ni `bad_spec`, pas de retour en arrière.

## Verification

**Commands:**
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur
- `uv run ruff check .` et `uv run pytest` -- expected: inchangés, tout passe (aucun fichier Python touché)

**Manual checks (if no CLI):**
- `uv run wavestack` : briques « Outils » (jours fériés) et « Hooks » avec H5 ; demander les jours fériés 2026 ; répondre depuis la Vue humain, au clavier puis à la souris ; recharger en attente ; masquer la Vue humain en attente ; « Vider la conversation » puis recharger.
