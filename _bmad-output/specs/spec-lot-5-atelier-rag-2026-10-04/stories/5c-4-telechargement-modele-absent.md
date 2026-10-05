---
title: 'Lot 5c-4 : téléchargement d''un modèle absent depuis l''Atelier RAG'
type: 'feature'
created: '2026-10-05'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '79423c5507261a2c654e7767e8fca10906ecb3e3'
context:
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-lot-5-atelier-rag-2026-10-04/stories/5c-3-generation-executee-par-le-modele-actif.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Un modèle d'embedding ou de reranking déclaré pour l'atelier (`[[rag_lab.embeddings]]`, `[[rag_lab.rerankers]]`) dont le fichier manque reste indisponible, et sa raison demande de le récupérer à la main ; les modèles de la brique ne se téléchargent que depuis la carte RAG de l'atelier principal.

**Approach:** Dans le mode Composer, l'étape Embedding (ou Reranking) propose « Télécharger (≈ N Mo) » pour chaque option dont les fichiers manquent (modèles de l'atelier et modèle de la brique). Le clic passe par `download_model` et ses événements (état `download`, progression dans `reason_text`, « Arrêter », `model_download`, `model_download_stopped`, `harness_error`) ; la place disque est vérifiée avant de commencer ; à la fin, l'étape dit le résultat et le catalogue relu rend l'option disponible.

