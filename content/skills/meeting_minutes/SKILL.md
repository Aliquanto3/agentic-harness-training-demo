---
name: meeting_minutes
label_fr: Compte rendu de réunion
description: Rédiger le compte rendu d'une réunion (décisions, actions, responsables), en lisant les notes avec l'outil read_file, fichier notes_reunion.txt. À charger quand l'utilisateur demande un compte rendu ou une synthèse de réunion.
---
Rédige un compte rendu de réunion structuré.

Étapes :
1. Si l'utilisateur ne donne pas les notes dans son message, lis-les avec l'outil read_file, chemin « notes_reunion.txt » (brique « Outils », outil « Lecture de fichier »).
2. Rédige le compte rendu dans cet ordre :
   - Présents : les participants, s'ils sont connus.
   - Décisions : ce qui a été décidé, une ligne par décision.
   - Actions : ce qu'il faut faire, avec le responsable et l'échéance quand elle est connue.
   - Prochaine réunion : date et heure, si elles sont indiquées.

N'invente ni décision, ni responsable, ni date : si une information manque, écris « non précisé ». Reste bref, une ligne par point.
