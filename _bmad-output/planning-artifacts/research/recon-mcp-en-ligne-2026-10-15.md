---
title: "Recherche technique : un MCP en ligne pour l'onglet MCP de WaveStack"
type: 'technical'
topic: "MCP distant gratuit, OAuth réel, pour la démo WaveStack (vague 2, public RSSI)"
decision: "Choisir le serveur MCP distant à brancher sur l'onglet MCP, pour démontrer l'authentification OAuth et le refus d'autorisation devant un public RSSI"
source: 'recherche web (ici), sans accès au dépôt privé de recherche BMAD complet'
status: draft
created: '2026-10-15'
updated: '2026-10-15'
---

# Recherche technique : un MCP en ligne pour WaveStack

**Décision que cette recherche sert :** quel serveur MCP distant brancher sur l'onglet MCP de WaveStack pour la démo (actuellement deux serveurs publics configurés : `datagouv` et `mslearn`, cf. `src/wavestack/mcp/servers.py`), en vue de la vague 2 qui ouvre la démo aux RSSI. Le serveur doit être gratuit, avec une authentification OAuth réelle (pas une clé API statique), des outils compréhensibles par un non-ingénieur, une stabilité et des versions épinglables, et des conditions d'usage claires. Chaque candidat doit permettre de montrer un appel que l'autorisation refuse (pour illustrer la sécurité).

**Méthode :** recherches web ciblées (pas d'accès à un rapport de recherche externe fourni par l'utilisateur), croisant la documentation officielle de chaque fournisseur et des guides tiers récents (2026). Les affirmations tierces non confirmées par la documentation officielle sont signalées comme telles.

## Classement

| Rang | Candidat | Pourquoi |
|---|---|---|
| 1 | **GitHub MCP Server (distant)** | Le plus parlant pour un RSSI : alertes de sécurité, secrets, dépôts. OAuth réel, gratuit avec un compte GitHub existant, outils nommés clairement (`list_secret_scanning_alerts`, `create_pull_request`, …). |
| 2 | **Atlassian MCP Server (Jira + Confluence)** | Terrain « entreprise » très lisible pour un RSSI (droits, suppression, workflow). OAuth 2.1 réel, gratuit sur le palier Free (10 utilisateurs), mais mise en œuvre OAuth plus complexe (enregistrement dynamique du client) et gouvernance encore mouvante. |
| 3 | **Notion MCP Server** | Le plus simple à comprendre pour un non-ingénieur (pages, recherche, commentaires), gratuit, OAuth réel via Cloudflare. Moins parlant pour un RSSI (pas de notion de sécurité native) et le périmètre « lecture seule » n'est pas garanti par le serveur hébergé lui-même. |

## 1. GitHub MCP Server (distant) — rang 1

