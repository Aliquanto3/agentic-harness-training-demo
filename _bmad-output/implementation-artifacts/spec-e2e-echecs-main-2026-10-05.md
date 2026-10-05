---
title: 'Échecs E2E de main du 2026-10-05 : arbres JSON des outils, historique des erreurs, faux positif « Augmented prompt »'
type: 'bugfix'
created: '2026-10-05'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La passe E2E complète de `main` (5713d78) donne 6 échecs, tous dus au vérificateur (`tools/e2e/run_e2e.py`), aucun au produit :

1. `mcp_full`, « mode cloud : les descriptions d'outils, MCP compris, en arbres JSON » : depuis le lot 1 du 2026-10-04 (805c71c, décision d'Anaël, BH13 « repli par défaut voulu »), un arbre JSON du Contexte LLM n'ouvre que sa racine (`jsonNode`, `src/wavestack/web/static/app.js:4240`). Le nom d'outil (`function.name`) est dans un `details` replié ; `all_inner_texts()` rend `""` pour un texte non rendu, d'où `['"function"', '', '', …]`. La vérification n'a pas suivi la décision.
2. `annex_language` et `backend_language`, « en/de : /diagnostic sans texte français » (passe complète seulement) : `/diagnostic` rejoue les `harness_error` du journal comme historique (`renderHarnessError(payload, live=false)`, `diagnostic.html:454`, ligne « — {message_text} » et cause en `div.action`). Les erreurs du faux fournisseur (`provider_errors`) et le 503 du reranker (`rag_rerank`, `_rerank_download_fails`) ont été émises en français avant le changement de langue. `_history_strings` (`run_e2e.py:8689`) ne met de côté que `model_load_*` et `diagnostic_check`, alors que la règle langues 5/5 excepte tout l'historique que les pages rejouent depuis le journal.
3. `annex_language`, « de : /rag sans texte français » : `_value_patterns` (`run_e2e.py:8637`) transforme `{n}` de `messages:session.mcp_lab.summary.prompts.one` (« {n} prompt ») en `.+?`, qui reconnaît la tuile « Augmented prompt », valeur `de` exacte de `rag_lab.yaml:augmented_prompt.label_text`.

**Approach:** Corriger le seul vérificateur : (1) lire les chaînes de l'arbre par `all_text_contents()` (texte du DOM, nœuds repliés compris), la racine restant repliée sous ses clés ; (2) ajouter `harness_error` aux événements rejoués comme historique dans `_history_strings` ; (3) ne pas signaler un texte qui est exactement une valeur littérale (sans variable) du catalogue traduit, dans `_french_left` et `_annex_french_left`.

## Boundaries & Constraints

**Always:** le produit ne change pas (`app.js`, `diagnostic.html` intacts) ; la mise de côté de l'historique reste limitée aux événements émis avant le dernier `language_changed` et aux genres que les pages rejouent comme historique.

**Never:** ne pas déplier d'office l'arbre JSON (décision du lot 1) ; ne pas élargir la mise de côté à tout texte émis avant le changement de langue (resserrement de la story 7) ; ne pas retirer la clé `prompts.one` des motifs ni baisser le seuil des six lettres.

## I/O & Edge-Case Matrix

| Cas | Entrée / état | Attendu |
|-----|---------------|---------|
| Nom d'outil replié | `local__define_term` sous `function` replié | lu par `text_contents`, vérification OK |
| Erreur avant changement de langue | `harness_error` français, puis `language_changed` → `de` | mis de côté sur `/diagnostic` |
| Erreur après changement de langue | `harness_error` émis en `de` après le changement | jamais mis de côté (et déjà en `de`) |
| Texte = valeur `de` exacte | « Augmented prompt » sur `/rag` en `de` | non signalé |
| Vrai reste français | « 3 prompt » non traduit, ou « Clé refusée… » émis après le changement | toujours signalé |

</frozen-after-approval>

## Implementation Notes

