---
title: Revue de la mise à jour R-01 à R-04 — spine contre revue de réconciliation et PRD
target: ../ARCHITECTURE-SPINE.md
sources:
  - review-reconcile-prd.md (R-01 à R-04)
  - ../.memlog.md (entrées « Update » du 2026-09-23)
  - ../../../prds/prd-agentic-harness-training-demo-2026-09-22/prd.md
date: 2026-09-23
---

# Revue de la mise à jour R-01 à R-04

## Verdict

Toutes les puces de « Correction proposée » de R-01 à R-04 ont atterri dans le spine, ou ont été modifiées ou écartées par une décision tracée du memlog. Aucune n'est perdue. La mise à jour introduit toutefois des incohérences :
- deux sont élevées : la garde réseau d'AD-15 ne peut pas fonctionner telle qu'elle est écrite, et deux règles normatives d'AD-4 se contredisent ;
- plusieurs sont moyennes : dans AD-4, AD-5, AD-6, AD-9 et AD-11, et une dérogation à NFR-4 n'est pas déclarée.

Il faut corriger ces points avant les epics. Aucun ne remet en cause le paradigme.

Bilan : 0 critique, 2 élevés, 8 moyens, 5 faibles.

## 1. Traçabilité des corrections proposées

Légende : **A** = atterri tel quel ou reformulé à l'identique ; **M** = modifié par une décision du memlog ; **É** = écarté par une décision du memlog ; **P** = atterri en partie.

### R-01 — Fenêtre et scénarios

| Puce proposée | Statut | Où | Remarque |
|---|---|---|---|
| AD-9 : plafond d'entrée dérivé de la mesure (débit × 30 s), fenêtre et réserve fixées ensemble après `llama-bench` | A | AD-9 « Valeur définitive », Deferred | Formulé comme « la plus grande fenêtre dont la lecture à froid tient en 30 s ». Le memlog (l. 53) garde 4 096 à titre provisoire. |
| Réserve qui dépend du raisonnement (512 ou 1 536), comprise dans la fenêtre | A | AD-9 « Réserve de sortie » | `usable = fenêtre − réserve`, `max_tokens = réserve`. |
| AD-19 : taille de contexte attendue par scénario + test pytest + drapeau `expects_overflow` | M | AD-9 « Scénarios fournis », AD-19 « Scénario » | Aucune taille attendue déclarée ; test marqué `model`, sauté sans GGUF (memlog l. 68). Le contexte testé reste ambigu (voir U-08). |
| Arbitrage PRD sur le module MCP | M | AD-9 « Cas du module MCP » | Documentation complète montrée avec Microsoft Learn ; data.gouv.fr sert de dépassement volontaire (memlog l. 53). Le scénario Souveraineté (FR-40) n'est pas traité (U-08). |
| AD-10 et AD-16 : événement `output_truncated` | M | AD-2 (catalogue), AD-9 « Sortie coupée » | Placé dans AD-9 plutôt qu'AD-10 et AD-16, avec `turn_ended{status: limit}` hors historique (memlog l. 67). Cohérent avec AD-17. |

### R-02 — Segments, rendu, attribution

| Puce proposée | Statut | Où | Remarque |
|---|---|---|---|
| 1. Emplacement fixe par type, table unique dans `context` | A / P | AD-4 « Emplacements » | La table n'inclut pas `tool_catalog` parmi les réponses d'outil du tour, alors qu'AD-25 l'y met (U-10). |
| 2. Rendu unique avec marqueurs, une tokenisation, premier caractère, reste à « Message et gabarit » | M | AD-4 « Attribution des tokens » | Deux rendus (réel et à sentinelles), contrôle octet pour octet, repli `harness_error` (memlog l. 69 et 70). Meilleure que la proposition. Mais le port moteur n'offre pas la primitive nécessaire (U-05). |
| 3. Catalogue fermé des types de segment | M | AD-4 « Types de segment » | Renommé : 12 types, `template_message` séparé en `user_message` et `template`. Il manque un type pour la sortie du modèle réinjectée dans le tour (U-03). |
| Historique structuré, re-rendu par le gabarit actif | A | AD-4 « Historique » | — |

### R-03 — Méta-outils et actions forcées

