# Sécurité, garde-fous et FinOps visible

[← Retour au README](../README.md)

Ce document décrit ce que WaveStack contrôle, refuse et journalise (V1.1, vague 2), pour un
RSSI ou un lecteur non développeur. Pour l'interface générale, voir le
[guide d'utilisation](guide.md) ; pour l'installation et le proxy, voir
[l'installation détaillée](installation.md).

- [Page Sécurité et bouton Journal](#page-sécurité-et-bouton-journal)
- [Autorisations des outils MCP](#autorisations-des-outils-mcp)
- [Connexion à GitHub](#connexion-à-github)
- [Garde-fous (toxicité, données personnelles, injection)](#garde-fous-toxicité-données-personnelles-injection)
- [Ce que le harnais ne protège pas](#ce-que-le-harnais-ne-protège-pas)

## Page Sécurité et bouton Journal

L'entrée **Sécurité** de la barre de navigation (`/security`, entre MCP et Diagnostic) répond,
pour un RSSI, à quatre questions : quels outils peuvent écrire, qui les a autorisés, qu'est-ce
qui a été bloqué, et qu'est-ce qui n'est pas couvert. La page montre, dépliable :

- la matrice de risques des outils (voir [Autorisations des outils MCP](#autorisations-des-outils-mcp)), avec un lien « Régler dans MCP » ;
- les contrôles actifs : autorisations par outil, les trois garde-fous, les hooks, la liste blanche réseau, la connexion GitHub ;
- le journal complet, avec un bouton « Télécharger le journal (CSV) » ;
- les limites de ce que le harnais ne protège pas (voir [plus bas](#ce-que-le-harnais-ne-protège-pas)).

Le bouton **Journal**, dans la barre de navigation de chaque page, affiche un compteur rouge
des refus et blocages de la séance (remis à zéro seulement au redémarrage de WaveStack, comme
le journal). Son clic ouvre un panneau avec les 5 derniers événements (outil ou garde-fou,
décision, raison) et un lien « Tout le journal » qui ouvre la page Sécurité.

## Autorisations des outils MCP

Dans l'Atelier MCP, chaque outil a un **niveau de risque** (faible, moyen, élevé — fixe) et une
**règle** (Autoriser, Demander, Refuser — modifiable), affichés sous l'outil choisi dans
« Serveurs et outils ». Règles par défaut :

| Outil | Risque | Règle |
|---|---|---|
| Glossaire, lecture RAM/système, outils de lecture de data.gouv.fr et Microsoft Learn | faible | Autoriser |
| Créer un fichier ou un dossier (bac à sable) | moyen | Demander |
| Capture d'écran | élevé | Demander |
| Lecture des alertes GitHub (secrets, Dependabot, issues…) | moyen | Autoriser |
| Écriture GitHub (fusion ou création de PR) et tout autre outil GitHub non listé ici | élevé | Refuser |

- **Refuser** : l'outil n'est jamais exécuté ; la Séquence montre le refus et sa raison ; le
  modèle reçoit un texte d'erreur qu'il restitue à l'utilisateur.
- **Demander** : l'appel attend une décision, affichée comme une étape « à décider » dans la
  Séquence, avec deux boutons, « Autoriser une fois » et « Refuser » (sans fenêtre modale). Sans
  réponse après 2 minutes, l'appel est refusé automatiquement.
- Chaque décision (autoriser, autoriser une fois, refuser, délai dépassé, annulé) rejoint le
  journal de sécurité, sans jamais contenir de secret.

## Connexion à GitHub

Dans le bloc GitHub de l'Atelier MCP, **« Se connecter à GitHub »** affiche un code à saisir sur
`github.com/login/device`. Une fois connecté, le jeton reste valable 8 h (renouvelé tout seul
pendant 6 mois), puis passe à l'état « expiré » avec un bouton « Se reconnecter » ; un appel
GitHub sans jeton valable est refusé avec ce message, jamais une erreur obscure. Le jeton est
enregistré hors du dépôt, sur ce poste seulement, et n'apparaît jamais dans le journal ni dans
la Séquence.

Un appel d'outil GitHub peut être refusé à trois niveaux différents, tous visibles et
journalisés :

| Niveau | Ce qui se passe | Ce que vous voyez |
|---|---|---|
| Lecture seule côté GitHub | Un jeton à lecture seule fait disparaître l'outil d'écriture de la liste : il n'est même pas proposé | L'outil n'apparaît pas |
| Politique WaveStack | La règle de l'outil est « Refuser » (cas par défaut pour toute écriture) : rien n'est envoyé à GitHub | « refusé par la politique de sécurité » |
| GitHub (403) | Le compte connecté n'a pas le droit d'agir : GitHub lui-même refuse | « Envoyé à GitHub : non » |

## Garde-fous (toxicité, données personnelles, injection)

La brique **Garde-fous** du panneau des briques (après Hooks) filtre le message envoyé au
modèle et sa réponse finale — jamais les résultats d'outils, le raisonnement, le sous-agent ni
les ateliers (LLM nu, RAG, MCP). Trois garde-fous, chacun avec son propre réglage :

| Garde-fou | Modes | Ce qu'il détecte |
|---|---|---|
| Toxicité | Bloquer, Signaler, Désactivé | Un message insultant ou agressif, en français comme en anglais |
| Données personnelles | Bloquer, Masquer (remplace « signaler »), Désactivé | Téléphone, e-mail, IBAN, NIR, SIRET, plaque, passeport |
| Injection de prompt (optionnel) | Bloquer, Signaler, Désactivé | Une instruction cachée qui tente de détourner le modèle |

- **Bloquer** : le message ou la réponse n'est jamais vu par le modèle ou par vous.
- **Signaler** : le verdict s'affiche (bandeau sous le message, détail dans Orchestration),
  rien n'est changé.
- **Masquer** (données personnelles) : le texte masqué (`[TÉLÉPHONE]`, `[E-MAIL]`…) est ce que
  le modèle reçoit réellement, pas seulement ce qui s'affiche.
- Chaque garde-fou a deux exemples prêts à l'emploi (« Essayer : … »), neutres et fabriqués,
  sans contenu dangereux réel.

**Installation.** Toxicité et Données personnelles s'installent ensemble par le bouton
« Installer » de la brique (ou `uv sync --extra guardrails`, voir
[Extras optionnels](installation.md#extras-optionnels)). **Injection** (Prompt Guard 2) demande
en plus un jeton Hugging Face et l'acceptation, par vous, de la licence Llama 4 Community :
marche à suivre détaillée dans [Extras optionnels](installation.md#extras-optionnels). Sans ce
jeton, le garde-fou reste « non installé », sans bloquer le reste du harnais. Les trois
garde-fous ensemble restent sous 1,5 Go de mémoire sur le PC de référence.

## Ce que le harnais ne protège pas

La page Sécurité liste, dépliable (pourquoi, et ce qu'il faudrait en production) :

- Les garde-fous se trompent (faux positifs, faux négatifs), plus souvent hors de l'anglais.
- Ils ne voient que la conversation principale, pas les outils, le sous-agent ni les ateliers ;
  un très long message n'est analysé qu'en partie par l'injection (512 premiers tokens).
- Sans Prompt Guard, l'injection indirecte (dans un document ou un résultat d'outil) n'est pas détectée.
- L'autorisation porte sur le nom d'un outil, pas sur ce qu'il fait vraiment côté serveur.
- Le jeton GitHub donne tous les droits accordés par l'OAuth App, pour 8 h.
- Ce jeton, comme le journal, est stocké en clair sur le poste, protégé par les seuls droits du compte Windows.
- Le bac à sable est un contrôle de chemin applicatif, pas un conteneur ni un compte système isolé.
- La capture d'écran voit tout l'écran ouvert, pas seulement WaveStack.
- Le journal n'a pas de valeur d'audit (local, non signé, modifiable par l'utilisateur du poste).
- WaveStack ne contrôle pas ce qu'un fournisseur cloud fait des messages qu'il reçoit.
- L'application n'a pas d'authentification : elle écoute sur `127.0.0.1`, tout utilisateur du poste y a accès.
- Les coûts et l'empreinte affichés sont des estimations, marquées « ≈ » quand l'usage n'est pas mesuré par le fournisseur.

## FinOps visible, cache, compression, sous-agent et mémoire de contexte locale

Les optimisations du harnais se voient maintenant en tokens et en dollars, pas seulement en
principe. Détail complet : [FinOps](guide.md#finops-coût-estimé-des-appels-cloud) et
[GreenOps](guide.md#greenops-empreinte-estimée-des-appels-au-modèle) dans le guide d'utilisation.

- **Cache de prompt (cloud)** : une ligne dépliable dans le compteur de l'appel montre les
  tokens relus et le montant économisé (prix plein, prix payé, écriture séparée, source) ; un
  net négatif se dit « … de surcoût (écriture) ».
- **Compression (Headroom)** : sa ligne d'orchestration existante porte maintenant le montant
  économisé en dollars, quand il est connu.
- **Sous-agent** : une ligne dédiée (tokens, coût, empreinte) apparaît sous « Délégation au
  sous-agent », séparée du total du tour (déjà inclus dedans, jamais à additionner).
- **Mémoire de contexte locale (KV-cache)** : pour un modèle local, une ligne « *n* tokens
  repris sans recalcul · environ *x* s évitées » apparaît dans le compteur de l'appel.
- **Bilan de la séance** : le bouton **Dépense** de la barre de navigation affiche
  « Dépense … $ · économisé … $ » (ou le temps évité, en séance locale sans coût). Son clic ouvre
  le panneau « Bilan de la séance » : deux barres (sans optimisation / coût réel), le
  pourcentage économisé, la répartition cache/compression, et un lien « Détail par appel ».
