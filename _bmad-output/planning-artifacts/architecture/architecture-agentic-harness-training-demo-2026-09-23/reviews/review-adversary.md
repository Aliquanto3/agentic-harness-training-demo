---
title: Revue adverse du spine WaveStack
target: ../ARCHITECTURE-SPINE.md
lens: "Deux unités conformes à la lettre de chaque AD, qui se construisent pourtant de façon incompatible"
date: 2026-09-23
---

# Revue adverse — ARCHITECTURE-SPINE.md (WaveStack)

## Verdict

Le paradigme (journal d’événements, un seul écrivain, contexte en segments, exécuteur d’outils unique) est bon. En revanche, le spine fixe des **principes de propriété** sans fixer les **formes partagées** qui les rendent vérifiables. Presque chaque AD laisse un vocabulaire ouvert : `kind` de segment, forme de `modify`, nom d’outil, identifiant de nœud, sémantique de « tour », modèle d’exécution concurrente. Deux agents qui construisent deux stories en parallèle vont donc inventer deux formes différentes, en respectant tous les deux les AD. J’ai trouvé 22 paires. Sept sont critiques : sans correction, l’intégration casse à coup sûr.

Échelle : **Critique** = incompatibilité certaine à l’intégration ; **Majeur** = incompatibilité probable, ou défaut pédagogique visible en démonstration ; **Mineur** = ambiguïté qu’une story tranchera, au risque qu’elle la tranche mal.

---

## A. Propriété de l’état et chemins de mutation

### F1 — Mémoire globale : trois écrivains possibles [Critique]

- **Story « mémoire globale » (brique)** : elle expose un outil natif `memory_write`. Son implémentation, dans `tools/`, écrit directement `memory.json` (chemin obtenu par `config`, AD-20). Conforme à AD-14 : l’outil passe par l’exécuteur. Conforme à AD-20 : seul `config` résout le chemin.
- **Story « tiroir d’édition de la mémoire »** : elle envoie l’intention `POST edit_memory`, et la `Session` écrit `memory.json`. Conforme à AD-3.
- **Story « Forcer : écrire en mémoire »** : elle appelle `memory_write` par l’exécuteur, avec `actor=user`. Conforme à AD-14 et FR-42.
- **Le conflit.** AD-3 dit « seule la Session modifie la mémoire globale », mais AD-14 place l’**exécution** de l’outil dans `tools`. Un outil qui écrit un fichier respecte AD-14 et viole AD-3, sans que personne ne le voie. Il y a alors deux écrivains de `memory.json`, deux formats possibles (liste de chaînes, ou dictionnaire clé-valeur) et deux événements (`memory_written` émis par l’outil, `global_memory_updated` émis par la session). Autre question sans réponse : une écriture faite à l’appel 2 d’un tour apparaît-elle dans le segment mémoire de l’appel 3 ? La story de la brique relira le fichier, celle du contexte gardera une copie prise en début de tour.
- **Correction (AD-3 à resserrer, nouvel AD-23 « Effets »).**
  - Un outil, un hook ou une brique ne fait **aucune** écriture d’état ni de fichier d’exécution. Il renvoie des **effets** typés (`Effect`, union pydantic dans `session/effects.py`) : `MemoryWrite{op: add|replace|delete, entry_id, text}`, `AuditAppend{lines}`, `SkillLoaded{skill_id}`, `ArmConsumed{armed_id}`.
  - La `Session` applique les effets dans l’ordre, persiste par un `MemoryStore` qu’elle possède seule, et émet un événement par effet appliqué (`global_memory_written{entry_id, op, text, trigger}`).
  - Le format de `memory.json` est fixé : liste d’entrées `{id, text, created_at, source: model|user|demo}`.
  - Le segment de mémoire globale est **recalculé à chaque `assemble_context`**. Une écriture à l’appel N est donc visible à l’appel N+1 : c’est justement ce qu’on veut montrer (« quand et comment la mémoire est injectée »).
  - Le tiroir d’édition produit les mêmes effets, par intention, et seulement hors tour (AD-3).

### F2 — Actions armées : état du navigateur ou état de la session ? [Critique]