| Puce proposée | Statut | Où | Remarque |
|---|---|---|---|
| Quatre méta-outils `source = harness` (`remember`, `load_tool_doc`, `load_skill`, `delegate`) par l'exécuteur unique, hooks compris | A | AD-25, AD-14 (`source`) | — |
| Lazy loading : seuls les noms et `load_tool_doc` ; appel sans documentation = erreur réinjectée | A | AD-25 « Lazy loading » | Précisé : la liste est dans la description de `load_tool_doc`, et la documentation entre ensuite dans `tools` (memlog l. 71). |
| Action forcée = appel d'outil de l'assistant avec sa réponse, `actor = user`, segment attribué à la brique | M | AD-25 « Action forcée », AD-2, AD-3 | `trigger = user` au lieu de `actor = user` : cohérent avec la sémantique d'AD-2. |
| Sans parseur : actions forcées possibles, actions du modèle indisponibles | P | AD-6 | Posé dans AD-6, mais contredit par la disponibilité calculée par brique (AD-12) et par l'abandon des actions armées (AD-3) (U-06). |

### R-04 — Sorties réseau

| Puce proposée | Statut | Où | Remarque |
|---|---|---|---|
| `truststore.inject_into_ssl()` sur tout le processus ; `HF_HUB_DISABLE_TELEMETRY=1` | A | AD-15 « Au démarrage » | Ajout de `HF_HUB_DISABLE_XET=1`. |
| `HF_HUB_OFFLINE=1` dès que le modèle est présent | É | AD-15 | Écarté par le memlog (l. 73), car la variable est lue à l'import. L'entrée l. 61 du memlog, plus ancienne, le mentionne encore : elle est simplement remplacée. |
| Liste fermée des sorties hors brique (sonde, poignée de main MCP, téléchargement), tracées « données sortantes (diagnostic) » et affichées dans le diagnostic | M / P | AD-15 « Sorties hors brique », AD-2 `outbound_request{origin}` | La poignée de main MCP est retirée de la liste (option stricte). L'affichage de ces sorties dans la page de diagnostic n'est pas écrit (U-12). |
| Option stricte : poignée de main MCP à l'activation, serveur dessiné « non contacté » | A | AD-15 « Serveur MCP public » | L'état « non contacté » n'existe pas dans le modèle `wanted` / `available` d'AD-12 (U-14). |
| Règle d'adoption des bibliothèques qui ouvrent leurs propres connexions, critère de R-15 | A | AD-15 « Règle d'adoption », conventions « Dépendances », Deferred (Headroom) | — |
| (Décision du memlog, hors proposition) Garde bloquante `sys.addaudithook` | nouveau | AD-15 | Irréalisable telle qu'elle est écrite (U-01). |

## 2. Constats

### U-01 — La garde réseau compare des adresses IP à une liste de noms d'hôtes — élevée — AD-15

- **Constat.**
  - L'événement d'audit `socket.connect` fournit `(ip, port)`, pas un nom d'hôte. La liste autorisée de `wavestack.toml` contient des noms : `www.data.gouv.fr`, `learn.microsoft.com`, `huggingface.co`. En l'état, la garde ne peut rien comparer. Il faudrait résoudre les noms à l'avance, ce qui est fragile, car les CDN changent d'adresse.
  - Derrière un proxy, UJ-3, toutes les connexions visent l'adresse du proxy. La garde doit donc l'autoriser explicitement, faute de quoi elle bloque tout.
  - Même avec Xet désactivé, le téléchargement Hugging Face est redirigé vers des hôtes CDN (`cdn-lfs*.hf.co` ou équivalent). Ces hôtes ne figurent nulle part dans la liste par défaut. Le README d'AD-21 cite `huggingface.co` pour le proxy, pas pour la liste de WaveStack.
  - Une bibliothèque qui se connecte à un hôte autorisé sans passer par `net` passe la garde sans émettre d'`outbound_request`. « Tout est tracé » ne tient alors plus (NFR-4).
  - Un audit hook ne voit que le module `socket` de Python. Le code réseau natif (Rust ou C, par exemple `hf_xet` ou un téléchargeur ONNX) y échappe. Ce plafond n'est pas écrit.
