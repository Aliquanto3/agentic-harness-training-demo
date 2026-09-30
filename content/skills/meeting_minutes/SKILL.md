---
name: meeting_minutes
label_text: Compte rendu de réunion
description: Rédiger le compte rendu d'une réunion (décisions, actions, responsables) à partir des éléments que donne le message. À charger quand l'utilisateur demande un compte rendu ou une synthèse de réunion.
---
Rédige un compte rendu de réunion structuré.

Étapes :
1. Si le message de l'utilisateur donne des éléments de la réunion (participants, sujets, décisions, dates), rédige à partir de ces seuls éléments, sans lire de fichier. Seulement si le message ne donne aucune note, lis-les avec l'outil read_file, chemin « notes_reunion.txt » (brique « Outils », outil « Lecture de fichier »).
2. Rédige le compte rendu dans cet ordre :
   - Présents : les participants, s'ils sont connus.
   - Décisions : ce qui a été décidé, une ligne par décision.
   - Actions : ce qu'il faut faire, avec le responsable et l'échéance quand elle est connue.
   - Prochaine réunion : date et heure, si elles sont indiquées.

N'invente ni décision, ni responsable, ni date : si une information manque, écris « non précisé ». Reste bref, une ligne par point.