- **Story « bouton Forcer » (front)** : la puce « Armé : Caveman » est un état de l’interface. AD-18 autorise un état du navigateur limité à l’interface, et la story le range dans `localStorage`. Au moment de l’envoi, le front joint `forced: [...]` au `POST send`.
- **Story « session / actions armées »** : AD-3 cite « actions armées » dans l’état de la session. La story crée l’intention `arm_action`, stocke la liste et la consomme au tour suivant.
- **Le conflit.** Il y a deux sources de vérité. Après un rechargement, la puce réapparaît depuis `localStorage` alors que la session l’a déjà consommée, ou l’inverse. AD-17 dit que le rejeu « applique les actions armées », mais lesquelles : celles du `POST` ou celles de la session ? Rien ne fixe non plus le **moment** de la consommation (avant le premier appel ? après `on_user_message` ?), l’**ordre** entre deux actions armées (skill et sous-agent), la **forme** d’une action (un outil forcé porte des arguments, FR-42), ni ce qui arrive si la brique ciblée devient indisponible entre l’armement et le tour.
- **Correction (AD-3 à resserrer).**
  - `ArmedAction{armed_id, kind: tool_call|memory_write|mcp_doc_load|skill_trigger|subagent_delegate, brick, target, args}` vit **uniquement** dans la session.
  - Intentions `arm_action` et `disarm_action`. Événements `action_armed`, `action_disarmed`, `action_consumed`, `action_dropped{reason}`. Le front projette la puce depuis ces événements, jamais depuis `localStorage`.
  - Consommation : après `on_user_message` et avant le premier `assemble_context`, dans l’ordre d’armement, chaque action passant par l’exécuteur (AD-14) avec `trigger=user`.
  - Une action dont la brique est indisponible est abandonnée, avec un événement.
  - La liste est vidée en fin de tour, **même** si le tour échoue ou est arrêté.
  - Le rejeu consomme les actions armées **courantes**, jamais celles du tour d’origine.

### F3 — Instantané du rejeu : les réglages restaurés annulent la démonstration [Critique]

- **Story « rejeu » (AD-17 à la lettre)** : elle restaure l’instantané du tour d’origine, qui contient l’historique, la configuration des briques, le **prompt système** et les **réglages**, puis applique la configuration **courante** des briques.
- **Story « bornes de boucle » (AD-10)** : le formateur passe de 6 à 2 appels maximum, puis rejoue pour provoquer l’événement de limite (matériau pédagogique cité dans le memlog).
- **Story « prompt système éditable » (FR-11)** : on modifie le prompt, puis on rejoue pour comparer.
- **Le conflit.** AD-17 restaure les réglages (bornes, fenêtre) et le prompt système du tour d’origine. Le rejeu ignore donc la modification que le formateur vient de faire, et la démonstration échoue en silence. Pire : restaurer une fenêtre différente oblige à recharger le modèle (AD-9) en plein rejeu. La phrase « restaure l’instantané, puis applique la configuration courante des briques » laisse chaque story décider seule de ce qui est « configuration » et de ce qui est « état ».
- **Correction (AD-17 à réécrire).** L’instantané ne contient **que l’état conversationnel** : l’historique de la branche active et les skills chargés (voir F6). Tout le reste est de la **configuration courante** au moment du rejeu : briques, sous-options, hooks actifs, prompt système, réglages (fenêtre, bornes), modèle, actions armées. La mémoire globale reste, comme aujourd’hui, dans son état courant. Une seule fonction, `Session.build_turn_state(origin_turn | None)`, sert à la fois l’envoi et le rejeu.

### F4 — Journal d’audit H2 : le hook, la trace ou un puits de fichiers ? [Majeur]

- **Story « H2 »** : la fonction hook ouvre `audit.log` (chemin par `config`) et y ajoute une ligne à `after_tool` et à `on_turn_end`. Pour consigner « chaque appel au modèle », elle relit ce qu’elle peut du tour.
- **Story « trace »** : elle ajoute un puits générique qui écrit tous les événements dans un fichier, pour le débogage. Une story voisine le branche sur `audit.log`, puisque c’est « le fichier du journal ».
- **Story « schéma »** : elle doit allumer le nœud fichier `audit.log` quand on y écrit, mais aucun événement ne le signale.
- **Le conflit.** Il y a deux écrivains du même fichier et deux formats. Le hook fait une entrée-sortie alors qu’AD-13 le décrit comme une fonction qui « renvoie une décision ». L’**entrée** d’un hook n’est définie nulle part : sans elle, H2 ne peut pas voir les appels au modèle du tour, et H1 ne sait pas sur quoi comparer.
- **Correction (AD-13 à resserrer, avec AD-23 d’F1).**
  - Signature : `hook(ctx: HookContext) -> HookResult{decision, detail, effects}`. `HookContext` est une vue en lecture seule : le point d’accroche, `turn_id`, `context_id`, l’appel d’outil résolu (voir F9) et les événements du tour jusqu’ici.
  - H2 renvoie `AuditAppend{lines}`. La session écrit le fichier (format JSON Lines, dates ISO) et émet `audit_appended{path, lines}`. Le schéma allume son nœud à partir de cet événement.
  - `trace` n’écrit **aucun** fichier.

### F5 — `modify` de H3 : réécrire le message ou ajouter un segment ? [Majeur]

