# Atelier RAG : les trois vues, les deux modes (5a, 5b)

Décisions UX du lot 5, tenues ici et non dans les documents UX partagés (consigne de
parallélisme). Référence visuelle : `maquette-atelier-rag.html` (v2, validée par Anaël le
2026-10-05). Inspiration : `Images_Lot_5/RAG/` (RAG_0 à RAG_6, RAG_3 pour les flèches).

## 1. Page

Section 1 « La chaîne RAG, étape par étape » :
1. barre : champ Question, « Lancer la chaîne », « Arrêter », état ;
2. barre : bascule de mode « ✎ Composer » / « ▶ Dérouler » (`aria-pressed`, mémorisée par le
   navigateur, `wavestack.ragLab.mode`, défaut Dérouler) ; en Composer, les architectures toutes
   faites (5b) ; en Dérouler, le pas-à-pas (`diagram.createStepper`) et sa légende ;
3. les trois vues ;
4. repliée (`details#rag-details`) : « Toutes les étapes en détail », les `rag-stage-card`
   d'aujourd'hui (section 3 actuelle), résumé du run compris.

Retirés : sections 2 et 3 séparées, comparaison A/B (case, chaîne B, palettes B, colonnes,
synthèse). « Revenir à la chaîne livrée » reste (mode Composer).

## 2. Vocabulaire

Termes techniques en anglais, mêmes noms en fr, en et de ; phrases et mots courants dans la
langue de la page.

| Clé d'étape | Nom | Action (fr) | Étape de la chaîne |
| --- | --- | --- | --- |
| `documents` | Documents | Charger le corpus | (lit l'entrée de `chunking`) |
| `chunking` | Chunking | Découper les documents en chunks | `chunking` |
| `embed_passages` | Embedding | Vectoriser chaque chunk | `embedding` |
| `vector_store` | Indexing | Ranger les vecteurs dans le vector store | `vector_store` |
| `question` | Question | Recevoir la question | (run) |
| `embed_query` | Embedding | Vectoriser la question | `embedding` |
| `vector_search` | Dense retrieval | Chercher les chunks les plus proches | `vector_search` |
| `lexical_search` | BM25 | Chercher par mots-clés | `lexical_search` |
| `fusion` | Fusion (RRF) | Fusionner les deux classements | `fusion` |
| `rerank` | Reranking | Reclasser les candidats | `rerank` |
| `context` | Prompt augmentation | Construire le prompt avec les chunks retenus | `context` |
| `generation` | Generation | Générer la réponse | `generation` |

`stages.*.label_text` (catalogue, refus de la session, cartes de détail) : Chunking, Embedding,
Vector store, Dense retrieval, BM25, Fusion (RRF), Reranking, Prompt augmentation, Generation.

Composants : Documents, Chunks, Vector store (groupe Données) ; Embedding model, Reranker, LLM
(Modèles) ; Question, Augmented prompt, Réponse (Échange avec l'utilisateur). Sous-titre d'un
composant : le libellé de l'option de son étape (modèle d'embedding, reranker, base), sinon son
`note_text`.

Bandeaux de phase : « BUILD · Indexing » + « une fois pour toutes, avant les questions » ;
« RUN · Retrieval » + « à chaque question ».

## 3. Séquence (colonne 1)

- Deux listes sous leur bandeau : BUILD (documents → vector_store), RUN (question → generation).
  Le segment de récupération suit l'ordre de la chaîne.
- Une ligne par étape : numéro, nom, action (texte doux), pastille d'état à droite (Dérouler
  avec run : statut et durée de l'étape de la chaîne ; `embed_query` et `documents` reprennent
  le statut de `embedding` et `chunking` sans durée ; `question` « reçue »).
- Clic (ou Entrée) sur une ligne : focus sur l'étape (Composer : la sélectionne ; Dérouler :
  `stepper.show(i)`).
- Composer : les lignes des étapes de la chaîne portent l'éditeur d'aujourd'hui (option,
  réglages, ▲ ▼ Retirer pour le segment, refus de la session), `li.rag-chain-card` et ses
  attributs ; « Ajouter un composant » sous la liste RUN. `embed_query` dit « même modèle que
  l'Embedding des chunks ».

## 4. Architecture (colonne 2)