- Mode non interactif (Anaël injoignable) : les trois échecs gardés dans une seule spec (un seul objectif : passe E2E complète verte), option recommandée prise à chaque point d'arrêt ; diagnostic : aucun défaut produit, donc rien à rendre en arbitrage.
- Base : `main` 5713d78. Seul fichier de code touché : `tools/e2e/run_e2e.py`.
- Reproduction minimale de l'échec 2 : `--only provider_errors annex_language backend_language` reproduit les 4 vérifications « /diagnostic » (erreurs du faux fournisseur) et l'échec 3 ; le 503 du reranker demande en plus `rag rag_rerank` (`rag_rerank` seul échoue sans l'index construit par `rag`). Rejouée sur 5713d78 : les 6 échecs de la passe complète (1 `mcp_full`, 4 « /diagnostic » en/de dans deux scénarios, 1 « /rag » de).
- Échec 1 : `all_inner_texts()` → `all_text_contents()` ; le repli lui-même reste vérifié par `_read_and_produced` (lot 1).
- Échec 2 : `_history_strings(r, errors=False)` ; `harness_error` n'est mis de côté qu'avec `errors=True`, passé par `_annex_french_left` seul (/diagnostic rejoue ces erreurs en lignes de contrôle ; l'écran principal n'en montre que des textes composés, notice de carte ou erreurs du tour, jamais mis de côté).
- Échec 3 : `_literals(french, translated)` : valeurs sans variable du catalogue traduit, moins les valeurs françaises dont la traduction diffère (garde contre un texte français copié par erreur dans `i18n/`). Mesuré : la règle ne met de côté que « Augmented prompt » (de) et « architecture not published, lower precision » (en), deux vraies traductions.
- Vérification : `uv run ruff check` et `ruff format --check` sur `run_e2e.py` OK ; avant correctif, `--only provider_errors annex_language backend_language mcp_full` : les 6 échecs reproduits ; après, `--only provider_errors mcp_full rag rag_rerank ui_language annex_language backend_language --channel msedge` : 155 vérifications réussies, 0 en échec (E094, 503 du reranker, compris). Passe complète laissée à Anaël. Captures : seules `10-` et `10b-` (`mcp_full`) gardées ; 10b datait de 6601114 et montrait encore l'arbre tout déplié.
- Point ouvert pour Anaël (produit, non corrigé) : avec le repli du lot 1, la section « Descriptions d'outils » ne montre plus que `"type": "function"` et `"function": { … } 3 clés` par outil ; on ne voit plus quel outil est natif ou MCP sans dépliage (capture 10b). Options : laisser (décision du lot 1, BH13) ; ou, pour ces seuls arbres, afficher `function.name` dans le résumé replié ou ouvrir un niveau de plus.
- Limite connue (comme pour `model_load_*` et `diagnostic_check`) : la mise de côté compare des textes ; une erreur réémise en français après le changement de langue avec un texte identique à une erreur d'avant serait mise de côté.

## Review Triage Log

Revue Blind Hunter (un relecteur sans contexte), 10 constats :

- low, rejeté : mise de côté par texte, une erreur réémise en français après le changement avec un texte identique serait cachée. Réel, mais limite déjà admise pour `model_load_*` et `diagnostic_check` ; l'apparier par `seq` demanderait de relier le DOM aux événements. Noté en limite connue (la ligne « émis après le changement » de la matrice suppose un texte nouveau).
- medium, patch : la mise de côté de `harness_error` valait aussi pour l'écran principal (`_french_left`) ; limitée à `_annex_french_left` (paramètre `errors`).
- low, patch : `_literals` sans garde contre un texte français copié dans `i18n/` ; les valeurs françaises à traduction différente sont retirées.
- low, rejeté : motifs `{n}` toujours « tout texte » ; un libellé exact est le seul cas observé, des variables numériques demanderaient de classer chaque variable du catalogue.
- false : `mcp_full` ne fige plus le repli ; « racine ouverte, sous-nœuds repliés » est vérifié par `_read_and_produced` (`run_e2e.py:1106-1111`) ; la capture 10b montre le comportement voulu.
- low, rejeté : pas de pytest des helpers ; `run_e2e.py` importe Playwright au chargement et aucun test du dépôt ne l'importe ; vérifié par script ponctuel et passes ciblées.
- low, rejeté : `_french_left` replie les blancs pour les mises de côté mais pas pour `fullmatch` ; antérieur au changement, et replier changerait la lecture des valeurs `ui.yaml` non repliées de `_french_patterns`.
- low, patch : docstring de `_french_left` sans la règle des littéraux ; complétée.
- low, patch : commande de reproduction sans `rag_rerank` ; notes corrigées.
- low, patch : spec sans base ni vérification ; base et résultats ajoutés aux notes.