- **Story « H3 »** : à `on_user_message`, elle renvoie `modify` avec le message réécrit (« [date] [règles] + message »). Conforme à AD-13 : « modify, avec le détail ».
- **Story « jauge / contexte »** : elle attribue le texte du message au segment « Message et gabarit ».
- **Le conflit.** L’injection du hook devient invisible dans la ventilation, alors que FR-2 exige un segment « injections de hook ». Le message modifié entre aussi dans l’historique, et un rejeu y réapplique H3 : double injection. Le même mot `modify` voudra dire « nouveaux arguments » à `before_tool` et on ne sait quoi à `before_model_call`.
- **Correction (AD-13).** Une matrice fermée fixe, pour chaque point d’accroche, les décisions permises et la forme de `modify` :
  - `on_user_message` : `modify` ajoute un segment `hook_injection` (`brick=hooks`). Il ne réécrit **jamais** le message. L’historique garde le message d’origine, et l’injection est recalculée à chaque tour.
  - `before_tool` : `modify` remplace les `args`.
  - `before_model_call` et `on_turn_end` : `allow` ou `block` seulement.
  - `ask_human` : autorisé seulement à `before_tool`.

---

## B. Contexte, segments, tokens, jauge

### F6 — Contenu d’un skill : résultat d’outil ou segment de brique ? [Critique]

- **Story « skills », variante A** : le déclenchement est un outil `load_skill(name)`. Son résultat, le contenu de `SKILL.md`, est réinjecté comme n’importe quel résultat d’outil. Conforme à AD-14.
- **Story « skills », variante B** : le skill déclenché devient un état, et la brique skills contribue un segment `skill_body` à chaque `assemble_context`, dans le bloc système. Conforme à AD-4 et AD-12.
- **Le conflit.**
  - En A, AD-22 **compresse** les résultats d’outils : Caveman serait compressé par Headroom. Le contenu vit aussi dans l’historique, disparaît si la mémoire courte est éteinte, et la jauge le range dans « résultats d’outils ».
  - En B, le contenu survit à l’extinction de la mémoire courte et se place en tête du contexte. Avec le modèle hybride, cela force une relecture complète du contexte (memlog).
  - La comparaison de tours aligne les segments par brique : A donne `brick=tools`, B donne `brick=skills`. FR-25 (Caveman appliqué au tour rejoué) n’a aucun sens défini en A.
- **Correction (AD-4 et nouvel AD « Skills »).**
  - Le déclenchement est un appel à l’outil `load_skill`, déclaré par la brique skills et passé par l’exécuteur (hooks compris, FR-42).
  - Son résultat réinjecté est un accusé court. L’exécuteur renvoie l’effet `SkillLoaded`, et la session ajoute le skill à `loaded_skills` (état conversationnel, dans l’instantané, voir F3).
  - La brique skills contribue un segment `skill_body` par skill chargé, à une position fixe (après le catalogue des skills). Ce segment est exclu de la compression.
  - « Vider la conversation » décharge les skills.

### F7 — `segment.kind` n’est pas un vocabulaire fermé : jauge, comparaison et contexte divergent [Critique]

- **Story « contexte »** : elle choisit librement ses `kind` (`system`, `history_msg`, `tool_desc`…).
- **Story « jauge »** : elle code en dur l’ordre de l’UX (prompt système, mémoire globale, descriptions d’outils et de skills, historique, RAG, résultats d’outils, message et gabarit) avec ses propres clés.
- **Story « sous-agent »** et **story « H3 »** : elles inventent `subagent_result` et `hook_inject`, deux clés absentes de l’ordre de l’UX.
- **Le conflit.** La jauge ne sait pas classer les `kind` inconnus et les range dans « autre », ou les perd. Si le front fait lui-même la correspondance, il viole AD-1 (« ne recalcule pas »). Autre ambiguïté : un résultat d’outil d’un tour **précédent** est-il `tool_result` (brique outils) ou `history` (brique mémoire courte) ? Selon la réponse, la jauge ventile différemment.
- **Correction (AD-4).** Une énumération fermée `SegmentKind` vit dans `context`, avec pour chaque valeur son ordre d’empilement dans la jauge, son libellé français (dans `content/`) et sa brique propriétaire par défaut :
  `system_prompt, global_memory, tool_catalog, skill_catalog, skill_body, history, rag_excerpt, tool_result, subagent_result, hook_injection, user_message, template, reasoning_history`.
  - Tout ce qui vient d’un tour antérieur est `history` (`brick=short_memory`), quel que soit son type d’origine.
  - La ventilation de la jauge est calculée **côté Python** et portée par l’événement `context_rendered{call_id, segments, total, window, reserve, by_kind}`.
  - Ajouter un `kind` passe par un amendement du spine, pas par une story.

