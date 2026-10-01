---
title: "E2E : options, cartes et interrupteurs de l'atelier"
type: 'chore'
created: '2026-10-01'
status: 'draft'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/tools/e2e/README.md'
warnings: []
deferred: []
---

<intent-contract>

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

</intent-contract>

## Verification

**Commands:**
- `uv run ruff check tools/e2e` -- expected: aucun écart.
- E2E (avec l'accord d'Anaël), tranches de 4 à 6 scénarios couvrant `mcp_full`, `mcp_lazy`, `skills`, `h5`, `forced_native`, `reasoning`, `programme` -- expected: 0 échec, contrôles ajoutés visibles dans le rapport.