- **Correction proposée.** Dans AD-15 :
  - filtrer sur l'événement `socket.getaddrinfo`, qui porte le nom d'hôte, par rapport à la liste autorisée ;
  - à `socket.connect`, n'accepter que la boucle locale, les adresses IP résolues à partir d'hôtes autorisés et l'adresse du proxy configuré ;
  - fixer le contenu par défaut de la liste : adresse de la sonde, hôtes de téléchargement Hugging Face (y compris les redirections CDN), serveurs MCP publics, API des outils ;
  - quand une connexion n'a pas été annoncée par `net` (drapeau dans la `TraceScope`), émettre un `outbound_request{origin: unannounced}` ;
  - noter la limite : le code réseau natif n'est pas couvert, ce qui justifie `HF_HUB_DISABLE_XET` et la règle d'adoption.

### U-02 — Contradiction entre « le prompt envoyé est toujours le rendu du gabarit » et « ajout seul pendant un tour » — élevée — AD-4 (touche NFR-1)

- **Constat.** AD-4 pose deux règles normatives :
  - l'étape 1 : le prompt envoyé est « toujours le rendu du gabarit avec les vraies valeurs, jamais une reconstruction » ;
  - la règle « Ajout seul » : le texte de l'appel n+1 commence par le texte exact de l'appel n, suivi de sa sortie.

  Les gabarits Qwen re-rendent les `tool_calls` structurés dans leur propre format XML (espaces, ordre des arguments, `tojson`) et traitent le raisonnement selon leur position. Le rendu de l'appel n+1 ne contient donc pas forcément la sortie brute de l'appel n à l'octet près. Le spine ne dit pas quelle règle l'emporte :
  - si c'est le gabarit, le préfixe n'est plus réutilisé : le modèle hybride relit tout, et la borne de 30 s par appel de NFR-1 tombe ;
  - si c'est l'ajout de la sortie brute, le prompt n'est plus le rendu, et le contrôle 4 de l'attribution ne tient plus.
- **Correction proposée.** Dans AD-4, trancher :
  - le prompt reste le rendu du gabarit ;
  - la propriété « ajout seul » devient un contrôle, pas une hypothèse. La session vérifie que `render(n+1)` commence par `render(n)`. Un écart émet un événement lisible « préfixe non réutilisé, relecture complète », avec la latence affichée ;
  - le test de non-régression Qwen3.5 couvre un tour à deux appels avec un appel d'outil ;
  - la sortie parsée de l'appel n est normalisée (arguments, espaces) de sorte que son rendu égale la sortie brute quand le modèle respecte le format.

### U-03 — Aucun type de segment pour la sortie du modèle réinjectée pendant un tour — moyenne — AD-4, AD-25 (touche FR-2, FR-30, FR-41)

- **Constat.** Dans un tour à plusieurs appels, l'appel n+1 contient la sortie de l'appel n : raisonnement, texte, appel d'outil de l'assistant. Il contient aussi l'appel d'outil de l'assistant fabriqué pour une action forcée (AD-25). Aucun des 12 `SegmentKind` ne couvre ce contenu :
  - `history` est réservé aux tours antérieurs ;
  - `tool_result` ne concerne que la réponse.

  Ce texte tombe donc hors sentinelles, dans `template`, c'est-à-dire « Message et gabarit ». Avec le raisonnement actif, cela peut représenter des centaines de tokens mal classés dans la jauge (FR-41) et dans le compteur par brique (FR-30). AD-25 dit que les segments d'une action forcée « restent attribués à la brique » sans préciser de quel type ils sont.
- **Correction proposée.** Amender AD-4 en ajoutant un type fermé `turn_output` (sortie de l'assistant pendant le tour courant, brique `core`, ou brique de l'action forcée si `trigger = user`), placé dans l'emplacement « dans le tour ». Au tour suivant, il devient `history`. Ajouter son libellé dans `content/`.

### U-04 — Contenus chargés en double au tour suivant — moyenne — AD-4, AD-25

- **Constat.** Un skill, une documentation MCP ou une écriture en mémoire chargés pendant le tour t entrent comme réponse d'outil, puis « rejoignent leur emplacement stable » au tour t+1. Mais l'historique structuré de t garde la réponse d'outil complète. Au tour t+1, le contenu figure donc deux fois : une fois en `history` et une fois en `skill_body`, `tools` ou `global_memory`. Dans une fenêtre de 2 560 à 3 584 tokens utiles, un corps de skill ou une documentation MCP en double peut à lui seul provoquer un dépassement, et fausse l'écart que FR-21 et FR-24 veulent montrer.
- **Correction proposée.** Dans AD-4 « Historique » : la réponse stockée de `load_skill`, `load_tool_doc` et `remember` est un talon (« skill caveman chargé », « documentation de X chargée »), puisque le contenu vit dans son emplacement stable. Le rendu du tour t reste inchangé dans la trace.