### F8 — Tokens par segment quand le gabarit entrelace et reformate [Critique]

- **Story « contexte », variante A** : elle compte chaque `segment.text` séparément avec `tokenize`, puis attribue `template = total − Σ segments`.
- **Story « contexte », variante B** : elle rend avec des marqueurs sentinelles et compte les tokens entre les marqueurs.
- **Le conflit.** La tokenisation BPE n’est pas additive : les fusions à la frontière entre segments donnent une somme différente, et `template` peut devenir **négatif**. Surtout, le gabarit Qwen **reformate** les outils (`tools | tojson` dans le bloc système) et le raisonnement : le texte du segment n’est pas le texte présent dans le prompt. A affiche un segment dont le texte n’a jamais été envoyé, ce qui viole l’esprit d’AD-4, alors que les deux variantes respectent sa lettre (« la somme est égale au total »). Les deux stories de comparaison et de jauge obtiendront des chiffres différents pour le même tour.
- **Correction (AD-4, algorithme normatif dans `context/render.py`).**
  1. Rendre le gabarit une fois, en remplaçant chaque texte de segment par un marqueur unique.
  2. Remplacer ensuite chaque marqueur par le texte réel, en notant les intervalles de caractères. `segment.text` devient **la sous-chaîne exacte du prompt rendu**, y compris quand le gabarit l’a sérialisée (un outil = un segment `tool_catalog`, texte = son JSON rendu).
  3. Tokeniser le prompt **entier** une fois, puis détokeniser jeton par jeton pour retrouver les positions.
  4. Attribuer chaque jeton au segment qui contient son premier caractère, et le reste à `template`.

  La somme est égale au total par construction. Le moteur factice des tests vérifie cette égalité et l’absence de valeur négative.

### F9 — Collision de noms entre outils natifs et MCP, et ce qui fait déclencher les hooks [Critique]

- **Story « outils natifs »** : outil `read_file`. H1 bloque `tool.name == "read_file"` si le chemin est dans le dossier confidentiel.
- **Story « serveur MCP local »** : elle expose aussi `read_file`, ou `search`. data.gouv.fr et Microsoft Learn exposent chacun leur propre `search`.
- **Story « H5 »** : elle suspend « les outils réseau » repérés par une liste de noms.
- **Le conflit.** Le parseur (AD-6) renvoie un nom nu. L’exécuteur trouve deux candidats, prend le premier et exécute le mauvais. H1 bloque le `read_file` MCP (ou le laisse passer). H5 manque les outils MCP publics. AD-14 définit bien une `source`, mais pas l’unicité du nom exposé au modèle ni la clé que les hooks comparent.
- **Correction (AD-14).**
  - Un `ToolRegistry` dans `tools` est le **seul** attributeur de noms exposés : outil natif = nom nu, outil MCP = `{server_id}__{tool}`. L’unicité est vérifiée à l’enregistrement ; en cas de collision, l’outil est indisponible, avec un événement.
  - Chaque outil déclare des **drapeaux** : `network: bool`, `reads_local_path: arg_name | None`, `hosting`.
  - Les hooks comparent des drapeaux et des arguments résolus, jamais des noms. H1 agit sur tout outil `reads_local_path` dont le chemin normalisé (`Path.resolve`) est sous le dossier confidentiel. H5 agit sur tout outil `network=true`, natif ou MCP.

### F10 — Propriété du segment « descriptions d’outils » quand cinq briques en apportent [Majeur]

- **Stories « outils », « MCP », « skills » (`load_skill`), « sous-agent » (`delegate`) et « mémoire » (`memory_write`)** : chacune contribue ses outils. Le gabarit les rend tous dans **un seul** bloc `tools`.
- **Le conflit.** La brique outils désactivée tout en laissant la brique MCP active pose problème : AD-10 range les bornes de boucle dans la « sous-option de la brique outils », si bien que la boucle agent n’a plus de réglage. Et qui possède le bloc `tools` ? La story « outils » crée un seul segment `tool_catalog` (`brick=tools`) contenant aussi les outils MCP, alors que la story « MCP » attend un segment à son nom, pour montrer les +2 900 tokens (FR-20, FR-21).
- **Correction (AD-10 et AD-12).**
  - La boucle agent appartient au **cœur de la session**, pas à une brique. Ses bornes sont des réglages de session, **affichés** sur la carte outils.
  - Toute brique qui contribue un outil exige la capacité `tool_call_parser`.
  - Un segment `tool_catalog` par outil, dont la `brick` est la brique déclarante. En mode lazy loading, le segment est la souche (nom et une ligne), puis la description complète après `mcp_doc_load`.

### F11 — Compression : une brique ne peut pas transformer les segments des autres [Majeur]

