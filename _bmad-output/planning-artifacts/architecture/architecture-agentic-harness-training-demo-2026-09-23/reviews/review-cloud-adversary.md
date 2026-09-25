---
title: Revue adverse des amendements « modèles cloud » (FR-43) du spine WaveStack
target: ../ARCHITECTURE-SPINE.md
scope: "Amendements du 2026-09-24 : AD-2, AD-3, AD-4 (mode chat), AD-5 (openai_chat), AD-6, AD-8, AD-9, AD-12, AD-15, AD-16, AD-20, AD-21 ; interactions avec AD-1, AD-10, AD-11, AD-14, AD-17, AD-23, AD-25 et la table des identifiants"
lens: "Deux unités conformes à la lettre de chaque AD, qui se construisent pourtant de façon incompatible (forme de données, propriétaire, chemin de mutation, fuite de secret)"
date: 2026-09-24
sources:
  - ../ARCHITECTURE-SPINE.md (git diff du 2026-09-24)
  - ../../../sprint-change-proposal-2026-09-24.md
  - ../../../ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
  - src/wavestack/config.py, net/factory.py, tools/network.py, session/diagnostic.py, trace/catalog.py (code livré, pour vérifier les points d'ancrage)
---

# Revue adverse : amendements « modèles cloud »

## Verdict

Les amendements ajoutent bien le cloud à côté du chemin local, mais ils le greffent sur des AD écrites pour du texte rendu. On trouve trois contradictions internes (le titre et le « Prevents » d'AD-5 interdisent ce que sa règle autorise ; `test_cloud_model` est de classe b, donc refusé dans le seul état où il sert ; les sorties hors brique sont tracées avec `turn_id = null`, alors que l'appel au modèle a lieu dans un tour). Surtout, **trois chemins laissent partir la clé vers un autre hôte ou dans la trace sans enfreindre la lettre** : une clé indexée par un `model_id` que deux fournisseurs partagent, l'en-tête `api-key` que httpx conserve lors d'une redirection, et la charge d'`effect_applied`. Le format chat exige aussi un identifiant d'appel d'outil que la forme de l'historique (AD-4) ne contient pas.

Échelle (reprise des revues précédentes) : **Critique** = incompatibilité certaine à l'intégration, fuite de secret, ou règle qui échoue en démonstration. **Majeur** = incompatibilité probable, ou défaut visible. **Mineur** = ambiguïté qu'une story tranchera, au risque de mal la trancher.

---

## P1 — Le port `Engine` : texte rendu ou corps chat ? Deux sources pour le « corps exact » — **Critique**

**Unité A : `models/engine.py` + adaptateur `openai_chat` (story 11, partie moteur).**
Elle garde la signature d'AD-5, `complete(prompt_ids | prompt_text, stop, max_tokens, cancel)`, et ajoute à côté une méthode `complete_chat(messages, tools, …)`. L'adaptateur construit lui-même le corps final : `model`, `stream: true`, `stream_options`, `max_tokens`, `stop`, voire `reasoning_effort` ou `parallel_tool_calls`. Il respecte la règle amendée (« reçoit messages et outils structurés »).

**Unité B : `context` en mode chat + `session` (story 11, partie contexte).**
Elle suit AD-4 à la lettre : « `context` construit le corps JSON (`messages`, `tools`), et `context_rendered` le porte tel qu'envoyé ». Pour respecter la signature d'AD-5, elle passe `prompt_text = json.dumps(body)`.

**Où ça casse.**
- AD-5 se contredit : son titre (« reçoit du texte déjà rendu, rien de plus ») et son « Prevents » (« un adaptateur qui envoie des messages de chat ») n'ont pas été amendés. Chaque unité peut invoquer une moitié de l'AD.
- `context_rendered` montre `{messages, tools}`. `outbound_request` (émis par `net`) montre le corps réellement envoyé, auquel l'adaptateur a ajouté `model`, `stream`, `max_tokens`… Le spine promet deux fois le « JSON exact », et les deux ne sont pas égaux. AD-15 impose de signaler tout écart entre aperçu et envoi, mais seulement pour H5 : ici l'écart passe en silence, ou bien une story l'ajoute et l'interface signale un écart à **chaque** appel.
- `stop` : les `stop_sequences` du registre (AD-6) sont des tokens de gabarit (`<|im_end|>`), sans objet côté fournisseur. De plus, certaines API limitent le nombre de séquences d'arrêt. Aucune règle ne dit si le port les transmet en mode chat.

**AD à resserrer :** AD-5 (titre, Prevents, signature), AD-4 (mode chat).

**Règle proposée.**
> Le port prend un `RenderedRequest`, union fermée `TextPrompt{ids | text}` | `ChatBody{json}`. En mode chat, `context` construit le **corps complet** : `model`, `messages`, `tools`, `stream`, `stream_options`, `max_tokens`, sans `stop`. L'adaptateur n'y ajoute rien, sauf l'en-tête d'authentification. `context_rendered.body` est égal, octet pour octet, au `body` d'`outbound_request` du même `call_id` ; un test le vérifie avec le moteur factice. Réécrire le titre et le Prevents d'AD-5 : « Le port moteur reçoit une requête entièrement construite par le harnais, rien de plus ».

---

## P2 — Identifiants d'appels d'outils : absents de l'historique, fabriqués de deux façons — **Critique**

**Unité A : `context/chat_body.py` (assembleur du mode chat).**
L'historique d'AD-4 est `tool_calls: [{name, arguments}]`, sans identifiant. Or le format chat exige `tool_calls[].id`, `type: "function"`, `function.arguments` **en chaîne JSON**, et un message `role: tool` avec son `tool_call_id`. L'assembleur fabrique donc des identifiants à chaque rendu, d'après la table des identifiants : `t3.main.c1.0`, soit `{call_id}.{n}`.

**Unité B : `session` (boucle de tour) et exécuteur (AD-14), actions forcées (AD-25).**
La session reçoit les `tool_calls` de l'API avec leur `id` fournisseur (`call_abc…`). Elle les met dans `model_call_ended.tool_calls` et les réinjecte tels quels. Pour une action forcée, elle fabrique son propre appel (AD-25 : « rendue comme un appel d'outil de l'assistant, suivi de sa réponse ») avec un autre schéma d'identifiant, ou sans identifiant.

**Où ça casse.**
- Au second appel du tour, le message `assistant` porte l'identifiant du fournisseur, et la réponse `tool` un identifiant fabriqué par l'assembleur, ou l'inverse. L'API refuse l'appel (400 : `tool_call_id` inconnu).
- Mistral n'accepte que des identifiants de 9 caractères alphanumériques (erreur connue, signalée par les intégrations tierces ; à confirmer par « Tester »). Or `t3.main.c1.0` contient des points : **toute action forcée échoue chez Mistral**, l'un des deux préréglages.
- Chaque `tool_call` doit recevoir exactement une réponse `tool`, y compris quand il est bloqué (H1), refusé (H5), mal formé (AD-10) ou coupé par une borne. Aucune AD ne l'exige : en local, le gabarit rend du texte et ne vérifie rien.
- Les arguments : l'historique stocke un objet, et l'API attend la chaîne émise. Re-sérialiser change l'ordre des clés et les blancs. Un argument JSON invalide (voie « mal formé », D5) ne peut pas être stocké comme objet.

**AD à resserrer :** AD-4 (forme de l'historique), AD-25 (action forcée), table des identifiants.

**Règle proposée.**
> Chaque appel d'outil porte un `tool_call_id` attribué **par la session**, au moment où l'appel naît (sortie du modèle ou action forcée), et stocké dans l'historique : `tool_calls: [{id, name, arguments, arguments_raw}]`. Le format est `[A-Za-z0-9]{9}`, compatible avec tous les fournisseurs, et dérivé de façon déterministe de `step_id` (hash tronqué). L'identifiant renvoyé par le fournisseur est remplacé, et l'original gardé dans la trace. Chaque identifiant reçoit exactement une réponse `tool`, quelle que soit l'issue : ok, bloqué, refusé, mal formé ou borne. `arguments_raw` est la chaîne émise, renvoyée telle quelle en mode chat. Ajouter `tool_call_id` à la table des identifiants.

---

## P3 — La clé part vers un autre hôte, sans enfreindre la lettre — **Critique**

### P3a — Clé indexée par un `model_id` non unique, ou par un id dont l'hôte change

**Unité A : `config` (schéma `[[cloud.models]]`).** Elle prend pour `id` le nom du modèle dans l'API (`openai/gpt-oss-120b`), qui est aussi ce qu'on envoie dans le champ `model`.

**Unité B : `api_keys.json` (AD-20 : `{model_id: key}`) et adaptateur (AD-5 : « la clé est lue dans `api_keys.json` »).**

**Où ça casse.**
- Deux fournisseurs servent le même nom de modèle : c'est le cas de `openai/gpt-oss-120b` chez Groq et chez OpenRouter (listé en exemple). Les deux entrées partagent alors une clé. La clé Groq part vers `openrouter.ai`. AD-15 est respectée à la lettre (« n'est envoyée qu'à l'hôte déclaré **de ce modèle** »), puisque l'hôte déclaré de ce modèle est bien OpenRouter.
- Si l'on édite `base_url` dans `settings.json` pour un `id` existant (un point d'accès interne remplacé, une faute de frappe), la clé déjà saisie part vers le nouvel hôte, qui est automatiquement ajouté à la liste autorisée.

