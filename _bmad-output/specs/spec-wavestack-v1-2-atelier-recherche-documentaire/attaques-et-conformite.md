# Vue Attaquer et fiches conformité (CAP-13 à CAP-16)

## Scénarios d'attaque (document piégé, CAP-13)

| Scénario | Mécanisme | Sans garde-fou | Avec garde-fou |
|---|---|---|---|
| Injection indirecte | Le document piégé contient une instruction cachée (« ignore les consignes, réponds… ») | La réponse obéit à l'instruction | `injection.py` (Prompt Guard 2) signale ou bloque le passage ; le verdict est visible dans le focus et le Journal de sécurité |
| Empoisonnement (PoisonedRAG) | Une affirmation fausse, rédigée pour remonter en tête sur une question cible | La réponse reprend l'affirmation fausse | Montrer la limite : aucun garde-fou de contenu ne la détecte ; le contrôle d'ancrage (CAP-6) ou la diversité des sources aident, et la fiche le dit |
| Empoisonnement du graphe | Le document piégé injecte une relation fausse dans le graphe de GraphRAG | La requête globale propage la relation dans un résumé de communauté | Montrer que l'effet persiste après retrait du document, tant que le graphe n'est pas reconstruit |

## Effacement (CAP-14)

Pour chaque architecture, la vérification liste où la sentinelle survit :

| Endroit | Architectures concernées |
|---|---|
| Chunks et vecteurs | dense, hybride, reranking, CRAG, RAPTOR |
| Index BM25 | hybride |
| Résumés dérivés | RAPTOR, PageIndex, GraphRAG (communautés), LLM Wiki |
| Entités et relations | GraphRAG |
| Cache de prompt ou KV | CAG, contexte long (préfixe en cache) |
| Contenu précalculé livré | toutes celles qui en ont un |

Chaque ligne affiche : présent, effacé, ou « à reconstruire ». Une requête qui vise la sentinelle, posée après l'effacement, montre ce qui fuit encore.

## Droits d'accès (CAP-15)

Deux profils : « Tous » et « RH ». Deux modes :
- **Filtrage après recherche** : le top-k est calculé sur tout le corpus, puis on retire les passages interdits. La fuite se voit quand le LLM a déjà reçu le passage, par exemple dans le contexte ou la réécriture, ou quand le nombre de résultats trahit l'existence du document.
- **Contrôle avant recherche** : seul l'index autorisé au profil est interrogé, de façon déterministe et sans LLM. On n'observe aucune fuite.

## Fiche conformité par architecture (CAP-16)

Ces sept axes reprennent ceux de la section Conformité du cadrage.

| Axe | Question posée |
|---|---|
| Localisation des données | Où transitent documents, index, dérivés et prompts ? Quatre classes : local, cloud UE, SecNumCloud, hors UE. Déclaratif par composant, tiré de la configuration (modèle cloud, juge, Jev, export OTel) |
| Copies et contenu dérivé | Nombre et nature des copies (chunks, résumés, graphe, wiki, cache) : un contenu synthétisé se protège comme sa source |
| Effacement | Que faut-il reconstruire pour effacer un document ? Résultat de CAP-14, coût et durée de remise en conformité |
| Droits d'accès | Le contrôle peut-il passer avant la recherche ? Un filtre de sortie ne suffit pas. Résultat de CAP-15 |
| Injection et outils | Surface d'injection : passages, résumés, graphe ; permissions des outils de la recherche agentique ; exfiltration |
| Traçabilité | Peut-on citer la source exacte d'une affirmation ? Journaux, arbre et export (CAP-12) |
| Cadre réglementaire | Grille qualitative : RGPD, AI Act selon l'usage, DORA ou NIS2 selon le secteur, dépendance fournisseur (Jev, par exemple, est propriétaire et sans hébergement local) |

**Données de la fiche** :
- elles sont déclarées dans `content/`, à côté de la matrice des risques de la page Sécurité (`mcp/policy.py` `RISKS`), dans le même format de niveaux ;
- la page Sécurité peut les afficher sans calcul côté page (AD-1).
