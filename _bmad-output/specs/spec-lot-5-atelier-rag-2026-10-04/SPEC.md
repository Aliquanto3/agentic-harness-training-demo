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

## Décisions de 5c (Anaël, 2026-10-05)

- Modèles déclarés en plus : voir `essai-modeles-5c.md` (embeddings multilingual-e5-small et Qwen3-Embedding-0.6B, reranker Qwen3-Reranker-0.6B), livrés par 5c-1 et 5c-2.
- 5c-3, génération exécutée dans l'Atelier RAG :
  1. **Dépense** : comptée dans la dépense de la session (FinOps/GreenOps, `consumption_updated`), comme l'Atelier LLM ; jamais dans la jauge d'un tour (aucun tour).
  2. **Prompt système** : le prompt système effectif de l'atelier principal, tel qu'un tour l'enverrait (rien si la brique « prompt système » est éteinte), puis le contexte construit par la chaîne avec son introduction, puis la question ; le focus montre le prompt envoyé.
  3. **Au choix** : une option sur la ligne Generation, « Modèle actif de l'atelier » (par défaut, exécutée) ou « Ne pas générer » (le comportement d'avant).
  4. **Bornes** : celles de l'atelier principal (borne de sortie, budget de raisonnement) ; progression en tokens et « Arrêter » pour la lenteur.
  5. **Cas limites** : sans modèle chargé, l'étape est sautée avec sa raison et le reste de la chaîne se termine ; le cache de préfixe de la conversation de l'atelier est écrasé, ce qu'on accepte, en ajoutant la cause « atelier RAG » à la ligne « Préfixe non réutilisé ».

## Notes de fusion

Branche `feat/lot-5-atelier-rag-2026-10-04`, base `370bb36` (lot 2), commits « lot 5a » puis « lot 5b ».

**Ajouts à `static/diagram.js` : aucun.** Le lot n'importe que `block`, `light`, `wire`, `wireLayer` et `createStepper`, sans en changer ni signature ni comportement. `explain` n'est plus utilisé par le RAG.

**`app_session.py` : non modifié.** Le catalogue (étapes, composants, préréglages) est produit par `Catalog.payload()` dans `rag/lab.py`, rendu tel quel par `rag_lab_state`.

**Fichiers carrefour touchés**

| Fichier | Nature | Zone |
| --- | --- | --- |
| `tools/e2e/run_e2e.py` | réécriture et ajouts dans les fonctions RAG seulement | de `# ---------- story 30: the RAG workshop` (≈ l. 11686) jusqu'à `RAG_LAB_STAGES_KINDS` (≈ l. 12880) ; liste `SCENARIOS` inchangée |
| `tests/test_i18n.py` | ajout de 26 lignes dans la branche `rel == "rag_lab.yaml"` | entre la branche `llm_lab.yaml` et la branche `mcp_lab.yaml` de `test_translated_file_mirrors_the_french_one` |
| `_bmad-output/implementation-artifacts/deferred-work.md` | 4 entrées ajoutées en fin de fichier | fin de fichier |
| `docs/guide.md` | section « Atelier RAG » réécrite (puces) | l. 268-322, titres inchangés |

Non touchés : `content/ui.yaml`, `content/messages.yaml` et leurs copies en/de, `pages.css`, `tokens.css`, `app.js`, `tests/test_ui_texts.py`, `tests/test_web_app.py`, `src/wavestack/web/app.py`, `diagram.js`, `app_session.py`, et tous les fichiers des lots 3, 4 et 6.

Fichiers propres au RAG modifiés : `rag.html`, `rag.js`, `rag.css`, `rag/lab.py`, `content/rag_lab.yaml` et `content/i18n/{en,de}/rag_lab.yaml`, `tests/test_rag_lab.py`, `tests/test_rag_lab_alt.py`, captures `55` à `59-atelier-rag-*.jpg` (`57-atelier-rag-comparaison.jpg` supprimée, remplacée par `57-atelier-rag-composer.jpg`), `annex-language-de-rag-{1280,1600}.jpg`.

**Conflits probables**

- **Lot 3 (Diagnostic et modèles)** : `run_e2e.py`, ses scénarios (`s_diagnostic`, `s_model_catalog`, `_models_*`) sont loin de la zone RAG, donc pas de conflit textuel attendu. Si le lot 3 régénère les captures `annex-language-de-rag-*.jpg` ou corrige `s_annex_language`, garder les captures de ce lot (la page /rag a changé). `test_readme_is_a_short_onboarding_page` est rouge avant ce lot (README à 121 lignes) ; le lot 3 ou une correction à part le solde. 5c attend la fusion du lot 3 (`app_session.py`, `_rag_lab_catalog`).
- **Lot 4 (Atelier MCP)** : `test_i18n.py`, si le lot 4 modifie la branche `mcp_lab.yaml`, juste après l'ajout RAG, conflit de voisinage : garder les deux. `diagram.js` : les ajouts du lot 4 n'interagissent pas avec le RAG (aucun appel modifié). `deferred-work.md` : conflit d'ajouts en fin de fichier, garder toutes les entrées.
- **Lot 6 (Atelier LLM)** : `run_e2e.py`, `s_llm_live` se termine juste avant le bloc `# ---------- story 30: the RAG workshop` ; un ajout du lot 6 en fin de `s_llm_live` touche la frontière, garder les deux blocs. `test_i18n.py` : la branche `llm_lab.yaml` précède immédiatement l'ajout RAG, même règle. `docs/guide.md` : section « Atelier LLM » distincte de « Atelier RAG ».
- **Après fusion** (registre `deferred-work.md`) : retirer les clés orphelines `rag.chain_a`, `rag.chain_b`, `rag.chain_b_steps`, `rag.chain_steps`, `rag.comparison.*` d'`ui.yaml` ; passer au vocabulaire chunk / prompt les refus `rag_lab.check.*` et les comptes `rag_lab.noun` de `messages.yaml` ; mettre à jour les lignes `rag-screen`, `rag-chain` et `rag-stage-card` d'EXPERIENCE.md d'après `vues-atelier-rag.md`.
