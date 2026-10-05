---
title: 'B1 (plan du 2026-10-05) : Atelier RAG, le bouton « Télécharger » des modèles visible sans sélectionner l''étape'
type: 'bugfix'
created: '2026-10-05'
status: 'done'
baseline_commit: 'd239b094e8b10bebdae0f13d878532dea1626d34'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/stories/5c-4-telechargement-modele-absent.md'
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/vues-atelier-rag.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les boutons « Télécharger (≈ N Mo) » des modèles absents de l'Atelier RAG (lot 5c-4) existent dans le DOM mais `rag.css` les masque tant que la ligne de l'étape n'est pas sélectionnée, en mode Composer seulement, alors que la page s'ouvre en Dérouler : Anaël ne les a pas trouvés.

**Approach (correctif validé par Anaël) :** (1) en Composer, les lignes « Télécharger » (et leur issue) des étapes Embedding et Reranking sont toujours visibles, sans clic ; (2) dans la colonne ARCHITECTURE, sur les tuiles « Embedding model » et « Reranker », dans les deux modes, une mention « N modèle(s) à télécharger » qui, au clic, passe en Composer et sélectionne l'étape ; sans étape Reranking dans la chaîne, l'architecture le dit (« ajoutez l'étape Reranking pour le télécharger ») ; (3) README.md (« Modèles du RAG ») et `docs/installation.md#modèles-du-rag` décrivent l'emplacement exact. Textes fr/en/de ; E2E RAG.

**Décisions prises par Claude (Anaël injoignable, option recommandée) :**
- Le compte N vient de la session (AD-1) : champ `download_count` de chaque étape du catalogue (options qui ont `download`).
- Sans étape Reranking, la phrase est un bouton au pied du groupe MODELS de l'architecture (la tuile Reranker n'existe pas) ; son clic passe en Composer et présélectionne Reranking dans « Ajouter un composant ».
- Les raisons d'indisponibilité (`.rag-chain-unavailable`) restent sur la ligne choisie : la ligne « Télécharger » nomme déjà le modèle, la séquence reste compacte.
- Le clic sur la mention donne le focus au premier bouton « Télécharger » de l'étape et l'amène à l'écran.

## Boundaries & Constraints

**Always:** AD-1 (compte, cibles, libellés de la session ; la page place) ; textes nouveaux dans `content/ui.yaml` section `rag` (pluriel `one`/`other`) et ses surcouches en/de ; la mention ne télécharge rien (le mode Dérouler et le focus ne téléchargent toujours pas).

**Never:** changer `download_model`, ses événements ou la carte RAG de l'atelier principal ; toucher `app_session.py` hors partie rag_lab (rien à y changer ici) ; montrer une mention quand N = 0.

## I/O & Edge-Case Matrix

| Scénario | État | Attendu |
|---|---|---|
| Composer, aucune ligne choisie | modèles absents | lignes « Télécharger » visibles dans Embedding et Reranking |
| Dérouler, tuile révélée | 2 modèles d'embedding absents | « 2 modèles à télécharger » sur la tuile ; clic : Composer, ligne Embedding choisie, focus sur son premier « Télécharger » |
| Tuile Reranker | 1 absent | « 1 modèle à télécharger » |
| Chaîne sans Reranking | reranker absent | au pied de MODELS : « Reranker : 1 modèle à télécharger ; ajoutez l'étape Reranking pour le télécharger » ; clic : Composer, Reranking présélectionné dans « Ajouter » |
| Tout présent | N = 0 | aucune mention |
| Téléchargement fini | catalogue relu | mention recomptée ou retirée |

</frozen-after-approval>

## Code Map

