# Risques et parades — WaveStack

| Risque | Parade |
|---|---|
| Le SLM rate ses appels d'outils ou de skills en pleine démonstration. | Scénarios éprouvés (CAP-40). Déclenchement forcé (CAP-8). Échecs montrés comme matériau pédagogique (CAP-16, NFR-8). Changement de modèle (CAP-34). |
| L'installation échoue sur les postes verrouillés (proxy, AppLocker, antivirus). | Voie hors ligne pour le modèle (CAP-36). Diagnostic (CAP-39). Roues précompilées, sans compilation ni exécutable à installer ; DLL non signées acceptées, vérifiées lors de la session pilote. Repli en démo pilotée. |
| Le contexte trop long (RAG et MCP en documentation complète) rend la latence insupportable. | Modèle par défaut de 2B au plus, fenêtre de contexte plafonnée, lazy loading MCP (CAP-22), compression du contexte (CAP-32), latence et jauge affichées (CAP-31, CAP-33). En dernier recours, vidéo d'une session précédente. |
| Pas de réseau en salle. | Toutes les briques non réseau fonctionnent hors ligne (NFR-3). |
| Périmètre V1 large (11 briques, scénarios) pour un porteur seul. | Pas d'échéance imposée. Livraison en deux paliers (constraint « Livraison en deux paliers »), le socle d'abord, pour tester tôt. |
| Le plafond de 4 Go ne laisse pas de place au modèle, aux embeddings, au reranker et aux serveurs MCP locaux réunis. | Mesure sur le poste de référence avant de figer le modèle par défaut. Modèles d'embedding et de reranking légers. Chargement des composants à l'activation de leur brique. |
| Une offre gratuite de modèle cloud change, ferme ou épuise son quota en séance (429). | Aucun fournisseur en dur (CAP-43). Fenêtre plafonnée à la moitié du quota par minute, pour qu'un tour avec un appel d'outil tienne dans la minute. Refus expliqué, sans nouvel essai. Test avant chaque séance, repli sur le modèle local. |
| Les prompts envoyés à un modèle cloud servent à entraîner le modèle du fournisseur. | Avertissement et infobulle par fournisseur ; scénarios sans donnée sensible (NFR-11) ; désactivation en console quand elle existe (Mistral). |
| Une clé API fuit (trace, dépôt, capture d'écran). | Clé hors dépôt, envoyée au seul hôte enregistré avec elle, jamais tracée ni renvoyée au navigateur, masquée dans les messages du fournisseur, champ masqué. Test avec une clé sentinelle. |
