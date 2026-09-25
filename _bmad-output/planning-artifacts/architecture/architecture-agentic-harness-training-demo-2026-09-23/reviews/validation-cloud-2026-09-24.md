---
title: 'Validation des amendements cloud du spine (FR-43)'
date: '2026-09-24'
target: ARCHITECTURE-SPINE.md (amendements du 2026-09-24)
branch: spec/cloud-llm
intent: validate
sources:
  - review-cloud-rubric-reconcile.md
  - review-cloud-verification.md
  - review-cloud-adversary.md
---

# Validation des amendements cloud du spine (FR-43)

## Verdict

**Les amendements du 2026-09-24 ne suffisent pas encore pour lancer la story 11.** Ils reprennent fidèlement le §4.4 de la proposition, et AD-3 et AD-21 vont même un peu au-delà. Mais ils ont été greffés sur des AD écrits pour du texte rendu localement :
- quatre formes partagées restent à inventer par la story 11 : le port moteur, les identifiants d'appels d'outils, les tokens réconciliés et le schéma de `[[cloud.models]]` ;
- la clé peut fuir sans enfreindre la lettre des règles ;
- le préréglage Mistral échouerait dès le premier appel.

Il faut une passe **Update** ciblée sur environ 10 AD existants. Aucun nouvel AD n'est nécessaire, aucun ID n'est renuméroté. Deux décisions reviennent au porteur : le quota par minute, et la confirmation de l'avertissement.

**Relecteurs** (subagents indépendants) :
- rubrique et réconciliation : 22 constats ;
- vérification web : 8 affirmations examinées ;
- adversaire : 13 paires.

**Lint** : 33 alertes « placeholder », toutes des faux positifs. Ce sont des jetons de format documentés, comme `{turn_id}`.

## Critiques

### C1. AD-5 se contredit, et « le JSON exact » désigne deux corps différents
- **Constat.** Le titre (« reçoit du texte déjà rendu, rien de plus ») et le Prevents (« un adaptateur qui envoie des messages de chat ») interdisent ce que la règle amendée autorise. La signature `complete(prompt_ids | prompt_text, …)` n'a pas été étendue. Une unité ajoutera `complete_chat`, une autre passera `json.dumps(body)` par la signature existante. Par ailleurs, `context_rendered` (AD-4) et `outbound_request` (AD-15) promettent chacun « le JSON exact ». Or l'adaptateur ajoute `model`, `stream` et `max_tokens`, donc les deux corps diffèrent.
- **Correctif.** Amender le titre, le Prevents et la signature d'AD-5 : `complete(request: RenderedPrompt | ChatBody, …)`. `context` construit le corps complet. L'adaptateur n'y ajoute que les en-têtes. Un test vérifie que le corps envoyé est identique octet pour octet à celui de `context_rendered`. Amender aussi le titre et le Prevents d'AD-4 (« tokens attribués exactement »).

### C2. L'historique (AD-4) n'a pas d'identifiant d'appel d'outil
- **Constat.** L'historique stocke `tool_calls: [{name, arguments}]`. Le format chat exige un `tool_call_id`, des arguments en chaîne et exactement une réponse `tool` par appel. Mistral n'accepte que des ids de **9 caractères alphanumériques** (vérification web). Les actions forcées (AD-25) et les ids Groq rejoués échoueraient.
- **Correctif.** La session attribue l'id au moment où l'appel est créé (modèle, sous-agent ou action forcée), au format `[A-Za-z0-9]{9}`. Il est stocké dans l'historique `{id, name, arguments}`. L'assembleur ne fabrique jamais d'id.

### C3. La clé peut partir vers un autre hôte
- **Constat.** Trois chemins :
  1. `api_keys.json {model_id: key}` confond deux fournisseurs qui servent le même nom de modèle (`openai/gpt-oss-120b` chez Groq et OpenRouter).
  2. Un `base_url` modifié dans `settings.json` enverrait la clé déjà saisie au nouvel hôte.
  3. httpx ne suit pas les redirections par défaut, mais le code livré les suit (`tools/network.py:39`, `follow_redirects=True`). Quand il les suit, httpx ne retire que `Authorization` : l'en-tête `api-key` d'Azure passe.