- `src/wavestack/rag/lab.py` -- `Catalog.payload` (~l.466) : ajouter `"download_count"` à chaque étape (options du payload dont `download` n'est pas `None`).
- `src/wavestack/web/static/rag.css` -- règles ~l.347-350 (`.rag-seq-step:not(.is-selected) .rag-chain-download:not(.is-active)`, notice) à retirer ; commentaire ~l.323 à corriger ; styles de la mention (`.rag-arch-download`, bouton discret sous le sous-titre, grille de la tuile `grid-column: 2`) et de la phrase du groupe (`.rag-arch-download-hint`), sans opacité (balayage AA).
- `src/wavestack/web/static/rag.js` -- `renderArchitecture` (~l.758) : pour une tuile dont `component.stage` a `download_count > 0`, `button.rag-arch-download[data-stage]` ; pour un composant du groupe non utilisé dont l'étape est `movable` avec `download_count > 0`, `button.rag-arch-download-hint`. Clic : `setMode("compose")`, puis `select(clé de l'étape propre : catalog.steps.find(s => s.own && s.stage === kind).key)`, `scrollIntoView` + focus sur `.rag-download` ; hint : palette `#rag-palette-a select` à la valeur du kind, focus sur `.rag-palette-add`. `setMode` met `current` à null : sélectionner après.
- `content/ui.yaml`, `content/i18n/{en,de}/ui.yaml` -- section `rag` : `arch_downloads` (one/other), `arch_downloads_title`, `arch_downloads_add` (one/other ; `{component}`, `{count}`, `{stage}`).
- `README.md` l.67-71, `docs/installation.md` l.183-191, `docs/guide.md` l.358-367 -- emplacement exact : page `/rag`, mention sur la tuile, mode Composer, ligne de l'étape.
- `tests/test_rag_lab_download.py` -- `download_count` du catalogue.
- `tools/e2e/run_e2e.py` -- `_rag_lab_download` (~l.13466) : bouton visible avant tout clic sur la ligne ; `_rag_lab` (~l.13548) : mentions des tuiles (textes et comptes égaux au catalogue), clic en Dérouler.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/rag/lab.py` -- `download_count` par étape -- AD-1.
- [x] `content/ui.yaml` ×3 -- textes de la mention et de la phrase.
- [x] `rag.css`, `rag.js` -- lignes toujours visibles ; mention et phrase, clic.
- [x] `tests/test_rag_lab_download.py` -- compte du catalogue.
- [x] `README.md`, `docs/installation.md`, `docs/guide.md` -- emplacement.
- [x] `tools/e2e/run_e2e.py` -- visibilité sans clic, mentions, clic depuis Dérouler, phrase sans Reranking (préréglage « RAG dense »).

**Acceptance Criteria:**
- Given `/rag` ouvert en Dérouler sur la chaîne livrée, when on clique la mention de la tuile Embedding model, then le mode est Composer, la ligne Embedding est choisie et son bouton « Télécharger » a le focus.
- Given la langue en ou de, when on lit la mention et la phrase, then elles sont traduites avec le bon pluriel.
- Given `uv run ruff check` et les tests concernés, when on les lance, then tout est vert ; l'E2E `rag rag_rerank rag_lab` passe.

## Implementation Notes

- Mode autonome (Anaël injoignable) : CHECKPOINT 1 « Approve and continue » pris à sa place ; implémentation faite directement dans la session (pas de sous-agent d'implémentation : machine partagée, 16 Go, deux autres agents en parallèle), revue à trois relecteurs en sous-agents.
- `Catalog.payload` : `download_count` par étape. `rag.js` : `downloadCount`, `downloadMention` (nom accessible « Embedding model : 2 modèles à télécharger »), `downloadHint`, `openDownloads` (focus : premier « Télécharger » actif, sinon le choix d'option, sinon la tête de ligne). `rag.css` : règle qui masquait lignes et issue hors ligne choisie retirée ; `.rag-arch-download` (flèche ⬇ hors nom accessible), `.rag-arch-download-hint`.
- Textes : `ui.yaml` ×3 (`rag.arch_downloads`, `arch_downloads_title`, `arch_downloads_add`). Docs : README, `installation.md`, `guide.md`, `vues-atelier-rag.md` §4 et §7.
- Tests : `test_each_stage_counts_its_models_to_download`, `test_a_downloaded_model_is_no_longer_counted`. E2E : `_rag_lab_arch_downloads` (visibilité sans clic, comptes, clic depuis Dérouler), phrase « ajoutez l'étape Reranking » dans `_rag_lab_presets` (« RAG dense »), issue visible sans ligne choisie dans `_rag_lab_download`.
- Vérifié : `pytest tests/test_rag_lab_download.py tests/test_rag_lab.py tests/test_ui_texts.py tests/test_i18n.py` 279 passés ; après revue, `test_rag_lab_download.py` + `test_ui_texts.py` 62 passés ; E2E `--only rag rag_rerank rag_lab --channel msedge` : 145 vérifications, 0 échec. Captures régénérées : 55 à 59 seulement (atelier RAG).

## Spec Change Log

## Review Triage Log

Passe 1, 2026-10-05.

| # | Source | Constat | Verdict | Preuve | Suite |
| --- | --- | --- | --- | --- | --- |
| 1 | blind, edge, verif | `installation.md` : « 2 modèles », « 1 modèle », « nombre de fichiers manquants » figés ; le modèle de la brique compte aussi | low | `download_count` compte les options à `download`, brique comprise (test : 2 et 2) | patch (« N modèles », brique comprise) |
| 2 | blind | ligne de `installation.md` non repliée | low | l.189 > 95 colonnes | patch |
| 3 | blind | mention sans nom accessible distinct ; ⬇ lu ; phrase sans infobulle | low | deux tuiles « 1 modèle à télécharger » possibles | patch (`aria-label` avec le composant, `content: "⬇ " / ""`, `title`) |
| 4 | blind | focus clavier perdu quand l'architecture est redessinée | low | `renderArchitecture` reconstruit ; cas rare (clavier sur la mention à la fin d'un téléchargement) | rejeté (restauration du focus à ajouter, complexité) |
| 5 | blind | compte inchangé pendant le téléchargement | low | le modèle reste absent tant qu'il n'est pas fini : le compte est juste | rejeté |
| 6 | blind, verif | tests manquants : clic Reranker, repli du focus, recompte après téléchargement, en/de rendus | low | recompte couvert en pytest ; pluriels en/de par `test_ui_texts` ; repli : voir 13 | rejeté (sauf 13) |
| 7 | blind, edge | E2E : tuile jamais révélée → délai Playwright au lieu d'un échec clair | low | boucle `range(12)` sans contrôle | patch (`r.check` puis retour) |
| 8 | blind | `SPEC.md` du lot 5 : « pas de téléchargement depuis Dérouler » | false | la mention ne télécharge pas : elle passe en Composer | rejeté |
| 9 | blind | `wavestack.toml`, `messages.yaml` ne parlent pas de la tuile | low | ils disent l'endroit exact du bouton, toujours vrai | rejeté |
| 10 | blind | README : cas sans Reranking absent, « N » pour deux nombres | low | paragraphe | patch |
| 11 | blind | phrase maladroite de `vues-atelier-rag.md` §7 | low | « lignes » répété | patch |
| 12 | edge | étape à une seule option, boutons désactivés : rien à focaliser | low | Reranking sans reranker déclaré n'a pas de `select` | patch (repli sur la tête de ligne) |
| 13 | verif | repli du focus (`select.rag-option`) jamais joué | medium | E2E au repos seulement | defer (`deferred-work.md`) |
| 14 | verif | issue de téléchargement : visibilité non vérifiée sans ligne choisie | medium | `to_contain_text` passe sur un élément masqué | patch (`to_be_visible`, aucune ligne choisie) |
| 15 | edge | pas d'étape propre pour le kind | false | `test_every_step_names_a_stage_of_the_chain_or_none` : une ligne propre par kind | rejeté |
| 16 | edge | palette sans l'option du kind | false | phrase montrée seulement si le composant n'est pas utilisé, donc l'étape absente, donc dans la palette | rejeté |
| 17 | edge | groupe sans tuile mais avec phrase | false | le groupe Modèles a toujours LLM (Generation fixe) | rejeté |
| 18 | edge | sélection héritée avant le premier contrôle E2E | false | `setMode("compose")` remet `current` à null ; contrôle passé | rejeté |
| 19 | edge | docstring de `_rag_lab_download` périmée | low | « (selected) » | patch |

## Verification

**Commands:**
- `uv run ruff check src tests tools && uv run ruff format --check src tests tools` -- expected: aucun écart
- `uv run pytest -q tests/test_rag_lab_download.py tests/test_rag_lab.py tests/test_ui_texts.py tests/test_i18n.py` -- expected: vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only rag rag_rerank rag_lab` -- expected: aucun FAIL
