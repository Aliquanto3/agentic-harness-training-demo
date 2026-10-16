# Sécurité, garde-fous et FinOps visible

[← Retour au README](../README.md)

Ce document décrit ce que WaveStack contrôle, refuse et journalise (V1.1, vague 2). Il
s'adresse à un RSSI ou à un testeur non développeur. Pour l'interface générale, voir le
[guide d'utilisation](guide.md). Pour l'installation et le proxy, voir
[l'installation détaillée](installation.md).

Quelques mots utilisés ici :

- **Outil MCP** : une action que le modèle peut demander au harnais (lire un glossaire, créer
  un fichier, lire des alertes GitHub…). MCP est le protocole qui relie le harnais à ces outils.
- **Séquence** et **Orchestration** : deux volets de l'écran principal. La Séquence montre
  chaque échange pas à pas ; l'Orchestration détaille chaque appel au modèle.
- **Token** : un morceau de mot. Les modèles comptent leur lecture et leur écriture en tokens,
  et les fournisseurs cloud facturent au token.

- [Page Sécurité et bouton Journal](#page-sécurité-et-bouton-journal)
- [Autorisations des outils MCP](#autorisations-des-outils-mcp)
- [Connexion à GitHub](#connexion-à-github)
- [Garde-fous (toxicité, données personnelles, injection)](#garde-fous-toxicité-données-personnelles-injection)
- [Ce que le harnais ne protège pas](#ce-que-le-harnais-ne-protège-pas)

## Page Sécurité et bouton Journal

L'onglet **Sécurité** de la barre de navigation (`/security`, entre MCP et Diagnostic) est
fait pour un RSSI. Il ne règle rien : les réglages restent dans l'Atelier MCP et dans la brique
Garde-fous. La page montre, de haut en bas :

- **Quatre cartes-questions**, calculées sur la séance en cours (aucun chiffre figé) :
  - « Quels outils peuvent écrire ? » : le nombre d'outils d'écriture, et combien sont
    autorisés, sur demande ou refusés ;
  - « Qui a autorisé quoi ? » : les autorisations que vous avez données une fois ;
  - « Qu'est-ce qui a été bloqué ? » : les appels d'outil refusés et les messages bloqués ;
  - « Qu'est-ce qui n'est pas couvert ? » : le nombre de limites connues.
- **La matrice des risques** : sept lignes (outil, nature, risque, règle). La règle est lue en
  direct. Elle affiche « Mixte (selon l'outil) » quand les outils d'une même ligne n'ont pas
  la même règle. Un lien « Régler dans MCP » mène à l'Atelier MCP.
- **Les contrôles actifs**, à déplier : autorisations des outils, les trois garde-fous, les
  hooks (contrôles automatiques avant ou après une étape), la liste blanche réseau (les seuls
  sites joignables) et la connexion GitHub.
- **Le journal de sécurité complet**, le plus récent en haut. Chaque ligne se déplie et donne
  la raison : qui a décidé, et ce qui n'est pas parti. Le bouton « Télécharger (CSV) »
  l'enregistre en tableur.
- **Les 12 limites** de ce que le harnais ne protège pas (voir
  [plus bas](#ce-que-le-harnais-ne-protège-pas)).

La page se met à jour en direct pendant la séance.

Le bouton **Journal** est dans la barre de navigation des six pages. Son compteur rouge
compte les refus et les blocages de la séance. Il ne revient à zéro qu'au redémarrage de
WaveStack, comme le journal. Un clic ouvre les 5 derniers événements (outil ou garde-fou,
décision, raison). Le lien « Tout le journal » ouvre la page Sécurité.

## Autorisations des outils MCP

Dans l'Atelier MCP, chaque outil a un **niveau de risque** (faible, moyen ou élevé, fixe). Il
a aussi une **règle** (Autoriser, Demander ou Refuser), que vous pouvez changer. Les deux
s'affichent sous l'outil choisi dans « Serveurs et outils ». Règles par défaut :

| Outil | Risque | Règle |
|---|---|---|
| Glossaire, lecture de la RAM et du système, outils de data.gouv.fr et de Microsoft Learn | faible | Autoriser |
| Créer un fichier ou un dossier (dans le bac à sable) | moyen | Demander |
| Capture d'écran | élevé | Demander |
| Lecture GitHub (alertes de secrets et Dependabot, fichiers, tickets) | moyen | Autoriser |
| Écriture GitHub (fusion ou création de PR) et tout outil GitHub non listé | élevé | Refuser |

Le **bac à sable** est un dossier réservé de WaveStack. Les outils locaux n'écrivent que
dedans. Un fichier créé y fait au plus 1 Mo. Seules les 20 dernières captures d'écran sont
gardées.

- **Refuser** : l'outil n'est jamais exécuté. La Séquence montre le refus et sa raison. Le
  modèle reçoit un message d'erreur, qu'il vous restitue.
- **Demander**, dans l'Atelier MCP : l'appel attend votre décision. Une étape « à décider »
  apparaît dans la Séquence, avec deux boutons, « Autoriser une fois » et « Refuser ». Sans
  réponse au bout de 2 minutes, l'appel est refusé.
- **Demander**, dans la conversation (brique MCP de l'écran principal) : seul l'Atelier MCP
  peut demander votre accord. Dans la conversation, Demander vaut donc refus, journalisé
  comme tel.
- Chaque décision rejoint le journal de sécurité : autorisé, autorisé une fois, refusé, délai
  dépassé ou annulé. Le journal ne contient jamais de secret.

## Connexion à GitHub

Dans le bloc GitHub de l'Atelier MCP, le bouton **« Se connecter à GitHub »** affiche un code.
Vous le saisissez sur `github.com/login/device`. Une fois connecté, le jeton (la clé d'accès
donnée par GitHub) reste valable 8 h. Il est renouvelé tout seul pendant 6 mois. Ensuite, il
passe à l'état « expiré », avec un bouton « Se reconnecter ». Un appel GitHub sans jeton
valable est refusé avec un message clair, avant tout envoi. Le jeton est enregistré sur ce
poste seulement, hors du dépôt. Il n'apparaît jamais dans le journal ni dans la Séquence.

Un appel d'outil GitHub peut être refusé à trois niveaux :

| Niveau | Ce qui se passe | Ce que vous voyez |
|---|---|---|
| Lecture seule côté GitHub | En mode lecture seule, GitHub ne propose pas ses outils d'écriture. WaveStack ne demande pas ce mode, pour montrer son propre refus. Ce cas n'a pas été vérifié en réel. | L'outil n'apparaît pas |
| Politique WaveStack | La règle de l'outil est « Refuser », le cas par défaut pour toute écriture. Rien n'est envoyé à GitHub. | « Refusé par la politique de sécurité… Envoyé à GitHub : non. » |
| GitHub (403) | WaveStack a laissé passer l'appel, mais le compte connecté n'a pas ce droit : GitHub refuse. | « Refusé par GitHub (403)… Envoyé à GitHub : oui » |

Un jeton expiré donne aussi « Envoyé à GitHub : non » : l'appel est arrêté avant l'envoi. Les
refus de la politique, du jeton expiré et du 403 sont journalisés.

## Garde-fous (toxicité, données personnelles, injection)

La brique **Garde-fous** est dans le panneau des briques, après Hooks. Elle contrôle votre
message avant le modèle, et la réponse finale avant vous. Elle ne contrôle pas les résultats
d'outils, le raisonnement, le sous-agent ni les ateliers (LLM, RAG, MCP). Trois garde-fous,
chacun avec son propre réglage :

| Garde-fou | Modes | Ce qu'il détecte |
|---|---|---|
| Toxicité | Bloquer, Signaler, Désactivé | Un message insultant ou agressif, en français comme en anglais |
| Données personnelles | Bloquer, Masquer, Désactivé | Téléphone, e-mail, IBAN, numéro de sécurité sociale, SIRET, plaque, passeport… |
| Injection de prompt (optionnel) | Bloquer, Signaler, Désactivé | Une consigne cachée qui tente de détourner le modèle |

- **Bloquer** : le message ne part pas au modèle, ou la réponse ne vous est pas montrée.
- **Signaler** : un bandeau sous le message donne le verdict, détaillé dans l'Orchestration.
  Rien n'est changé.
- **Masquer** (données personnelles seulement, à la place de Signaler) : le texte masqué
  (`[TÉLÉPHONE]`, `[E-MAIL]`…) est ce que le modèle reçoit vraiment.
- Chaque garde-fou propose deux exemples prêts à l'emploi (« Essayer : … »). Ils sont
  fabriqués et neutres.

**Installation.** Toxicité et Données personnelles s'installent ensemble, par le bouton
« Installer » de la brique (ou `uv sync --extra guardrails`, voir
[Extras optionnels](installation.md#extras-optionnels)). Le garde-fou **Injection** (Prompt
Guard 2, de Meta) demande en plus un jeton Hugging Face. Il demande aussi que vous acceptiez
la licence Llama 4 Community. La marche à suivre est dans
[Extras optionnels](installation.md#extras-optionnels). Tant qu'il n'est pas installé, il
reste « non installé », sans interrupteur, et le reste du harnais fonctionne.

**Mémoire.** Toxicité et Données personnelles ensemble occupent environ 0,5 Go de RAM
(mesuré). Avec Injection, les trois devraient rester sous 1,5 Go ; la mesure reste à faire sur
le poste de référence.

## Ce que le harnais ne protège pas

La page Sécurité liste 12 limites. Chacune se déplie : pourquoi, et ce qu'il faudrait en
production. Résumé (ce texte est encore un brouillon, à valider) :

- Les garde-fous se trompent (faux positifs, faux négatifs), plus souvent hors de l'anglais.
- Ils ne voient que la conversation principale : ni les outils, ni le sous-agent, ni les
  ateliers. Un très long message n'est analysé qu'en partie. Pour l'injection, ce sont les
  512 premiers tokens. Le verdict le signale.
- Sans Prompt Guard, l'injection indirecte (cachée dans un document ou un résultat d'outil)
  n'est pas détectée.
- L'autorisation porte sur le nom d'un outil, pas sur ce qu'il fait vraiment côté serveur.
- Le jeton GitHub donne tous les droits accordés à l'application GitHub de WaveStack
  (une « OAuth App »), pendant 8 h.
- Ce jeton est stocké en clair sur le poste, protégé par les seuls droits du compte Windows.
- Le bac à sable est un contrôle de chemin dans l'application. Ce n'est ni un conteneur ni un
  compte système isolé.
- La capture d'écran voit tout l'écran, pas seulement WaveStack.
- Le journal n'a pas de valeur d'audit : il est local, non signé, modifiable sur le poste.
- WaveStack ne contrôle pas ce qu'un fournisseur cloud fait des messages qu'il reçoit.
- L'application n'a pas d'authentification. Elle n'écoute que sur ce poste (`127.0.0.1`), et
  toute personne qui utilise le poste y a accès.
- Les coûts et l'empreinte sont des estimations, marquées « ≈ » quand le fournisseur ne
  mesure pas l'usage.

## FinOps visible, cache, compression, sous-agent et mémoire de contexte locale

Les économies du harnais se voient maintenant en tokens et en dollars. Détail complet :
[FinOps](guide.md#finops-coût-estimé-des-appels-cloud) et
[GreenOps](guide.md#greenops-empreinte-estimée-des-appels-au-modèle) dans le guide.

- **Cache de prompt (cloud)** : le fournisseur relit à prix réduit le début d'un message déjà
  envoyé. Une ligne dépliable, dans le compteur de l'appel, montre les tokens relus et le
  montant économisé. Si l'écriture en cache a coûté plus que la relecture, elle dit « … de
  surcoût (écriture) ». Si le fournisseur ne déclare pas le prix du cache, elle dit « prix du
  cache non déclaré », sans inventer d'économie.
- **Compression (Headroom)** : Headroom réduit le texte envoyé au modèle. Sa ligne dans
  l'Orchestration donne le montant économisé en dollars, quand il est connu.
- **Sous-agent** : une ligne dédiée (tokens, coût, empreinte) apparaît sous « Délégation au
  sous-agent ». Elle est déjà comprise dans le total du tour : ne l'ajoutez pas.
- **Mémoire de contexte locale (KV-cache)** : un modèle local garde en mémoire le début de la
  conversation déjà lu. Une ligne « *n* tokens repris sans recalcul · environ *x* s évitées »
  apparaît alors dans le compteur de l'appel.
- **Bilan de la séance** : le bouton **Dépense** de la barre de navigation affiche « Dépense … $
  · économisé … $ ». Il dit « surcoût du cache … $ » si le cache a coûté plus qu'il n'a
  rapporté. En séance locale, sans coût, il dit le temps de calcul évité. Un clic ouvre le
  « Bilan de la séance » : deux barres (sans optimisation, coût réel), le pourcentage
  économisé, la part du cache et de la compression, et un lien « Détail par appel ». Sans
  économie chiffrée, il dit « Aucune économie mesurée pour l'instant ».