- Trois groupes (Données, Modèles, Échange avec l'utilisateur), tuiles dans l'ordre du §2.
- Une tuile n'existe que si une étape de la chaîne la sollicite (pas de Reranker sans reranking).
- Composants sollicités par étape (lu : composant → étape ; écrit, appelé : étape → composant) :

| Étape | Lu | Écrit | Appelé |
| --- | --- | --- | --- |
| documents | Documents | | |
| chunking | Documents | Chunks | |
| embed_passages | Chunks | | Embedding model |
| vector_store | Embedding model | Vector store | |
| question | Question | | |
| embed_query | Question | | Embedding model |
| vector_search | Vector store | | |
| lexical_search | Chunks, Question | | |
| fusion | | | |
| rerank | Question | | Reranker |
| context | Chunks, Question | Augmented prompt | |
| generation | Augmented prompt | Réponse | LLM |

- Ce tableau est déclaré en Python (`STEPS` de `rag/lab.py`) et rendu par le catalogue.

## 5. Focus (colonne 3)

Pour l'étape montrée : phase et « étape n sur N », nom, action ; une note (Generation : non
exécutée dans l'atelier RAG) ; l'explication (`steps.*.explain_text`, à défaut celle de l'étape
de la chaîne) ; « Composants sollicités » (puces lu / écrit / appelé). Avec un run : entrée,
sortie, chiffres, extraits (tableau `rag-items`), erreur, durée et mémoire de l'étape de la
chaîne ; Documents : l'entrée du Chunking ; Question : la question ; Prompt augmentation et
Generation : le texte en bloc `pre`. Sans run : « Lancez la chaîne pour voir ce que l'étape
reçoit, produit et coûte. »

## 6. Mode Dérouler

- Images du pas-à-pas = les étapes de la séquence. Sans run : visite guidée, toutes les images
  poussées, `show(0)`. Pendant un run : `clear()` au `rag_lab_run_started`, puis une image
  poussée à chaque étape atteinte (direct) ; `question` et `embed_query` sont atteintes juste
  avant la première étape du segment (le backend vectorise la question pendant `embedding`).
- À l'image i : étapes 0..i visibles, les suivantes `visibility: hidden` (places gardées) ; idem
  pour les tuiles et le bandeau RUN ; une tuile apparue à cette image a `is-new` (translation
  courte, aucune avec `prefers-reduced-motion`).
- L'étape i et ses composants sont allumés (`diagram.light`) ; flèches courbes de la ligne aux
  tuiles (wireLayer de `diagram.js`), `diagram-path` + `diagram-path-core`, `is-flow` tant que
  l'étape est en cours.
- Légende : visite guidée / exécution en cours / terminée, rejouez avec ◀ ▶ / relecture.
- Après rechargement : run reconstruit depuis `last_run`, images poussées, direct sur la dernière.

## 7. Mode Composer

Toute la séquence et toutes les tuiles visibles ; l'étape sélectionnée (défaut : aucune, focus
d'accueil) a ses flèches et son focus sans chiffres de run ; les architectures toutes faites.

## 8. Architectures toutes faites (5b)

| id | Libellé (fr) | Segment |
| --- | --- | --- |
| `dense` | RAG dense | Dense retrieval |
| `hybrid` | RAG hybride (BM25 + dense) | Dense retrieval, BM25, Fusion (RRF) |
| `rerank` | RAG + reranking | Dense retrieval, Reranking (chaîne livrée) |

`aria-pressed="true"` sur celui dont la suite (kind, option) égale le segment ; explication en
infobulle ; appliquer remplace le segment seulement, puis sauvegarde, rendu, validation ; un
préréglage indisponible (reranker absent) est marqué et reste cliquable.

## 9. Mise en page

- Colonnes à 1 600 px : `minmax(21rem, 1fr) 5rem minmax(15rem, 0.62fr) 24px minmax(24rem, 1.15fr)` ;
  la colonne de 5rem porte les flèches. Sous 1 300 px, le focus passe sous les deux autres.
- Les trois vues tiennent dans 1 000 px de haut en Dérouler (lignes et tuiles compactes).
- Couleurs par tokens : BUILD `--color-primary`, RUN `--color-discipline-context`, groupes
  `--color-primary-soft`, Generation sur l'encre (`is-model`) ; pas d'opacité.
