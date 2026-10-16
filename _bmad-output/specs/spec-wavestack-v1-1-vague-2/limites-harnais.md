# Ce que le harnais ne protège pas (CAP-9, vue RSSI)

Texte affiché en vue RSSI, à côté des contrôles actifs. Brouillon du 16/10, à valider par Anaël.

| Limite | Pourquoi | Ce qu'il faudrait en production |
|---|---|---|
| Les garde-fous se trompent. | Ce sont des classifieurs : faux positifs et faux négatifs. Ils sont plus faibles hors de l'anglais (Llama Guard : 38 % de violations évitées en français contre 75 % en anglais, selon Meta). | Plusieurs couches, des seuils calibrés sur ses propres données, une revue humaine des cas limites. |
| L'injection indirecte passe si le détecteur est absent. | Un document du RAG ou un résultat d'outil peut contenir des consignes. Sans Prompt Guard (optionnel), rien ne les détecte. | Détection sur tout contenu entrant, pas seulement sur le message de l'utilisateur. |
| L'autorisation porte sur le nom de l'outil, pas sur ce qu'il fait. | Un serveur MCP peut décrire un outil de façon trompeuse ou changer son comportement côté serveur. | Serveurs MCP approuvés et épinglés, revue de leurs descriptions, journal côté serveur. |
| Le jeton GitHub donne tous les droits accordés. | Les droits d'une OAuth App sont larges ; WaveStack filtre les outils, mais le jeton reste valable 8 h pour tout ce qu'il couvre. | GitHub App à permissions fines, jetons courts, révocation centralisée. |
| Le bac à sable n'isole pas le processus. | C'est un contrôle de chemin dans l'application, pas un conteneur ni un compte système dédié. | Exécution des outils dans un conteneur ou une VM, sous un compte sans privilège. |
| La capture d'écran voit tout l'écran. | Les autres fenêtres ouvertes y figurent. Elle reste sur le poste, mais elle existe. | Interdire l'outil, ou le limiter à une fenêtre précise. |
| Le journal n'a pas de valeur d'audit. | Il est local, non signé, et modifiable par l'utilisateur du poste. | Envoi vers un SIEM, horodatage et intégrité garantis. |
| Le harnais ne contrôle pas ce que fait le fournisseur cloud. | Les messages envoyés à un modèle cloud sont soumis à ses conditions de conservation et d'usage. Presidio détecte des données personnelles, il ne garantit pas leur absence. | Contrat et région d'hébergement maîtrisés, ou modèle local pour les données sensibles. |
| L'appli n'a pas d'authentification. | Elle écoute seulement sur la machine (127.0.0.1) : quiconque utilise le poste y a accès. | Authentification et cloisonnement par utilisateur, hors du périmètre de la démo. |
| Les coûts sont des estimations. | Prix déclarés dans la configuration ; « ≈ » quand l'usage n'est pas mesuré par le fournisseur. | Rapprochement avec la facture du fournisseur. |
