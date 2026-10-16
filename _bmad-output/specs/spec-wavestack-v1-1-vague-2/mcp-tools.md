# Outils MCP : risques et règles par défaut (CAP-1, CAP-2, CAP-4, CAP-9)

Base de la matrice de risques de la vue RSSI. Règles par défaut validées par Anaël le 16/10.

| Serveur | Outil | Nature | Risque | Règle par défaut | Ce que le RSSI doit voir |
|---|---|---|---|---|---|
| local | `list_terms`, `define_term` | lecture | faible | autoriser | Contraste avec les outils d'écriture. |
| local | lecture RAM et système | lecture | faible | autoriser | Une information système peut déjà être sensible. |
| local | créer fichier / dossier | écriture, bac à sable | moyen | demander | Effet réel sur le poste, confiné ; refus d'un chemin hors bac à sable. |
| local | capture d'écran | lecture sensible | élevé | demander | Fuite possible ; l'image reste locale, le modèle ne reçoit que chemin et taille. |
| datagouv, mslearn | outils existants | lecture, réseau | faible | autoriser | Sortie réseau soumise à la liste blanche et au hook H5. |
| GitHub | `list_secret_scanning_alerts`, `list_dependabot_alerts`, `get_file_contents`, `list_issues` | lecture, OAuth | moyen | autoriser | Le modèle agit avec les droits de la personne connectée. |
| GitHub | `merge_pull_request`, `create_pull_request` et toute écriture | écriture, OAuth | élevé | refuser | Double refus possible : politique WaveStack en amont, 403 GitHub sur un compte en lecture seule. |

## GitHub MCP distant (recon-mcp du 15/10, test du 16/10)

- URL : `https://api.githubcopilot.com/mcp/`, en GA depuis le 04/09/2025. Transport Streamable HTTP (réponses `text/event-stream`, en-tête `Mcp-Session-Id`). Fonctionne derrière le proxy Zscaler.
- OAuth App WaveStack : Client ID `Ov23li3Ovj8ZnyXMFUPQ` (public), Device Flow activé, jetons qui expirent, aucun client secret. Testée le 16/10 : device flow → jeton `gho_` valable 8 h (avec un refresh token de 6 mois), accepté en `Authorization: Bearer` par le serveur distant (46 outils, alertes comprises). Jeton fin en repli.
- La version du serveur distant est un hash de commit : pas d'épinglage possible. Limite : 5 000 requêtes REST par heure par jeton.
- `X-MCP-Toolsets` doit inclure `secret_protection`, `dependabot` et `code_security`, sinon les outils d'alertes ne sont pas exposés (46 outils par défaut, sans eux).
- `X-MCP-Readonly: true` réduit la liste à 28 outils : les outils d'écriture (`merge_pull_request`, `create_pull_request`) disparaissent.
- Trois niveaux de refus à expliquer en vue RSSI : lecture seule côté GitHub (l'outil n'est pas proposé), politique WaveStack (refuser), 403 GitHub (compte sans droit). La démo du refus WaveStack se fait sans `X-MCP-Readonly`.
- Le serveur local versionné par tag Git reste l'option si un épinglage strict est exigé.
