# Mesures réelles OpenAI (fournisseurs natifs 4/5), 2026-10-03

Clé `OPENAI_API_KEY` lue dans l'environnement utilisateur de Windows et passée au seul
processus de mesure (jamais affichée, journalisée, écrite ni commitée). Requêtes `POST
https://api.openai.com/v1/responses`, `Authorization: Bearer`, `stream: true`, `store: false`,
modèle `gpt-6-luna`.

**Bloquant : le compte n'a plus de crédit.** La première requête a reçu un 200, puis un
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

## Résultats

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

## Réponses aux questions de la story

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

## Recette (« clé réelle »)

Non faite : le tour Outils raisonnement allumé et le tour Raisonnement demandent une réponse du
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
