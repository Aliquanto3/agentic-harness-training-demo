---
id: SPEC-corrections-2026-09-30
companions:
  - ecrans-lots-2-a-4.md
  - atelier-mcp.md
  - ../spec-langues/i18n-conventions.md
  - ../../planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
sources:
  - ../../implementation-artifacts/plan-corrections-2026-09-30.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Corrections du 2026-09-30 : navigation, pages annexes, LLM nu, atelier MCP, traductions

## Why

Retours d'Anaël du 2026-09-30 sur `main`, après les fusions de Gemini, FinOps, GreenOps et Langues 1 à 5. Ils mêlent une douleur et une vision :
- la douleur : un serveur périmé d'un autre working tree a simulé quatre bugs sans qu'on puisse le voir ; la barre haute sature ; les pages Diagnostic et Modèles sont peu lisibles ; deux constats différés gênent l'E2E et l'installation hors ligne ;
- la vision : faire du LLM nu une page où l'on manipule l'échantillonnage, et donner au protocole MCP sa propre page, comme le LLM nu et le RAG ont la leur.

Les langues fusionnées la veille imposent que tout texte nouveau naisse en `fr`, `en` et `de`.

## Capabilities

- **CAP-1** Serveur identifiable (story 1)
  - **intent:** Le formateur sait quel dossier et quel commit servent la page ouverte, et le CLI qui réutilise une instance le dit.
  - **success:** `GET /api/health` rend le dossier du projet et le commit ; lancer `wavestack` sur un port occupé par une instance saine affiche « déjà lancée depuis {dossier} ({commit}) », dans la langue de la session.
- **CAP-2** Navigation commune (story 2)
  - **intent:** Chaque page a la même barre de navigation en tête ; l'atelier garde ses contrôles dans une barre basse.
  - **success:** Sur chaque page, la barre commune mène aux autres pages et marque la page courante ; en `de` à 1 280 et 1 600 px, normal et projection, ni la barre commune ni la barre basse n'ont de contrôle tronqué (`_bar_fits`), selon une tranche E2E.
- **CAP-3** Diagnostic et Modèles lisibles (story 3)
  - **intent:** Le formateur trie et filtre le tableau des modèles, et voit la progression de la recherche des modèles au diagnostic.
  - **success:** Un tri par colonne pose `aria-sort` et réordonne les lignes ; les filtres combinés réduisent le compteur « n sur N » ; pendant la découverte, le diagnostic affiche l'état de recherche et une progression au lieu d'une liste vide ; vérifié par E2E.
- **CAP-4** Constats différés soldés (story 4)
  - **intent:** `rag_rerank` passe dans une tranche chargée, et Headroom compte hors ligne dans un `.venv` neuf.
  - **success:** `rag_rerank` passe dans sa tranche E2E habituelle (avec `rag` et `rag_lab`) trois fois de suite ; les deux tests Headroom hors ligne passent avec un cache tiktoken réduit à ce que livre le dépôt.
- **CAP-5** LLM nu pédagogique (story 5)
  - **intent:** Le stagiaire voit la distribution des candidats changer à chaque réglage d'échantillonnage et compare deux réglages sur la même invite.
  - **success:** Changer top-k, top-p, min-p ou la température redessine les barres des candidats sans nouvelle génération ; « Comparer » produit deux réponses côte à côte ; vérifié par E2E avec le faux modèle.
- **CAP-6** Atelier MCP (story 6)
  - **intent:** Le stagiaire voit un serveur MCP comme un processus à part, la poignée de main JSON-RPC, ce que pèse la documentation des outils, et un appel d'outil avec ses erreurs.
  - **success:** Sur `/mcp`, « Se connecter » au glossaire local affiche `initialize` et `tools/list` avec sens et durée, les outils avec leur poids complet et lazy ; un appel rend la réponse brute et le texte réinjecté ; un argument invalide montre `is_error` ; vérifié par `test_mcp_lab.py` et `s_mcp_lab`.
- **CAP-7** Traductions complètes (story 7)
  - **intent:** Aucun texte produit par l'interface ou le backend ne reste français en `en` ou en `de`.
  - **success:** `content/i18n/{en,de}/messages.yaml` ont exactement les clés et variables du français (parité stricte dans `test_i18n.py`) ; la tranche E2E `backend_language` passe en `en` et `de` ; tout texte ajouté par les stories 1 à 6 existe dans les trois langues.

## Constraints

- **Langues.** Tout texte nouveau passe par `ui.yaml` + `t()` (front), `messages.yaml` + `msg()` (backend, contrôle statique de `test_backend_messages.py`), ou un contenu de `content/` avec champs `*_text` et surcouche `content/i18n/{en,de}/`. Jamais de libellé en dur ni de champ `*_fr` neuf. Détail : `i18n-conventions.md`.
- **L'allemand est la langue la plus longue** : toute mise en page nouvelle tient en `de` à 1 280 et 1 600 px, en mode normal et en projection.
- **UX sans atelier interactif** : les stories 2, 3, 5 et 6 mettent à jour `DESIGN.md` et `EXPERIENCE.md` elles-mêmes, à partir des décisions de `ecrans-lots-2-a-4.md` et `atelier-mcp.md` ; choix visuels selon `tokens.css`.
- **Aucune dépendance nouvelle** sans nécessité démontrée, rien qui demande des droits d'administrateur, `uv` pour tout.
- **PC cible (16 Go, CPU)** : `pytest` en quarts l'un après l'autre, E2E par tranches `--only` de 4 à 6 scénarios, jamais deux suites à la fois, aucun modèle local chargé pendant `pytest` (doublures seulement).
- **Une story livrée ne se casse pas** : une story bloquée s'arrête à un incrément livrable ou passe `blocked`, sans toucher aux précédentes.
- **Atelier MCP en bac à sable** : ses connexions sont les siennes ; il ne modifie jamais l'état de la brique MCP de l'atelier.

## Non-goals

- Le lot 1 (Gemma) et la relance manuelle du lot 0 : déjà faits.
- Revenir sur le menu « Affichage ▾ » de Langues 2.
- Un banc de test JS : la vérification du front reste l'E2E.
- Des générations réellement parallèles en local pour l'A/B du LLM nu.
- Une quatrième langue, ou traduire les descriptions d'outils des serveurs MCP publics.

## Success signal

- Le matin du 2026-10-01, sur `feat/nuit-2026-09-30` lancée sur 8420 : chaque page s'ouvre par la même barre en `fr`, `en` et `de` ; le tableau des modèles se trie ; le LLM nu redessine sa distribution au curseur ; `/mcp` montre la poignée de main du glossaire local ; `ruff`, `pytest` (quarts) et l'E2E complet (tranches) passent.

## Assumptions

- Les captures E2E de l'atelier MCP prennent les numéros 61 et 62 (59 est pris par Gemini, 60 réservé).
- La progression du diagnostic passe par un événement nouveau émis pendant `_discover` ; le contrat d'événements (ARCHITECTURE-SPINE) est mis à jour dans la story 3.
- Pour `cl100k_base`, livrer la table dans le dépôt (licence MIT de tiktoken) et pointer le cache dessus est préféré au téléchargement à l'installation, qui demande le réseau.