**Décisions (prises par Claude, sans effet sur le contrat) :**
- Cibles nouvelles de `download_model` : `rag_lab_embedding:<id>` et `rag_lab_reranker:<id>` ; les cibles `rag_embedding` et `rag_reranker` sont réutilisées pour l'option `declared` de chaque étape.
- La vérification de place vaut pour tout `download_model`, carte RAG de l'atelier principal comprise : besoin = somme des tailles des fichiers manquants, sans marge ; disque illisible : pas de refus, le téléchargement dit l'erreur d'écriture s'il y en a une.
- Progression et messages de fin nomment le genre du modèle (« modèle d'embedding », « de reranking »), comme la carte ; la ligne de l'étape nomme le modèle.

## Boundaries & Constraints

**Always:**
- AD-1 : disponibilité, libellé et taille du bouton, progression, refus, issue viennent de la session (`catalog.stages[].options[].download`, `session_state`, événements) ; la page ne fait que les placer.
- Téléchargement d'un modèle de l'atelier tracé hors brique : portée `brick=None`, `context_id="rag_lab"`, composant `rag_lab.embedding` ou `rag_lab.rerank` (la carte RAG de l'atelier principal ne l'affiche pas). Ceux de la brique gardent leur portée (`rag`, `rag.retriever` / `rag.reranker`).
- sha256 déclaré vérifié par `download_files` ; aucun chargement en mémoire après le téléchargement (le run charge, avec le budget).
- Textes nouveaux en fr, en, de ; champ `download` du payload optionnel (`None` par défaut).
- Fichiers carrefour en ajouts seulement ; `web/app.py` : docstring de `DownloadModelIntention` seulement.

**Never:** nouvel endpoint ; téléchargement de fastembed ; télécharger depuis le mode Dérouler ou le focus ; toucher la carte RAG de l'atelier principal (`app.js`) ; reprise d'un `.part` ; changer les autres étapes ou le run.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Modèle de l'atelier absent | fichier manquant | option indisponible, raison « Cliquez sur Télécharger… », `download` = cible + « Télécharger (≈ 132 Mo) » | N/A |
| Téléchargement réussi | clic, `idle`, place suffisante | 200 ; `session_state` `download` avec progression ; `effect_applied` `model_download` (portée atelier) ; `idle` ; catalogue relu : option disponible, plus de `download` ; l'étape dit « Modèle téléchargé » | N/A |
| Place insuffisante | libre < besoin | 409, rien ne démarre, état `idle` | « Place insuffisante pour le modèle d'embedding : 640 Mo à télécharger, 200 Mo libres dans … » |
| Arrêter | « Arrêter » pendant le téléchargement | `model_download_stopped`, `.part` supprimé, option toujours indisponible, ligne neutre dans l'étape | N/A |
| Échec réseau / sha256 | serveur en erreur | `harness_error` portée atelier, `idle` | message, cause et copie à la main dans l'étape |
| Cible inconnue | `rag_lab_embedding:nope` | 404 | `web.unknown.download_target` |
| Session occupée | état ≠ `idle` | boutons désactivés avec la raison ; POST : 409 | raison de la session |
| Fichier déjà présent | copié à la main entre-temps | 409 « Rien à télécharger », catalogue relu | N/A |
| Modèle de la brique absent | option `declared` | bouton dans l'étape, cible `rag_embedding` / `rag_reranker` | N/A |
| Reranker présent mais refusé | en-tête GGUF refusé | aucun bouton, raison du refus | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/download.py` -- nouvelle `free_bytes(dest) -> int | None` : premier parent existant de `dest`, `shutil.disk_usage(...).free`, `None` sur `OSError` (les tests la remplacent par `monkeypatch`).
- `src/wavestack/session/app_session.py` -- `download_model` (l. 6165) : résoudre la cible (brique ou `rag_lab_*:<id>` via `self.cfg.rag_lab_embeddings[0]` / `rag_lab_rerankers[0]`, `KeyError` sinon), vérifier la place après `missing_files` et avant `_enter_rag_job` (`SendRefused(session.download.disk_full)`), passer la portée à `_run_download` (l. 6240 : paramètre `scope: dict` à la place de `component`, défaut brique). `_rag_lab_catalog` (l. 9174) : `OptionState.download` pour `("embedding","declared")` d'après `_rag_offers()["download"]` (l. 3126), pour `("rerank","declared")` d'après `(_rerank_card() or {}).get("download")` (l. 3336), pour chaque modèle de l'atelier absent (`missing_files`, taille arrondie en Mo comme `_rag_offers`, libellé `texts.download_label_text`). Commentaires « ne les télécharge pas encore » (l. ~9218, 9228) à mettre à jour. Garder `_rag_caught_up` après le téléchargement.
- `src/wavestack/rag/lab.py` -- `OptionState` (l. 415) + `download: dict[str, str] | None = None` ; `Catalog.payload` (l. 466) + `"download"` ; `RagLabContent` (l. 244) + `download_label_text`, `download_stop_text`, `download_done_text`.
- `src/wavestack/web/static/rag.js` -- `stageControls` (l. 255) : pour chaque option à `download`, une ligne `p.rag-chain-download` avec `button.rag-download[data-target]` (nom de l'option en `aria-label`), désactivé si `busyReason()` (raison en `title`) ; pendant le téléchargement lancé par la page (`store.download = {target, kind}`), la progression `store.session.reason_text` et `button.rag-download-stop` à sa place ; `store.downloadNotices[kind]` sous la ligne. `applyEnvelope` (l. 1065) : `effect_applied` (`model_download`, `model_download_stopped`) et `harness_error` sans tour dont le composant est `rag_lab.embedding|rag_lab.rerank|rag.retriever|rag.reranker`, pris seulement pendant `store.download` ; `session_state` passant de `download` à `idle` : relire le catalogue (`GET /api/rag_lab`, catalogue seul, puis `validateChains` et `redraw`). `renderBusy` (l. 1288) : `#rag-stop` actif aussi en `download`. `rag.css` : la ligne, sans opacité.
- `content/rag_lab.yaml` + `content/i18n/{en,de}/rag_lab.yaml` -- `download_label_text` (« Télécharger (≈ {size_mb} Mo) »), `download_stop_text`, `download_done_text`.
- `content/messages.yaml` ×3 -- `session.download.disk_full` (`noun`, `need`, `free`, `dest`) ; `session.rag_lab.lab_embedding_absent` / `lab_reranker_absent` : « cliquez sur Télécharger dans cette étape, ou placez-le à cet endroit » (plus de « pas encore »).
- `src/wavestack/web/app.py` -- docstring de `DownloadModelIntention` (l. 141) : les cibles de l'atelier.
- `wavestack.toml` -- commentaires « L'atelier ne les télécharge pas encore » (l. ~148, ~190).
- Tests -- `tests/test_rag_download.py` (fixtures `Server`, `download_session`, `wait_download`, `MockTransport`) à imiter dans un nouveau `tests/test_rag_lab_download.py` ; catalogue de 5c-1/5c-2 dans `tests/test_rag_lab_embeddings.py`, `tests/test_rag_lab_rerankers.py`.
- E2E -- `tools/e2e/run_e2e.py` l. 13553-13570 (`_rag_lab`, modèles de l'atelier indisponibles) : bouton visible, clic, état `download`, « Arrêter » de l'étape ; issue `model_download_stopped` ou `harness_error` (hors ligne) de composant `rag_lab.embedding`, dite dans l'étape, bouton de nouveau actif. Aucun vrai téléchargement complet.
- Docs -- `docs/guide.md` l. 294, 331 (Atelier RAG).

## Tasks & Acceptance

**Execution:**
- [x] `models/download.py` -- `free_bytes`.
- [x] `app_session.py` -- cibles, place disque, portée, `OptionState.download` dans le catalogue.
- [x] `rag/lab.py` -- `OptionState.download`, payload, textes de `RagLabContent`.
- [x] contenus ×3 (`rag_lab.yaml`, `messages.yaml`), `wavestack.toml`, `web/app.py` docstring.
- [x] `rag.js`, `rag.css` -- bouton, progression, arrêt, issue, catalogue relu.
- [x] `tests/test_rag_lab_download.py` -- la matrice entière (embedding et reranker de l'atelier, brique, place, arrêt, échec, cible inconnue, route 404/409, `free_bytes`) ; E2E ; `docs/guide.md`.
- [x] Fin de lot : pytest complet, E2E complet ; `SPEC.md` (CAP-5, Non-goals, Notes de fusion de 5c) ; entrée de `deferred-work.md`.

**Acceptance Criteria:**
- Given un modèle de l'atelier absent et la place suffisante, when on clique « Télécharger » dans son étape, then le fichier arrive sous `models/`, aucun événement du téléchargement ne porte `brick="rag"`, et l'option devient disponible sans recharger la page.
- Given la langue en ou de, when on lit le bouton, la progression, le refus de place et l'issue, then ils sont traduits.
- Given `uv run ruff check .` et `uv run pytest` complet, when on les lance, then tout est vert ; les E2E (passe complète) passent.

## Implementation Notes

- `download_model` passe par `_download_target` (modèle, nom du genre, portée) : `rag_lab_embedding:<id>` / `rag_lab_reranker:<id>` lus par `cfg.rag_lab_embedding` / `rag_lab_reranker` (id inconnu, vide ou d'un autre genre : `KeyError`, 404), portée `_rag_lab_scope("rag_lab", "rag_lab.embedding" | "rag_lab.rerank", brick=None)` ; les cibles de la brique gardent `{"brick": "rag", "component": …}` et n'exigent plus rien de neuf. Place : `free_bytes(dest)` après `missing_files`, refus `session.download.disk_full` (besoin arrondi au Mo, au moins 1 ; libre tronqué au Mo), `None` : pas de refus.
- `_run_download(…, scope=…)` : `scoped(**scope, origin="download")` pendant, `scoped(**scope)` pour l'issue. Les fichiers sont relus (`_rag_refresh`) avant `idle`, pour que le catalogue relu par la page à ce moment n'offre plus le « Télécharger » de la brique ; `_rag_caught_up` reste après.
- Catalogue : `OptionState.download` (payload `download`, `None` par défaut) ; brique : `_rag_offers()["download"]` et `_rerank_card()["download"]` tels quels (cible et libellé de la carte) ; modèles de l'atelier : `_rag_lab_download` (« Télécharger (≈ N Mo) » de `rag_lab.yaml`). Un reranker présent mais refusé n'a pas de fichier manquant, donc pas de bouton.
- `rag.js` : `div.rag-chain-downloads[data-kind]` dans la ligne de l'étape (Composer), une `p.rag-chain-download[data-target]` par option à `download`, visible sur la ligne choisie ou pendant son téléchargement ; progression `session_state.reason_text` et `button.rag-download-stop` (POST `stop`) à la place du bouton ; issue `p.rag-chain-download-notice` (`is-error` pour un échec ou un refus). Lignes redessinées en place à chaque `session_state` (focus gardé sur la même cible) ; passage de `download` à un autre état : `store.download` oublié, catalogue relu (`reloadCatalog`). Un refus du POST (409, 404, réseau) est dit dans l'étape et relit le catalogue. `#rag-stop` actif en `download`.
- Textes : `rag_lab.yaml` ×3 (`download_label_text`, `download_stop_text`, `download_done_text`), `messages.yaml` ×3 (`session.download.disk_full`, `lab_embedding_absent`, `lab_reranker_absent`). Docs : `guide.md` (puce « Télécharger un modèle absent »), `installation.md` (phrase « ne les télécharge pas encore » périmée, hors Code Map).
- Tests : `tests/test_rag_lab_download.py` (19 cas). E2E : `_rag_lab_download` (Qwen3-Embedding, 639 Mo : jamais fini, la pile est hors ligne). `--only rag_lab` seul échoue avant 5c-4 aussi (il suppose `rag` et `rag_rerank` joués avant) : lancé avec `--only rag rag_rerank rag_lab`, 140 vérifications PASS ; navigateur `--channel msedge` (pas de Chromium de Playwright sur ce poste).
- Fin de lot : `pytest` complet 5 956 passés, 1 échec antérieur (`test_readme_is_a_short_onboarding_page`, rouge aussi sur `79423c5`). E2E complet : 1 094 PASS, 6 FAIL, les mêmes 6 que la passe de référence sur `79423c5` (1 092 PASS) : `mcp_full` (arbres JSON en mode cloud), `annex_language` et `backend_language` (textes français du journal sur `/diagnostic` en en/de, « Augmented prompt » sur `/rag` en de pris pour un texte de `messages.yaml`). `test_ui_texts` lit toute chaîne `"rag.…"` de `rag.js` comme une clé d'`ui.yaml` : les composants `rag.retriever` / `rag.reranker` sont construits par morceaux.

## Spec Change Log

## Review Triage Log

Passe 1, 2026-10-05.

| # | Source | Constat | Verdict | Preuve | Suite |
| --- | --- | --- | --- | --- | --- |
| 1 | verif | relecture des fichiers avant `idle` (`_rag_refresh`) épinglée par aucun test | medium | `wait_download` attend 50 ms : `_rag_caught_up` rafraîchit aussi, le test passe sans le bloc | patch (test qui lit le catalogue avec `_rag_caught_up` neutralisé) |
| 2 | verif | E2E : progression et « Arrêter » de l'étape jamais vus ; l'issue « échec » couvre un arrêt cassé | medium | `stop.click` dans `suppress(PlaywrightTimeout)`, `outcome()` accepte `harness_error` | patch (visibles en état `download` ; arrêt cliqué ⇒ `model_download_stopped`) |
| 3 | verif | `#rag-stop` actif en `download` sans test | low | aucun `rag-stop` dans `tests/` ni `run_e2e.py` | patch (une assertion dans la même fenêtre) |
| 4 | verif, blind | refus du POST (place, déjà présent) et réussite jamais montrés dans l'étape par un test ; étape Reranking et option `declared` non parcourues en E2E | medium | pile E2E hors ligne ; seul le chemin accepté est joué | defer (fichier de taille déclarée ou petit modèle servi localement à prévoir dans l'E2E) |
| 5 | blind, edge | refus de place contradictoire (« 640 Mo à télécharger, 640 Mo libres ») : besoin arrondi, libre tronqué | low | `round(total/1e6)` contre `free // 1e6` | patch (besoin arrondi au Mo supérieur) |
| 6 | blind | pas de marge de place ; vérification faite une fois | false | décision du bloc figé : « sans marge » | rejeté |
| 7 | blind, edge | `_rag_refresh` deux fois, exception avalée | low | le second appel (`_rag_caught_up`) relit et laisse remonter une erreur ; coût d'une relecture négligeable | rejeté |
| 8 | blind | `missing_files` deux fois par modèle et par catalogue | low | quelques `stat` de plus, invisibles | rejeté |
| 9 | blind | raison « Cliquez sur « Télécharger » dans cette étape » montrée aussi hors Composer (`unavailable_text` du run, focus) | low | `_rag_lab_absent` repris l. 9746, 9940 | patch (texte ×3 : « en mode Composer ») |
| 10 | blind | issue sans `role="status"` ; zone de progression recréée chaque seconde | low | `fillDownloads` : `replaceChildren` | patch (rôle de l'issue) ; recréation rejetée (restructuration) |
| 11 | blind | issue affichée sur les lignes non choisies, jamais effacée | low | CSS ne cache que `.rag-chain-download` hors `.is-selected` | patch (issue cachée hors ligne choisie, comme les raisons) |
| 12 | blind | libellés différents (brique / atelier) dans la même étape | low | libellé de la carte repris tel quel, nomme le genre | rejeté |
| 13 | blind | tests : textes d'issue en/de non vérifiés ; raison « occupée » seulement non vide | low | textes d'issue antérieurs (stories 15-16) déjà traduits | rejeté |
| 14 | blind | progression d'un modèle de l'atelier montrée sur la carte principale comme celle de la brique | low | décision « nom du genre » du bloc figé ; entrée déjà dans `deferred-work.md` | rejeté |
| 15 | blind | story : Code Map (`[0]`, `installation.md`) et « carrefour en ajouts » non suivis | false | `app_session.py` n'est pas un carrefour ; écart d'écriture du plan, sans effet | rejeté |
| 16 | blind | `SPEC.md` : Non-goals, « livrées » avant le commit, captures 55-59 « régénérées » absentes du diff | false | captures 55-59 modifiées dans l'arbre (diff filtré) ; « livrées » vrai au commit | rejeté |
| 17 | blind | docs : place disque non dite pour la carte principale ; paragraphes non repliés | low | `guide.md` l. 130, 180 ; lignes > 95 colonnes | patch |
| 18 | blind | `wavestack.toml` (rerankers) sans « adresse déclarée, sha256 » ; allemand « MB herunterzuladen » | low | commentaires et texte | patch |
| 19 | edge | dossier `embedding/` en jonction vers un autre volume : mauvais disque mesuré | low | cas rare, correctif à branches | rejeté |
| 20 | edge | POST en échec réseau alors que le téléchargement a démarré | low | serveur local ; le passage à `idle` relit le catalogue de toute façon | rejeté |
| 21 | edge | focus repris plus tard après un clic ailleurs | low | fenêtre de quelques ms entre clic et état `download` | rejeté |
| 22 | edge | focus perdu si l'étape n'a qu'une option (pas de `select`) | low | l'étape Reranking a ses rerankers déclarés | rejeté |
| 23 | edge | E2E sur un poste à moins de 639 Mo libres : délai dépassé | low | poste de développement | rejeté |
| 24 | edge | sqlite-vec inutilisable ou contenu invalide : pas de bouton pour le modèle de la brique | low | même règle que la carte (`_rag_offers`) ; cas rare | rejeté |

- Revue 1 : besoin arrondi au Mo supérieur (`math.ceil`, libre tronqué : jamais « 640 Mo à télécharger, 640 Mo libres ») ; test du relu avant `idle` (`_rag_caught_up` remplacé) ; E2E : progression, « Arrêter » de l'étape et `#rag-stop` vérifiés pendant `download`, arrêt cliqué ⇒ `model_download_stopped` exigé ; raisons « dans cette étape en mode Composer » (en « Compose », de « Zusammenstellen », les noms des boutons de mode) ; issue en `role="status"`, masquée hors ligne choisie ; place disque dite aussi pour la carte RAG dans `guide.md`, paragraphes rewrappés.

## Design Notes

- La page ne connaît la cible en cours que pour un téléchargement qu'elle a lancé (`store.download`) ; après un rechargement en plein téléchargement, la progression reste visible dans `#rag-busy` et `#rag-stop` l'arrête : pas de champ nouveau dans `session_state`.
- L'issue n'est prise que pendant `store.download`, pour qu'un échec de chargement du modèle de la brique (même composant `rag.retriever`) ne s'affiche pas dans l'étape.

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q tests/test_rag_lab_download.py tests/test_rag_download.py tests/test_rag_rerank.py tests/test_rag_lab.py tests/test_rag_lab_embeddings.py tests/test_rag_lab_rerankers.py tests/test_i18n.py tests/test_ui_texts.py` -- expected: vert
- `uv run pytest -q` puis `uv run python tools/e2e/run_e2e.py` (passe complète) -- expected: vert (fin de lot)
