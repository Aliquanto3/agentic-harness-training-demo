# Écrans des lots 2 à 4 : décisions de détail

Détail des CAP-2, CAP-3 et CAP-5 de `SPEC.md`, repris de `plan-corrections-2026-09-30.md`.

## Barre de navigation commune (CAP-2, story 2)

- Une barre identique en tête de chaque page servie : logo WaveStack, Atelier (`/`), LLM nu (`/llm`), Atelier RAG (`/rag`), Diagnostic (`/diagnostic`), Modèles (`/models`), puis le thème et la langue. La page courante est marquée (`aria-current="page"`).
- La story 6 insère « Atelier MCP » (`/mcp`) entre « Atelier RAG » et « Diagnostic ».
- Elle remplace `.page-tabs` des pages annexes et absorbe `#llm-link`, `#rag-link` et le titre de la barre de l'atelier.
- Un seul balisage, partagé par les pages (fichier JS ou gabarit commun, au choix de l'implémentation), libellés par `t()` dans une section `common.nav` de `ui.yaml`.
- Le menu « Affichage ▾ » de Langues 2 (thème, langue, projection) reste la décision en vigueur ; `#theme-picker`, `#language-picker` et `#projection-toggle` gardent leurs identifiants.

## Atelier : barre basse et volets (CAP-2, story 2)

- La barre actuelle de l'atelier (`.top-bar` : scénario, modèle, dépense, indicateurs, actions) passe en bas de l'écran.
- Les titres de volets (« Vue humain »…) descendent d'un cran typographique (tokens de `tokens.css`).
- Risques à traiter dans la story : règles de projection et paliers 1 000 / 1 100 / 1 280 / 1 400 / 1 500 / 1 600 px de `app.css` qui visent `.top-bar` ; vérification E2E « la barre tient » (`_bar_fits`) ; panneau « Fenêtre » calé sous la barre.
- Constat différé « barre saturée à 1 600 px » : aucun sélecteur réduit à deux lettres suivies de « … » en `de` à 1 280 et 1 600 px, normal et projection.

## Page Modèles (CAP-3, story 3)

- Refonte avec les tokens de `tokens.css` (principes du skill `artifact-design`, `dataviz` pour tableau et jauges).
- Tableau : tri par colonne au clic et au clavier, `aria-sort` sur l'en-tête actif ; filtres hébergement, éditeur, outils, raisonnement, texte libre ; aucune dépendance JS. Données : `/api/diagnostic.models`, déjà servies.
- Le tri et les filtres se combinent ; un compteur dit « n modèles sur N ».

## Page Diagnostic (CAP-3, story 3)

- Tant que le contrôle `model` n'est pas rendu, la liste des candidats affiche « Recherche et test des modèles en cours… » avec une progression n sondés sur N (nouvel événement de progression émis par la découverte, `_discover`), au lieu d'une liste vide confondue avec « aucun ».
- Hiérarchie visuelle des contrôles ; bloc cloud plus lisible.

## LLM nu pédagogique (CAP-5, story 5)

- Démarche : pour chaque section, les questions qu'un stagiaire se pose, et une manipulation visible qui y répond ; les questions sont écrites dans la page.
- Section 2, distribution vivante : barres des candidats (déjà calculés par `candidates_from_logits`) recalculées à chaque réglage de top-k, top-p, min-p et température, sans nouvelle génération quand les logits sont déjà connus.
- Comparaison A/B : la même invite générée avec deux réglages, rendue côte à côte. En local, séquentielle (un seul modèle sur CPU, session `llm_lab` exclusive) ; parallèle seulement pour un modèle cloud.
- Autres sections : la frise du chargement et le chronomètre lecture/génération existent ; les enrichir de schémas (table d'embedding, fenêtre glissante, réflexion puis réponse).
- Incrément livrable minimal si la story bloque : la distribution vivante seule.
