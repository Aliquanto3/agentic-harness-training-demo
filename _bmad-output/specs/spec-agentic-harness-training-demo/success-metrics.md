# Indicateurs de succès — WaveStack

Mesure : questionnaire court en fin de session, plus une question ouverte sur les idées d'usage. Anaël le construit avant la session pilote. Les cibles autres que SM-1 sont à confirmer après la session pilote (voir Assumptions de SPEC.md).

## Principaux

- **SM-1 : Compréhension des briques.** Part des participants qui savent expliquer ce qu'ajoutent un skill, un MCP, un hook et un harnais à un LLM nu. Cible : 80 % ou plus. Valide CAP-5 à CAP-29 (activation et explication des briques).
- **SM-2 : Trois ingénieries.** Part des participants qui distinguent prompt, context et harness engineering. Cible : 70 % ou plus. Valide CAP-6, CAP-31, CAP-32, CAP-33.
- **SM-3 : Réflexe hébergement.** Part des participants qui, face à une solution tierce décrite en exercice, posent la question de l'hébergement du harnais, des données et du modèle. Cible : 80 % ou plus. Valide CAP-3, CAP-23, CAP-40.
- **SM-4 : Idées d'usage.** Part des participants qui formulent au moins une idée d'application agentique pour leur métier. Cible : 70 % ou plus. Valide CAP-42.

## Secondaires

- **SM-5 : Installation.** Part des participants qui tentent l'installation (profils techniques, en amont ou après la session) et réussissent sur leur poste professionnel sans droits admin, en moins de 20 minutes. Cible : 80 % ou plus. Valide CAP-37 à CAP-39.
- **SM-6 : Fiabilité en session.** Part des sessions menées sans repli forcé (plantage, blocage du modèle). Cible : 90 % ou plus. Valide NFR-8 et CAP-40.
- **SM-7 : Présentable en clientèle.** WaveStack est montré au moins une fois à un client sans adaptation majeure. Cible V2, sans chiffre en V1. Valide NFR-10, NFR-11 et CAP-40. La validation par Wavestone de l'usage en clientèle n'est pas requise pour l'usage interne ; à obtenir avant toute présentation client (V2).

## Contre-indicateurs (à ne pas optimiser)

- **SM-C1 : Qualité des réponses du modèle.** Améliorer les réponses au prix d'un modèle plus gros ou d'un contexte masqué trahirait l'objectif. Contrebalance SM-6.
- **SM-C2 : Nombre de briques et de fonctionnalités.** Ajouter des briques pour paraître complet dilue la progression. Contrebalance SM-1.
- **SM-C3 : Vitesse perçue.** Cacher des étapes pour aller plus vite retire de la transparence. Contrebalance NFR-1.