- **Story « compression »** : elle en fait une brique (AD-12) qui, à `assemble_context`, renvoie des copies compressées des segments `tool_result` et `rag_excerpt`. Conforme à la règle « une brique renvoie des contributions et ne modifie rien ».
- **Story « contexte »** : elle concatène toutes les contributions.
- **Le conflit.** Les segments apparaissent en double, les tokens sont comptés deux fois, et la jauge dépasse la réalité. L’alternative est que la brique importe la brique outils, ce qui viole « une brique n’importe jamais une autre brique ».
- **Correction (AD-4 et AD-22).** Il faut ajouter une étape fixe `transform_context`, entre `assemble_context` et le rendu, **appelée par la session**. Le `Compressor` y reçoit les segments de `kind ∈ {tool_result, rag_excerpt}` et renvoie des remplaçants qui gardent la `brick` et le `kind` d’origine, avec `compressed_from: {tokens_before, text_before}`. `skill_body`, `subagent_result` et `history` ne sont jamais compressés en V1.

---

## C. Tours, contextes, identifiants

### F12 — Ce qu’est un « tour » : identifiants de segments en collision, hooks du sous-agent [Critique]

- **Story « sous-agent »** : elle garde le `turn_id` du tour principal, prend `context_id=sub1` et numérote ses appels à partir de 1. Conforme aux conventions.
- **Story « contexte »** : `segment.id = {turn_id}.{call}.{n}`.
- **Le conflit.** L’appel 2 du principal et l’appel 2 du sous-agent produisent tous les deux `t3.2.1`. La sélection synchronisée (FR-4) et la comparaison mélangent alors les deux contextes. Les hooks posent la même question : le sous-agent déclenche-t-il `on_user_message` (sa tâche) et `on_turn_end` ? Si oui, H2 et H3 s’exécutent deux fois par tour, et H3 injecte la date dans le sous-agent. `sub{n}` est-il numéroté par tour ou par session ? Côté rejeu : un nouveau `turn_id`, mais comment le front sait-il quel tour il rejoue ?
- **Correction (conventions et AD-11).**
  - `segment.id = {turn_id}.{context_id}.{call}.{n}`, avec `call` compté **par contexte**. `sub{n}` est numéroté par session.
  - Le sous-agent n’est **pas** un tour. Il déclenche `before_model_call`, `before_tool` et `after_tool` avec son `context_id`, mais jamais `on_user_message` ni `on_turn_end`.
  - `turn_started{turn_id, replay_of: turn_id|null, restored_from: turn_id|null, user_message}`.
  - L’historique est une **liste de tours de la branche active**. Rejouer t3 fait de t4 la suite de t2, et t3 reste consultable hors branche.

### F13 — L’enveloppe ne porte ni l’étape, ni le déclencheur, ni le composant [Critique]

- **Story « exécuteur »** : `tool_executed` porte `actor=harness`, puisque c’est le harnais qui exécute.
- **Story « orchestration »** : elle affiche le badge « forcé par l’utilisateur » à partir de `actor`, comme le demande AD-2.
- **Story « schéma »** : elle doit allumer « le nœud de l’outil » ou « le nœud du hook » (UX), mais l’enveloppe ne porte que `brick`.
- **Le conflit.** Une action forcée donne `actor=user` sur un événement et `actor=harness` sur les suivants : le badge est incohérent d’une étape à l’autre. Rien ne relie les événements d’un même cycle d’outil (demande, `before_tool`, exécution, `after_tool`, réinjection) pour les regrouper ou pour la sélection synchronisée. Chaque story ajoutera son `call_id` dans son `payload`, sous un nom différent.
- **Correction (AD-2 : l’enveloppe devient)**
  `{seq, ts, session_epoch, turn_id|null, context_id|null, step_id|null, parent_step|null, kind, actor, trigger, brick, component|null, payload}`
  - `actor` = qui **produit** l’événement. `trigger ∈ {model, user, harness, hook}` = qui a **causé** la chaîne. Il est hérité de l’étape parente, et c’est lui qui porte le badge.
  - `step_id` (`{turn_id}.{context_id}.s{n}`) regroupe un cycle.
  - `component` est l’identifiant de nœud du schéma (F14).
  - `turn_id` et `context_id` valent `null` hors tour (démarrage MCP, téléchargement, diagnostic).
  - La portée courante est posée par la session dans une `contextvar` `TraceScope`. `net`, `mcp` et `tools` émettent sans recevoir de paramètres. Attention : la portée doit être **copiée explicitement** lors d’un passage de thread à boucle (F16).

### F14 — Identifiants des nœuds du schéma [Majeur]