- **Ce que c'est :** le serveur MCP officiel de GitHub, hébergé (`https://api.githubcopilot.com/mcp/`), couvrant dépôts, issues, pull requests, Actions, et les fonctionnalités de sécurité (secret scanning, Dependabot, code scanning). Authentification par OAuth « en un clic » par défaut (jeton d'accès personnel possible en repli manuel), avec des portées (scopes) approuvées à la connexion ; une politique d'organisation peut aussi restreindre les portées et applications autorisées [GitHub Docs, docs.github.com, consulté le 15/10/2026](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/set-up-the-github-mcp-server).
- **Gratuit :** oui, avec un compte GitHub existant (y compris gratuit) ; les appels consomment les limites de débit de l'API GitHub sous-jacente, pas un quota MCP séparé — un jeton personnel ou OAuth App dispose de 5 000 requêtes REST par heure, une GitHub App peut aller jusqu'à 12 500–15 000/heure [synthèse de sources tierces 2026, non confirmée par une page GitHub officielle unique ; voir github/github-mcp-server, policies-and-governance.md, consulté le 15/10/2026](https://github.com/github/github-mcp-server/blob/main/docs/policies-and-governance.md).
- **Outils parlants :** noms explicites en anglais (`get_file_contents`, `list_issues`, `create_pull_request`, `list_secret_scanning_alerts`, `list_dependabot_alerts`) — compréhensibles pour un non-ingénieur avec un minimum d'explication, car ils reprennent le vocabulaire de l'interface web GitHub.
- **Stabilité / versions épinglables :** le dépôt `github/github-mcp-server` est public avec des releases ; au 15/10/2026 le statut exact (preview ou GA) de la version *distante* n'est pas confirmé par une annonce officielle trouvée — une page de politique datée de juillet 2025 indique que le passage en GA est encore attendu à cette date, ce qui est une information à vérifier avant la démo [github/github-mcp-server, policies-and-governance.md, consulté le 15/10/2026](https://github.com/github/github-mcp-server/blob/main/docs/policies-and-governance.md). Le serveur local (binaire) est, lui, versionné par tag Git — préférable si un épinglage strict est exigé.
- **Conditions d'usage :** celles du compte GitHub (CGU GitHub standard) ; aucune clause MCP spécifique trouvée au-delà de la politique de gouvernance ci-dessus.
- **Scénario de démo :** connecter le compte GitHub de démo (lecture seule sur un dépôt public), demander au modèle « y a-t-il des alertes de sécurité ouvertes sur ce dépôt ? » → `list_secret_scanning_alerts` / `list_dependabot_alerts` renvoie une liste lisible, sans jargon réseau.
- **Appel refusé (sécurité) :** demander au modèle de fusionner une pull request ou de supprimer une branche protégée sur un dépôt où le compte de démo n'a que la lecture → l'appel `merge_pull_request` (ou équivalent) échoue côté GitHub avec une erreur de permission (403), que l'onglet « Autorisation » de WaveStack peut aussi intercepter en amont si l'outil est marqué comme une action d'écriture non accordée. Cela illustre à la fois l'OAuth à portée limitée côté fournisseur et le filtrage applicatif côté WaveStack.

## 2. Atlassian MCP Server (Jira + Confluence) — rang 2

- **Ce que c'est :** le serveur MCP distant officiel d'Atlassian (dépôt `atlassian/atlassian-mcp-server`), couvrant Jira, Confluence, Jira Service Management, Bitbucket et Compass, avec OAuth 2.1 ou jetons API ; point d'entrée recommandé `https://mcp.atlassian.com/v2/mcp` (la documentation tierce cite aussi d'anciens chemins `v1/sse` ou `v1/mcp`, à vérifier au moment du branchement) [atlassian/atlassian-mcp-server, README, consulté le 15/10/2026](https://github.com/atlassian/atlassian-mcp-server). L'authentification utilise un enregistrement dynamique de client OAuth (pas d'identifiant client fixe), ce qui fonctionne avec les clients MCP qui gèrent la découverte dynamique [Microsoft, mcscatblog, consulté le 15/10/2026](https://microsoft.github.io/mcscatblog/posts/atlassian-jira-remote-mcp-copilot-studio/).
- **Gratuit :** oui, sans frais séparé, sur tout compte Atlassian Cloud y compris le palier Free (10 utilisateurs) ; les appels comptent dans les limites de débit du palier existant, qui augmentent avec le palier payant ; certaines fonctionnalités enrichies (recherche façon « graphe de travail », Rovo) consomment des crédits Rovo et seront facturées en dépassement à partir du 03/12/2026 selon une source tierce — à vérifier avant la démo si ces outils sont utilisés [synthèses tierces 2026, non vérifiées sur une page Atlassian officielle unique, consulté le 15/10/2026](https://www.pulsemcp.com/servers/atlassian).
- **Outils parlants :** actions nommées par produit (recherche et création d'issues Jira, lecture/écriture de pages Confluence) ; nécessite de ne pas exposer d'emblée les outils Bitbucket/Compass si l'audience RSSI doit rester concentrée sur un scénario simple.
- **Stabilité / versions épinglables :** le dépôt `atlassian/atlassian-mcp-server` est public, mais le passage conseillé « v1 → v2 » documenté en 2026 montre que l'URL d'entrée elle-même a changé une fois déjà ; pas de mécanisme d'épinglage de version pour un serveur distant au-delà de choisir l'URL `v1` ou `v2` explicitement.
- **Conditions d'usage :** CGU Atlassian Cloud standard ; limitation documentée : ne couvre pas Jira Server/Data Center, et Atlassian indique ne pas (encore) répondre aux exigences FedRAMP/HIPAA — point pertinent à mentionner devant un public RSSI, justement pour discuter de la portée d'un déploiement réel [synthèse tierce 2026, consulté le 15/10/2026](https://www.pulsemcp.com/servers/atlassian).
- **Scénario de démo :** avec un compte Atlassian Cloud de démo sur un projet Jira public du bac à sable, demander « liste les tickets ouverts de ce projet » → l'outil de recherche Jira renvoie une liste lisible par un non-ingénieur.
- **Appel refusé (sécurité) :** demander la suppression d'un ticket ou d'un espace Confluence avec un compte de démo qui n'a pas le rôle administrateur → Atlassian documente que les actions de suppression/administration Jira sont réservées aux configurations où l'admin les a activées ; le refus provient du périmètre OAuth de l'utilisateur connecté, pas d'un jeton statique surpuissant — bon exemple pédagogique de « l'IA n'a que les droits de la personne connectée ».

## 3. Notion MCP Server — rang 3

- **Ce que c'est :** le serveur MCP officiel hébergé par Notion, construit sur le paquet `workers-oauth-provider` de Cloudflare ; transport recommandé Streamable HTTP à `https://mcp.notion.com/mcp`, et SSE à `https://mcp.notion.com/sse` pour les clients plus anciens [Notion Developers, consulté le 15/10/2026](https://developers.notion.com/guides/mcp/get-started-with-mcp).
- **Gratuit :** la connexion elle-même ne coûte rien et fonctionne sur un espace de travail Notion gratuit ; certains outils (recherche de sources connectées, filtres de recherche avancés, requêtes SQL multi-sources) nécessitent Notion AI ou un palier Business/Enterprise et affichent un statut `plan_required`/`upgrade_required` dans le client [Notion Developers, « Supported tools », consulté le 15/10/2026](https://developers.notion.com/guides/mcp/mcp-supported-tools).
- **Outils parlants :** noms très clairs pour un non-ingénieur (`notion-search`, `notion-create-pages`, `notion-update-page`, `notion-create-comment`…) ; Notion étiquette elle-même chaque outil « Read-only » ou « Destructive » dans l'onglet Outils du client, ce qui est directement exploitable pour une pédagogie sur l'autorisation [TrueFoundry, consulté le 15/10/2026](https://www.truefoundry.com/blog/notion-mcp-server) ; [Notion, « Security best practices for Agent connections », consulté le 15/10/2026](https://www.notion.com/help/security-best-practices-for-agent-connections).
- **Stabilité / versions épinglables :** pas de version de protocole figée documentée par Notion pour le serveur hébergé ; une alternative auto-hébergée existe (`mcp-notion-server` côté communauté) si un épinglage de version précis est requis, mais elle sort du périmètre « gratuit et sans administration » recherché ici.
- **Conditions d'usage :** CGU Notion standard. Point de vigilance pour la démo RSSI : selon une analyse tierce, le serveur hébergé n'a qu'une seule portée OAuth « par défaut » donnant accès à l'ensemble de l'espace de travail autorisé, sans portée « lecture seule » garantie par le fournisseur — Notion recommande en pratique de créer un compte d'intégration dédié et de limiter manuellement les outils actifs dans les réglages de l'agent, plutôt que de compter sur une portée OAuth restreinte [synthèse tierce 2026, non confirmée par Notion elle-même, consulté le 15/10/2026](https://www.truefoundry.com/blog/notion-mcp-server) ; [Notion, sécurité, consulté le 15/10/2026](https://www.notion.com/help/security-best-practices-for-agent-connections).
- **Scénario de démo :** demander « cherche la page "Compte-rendu" dans cet espace de démo » → `notion-search` renvoie un résultat lisible sans jargon.
- **Appel refusé (sécurité) :** demander la suppression/l'archivage d'une page via un outil étiqueté « Destructive » → si le client MCP honore l'annotation `destructiveHint: true`, il demande confirmation ; dans WaveStack, c'est l'onglet « Autorisation » qui peut bloquer cet appel avant exécution — bon exemple de défense en profondeur quand le fournisseur ne garantit pas lui-même un mode lecture seule.

## Limites de cette recherche

- Recherche faite uniquement via web (pas de rapport externe fourni, pas d'essai réel de connexion aux trois serveurs — aucune connexion n'a été établie, conformément à la consigne « pas de serveur lancé »).
- Plusieurs points (statut GA exact de GitHub MCP, URL `v1`/`v2` d'Atlassian, nombre exact d'outils Notion) varient selon les sources tierces consultées et devront être revérifiés au moment du branchement effectif dans WaveStack, idéalement sur la documentation officielle du jour.
- Le contexte local lu (`src/wavestack/mcp/servers.py`) montre que WaveStack attend un couple `(id, url)` par serveur public et un fichier `content/mcp.yaml` pour les textes affichés ; aucun des trois candidats n'a été testé contre le code WaveStack lui-même.

## Sources

- [GitHub Docs — Set up the GitHub MCP server](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/set-up-the-github-mcp-server)
- [github/github-mcp-server — policies-and-governance.md](https://github.com/github/github-mcp-server/blob/main/docs/policies-and-governance.md)
- [github/github-mcp-server (dépôt)](https://github.com/github/github-mcp-server)
- [atlassian/atlassian-mcp-server (dépôt officiel)](https://github.com/atlassian/atlassian-mcp-server)
- [Microsoft mcscatblog — Wiring up the Jira (Atlassian) Remote MCP server in Copilot Studio](https://microsoft.github.io/mcscatblog/posts/atlassian-jira-remote-mcp-copilot-studio/)
- [PulseMCP — Official Jira & Confluence MCP Server](https://www.pulsemcp.com/servers/atlassian)
- [Notion Developers — Connect to Notion MCP](https://developers.notion.com/guides/mcp/get-started-with-mcp)
- [Notion Developers — Supported tools](https://developers.notion.com/guides/mcp/mcp-supported-tools)
- [Notion — Security best practices for Agent connections](https://www.notion.com/help/security-best-practices-for-agent-connections)
- [TrueFoundry — Notion MCP Server: Tools, Setup & Safe Access](https://www.truefoundry.com/blog/notion-mcp-server)