- **Correctif (AD-15, AD-20).** Un `id` local unique par entrée cloud, qui sert de clé à `api_keys.json`. La clé est liée à l'hôte au moment de la saisie : `{id: {host, key}}`, et elle est ignorée si l'hôte a changé. `follow_redirects=False` est explicite pour `origin = model`. Azure passe par l'API v1 avec `Bearer`.

## Hautes

### H4. La clé peut entrer dans la trace
- **Constat.** Trois voies : la charge libre d'`effect_applied`, puisqu'AD-23 ne prévoit aucun effet pour la clé ; la « cause » d'un `harness_error`, car certains fournisseurs recopient la clé masquée dans leur 401 ; l'écho de l'intention.
- **Correctif (AD-20, AD-23, AD-16).** Un effet `ApiKeySet{model_id}` qui ne porte pas la clé. `SecretStr` de bout en bout. Les chaînes du fournisseur sont filtrées avant d'entrer dans un événement. Un test avec une clé sentinelle couvre la trace, `settings.json`, les journaux et `/api/*`.

### H5. Le préréglage Mistral ne fonctionne pas en l'état
- **Constat.** Mistral rejette `stream_options` (422 `extra_forbidden`). Son raisonnement arrive dans `delta.content` sous forme de liste de blocs `thinking` et `text`, et `reasoning_content` n'existe pas. Chez Groq, l'usage arrive dans `x_groq.usage`, et Qwen renvoie son raisonnement dans `<think>`. Les paramètres qui activent le raisonnement varient selon le fournisseur et le modèle.
- **Correctif (AD-5, AD-6).** Rendre déclaratifs, par entrée `[[cloud.models]]` : `stream_usage` (booléen), le format du raisonnement (`field` / `content_blocks` / `think_tags`) et les paramètres de raisonnement. Le bouton « Tester » valide la déclaration.

### H6. Les tokens réconciliés n'ont pas d'événement
- **Constat.** `usage.prompt_tokens` arrive après `context_rendered`, et aucun événement ne porte la ventilation corrigée. Le front devrait donc recalculer, ce qui viole AD-1 et le « sans recalcul côté front » de CAP-31. Rien ne marque non plus un segment comme estimé. La règle « concaténation = prompt envoyé » tombe en mode chat sans remplaçant.
- **Correctif (AD-2, AD-4).** Un segment porte `estimated: bool`. En mode chat, `context_rendered` porte les segments et le `body` JSON. Après l'appel, un nouveau kind `context_reconciled{call_id, segments, total}` (ou ces champs sur `model_call_ended`) remplace les estimations. Rétablir le libellé de D6 : « Gabarit appliqué chez le fournisseur (estimé) ».

### H7. La liste des erreurs d'AD-16 est incomplète, et D5 s'est perdue
- **Constat.** Manquent :
  - le 400 pour un contexte dépassé ;
  - le **413 de Groq**, quand une requête seule dépasse le quota par minute : il n'est pas réessayable ;
  - les 422 de validation de Mistral ;
  - les erreurs envoyées en plein flux, après un 200 ;
  - `tool_use_failed` de Groq, qui devrait suivre la voie de l'appel mal formé (AD-10/AD-14) et non terminer le tour.

  Par ailleurs, D5 (« arguments JSON invalides → voie mal formée ») n'a atterri nulle part.
- **Correctif.** Compléter AD-16. Dans AD-6 ou AD-10 : des arguments JSON invalides et `tool_use_failed` suivent la voie de l'appel mal formé.

### H8. `max_window` ne protège pas le quota par minute *(décision du porteur)*
- **Constat.** Le quota de 8 000 tokens par minute de Groq gpt-oss-120b est confirmé. Groq compte le prompt plus le `max_tokens` demandé. `max_window` borne un appel, pas un tour : le 2e appel d'un tour avec outils déclenche très probablement un 429, alors que c'est justement le critère de succès §5 « un tour Groq avec outils ». Le plafond de 200 000 tokens par jour tient mal une demi-journée de formation.
- **Options.**
  - (a) Assumer le 429 comme matériau pédagogique.
  - (b) La session espace les appels d'après les en-têtes `x-ratelimit-*`.
  - (c) Fixer une fenêtre par défaut basse pour Groq (environ 3 000).
  - (d) Choisir un préréglage Groq au quota plus large.

  La règle « `max_window` tient compte du TPM » doit devenir une formule, ou disparaître.

