---
name: working_days
label_text: Jours ouvrés
description: Compter les jours ouvrés d'une période avec les outils get_datetime, public_holidays (réseau) et calculator. À charger quand l'utilisateur demande combien de jours ouvrés ou travaillés compte une période.
---
Compte les jours ouvrés (du lundi au vendredi, hors jours fériés) d'une période, en trois étapes, dans cet ordre.

Outils à activer (brique « Outils ») : « Heure et date » (get_datetime), « Jours fériés » (public_holidays) et « Calculatrice » (calculator). public_holidays est un outil réseau, désactivé par défaut : s'il manque, dis à l'utilisateur de l'activer.

1. Appelle get_datetime pour connaître la date du jour, et donc l'année, si la période ne la précise pas (« ce mois-ci », « le mois prochain »).
2. Appelle public_holidays avec l'année de la période, pour obtenir la liste des jours fériés. Si la période s'étend sur deux années, appelle-le pour chacune des deux.
3. Compte les jours du lundi au vendredi de la période, puis retire avec calculator les jours fériés qui tombent un jour de semaine dans la période (par exemple 23-2).

Réponds avec le nombre de jours ouvrés, puis la liste des jours fériés retirés. Si un outil échoue, dis lequel et pourquoi, sans inventer de date.