### P3b — Redirection : httpx ne retire que `Authorization`

**Unité A : `openai_chat`.** Pour Azure, elle place la clé dans l'en-tête déclaré `api-key` (AD-5).

**Unité B : `net`.** C'est le code livré (`tools/network.py` : `follow_redirects=True`, le crochet de `factory.py` revérifie la liste autorisée à chaque saut). httpx retire `Authorization` sur une redirection vers une autre origine, mais **garde tout autre en-tête**, dont `api-key`.

**Où ça casse.** Un 307 vers un autre hôte de la liste autorisée (n'importe lequel : `huggingface.co`, un serveur MCP public, un autre fournisseur) emporte la clé. AD-15 dit que la clé « n'accompagne jamais une redirection vers un autre hôte », sans dire qui le garantit. `net` ne sait pas quel en-tête est secret, et l'adaptateur ne voit pas les sauts.

**AD à resserrer :** AD-15, AD-20, schéma `[[cloud.models]]` (voir P7).

**Règle proposée.**
> - L'`id` d'un modèle cloud est un identifiant WaveStack unique (`{provider}.{slug}`), distinct du champ `model` envoyé à l'API. Son unicité est vérifiée après la fusion de `wavestack.toml` et de `settings.json`.
> - `api_keys.json` devient `{id: {host, key}}`. L'hôte est enregistré à la saisie. Si l'hôte déclaré diffère de l'hôte enregistré, `key_set = false` et la clé n'est pas envoyée : il faut la ressaisir.
> - Le client d'un modèle cloud **ne suit aucune redirection** : `follow_redirects=False`, et un 3xx devient `harness_error`. C'est `net` qui applique la règle, sur `origin = model`.
> - La clé ne passe que par l'en-tête déclaré. Un `base_url` qui contient des paramètres de requête est refusé au chargement de la configuration.

---

## P4 — Fuite de la clé dans la trace par la lettre des règles — **Majeur**

AD-20 dit seulement que `api_keys.json` « n'est jamais lu par `trace` ni renvoyé par l'API locale ». Trois chemins contournent cette phrase sans la violer.

**Paire 1 : `session/effects.py` × catalogue `trace`.**
- AD-20 impose que la session écrive `api_keys.json` « par les effets (AD-23) ». Une story ajoute donc `ApiKeyWrite{model_id, key}` à l'union.
- AD-23 : la session « émet `effect_applied` », sans en fixer la charge. Le motif naturel est `payload = effect.model_dump()`. **La clé entre dans le journal**, puis dans le flux SSE et dans `/api/state`.
- `trace` n'a jamais lu le fichier : la lettre d'AD-20 est respectée.
- De plus, aucun nœud fixe ne correspond à `api_keys.json`. Le `component` exigé par AD-23 sera inventé (`file.settings`, `file.api_keys`), ou omis.

**Paire 2 : adaptateur `openai_chat` × AD-16.**
- AD-16 : le refus d'un fournisseur devient `harness_error` « avec cause ». La cause la plus simple est le corps de la réponse d'erreur.
- Or certains fournisseurs recopient la clé, masquée en partie, dans leur message 401 (OpenAI : « Incorrect API key provided: sk-…abcd »). La même chose vaut pour le `diagnostic_check` du bouton « Tester » (« Échec avec la raison du fournisseur »).

**Paire 3 : `web` (intention `set_api_key`) × journalisation.**
- La réponse de l'intention peut renvoyer le modèle pydantic reçu, ce qui fait écho de la clé.
- `logging` en DEBUG sur httpx ou httpcore peut écrire les en-têtes.

**AD à resserrer :** AD-20, AD-23, AD-16.

**Règle proposée.**
> - La clé est un `SecretStr` de bout en bout : intention, effet, adaptateur.
> - L'effet `ApiKeySet{id, host}` ne porte pas la clé : la session l'écrit hors de l'union sérialisable, ou le champ est exclu de toute sérialisation. `effect_applied` porte `{kind, id, key_set}`. Le nœud fixe `file.api_keys` est réservé dans AD-12, et dessiné sans contenu.
> - Toute chaîne issue d'un fournisseur (erreur, raison de test) passe par un filtre qui remplace toute occurrence de la clé, et de ses 4 premiers ou derniers caractères, par `•••`.
> - Test obligatoire : une clé sentinelle, puis une recherche dans le journal, `/api/*`, les réponses d'intention, `settings.json` et la sortie console.

---

## P5 — Classes d'intentions et verrou : `test_cloud_model` refusé là où il sert ; `set_api_key` sans classe — **Majeur**

**Unité A : `web` et routeur des intentions.** Il implémente la table d'AD-3 de façon générique : une intention de classe (b) est « refusée hors `idle` ». AD-21 classe `test_cloud_model` en (b), comme `download_model`. En état `diagnostic`, le routeur la refuse.

**Unité B : `session/diagnostic.py`.** AD-3 amendée dit que la session minimale en état `diagnostic` « ne traite que `select_model`, `download_model`, `set_api_key` et `test_cloud_model` ». Elle les traite.

**Où ça casse.**
- Les deux lectures sont conformes, et incompatibles : la page de diagnostic bloquant est précisément là où l'état n'est pas `idle`. Le code livré a déjà dû trancher contre le spine : `diagnostic.py` déclare `select_model` « class a », alors que « changer de modèle » est en (b).
- `set_api_key` n'a aucune classe. Une story le met en (a) (« enregistrer », comme le prompt système) : il est alors accepté en plein tour. Si l'adaptateur a lu la clé au chargement, la nouvelle clé ne sert pas avant le prochain lancement, et l'utilisateur tourne en rond sur « Clé refusée, vérifiez-la dans le diagnostic ». Si l'adaptateur lit la clé à chaque appel, elle change entre deux appels d'un même tour.
- Aucun état du verrou ne couvre le test lui-même : un appel réseau de plusieurs secondes. Pendant qu'il tourne, `select_model` ou un second `test_cloud_model` peuvent arriver.

**AD à resserrer :** AD-3, AD-21.

**Règle proposée.**
> - Classe (b) = « refusée hors `idle`, sauf en `diagnostic` pour les quatre intentions du diagnostic ».
> - `set_api_key` est de classe (b). L'adaptateur lit la clé au début de chaque tour, figée dans le `TurnState`, jamais en cours de tour.
> - `test_cloud_model` fait passer la session dans l'état `model_load` (raison « Test de {modèle} en cours »), ou dans un état `testing` ajouté au verrou.
> - Aligner le code de la story 1b (`select_model`) sur la classe retenue.

---

## P6 — Qui garantit l'avertissement, et que devient le choix au lancement suivant ? — **Majeur**

**Unité A : front du diagnostic (EXPERIENCE `cloud-warning`).** Au clic sur « Choisir », il affiche l'avertissement, puis envoie `select_model{…}` sur « Utiliser ce modèle ». La garantie n'existe que dans le navigateur.

**Unité B : `session/diagnostic.py`.** Elle accepte `select_model` pour un identifiant cloud comme pour un chemin, et persiste le choix. C'est le code livré de la story 1b : `save_setting("selected_model", path)`, une chaîne.

**Où ça casse.**
1. **Confirmation contournable.** Tout client local qui passe `Origin` (un script de test, un scénario futur, un `settings.json` édité à la main) active un modèle cloud sans avertissement. D15 exige pourtant l'avertissement « avant tout appel ». Rien dans l'état de la session ne dit que l'avertissement a été confirmé.
2. **Forme persistée.** `selected_model` est aujourd'hui un chemin. Une unité enregistre `"cloud:groq.gpt-oss"`, une autre un objet, une troisième l'`id` nu. La règle de démarrage de la story 1b, `_usable(candidates, saved)`, compare des chemins.
3. **« Jamais chargé d'office » contre « le choix enregistré ».**
   - AD-21 dit à la fois « un modèle cloud n'est jamais chargé d'office » et « un modèle cloud enregistré devenu inutilisable produit un avertissement, puis la règle de démarrage s'applique ». Une unité relit le choix cloud au lancement (règle 1b). Une autre exige un nouveau choix à chaque lancement : le choix enregistré ne sert alors à rien, et l'avertissement réapparaît à chaque lancement, contre EXPERIENCE (« pas à chaque lancement »).
   - « Pas de réseau » comme critère d'inutilisabilité suppose une requête au lancement vers le fournisseur. Cette requête n'est ni « choisie explicitement » ni un test demandé : elle sort de la liste fermée d'AD-15.
4. **« Tester » envoie des données avant l'avertissement.** Dans EXPERIENCE, « Tester » est actif dès qu'une clé existe, alors que l'avertissement n'apparaît qu'à « Choisir ». D15 dit « avant tout appel ». Le contenu du test est fixe, sans donnée de l'utilisateur, mais c'est la clé et l'adresse IP du poste qui partent.

**AD à resserrer :** AD-3, AD-21, AD-20 (format de `settings.json`).

**Règle proposée.**
> - `select_model` prend `{source: file|server|cloud, ref}`. Pour `source = cloud`, le champ `warning_confirmed: Literal[True]` est obligatoire, et la session refuse sans lui. `settings.json` enregistre `selected_model = {source, ref}` et `cloud_warning_confirmed = [id…]`.
> - Au lancement, un modèle cloud enregistré est **utilisable** s'il est déclaré, que `key_set` est vrai et que l'hôte enregistré correspond. Aucune requête n'est faite : un défaut réseau se découvre au premier tour, en `harness_error`.
> - « Jamais chargé d'office » signifie seulement : jamais retenu sans choix explicite enregistré.
> - Le texte de « Tester » dit ce qui part (requête fixe, clé, adresse IP), ou bien « Tester » exige la même confirmation que « Choisir ».

---

## P7 — Schéma de `[[cloud.models]]` et fusion `wavestack.toml` / `settings.json` — **Majeur**

**Unité A : `config.load_config()`.** C'est le code livré : `_deep_merge` fusionne les dictionnaires, mais **remplace les listes en bloc**.

**Unité B : story 11.** D3 prévoit d'ajouter un point d'accès interne dans `settings.json`, sous `cloud.models`, « en plus » des préréglages.

**Où ça casse.**
- Déclarer `cloud.models = [ {wavestone…} ]` dans `settings.json` **efface Groq et Mistral**. Pour garder les deux, une autre unité ajoute les listes : un même `id` présent des deux côtés apparaît alors deux fois (voir P3a pour la conséquence sur la clé).
- Aucune AD ne possède le schéma. Ses champs sont éparpillés : capacités `tools`, `reasoning` et `context` (AD-6), `window` et `max_window` (AD-9), en-tête d'authentification (AD-5), nom du fournisseur (AD-12), hébergement, entraînement, offre d'essai et clause EEE (EXPERIENCE, D15). Une unité lit `context`, une autre `native_context`. Avec `extra = allow`, une clé écrite par erreur dans l'entrée (`api_key = …`) repart par `/api/diagnostic`.
- Les textes de l'infobulle et de l'avertissement sont en français, alors qu'AD-19 veut tout contenu pédagogique dans `content/`. Une unité les met dans `wavestack.toml`, l'autre dans `content/providers/`.
- `window` par modèle contre le réglage de fenêtre de l'interface (AD-9, classe b) : quand le modèle cloud a un `window`, modifier la fenêtre dans l'interface ne change rien, et aucune raison n'est affichée.

**AD à resserrer :** nouvelle clause dans AD-6 (ou AD-20), convention « Configuration ».

**Règle proposée.**
> - Un modèle pydantic `CloudModel` unique, dans `config`, avec `extra = "forbid"` : `id`, `provider`, `model`, `base_url` (https, sans requête), `auth_header` (`authorization_bearer` | `api_key`), `capabilities{tools, reasoning, context}`, `max_window`, `window?`, `reasoning_in_history` (voir P10), `notice_ref`.
> - Fusion **par `id`** : une entrée de `settings.json` remplace l'entrée de même `id` et ajoute les autres. `enabled = false` retire un préréglage.
> - Les textes français sont dans `content/providers/{provider}.yaml`, référencés par `notice_ref`.
> - La fenêtre effective affiche sa source (« plafonnée par le modèle cloud »).

---

## P8 — `outbound_request` d'un appel au modèle : `turn_id = null` et portée sans `origin = model` — **Majeur**

**Unité A : `net` (crochet de `factory.py`).** Elle lit `origin` dans la `TraceScope`. AD-2, § Portée, n'a pas été amendée : « La portée porte aussi `origin` (`brick`, `diagnostic` ou `download`) ». Le code livré type `origin: Literal["brick", "diagnostic", "download"]` et prend `"brick"` par défaut. Un appel au modèle, fait dans la portée du tour, est donc tracé `origin = brick`, ou bien la validation échoue.

**Unité B : `session`.** AD-15 range l'appel au modèle cloud parmi les « sorties hors brique », « chacune tracée avec `turn_id = null` ». La session pose donc une portée sans tour pour l'appel.

**Où ça casse.**
- Avec A, les données sortantes du modèle se mélangent à celles des briques : le décompte FR-22 et le badge de brique sont faux.
- Avec B, l'événement perd `turn_id` et `call_id`. Le front ne peut plus rattacher le corps envoyé à l'appel, alors qu'EXPERIENCE le montre « dans Contexte LLM » de cet appel. La règle de `turn_id = null` a été écrite pour la sonde et le téléchargement, qui n'ont pas de tour.

**AD à resserrer :** AD-2 (Portée), AD-15 (Sorties hors brique).

**Règle proposée.**
> - `TraceScope.origin` ∈ `brick | diagnostic | download | model`.
> - L'appel au modèle garde la portée de l'appel (`turn_id`, `context_id`, `call_id`, `component = core.model` ou `core.model_sub`, `edge = core.harness→core.model`) et porte `origin = model`.
> - `turn_id = null` ne vaut que pour la sonde, le téléchargement et `test_cloud_model`.

---

## P9 — Réconciliation des tokens : quel événement porte la ventilation après `usage` ? — **Majeur**

**Unité A : `session` et `context`.** `context_rendered` est émis **avant** l'appel (AD-9 : la session y calcule `used`, `percent` et la ventilation). Après `usage`, la session réémet un second `context_rendered` pour le même `call_id`, avec la ventilation réconciliée.

**Unité B : magasin de projection du front.**
- Il reçoit `model_call_ended.prompt_tokens` et calcule lui-même `template = prompt_tokens − Σ estimations`. C'est permis à la lettre d'AD-1, qui autorise « les écarts entre deux valeurs reçues ».
- Dans le cas négatif, la réduction proportionnelle est un recalcul, interdit. Le front la fait quand même, ou il affiche un `template` négatif.

**Où ça casse.**
- Un double `context_rendered` casse les projections qui comptent les rendus par appel.
- Un calcul côté front diverge de celui de la session (arrondi de la réduction proportionnelle, somme qui ne tombe plus juste).
- Cas sans `usage` : annulation (le bloc `usage` arrive en fin de flux, jamais reçu), erreur 429, ou fournisseur qui ignore `include_usage`. `model_call_ended.prompt_tokens` n'a alors pas de valeur, et la règle « `usage` fait foi » ne dit pas quoi faire.
- « L'écart du dernier appel » : dernier appel de quel contexte ? L'écart d'un appel `sub{n}` (peu de messages) sert à l'aperçu du contexte principal. Et l'écart est-il additif ou proportionnel ? Le surcoût du gabarit croît avec le nombre de messages et d'outils, donc un écart additif sous-estime.

**AD à resserrer :** AD-2 (catalogue), AD-4 (mode chat), AD-1.

**Règle proposée.**
> - Nouveau `kind` `context_reconciled{call_id, segments: [{id, tokens}], used, percent, usage_source}`, émis par la session juste après `model_call_ended`, seulement en mode chat. Les projections remplacent la ventilation de `context_rendered` par lui. Le front n'additionne ni ne répartit rien.
> - Sans `usage` : `usage_source = estimate`, pas de `context_reconciled`, et « ≈ » est conservé.
> - L'écart d'estimation est un **ratio** (`usage / Σ estimations`), tenu par `context_id`, et remis à zéro au changement de modèle.

---

## P10 — Quota par minute : `max_window` par appel ne protège pas d'un 429 en plein tour — **Majeur**

**Unité A : `context/window`.** AD-9 : fenêtre effective = min(…, `max_window`). Pour Groq gpt-oss-120b (8 000 tokens/min), la story fixe `max_window` = 7 000. Chaque appel tient.

**Unité B : boucle de tour (AD-10).** Jusqu'à 6 appels par tour, plus 4 pour le sous-agent. Chaque appel renvoie tout le contexte.

**Où ça casse.** Deux appels à 5 000 tokens en moins d'une minute font 10 000 tokens par minute : un 429 au second appel. C'est le cas le plus courant, un appel d'outil suivi de la réponse. Le tour se termine en `error` (AD-16, sans nouvel essai). La démonstration « même harnais, modèle plus gros » échoue dès le premier outil. Chaque unité respecte sa règle : un plafond par appel ne peut pas exprimer un débit.

**AD à resserrer :** AD-9, AD-16.

**Règle proposée.**
> - Soit l'entrée déclare `tpm`, et la session tient une fenêtre glissante des tokens envoyés : avant un appel qui dépasserait le quota, elle attend en affichant « Attente du quota du fournisseur (n s) » (un état visible, annulable, pas un nouvel essai) ou refuse avec un événement expliqué.
> - Soit le spine assume le 429 en plein tour comme matériau pédagogique, et le dit : `max_window` ≤ tpm / 2, avec les bornes d'appels réduites pour les modèles cloud.

---

## P11 — Rendu chat de l'historique : raisonnement, actions forcées sans outils, normalisation — **Majeur**

**Paire 1 : raisonnement des tours précédents.**
- AD-4 : « c'est le gabarit qui décide de ce qu'il garde, par exemple le raisonnement des tours précédents ». En mode chat, il n'y a pas de gabarit local.
- Unité A renvoie `reasoning` ou `reasoning_content` dans les messages `assistant`. Certains fournisseurs refusent ce champ en entrée ; d'autres, au contraire, attendent le raisonnement entre deux appels d'outils d'un même tour (famille gpt-oss).
- Unité B le supprime toujours.
- Aucune règle ne tranche. Le résultat varie selon le fournisseur, et la jauge compte des segments `history` qui ne partent pas.

**Paire 2 : action forcée sur un modèle sans `tools` déclaré.**
- AD-6 : sans parseur, le mode `model` est indisponible, mais `forced` reste disponible. En local, le gabarit rend l'appel fabriqué en texte, quoi qu'il arrive.
- En chat, l'unité d'assemblage envoie `assistant.tool_calls` et `role: tool` sans liste `tools`, ce que certaines API refusent. L'action « disponible » échoue alors en 400.

**Paire 3 : normalisation (AD-4, étape 2).**
- Elle neutralise les tokens spéciaux « du vocabulaire ». En mode chat, il n'y a pas de vocabulaire local.
- Une unité saute l'étape, une autre neutralise la liste de Qwen3.5. Un contenu non fiable (page web, résultat MCP) peut alors injecter `<|im_start|>` dans le gabarit du fournisseur, selon sa façon de tokeniser.

**AD à resserrer :** AD-4 (mode chat), AD-6, AD-25.

**Règle proposée.**
> - `reasoning_in_history: none | in_turn | all` est déclaré par modèle cloud (défaut `none`). Les segments non envoyés ne sont pas comptés.
> - Pour un modèle cloud sans `tools`, `forced` est rendu en `injection` (texte dans le message utilisateur), avec sa raison.
> - En mode chat, l'étape 2 neutralise une liste fixe de marqueurs de gabarit courants (`<|…|>`, `[INST]`, `<s>`), déclarée dans `wavestack.toml`.

---

## P12 — `model_call_ended` en mode chat : `raw_output`, temps et débit non comparables — **Majeur**

**Unité A : adaptateur `openai_chat`.**
- `prompt_ms` = délai jusqu'au premier fragment (réseau et file d'attente compris).
- `gen_ms` = du début de l'envoi à la fin.
- `raw_output` = texte des deltas `content`.
- `finish_reason: tool_calls` donne `stop`, et `content_filter` donne `error`.