- **Story « MCP »** : elle déclare le composant `datagouv`. **Story « outils »** : un composant par outil, `clock`, `calculator`. **Story « hooks »** : un composant `hooks`.
- **Story « schéma »** : elle crée un nœud par brique (`id = brick.id`), et un nœud par composant seulement pour les composants réseau.
- **Le conflit.** Les identifiants ne sont pas uniques entre briques (`local` pour le MCP local et pour un outil `local`). Les nœuds fixes (Harnais, Modèle, second Modèle du sous-agent, fichiers mémoire et audit) n’appartiennent à aucune brique : chaque story les nomme à sa façon (`harness`, `core`, `llm`). Les arêtes ne sont déclarées nulle part, donc la story « schéma » les invente et « le flux s’arrête au hook » n’est pas dérivable.
- **Correction (AD-12).**
  - Identifiant de composant = `{brick_id}.{component}`, unique et validé au chargement des briques.
  - Nœuds fixes réservés : `core.harness`, `core.model`, `core.model_sub`, `file.memory`, `file.audit`, `file.demo_dir`.
  - Chaque composant déclare `edges_to: [component_id]`.
  - Le schéma est une réponse de lecture de l’API, `GET /architecture` (nœuds, arêtes, état, raison), recalculée à chaque `bricks_changed`. Le halo se déduit du champ `component` des événements (F13).

### F15 — Sous-agent : quelles briques contribuent à son contexte ? [Majeur]

- **Story « sous-agent »** : elle construit elle-même un contexte minimal (tâche et outils), ce qui l’oblige à connaître la brique outils et viole la règle d’import.
- **Story « session »** : elle appelle `assemble_context(context_id=sub1)` sur **toutes** les briques actives.
- **Le conflit.** Dans le second cas, le sous-agent reçoit la mémoire globale, les 2 900 tokens de data.gouv.fr, le catalogue des skills et l’injection H3. L’économie montrée par FR-29 disparaît, et le dépassement de fenêtre dans le sous-agent devient probable.
- **Correction (AD-11 et AD-12).** Chaque brique déclare `contributes_to: {main, sub}`, avec `main` seul par défaut. Le contexte du sous-agent se limite à : un gabarit, un prompt système du sous-agent (fichier dans `content/`), la tâche, et les outils que la brique sous-agent liste dans sa déclaration (lecture de page web par défaut). Le contrôle de fenêtre d’AD-9 s’applique aussi au sous-agent, avec son propre événement de dépassement.

---

## D. Concurrence, flux, annulation

### F16 — llama-cpp bloquant, FastAPI asynchrone, client MCP asynchrone : aucun modèle d’exécution [Critique]

- **Story « moteur »** : `complete()` est un générateur **synchrone**, puisque llama-cpp-python bloque.
- **Story « web / session »** : le tour s’exécute dans le gestionnaire `async` du `POST send`. La boucle d’événements est bloquée pendant 30 s de prefill, le flux SSE se fige, et l’intention « arrêt » n’est jamais reçue.
- **Story « MCP »** : le SDK `mcp` est asynchrone ; les clients vivent sur la boucle principale.
- **Story « net »** : `httpx.AsyncClient` partagé (AD-15 dit « un client httpx partagé »), alors que les outils natifs synchrones veulent un `httpx.Client`.
- **Le conflit.** Chaque story choisit son modèle. L’un appelle `asyncio.run()` dans un thread, ce qui crée une seconde boucle, et le client MCP lié à la première échoue. L’autre bloque la boucle principale. `contextvars` (F13) ne traverse pas `run_coroutine_threadsafe`.
- **Correction (nouvel AD « Modèle d’exécution »).**
  - Un seul **thread de travail** exécute tours, rechargements de modèle et réinitialisations. La session y est synchrone, et le port `Engine` est synchrone.
  - La boucle asyncio de FastAPI reçoit les intentions et sert le SSE. Elle ne touche jamais l’état.
  - Le journal d’événements est une liste protégée par un verrou, avec réveil des abonnés SSE par `loop.call_soon_threadsafe`.
  - Les clients MCP vivent sur la boucle principale. Les appels venant du thread de travail passent par `run_coroutine_threadsafe(...).result(timeout)`, avec copie explicite de la `TraceScope`.
  - `net` fournit un `Client` synchrone et un `AsyncClient`, construits par la **même** fabrique (truststore, proxy, liste d’adresses autorisées, émission des données sortantes).

### F17 — Arrêt du tour : aucun mécanisme d’annulation [Critique]

