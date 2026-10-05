---
id: SPEC-lot-5-atelier-rag-2026-10-04
companions:
  - vues-atelier-rag.md
  - ../spec-langues/i18n-conventions.md
  - ../../planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
sources:
  - ../../implementation-artifacts/plan-corrections-2026-10-04.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Lot 5 du 2026-10-04 : Atelier RAG en deux pipelines

## Why

Retour d'Anaël du 2026-10-04 : l'Atelier RAG montre une seule chaîne linéaire de cartes, alors qu'un RAG se comprend en deux temps, l'indexation faite une fois pour toutes (build) puis la requête à chaque question (run), avec ses composants (données, modèles) sollicités tour à tour (schémas de formation `Images_Lot_5/RAG/`). Les explications en texte alourdissent les cartes, l'exécution ne se voit qu'en section 3, et composer une architecture connue (hybride, reranking) demande plusieurs gestes. Le lot 2 a livré `static/diagram.js` pour que les ateliers parlent la même langue visuelle ; ce lot l'applique au RAG. Il avance en parallèle des lots 3, 4 et 6 et doit se fusionner sans conflit difficile (ordre 3 → 4 → 5 → 6). La maquette v2 (`maquette-atelier-rag.html`), validée par Anaël le 2026-10-05, est la référence visuelle.

## Capabilities

- **CAP-1** Trois vues et mode Composer (story 5a-1)
  - **intent:** Le formateur voit la chaîne comme une séquence d'étapes BUILD puis RUN, à côté de l'architecture de ses composants et d'un focus sur une étape, et l'édite dans la séquence.
  - **success:** Sur `/rag` à 1 600 × 1 000, la section 1 montre la séquence (bandeaux BUILD · Indexing et RUN · Retrieval, 10 à 12 étapes), l'architecture (groupes Données, Modèles, Échange avec l'utilisateur, seules les tuiles sollicitées par la chaîne) et le focus, selon `vues-atelier-rag.md` ; en Composer, un clic sur une étape affiche son explication dans le focus et ses flèches vers ses composants ; options, réglages, ▲ ▼ Retirer, Ajouter et refus de la session marchent comme aujourd'hui ; plus de comparaison A/B ; vérifié par E2E.
- **CAP-2** Vocabulaire technique en anglais (story 5a-1)
  - **intent:** Le formateur lit des noms techniques cohérents, en anglais, dans les trois langues de la page.
  - **success:** Étapes, composants et `stages.*.label_text` portent les noms du §2 de `vues-atelier-rag.md` en fr, en et de ; aucun nom d'étape ne mêle les deux langues ; `RagLabContent` valide les clés `steps`, `components`, `groups`, `phases` dans les trois langues.
- **CAP-3** Mode Dérouler : apparition progressive et exécution en direct (story 5a-2)
  - **intent:** Le formateur fait arriver les étapes et les composants un à un, à la main ou au fil d'une exécution réelle, et voit quels composants l'étape en cours sollicite.
  - **success:** En Dérouler sans run, seule l'étape Documents et sa tuile sont visibles ; chaque ▶ ajoute l'étape suivante et les composants qu'elle sollicite pour la première fois ; pendant un run, l'étape atteinte s'allume avec ses composants, ses flèches sont animées et le focus montre ses entrée, sortie, chiffres et extraits ; ◀ ▶ rejouent ; après rechargement, le même état revient depuis `last_run` ; vérifié par E2E.
- **CAP-4** Architectures toutes faites (story 5b-1)
  - **intent:** Le formateur applique en un clic un RAG dense, un RAG hybride (BM25 + dense + fusion) ou un RAG avec reranking.
  - **success:** `GET /api/rag_lab` rend `catalog.presets` (trois entrées : id, textes, segment, disponibilité) ; un clic sur « RAG hybride » remplace le segment par Dense retrieval, BM25, Fusion (RRF) sans toucher le reste ; la chaîne est validée et s'exécute ; le bouton du préréglage courant est `aria-pressed="true"` ; testé en pytest et E2E.
- **CAP-5** Modèle par composant (stories 5c-1 à 5c-4, non implémentées dans ce lot)
  - **intent:** Le formateur choisit le modèle de chaque composant (embedding, reranker, LLM de génération), exécute la génération et télécharge un modèle absent depuis l'Atelier RAG.
  - **success:** Plusieurs embeddings et rerankers déclarés sont proposés ; la génération s'exécute avec le modèle actif et s'arrête par « Arrêter » ; un modèle absent se télécharge depuis l'étape (`download_model`) avec progression ; vérifié par pytest et E2E.

## Constraints

