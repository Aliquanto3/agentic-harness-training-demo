---
title: Revue de réconciliation — spine d'architecture contre PRD
target: ../ARCHITECTURE-SPINE.md
sources:
  - ../../../prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
  - ../../../prds/prd-agentic-harness-training-demo-2026-09-22/addendum.md
  - ../.memlog.md
date: 2026-09-23
---

# Revue de réconciliation : spine d'architecture contre PRD

## Verdict

Le spine couvre bien le PRD : les 42 FR et les 11 NFR sont liés, et les trois points du §11 confiés à l'architecture sont tranchés. Il reste pourtant quatre trous importants à combler avant les epics :
1. la fenêtre par défaut ne tient pas les scénarios fournis ;
2. aucune règle ne fixe comment les segments deviennent le texte envoyé au modèle, ni comment on attribue les tokens ;
3. il manque le mécanisme par lequel le modèle déclenche les actions autres que les outils, alors que FR-42 en dépend ;
4. des sorties réseau ont lieu sans qu'une brique réseau ait été activée.

Aucun de ces points ne remet en cause le paradigme. Chacun se corrige en modifiant un AD.

Bilan : 0 critique, 4 élevés, 11 moyens, 10 faibles. 8 dérogations volontaires au PRD, à reporter dans le PRD.

## Méthode