**Unité B : `session`, qui calcule `output_tps` (AD-2).**
- Elle fait `output_tps = output_tokens / gen_ms`, sur le modèle du chemin local, où `gen_ms` exclut la lecture du prompt.
- Elle attend dans `raw_output` le texte brut du modèle, affiché dans le volet « sortie brute ».

**Où ça casse.**
- Le débit, qui est *la* démonstration (170 à 900 tokens/s contre 10), est mesuré différemment en local et en cloud. Le chiffre cloud est écrasé par la latence réseau, et la comparaison devient trompeuse.
- `raw_output` n'a pas de définition en chat. Les appels d'outils structurés n'y figurent pas, et le volet « sortie brute » montre moins que ce que le modèle a produit.
- Le raisonnement caché par le fournisseur retarde `model_first_token`. Il est compté dans `completion_tokens`, mais n'apparaît dans aucun canal.

**AD à resserrer :** AD-2, AD-5.

**Règle proposée.**
> - `prompt_ms` = de l'envoi au premier delta, tous canaux ; en chat, il est libellé « attente du premier token, réseau compris ».
> - `gen_ms` = du premier au dernier delta ; `output_tps = output_tokens / gen_ms` dans les deux modes.
> - En chat, `raw_output` = la suite des deltas SSE `choices[0].delta`, sérialisée en JSON Lines.
> - Table fermée `finish_reason → stop_reason` dans AD-5.
> - `completion_tokens − tokens vus` est affiché comme « raisonnement non transmis ».

