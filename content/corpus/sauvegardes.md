# Politique de sauvegarde d'Exemplia

<!-- Texte fictif rédigé pour WaveStack. Exemplia est une organisation imaginaire : cette politique ne décrit aucune entreprise réelle. -->

Les données d'Exemplia suivent la règle 3-2-1 : au moins 3 copies de chaque donnée, sur 2 supports différents, dont 1 copie conservée hors du site principal. Cette règle s'applique aux serveurs de fichiers, aux bases de données des applications et à la messagerie.

La sauvegarde complète des serveurs a lieu chaque dimanche à 2 h du matin. Chaque nuit de la semaine, à 22 h, une sauvegarde incrémentale copie uniquement ce qui a changé depuis la veille. Les bases de données critiques, comme la comptabilité et la gestion des clients, sont en plus sauvegardées toutes les 4 heures en journée.

Les sauvegardes quotidiennes sont conservées 35 jours, les sauvegardes hebdomadaires 12 semaines et une sauvegarde mensuelle est gardée 7 ans pour les obligations comptables. Une copie hebdomadaire est écrite sur bande, puis déconnectée du réseau et rangée dans un coffre situé dans un second bâtiment, à 30 kilomètres du siège : elle reste hors d'atteinte d'un rançongiciel.

Les objectifs de reprise sont fixés par application. Pour les applications critiques, la perte de données maximale admise est de 4 heures et le service doit repartir en moins de 8 heures. Pour les autres applications, la perte admise est de 24 heures et le délai de reprise de 2 jours ouvrés.

Un test de restauration est mené chaque mois sur un échantillon de 10 fichiers tirés au hasard, et chaque semestre sur une application complète, dans un environnement isolé. Le résultat de chaque test est consigné dans le registre de l'équipe d'exploitation ; un échec est traité comme un incident de niveau 2.

Les postes de travail ne sont pas sauvegardés : chaque collaborateur enregistre ses documents dans son espace réseau ou dans l'espace de son équipe, qui eux le sont. Un fichier supprimé par erreur peut être restauré par le support pendant les 35 jours de conservation, sur simple demande.