### U-05 — Le port moteur n'offre pas la primitive qu'exige l'attribution — moyenne — AD-5, AD-4

- **Constat.** L'étape 6 d'AD-4 cumule `detokenize([id], special=True)` pour obtenir les décalages en octets. Or le port `Engine` d'AD-5 n'expose que `complete`, `tokenize`, `metadata` et `close`. Pour `llama_server`, le tokenizer vient de `/tokenize`, et rien n'indique d'où viendraient les octets de chaque token. Par ailleurs, pour un tokenizer SentencePiece (famille inconnue), la détokenisation token par token peut perdre l'espace de tête. La somme des octets ne serait alors plus égale au prompt, et aucun contrôle ne le détecte.
- **Correction proposée.** Dans AD-5, ajouter `token_bytes(ids) → list[bytes]` au port :
  - `llama_cpp` et `ollama_raw` : `detokenize` du GGUF ;
  - `llama_server` : `/tokenize` avec `with_pieces`, ou `/detokenize`.

  Dans AD-4, étape 6 : vérifier que `b"".join(token_bytes) == prompt.encode()`, sinon émettre « attribution approximative ».

### U-06 — Actions forcées sans parseur : la disponibilité par brique les annule — moyenne — AD-6, AD-12, AD-3 (touche FR-42, FR-12)

- **Constat.**
  - AD-6 : sans parseur, les actions décidées par le modèle sont indisponibles, mais les actions forcées restent possibles.
  - AD-12 : la disponibilité se calcule par brique (`available`).
  - AD-3 : « une action dont la brique est indisponible est abandonnée ».

  Si l'absence de parseur rend indisponibles les briques mémoire globale, skills, sous-agent ou outils (le memlog, l. 37, dit « brique outils indisponible »), les actions forcées sont abandonnées. C'est l'inverse d'AD-6 et du but de FR-42, qui veut faire aboutir la démonstration malgré un SLM faible.
- **Correction proposée.** Dans AD-12, calculer la disponibilité par brique et par mode d'action (`model_decided`, `forced`, `injection`) au même point unique. Dans AD-3, l'abandon porte sur l'indisponibilité du mode `forced`. Vérifier aussi que le gabarit sait rendre des `tool_calls` : sans cela, l'action forcée ne peut pas être rendue selon AD-25.

### U-07 — Dépassement, borne ou sortie coupée dans le sous-agent : le statut du tour principal n'est pas défini — moyenne — AD-11, AD-9, AD-10, AD-2

- **Constat.** AD-11 applique AD-9 au sous-agent « avec son propre événement de dépassement ». Or AD-9 et AD-10 terminent le tour par `turn_ended{status: overflow|limit}`, et `limit_reached{limit: sub_calls}` existe. Un dépassement, une borne atteinte ou une sortie coupée dans `sub{n}` mettent-ils fin au tour principal, ou reviennent-ils comme un `subagent_result` en échec ? Rien ne le dit. Pourtant, FR-29 et FR-42 font continuer le tour après une action, et le refus H5 continue aussi le tour.
- **Correction proposée.** Dans AD-11 : en contexte `sub{n}`, `context_overflow`, `output_truncated` et `limit_reached{sub_calls}` terminent la délégation, pas le tour. Le contexte principal reçoit un `subagent_result` d'échec, lisible et en français, et le tour continue sous les bornes principales.

### U-08 — Test des scénarios : contexte mesuré ambigu ; FR-40 et FR-38 non couverts — moyenne — AD-9, AD-19 (touche NFR-1, FR-38, FR-40)

- **Constat.**
  - Le test « rend son contexte » sans dire lequel. Le `context_preview` est calculé « sans message ni extraits RAG », alors que le premier appel réel contient les deux. Un test fondé sur l'aperçu sous-estime le contexte, et l'affirmation « le `context_preview` au lancement montre le même résultat » n'est vraie que si le test mesure aussi l'aperçu.
  - La réserve dépend de la brique raisonnement (AD-9). Avec FR-38, les briques des modules précédents restent actives, raisonnement compris (2ᵉ module). Le module MCP démarre alors avec 2 560 tokens utiles, pas 3 584. Le test doit utiliser la réserve du scénario.
  - FR-40 (Souveraineté) passe par data.gouv.fr. Le spine n'indique pas que ce scénario est en lazy loading. En documentation complète, il déborde, sans que `expects_overflow` le prévoie.
