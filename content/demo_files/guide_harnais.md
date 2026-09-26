# Guide du harnais d'agent

Document de démonstration de WaveStack, volontairement long : il sert à montrer la
délégation à un sous-agent. Texte original, non confidentiel.

## 1. Le modèle et le harnais

Un modèle de langage ne fait qu'une chose : il lit une suite de tokens et prédit la
suite la plus probable. Il n'a ni mémoire entre deux appels, ni horloge, ni accès aux
fichiers, ni moyen d'agir sur le monde. Tout ce qui ressemble à un agent capable de
chercher, de lire, de calculer ou d'écrire vient du code qui l'entoure : le harnais.

Le harnais prépare le contexte avant chaque appel, lit la sortie du modèle, exécute les
actions demandées et décide s'il faut rappeler le modèle. Deux agents construits sur le
même modèle peuvent donc se comporter très différemment : la différence tient au harnais,
pas au modèle.

## 2. Le contexte, une ressource rare

Le contexte est le texte complet que le modèle lit à chaque appel. Sa taille est bornée
par la fenêtre de contexte du modèle, comptée en tokens. Une partie de la fenêtre est
réservée à la réponse ; le reste est partagé entre le prompt système, l'historique de la
conversation, la description des outils, les documents retrouvés et les résultats
d'outils.

Chaque token lu coûte du temps de calcul, surtout sur un ordinateur sans carte
graphique : un contexte deux fois plus long met à peu près deux fois plus de temps à être
lu. Un bon harnais économise donc le contexte. Il n'y met que ce qui sert à la tâche, il
retire ce qui ne sert plus, et il résume ce qui est trop long.

## 3. La mémoire

La mémoire courte réinjecte les échanges précédents à chaque appel : sans elle, le modèle
oublie tout d'un message à l'autre. Elle grossit à chaque tour, jusqu'à remplir la
fenêtre. Plusieurs stratégies la contiennent : la fenêtre glissante, qui ne garde que les
échanges récents ; la compaction, qui résume les anciens échanges ; le retrait des vieux
résultats d'outils, souvent les plus volumineux.

La mémoire globale, elle, survit à la conversation : c'est un fichier que le harnais
relit à chaque tour et que le modèle peut compléter quand il apprend quelque chose
d'utile sur l'utilisateur.

## 4. Les outils

Un outil est une fonction que le harnais sait exécuter : lire l'heure, calculer, lire un
fichier, interroger un service. Le harnais décrit chaque outil au modèle, avec son nom,
ce qu'il fait et ses paramètres. Quand le modèle veut s'en servir, il écrit un appel dans
un format convenu ; le harnais le repère, vérifie les arguments, exécute l'outil et
réinjecte son résultat dans le contexte. Le modèle n'exécute jamais rien lui-même.

Les descriptions d'outils ont un coût : elles occupent le contexte à chaque appel, même
quand l'outil ne sert pas. Avec des dizaines d'outils, ce coût devient énorme. Le lazy
loading le réduit : le harnais ne donne qu'une ligne par outil, et ne charge la
documentation complète que lorsque le modèle la demande.

## 5. La boucle d'agent et ses bornes

Un tour d'agent est une boucle : appel au modèle, lecture de la sortie, exécution des
outils demandés, réinjection des résultats, puis nouvel appel, jusqu'à une réponse sans
appel d'outil. Une boucle sans limite peut tourner indéfiniment, par exemple si le modèle
redemande le même outil ou écrit des appels mal formés.

Le harnais pose donc trois bornes. La première limite le nombre d'appels au modèle dans
un tour. La deuxième limite les nouveaux essais après un appel refusé, mal formé ou vers
un outil inconnu. La troisième réserve une place fixe à la réponse, pour qu'une sortie
trop longue soit coupée proprement au lieu de déborder. Quand une borne est atteinte, le
harnais arrête la boucle et l'explique : c'est du code qui décide, pas le modèle.

## 6. Les hooks

Un hook est un morceau de code que le harnais appelle à un point fixe du tour : à la
réception du message, avant chaque appel au modèle, avant et après chaque outil, en fin
de tour. Un hook peut laisser passer, modifier, bloquer ou demander l'avis d'un humain.
Il sert de garde-fou (interdire la lecture d'un dossier sensible), de journal d'audit,
d'injection de contexte (la date du jour) ou de validation humaine avant toute sortie
réseau. Le modèle ne peut pas contourner un hook, puisqu'il n'est pas dans la boucle de
décision : le hook s'exécute avant ou après lui.

## 7. Les skills et le chargement progressif

Un skill est un ensemble d'instructions pour un type de demande, par exemple rédiger un
compte rendu de réunion. Tant qu'il ne sert pas, seuls son nom et sa description occupent
le contexte. Quand une demande s'y prête, le modèle le charge par un méta-outil et ses
instructions complètes rejoignent le contexte. On ne paie ainsi les tokens d'un skill que
lorsqu'il sert.

## 8. Le sous-agent

Certaines sous-tâches consomment beaucoup de contexte pour un résultat court : lire un
long document pour en extraire cinq idées, parcourir une page web pour trouver un chiffre.
Si l'agent principal fait ce travail lui-même, tout le document entre dans son contexte et
y reste pour la suite du tour, puis dans l'historique des tours suivants.

Le harnais peut plutôt déléguer la sous-tâche à un sous-agent. C'est le même modèle, mais
appelé dans un contexte propre : un prompt système court, la tâche, et quelques outils.
Le sous-agent ne voit ni la conversation ni le prompt principal. Il lit le document, en
tire le résultat demandé, et seul ce résultat revient dans le contexte principal.
L'économie est directe : les milliers de tokens du document restent dans le contexte du
sous-agent, qui disparaît une fois la tâche finie, et l'agent principal ne reçoit que
quelques centaines de tokens.

La délégation a aussi ses limites. Le sous-agent a ses propres bornes, plus serrées que
celles du tour principal. Si son contexte déborde ou s'il n'aboutit pas, le harnais
réinjecte une erreur explicite et le tour principal continue. Et comme le modèle est le
même, déléguer ne rend pas le travail plus intelligent : cela le rend moins coûteux pour
le contexte principal. Sur un petit modèle local, les deux contextes sont lus l'un après
l'autre par la même instance, ce qui se voit dans le temps du tour.

## 9. Où vont les données

Tant que tout tourne sur le poste, rien ne sort : le modèle, le harnais, les fichiers et
les outils locaux restent sur la machine. Une sortie réseau apparaît dès qu'un outil
interroge un service public, qu'un serveur MCP distant est connecté, ou que le modèle
lui-même est hébergé dans le cloud. Dans ce dernier cas, chaque appel envoie le contexte
entier au fournisseur, sous-agent compris. Un harnais honnête montre ces sorties, en
affiche le contenu exact et permet de les faire valider par un humain avant l'envoi.

## 10. À retenir

- Le modèle prédit du texte ; le harnais en fait un agent.
- Le contexte est rare : chaque brique du harnais y ajoute des tokens, avec un gain et un
  coût.
- Les outils, les skills et la documentation se chargent à la demande pour économiser le
  contexte.
- Les bornes et les hooks sont du code : ils décident à la place du modèle quand il le
  faut.
- Le sous-agent isole une sous-tâche volumineuse : seul son résultat revient dans le
  contexte principal.
