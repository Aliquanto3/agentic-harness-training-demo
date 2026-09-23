# Rapprochement brief → PRD : WaveStack

Entrées : `briefs/brief-agentic-harness-training-demo-2026-09-22/brief.md` et `addendum.md`.
Cibles : `prd.md` et `addendum.md` (dossier PRD).
Règle appliquée : ce que le PRD tranche explicitement (11 briques avec sous-agent et Headroom, Caveman en V1, liste d'outils, modèle de 2B au plus, clients en V2) n'est pas signalé comme écart.

## Écarts brief → PRD

### E1. Imaginer des usages métier : aucune fonctionnalité ne le porte (haute)
- **Source** (brief, Executive Summary et Who This Serves) : « puis imaginer des usages dans leur propre métier » ; « objectif : qu'ils repartent avec le vocabulaire et les repères [...] et imaginer des cas d'usage dans leur métier ».
- **PRD** : présent en §1 (Vision), dans les JTBD (§2.1) et en SM-4, mais SM-4 est le seul indicateur principal sans « Valide FR-… ». Les scénarios (FR-38) sont découpés par brique, pas par métier. Les practices n'apparaissent que dans la description des hooks (§4.8).
- **Correction** : ajouter à FR-6 ou FR-38 un exemple d'usage métier par brique, rattaché à une practice (hooks → SOC/DLP, MCP public → souveraineté, RAG → BA/PO…), et faire valider SM-4 par cette exigence.

### E2. Participant actif devenu spectateur (moyenne)
- **Source** (brief, Executive Summary) : « Chaque brique s'active ou se désactive en direct, et l'utilisateur voit simultanément… » ; les utilisateurs primaires sont les collègues formés.
- **PRD** : §2.3 : « le formateur est seul aux commandes, WaveStack est projeté » ; le participant « regarde WaveStack projeté » (Glossaire). La manipulation directe est réservée aux profils techniques qui installent l'outil.
- **Correction** : dire en §2.3 si ce choix est voulu et prévoir un moment où les participants manipulent (prompts proposés par la salle, exercice en binôme sur un poste installé), sans quoi l'appropriation visée par le brief repose uniquement sur l'observation.

### E3. Priorité de l'effort sur MCP, skills et hooks diluée (moyenne)
- **Source** (brief, The Solution) : « l'effort porte sur MCP, skills et hooks, qui sont le vrai cœur pédagogique pour une audience qui maîtrise déjà les bases ».
- **PRD** : §7.1 dit seulement « MCP, skills et hooks traités avec la même profondeur que les briques de base » (logique de parité, pas de priorité). Le PRD ajoute sous-agent, compression, sessions enregistrées et rejeu, et le risque « Périmètre V1 large » (§9) renvoie l'ordre de priorité aux epics.
- **Correction** : écrire en §7.1 que MCP, skills et hooks passent avant le sous-agent et Headroom en cas d'arbitrage, conformément à SM-C2.

### E4. Ordre de progression pédagogique non fixé comme exigence (moyenne)
- **Source** (brief, The Solution) : « La progression pédagogique suit l'ordre : LLM nu → raisonnement → mémoire courte → prompt système → mémoire globale → outils → RAG (simple, puis reranking) → MCP (documentation complète, puis lazy loading) → skills → hooks. »
- **PRD** : FR-38 exige un parcours ordonné sans donner l'ordre. La Vision (§1) donne une liste incomplète (sans mémoire globale ni compression), et la place du sous-agent et de la compression dans le parcours n'est dite nulle part. FR-21 propose une bascule entre les deux modes sans l'ordre « d'abord documentation complète, puis lazy loading ».
- **Correction** : inscrire dans FR-38 l'ordre du brief, en y plaçant le sous-agent et la compression (par exemple après les hooks), et préciser que chaque module part de la documentation complète avant le lazy loading.

### E5. Question UX « fusion des vues » déformée (moyenne)
- **Source** (brief, Scope ; addendum du brief, Points ouverts) : « la fusion ou non des vues LLM et harnais » ; « ou de faire de la vue "LLM" une extension de la vue "humain", plus un onglet dédié RAG ».
- **PRD** : §4.1 : « fusion des vues humain et harnais ». Le Glossaire et FR-2 fusionnent déjà les vues LLM et harnais en une seule « vue harnais », ce qui tranche la question de fait. L'addendum du PRD présente pourtant cette question comme ouverte (« fusionner les vues LLM et harnais… À trancher »).
- **Correction** : reformuler §4.1 avec les options du brief (vues LLM et harnais séparées ou fusionnées, vue LLM comme extension de la vue humain, onglet RAG), ou dire explicitement que le PRD fusionne les vues LLM et harnais et que seule la découpe en volets reste ouverte.

### E6. La confusion « plugin » n'est pas traitée (basse)
- **Source** (brief, The Problem) : « confondent souvent skill, plugin, outil et MCP ».
- **PRD** : repris en §1, mais « plugin » ne figure ni dans le Glossaire ni dans aucune exigence. §4.7 distingue skill, outil, MCP et prompt système, pas plugin.
- **Correction** : ajouter « plugin » au Glossaire (un paquet qui regroupe skills, hooks, MCP…) et l'intégrer à l'explication de FR-6 ou de §4.7.

### E7. Practice « transformation numérique » omise (basse)
- **Source** (brief, Who This Serves) : « …souveraineté, numérique responsable, transformation numérique ».
- **PRD** : §2.1 énumère les practices sans « transformation numérique ».
- **Correction** : ajouter « transformation numérique » à la liste des practices du §2.1.

### E8. Question « solution tierce » non outillée (basse)
- **Source** (brief, Success Criteria) : « Se poser la bonne question sur une solution agentique tierce : où est hébergé le harnais, où sont hébergées les données, où est hébergé le LLM. »
- **PRD** : SM-3 mesure ce réflexe « face à une solution tierce décrite en exercice », mais aucune exigence ne fournit cet exercice. FR-38 (« Où vont mes données ? ») porte sur WaveStack lui-même.
- **Correction** : ajouter à FR-38 un exercice de transposition : une solution agentique tierce fictive à analyser selon les trois lieux d'hébergement.

### E9. Skills « amusants » : ton ludique perdu et second skill non défini (basse)
- **Source** (addendum du brief, Points ouverts) : « Skills "amusants" (ex. Caveman) ».
- **PRD** : FR-23 exige « au moins deux skills », mais seul Caveman est nommé et l'intention ludique n'apparaît plus.
- **Correction** : proposer en FR-23 un second skill (`[ASSUMPTION]`) et garder l'intention d'un skill ludique et mémorable.

### E10. Filiation wavelocalai et ADN « IA locale responsable » (basse)
- **Source** (brief, Vision) : « cohérent avec l'ADN "IA locale responsable" déjà porté par des initiatives internes comme wavelocalai ».
- **PRD** : mentionné seulement dans l'addendum, comme repo technique. La Vision du PRD parle de numérique responsable sans cette filiation, qui sert pourtant d'argument interne et client.
- **Correction** : ajouter en §1 (Trajectoire) une phrase qui situe WaveStack dans la lignée de wavelocalai.

### E11. Risque « conception entièrement nouvelle » absent (basse)
- **Source** (addendum du brief) : « Aucun MCP, skill ou hook dans le repo : ces briques n'ont pas de précédent réutilisable, conception entièrement nouvelle. »
- **PRD** : absent du §9, alors que ces trois briques forment le cœur pédagogique.
- **Correction** : ajouter au §9 le risque d'estimation sur MCP, skills et hooks (aucun code à reprendre) avec une parade (les prototyper en premier).

## Contradictions internes du PRD

- **C1 (moyenne).** NFR-3 cite « outil de recherche web » parmi les briques réseau, alors que FR-13 reporte la recherche web en V2. Remplacer par « outils réseau de FR-13 (jours fériés, Wikipedia) ».
- **C2 (basse).** L'addendum du PRD renvoie à « (Q2) » pour la question des volets, qui est la question 1 du §10 (la Q2 porte sur la publication open source). Corriger le renvoi.
- **C3 (basse).** FR-5 donne en exemple « le lazy loading MCP exige la brique MCP », mais le lazy loading est un mode de FR-21, pas une brique du Glossaire (le reranking pose la même question). Soit ajouter au Glossaire la notion de « sous-option d'une brique », soit changer l'exemple.
- **C4 (basse).** La Vision (§1) liste 9 briques, sans mémoire globale ni compression, alors que le Glossaire en compte 11 et que le §9 parle de « 11 briques ». Aligner la liste de la Vision.
- **C5 (basse).** UJ-4 (scénario « Où vont mes données ? ») est étiqueté « cible V2 », alors que FR-38 exige ce scénario en V1 et que SM-3 s'appuie dessus. Préciser que le scénario est V1 et que seul son usage en clientèle relève de la V2.
- **C6 (basse).** Au §2.2, l'intitulé « clients en autonomie » est suivi d'une explication sur la « démo client, menée par un formateur », et SM-7 (montré à un client) est un indicateur V1 alors que la démo client relève de la V2 (§7.2). Clarifier que SM-7 est un signal opportuniste et non un objectif V1.
