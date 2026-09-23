---
title: Revue adverse de la mise à jour R-01 à R-04 du spine WaveStack
target: ../ARCHITECTURE-SPINE.md
scope: "AD-2, AD-4, AD-9, AD-10, AD-15, AD-21, AD-25 (modifications du 2026-09-23, entrées R-01 à R-04 du .memlog)"
lens: "Deux unités conformes à la lettre de chaque AD, qui se construisent pourtant de façon incompatible ; faisabilité technique des nouvelles règles"
date: 2026-09-23
---

# Revue adverse — mise à jour R-01 à R-04

## Verdict

La mise à jour ferme bien les vocabulaires (catalogue d'AD-2, `SegmentKind` des méta-outils, liste fermée des sorties hors brique). En revanche, trois des nouvelles règles normatives **ne tiennent pas techniquement telles qu'écrites** : la garde réseau est aveugle au trafic MCP sous Windows, le cumul de `detokenize` de llama-cpp-python perd des octets sur 360 tokens de Qwen3.5, et le contrôle octet pour octet échoue sur l'appel d'outil le plus courant (sans texte avant). La règle « ajout seul pendant un tour » n'a pas de source de vérité : AD-17 et AD-23 poussent chacune une lecture différente de l'état en cours de tour.

Échelle : **Critique** = incompatibilité certaine à l'intégration, ou règle qui échoue en démonstration ; **Majeur** = incompatibilité probable, ou défaut visible ; **Mineur** = ambiguïté qu'une story tranchera, au risque de mal la trancher.

---

## A. Vérifications techniques (faits mesurés)

Tous les essais ont été faits le 2026-09-23 sur ce poste, avec CPython 3.13.13 Windows x64 (celui qu'exige AD-21).

### A1 — L'audit hook `socket.connect` voit-il les connexions asyncio/anyio ? **Non, pas sous Windows.**

Essai : `sys.addaudithook` qui note `socket.connect` et `socket.getaddrinfo`, puis une connexion vers un serveur local par trois voies.

| Voie | Événements vus | `socket.connect` vers la cible ? |
| --- | --- | --- |
| `socket.create_connection("localhost", p)` (voie de `httpx.Client`) | `getaddrinfo('localhost')`, `connect(('::1', p))`, `connect(('127.0.0.1', p))` | oui |
| `asyncio.open_connection` sous `ProactorEventLoop` | `bind`, et un `connect` vers la paire de sockets interne de la boucle | **non** |
| `asyncio.open_connection` sous `SelectorEventLoop` | `connect` vers la cible | oui |
| `asyncio.open_connection("localhost", p)` sous Proactor | `getaddrinfo('localhost', p)` seul | **non** |

Sous Proactor, asyncio se connecte par `_overlapped.ConnectEx`, qui n'émet pas l'événement d'audit `socket.connect`. Or :
- `uvicorn/loops/asyncio.py` (branche master) renvoie `asyncio.ProactorEventLoop` sous Windows dès qu'il n'y a ni `--reload` ni `--workers` : c'est le cas de `uv run wavestack` ;
- le transport stdio du serveur MCP local (AD-21) exige Proactor sous Windows (Selector ne gère pas les sous-processus) ;
- anyio (`_backends/_asyncio.py`) se connecte par `loop.create_connection`, donc par `ConnectEx` sous Proactor.

**Conséquence :** la garde ne voit jamais le trafic de `httpx2.AsyncClient`, c'est-à-dire les appels MCP publics (data.gouv.fr, Microsoft Learn), la principale sortie réseau pendant un tour. Seul `socket.getaddrinfo` est vu, et seulement pour un nom d'hôte (pas pour une adresse IP littérale).

Deux autres limites, valables sur toutes les voies :
- `socket.connect` reçoit une **adresse IP**, alors que la liste autorisée contient des **noms d'hôte**. Résoudre la liste au démarrage échoue avec les CDN, dont les IP tournent. Résoudre dans le hook provoque un appel réentrant à `getaddrinfo`.
- **Derrière un proxy** (le cas du PC professionnel, qu'AD-15 prend en charge), `connect` vise le proxy, jamais la destination. Soit la garde bloque tout, soit l'adresse du proxy est autorisée, et la garde laisse alors tout passer.

### A2 — `detokenize([id], special=True)` cumulé redonne-t-il les octets du prompt ? **Non, pas avec l'API de llama-cpp-python.**

`llama_cpp/_internals.py` (branche main, voie de `Llama.detokenize` → `LlamaTokenizer.detokenize` → `LlamaModel.detokenize`) :

```python
size = 32
buffer = (ctypes.c_char * size)()
for token in tokens:
    n = llama_cpp.llama_token_to_piece(self.vocab, llama_cpp.llama_token(token), buffer, size, 0, special)
    assert n <= size
    output += bytes(buffer[:n])
```

`llama_token_to_piece` renvoie **l'opposé de la taille nécessaire** quand le tampon est trop petit. L'assertion `n <= size` passe avec un `n` négatif, et `buffer[:n]` renvoie alors une tranche vide ou tronquée, **sans erreur**.

Mesure sur le vocabulaire de `Qwen/Qwen3.5-0.8B` (`vocab.json`, 248 044 entrées, décodage byte-level GPT-2) : **360 tokens dépassent 32 octets**, et le plus long en fait 128. On y trouve des suites d'espaces (indentation de JSON ou de code, donc des résultats d'outils et des pages web), des `//------…`, des `/*****…`, et 152 tokens non ASCII.

Le cumul des décalages dérive donc en silence dès le premier de ces tokens. Tous les tokens suivants sont attribués au mauvais segment. La somme reste égale au total, donc le contrôle d'AD-4 (« la somme est égale au total par construction ») ne détecte rien, et le contrôle 4 porte sur le texte, pas sur les décalages.

Le principe (cumul d'octets pour un BPE byte-level) est correct : une pièce peut être un fragment UTF-8, et seul le cumul en octets est juste. C'est l'outil prescrit qui est faux. Par ailleurs, le port `Engine` d'AD-5 n'expose aucune détokenisation, et le `/detokenize` de llama-server renvoie une chaîne, avec perte sur les fragments UTF-8. Seul `/tokenize` avec `with_pieces: true` renvoie des octets (« a list of bytes otherwise », README du serveur).

### A3 — Les sentinelles survivent-elles à `tojson(ensure_ascii=False)` et aux filtres Qwen ? **Oui pour `tojson`, non pour les tests de vacuité.**

- `json.dumps({"d": "x"}, ensure_ascii=False)` laisse U+E000 et U+E001 intacts : **OK**. Le gabarit de Qwen3.5 rend les outils par `tool | tojson`, et les sentinelles y passent.
- `str.strip()` (donc `|trim`) ne retire pas les caractères de la zone privée : `" x ".strip()` reste inchangé. Sur un texte déjà normalisé (étape 2), `trim` est bien neutre : **OK**.
- En revanche, un texte **vide** encadré de sentinelles devient **non vide**. Le gabarit de Qwen3.5 (`chat_template.jinja` de `Qwen/Qwen3.5-0.8B`) teste la vacuité à plusieurs endroits :
  - ligne 111 : `{%- if content|trim %}` choisit entre `'\n\n<tool_call>\n'` et `'<tool_call>\n'` ;
  - ligne 56 : `{%- if content %}` pour le prompt système quand des outils sont présents.

  **Essai** (rendu Jinja configuré comme AD-4 : système, utilisateur, assistant avec `content = ""`, raisonnement et un appel d'outil, puis réponse d'outil) : le rendu d'attribution, une fois les sentinelles retirées, **diffère** du prompt envoyé de deux lignes vides. Si l'on n'encadre pas les textes vides, les deux rendus sont **égaux**.

  Un assistant qui appelle un outil sans texte avant, c'est-à-dire le cas nominal, fait donc échouer le contrôle 4 à **chaque appel**, et l'interface affiche « attribution approximative » en permanence.
- Le gabarit fait aussi `startswith('<tool_response>')`, `split('</think>')` et `'</think>' in content`. Avec des textes normalisés, ces tests ne changent pas de résultat, sauf quand un segment est vide ou commence par ces balises. Le test de non-régression doit couvrir ces cas.

### A4 — La règle d'ajout seul tient-elle avec le lazy loading décrit ? **Seulement si l'on fixe qui lit quel état.** Voir T2.

Deux constats sur le gabarit de Qwen3.5 :
- **Appels d'outils.** L'appel d'outil de l'assistant est **re-sérialisé** depuis `{name, arguments}` (lignes 105 à 128 : `<parameter=…>\n` + `args_value|string` + `\n</parameter>`), et le contenu passe par `|trim`. La propriété « le texte de l'appel n+1 commence par le texte exact de l'appel n, suivi de sa sortie » n'est donc vraie que si la sortie brute du modèle est déjà canonique. Un paramètre `\n 3 \n` que le parseur convertit en `3` casse le préfixe.
- **Raisonnement.** Il n'est rendu que pour les messages postérieurs au dernier message utilisateur (`loop.index0 > ns.last_query_index`). C'est cohérent pendant un tour, et c'est ce qui l'efface aux tours suivants : AD-4 doit le dire pour que la jauge ne l'attende pas dans `history`.

Rien dans le spine ne vérifie cette propriété. llama-cpp-python réutilise le cache sur le plus long préfixe commun, donc une rupture ne produit pas de faux résultat. Elle produit une relecture silencieuse, et une affirmation pédagogique fausse.

---

## B. Trous principaux (paires d'unités divergentes)

### T1 — Garde réseau : aveugle au MCP public, fondée sur des IP, contournée par le proxy [Critique] — AD-15, AD-21

- **Story « garde réseau » (cli).** Elle installe `sys.addaudithook` sur `socket.connect`, comme AD-15 le dit à la lettre. Pour comparer des IP à une liste de noms, elle résout la liste au démarrage. Le test pytest passe, parce que pytest tourne sans boucle Proactor et que le test utilise `socket.create_connection`.
- **Story « client MCP public » (mcp, net).** Elle utilise `httpx2.AsyncClient` sur la boucle d'uvicorn (Proactor). Aucune de ses connexions ne passe par la garde (A1). La démonstration « tout est bloqué hors liste » est fausse pour exactement le trafic qu'elle doit illustrer.
- **Story « téléchargement » (models/download.py).** `huggingface.co/…/resolve/main/Qwen3.5-2B-Q4_K_M.gguf` répond `302` vers `us.aws.cdn.hf.co/xet-bridge-us/…` (mesuré, `HF_HUB_DISABLE_XET` n'y change rien : le fichier est stocké en Xet). Le README d'AD-21 ne liste que `huggingface.co`. `net` refuse la redirection (hôte hors liste), et la garde refuse l'IP du CDN, qui ne figure pas dans la résolution faite au démarrage.
- **Poste derrière un proxy.** Les trois stories divergent : l'une autorise l'IP du proxy, une autre la refuse, et la dernière laisse `net` décider par destination.
- **Correction.**
  - Garde sur `socket.getaddrinfo` (nom d'hôte, vu sur toutes les voies, Proactor compris), plus `socket.connect` pour les seules IP littérales. La liste autorisée accepte des suffixes (`*.hf.co`).
  - L'hôte du proxy configuré est autorisé d'office. Le contrôle par destination reste dans `net` (hook de requête et redirections).
  - Test pytest obligatoire sous `ProactorEventLoop` avec le vrai client MCP. Mettre à jour la liste de domaines d'AD-21 (`*.hf.co`).
  - Préciser qui émet le `harness_error` : l'appelant `net` ou `mcp`, jamais le hook. Préciser aussi que les processus enfants (sonde, serveur MCP local) installent la même garde à leur démarrage.

### T2 — « Ajout seul » sans source de vérité : état courant (AD-17, AD-23) contre état figé (AD-4) [Critique] — AD-4, AD-17, AD-23, AD-25

- **Story « assemblage du contexte » (context).** AD-17 dit que « la mémoire globale est toujours dans son état courant », et AD-23 que les effets sont appliqués aussitôt. Elle ré-assemble donc à chaque appel à partir de l'état de la session. Après `remember` ou `load_tool_doc` à l'appel 2, le message système ou la variable `tools` de l'appel 3 change : le préfixe est réécrit, ce que la règle d'ajout seul interdit.
- **Story « exécuteur et lazy loading » (tools, mcp).** Pour respecter l'ajout seul, elle lit l'instantané de début de tour (AD-17 : « documentations MCP chargées »). L'outil dont la documentation vient d'être chargée n'y figure pas, et son appel produit « erreur réinjectée » (AD-25). Le modèle ne peut donc **jamais** appeler dans le même tour l'outil qu'il vient de documenter, et le « déclic MCP » d'UJ-1 demande deux tours.
- **Aggravants.**
  - **Doublons.** La réponse de `load_skill` ou de `load_tool_doc` du tour t devient `history` au tour t+1 (AD-4 : « tout ce qui vient d'un tour antérieur »), et rejoint en même temps son emplacement stable. Elle est comptée deux fois, sur une fenêtre de 4 096 tokens où data.gouv.fr est déjà au bord du dépassement.
  - **Table d'emplacements.** Elle ne place `tool_catalog` que dans la variable `tools`, alors qu'AD-25 le met aussi en réponse d'outil. Une table indexée par type range la documentation chargée au mauvais endroit.
- **Correction.**
  - `TurnState`, figé par `build_turn_state`, est la **seule** source des emplacements stables pour tous les appels du tour.
  - Un ensemble `loaded_in_turn` (skills, documentations, écritures mémoire), alimenté par les effets, est lu par l'exécuteur pour décider si un outil est appelable, et par l'assembleur seulement pour les réponses d'outil.
  - Au tour suivant, la réponse d'outil d'un méta-outil de chargement est rendue par un résumé court (`history`), pas en entier.
  - La table d'emplacements est indexée par (type, phase : stable ou dans le tour).

### T3 — Sentinelles : textes vides, segments imbriqués [Critique] — AD-4 (étapes 3 et 5), AD-25

- **Vide.** Mesuré en A3 : encadrer un `content` vide fait échouer le contrôle 4 sur tout appel d'outil sans texte avant. Une story « rendu » qui encadre tous les segments (lecture littérale de l'étape 3) déclenche « attribution approximative » à chaque appel d'outil. Une story qui saute les vides obtient l'égalité. Leurs jauges diffèrent : dans le premier cas, tout passe en `template`.
- **Imbrication.** L'étape 3 dit qu'un outil de la variable `tools` forme **un** segment, « de la première à la dernière chaîne ». AD-25 met dans la description de `load_tool_doc` **un segment `tool_catalog` par outil MCP**. Les segments sont donc imbriqués, et l'étape 5 (découpage linéaire) ne dit rien de ce cas. Une implémentation produit un seul segment `load_tool_doc`, et perd la ventilation par serveur. Une autre produit N+1 segments qui se chevauchent : les tokens sont comptés deux fois, ou le chevauchement est tranché arbitrairement.
- **Correction.**
  - Étape 3 : « un texte vide n'est pas encadré et ne produit pas de segment ».
  - Étape 5 : « les segments ne s'imbriquent jamais. Un segment englobant est coupé en morceaux disjoints, de même type, brique et composant, avec un `id` propre à chacun ».
  - Le test de non-régression Qwen3.5 inclut un assistant à contenu vide avec appel d'outil, et la description de `load_tool_doc` avec deux serveurs.

### T4 — Décalages en octets : `detokenize` de llama-cpp-python tronque, et le port n'expose rien [Majeur] — AD-4 (étape 6), AD-5

- **Story « attribution » (context/render.py).** Elle appelle `Llama.detokenize([id], special=True)` comme prescrit. Les 360 tokens de plus de 32 octets renvoient une tranche vide (A2). Les décalages dérivent en silence après la première indentation de JSON ou le premier `-----` d'une page web.
- **Story « adaptateur llama_server » (models).** Le port `Engine` d'AD-5 n'a pas de méthode de détokenisation. Elle en ajoute une sur `/detokenize`, qui renvoie une chaîne avec perte sur les fragments UTF-8. `context` importe llama_cpp directement pour le mode en processus, ce qui viole la règle « seul `models` importe les bibliothèques d'inférence ». On obtient deux voies, et deux attributions différentes pour un même prompt.
- **Correction.**
  - Ajouter au port `Engine.token_pieces(ids) -> list[bytes]`.
    - `llama_cpp` : appel de bas niveau `llama_token_to_piece`, avec un tampon réagrandi quand `n < 0`.
    - `llama_server` : `/tokenize` avec `with_pieces: true`.
    - `ollama_raw` : GGUF en `vocab_only`, même code que `llama_cpp`.
  - Étape 6 : vérifier `b"".join(pieces) == prompt.encode("utf-8")`, sinon `harness_error`.
  - Test unitaire sur un token de 128 espaces.

### T5 — Bornes et sorties coupées du sous-agent : fin du tour principal ou résultat partiel ? [Majeur] — AD-2, AD-9, AD-10, AD-11

- **Story « boucle de tour » (session).** À la lettre d'AD-10, `limit_reached{limit: sub_calls}` est suivi de `turn_ended{status: limit}`. De même, `context_overflow` ou `output_truncated` dans `context_id = sub1` sont suivis de `turn_ended{overflow|limit}` (AD-9, qu'AD-11 applique au sous-agent). Le tour principal meurt avec la délégation.
- **Story « sous-agent » (bricks).** Elle respecte « ce n'est pas un tour » (AD-11) et renvoie un `subagent_result` du type « limite du sous-agent atteinte ». Le tour principal continue, et c'est ce qui se démontre bien. Le front reçoit un `limit_reached` sans `turn_ended`, alors que la projection attend la paire.
- **Correction.** Dans un contexte `sub{n}`, un dépassement, une sortie coupée ou la borne `sub_calls` émettent leur événement avec le `context_id` du sous-agent, puis `tool_ended{status: limit|overflow}` de `delegate`. Le résultat réinjecté est une erreur en français. `turn_ended` n'est jamais émis depuis un sous-contexte.

---

## C. Trous secondaires

### S1 — Test d'ajustement des scénarios MCP qui dépend du réseau [Majeur] — AD-9, AD-15

Le dépassement volontaire (data.gouv.fr en documentation complète) et le cas Microsoft Learn (~1 250 tokens) dépendent de la réponse **en direct** à `tools/list`. Or le test marqué `model` tourne sous la garde réservée à la boucle locale. Une story « test » code en dur une liste d'outils, pendant qu'une story « MCP » utilise la liste en direct : le test et le `context_preview` divergent dès que data.gouv.fr ajoute un outil.

**Correction :**
- instantané versionné `content/mcp_snapshots/{server_id}.json`, lu par le test ;
- `harness_error` d'information si le serveur en direct diffère de l'instantané de plus de N tokens.

### S2 — Téléchargement à l'activation de RAG, ou seulement sur intention explicite ? [Majeur] — AD-21, AD-15, AD-3, AD-20

AD-21 dit que « la même voie sert […] à l'activation de la brique RAG ». AD-15 dit « seulement sur l'intention explicite `download_model` ». Or l'activation d'une brique est une intention de classe (a), prise en compte au tour suivant : une story télécharge donc dès la bascule, et une autre affiche un bouton.

Trois autres points restent ouverts :
- `download_model` ne figure dans aucune classe d'AD-3, et aucun état du verrou (`idle`, `turn`…) ne couvre un téléchargement de 600 Mo. Un tour peut-il partir pendant ce temps ?
- En diagnostic bloquant, il n'y a pas de session : qui traite `download_model` et `select_model` ?
- `hf_hub_download` écrit par défaut dans le cache HF, pas dans `models/` d'AD-20, et sans passer par un effet.

**Correction :**
- `download_model` en classe (b), avec un état `download` du verrou ;
- l'activation de RAG sans modèle rend la brique indisponible (« modèle absent, télécharger ») ;
- `local_dir = config.models_dir` ;
- le diagnostic sans session passe par une `Session` minimale en état `diagnostic`.

### S3 — Sortie de l'assistant pendant le tour : aucun `SegmentKind` [Majeur] — AD-4

Plusieurs textes n'ont pas de type, alors qu'AD-4 leur réserve un emplacement (« les messages de l'assistant ») :
- le raisonnement, le texte et l'appel d'outil de l'appel n, rendus dans l'appel n+1 ;
- la partie « appel » d'une action forcée.

Une story les classe en `history` (brique `short_memory`, même si la brique est éteinte). Une autre les laisse aux morceaux hors sentinelles, donc à `template`, et « Message et gabarit » gonfle de jusqu'à 1 536 tokens de raisonnement.

**Correction :** amendement du spine, avec un type `assistant_turn`, ou la règle « rendu comme `history` quelle que soit l'activation de `short_memory` ».

### S4 — Qui émet `output_truncated`, et d'où vient `origin` ? [Mineur] — AD-2, AD-9, AD-15

- **`output_truncated`.** Le canal en cours est connu du séparateur incrémental (AD-6). L'adaptateur (`models`) et la session peuvent donc l'émettre tous les deux : doublon, ou aucun. **Correction :** la session émet, à partir de `model_call_ended.stop_reason`.
- **`origin`.** Diagnostic, téléchargement et activation d'une brique ont tous `turn_id = null` : on ne peut donc pas déduire l'origine de la portée. **Correction :** ajouter `origin` à la `TraceScope`, posé par l'appelant (`net` le lit), sans toucher l'enveloppe.

### S5 — `tokenize(special=True)` sur du contenu non fiable [Mineur] — AD-5, AD-4

Une page web ou un résultat d'outil qui contient `<|im_end|>\n<|im_start|>system` est tokenisé en **vrais tokens de contrôle**. L'aller-retour d'octets reste exact, et le contrôle 4 ne voit rien, mais c'est une injection de structure.

**Correction :** tokeniser par segment, avec `special=True` seulement sur les morceaux `template`. À défaut, neutraliser les balises spéciales dans les textes de segment à l'étape 2 (normalisation), et le tracer.

### S6 — `remember` compressible, `load_tool_doc` non [Mineur] — AD-22, AD-25

`remember` → `tool_result` entre dans le champ de la compression, mais `load_tool_doc` → `tool_catalog` n'y entre pas. C'est cohérent si c'est voulu, mais le spine devrait le dire pour que la story de compression ne s'étonne pas.

---

## D. Récapitulatif

| # | Sévérité | AD | Correction en une ligne |
| --- | --- | --- | --- |
| T1 | Critique | AD-15, AD-21 | Garde sur `socket.getaddrinfo` (noms, suffixes) + `connect` pour les IP littérales, proxy autorisé d'office, test sous Proactor, `*.hf.co` |
| T2 | Critique | AD-4, AD-17, AD-23, AD-25 | `TurnState` figé = source des emplacements stables ; `loaded_in_turn` lu par l'exécuteur ; pas de doublon au tour suivant |
| T3 | Critique | AD-4, AD-25 | Texte vide jamais encadré ; segments jamais imbriqués (découpe en morceaux disjoints) ; test avec contenu vide |
| T4 | Majeur | AD-4, AD-5 | `Engine.token_pieces(ids) -> list[bytes]` avec tampon réagrandi ; vérifier `join == prompt.encode()` |
| T5 | Majeur | AD-9, AD-10, AD-11 | Borne ou dépassement du sous-agent → `tool_ended{limit|overflow}` de `delegate`, jamais `turn_ended` |
| S1 | Majeur | AD-9 | Instantané `tools/list` versionné pour le test |
| S2 | Majeur | AD-21, AD-3 | `download_model` en classe (b), état `download`, `local_dir = models/` |
| S3 | Majeur | AD-4 | `SegmentKind` pour la sortie de l'assistant pendant le tour |
| S4 | Mineur | AD-2, AD-15 | La session émet `output_truncated` ; `origin` dans la `TraceScope` |
| S5 | Mineur | AD-5 | `special=True` réservé aux morceaux `template` |
| S6 | Mineur | AD-22 | Dire si la réponse de `remember` est compressible |

**Sources vérifiées :** `llama_cpp/_internals.py` (abetlen/llama-cpp-python, main) ; `uvicorn/loops/asyncio.py` (encode/uvicorn, master) ; `anyio/_backends/_asyncio.py` (agronholm/anyio, master) ; `tools/server/README.md` (ggml-org/llama.cpp, master) ; `chat_template.jinja` et `vocab.json` de `Qwen/Qwen3.5-0.8B` (Hugging Face) ; redirection `resolve` de `unsloth/Qwen3.5-2B-GGUF` (en-têtes HTTP) ; essais locaux sous CPython 3.13.13 Windows.
