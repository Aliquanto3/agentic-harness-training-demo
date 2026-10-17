# Corpus Exemplia enrichi et jeu de questions

## Corpus

**L'existant.**
- 8 documents par langue, d'environ 330 mots, dans `content/corpus/*.md`, avec des copies dans `content/i18n/{en,de}/corpus/`.
- La liste est déclarée dans `content/rag.yaml:52-77`.
- Les thèmes : mots de passe, télétravail, classification, incidents, données personnelles, IA générative, déplacements et sauvegardes.
- Deux renvois implicites existent :
  - `ia_generative.md:7` renvoie à `classification.md:5` ;
  - `sauvegardes.md:13` renvoie à `incidents.md`.

**La cible** : 25 à 30 documents de la même entreprise fictive, pour environ 12 000 tokens par langue. Les 8 documents existants restent, éventuellement retouchés pour expliciter des renvois. Les documents ajoutés doivent couvrir :

| Besoin | Contenu attendu | Sert |
|---|---|---|
| Multi-sauts | Au moins deux chaînes de 2 à 3 documents qui se renvoient (ex. politique → procédure → annexe de contacts) | CAP-2, CAP-3 (décomposition), GraphRAG |
| Temporel | Un document en deux versions datées (v1 périmée, v2 en vigueur), plus une note de changement | CAP-2, mise à jour (CAP-8) |
| Interlingue | Trois documents dans une seule langue (ex. une note du siège allemand en de seulement, une procédure anglaise en en seulement) | Questions posées dans une autre langue |
| Global | Assez de documents d'un même thème pour qu'une question de synthèse demande plusieurs sources | GraphRAG global, RAPTOR, LLM Wiki |
| Sans réponse | Thèmes voisins absents du corpus | Refus attendu |
| Droits | Un marquage `audience: all` ou `audience: hr` sur chaque document ; 3 à 4 documents RH (rémunérations, dossier disciplinaire fictif) | CAP-15 |
| Document piégé | Un document qui porte une instruction cachée (injection indirecte) et une affirmation fausse optimisée pour une question cible (PoisonedRAG) ; inactif par défaut | CAP-13 |
| Sentinelle | Un document au contenu reconnaissable (code fictif unique) ; inactif par défaut, activé pour la démonstration d'effacement | CAP-14 |

**Règles.**
- Le contenu est entièrement fictif, sans donnée personnelle réelle.
- Les documents monolingues font exception au contrôle de miroir i18n : ils sont déclarés comme tels dans `content/rag.yaml`, et le test les exempte nommément.
- Les documents piégé et sentinelle sont dans le dépôt, mais exclus de l'index tant qu'on ne les active pas.

## Jeu de questions

Il est déclaré dans `content/` en fr, en et de, avec au moins 3 questions par type.

| Type | Exemple d'intention | Attendu |
|---|---|---|
| Factuelle | Un chiffre d'une politique | Réponse et passage |
| Multi-sauts | Une réponse qui exige deux documents liés | Réponse et passages des deux documents |
| Globale | Les grands thèmes de la sécurité dans l'entreprise | Synthèse et ensemble de documents attendus |
| Sans réponse | Un thème absent | « Je ne sais pas » ; aucun passage attendu |
| Temporelle | La règle en vigueur, alors que la v1 est périmée | Réponse issue de la v2 ; le passage de la v1 est marqué « piège » |
| Interlingue | Une question en fr sur la note qui n'existe qu'en de | Réponse et passage dans l'autre langue |
| Suivi de conversation | « Et pour les prestataires ? » après une question | Question autonome attendue et passage |

Chaque entrée porte :
- `id` ;
- `type` ;
- `question` (avec l'historique pour le suivi) ;
- `answer` ;
- `expected_passages` (document et extrait) ;
- `audience`, le cas échéant.

Un test vérifie que chaque extrait attendu existe dans le document cité, dans chaque langue où la question existe.

Une annotation humaine (verdict par critère) accompagne au moins une question par type : elle sert à la vue Évaluer.