- **Correction proposée.** Dans AD-9 :
  - le test rend le premier appel de chaque prompt suggéré : aperçu, plus message, plus une provision RAG de `top_k × taille maximale d'un extrait` si la brique RAG est `wanted` ;
  - le test utilise la réserve du scénario ;
  - le scénario Souveraineté est en lazy loading ;
  - si FR-38 ne tient pas (briques cumulées), le scénario peut éteindre des briques. Il le déclare, et le PRD est aligné.

### U-09 — Sorties hors brique non déclarées comme dérogation à NFR-4 — moyenne — AD-15 (touche NFR-4)

- **Constat.** NFR-4 dit : « Aucune donnée ne quitte le poste, hormis par une brique réseau activée explicitement. » AD-15 autorise deux sorties hors brique : la sonde du diagnostic, qui part sans action de l'utilisateur, et le téléchargement. Ce choix est justifié par FR-37, mais il s'écarte de la lettre de NFR-4. La liste des dérogations du memlog (l. 63) ne le mentionne pas.
- **Correction proposée.** Ajouter une dérogation O-9 au PRD. NFR-4 deviendrait : « … hormis par une brique réseau activée explicitement, la sonde de connectivité du diagnostic (sans donnée de l'utilisateur) et le téléchargement d'un modèle demandé par l'utilisateur. » Dans AD-15, préciser que la sonde n'envoie aucune donnée (`HEAD` vers une adresse fixe).

### U-10 — Table des emplacements incomplète et segments imbriqués en lazy loading — faible — AD-4, AD-25

- **Constat.**
  - L'emplacement « dans le tour » liste `tool_result`, `subagent_result` et `skill_body`, mais pas `tool_catalog`. Or AD-25 fait entrer la documentation MCP chargée pendant le tour comme réponse d'outil de type `tool_catalog`.
  - En lazy loading, chaque ligne d'outil MCP est un segment `tool_catalog` situé *à l'intérieur* de la description de `load_tool_doc`, qui est elle-même un segment de la variable `tools`, couvert « de la première à la dernière chaîne ». Ces segments sont imbriqués, alors que le découpage de l'étape 5 suppose des segments disjoints.
- **Correction proposée.** Ajouter `tool_catalog` à l'emplacement « dans le tour ». Pour l'étape 3 d'AD-4, poser que le segment le plus interne l'emporte et que le reste du parent lui revient.

### U-11 — Téléchargement des modèles RAG « à l'activation » : automatique ou sur intention ? — faible — AD-21 contre AD-15

- **Constat.** AD-21 dit : « la même voie sert aux modèles d'embedding et de reranking, à l'activation de la brique RAG ». On peut le lire comme un téléchargement automatique. AD-15 limite le téléchargement à l'intention explicite `download_model`.
- **Correction proposée.** Dans AD-21, écrire : « à l'activation, si les modèles manquent, la brique RAG est indisponible, avec l'action "Télécharger" (`download_model`) ».

### U-12 — Petites contradictions d'AD-15 avec AD-21 et le diagnostic — faible

- **Constat.**
  - AD-15 réserve la boucle locale « aux adaptateurs de modèle et à la découverte ». Or AD-21 (étape 1) interroge `GET /api/health` d'une autre instance sur la boucle locale, et seul `net` crée des clients HTTP.
  - « Avant tout import d'une bibliothèque tierce » n'est pas exact, puisque `truststore` est lui-même une bibliothèque tierce.
  - La proposition R-04 voulait que les sorties hors brique soient « affichées dans le diagnostic ». AD-21 ne dit pas que la page `/diagnostic` projette les `outbound_request{origin: diagnostic|download}`.
- **Correction proposée.** Ajouter le contrôle d'instance aux usages autorisés de la boucle locale. Écrire « avant tout autre import tiers ». Dans AD-21, ajouter que la page de diagnostic liste les `outbound_request` avec leur `origin`.

### U-13 — Catalogue d'AD-2 et charge utile des événements NFR-8 — faible — AD-2, AD-3, AD-14, AD-9

- **Constat.**
  - `session_reset` est cité par l'enveloppe d'AD-2 mais n'apparaît pas dans la liste des `kind` fixés.
  - L'abandon d'une action armée (AD-3) et la collision de noms (AD-14) émettent « un événement » qui n'a pas de `kind`.
  - `context_overflow{used, usable}` ne porte ni le message français, ni les pistes (« fenêtre glissante, compaction… ») ni les propositions pour poursuivre, alors que NFR-8 les exige. La convention « Messages » le laisse seulement supposer.
- **Correction proposée.** Ajouter au catalogue :
  - `session_reset` ;
  - `armed_action_dropped` ;
  - `tool_unavailable`.

  Donner à `context_overflow`, `output_truncated` et `limit_reached` des champs `message_fr` et `next_steps_fr[]`. Pour `context_overflow`, les pistes proposées comprennent le passage en lazy loading.

### U-14 — État « non contacté » et diagrammes — faible — AD-12, AD-15, Structural Seed

- **Constat.**
  - L'état « non contacté » d'un serveur MCP public (AD-15) n'existe pas dans le contrat `wanted` / `available` d'AD-12.
  - Le diagramme du tour n'a pas de branche « sortie coupée » (`output_truncated`).
  - Le diagramme des processus ne montre pas la sonde de connectivité.
- **Correction proposée.** Dans AD-12, ajouter un état de connexion (`not_contacted | connected | unavailable`) pour les composants `network_service`. Ajouter la branche `length` dans le diagramme du tour, et la sonde dans le diagramme des processus.

### U-15 — Effets d'un tour non terminé — faible — AD-17, AD-23

- **Constat.** Un tour en `limit`, `overflow` ou `error` n'entre pas dans l'historique. Mais les effets `SkillLoaded` et `ToolDocLoaded` qu'il a appliqués modifient l'état conversationnel des tours suivants : le skill est chargé sans trace dans l'historique. Le spine ne dit pas si ces effets sont conservés ou annulés. En revanche, `MemoryWrite` et `AuditAppend` sont volontairement durables.
- **Correction proposée.** Dans AD-17, préciser que les effets conversationnels d'un tour non `completed` sont annulés (retour à l'instantané) et que les effets durables (mémoire, audit) restent.

