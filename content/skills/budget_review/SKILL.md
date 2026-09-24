---
name: budget_review
label_fr: Point budget
description: Faire le point sur le budget du projet avec les outils read_file (fichier confidentiel/budget_projet.txt) et calculator, rendu en tableau. À charger quand l'utilisateur demande le budget du projet, son total ou la répartition de ses postes.
---
Fais le point sur le budget du projet, en trois étapes, dans cet ordre.

Outils à activer (brique « Outils ») : « Lecture de fichier » (read_file) et « Calculatrice » (calculator). Si l'un d'eux est désactivé, dis-le à l'utilisateur et demande-lui de l'activer.

1. Lis le budget avec read_file, chemin « confidentiel/budget_projet.txt ».
2. Calcule le total avec calculator, en additionnant tous les postes (par exemple 12000+48000+5000).
3. Calcule la part de chaque poste dans le total, en pourcentage (par exemple 12000*100/65000) : envoie tous ces appels à calculator ensemble, dans une seule réponse, un appel par poste.

Réponds enfin avec un tableau Markdown à trois colonnes : Poste, Montant (€), Part du total (%), avec une dernière ligne « Total ».

Ne calcule jamais de tête : chaque nombre du tableau vient du fichier ou de calculator. Arrondis les pourcentages à une décimale.
