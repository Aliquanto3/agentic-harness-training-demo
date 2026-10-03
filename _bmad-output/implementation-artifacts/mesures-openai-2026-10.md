# Mesures réelles OpenAI (fournisseurs natifs 4/5), 2026-10-03

Clé `OPENAI_API_KEY` lue dans l'environnement utilisateur de Windows et passée au seul
processus de mesure (jamais affichée, journalisée, écrite ni commitée). Requêtes `POST
https://api.openai.com/v1/responses`, `Authorization: Bearer`, `stream: true`, `store: false`,
modèle `gpt-6-luna`.

**Le soir, crédit rechargé par Anaël, les mesures 2, 3 et 5 et la recette ont abouti : voir
« Mesures du 2026-10-03 au soir ».** L'après-midi, le compte n'avait plus de crédit. La première requête a reçu un 200, puis un
événement `error` (`insufficient_quota`, code `credit_balance_exhausted`, « You have no credits
remaining. Add credits to continue using the API at
https://platform.openai.com/settings/organization/billing/ ») et `response.failed` sans usage.
Aucune réponse n'a donc pu être générée : les mesures qui demandent une réponse du modèle (2, 3,
5 et la recette « clé réelle » de l'acceptation) restent à faire, **action d'Anaël : ajouter du
crédit au compte OpenAI**. La validation des paramètres, elle, se fait avant le contrôle du
crédit : un paramètre refusé rend un 400 immédiat, un corps accepté rend le 200 puis l'erreur de
crédit. Les mesures 1 et 4 sont tranchées à ce niveau.

7 requêtes, aucune facturée (usage `null` dans `response.failed`, 400 non facturé). **Coût
total : 0 $.**

## Mesures du 2026-10-03 au soir (crédit rechargé)

Anaël a rechargé le crédit le 2026-10-03 au soir. Mêmes règles (clé lue dans l'environnement
utilisateur, passée au seul processus de mesure ; aucun serveur WaveStack sur 8420). **39
requêtes, toutes 200 puis `response.completed`, 0,0024 $ en tout** (0,0011 $ pour les 22
appels écrits à la main, 0,0013 $ pour les 3 recettes par `AppSession` ; coûts calculés sur
l'`usage` de chaque réponse aux prix déclarés), sous le plafond de 0,50 $.

Forme réelle relevée, conforme à l'adaptateur : `response.output_item.added` puis
`response.reasoning_summary_part.added`, `response.reasoning_summary_text.delta` (champs
`item_id`, `output_index`, `summary_index`, `delta`), `…text.done`, `…part.done`,
`response.output_item.done` ; l'item `reasoning` fini vaut `{id: "rs_…", type: "reasoning",
content: [], encrypted_content: "…" (≈ 1 500 caractères), summary: [{type: "summary_text",
text}]}`. Les appels : `output_item.added` (`function_call`, `call_id`, `name`),
`response.function_call_arguments.delta` et `.done`, `output_item.done`. L'`usage` porte aussi
`input_tokens_details.cache_write_tokens` (toujours 0 ici ; l'adaptateur ne le lit pas, aucun
prix d'écriture en cache n'étant déclaré). `summary: "auto"` est rendu `"detailed"` par
OpenAI. Le résumé arrive **en anglais**, même avec des instructions en français.

| # | Mesure de la story | Requête (sans clé) | Statut | Extrait de réponse | Coût |
|---|---|---|---|---|---|
| E0 | **2** : effort « low », « Combien font 1234 × 5678 ? Utilise la calculatrice. », puis la sortie de l'outil | `effort: "low"`, outil `calculator` | 200 ×2 | 0 token de raisonnement, aucun item `reasoning` (premier essai, question trop simple) | 0,00004 $ |
| E1 | **2** : effort « low », question à outil simple (« Calcule (1234 × 5678) − (987 × 654), puis divise par 7 », un appel par opération), boucle de 5 appels puis un tour de suite | `reasoning: {effort: "low", summary: "auto"}`, outil `calculator`, `store: false`, `include` | 200 ×6 | **0 token de raisonnement** à chaque appel, aucun item `reasoning`, aucun résumé : sur une tâche simple, Luna ne raisonne pas | 0,00021 $ |
| E2 | **2** : effort « medium », même boucle | `effort: "medium"` | 200 ×5 | **0 token de raisonnement** aussi : l'effort ne force pas le raisonnement | 0,00016 $ |
| E3 | **2** : effort « low », énigme (« plus petit n > 1 tel que n mod 3 = 2, n mod 5 = 3, n mod 7 = 2, en raisonnant, puis n × 1234 et n × 5678 à la calculatrice ») | `effort: "low"` | 200 ×4 | 1er appel : `reasoning` (71 tokens de raisonnement sur 94, résumé visible « **Calculating using CRT** … ») puis `function_call` ; appels suivants sans raisonnement ; tour de suite : 32 tokens de raisonnement, résumé visible | 0,00027 $ |
| E4 | **2** : effort « medium », même énigme | `effort: "medium"` | 200 ×3 | 1er appel : 96 tokens de raisonnement sur 119 (contre 71 sur 94 en « low »), résumé visible ; même réponse (n = 23) | 0,00022 $ |
| E5 | **3** : items `reasoning` renvoyés avec leur `id` | 2e appel d'E3 et d'E4 : `input` = `message` `user`, item `reasoning` **verbatim, `id` `rs_…` compris**, `function_call` **reconstruit sans son `id` `fc_…`** (`call_id`, `name`, `arguments`), `function_call_output` | 200 | accepté | (dans E3, E4) |
| E6 | **3** : item `reasoning` avant un `message` reconstruit | tour de suite d'E3 : l'historique porte l'item `rs_…` du 1er appel, les `function_call` et leurs sorties, la réponse en `message` `assistant` **en chaîne, sans `id` `msg_…`**, puis « Et multiplié par 3 ? » | 200 | accepté | (dans E3) |
| E7 | **3** : entrelacement rs/fc/rs/fc | deux énigmes indépendantes, « lance les deux calculs dans la même réponse », effort « medium » | 200 ×2 | **non obtenu** : la sortie est `reasoning`, `function_call`, `function_call` (un seul item `reasoning`, avant deux appels parallèles) ; renvoyée dans cet ordre, acceptée. 109 tokens de raisonnement mais **résumé vide** | 0,00020 $ |
| R1′ | Recette : tours Outils et Raisonnement par `AppSession`, premier essai | énigme à un produit, puis train | 200 ×5 | deux tours `completed` ; résumé au tour Raisonnement ; aucun item `reasoning` sur un appel d'outil (le modèle n'a pas raisonné avant ses appels) | 0,00039 $ |
| R2 | Recette : trois tours par `AppSession` (briques Prompt système, Mémoire courte, Outils, Raisonnement) | énigme (deux produits), train (« part à 9 h 40, 275 km à 110 km/h, arrêt de 18 min »), « Et s'il part à 10 h 05 ? » | 200 ×9 | trois `turn_ended` `completed` ; résumé au canal Raisonnement au tour 3 (« **Calculating time from minutes** … ») ; au tour 3, l'item `rs_…` de la réponse finale du tour 2 repart, `id` compris, juste avant son `message` : accepté ; outils envoyés avec `strict: false` | 0,00064 $ |
| R3 | Recette (acceptation « clé réelle ») : tour Outils raisonnement allumé, par `AppSession` | les deux énigmes (prompt d'E7), effort « low » | 200 ×3 | 2e appel : résumé au canal Raisonnement (« **Solving CRT manually** … ») et **deux appels parallèles** ; 3e appel : l'item `rs_…` repart, `id` compris, **juste avant ses deux `function_call`**, puis les deux sorties : accepté ; réponse « (a) 28 382, (b) 130 594 », `turn_ended` `completed` | 0,00027 $ |

Réponses :

- **2** : le résumé est visible dès que le modèle raisonne, en « low » comme en « medium ». Ni
  l'un ni l'autre ne force le raisonnement : sur une tâche simple, 0 token. Sur l'énigme,
  « medium » raisonne un peu plus (96 contre 71 tokens), pour un coût négligeable dans les deux
  cas (moins de 0,0001 $ l'appel). **`on` garde l'effort « low »** : il suffit à montrer le
  résumé, et un tour simple ne raisonne de toute façon pas. Pour la démonstration : poser une
  question qui demande de raisonner (énigme, durée avec un arrêt) pour voir le canal
  Raisonnement.
- **3** : items `reasoning` renvoyés **avec leur `id`** sous `store: false` : **acceptés**, avant
  un `function_call` comme avant un `message`, et avant deux appels parallèles. Les
  `function_call` et `message` reconstruits par le traducteur, **sans leurs `id` `fc_…` et
  `msg_…`**, sont acceptés à côté : rien à changer. Entrelacement rs/fc/rs/fc non obtenu (un
  seul item `reasoning` par réponse) ; le traducteur garde de toute façon l'ordre reçu (tests).
- **5** : le résumé s'affiche **sans vérification d'organisation** (E3, E4, R2, R3). Un résumé
  peut rester vide alors que le modèle a raisonné (E7 : 109 tokens, résumé vide) : c'est un choix
  d'OpenAI (`summary: "auto"`), pas un défaut de vérification ; aucune action d'Anaël.

Aucune mesure n'a montré de défaut du code : aucun changement après mesure.

## Mesures du 2026-10-03 après-midi (compte sans crédit)

### Résultats

| # | Mesure de la story | Requête (sans clé) | Statut | Extrait de réponse | Coût |
|---|---|---|---|---|---|
| M1 | **1** : `temperature` et `top_p`, raisonnement éteint | `reasoning: {effort: "none"}`, `temperature: 0.7`, `top_p: 0.9`, `max_output_tokens` 64, `include: ["reasoning.encrypted_content"]` | 200 puis `error` | paramètres acceptés (renvoyés tels quels dans `response.created` : `temperature` 0,7, `top_p` 0,9, `reasoning.effort` « none ») ; puis `credit_balance_exhausted` | 0 $ |
| V1 | **1** (contre-épreuve) : `temperature` et `top_p`, raisonnement allumé | `reasoning: {effort: "low", summary: "auto"}`, mêmes réglages | **400** | « Unsupported parameter: 'temperature' is not supported with this model. » (`param: temperature`) | 0 $ |
| V2 | **4** : contenu d'assistant en chaîne, et forme complète du traducteur | `instructions` (deux systèmes joints par « \n\n »), `input` : `message` `user` en chaîne, `function_call` (`call_id` du harnais `t1.c1`), `function_call_output`, `message` `assistant` **en chaîne**, `message` `user` ; `tools` `{type: "function", name, description, parameters}` ; `reasoning` low + `summary: "auto"` ; `store: false`, `include` | 200 puis `error` | corps accepté ; puis `credit_balance_exhausted` | 0 $ |
| R1 | Recette (acceptation « clé réelle ») : deux tours réels par `AppSession` | corps écrit par le harnais : `instructions`, `input`, outils de la brique Outils, `max_output_tokens` 1 536, `reasoning` low + `summary: "auto"`, `store: false`, `include` | 200 puis `error` (2 tours, joués deux fois : avant et après la lecture différée d'`error`) | corps accepté ; `harness_error` « OpenAI refuse l'appel. Aucun quota actif sur ce compte… » (depuis la revue : « le crédit du compte est épuisé »), message du fournisseur cité, `turn_ended` `error`, aucun coût compté | 0 $ |

Forme réelle des événements relevée : `response.created` et `response.in_progress` (objet
`response` complet, `usage: null`), puis, sur ce compte, `error` de forme `{type: "error",
error: {type, code, message, param}, sequence_number}` et `response.failed` (`response.error:
{code, message}`, `usage: null`). L'adaptateur lit les deux formes d'`error` (imbriquée et à
plat) et répond « le crédit du compte est épuisé. Ajoutez du crédit… » à `insufficient_quota`
ou `credit_balance_exhausted` (`code` ou `type`, dans le flux ou sur un 429).
L'objet `response` renvoyé montre aussi `reasoning.context: "all_turns"` et
`prompt_cache_retention: "24h"` par défaut.

### Réponses aux questions de la story (avant le crédit ; 2, 3 et 5 : voir plus haut)

1. **`temperature` et `top_p`** : acceptés avec l'effort « none », refusés (400) avec l'effort
   « low ». `sampling = ["temperature", "top_p"]` pour `openai_luna` ; la règle `sampling_sent`
   (rien pendant que le modèle raisonne) les retire raisonnement allumé.
2. **Effort `low` puis `medium` (résumé visible, tokens de raisonnement, coût)** : non mesuré
   (crédit épuisé). `on` garde l'effort « low » de la spec.
3. **Items `reasoning` renvoyés avec leur `id` sous `store: false`** : non mesuré (aucun item
   reçu). L'adaptateur les renvoie verbatim, `id` compris ; si OpenAI le refuse, la parade de la
   spec est de les renvoyer sans `id` (`AppSession._reasoning_item`).
4. **Contenu d'assistant en chaîne** : accepté à la validation (V2), comme les items
   `function_call` à `call_id` du harnais et `function_call_output`.
5. **Résumé absent faute de vérification d'organisation** : non observable sans réponse. OpenAI
   peut exiger la vérification de l'organisation avant de rendre les résumés : si le canal
   Raisonnement reste vide une fois le crédit ajouté, c'est l'action d'Anaël dans la console
   OpenAI (vérification de l'organisation, dans ses paramètres).

### Recette (« clé réelle »)

Faite le soir (R1′, R2, R3 plus haut). L'après-midi, non faite : le tour Outils raisonnement allumé et le tour Raisonnement demandent une réponse du
modèle. Un tour réel par `AppSession` (briques Prompt système, Mémoire courte, Outils et
Raisonnement allumées) a seulement prouvé que le corps réel du harnais passe la validation
d'OpenAI et que le chemin d'erreur réel aboutit de bout en bout (R1). À
rejouer, crédit ajouté : un tour Outils (« Combien font 1234 × 5678 ? Utilise la
calculatrice. ») puis un tour Raisonnement (« Un train part à 9 h et roule 150 km à 100 km/h…
»). À relever, par numéro de mesure de la story :

- **2** : effort « low » puis « medium » sur la même question à outil : résumé visible ou non,
  `output_tokens_details.reasoning_tokens`, coût de chaque appel ;
- **3** : items `reasoning` renvoyés avec leur `id` (`rs_…`) sous `store: false` : acceptés, ou
  refusés (alors les renvoyer sans `id`) ; et, si un item renvoyé avec son `rs_` est refusé ou
  ignoré, si les items `function_call` et `message` reconstruits par le traducteur (sans leurs
  `id` `fc_…` et `msg_…`, seulement `call_id`, `name`, `arguments` ou `role`, `content`) doivent
  porter ces `id` à côté de lui ;
- **5** : résumé absent faute de vérification d'organisation (canal Raisonnement vide alors que
  `reasoning_tokens` > 0) : le consigner, action d'Anaël dans la console ;
- un appel où le modèle entrelace raisonnement et appels (`rs`, `fc`, `rs`, `fc`) : renvoyé dans
  le même ordre, accepté.

Les mesures 2, 3 et 5 n'ont pas de ligne dans le tableau : aucune n'a pu être jouée.