- AD-1 : tout chiffre, statut, disponibilité, préréglage et la table étape → composants viennent de la session (`/api/rag_lab`, événements `rag_lab_*`) ; la page ne calcule que la mise en page.
- Le backend garde une seule étape `embedding` (passages puis question) et ses événements : les étapes `embed_passages` et `embed_query` de la séquence en sont deux lectures.
- Backend du run inchangé (pipelines ≤ 2, `compare()`) : la page n'envoie qu'une chaîne ; le nettoyage de la voie B attend 5c (après la fusion du lot 3, `app_session.py`).
- `static/diagram.js` (partagé avec les lots 4 et 6) : ajouts seulement, nouvelles fonctions ou options à valeur par défaut ; ni signature ni comportement du schéma du harnais changés ; chaque ajout listé dans les Notes de fusion.
- Fichiers carrefour (`content/ui.yaml`, `content/messages.yaml` et leurs copies en/de, `pages.css`, `tokens.css`, `app.js`, `tools/e2e/run_e2e.py`, `tests/test_ui_texts.py`, `tests/test_web_app.py`, `src/wavestack/web/app.py`) : ajouts seulement, groupés en section RAG (`rag_lab.*`, `s_rag_*`/`_rag_*`) ; lignes hors RAG intouchées. Les clés `rag.*` de `ui.yaml` devenues inutiles (comparaison, chaîne B) restent, signalées pour un nettoyage après fusion.
- Fichiers interdits : `diagnostic.html`, `static/logos/`, `models/catalog.py`, `models/discovery.py`, `models/servers.py`, `content/models/`, `mcp.*`, `mcp/lab.py`, `content/mcp_lab.yaml`, `llm.*`, `llm_lab.py`, `content/llm_lab.yaml`, DESIGN.md, EXPERIENCE.md et `.memlog.md` des UX partagés. `app_session.py` : seulement si indispensable pour relayer `rag_lab_stage_*`, minimal et signalé.
- Textes nouveaux dans `content/rag_lab.yaml` et ses copies `content/i18n/{en,de}/`, validés par `RagLabContent` (mêmes clés dans les trois langues).
- Sélecteurs E2E de l'éditeur gardés : `li.rag-chain-card[data-kind][data-stage-id]`, `select.rag-option`, `input[data-param]`, `.rag-move-button[data-action]`, `.rag-chain-refusal`, `#rag-palette-a`, `#rag-reset-chain`, `#rag-run`, `#rag-question`, `.rag-stage-card` (dans `#rag-details`).
- États sans opacité (balayage de contraste AA de l'E2E, clair et sombre) ; couleurs par les tokens existants.
- Exécution : appli à la main sur le port 8425, sans changer le modèle ni les réglages du dossier de données partagé ; E2E `--only` RAG pendant le développement, une passe complète à la fin.

## Non-goals

- Aucune étape backend nouvelle ni découpage de l'étape `embedding` en deux.
- Pas de comparaison A/B dans la page (retirée à la demande d'Anaël).
- Pas de glisser-déposer : ▲ ▼ restent les seuls déplacements.
- 5c (choix du modèle par composant, génération exécutée, téléchargement) n'est pas implémenté dans ce lot.
- Pas de préréglage « hybride + reranking » : il se compose à la main.
- Pas de mise à jour de DESIGN.md / EXPERIENCE.md partagés : la décision UX vit dans `vues-atelier-rag.md`.
- Pas de fusion, rebase ni push sans demande d'Anaël.

## Success signal

- Sur `/rag` à 1 600 × 1 000, le formateur choisit « RAG hybride » en Composer, passe en Dérouler, lance la chaîne et voit les étapes BUILD puis RUN arriver une à une, chacune allumant ses composants (Chunks, Embedding model, Vector store…), le focus expliquer le Reranking ou la Fusion avec les vrais rangs, puis rejoue avec ◀ ; les E2E RAG et la suite pytest passent.

## Assumptions

- « Avec reranking » (plan, 5b) est la chaîne dense + reranking, celle livrée.
- Story Breakdown déroulé sans conversation (consigne d'enchaîner jusqu'au build) : checkpoints décidés par Claude, notés au memlog.

## Open Questions

- 5c : la génération exécutée dans l'Atelier RAG compte-t-elle dans la dépense (FinOps/GreenOps) de l'atelier principal, et avec quel prompt système ?
- 5c : quels rerankers et embeddings déclarer en plus (noms, tailles, licences) ?

## Notes de fusion

À compléter à la fin du build (fichiers carrefour touchés, ajouts à `diagram.js`, conflits probables avec les lots 3, 4 et 6).