- **Story « session »** : elle accepte l’intention « arrêt » (AD-3) et positionne un drapeau.
- **Story « moteur »** : `complete(stream=False)` renvoie la chaîne complète, et rien ne permet d’interrompre la génération. **Story « outils »** : un appel `httpx` de 20 s. **Story « H5 »** : l’attente n’a pas de délai d’expiration (AD-13).
- **Le conflit.** Le drapeau n’est lu par personne. Un arrêt pendant une attente H5 laisse le tour suspendu pour toujours. Personne ne décide si le message et la réponse partielle d’un tour arrêté entrent dans l’historique, alors que la story « rejeu » et la story « mémoire courte » dépendent de ce choix.
- **Correction (AD-3 et AD-5).**
  - Un `CancelToken` est passé à tout appel bloquant des ports (`Engine.complete`, exécuteur, `net`, attente H5).
  - Les adaptateurs streament **toujours** en interne et testent le jeton à chaque token. Le prefill de llama-cpp n’est pas interruptible : la latence d’arrêt est bornée par le prefill en cours, et l’interface affiche « arrêt demandé ».
  - Un arrêt pendant H5 résout l’attente en `cancelled`.
  - Le tour se termine par `turn_ended{status: completed|cancelled|limit|overflow|error}`.
  - Un tour qui n’est pas `completed` reste dans la trace mais **n’entre pas** dans l’historique de la branche.

### F18 — Événements de streaming des tokens [Majeur]

- **Story « moteur »** : un événement `model_token{text}` par token. À 30 tokens/s, un tour de 500 tokens produit 500 `seq`. Un rechargement rejoue des milliers d’événements.
- **Story « vue humain »** : elle concatène les deltas et masque le raisonnement (FR-9) en repérant `<think>` côté JS.
- **Story « compteur »** : elle compte les tokens de sortie en comptant les événements.
- **Le conflit.** Repérer `<think>` dans le front viole AD-1 (l’interface recalcule), et le repérage dépend du modèle alors que c’est le rôle d’AD-6. Les fragments de llama-cpp-python peuvent couper un caractère UTF-8 multioctet : les accents français s’affichent en `�`. Le décompte par événement devient faux dès qu’une story regroupe les tokens.
- **Correction (AD-2 et AD-6).**
  - `model_delta{call_id, channel: reasoning|text|tool_call, text}` : texte UTF-8 complet, regroupé toutes les 50 ms au plus. Le découpage par canal est fait par un **séparateur incrémental** fourni par le registre de capacités.
  - `model_call_finished{call_id, raw_output, reasoning, text, tool_calls, output_tokens, prompt_tokens, elapsed_ms, stop_reason}` **fait foi**. Les projections remplacent les deltas par cet événement.

### F19 — Attente H5, rechargement du navigateur, deux onglets [Majeur]

- **Story « H5 »** : elle émet `approval_requested` et attend l’intention `approve` ou `deny`.
- **Story « front / reconnexion »** : au rechargement, elle rejoue le SSE depuis `seq=0` et reconstruit la boîte de dialogue seulement si elle a gardé une trace locale.
- **Le conflit.** Sans identifiant de demande, une réponse venue d’un onglet périmé, ou d’un second onglet (AD-3 dit une session, pas un seul client), valide la mauvaise attente. Si rien ne permet de déduire du journal qu’une attente est **en cours**, le rechargement perd la boîte de dialogue et le tour reste bloqué sans délai d’expiration. La réinitialisation (FR-39) remet-elle `seq` à 0 ? Un client qui reprend à `seq=812` ne recevrait alors plus rien.
- **Correction (AD-2, AD-3 et AD-13).**
  - `approval_requested{approval_id, tool, destination, preview}` et `approval_resolved{approval_id, decision: approved|denied|cancelled, by}`. L’intention porte `approval_id` : la première réponse l’emporte, les suivantes sont refusées avec leur raison.
  - `GET /state` (construit depuis le journal) renvoie l’état courant : opération en cours, attente en cours, actions armées, briques, dernier `seq`. Le front démarre par `/state`, puis reprend le SSE à `last_seq+1`.
  - `seq` ne redémarre jamais : la réinitialisation émet `session_reset` et incrémente `session_epoch`, et les projections se vident à cet événement.
  - Le journal vit en mémoire : un redémarrage du processus le perd, et c’est assumé.

### F20 — H5 montre « les données qui sortiraient », mais `net` ne les connaît qu’à l’envoi [Majeur]

- **Story « H5 »** : elle affiche l’outil et ses arguments.
- **Story « net » (AD-15)** : elle émet la charge exacte **au moment** de l’envoi, après les hooks. Pour le MCP public, la requête JSON-RPC est construite dans le SDK.
- **Le conflit.** FR-27 exige que l’utilisateur voie les données exactes **avant** d’accepter. Les deux stories respectent leur AD, et la promesse n’est pourtant pas tenue.
- **Correction (AD-14 et AD-15).**
  - Chaque outil `network=true` fournit `preview_request(args) -> {method, url, body}`, que H5 affiche. Pour le MCP, l’exécuteur construit lui-même le corps `tools/call` (déterministe) et le passe au transport.
  - `net` émet ensuite l’événement réel, et l’interface signale tout écart entre l’aperçu et l’envoi.