## 3. Exigences discrètes du PRD

| Exigence | État après la mise à jour | Constat |
|---|---|---|
| NFR-1 : 30 s par appel, fenêtre plafonnée pour tenir la borne | Tenue par transitivité : la fenêtre définitive est mesurée, et les scénarios tiennent dans la fenêtre. Rompue si l'ajout seul échoue (relecture complète du modèle hybride). | U-02, U-08. Hors périmètre : l'appel qui suit une délégation sans `save_state` (R-09) reste hors borne, sans dérogation écrite. |
| NFR-3 : aucune télémétrie ; sans réseau, briques indisponibles avec explication | Télémétrie HF coupée ; garde bloquante ; vérification à l'activation | U-01 (la garde telle qu'écrite ne fonctionne pas). |
| NFR-4 : rien ne sort hors brique réseau activée | Sonde et téléchargement hors brique | U-09 (dérogation non déclarée), U-01 (sorties non annoncées). |
| FR-2 : chaque segment étiqueté par sa brique ; intégralité du contexte | Attribution exacte hors sortie du modèle pendant le tour | U-03, U-10. |
| FR-30 : tokens par segment, donc par brique | Somme exacte par construction | U-05 (primitive absente du port), U-03. |
| FR-41 : jauge ventilée selon FR-2, mise à jour à chaque appel | Ventilation fermée, réserve variable | U-03, U-04 (double comptage au tour suivant). |
| FR-42 : action forcée, cycle complet, hooks compris ; badge de l'auteur | Exécuteur unique, `trigger = user` | U-06 (actions forcées annulées si la brique est indisponible faute de parseur). |

## 4. Points bien traités

- Le catalogue d'AD-2 reprend exactement les `kind` de R-01. Les statuts de `turn_ended` (`completed|cancelled|limit|overflow|error`) sont cohérents avec AD-9, AD-10, AD-13, AD-16 et AD-17. Aucun statut n'est contradictoire.
- L'algorithme d'attribution d'AD-4 (double rendu, sentinelles de la zone privée Unicode, contrôle octet pour octet, repli explicite) est plus robuste que la proposition R-02, et il est testable.
- AD-25 ferme proprement R-03. Le choix de `trigger` plutôt que d'`actor` est cohérent avec l'enveloppe.
- L'abandon de `HF_HUB_OFFLINE` et l'import confiné de `huggingface_hub` sont justifiés et tracés.