J'ai lu chaque FR, NFR, UJ, ligne du tableau des risques (§9), hypothèse du §11 et entrée du glossaire (§3), ainsi que les contraintes implicites (§6, §7, CLAUDE.md), et je les ai confrontés aux AD-1 à AD-22, aux conventions, à la stack et à la section Deferred. Les détails purement UI ne sont retenus que s'ils imposent un invariant. Le fichier EXPERIENCE.md n'a servi qu'à lever deux doutes (bascule d'une brique pendant un tour, jauge).

## Synthèse des constats

| ID | Sévérité | Référence PRD | Sujet |
|---|---|---|---|
| R-01 | élevée | NFR-1, FR-20, FR-21, FR-38, FR-40, FR-9 | Fenêtre de 4 096 tokens (dont 512 pour la sortie) : les scénarios fournis ne tiennent ni dans la fenêtre ni dans la borne de 30 s |
| R-02 | élevée | FR-2, FR-30, FR-41, FR-32, glossaire « Contexte » | Passage des segments aux messages du gabarit et attribution des tokens non définis |
| R-03 | élevée | FR-42, FR-12, FR-21, FR-24, FR-29 | Mécanisme des actions décidées par le modèle (hors outils) et représentation d'une action forcée |
| R-04 | élevée | NFR-3, NFR-4, FR-37, AD-15 | Sorties réseau sans brique activée ; bibliothèques qui contournent `net` |
| R-05 | moyenne | FR-7, FR-11 | Le rejeu restaure le prompt système et les réglages de l'instantané, ce qui annule le changement à comparer |
| R-06 | moyenne | NFR-8, FR-33, FR-34, SM-6 | Un crash natif de llama.cpp, en processus, fait tomber toute l'application |
| R-07 | moyenne | FR-34, NFR-2, glossaire « Fenêtre » | Serveurs externes : `n_ctx` et `num_ctx`, troncature silencieuse, modèle Ollama resté chargé |
| R-08 | moyenne | NFR-2 (et §11) | Budget mémoire : le socle Python et le serveur MCP local ne sont pas comptés |
| R-09 | moyenne | NFR-1 (borne par appel), FR-29 | Réutilisation du cache KV entre les appels d'un tour et après un sous-agent |
| R-10 | moyenne | FR-13, FR-27 (H1), NFR-4 | Outil de lecture de fichier non confiné ; calculatrice |
| R-11 | moyenne | NFR-4 | API locale exposée au CSRF et au DNS rebinding |
| R-12 | moyenne | FR-3, FR-4, FR-34, FR-12, FR-16, FR-27 (H2) | Identité des composants dans les événements ; modèle et fichiers absents du schéma dérivé |
| R-13 | moyenne | FR-1, FR-2, FR-9, FR-15 | Flux de sortie non typé (raisonnement, texte, appel d'outil) |
| R-14 | moyenne | FR-16, UJ-3, FR-34, FR-37 | RAG : voie hors ligne des modèles d'embedding et de reranking, appariement index et embedding |
| R-15 | moyenne | FR-31, NFR-3, NFR-4, NFR-5, NFR-10 | Critères de décision du test préalable Headroom absents d'AD-22 |
| R-16 | faible | FR-5, FR-9, FR-13, FR-18, FR-21, FR-27 | Sous-options de brique absentes du contrat de brique |
| R-17 | faible | FR-27 (H5), FR-22 | Aperçu H5 identique aux données envoyées ; H5 sur les outils MCP publics |
| R-18 | faible | FR-22 | Échanges MCP en stdio (découverte comprise) non tracés explicitement |
| R-19 | faible | FR-13, NFR-11, addendum | Lecture de page web : taille maximale, repli hors ligne, adresse testée au démarrage, page jamais copiée |
| R-20 | faible | FR-20, §9 (pas de réseau) | Serveur MCP public « indisponible jusqu'au redémarrage » : aucune reprise possible |
| R-21 | faible | FR-39, AD-2 | La réinitialisation ne marque pas le journal (reconnexion SSE) |
| R-22 | faible | FR-5, AD-3 | Bascule d'une brique pendant un tour : refusée par le spine, attendue par le PRD et l'UX |
| R-23 | faible | §7.1 | Les AD ne sont pas rattachés aux paliers |
| R-24 | faible | FR-33, FR-12, glossaire « Fenêtre » | Cas limites des capacités : plafond natif, absence de `chat_template`, mémoire sans parseur |
| R-25 | faible | NFR-10, NFR-11 | Fichiers de licence et mentions des tiers |

## Constats détaillés

### R-01 — Fenêtre par défaut et scénarios fournis — élevée

- **Référence PRD.** NFR-1 (« avec la configuration la plus chargée d'un scénario fourni, par exemple le MCP en documentation complète, le premier token arrive en moins de 30 s » ; « la fenêtre de contexte est plafonnée pour tenir ces bornes »), FR-20 (data.gouv.fr ≈ 2 900 tokens), FR-21, FR-38 (« démarrer un module directement, avec les briques des modules précédents déjà actives »), FR-40 (scénario Souveraineté avec data.gouv.fr), FR-9.
- **Constat.**
  - AD-9 fixe une fenêtre de 4 096 tokens, dont 512 réservés à la sortie : il reste 3 584 tokens pour l'entrée. Le module MCP arrive après les modules outils, RAG, mémoire et prompt système, qui restent actifs (FR-38). Les descriptions de data.gouv.fr (2 900 tokens), plus celles des outils natifs, les extraits RAG et le prompt système, dépassent cette entrée par construction. Le scénario central de FR-21 et le scénario Souveraineté de FR-40 déclencheraient donc le dépassement de NFR-8 au lieu de répondre.
  - Le spine estime la lecture du contexte à 60 à 110 tokens/s (section Deferred), soit 2 000 à 3 000 tokens en 30 s. Une fenêtre pleine dépasse donc déjà la borne de NFR-1. Le plafond, tel qu'il est posé, ne « tient » pas NFR-1, contrairement à ce que ce dernier exige.
  - Avec la brique raisonnement, Qwen3.5 produit couramment plus de 512 tokens de réflexion. La sortie est alors coupée par `max_tokens` avant la réponse. Ce cas (arrêt pour cause de longueur) ne figure dans aucun AD comme événement de NFR-8.
- **Correction proposée.**
  - AD-9 : ajouter la règle « le plafond d'entrée est dérivé de la mesure : `entrée_max ≈ débit_lecture_mesuré × 30 s`. La valeur par défaut de la fenêtre et la réserve de sortie se fixent ensemble après `llama-bench` ». Rendre la réserve de sortie dépendante de la brique raisonnement (par exemple 512 sans raisonnement, 1 536 avec), toujours comprise dans la fenêtre.
  - AD-19 : chaque scénario déclare une taille de contexte attendue. Un test `pytest` rend le contexte de chaque scénario fourni avec le tokenizer du modèle par défaut et échoue si `contexte + réserve > fenêtre`. Les scénarios qui démontrent volontairement un dépassement portent un drapeau `expects_overflow`.
  - Arbitrage à remonter au PRD : dans le scénario MCP en documentation complète, soit on montre Microsoft Learn (1 250 tokens) et data.gouv.fr sert à la démonstration volontaire du dépassement, soit le module MCP désactive les briques des modules précédents qui pèsent lourd (RAG, outils non utilisés).
  - AD-10 et AD-16 : ajouter l'événement `output_truncated` (arrêt pour cause de longueur), affiché comme un événement lisible du harnais.

### R-02 — Des segments au texte envoyé : correspondance et attribution des tokens — élevée

- **Référence PRD.** FR-2 (chaque segment est étiqueté par sa brique), FR-30 (tokens par segment), FR-41 (jauge « ventilée selon les segments de FR-2 »), FR-32 (« la conversation est conservée : le harnais reconstruit le contexte à chaque tour »), glossaire « Contexte ».
- **Constat.** AD-4 affirme deux choses sans dire comment les obtenir :
  - le rendu du `chat_template` s'applique « à ces segments » ;
  - la somme des tokens des segments est égale au total.

  Or un `chat_template` reçoit des messages (`role`, `content`, `tool_calls`) et une variable `tools`, pas des segments. Plusieurs segments (prompt système, mémoire globale, descriptions de skills, extraits RAG) doivent entrer dans le même message, et les descriptions d'outils sont mises en forme par le gabarit lui-même.

  Par ailleurs, compter chaque segment séparément ne donne pas le total, car un token peut chevaucher la frontière entre deux segments. Sans règle commune, chaque brique fera son propre choix, et la jauge ne tombera pas juste.

  Enfin, le catalogue des types de segment qui sert à ventiler la jauge n'est pas fermé. Pour que l'historique survive à un changement de modèle (FR-32), les appels d'outils de l'historique doivent être stockés sous forme structurée, et non dans le XML propre à Qwen.
- **Correction proposée.** Compléter AD-4 par trois règles.
  1. **Correspondance.** Chaque type de segment a un emplacement fixe : message `system`, `user`, `assistant`, `tool`, ou variable `tools` du gabarit. L'ordre à l'intérieur d'un emplacement est fixé par une table unique dans `context`.
  2. **Attribution.** Le gabarit est rendu une seule fois, avec des marqueurs de début et de fin autour de chaque segment. Le texte obtenu est découpé en portions par segment, puis le texte réel (sans marqueurs) est tokenisé une seule fois, avec correspondance des positions de caractères (offsets). Chaque token est attribué au segment qui contient son premier caractère ; le reste revient à « Message et gabarit ». La somme est égale au total par construction.
  3. **Catalogue fermé** des types de segment, qui sont aussi les couleurs de la jauge : `template_message`, `system_prompt`, `history`, `tool_descriptions`, `skill_descriptions`, `skill_content`, `rag_extracts`, `tool_results`, `subagent_result`, `hook_injection`, `global_memory`.

  L'historique est stocké sous forme de messages structurés (`role`, `content`, `reasoning`, `tool_calls` sous la forme `{name, arguments}`) et re-rendu par le gabarit du modèle actif à chaque appel.

### R-03 — Actions décidées par le modèle hors outils ; forme d'une action forcée — élevée

- **Référence PRD.** FR-42 (cinq actions : outil, écriture en mémoire, documentation MCP en lazy loading, skill, délégation ; « une action forcée suit tout le cycle du harnais, hooks compris »), FR-12, FR-21, FR-24, FR-29.
- **Constat.** AD-14 garantit que les appels d'outils (du modèle, du sous-agent ou forcés) passent par les hooks. Mais rien ne dit comment le modèle *demande* :
  - une écriture en mémoire ;
  - le chargement d'une documentation en lazy loading ;
  - le déclenchement d'un skill ;
  - une délégation.

  Rien ne dit non plus que ces quatre actions passent par l'exécuteur. On ne sait pas davantage comment une action forcée apparaît dans le contexte. Soit c'est un faux appel d'outil que le harnais attribue au modèle, soit c'est un segment injecté. Le choix change le contexte réel, donc ce que montre FR-2. En l'état, `before_tool` et `after_tool` ne s'appliqueraient pas, par exemple, à un skill forcé, ce qui contredit FR-42.
- **Correction proposée.** Créer AD-23, « Méta-outils du harnais », ou compléter AD-14.
  - Les quatre actions sont des outils du harnais, de source `harness` : `remember`, `load_tool_doc`, `load_skill`, `delegate`. Chacun est déclaré par sa brique, avec son schéma, et passe par l'exécuteur unique, hooks compris.
  - En lazy loading, le contexte ne contient que le nom de chaque outil MCP et `load_tool_doc`. Appeler un outil dont la documentation n'est pas chargée produit une erreur réinjectée (FR-15).
  - Une action forcée est rendue dans le contexte comme un appel d'outil de l'assistant, avec son résultat. Elle porte `actor = user`, et le segment reste attribué à la brique. Ainsi le contexte montré est bien celui envoyé, et le modèle voit une forme cohérente.
  - Si le modèle n'a pas de parseur d'appels d'outils, les actions forcées restent possibles et les actions décidées par le modèle sont indisponibles (voir R-24).

### R-04 — Sorties réseau sans brique activée — élevée

- **Référence PRD.** NFR-4 (« Aucune donnée ne quitte le poste, hormis par une brique réseau activée explicitement »), NFR-3 (« Aucune télémétrie »), FR-37 (le diagnostic vérifie l'accès au réseau), FR-20 (« s'il ne répond pas au démarrage »), UJ-3 (proxy).
- **Constat.**
  - AD-16 et AD-21 impliquent de contacter au démarrage les serveurs MCP publics et un point réseau pour le diagnostic, et de télécharger le modèle, avant toute activation de brique réseau. Rien ne dit que ces sorties sont tracées ni qu'elles sont limitées à une vérification de connectivité.
  - AD-15 pose que seul `net` ouvre des connexions HTTP. C'est faux pour les bibliothèques tierces, qui ouvrent leurs propres connexions :
    - `huggingface_hub`, qui a son propre client HTTP et sa télémétrie ;
    - `headroom-ai`, qui télécharge ONNX Runtime depuis `cdn.pyke.io` à l'exécution (memlog) ;
    - `litellm`, que tire `headroom-ai`.

    Ces sorties échappent à la trace, à la liste d'adresses autorisées et à `truststore`. Derrière un proxy qui inspecte le TLS, le téléchargement de UJ-3 échouerait avant même que le diagnostic puisse proposer la voie hors ligne.
- **Correction proposée.** Compléter AD-15.
  - Au démarrage, `truststore.inject_into_ssl()` s'applique à tout le processus. On y fixe aussi `HF_HUB_DISABLE_TELEMETRY=1`, et `HF_HUB_OFFLINE=1` dès que le modèle est présent.
  - Les sorties hors brique sont limitées à une liste fermée : sonde de connectivité, poignée de main MCP (`initialize`, puis `tools/list`), téléchargement du modèle à la demande. Chacune est émise dans la trace comme « données sortantes (diagnostic) » et affichée dans le diagnostic.
  - Option plus stricte, recommandée pour NFR-4 : la poignée de main MCP n'a lieu qu'à l'activation de la brique MCP. Le schéma dessine le serveur public avec l'état « non contacté ».
  - Règle d'adoption, à ajouter aux conventions : une bibliothèque qui ouvre ses propres connexions n'est acceptée que si elle accepte un client `httpx` injecté ou si elle fonctionne hors ligne. Cette règle devient un critère de R-15.

### R-05 — Le rejeu annule le changement à comparer — moyenne

- **Référence PRD.** FR-7 (« rejouer le dernier prompt après avoir changé les briques » ; « l'historique est restauré dans cet état ; la mémoire globale, elle, reste dans son état courant »), FR-11.
- **Constat.** Selon AD-17, l'instantané contient l'historique, la configuration des briques, le prompt système et les réglages. Le rejeu restaure cet instantané puis applique la configuration courante des briques, mais pas le prompt système ni les réglages courants. Un formateur qui modifie le prompt système (ou la fenêtre, ou les bornes d'appels) puis rejoue verra donc son changement annulé : c'est justement la comparaison que FR-7 doit permettre.
- **Correction proposée.** AD-17 : l'instantané ne restaure que l'état propre à la conversation, c'est-à-dire l'historique et le compteur de tours. Toute la configuration (briques, sous-options, prompt système, réglages, modèle actif, actions armées) est celle du moment du rejeu. Chaque tour enregistre la configuration utilisée, pour la comparaison côte à côte. Ajouter à l'événement de début de tour le champ `replay_of: turn_id | null`.

### R-06 — Crash natif du moteur en processus — moyenne

- **Référence PRD.** NFR-8 (« Aucune défaillance du modèle ne fait planter l'application »), FR-33 (modèle inconnu), FR-34 (blobs d'Ollama, dont le chargement n'est pas vérifié selon le memlog), SM-6.
- **Constat.** AD-16 ne contient que les exceptions Python. Un `GGML_ASSERT`, une architecture non prise en charge, un GGUF corrompu ou un manque de mémoire à l'allocation font avorter llama.cpp. Comme le moteur tourne dans le processus, l'avortement emporte le serveur web et la session en pleine démonstration. Le risque augmente précisément avec les fichiers découverts (AD-7).
- **Correction proposée.** AD-7 et AD-8 : tout GGUF qui n'a jamais été chargé avec succès est d'abord ouvert dans un processus enfant de sonde (`sys.executable -m wavestack.models.probe <chemin>`, avec `vocab_only` puis un chargement complet). La sonde vérifie `general.architecture`, le gabarit et la mémoire résidente mesurée, qui alimente AD-8. Un succès est mémorisé dans `settings.json` (chemin, taille, date de modification). Un échec rend le fichier « incompatible », avec la raison. Ce plafond de la protection (un crash reste possible en cours d'inférence) est à noter dans AD-16.

### R-07 — Serveurs externes : fenêtre, troncature, mémoire — moyenne

- **Référence PRD.** FR-34 (serveur déjà lancé ; « le contexte affiché reste le contexte réel »), glossaire « Fenêtre de contexte » (plafonnée sous la limite du modèle), NFR-2, AD-8 (« jamais deux modèles »).
- **Constat.**
  - AD-9 charge le modèle avec `n_ctx` égal à la fenêtre, ce qui ne vaut que pour le mode en processus.
    - Pour Ollama, sans `options.num_ctx`, le serveur garde sa propre taille de contexte et peut tronquer le prompt en silence. Le contexte affiché deviendrait alors faux.
    - Pour llama-server, `n_ctx` est fixé au lancement du serveur (divisé par `--parallel`) et WaveStack ne peut pas le changer.
  - AD-8 libère le modèle en processus en mode serveur. Mais en revenant au mode en processus, le modèle d'Ollama reste chargé (`keep_alive`) : on a alors deux modèles en mémoire.
- **Correction proposée.**
  - AD-5 et AD-9 : la fenêtre effective vaut le minimum de la fenêtre configurée, du contexte natif et du contexte du serveur (lu par `/props` pour llama-server, fixé par `options.num_ctx` pour Ollama). `ollama_raw` envoie toujours `num_ctx`. Chaque adaptateur vérifie que le nombre de tokens d'entrée renvoyé par le serveur (`prompt_eval_count` pour Ollama, `tokens_evaluated` pour llama-server) est égal au compte du harnais. Un écart émet `harness_error` avec le message « transparence réduite ».
  - AD-8 : en quittant le mode Ollama, l'adaptateur envoie `keep_alive: 0`. Un modèle servi par llama-server reste compté dans le budget tant que le serveur répond.

### R-08 — Périmètre du budget mémoire — moyenne

- **Référence PRD.** NFR-2 (« le périmètre mesuré couvre les processus de WaveStack (harnais, modèle, serveurs MCP locaux, index RAG) »), §11 (hypothèse à mesurer).
- **Constat.** Le `LoadRegistry` d'AD-8 ne compte que les composants lourds, estimés d'après les fichiers. Il oublie deux postes du périmètre de NFR-2, qui pèsent chacun plusieurs dizaines à centaines de Mo : le socle du processus Python (FastAPI, pydantic, la bibliothèque `mcp`, Jinja2) et le processus enfant du serveur MCP local. Pourtant `psutil` figure déjà dans la stack.
- **Correction proposée.** AD-8 : le budget se calcule ainsi : mémoire résidente mesurée du processus WaveStack et de ses enfants (`psutil`), plus les estimations des composants à charger. Le refus porte sur ce total. Le diagnostic (FR-37) affiche la même mesure. L'hypothèse de NFR-2 est ainsi rendue mesurable par l'application elle-même.

### R-09 — Cache KV entre les appels d'un tour — moyenne

- **Référence PRD.** NFR-1 (« ces bornes s'appliquent au premier token de chaque appel »), FR-29, UJ-6.
- **Constat.** Un tour avec outils fait jusqu'à 6 appels. Si chaque appel relit tout le contexte, la borne de 30 s par appel ne tient pas au-delà du premier. Deux obstacles s'y opposent, et aucun AD ne les traite :
  - selon le memlog, Qwen3.5 est un modèle hybride : réécrire le début du contexte force une relecture complète ;
  - les gabarits de Qwen reformatent les appels d'outils et retirent le raisonnement des tours précédents.

  Pour le sous-agent, AD-11 accepte de relire le contexte principal (« latence affichée »), mais NFR-1 borne aussi cet appel.
- **Correction proposée.**
  - AD-4 : pendant un tour, le rendu est **ajout seul**. Le texte de l'appel n+1 commence par le texte exact de l'appel n, suivi de la sortie générée. Les briques ne modifient pas les segments déjà rendus pendant un tour ; la compression et H3 s'appliquent avant le premier appel. Un test vérifie cette propriété avec le moteur factice.
  - AD-11 : sauvegarder puis restaurer l'état du moteur (`save_state()` et `load_state()` de llama-cpp-python) autour de la délégation, si le test préalable confirme que cela fonctionne pour le modèle hybride. Sinon, documenter dans le PRD que l'appel qui suit une délégation est hors borne.
  - Ajouter ce test à la section Deferred, avec `llama-bench`.

### R-10 — Confinement des outils locaux — moyenne

- **Référence PRD.** FR-13 (lecture de fichier « dans un dossier de démonstration » ; calculatrice), FR-27 (H1), NFR-4, NFR-11.
- **Constat.** Les arguments viennent du modèle, donc d'une source non fiable. Si seul H1 empêche de sortir du dossier, désactiver H1 (ce que FR-27 permet) ouvre tout le disque du formateur : `C:\Users\...` ou `%LOCALAPPDATA%\WaveStack\settings.json`. Le contenu lu peut ensuite partir vers un serveur MCP public. H1 doit rester une démonstration, pas la seule protection.
- **Correction proposée.** AD-14 : l'outil `read_file` résout le chemin (`Path.resolve()`) et refuse tout ce qui sort de `content/demo_files/`. Ce refus est une erreur de l'outil, pas un hook. H1 protège le sous-dossier confidentiel qui se trouve *à l'intérieur* de la zone autorisée. La calculatrice passe par un évaluateur d'expressions arithmétiques fondé sur `ast` (liste blanche d'opérateurs), jamais par `eval`. Un test couvre chacun de ces deux cas.

### R-11 — API locale : CSRF et DNS rebinding — moyenne

- **Référence PRD.** NFR-4 (confidentialité ; écoute sur `127.0.0.1`).
- **Constat.** Écouter sur `127.0.0.1` n'empêche pas une page web ouverte dans le même navigateur d'envoyer des `POST` d'intentions, qui peuvent déclencher des outils ou des sorties réseau. Un DNS rebinding permet aussi de lire le flux SSE, qui contient la conversation et les fichiers lus. AD-18 n'en parle pas.
- **Correction proposée.** AD-18 :
  - `TrustedHostMiddleware` limité à `127.0.0.1` et `localhost` ;
  - rejet de tout `POST` dont l'en-tête `Origin` n'est pas celui du serveur ;
  - intentions en `application/json` uniquement ;
  - aucun en-tête CORS.

  Trois lignes de code et un test.

### R-12 — Identité des composants, modèle et fichiers dans le schéma — moyenne

- **Référence PRD.** FR-3 (« le composant en cours d'action est mis en évidence » ; composants actifs : modèle, harnais, briques, serveurs MCP, données), FR-4 (un segment met en évidence « la brique et le composant correspondants »), FR-34 (« le schéma d'architecture montre le modèle comme un processus local distinct de WaveStack »), FR-12, FR-16, FR-27 (H2).
- **Constat.** L'enveloppe d'AD-2 porte `brick` mais pas de composant. Deux serveurs MCP publics, deux fichiers (mémoire et journal d'audit) ou le modèle ne peuvent donc pas être distingués pour la mise en évidence. AD-12 dérive le schéma des déclarations *de briques*. Le modèle et le harnais ne sont pas des briques, et le lieu d'hébergement du modèle change avec l'adaptateur : dans le processus WaveStack, ou processus local distinct.
- **Correction proposée.**
  - AD-2 : ajouter `component: str | null` à l'enveloppe, et `component` aux segments d'AD-4.
  - AD-12 : les composants du socle (navigateur, harnais, modèle) sont déclarés par `session` et `models`. L'adaptateur de moteur déclare son lieu d'hébergement (`in_process` ou `local_process` pour `ollama_raw` et `llama_server`). Les fichiers d'AD-20 et l'index RAG sont déclarés comme composants `local_file` par leur brique, avec leur chemin.

### R-13 — Flux de sortie typé — moyenne

- **Référence PRD.** FR-1 (streaming ; indicateur pendant les phases sans token), FR-2 (« la sortie brute du modèle est affichée : raisonnement, texte, appels d'outils »), FR-9 (raisonnement masquable dans la vue humain), FR-15.
- **Constat.** `Engine.complete` renvoie des tokens en flux, et AD-6 fournit un parseur d'appels d'outils. Mais aucun AD ne dit :
  - si le parseur travaille au fil du flux ;
  - ce que reçoit la vue humain (sans balise de raisonnement ni XML d'appel d'outil) ;
  - si la sortie brute complète est émise à l'identique.

  Sans règle, le front devra reconnaître lui-même `<think>` ou `<tool_call>`, ce qu'AD-1 interdit.
- **Correction proposée.** AD-6 : chaque famille fournit un parseur incrémental qui émet des fragments typés `reasoning`, `text` et `tool_call_partial`, et un événement final `model_output_raw` qui contient le texte brut intégral, même mal formé. Ajouter au catalogue d'AD-2 les phases `prefill_started` et `prefill_done`, avec le nombre de tokens, pour l'indicateur de travail de FR-1. Les délimiteurs du raisonnement rejoignent le registre.

### R-14 — RAG hors ligne et appariement de l'index — moyenne

- **Référence PRD.** FR-16, UJ-3 (voie hors ligne), FR-34, FR-37.
- **Constat.** AD-21 et AD-7 ne décrivent la voie hors ligne et la découverte que pour le modèle de langage. Les modèles d'embedding et de reranking (639 Mo et 438 Mo selon le memlog) se téléchargent aussi : sur un poste où le proxy bloque le téléchargement, la brique RAG reste indisponible sans action corrective. De plus, l'index sqlite-vec précalculé n'a de sens qu'avec le modèle d'embedding qui l'a produit. Si le test préalable impose fastembed, l'index doit être reconstruit, et rien ne détecte l'écart.
- **Correction proposée.**
  - AD-21 et AD-7 : tous les modèles (LLM, embedding, reranker) suivent la même voie : téléchargement, dossier `models/`, découverte, copie hors ligne. Le diagnostic les vérifie seulement si les briques qui en ont besoin sont activées.
  - AD-22 : l'index enregistre dans une table de métadonnées l'identifiant et l'empreinte du modèle d'embedding, ainsi que la dimension. Au chargement, un écart rend la brique RAG indisponible, avec la raison. Le script `build_rag_index.py` fait foi.

### R-15 — Critères du test préalable Headroom — moyenne

- **Référence PRD.** FR-31, NFR-3, NFR-4, NFR-5, NFR-10 ; §9 (« dépendances Python pures privilégiées »).
- **Constat.** Le memlog liste des points bloquants :
  - `compress()` travaille sur des messages au format OpenAI ;
  - la bibliothèque tire `litellm` et l'exécutable natif `ast-grep-cli` ;
  - ONNX Runtime est téléchargé à l'exécution ;
  - l'extra `[proxy]` épingle `mcp<2`.

  AD-22 ne reprend aucun de ces points comme critère d'acceptation. La première story du palier 2 n'a donc pas de condition de succès vérifiable.
- **Correction proposée.** AD-22 : Headroom n'est adopté que si les six conditions suivantes sont réunies :
  1. il fonctionne entièrement hors ligne, sans téléchargement à l'exécution ;
  2. il ne tire pas `torch` ;
  3. il n'ajoute aucun exécutable natif lancé en sous-processus, sinon le risque AppLocker ou WDAC de NFR-5 serait aggravé ;
  4. il n'entre pas en conflit avec `mcp` 2.x ;
  5. sa mémoire est comptée par le `LoadRegistry` et reste dans le budget ;
  6. il s'appelle segment par segment (un message par segment) sans perdre l'attribution à la brique.

  Sinon, on bascule sur le compresseur maison, et le PRD est modifié (voir la dérogation O-2).

### R-16 — Sous-options de brique — faible

- **Référence PRD.** FR-5 (dépendance « le lazy loading MCP exige la brique MCP »), FR-9 (afficher ou masquer le raisonnement), FR-13 (« outils activables individuellement »), FR-18, FR-21, FR-27 (chaque hook s'active séparément).
- **Constat.** AD-12 ne déclare que la brique entière. Les sous-options (chaque outil, chaque hook, chaque serveur MCP, reranking, lazy loading, bornes de boucle) et leurs dépendances ne sont pas dans le contrat. Chaque story les inventera.
- **Correction proposée.** AD-12 : une brique déclare aussi `options: [{id, kind: toggle|choice|int, default, requires}]`. La disponibilité d'une option est calculée au même point unique que celle de la brique. Les scénarios (AD-19) fixent brique et options avec les mêmes identifiants.

### R-17 — H5 : aperçu fidèle et périmètre — faible

- **Référence PRD.** FR-27 (H5 : l'utilisateur « voit l'outil, la destination et les données qui sortiraient du poste », « avant l'exécution d'un outil réseau »), FR-22.
- **Constat.** H5 s'exécute à `before_tool`, alors que `net` émet les données exactes au moment de l'envoi. Rien ne garantit que l'aperçu présenté pour accord soit identique à ce qui part. Le spine ne précise pas non plus que H5 s'applique aux outils MCP publics, qui sont pourtant des services réseau.
- **Correction proposée.** AD-14 et AD-15 : un outil réseau construit sa requête (méthode, URL, corps) *avant* `before_tool`. H5 affiche cette requête, et `net` l'envoie sans la modifier. Le critère d'application de H5 est `hosting == network_service`, qui couvre les outils natifs réseau et le MCP public.

### R-18 — Échanges MCP locaux tracés — faible

- **Référence PRD.** FR-22 (« découverte des outils, appel, résultat »).
- **Constat.** AD-15 trace le JSON-RPC du MCP public via `net`. Le MCP local passe par stdio, et sa découverte (`tools/list`) ne passe pas par l'exécuteur d'AD-14.
- **Correction proposée.** AD-14 : le module `mcp` émet `mcp_discovery`, `mcp_request` et `mcp_response`, avec le JSON-RPC exact, pour les deux transports. Pour le transport HTTP, `net` ajoute l'événement « données sortantes ».

### R-19 — Outil de lecture de page web — faible

- **Référence PRD.** FR-13 (taille maximale, repli hors ligne sur un long fichier de démonstration, conversion en texte), NFR-11 et addendum (page jamais copiée dans le dépôt ; l'adresse change, on la teste au démarrage).
- **Constat.** AD-15 couvre la liste d'adresses autorisées. La coupe à une taille maximale, la substitution hors ligne, la conversion en texte (sans bibliothèque dans la stack) et l'interdiction de mise en cache ne figurent nulle part.
- **Correction proposée.** AD-14 (outil `fetch_page`) : taille maximale en octets et en tokens dans `wavestack.toml`. Sans réseau, l'outil lit un fichier de `content/demo_files/` et l'indique dans son résultat. Conversion avec `html.parser` de la bibliothèque standard, ou lecture directe des pages `.md`. Aucune écriture sur disque du contenu lu.

### R-20 — Reprise d'un serveur MCP public — faible

- **Référence PRD.** FR-20, §9 (pas de réseau en salle ; le Wi-Fi arrive souvent après le lancement).
- **Constat.** Avec AD-16, un serveur qui ne répond pas au démarrage reste indisponible jusqu'au redémarrage. Pendant une session, le formateur devrait relancer WaveStack.
- **Correction proposée.** AD-16 : l'intention `retry_network` refait la sonde et la poignée de main, entre deux tours. La même sonde est refaite à l'activation de la brique MCP.

### R-21 — Réinitialisation et journal — faible

- **Référence PRD.** FR-39 ; AD-2 (le flux SSE peut repartir d'un `seq` donné).
- **Constat.** Après une réinitialisation, un navigateur qui se reconnecte à partir de `seq = 0` reconstruirait les tours d'avant.
- **Correction proposée.** AD-2 : l'événement `session_reset` marque une époque. Le flux rejoue depuis le dernier `session_reset` quand le `seq` demandé lui est antérieur.

### R-22 — Bascule d'une brique pendant un tour — faible

- **Référence PRD.** FR-5 (« le changement prend effet au tour suivant ») ; EXPERIENCE.md ne désactive pas l'interrupteur pendant un tour.
- **Constat.** AD-3 refuse toute intention autre que H5 et l'arrêt pendant un tour. Le formateur qui active une brique pendant une génération lente se verra refuser l'action, alors que le PRD et l'UX laissent attendre un effet différé.
- **Correction proposée.** AD-3 : les intentions de configuration reçues pendant un tour sont mises en attente et appliquées à la fin du tour, avec un événement `intent_queued`. Seules les intentions qui touchent l'état du tour en cours (envoi, rejeu, modèle, réinitialisation) sont refusées. Autre voie : garder le refus et demander à l'UX de désactiver les interrupteurs pendant un tour.

### R-23 — Rattachement aux paliers — faible

- **Référence PRD.** §7.1 (palier 1 socle, palier 2 complément ; MCP, skills et hooks passent avant le sous-agent et la compression).
- **Constat.** La carte des capacités ne dit pas quels AD ou adaptateurs relèvent du palier 2 (`ollama_raw`, `llama_server`, RAG, compression, sous-agent). Les epics risquent de tirer du palier 2 dans le socle.
- **Correction proposée.** Ajouter une colonne « Palier » à la carte des capacités (Capability → Architecture Map). Préciser dans AD-2 et AD-4 que `context_id` et les types de segment du palier 2 existent dès le palier 1, pour ne pas modifier l'enveloppe plus tard.

### R-24 — Cas limites des capacités — faible

- **Référence PRD.** FR-33, FR-12, glossaire « Fenêtre de contexte ».
- **Constat.** Trois cas ne sont pas traités :
  - une fenêtre configurée plus grande que le contexte natif d'un petit modèle ;
  - un GGUF sans `chat_template`, pour lequel même le LLM nu est impossible ;
  - la mémoire globale sans parseur d'appels d'outils : l'injection reste possible, seule l'écriture par le modèle ne l'est pas.
- **Correction proposée.** AD-6 et AD-9 : la fenêtre effective est plafonnée par le contexte natif. Un GGUF sans gabarit est refusé comme « incompatible », avec la raison. La disponibilité se calcule par action, et non seulement par brique. Ainsi, la mémoire globale reste disponible en injection et en écriture forcée.

### R-25 — Licences du dépôt — faible

- **Référence PRD.** NFR-10 ; addendum (« ajouter un fichier de licence au dépôt » ; Caveman sous MIT).
- **Constat.** La convention « Licences » couvre les dépendances ajoutées. Elle ne couvre ni la licence du dépôt, ni l'attribution du skill Caveman repris, ni les bibliothèques JS et les polices recopiées sous `static/vendor` (AD-18).
- **Correction proposée.** Conventions : un fichier `LICENSE` à la racine ; `THIRD_PARTY_NOTICES` pour tout élément recopié (skill Caveman, `static/vendor`, polices) ; en-tête de licence conservé dans `content/skills/caveman/`.

## Dérogations volontaires au PRD, à reporter dans le PRD

| ID | Référence PRD | Texte actuel | Choix du spine | Modification du PRD proposée |
|---|---|---|---|---|
| O-1 | FR-34 (3ᵉ puce), addendum « Moteur d'inférence » | « via une interface compatible OpenAI (palier 2) » ; « Si le serveur ne permet pas d'envoyer ce texte brut, l'interface signale que la transparence est réduite » ; « derrière un adaptateur compatible OpenAI » | AD-5 : points d'entrée natifs en texte brut seulement (`/api/generate` avec `raw: true`, `/completion`) ; aucun adaptateur de chat ni compatible OpenAI en V1 (V2) | Remplacer par « via son point d'entrée natif en texte brut (Ollama `/api/generate` en mode `raw`, llama-server `/completion`) ». Supprimer la phrase sur la transparence réduite, ou la réserver à l'écart de tokens de R-07. Ajouter en V2 (§7.2) : « serveur au format chat ». |
| O-2 | FR-31 (titre), §3 « Compression du contexte », §4.10, UJ-7, §7.1 palier 2, §1 | « démontrée avec Headroom » ; « (Headroom) » | AD-22 : port `Compressor` ; headroom-ai en dépendance optionnelle, à condition de passer le test préalable ; sinon compresseur maison | « Compression du contexte, démontrée avec Headroom si le test préalable le valide (hors ligne, dans le budget), sinon avec un compresseur minimal du harnais. » Rendre le titre de FR-31 neutre : « Compression du contexte ». |
| O-3 | §3 « Sous-agent » | « une seconde instance du modèle, dotée de son propre contexte » | AD-11 : même instance du moteur, contexte distinct, à tour de rôle | « un second agent, qui réutilise le modèle déjà chargé avec son propre contexte ». Le mot « instance » crée l'ambiguïté avec NFR-2. |
| O-4 | §9, ligne « installation » | « Dépendances Python pures privilégiées » | Roues précompilées à DLL non signées acceptées (llama-cpp-python, sqlite-vec) ; risque AppLocker ou WDAC vérifié en session pilote (Deferred) | « Roues précompilées, sans compilation ni exécutable à installer ; DLL non signées acceptées, vérifiées lors de la session pilote. » |
| O-5 | FR-33 (dernière puce) | « Pour un modèle inconnu, les capacités sont lues dans son fichier » | AD-6 : le raisonnement et la taille de contexte se lisent dans le GGUF, mais l'appel d'outils exige une famille connue du registre (parseur) | Ajouter : « L'appel d'outils n'est disponible que pour les familles dont le format d'appel est connu de WaveStack. » |
| O-6 | FR-20 (3ᵉ puce) | « s'il ne répond pas au démarrage […] il est indisponible » | AD-16 : indisponible « jusqu'au redémarrage » | Aligner après R-20 : « indisponible jusqu'à une nouvelle tentative ». |
| O-7 | Addendum « Budget mémoire » | Embedding et reranker « de quelques centaines de Mo au plus » | Candidats de 639 Mo et 438 Mo, via llama-cpp-python ; repli sur fastembed | Mettre à jour l'ordre de grandeur, ou fixer un plafond cumulé (par exemple 1,1 Go) vérifié par AD-8. |
| O-8 | Addendum « Pistes » (brief) | « NiceGUI ou Streamlit », « ChromaDB ou sqlite-vec », « Ollama plus simple : à arbitrer » | FastAPI, SSE et JS natif ; sqlite-vec ; llama-cpp-python en processus | Marquer ces trois pistes « tranchées le 2026-09-23 (architecture) », comme la piste UX. |

À noter aussi : la section Deferred du spine renvoie au PRD pour le paragraphe « Modèle par défaut (0.8B ou 2B) ». Le PRD dit « 2B au plus » (FR-32). Il n'y a pas de contradiction, mais le PRD peut citer les deux candidats.

## Contrôle des hypothèses du §11

| Hypothèse (§11) | Qui tranche | État dans le spine | Commentaire |
|---|---|---|---|
| NFR-1 : génération de plus de 10 tokens/s | Mesure | Reportée (Deferred, `llama-bench`) | Conforme. À compléter par le débit de *lecture* du contexte, qui borne la fenêtre (R-01). |
| NFR-2 : périmètre mesuré, hors navigateur | Mesure | Partiel | AD-8 ne compte que les composants lourds (R-08). |
| NFR-2 : place d'un serveur externe dans le budget | **Architecture** | **Tranché**, AD-8 | Le modèle servi est compté ; refus en cas de dépassement ; jamais deux modèles. Reste le cas `keep_alive` d'Ollama (R-07). |
| FR-34 : détection des modèles d'Ollama, texte brut vers les serveurs locaux | **Architecture** | **Tranché**, AD-7 et AD-5 | Lecture des manifestes, blob `image.model` chargé en processus ; mode brut natif, BOS neutralisé. Restent : la synchronisation de `num_ctx` et le contrôle de troncature (R-07), la sonde du blob avant chargement (R-06). Implique la dérogation O-1. |
| NFR-8 : nombre maximal d'appels au modèle par tour | **Architecture** | **Tranché**, AD-10 | 6 appels, dont 2 nouveaux essais au plus, 4 pour le sous-agent ; action forcée non comptée ; réglable. |
| NFR-1 : plafond de la fenêtre « fixé en architecture » (texte de NFR-1, pas le §11) | Architecture | Tranché à titre provisoire, AD-9 | 4 096 et 512, valeur définitive après mesure. Incohérent avec les scénarios et la borne de 30 s (R-01). |
| NFR-6 : Windows en cible, macOS et Linux au mieux | Anaël | Repris (Deferred) | Conforme. Petite remarque : sous macOS, le chemin d'usage est `~/Library/Application Support`, pas `~/.local/share`. |
| §8 : cibles des indicateurs | Anaël | Hors architecture | Sans objet. |

Les trois hypothèses du §11 confiées à l'architecture sont tranchées. Aucune ne reste ouverte, mais deux d'entre elles (serveur externe et Ollama) gardent des détails d'exécution à reprendre dans AD-5, AD-8 et AD-9.

## Points bien couverts, sans constat

- Les invariants de transparence, le cœur du produit, sont bien posés : journal d'événements et projections (AD-1, AD-2), gabarit rendu par le harnais (AD-4, AD-5), exécuteur unique (AD-14), sortie réseau unique (AD-15), défaillances contenues (AD-16).
- Contraintes implicites respectées :
  - `uv` sans `pip` ; `ruff` et `pytest` ; moteur factice pour les tests ;
  - code en anglais, interface en français ;
  - aucun fournisseur cloud, aucun framework multi-agents ;
  - une session par instance ; écoute sur `127.0.0.1` ;
  - aucun CDN ni Node ;
  - données hors du dépôt et hors OneDrive.
- UJ-1 à UJ-7 : chaque temps fort s'appuie sur un AD. Les réserves sont UJ-3 (R-14, pour le RAG), UJ-6 (R-09) et UJ-1 et UJ-4 (R-01 et R-12).
- Risques du §9 : toutes les parades ont un point d'ancrage, sauf « dépendances Python pures » (O-4).
- Glossaire : « un seul modèle actif », « trois lieux d'hébergement », « hook déterministe » et « skill chargé à la demande » sont respectés.