---

## P13 — Sous-agent et rejeu en mode chat — **Mineur**

- **Sous-agent (AD-11).**
  - La préservation par `save_state()` et `load_state()` est sans objet en mode chat. La règle « sinon, il est relu, et la latence s'affiche » s'applique, mais le spine ne dit pas que c'est le cas nominal en chat. Une unité tente `save_state` sur l'adaptateur et lève une erreur.
  - `core.model_sub` passe en `network_service` (AD-12). Ses appels doivent porter `origin = model` et `component = core.model_sub` (P8).
- **Rejeu (AD-17).** Le modèle est « lu dans la configuration courante ». Un rejeu après passage au cloud re-rend en chat un historique produit en local. Il n'a pas de `tool_call_id` (P2), et ses arguments ont été analysés par le parseur XML. Le changement de modèle attend le palier 2 (redémarrage, journal perdu), donc le cas n'existe pas avant CAP-34. Il faut le noter pour que CAP-34 hérite de P2.
- **Données confidentielles.** Avec H1 désactivé pour la démonstration, le contenu d'un fichier confidentiel entre dans un `tool_result`, puis part chez le fournisseur à l'appel suivant. C'est conforme à la lettre et couvert par l'avertissement (« tout le contexte »). Un scénario qui combine H1 désactivé et un modèle cloud mérite pourtant une mention dans l'avertissement, ou une interdiction dans le chargeur de scénarios.

