# Vues de l'Atelier recherche documentaire

La référence visuelle est `maquette-atelier-recherche-documentaire.html` (dans ce dossier). Elle s'ouvre en `file://` et utilise les tokens et styles réels du dépôt, avec des données fictives. Elle reste à faire valider par Anaël.

## Page

- **Page** : `/rag`, au titre « Atelier recherche documentaire ». L'onglet de la barre commune garde sa place.
- **Onglets de vue**, sous l'en-tête : Construire · Comparer · Évaluer · Attaquer · Fiches.
- **Barre de question** : la question libre ou un sélecteur « question préparée » (CAP-2), avec un badge de type.
- **Préréglages** : une rangée de 11 boutons groupés en trois familles :
  - **Recherche** : dense, hybride, reranking, CRAG ;
  - **Structure** : PageIndex, RAPTOR, GraphRAG, LLM Wiki ;
  - **Sans index** : contexte long, CAG, agentique.

  Un préréglage indisponible reste visible, grisé par motif et non par opacité, avec sa raison.

## Onglet Construire

C'est l'onglet par défaut : les vues séquence, architecture et focus du lot 5 (`vues-atelier-rag.md`), inchangées. Il ajoute :
- **Coûts en trois temps** sous la séquence (CAP-8) : construction, mise à jour et requête. Chaque carte montre les tokens, la durée, les dollars et les gCO₂e, avec la mention « mesuré à la construction » sur le contenu précalculé, plus les boutons « Ajouter », « Modifier » et « Supprimer un document » pour mesurer une mise à jour.
- **Dans le focus**, selon l'étape :
  - la requête réécrite ou les sous-requêtes (CAP-3) ;
  - les chunks (CAP-4) ;
  - le prompt final et le budget (CAP-5) ;
  - pour les décisions System One : auteur, probabilité et seuil (CAP-6) ;
  - le rang du passage attendu (CAP-10).
- **Lien « Fiche »** dans le focus, vers la fiche du composant (CAP-17).
- **Arbre des étapes** dans un volet repliable (CAP-12), avec durées et tokens, plus un bouton d'export OTLP, visible seulement quand l'extra est installé et l'URL réglée.
- **Bouton « Épingler cette exécution »** (CAP-9).

## Onglet Comparer (CAP-9)

- Deux colonnes : « Épinglée » et « Courante ». Chacune porte l'architecture, la question et l'heure.
- Une ligne par étape, alignée par rôle (recherche, contexte, réponse), quand les chaînes diffèrent.
- Les écarts sont mis en évidence : passages ajoutés ou perdus, rang du passage attendu, coûts B/U/Q.
- Pas de synthèse rédigée : le participant lit les écarts.

## Onglet Évaluer (CAP-11, `evaluation.md`)

- Un bandeau permanent : « Démonstration, pas un banc : n = … questions ».
- Un tableau questions × critères : verdict de chaque juge, annotation humaine, désaccords marqués.
- Les agrégats par architecture évaluée (rappel@k, MRR, fidélité…), avec n.
- Un panneau « Pièges », avec les quatre cas livrés.

## Onglet Attaquer (CAP-13 à CAP-15, `attaques-et-conformite.md`)

Trois cartes :
- **Document piégé** : activer, choisir le scénario, garde-fous oui/non ;
- **Effacement** : supprimer la sentinelle, puis le tableau des endroits où elle survit ;
- **Droits** : profil Tous ou RH, mode après ou avant la recherche.

Chaque carte relance la question cible et montre l'effet dans le focus.

## Onglet Fiches (CAP-16, CAP-17)

- Une liste des composants et des architectures.
- Une fiche en quatre blocs : à quoi il sert, quand l'utiliser ou l'éviter, ce qu'il coûte, ce que dit la littérature (avec les liens).
- Pour une architecture, la fiche conformité sur six axes, avec liens vers les démonstrations de l'onglet Attaquer.

## Règles UX conservées

- AD-1 : chiffres, statuts et disponibilités viennent de la session ; la page ne calcule que la mise en page.
- Contraste AA en clair et en sombre, états sans opacité.
- Les sélecteurs E2E du lot 5 sont conservés.