---

## E. Réglages, modèle et opérations longues

### F21 — Changements de réglages et de modèle : une « opération » qui n’est pas un tour [Majeur]

- **Story « fenêtre » (AD-9)** : l’intention `set_window` recharge le modèle (5 à 20 s) dans le gestionnaire HTTP.
- **Story « changement de modèle » (FR-32)** : même chose, par une autre intention. **Story « réinitialisation »** : elle recharge `content/`.
- **Le conflit.** AD-3 ne verrouille que les **tours**. Un envoi pendant un rechargement, un changement de fenêtre pendant un changement de modèle ou une réinitialisation pendant un rechargement sont tous « conformes », et leur combinaison appelle `close()` sur un moteur utilisé ailleurs. AD-8 ne dit pas ce qui arrive quand le budget refuse la nouvelle fenêtre : l’ancienne est-elle gardée ? Et qui écrit `settings.json` : `config.save()`, appelé par la story fenêtre, ou la session ? Les conventions disent seulement « via une intention ».
- **Correction (AD-3).**
  - Un seul verrou d’**opération** : `idle | turn | model_load | reset`. Toute intention qui modifie l’état est refusée hors `idle`, sauf H5 et l’arrêt pendant `turn`. L’envoi est refusé pendant `model_load`, avec la raison (déjà dans l’UX).
  - Un rechargement refusé par le budget laisse le modèle et la fenêtre précédents actifs, et émet un événement.
  - La session est le seul appelant de `config.save_settings()`.
  - Un réglage modifié prend effet **au tour suivant**, jamais au milieu d’un tour.

### F22 — Brique « activée » ou « disponible » après un changement de modèle [Mineur]

- **Story « capacités » (AD-6)** : elle réévalue au changement de modèle et **désactive** la brique outils si le nouveau modèle n’a pas de parseur.
- **Story « scénarios »** : elle fixe la liste des briques et des hooks actifs, et s’attend à la retrouver quand on revient au modèle précédent.
- **Le conflit.** Le premier modèle efface le choix de l’utilisateur, le second suppose qu’il est gardé.
- **Correction (AD-12).** L’état d’une brique est `wanted` (choix de l’utilisateur ou du scénario, persistant) et `available` (calculé). L’état effectif est `wanted ∧ available`. Un changement de modèle ne modifie jamais `wanted`.

---

## Récapitulatif des amendements

| AD | Amendement | Findings |
| --- | --- | --- |
| AD-2 | Enveloppe étendue (`session_epoch`, `step_id`, `parent_step`, `trigger`, `component`, identifiants nuls hors tour) ; `model_delta` et `model_call_finished` ; approbations identifiées ; `GET /state` | F13, F18, F19 |
| AD-3 | Verrou d’opération ; actions armées dans la session seulement ; `CancelToken` ; la session seule écrit `settings.json` ; les réglages prennent effet au tour suivant | F2, F17, F21 |
| AD-4 | `SegmentKind` fermé avec ordre de jauge ; algorithme d’attribution des tokens par positions ; étape `transform_context` ; un segment `tool_catalog` par outil | F7, F8, F10, F11 |
| AD-6 | Séparateur incrémental des canaux de sortie | F18 |
| AD-10 | Boucle agent dans le cœur de la session, pas dans la brique outils | F10 |
| AD-11 | Le sous-agent n’est pas un tour ; déclaration `contributes_to` ; fenêtre du sous-agent | F12, F15 |
| AD-12 | Identifiants `{brick}.{component}`, nœuds réservés, `edges_to`, `GET /architecture` ; `wanted` et `available` | F14, F22 |
| AD-13 | `HookContext` et `HookResult` ; matrice des décisions par point d’accroche ; `ask_human` seulement à `before_tool` | F4, F5, F19 |
| AD-14 | `ToolRegistry` et noms préfixés pour le MCP ; drapeaux `network` et `reads_local_path` ; `preview_request` | F9, F20 |
| AD-17 | L’instantané ne contient que l’état conversationnel ; branche active | F3, F12 |
| AD-22 | La compression est une étape de la session, avec liste blanche de `kind` | F11 |
| **Nouveau AD-23** | Effets typés, appliqués par la session seule (mémoire, audit, skill chargé) | F1, F4, F6 |
| **Nouveau AD-24** | Modèle d’exécution : un thread de travail, boucle asyncio pour le web et le MCP, `net` synchrone et asynchrone | F16 |
| **Nouveau AD-25** | Skills : `load_skill`, puis `loaded_skills`, puis segment `skill_body` | F6 |