**AD à resserrer :** AD-11, AD-17.

**Règle proposée.**
> - AD-11 : « en mode chat, le contexte principal est toujours renvoyé en entier ; aucune préservation d'état n'est tentée ».
> - AD-17 : l'historique porte les `tool_call_id` dès maintenant (P2), pour qu'un rejeu inter-modèles soit possible au palier 2 sans migration.

---

## Synthèse

| # | Paire | Sévérité | AD à resserrer |
| --- | --- | --- | --- |
| P1 | Port `Engine` texte / corps chat ; deux « corps exacts » | Critique | AD-5, AD-4 |
| P2 | `tool_call_id` absent de l'historique ; actions forcées ; format Mistral | Critique | AD-4, AD-25, identifiants |
| P3 | Clé envoyée à un autre hôte (id partagé, `base_url` modifiée, redirection `api-key`) | Critique | AD-15, AD-20 |
| P4 | Clé dans la trace via `effect_applied`, cause d'erreur, écho d'intention | Majeur | AD-20, AD-23, AD-16 |
| P5 | `test_cloud_model` en classe b refusé en `diagnostic` ; `set_api_key` sans classe | Majeur | AD-3, AD-21 |
| P6 | Confirmation de `cloud-warning` garantie par le front seul ; forme et relance du choix | Majeur | AD-3, AD-21, AD-20 |
| P7 | `[[cloud.models]]` sans propriétaire ; fusion qui efface les préréglages | Majeur | AD-6/AD-20, conventions |
| P8 | `outbound_request` du modèle : `turn_id = null`, `origin` absent de la portée | Majeur | AD-2, AD-15 |
| P9 | Événement de réconciliation des tokens absent ; cas sans `usage` | Majeur | AD-2, AD-4, AD-1 |
| P10 | Quota par minute contre plafond par appel : 429 au 2e appel | Majeur | AD-9, AD-16 |
| P11 | Raisonnement en historique, forcé sans `tools`, normalisation en chat | Majeur | AD-4, AD-6, AD-25 |
| P12 | `model_call_ended` en chat : débit non comparable, `raw_output` indéfini | Majeur | AD-2, AD-5 |
| P13 | Sous-agent et rejeu en mode chat ; H1 éteint avec un modèle cloud | Mineur | AD-11, AD-17 |

**Priorité avant la story 11 :** P1, P2 et P3 (contrats de données et secret), puis P4 et P5, que la story ne peut pas trancher seule sans créer une seconde convention.