### H9. `[[cloud.models]]` est une dimension silencieuse
- **Constat.** Aucune AD ne fixe le schéma de l'entrée. Or cette entrée alimente à la fois la configuration, l'infobulle, l'avertissement, AD-6, AD-9 et AD-15. De plus :
  - `_deep_merge` (`config.py:37`) **remplace les listes**, donc un point d'accès ajouté dans `settings.json` efface Groq et Mistral ;
  - `selected_model` est un chemin de fichier ;
  - « jamais chargé d'office » (D1, CAP-43) se heurte au choix mémorisé et rechargé de la story 1b.
- **Correctif (AD-20 seed, AD-21).** Fixer le schéma : `{id, provider, base_url, model, auth_header, stream_usage, reasoning_format, tools, reasoning, context, max_window, window, hosting_fr, training_fr, trial, notes_fr}`. Fusionner par `id` : `settings.json` ajoute ou remplace une entrée, sans effacer les autres. `selected_model` devient `{kind: file|cloud, ref}`. Reformuler : « jamais **choisi** d'office ; un choix explicite mémorisé est repris au lancement, sans réafficher l'avertissement ».

## Moyennes

- **M10. AD-3, classes d'intentions.** `test_cloud_model` est en classe (b), donc « refusée hors `idle` », alors qu'elle sert en état `diagnostic`. `download_model` avait déjà ce défaut. `set_api_key` n'a pas de classe. Correctif : une règle explicite pour l'état `diagnostic`.
- **M11. Confirmation de l'avertissement** *(décision du porteur)*. Seul le front la garantit. De plus, « Tester » envoie un appel avant la confirmation exigée « avant tout appel » par CAP-43. Correctif proposé : `select_model{acknowledged: true}`, vérifié par la session, et CAP-43 reformulée (« le test envoie une invite fixe, sans donnée de l'utilisateur »).
- **M12. Origine et portée.** L'`origin` de la `TraceScope` (AD-2, l. 119) n'inclut pas `model`. AD-15 range l'appel au modèle parmi les sorties « hors brique » tracées avec `turn_id = null`, alors qu'il a lieu dans un tour. Correctif : l'appel dans un tour porte son `turn_id` ; seul `test_cloud_model` a `turn_id = null`.
- **M13. « Pas de réseau » au lancement.** Le vérifier demanderait une sortie hors de la liste fermée d'AD-15. Correctif : ne vérifier que la présence de la clé, ou passer par la sonde du diagnostic.
- **M14. Contenus.** Le texte commun de l'avertissement dans `content/` n'est pas relié à AD-19 dans la carte des capacités.
- **M15. Canal forcé sans `tools`, raisonnement rendu en chat.** Le raisonnement des tours antérieurs est-il renvoyé ? Une action forcée envoie-t-elle `tools` ? Ces points sont à trancher dans la table d'emplacements du mode chat (adversaire, P11).

## Basses

- **L16. Procédure Update.** Le memlog ne contient aucune entrée pour ces amendements, alors qu'il fait autorité. `architecture-view.html` n'a pas été régénéré. La proposition annonce 11 AD amendés, mais AD-3 l'est aussi : 12 au total.
- **L17.** Le débit local et le débit cloud ne sont pas comparables tels quels (tokens de sortie divisés par `gen_ms` ?). `raw_output` n'est pas défini en mode chat. Le sous-agent et le rejeu en mode chat sont à vérifier (P12, P13).
- **L18.** Les 33 alertes « placeholder » du lint sont des faux positifs.

## Ce qui tient

- La portée et l'esprit : option explicite, aucune dépendance nouvelle (httpx est déjà présent), aucune reprise de code livré.
- La carte des capacités, le schéma des processus et le report de Vertex (le jeton OAuth est confirmé).
- AD-8 (mémoire nulle), AD-12 (nœud en zone Réseau) et la liste autorisée d'AD-15 alimentée par la configuration.
- Azure fonctionne avec un simple `base_url`, sur l'API v1.

## Suite proposée

Intégrer ces constats par l'intention **Update** du même skill : entrées dans le memlog, amendement d'AD-2, 3, 4, 5, 6, 10, 15, 16, 20 et 21 sans renumérotation, puis nouveau passage du gate. Avant cela, deux décisions sont attendues : H8 (quota) et M11 (confirmation). La proposition de changement et la SPEC (CAP-43, D6) sont à répercuter au même moment.
