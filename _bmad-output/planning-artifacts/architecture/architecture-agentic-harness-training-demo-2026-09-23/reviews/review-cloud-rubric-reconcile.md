---
reviewed: ARCHITECTURE-SPINE.md, amendements « modèles cloud via API » du 2026-09-24 (non commités, branche spec/cloud-llm)
lens: grille « bon spine » sur les amendements cloud, puis réconciliation avec sprint-change-proposal-2026-09-24.md (D1 à D15, §4.4, §5), SPEC.md (CAP-43, CAP-3, CAP-31, CAP-35, NFR), EXPERIENCE.md (composants et états cloud), stories.yaml (story 11)
date: 2026-09-24
---

# Revue des amendements cloud du spine : grille et réconciliation

## Verdict

Les amendements reprennent fidèlement la lettre du §4.4 : tous les paragraphes prévus sont en place, et AD-3 et AD-21 vont même un peu plus loin. En revanche, le spine n'est pas encore un contrat suffisant pour la story 11. Le mode chat d'AD-4 ne dit pas quel événement porte la ventilation corrigée après l'appel. Or le front n'a pas le droit de la recalculer (AD-1, CAP-31). Il ne dit pas non plus quelle forme prend le contexte rendu. La forme des messages au format chat n'est pas fixée (ids d'appel d'outil, réponse à un appel mal formé), et elle est incompatible avec l'historique tel qu'il est stocké aujourd'hui. D5 (« arguments JSON invalides → voie mal formée ») s'est perdue. Les titres et les Prevents d'AD-4 et d'AD-5 contredisent désormais leur Rule. Enfin, la configuration `[[cloud.models]]` est une dimension silencieuse : pas de schéma, pas d'identifiant, pas de persistance du choix. Sa fusion avec `settings.json` efface les préréglages dans le code actuel. Il faut une passe ciblée sur environ 8 AD, sans nouvel AD.

Échelle : **Critique** (bloque la story) · **Haute** (divergence ou échec probable) · **Moyenne** (divergence possible, à trancher avant la story 11) · **Basse** (hygiène, traçabilité).

Les numéros de ligne renvoient à l'arbre de travail non commité de `spec/cloud-llm`. Sauf mention contraire, il s'agit de `ARCHITECTURE-SPINE.md`.

## Synthèse

| # | Sévérité | Emplacement | Sujet |
|---|---|---|---|
| 1 | Haute | AD-4 l. 177-183, AD-2 l. 116, AD-1 l. 78, AD-9 l. 261 | Aucun événement ne porte la ventilation corrigée par `usage` ni le marquage « estimé » : le front devrait recalculer |
| 2 | Haute | AD-4 l. 145, 178 | Forme de `context_rendered` en mode chat indéfinie ; l'invariant « concaténation = prompt envoyé » tombe sans remplaçant |
| 3 | Haute | AD-4 l. 151, 177-178 ; AD-25 l. 532 | Forme des messages au format chat : ids d'appel d'outil, arguments en chaîne, réponse d'un appel mal formé, raisonnement de l'historique |
| 4 | Haute | AD-5 l. 202, AD-6 l. 218, AD-14 l. 350 | D5 perdue : arguments JSON invalides et refus « appel d'outil raté » du fournisseur finissent en `error` au lieu de la voie mal formée |
| 5 | Haute | AD-4 l. 140-143, AD-5 l. 187-191 | Titres et Prevents d'AD-4 et d'AD-5 contredits par leur Rule ; signature du port `Engine` non étendue |
| 6 | Haute | AD-9 l. 254 ; D7 | `max_window` borne un appel, pas un tour : avec 8 000 tokens/min, le 2e appel d'un tour avec outils déclenche presque sûrement un 429 |
| 7 | Haute | AD-6 l. 218, AD-15 l. 386, AD-20 l. 455, AD-21 l. 472-474, conventions l. 540 | `[[cloud.models]]` sans schéma ; `model_id` non défini ; persistance du modèle cloud choisi non fixée |
| 8 | Moyenne | Conventions l. 543, AD-15 l. 386 ; `config.py` l. 37-44 | Fusion `wavestack.toml`/`settings.json` : une liste dans `settings.json` remplace les préréglages ; `settings.json` écrit à la fois par la session et à la main |
| 9 | Moyenne | AD-15 l. 387-390, AD-2 l. 119 | Appel au modèle rangé parmi les sorties « hors brique, `turn_id = null` » ; `origin` de la `TraceScope` sans `model` |
| 10 | Moyenne | AD-3 l. 129-133, AD-21 l. 472 | `set_api_key` et `test_cloud_model` hors des classes d'intentions ; comportement après démarrage ; confirmation de l'avertissement non située |
| 11 | Moyenne | AD-21 l. 471-474, AD-7 l. 226 | Liste cloud imbriquée sous « échec bloquant » ; spine non aligné sur la story 1b ; « jamais chargé d'office » face au choix mémorisé |
| 12 | Moyenne | AD-21 l. 472 ; CAP-43 (SPEC l. 154) | Test : contenu, prompt, événement de résultat non fixés ; « à confirmer avant tout appel » contredit le test avant le choix |
| 13 | Moyenne | AD-6 l. 214, 218 ; AD-9 l. 255 | Raisonnement du modèle cloud : aucune règle de correspondance avec la brique ; un modèle qui raisonne toujours épuise la réserve de 512 tokens |
| 14 | Moyenne | AD-4 l. 179-181 | Estimation : `chars_per_token` appliqué à des octets, arrondi non fixé, portée de « l'écart du dernier appel » (premier appel, sous-agent) |
| 15 | Moyenne | AD-15 l. 396, AD-20 l. 449-455, AD-23 l. 495-501, conventions l. 545 | Clé : journaux, `settings.json`, messages d'erreur et effets non couverts ; écriture d'`api_keys.json` hors de l'union d'effets |
| 16 | Moyenne | AD-19 l. 439, AD-1 l. 77 | Texte propre au fournisseur (infobulle, avertissement) et données du `model-indicator` : ni source ni événement |
| 17 | Basse | AD-4 l. 180, 183 ; D6 ; CAP-31 | Libellé « (estimé) » perdu ; « tout ≈ » (D6) contre « ventilation ≈, total API » (CAP-31) ; libellé `template` en mode chat |
| 18 | Basse | AD-2 l. 116 ; EXPERIENCE l. 138 | `output_tps` sans formule ; `usage_source: estimate` sans règle pour les tokens de sortie ; `token-counter` sans débit |
| 19 | Basse | AD-16 l. 404 | Liste des refus incomplète (413, 400 contexte, 5xx, réseau) ; délai conseillé non structuré |
| 20 | Basse | AD-24 l. 513 ; conventions l. 546 | Annulation pendant l'attente du premier fragment ; test de l'adaptateur sans réseau non prévu (le « 429 simulé par le moteur factice » ne teste pas l'adaptateur) |
| 21 | Basse | Non-objectif SPEC l. 183 ; AD-8 l. 247, AD-12 l. 315 | `openai_chat` pointé sur la boucle locale serait traité en « cloud » (mémoire nulle, zone Réseau) ; forme d'URL Azure |
| 22 | Basse | Binds des AD, carte l. 680, companion, arborescence, EXPERIENCE l. 157 | Traçabilité : FR-43 absent de tous les `Binds` ; carte incomplète ; `architecture-view.html` non mis à jour ; état « Aucun tour » contredit |

---

## Constats détaillés

### 1. Aucun événement ne porte la ventilation corrigée ni le marquage « estimé » (Haute)

**Emplacement.** AD-4, mode chat, l. 177-183 ; AD-2, l. 116 ; AD-1, l. 78 ; AD-9, l. 261. Exigence source : CAP-31 (SPEC l. 116-118, « sans recalcul côté front »), D6.

**Problème.**
- `context_rendered` est émis **avant** l'appel : la jauge doit bouger avant l'envoi (AD-9). En mode chat, il porte donc des estimations.
- `usage.prompt_tokens` n'arrive qu'**après** l'appel, dans le dernier fragment du flux. La règle « l'écart va à `template`, réduction proportionnelle si négatif, la somme reste égale au total » (l. 180) produit une **nouvelle ventilation**. Aucun événement n'est désigné pour la porter : `model_call_ended` ne porte que `prompt_tokens`.
- AD-1 (l. 78) interdit au front de recalculer « tokens » et « ventilation de la jauge ». Deux implémentations divergeront : l'une réémet `context_rendered`, l'autre ajoute la ventilation à `model_call_ended`, une troisième laisse le front faire la soustraction, ce qui viole AD-1.
- De même, rien dans `context_rendered` ni dans `context_preview` ne dit au front que les valeurs sont estimées. La phrase « Les valeurs estimées sont marquées ≈ dans l'interface » (l. 183) n'a pas de support dans les données.

**Correctif.** Dans AD-4 (mode chat) et AD-2 :
- `context_rendered` et `context_preview` portent `tokens_basis: exact|estimate`, calculé par la session.
- Après l'appel, la session émet un second `context_rendered{call_id identique, tokens_basis: "api", …}` qui remplace le premier dans les projections, comme `model_call_ended` remplace les deltas. Autre solution : `model_call_ended` porte `segments_tokens` ; il faut en retenir une seule.
- L'arrondi et la réduction proportionnelle sont faits en Python (voir n° 14). Le front ne fait qu'afficher, avec « ≈ » quand `tokens_basis ≠ exact`.

### 2. La forme de `context_rendered` en mode chat n'est pas définie (Haute)

**Emplacement.** AD-4, l. 145 (« leur concaténation est exactement le prompt envoyé. Le front n'a besoin d'aucun décalage de caractères ») et l. 178 (« `context_rendered` le porte tel qu'envoyé »).

**Problème.** En mode chat, la concaténation des segments n'est plus le corps envoyé :
- la syntaxe JSON n'appartient à aucun segment ;
- les segments `tool_catalog` sont des fragments d'un schéma JSON ;
- le segment d'écart `template` n'a aucun texte.

L'invariant de la l. 145 tombe sans être remplacé. On ne sait pas si le corps JSON est un champ distinct (`body`), ni comment le front relie un segment à sa place dans le corps pour la sélection synchronisée (FR-4) et pour le bandeau « ce contexte est le corps JSON envoyé ». Or AD-4 ne dit pas non plus ce que devient la normalisation (étape 2, l. 170) sans vocabulaire : la neutralisation des tokens spéciaux est impossible.

Le story dev devra inventer ce format, et le front de Contexte LLM en dépend.

**Correctif.** Ajouter au mode chat une règle normative, en choisissant l'une des deux options :

- **(a) Segmentation du JSON sérialisé.** Le corps est sérialisé une seule fois, par exemple avec `json.dumps(ensure_ascii=False, separators=(",", ":"))`. Ces octets sont envoyés, tracés et découpés par la même méthode de sentinelles appliquée aux chaînes JSON. La syntaxe JSON devient des segments `template`, et la concaténation reste égale au corps envoyé : l'invariant d'AD-4 est conservé.
- **(b) Champs séparés.** `context_rendered{body, segments}`, avec des segments sans position et une règle de sélection par `id` de message.

Je recommande (a) : elle garde l'invariant et réutilise le code de `render.py`. Dans les deux cas :
- préciser que le segment d'écart « chez le fournisseur » est un segment `template` sans texte, par exception à « un texte vide ne produit pas de segment » (l. 171) ;
- préciser que l'étape 2 en mode chat se limite aux blancs et à la zone privée Unicode.

### 3. Forme des messages au format chat incompatible avec l'historique stocké (Haute)

**Emplacement.** AD-4, Historique, l. 151 (`tool_calls: [{name, arguments}]`) ; mode chat, l. 178 ; AD-25, l. 532 (action forcée rendue comme un appel de l'assistant suivi de sa réponse).

**Problème.** Le format `/chat/completions` exige ceci :
- `tool_calls[].id` et `type: "function"` ;
- `function.arguments` en **chaîne** JSON ;
- une réponse `role: "tool"` qui porte `tool_call_id` et suit un message de l'assistant qui contient cet appel.

L'historique stocké n'a pas d'`id`. Le code actuel le confirme : `app_session.py` l. 1423-1432 réinjecte l'erreur d'un appel mal formé sous la forme d'un message `assistant` sans `tool_calls`, suivi d'un message `tool` avec `name: None`. Un fournisseur refusera cette séquence avec une erreur 400. Le spine ne dit pas non plus :
- ce qu'il advient du `reasoning` des tours précédents : en local, c'est le gabarit qui le décide (l. 151). Au format chat, aucun gabarit du harnais ne s'applique, et certains fournisseurs refusent un champ inconnu ;
- comment fabriquer l'id d'une action forcée (AD-25). Certains fournisseurs imposent un format d'id, à vérifier avec « Tester ».

**Correctif.** Dans AD-4 :
- **Historique.** Les `tool_calls` stockés portent un `id`, généré par la session quand le moteur n'en fournit pas. Il est au format `call_{turn}{n}`, alphanumérique et assez court pour le fournisseur le plus strict déclaré.
- **Mode chat.** L'adaptateur de corps (dans `context`) :
  - sérialise `arguments` en chaîne ;
  - n'envoie pas le `reasoning` de l'historique, sauf capacité déclarée ;
  - rend la réponse à un appel mal formé comme un message `user` ou `tool` apparié à un appel fabriqué. Choisir l'une des deux formes et l'écrire.
- Ajouter ces cas au moteur factice.

### 4. D5 perdue : arguments invalides et « appel d'outil raté » côté fournisseur (Haute)

**Emplacement.** AD-6, l. 218 (« Son parseur d'appels d'outils est le format structuré de l'API ») ; AD-5, l. 202 (« Un code HTTP d'erreur termine l'appel par `stop_reason: error` ») ; AD-14, l. 350 ; AD-10. Source : D5 (proposition l. 81), CAP-16.

**Problème.**
- La phrase de D5, « Des arguments JSON invalides suivent la voie de l'appel mal formé (CAP-16) », n'a atterri nulle part : ni dans le spine, ni dans `invoke_dev_with` de la story 11 (stories.yaml l. 132).
- Plus grave, certains fournisseurs valident l'appel d'outil **côté serveur**. Groq renvoie une erreur 400 `tool_use_failed` avec la génération ratée ; ce point est à vérifier avec « Tester ». Avec la règle de la l. 202, un appel mal formé devient `harness_error` et `turn_ended{status: error}` : ni nouvel essai (AD-10), ni matériau pédagogique (CAP-16).
- Enfin, il n'est dit nulle part qui parse `arguments` : l'adaptateur ou l'exécuteur.

**Correctif.**
- **AD-6, modèle cloud.** Le parseur du mode chat valide `arguments` comme un objet JSON. Un échec produit un `Malformed{fragment, detail_fr}` identique à celui du parseur local. Un nom d'outil inconnu suit AD-14.
- **AD-5.** Un refus du fournisseur identifié comme appel d'outil raté (code et type déclarés par fournisseur, par exemple `tool_use_failed`) n'est pas une erreur : l'adaptateur rend la génération fournie comme sortie `tool_call` mal formée, et la voie AD-10 s'applique.
- Reprendre ces deux points dans `invoke_dev_with`.

### 5. Titres, Prevents et port contredits par leur Rule (Haute)

**Emplacement.** AD-4, titre l. 140 (« rendu par le harnais, tokens attribués exactement ») et Prevents l. 143 (« des totaux qui ne tombent pas juste ») ; AD-5, titre l. 187 (« Le port moteur reçoit du texte déjà rendu, rien de plus »), Prevents l. 190 (« un adaptateur qui envoie des messages de chat ») et signature l. 191.

**Problème.**
- Le Prevents d'AD-5 interdit exactement ce que `openai_chat` fait.
- Le titre d'AD-4 promet un rendu par le harnais et des tokens exacts, alors que le mode chat délègue le rendu et estime.
- La signature `complete(prompt_ids | prompt_text, stop, max_tokens, cancel)` n'accepte ni messages ni outils. Le code réel (`models/engine.py` l. 56-59) n'accepte que `prompt_ids`, et `EngineMetadata` n'a pas de champ `input`.

Un lecteur qui s'en tient aux titres (ce qui arrive en revue de story) conclura que la story 11 viole le spine. Un développeur changera la signature à sa façon.

**Correctif.**
- **AD-4.** Titre : « …rendu par le harnais (ou corps JSON en mode chat), tokens exacts en local, estimés et recalés en mode chat ». Prevents, ajouter : « un contexte cloud présenté comme exact ».
- **AD-5.** Titre : « Le port moteur reçoit un contexte déjà assemblé : texte rendu, ou messages structurés pour le mode chat ». Prevents : « un adaptateur texte qui envoie des messages de chat ou ajoute des tokens ; un adaptateur chat qui modifie les messages reçus ».
- **Signature.** `complete(request: RenderedPrompt | ChatBody, stop, max_tokens, cancel)`, avec `metadata().input: ids|text|chat`. `context` choisit le mode d'après `metadata().input`, et nulle part ailleurs.

### 6. `max_window` borne un appel, pas un tour : 429 quasi systématique au 2e appel (Haute)

**Emplacement.** AD-9, l. 254 (« `max_window` tient compte du quota de tokens par minute du fournisseur ») ; D7 (proposition l. 83). Critère de succès §5 : « un tour Groq ou Mistral fonctionne avec outils ».

**Problème.** Chaque appel renvoie tout le contexte :
- un tour avec outils fait au moins 2 appels en quelques secondes, et jusqu'à 6, plus 4 pour le sous-agent (AD-10, AD-11) ;
- avec gpt-oss-120b à 8 000 tokens/min (recherche, `groq-cerebras-cloudflare-r2-1.md` l. 5), une fenêtre qui fait tenir un appel dans le quota épuise la minute dès le 2e appel ;
- si le fournisseur compte aussi `max_tokens` dans ce quota, ce qui est à vérifier, la marge est encore plus faible.

La règle telle qu'écrite garantit presque un 429 sur le cas même que le §5 exige de réussir. D11 interdit en outre tout nouvel essai automatique.

**Correctif.** Trancher explicitement (décision du porteur), puis l'écrire dans AD-9 :
- **(a)** Déclarer `tpm` dans l'entrée, et poser `max_window = floor(tpm / k) − réserve`, où `k` est un nombre d'appels par minute visé, réglable (par défaut 3).
- **(b)** Avant un appel dont l'estimation dépasse le reste de la minute, la session **attend** de façon visible (« Attente du quota du fournisseur : 22 s »). Ce n'est pas un nouvel essai, c'est un événement, qui reste compatible avec D11.
- **(c)** Assumer le 429 comme matériau pédagogique, et retirer « avec outils » du §5 pour Groq.

Dans tous les cas, `max_window` est une valeur **déclarée** à la main, pas calculée par la session. Il faut le dire, sinon deux implémentations divergent.

### 7. `[[cloud.models]]` sans schéma ni identité ; persistance du choix non fixée (Haute)

**Emplacement.** AD-6, l. 218 ; AD-9, l. 254 (`window`, `max_window`) ; AD-15, l. 386 ; AD-20, l. 455 (`{model_id: key}`) ; AD-21, l. 472-474 (« modèle cloud enregistré ») ; identifiants, l. 540.

**Problème.** La seule structure de configuration nouvelle est citée dans six AD sans être définie. Plusieurs unités en dépendent :
- l'adaptateur a besoin de `base_url`, du nom du modèle chez le fournisseur et de l'en-tête ;
- les capacités ont besoin de `tools`, `reasoning` et `context` ;
- la fenêtre a besoin de `window` et `max_window` ;
- la garde a besoin de l'hôte ;
- l'infobulle et l'avertissement ont besoin du fournisseur, de l'hébergement, de l'usage pour l'entraînement, de l'offre d'essai, de l'URL de la console et de la clause EEE ;
- le schéma a besoin du nom du fournisseur ;
- `api_keys.json` et la persistance ont besoin de `model_id`.

En outre :
- `model_id` n'a pas de format. Les noms de modèle du fournisseur contiennent des `/`, comme `openai/gpt-oss-120b`.
- `selected_model` (story 1b) est un **chemin** : rien ne dit comment un choix cloud y est mémorisé, alors qu'AD-21 l. 474 suppose qu'il l'est.
- Rien n'interdit une clé dans une entrée déclarée dans `settings.json`, ce qui contredit le critère §5 « clé absente de `settings.json` ».
- Une clé par `model_id` impose de saisir deux fois la même clé Groq pour deux modèles Groq.

**Correctif.** Ajouter à AD-6, ou dans un sous-paragraphe d'AD-20 « Déclaration d'un modèle cloud », un modèle pydantic normatif :
```
CloudModel{id: str (snake_case, [a-z0-9_]+, unique), provider: str, provider_label: str, base_url: HttpUrl,
  model: str, auth_header: "authorization_bearer"|"api-key" = "authorization_bearer",
  key_ref: str = provider, capabilities{tools: bool, reasoning: bool, context: int},
  window: int | None, max_window: int, tpm: int | None,
  disclosure{hosting_fr, training: yes|no|opt_out, trial: bool, console_url, eea_clause: bool}}
```
- Préciser qu'**aucun champ de clé** n'est accepté (entrée refusée avec `harness_error`).
- Déclarer `api_keys.json` sous la forme `{key_ref: key}`.
- Mémoriser le choix dans `selected_model = "cloud:{id}"`. Ajouter `cloud:{id}` à la table des identifiants.

### 8. Fusion `wavestack.toml` / `settings.json` : les ajouts effacent les préréglages (Moyenne)

**Emplacement.** Conventions, l. 543 (« Défauts dans `wavestack.toml`, surcharges dans `settings.json`, écrites par la session seule ») ; AD-15, l. 386 (« `settings.json` édité à la main ») ; D3 (proposition l. 79 : « ajouts dans `settings.json` »). Code : `src/wavestack/config.py` l. 37-44.

**Problème.**
- `_deep_merge` fusionne les dictionnaires mais **remplace** les listes. Une liste `cloud.models` ajoutée à `settings.json` pour un point d'accès interne fait disparaître Groq et Mistral, alors que D3 parle d'**ajout**.
- La convention dit que `settings.json` est écrit par la session seule ; AD-15 et D3 supposent qu'il est édité à la main. La session réécrit ce fichier (`selected_model`, `probed_models`) : une édition manuelle pendant qu'elle tourne peut être perdue.

**Correctif.**
- Conventions : « Les listes d'entrées identifiées (`cloud.models`) se fusionnent **par `id`** : une entrée de `settings.json` ajoute ou remplace l'entrée de même `id`, et `enabled = false` la masque. »
- Préciser que `settings.json` peut être édité à la main quand WaveStack est arrêté, et que la session le réécrit par lecture-modification-écriture en conservant les clés inconnues, ce que fait déjà `save_setting`.

### 9. Appel au modèle rangé parmi les sorties « hors brique, `turn_id = null` » (Moyenne)

**Emplacement.** AD-15, l. 387-390 ; AD-2, l. 119 ; EXPERIENCE l. 142.

**Problème.**
- La liste fermée des sorties hors brique impose « chacune tracée avec `turn_id = null` ». L'appel au modèle y est ajouté, alors qu'il a lieu **dans un tour** : son `outbound_request` doit porter `turn_id`, `call_id`, `step_id`, le `component` `core.model` et l'arête `core.harness → core.model`. Sans cela, l'Orchestration ne peut pas le rattacher à l'étape « Appel au modèle ». Seul le test du diagnostic est réellement hors tour.
- AD-2, l. 119, énumère toujours `origin` de la `TraceScope` comme « `brick`, `diagnostic` ou `download` » : `model` y manque, alors que la l. 110 l'ajoute.
- Enfin, rien ne dit qui pose `origin = model` (la session avant l'appel, ou l'adaptateur).

**Correctif.**
- AD-15 : scinder la liste. Les sorties hors brique et hors tour sont la sonde, le téléchargement et le test. L'appel au modèle cloud est une sortie **dans le tour**, tracée avec la portée de l'appel.
- AD-2, l. 119 : ajouter `model`. Préciser que la session pose `origin = model` dans la portée de l'appel au modèle.

### 10. Intentions cloud hors des classes d'AD-3 (Moyenne)

**Emplacement.** AD-3, l. 129-133 ; AD-21, l. 472 ; EXPERIENCE l. 122 (`model-indicator` cliquable vers le diagnostic).

**Problème.**
- AD-3 l. 129 autorise `set_api_key` et `test_cloud_model` dans la session minimale de diagnostic, mais les classes (a), (b) et (c) ne les mentionnent pas. `test_cloud_model` est dit « classe b » dans AD-21 seulement, et `set_api_key` n'a aucune classe.
- Après le démarrage, le `model-indicator` renvoie au diagnostic : on ne sait pas si la session `idle` accepte ces deux intentions, ni ce que fait `select_model` d'un modèle cloud. Selon la story 1b, il est enregistré « pour le prochain lancement ».
- La confirmation de l'avertissement (« à confirmer avant tout appel ») n'a pas de support. On ne sait pas si elle vit seulement dans le front, ou si `select_model` exige `acknowledged: true` pour une entrée cloud.
- À noter, bien que ce soit antérieur au cloud : la story 1b classe `select_model` en (a), alors qu'AD-3 range « changer de modèle » en (b).

**Correctif.** AD-3 :
- **(a)** : `set_api_key` (effet sur `api_keys.json`, pris en compte au prochain appel).
- **(b)** : `test_cloud_model`.
- `select_model` d'une entrée cloud exige `acknowledged: true`. Sinon, la session refuse, avec la raison « avertissement non confirmé ». La confirmation est ainsi vérifiable par un test.
- Aligner la classe de `select_model` entre AD-3 et la story 1b.

### 11. AD-21 : liste cloud sous « échec bloquant », spine non aligné sur la story 1b (Moyenne)

**Emplacement.** AD-21, l. 471-474 ; AD-7, l. 226 (« Une seule fonction de découverte liste les candidats ») ; D1, D10 ; CAP-43 (« jamais chargé d'office »).

**Problème.**
- Les puces cloud sont imbriquées sous « 4. En cas d'échec bloquant, … la page liste les candidats ». Lu à la lettre, un poste qui a un seul GGUF (diagnostic vert, chargement d'office) ne verrait jamais les modèles cloud. La story 1b (faite) a changé la règle : les candidats sont toujours listés, et un choix fait après le chargement est enregistré « pour le prochain lancement ». Le spine ne le dit pas, et D10 (« le changement à chaud reste pour CAP-34 ») n'y figure pas explicitement.
- « Un modèle cloud n'est jamais chargé d'office » (l. 473) coexiste avec « un modèle cloud **enregistré** » (l. 474), rechargé au lancement suivant sans nouvel avertissement (EXPERIENCE l. 147 : « pas à chaque lancement »). Ce n'est pas faux, mais « d'office » doit être défini : c'est-à-dire sans choix explicite préalable.
- AD-7 n'est pas amendé. On ne sait pas si les entrées cloud sortent de la fonction unique de découverte (`source: cloud`, sans sonde) ou si le diagnostic les ajoute à la liste.

**Correctif.**
- Sortir les puces cloud de l'étape 4 : « Le diagnostic liste toujours les candidats (AD-7) et les modèles cloud déclarés. Un choix fait après le chargement est enregistré pour le prochain lancement (pas de changement à chaud avant CAP-34). »
- Définir « d'office » : sans choix explicite enregistré.
- AD-7 : « La fonction de découverte ajoute les entrées `cloud.models` comme candidats `source = cloud`, sans sonde. »

### 12. Test d'un modèle cloud sous-spécifié ; « avant tout appel » contredit le parcours (Moyenne)

**Emplacement.** AD-21, l. 472 ; D12 (proposition l. 88) ; CAP-43 (SPEC l. 154) ; EXPERIENCE (état « Test d'un modèle cloud »).

**Problème.**
- D12 fixe un appel minimal **en streaming, avec un outil**, qui affiche la réponse, l'appel d'outil reçu et le débit. Le spine ne garde que « bouton Tester, classe b, `origin = model` ». On ne sait pas :
  - quel prompt et quel outil sont envoyés (contenu en français, donc `content/` selon AD-19) ;
  - quel événement porte le résultat : `diagnostic_check{check: "cloud_test:{id}"}` ? des `model_call_*` avec `turn_id = null` ?
  - quels champs sont portés : AD-1 interdit au front de calculer le débit.
- **Contradiction.** CAP-43 dit « le choisir affiche un avertissement…, à confirmer **avant tout appel** ». Or le parcours de CAP-43 lui-même et celui d'EXPERIENCE placent « Tester » **avant** « Choisir ». Le test est un appel, et il part donc sans confirmation.

**Correctif.**
- AD-21 : « Le test envoie le prompt et l'outil fixes de `content/diagnostic/cloud_test.yaml`, en streaming. Il émet les `model_call_*` (`turn_id = null`) puis `diagnostic_check{check: cloud_test, model_id, status, message_fr, reply, tool_call_received, output_tps, prompt_tokens}`. Son `usage` initialise l'écart du n° 14. »
- CAP-43 (et FR-43) : reformuler en « à confirmer avant tout appel qui porte le contexte de l'utilisateur ; le test n'envoie qu'un prompt fixe, affiché ».

### 13. Raisonnement du modèle cloud : aucune correspondance avec la brique (Moyenne)

**Emplacement.** AD-6, l. 214 (« sa variable de raisonnement ») et l. 218 ; AD-9, l. 255 (réserve de 512, ou 1 536 avec raisonnement).

**Problème.**
- En local, la brique raisonnement agit par `enable_thinking`. En cloud, la capacité `reasoning` est déclarée, mais rien ne dit quel paramètre de requête la brique pilote (`reasoning_effort`, `reasoning_format`, un modèle distinct, ou rien).
- Certains modèles (gpt-oss) raisonnent toujours. Brique éteinte, la réserve de 512 tokens peut être consommée par le raisonnement : `stop_reason = length`, `output_truncated`, puis `turn_ended{status: limit}` (AD-9). Le tour échoue sans que la cause soit claire pour la salle.
- « Une capacité non déclarée est absente » ne dit pas quoi faire des deltas `reasoning` reçus d'un modèle qui ne l'a pas déclarée.

**Correctif.** AD-6, modèle cloud :
- l'entrée déclare `reasoning{param, on, off, always}`. La brique applique `on` ou `off` ;
- si `always = true`, la réserve est celle du raisonnement (1 536), brique éteinte comprise, et la brique « raisonnement » apparaît « toujours active pour ce modèle », avec sa raison ;
- les deltas `reasoning` sont toujours affichés dans leur canal.

### 14. Règle d'estimation incomplète (Moyenne)

**Emplacement.** AD-4, l. 179-181.

**Problème.**
- « octets UTF-8 / `chars_per_token` » : le nom dit caractères, le calcul utilise des octets. En français, les accents font diverger les deux d'environ 5 à 10 %. Deux implémentations choisiront différemment.
- L'arrondi n'est pas fixé : « réduites en proportion » et « la somme reste égale au total » exigent une méthode déterministe (plus forts restes). Le moteur factice ne peut pas vérifier une égalité sans elle.
- « l'écart du dernier appel » : on ne sait pas s'il est pris par contexte (`main` ou `sub{n}`, dont les outils diffèrent), par modèle, ni ce qu'il vaut au premier appel. À 0, le premier contrôle de dépassement sous-estime (syntaxe JSON, gabarit du fournisseur), et un appel trop long part quand même. Le fournisseur le refuse alors en 400 au lieu du `context_overflow` pédagogique.

**Correctif.** AD-4 :
- renommer `bytes_per_token` (ou compter en caractères) ;
- arrondi par plus forts restes, en Python ;
- l'écart est mémorisé par `(model_id, context_id)` pour la session ;
- sa valeur initiale est celle du test (n° 12), sinon un forfait déclaré (`template_overhead`, par défaut 5 % de l'estimation).

### 15. Clé : journaux, `settings.json`, erreurs et effets non couverts (Moyenne)

**Emplacement.** AD-15, l. 390 et 396 ; AD-20, l. 449-455 ; AD-23, l. 495-501 ; conventions « Journalisation », l. 545. Sources : D8 (« ni dans la trace, **ni les journaux**, ni les réponses de l'API locale ») ; §5 (« absente de la trace, de `settings.json`, des journaux et de `/api/*` »).

**Problème.**
- Le spine couvre la trace (« aucun en-tête n'est tracé ») et l'API (« le front ne reçoit que `key_set` »). Il ne couvre pas le `logging` console : un `DEBUG` httpx ou httpcore, ou un `repr` de requête dans une exception, peut exposer la clé. Il ne couvre pas non plus les messages d'erreur (`harness_error.cause` construit à partir d'une exception) ni `settings.json` (voir n° 7).
- AD-20 l. 451 impose que la session écrive « par les effets (AD-23) », mais l'union d'AD-23 est fermée et n'a pas d'effet pour `api_keys.json`, ni pour `settings.json`. Si un effet `ApiKeySet{key}` est ajouté, `effect_applied` risque de tracer la clé.

**Correctif.**
- AD-15 : « Aucune clé dans un événement, un message d'erreur, une ligne de `logging` ni `settings.json`. L'en-tête d'authentification est posé par l'adaptateur sur la requête, jamais sur le client partagé. Les loggers `httpx` et `httpcore` restent au niveau `WARNING`. »
- AD-23 : ajouter `ApiKeySet{key_ref}`. La valeur passe hors de l'effet, et `effect_applied` ne porte que `key_ref`. Sinon, déclarer `api_keys.json` et `settings.json` comme exceptions écrites directement par la session.
- Un test pytest cherche une clé factice dans le journal, les journaux capturés, `settings.json` et toutes les réponses `/api/*`. C'est déjà un critère du §5, mais il n'est pas dans le spine.

### 16. Texte propre au fournisseur et données du modèle actif sans source (Moyenne)

**Emplacement.** AD-19, l. 439 (« Tout contenu pédagogique est un fichier en français sous `content/` ») ; AD-1, l. 77 ; D15 (« la partie propre au fournisseur vient de sa déclaration ») ; EXPERIENCE l. 122, 146, 147.

**Problème.**
- L'infobulle et l'avertissement combinent un texte commun (`content/`) et des éléments propres au fournisseur. Si ces éléments sont des phrases en français dans `wavestack.toml`, AD-19 est contourné sans être amendé.
- AD-1 exige que toute donnée affichée vienne d'un événement ou d'une lecture de l'API. Or le `model-indicator` (fournisseur, étiquette RÉSEAU, infobulle) n'a ni champ dans `/api/state` ni événement désigné.

**Correctif.**
- AD-19 : les éléments propres au fournisseur sont **structurés** (`disclosure{…}` du n° 7 : énumérations, booléens, un seul champ libre `hosting_fr`), et les phrases sont dans `content/cloud/*.yaml`.
- AD-1 ou AD-12 : `/api/state` et `session_state` portent `active_model{id, label, hosting, provider_label, disclosure}`, construit par la session.

### 17. Libellé « (estimé) » perdu et « ≈ » incohérent (Basse)

**Emplacement.** AD-4, l. 180 et 183 ; D6 (proposition l. 82) ; CAP-31 (SPEC l. 117) ; AD-4, l. 148 (`user_message` et `template` forment « Message et gabarit »).

**Problème.**
- D6 fixe le libellé « Gabarit appliqué chez le fournisseur **(estimé)** ». Le spine et EXPERIENCE (l. 182) ont perdu « (estimé) ». Or ce segment contient aussi l'erreur d'estimation : sans ce mot, il enseigne une chose fausse.
- D6 dit « **tout** est affiché avec ≈ ». CAP-31 dit « la ventilation par segment est ≈, **le total vient de l'API** » : le total n'est donc pas estimé.
- En mode chat, `template` ne peut pas être regroupé avec `user_message` sous « Message et gabarit » dans la jauge sans perdre le libellé propre.

**Correctif.**
- Reprendre le libellé de D6, dans `content/` (clé `template_provider`).
- Aligner D6 sur CAP-31 : « ≈ » partout, sauf pour le total quand `usage_source = api`.
- Préciser le regroupement de jauge en mode chat.

### 18. `output_tps` sans formule ; `usage_source: estimate` flou ; compteur sans débit (Basse)

**Emplacement.** AD-2, l. 116 ; EXPERIENCE l. 138 ; CAP-31 (débit pour chaque appel) ; D14.

**Problème.**
- « débit calculé par la session » ne dit pas si le débit se mesure depuis le premier token ou depuis l'envoi. Le test (n° 12) et le compteur afficheront des débits différents pour le même appel, alors que la comparaison local et cloud est le cœur de D14.
- `usage_source: estimate` : quand le fournisseur ne renvoie pas `usage`, le spine ne dit pas comment `output_tokens` est estimé.
- Le composant `token-counter` d'EXPERIENCE (l. 138) n'a pas été amendé : seul l'état « Modèle cloud actif » affiche le débit, alors que CAP-31 le demande pour chaque appel, local compris.

**Correctif.**
- AD-2 : `output_tps = output_tokens / (gen_ms / 1000)`, où `gen_ms` court de `model_first_token` à la fin, arrondi à l'unité.
- `estimate` s'applique aux deux compteurs, avec la même règle que le n° 14.
- Amender `token-counter`.

### 19. Liste des refus du fournisseur incomplète (Basse)

**Emplacement.** AD-16, l. 404.

**Problème.** La liste (429, 401 ou 403, 404, délai dépassé) omet :
- 413 : certains fournisseurs signalent ainsi une requête plus grosse que le quota par minute (Groq, à vérifier) ;
- 400 « contexte trop long » ;
- 5xx ;
- `NetworkBlocked` et l'échec DNS (pas de réseau en salle).

Le délai conseillé et la portée du quota (minute ou jour), qu'affiche la carte d'EXPERIENCE, ne sont pas des champs structurés.

**Correctif.** Ajouter « tout autre code : cause générique avec le code HTTP et le message du fournisseur cité ». Donner à `harness_error` les champs `http_status`, `retry_after_s` et `quota_scope: minute|day|unknown`, construits en Python.

### 20. Annulation et testabilité de l'adaptateur (Basse)

**Emplacement.** AD-24, l. 513 ; conventions « Qualité », l. 546 ; §5 (« un 429 simulé par le moteur factice »).

**Problème.**
- Le `CancelToken` est testé « à chaque fragment ». Pendant l'attente du premier fragment (file d'attente du fournisseur), l'arrêt ne fait rien avant le délai de lecture. AD-24 ne le signale que pour llama.cpp.
- Le moteur factice rejoue des sorties : il teste la session, pas la traduction HTTP → `harness_error` de l'adaptateur. La garde interdit le réseau en test, et le spine ne dit pas comment tester `openai_chat` sans nouvelle dépendance.

**Correctif.**
- AD-24 : étendre la mention « arrêt demandé jusqu'au premier fragment » au mode chat, ou fermer la réponse depuis la boucle.
- Conventions : « `openai_chat` se teste avec `httpx.MockTransport` injecté par la fabrique `net` (SSE, `usage`, 429, `tool_use_failed`, arguments invalides). »

### 21. `openai_chat` vers la boucle locale ; forme d'URL Azure (Basse)

**Emplacement.** Non-objectif SPEC l. 183 (« pointer l'adaptateur chat vers un serveur local reste possible par configuration ») ; AD-8, l. 247 ; AD-12, l. 315 ; AD-5, l. 198-200.

**Problème.**
- Une entrée `[[cloud.models]]` dont la `base_url` est `127.0.0.1` serait traitée en « cloud » : coût mémoire nul (AD-8), zone Réseau (AD-12), avertissement cloud. Tout cela est faux.
- `POST {base_url}/chat/completions` et l'en-tête `api-key` ne conviennent qu'au point d'accès Azure « v1 ». Le format classique exige `?api-version=`.

**Correctif.**
- Soit refuser la boucle locale dans `cloud.models` en V1 (cohérent avec « sans être visé »), soit dériver `hosting` et le coût mémoire de l'hôte.
- Ajouter `query: dict` optionnel à l'entrée, ou écrire « point d'accès Azure v1 seulement ».

### 22. Traçabilité et documents voisins (Basse)

- **Binds.** Aucun `Binds` d'AD n'inclut FR-43 (AD-4 l. 142, AD-5 l. 189, AD-6 l. 208, AD-9 l. 251, AD-15 l. 361, AD-16 l. 400, AD-20 l. 446, AD-21 l. 459). FR-43 n'est relié au spine que par le frontmatter et la carte.
- **Carte, l. 680.** La ligne FR-43 omet AD-2 (événements), AD-3 (intentions), AD-8, AD-12 (schéma) et AD-16 (refus), pourtant amendés pour elle.
- **AD-12, l. 315.** Seule l'arête `core.harness → core.model` est dite `crosses_boundary`. Celle vers `core.model_sub` doit l'être aussi.
- **Companion.** `architecture-view.html` ne contient aucune mention de cloud ni d'`openai_chat` (0 occurrence). Il est listé dans `companions` et n'est plus à jour.
- **Arborescence, l. 647 et 656.** Les commentaires de `wavestack.toml` (`[[cloud.models]]`) et de `models/` (adaptateur `openai_chat`, `api_keys`) ne sont pas mis à jour.
- **EXPERIENCE l. 157.** L'état « Aucun tour » place le nœud Modèle « dans la zone Poste de travail ». Avec un modèle cloud actif, il est en zone Réseau (EXPERIENCE l. 182, AD-12).
- **AD-13 et AD-14.** Il faut écrire que H5 (validation avant sortie réseau) ne s'applique pas à l'appel au modèle : l'avertissement confirmé au choix en tient lieu. Sinon, un développeur de hooks posera la question, ou l'ajoutera.
- **README (AD-21, l. 466).** La clé API et le test avant chaque séance (D12) ne figurent pas dans la liste de ce que documente le README.

---

## Réconciliation

### Décisions D1 à D15

| # | Atterrissage | Où | Écart |
|---|---|---|---|
| D1 Option explicite, jamais un défaut | Partiel | AD-21 l. 473 | « d'office » non défini face au choix mémorisé (n° 11) ; « scénarios jouables sans clé » absent du spine (présent dans NFR-4) |
| D2 Adaptateur `openai_chat` unique, `net`, sans SDK | Fidèle | AD-5 l. 198-202, AD-15 | « pas de SDK OpenAI » n'est qu'implicite (règle « seul `net` crée des clients ») ; analyse SSE manuelle non dite |
| D3 Déclaration toml et `settings.json`, en-tête configurable | Partiel | AD-5 l. 200, AD-15 l. 386 | schéma absent (n° 7) ; « ajouts » cassés par la fusion (n° 8) |
| D4 Préréglages Groq et Mistral, exemples commentés | Hors spine | story 11 | normal pour un spine ; ne dépend que du schéma (n° 7) |
| D5 Capacités déclarées ; arguments invalides → voie mal formée | Partiel | AD-6 l. 218 | **la seconde moitié est perdue** (n° 4) |
| D6 Estimation, total API, écart en `template`, « ≈ », pas de nouveau `SegmentKind` | Partiel | AD-4 l. 177-183 | libellé « (estimé) » perdu ; événement de la ventilation corrigée absent (n° 1, 17) |
| D7 Fenêtre effective avec `max_window`, surcharge par modèle | Fidèle, insuffisant | AD-9 l. 254 | quota par tour non traité (n° 6) ; priorité entre `window` et le réglage de l'interface non dite |
| D8 Troisième sortie, `origin = model`, corps exact, clé jamais tracée | Partiel | AD-2 l. 110, AD-15 l. 390 | `turn_id = null` contradictoire (n° 9) ; « journaux » absents (n° 15) |
| D9 Clé saisie au diagnostic, `api_keys.json`, envoyée au seul hôte déclaré | Fidèle | AD-20 l. 449-455, AD-15 l. 396, AD-21 l. 472 | effet d'écriture absent (n° 15) ; clé par modèle (n° 7) |
| D10 Choix au diagnostic, pas de changement à chaud | Partiel | AD-21 l. 472 | imbriqué sous « échec bloquant » ; « à chaud = CAP-34 » non écrit (n° 11) |
| D11 429 expliqué, pas de nouvel essai ; 401, 404, délai | Fidèle | AD-16 l. 404, AD-5 l. 202 | 403 ajouté (bien) ; liste non fermée (n° 19) |
| D12 Tester : streaming, un outil, réponse, appel d'outil, débit ; README | Partiel | AD-21 l. 472 | contenu, événement et README absents (n° 12, 22) |
| D13 Modèle dessiné comme service réseau, avec son fournisseur | Fidèle | AD-12 l. 315, schéma l. 596, 609 | arête du sous-agent (n° 22) |
| D14 NFR-1 local seulement ; premier token, durée, débit affichés | Partiel | AD-2 l. 116 (`output_tps`) | formule absente (n° 18) |
| D15 Avertissement à confirmer ; indicateur, infobulle, bandeau | Partiel | AD-21 l. 472 (renvoi à `cloud-warning`) | confirmation non vérifiable (n° 10) ; données de l'indicateur et du texte fournisseur sans source (n° 16) |

### Amendements prévus au §4.4

| Amendement | Statut | Remarque |
|---|---|---|
| Frontmatter (`binds` + FR-43, `updated`) | Fait | l. 10-11 |
| AD-2 `origin … \| model` | Partiel | l. 110 fait ; l. 119 (`TraceScope`) oublié (n° 9) |
| AD-2 `output_tps`, `usage_source` | Fait | l. 116 |
| AD-4 mode chat | Fait mot pour mot | comporte les trous des n° 1, 2, 3 et 14 ; titre non amendé (n° 5) |
| AD-5 `openai_chat` | Fait | titre, Prevents et signature non amendés (n° 5) |
| AD-6 capacités déclarées | Fait | D5 incomplète (n° 4) |
| AD-8 coût nul | Fait | l. 247 |
| AD-9 `max_window`, `window` | Fait | n° 6 |
| AD-12 nœuds fixes en `network_service` | Fait | l. 315 |
| AD-15 sortie `origin = model`, liste d'adresses, redirection | Fait | n° 9 (`turn_id`) |
| AD-16 refus du fournisseur | Fait | l. 404 |
| AD-20 `api_keys.json` | Fait | l. 449, 455 |
| AD-21 liste, clé, Tester, jamais d'office, enregistré inutilisable | Fait, plus le renvoi à `cloud-warning` | placement (n° 11) |
| Schéma des processus (`llmcloud`) | Fait | l. 596, 609 |
| Carte FR-43 | Fait tel que prévu | incomplète (n° 22) |
| Reports V2 et GCP Vertex | Fait | l. 710-711 |
| (hors §4.4) AD-3 intentions du diagnostic | Ajouté | classes absentes (n° 10) |

### CAP-43 et exigences voisines

| Exigence | Spine | Remarque |
|---|---|---|
| Choix au diagnostic d'un modèle déclaré | AD-21 | n° 11 |
| Préréglages Groq et Mistral, point d'accès ajouté | AD-15 l. 386 (implicite) | n° 7, 8 |
| Saisie de la clé | AD-3, AD-20, AD-21 | n° 10 |
| « le teste » | AD-21 | n° 12 |
| « mêmes tours qu'en local » | AD-4, AD-5 | n° 2, 3, 4 et 6 menacent ce point |
| Pictogramme réseau et infobulle (hébergement, entraînement, essai, console) | aucun | UX seulement ; données sans source (n° 16) |
| Avertissement à confirmer **avant tout appel** | AD-21 (renvoi) | pas vérifiable ; contradiction avec le test (n° 10, 12) |
| Barre haute qui signale un modèle réseau | aucun | n° 16 |
| « Tester » prouve streaming **et appel d'outils** | non | n° 12 |
| Chaque appel tracé comme donnée sortante, clé jamais tracée | AD-15 | n° 9, 15 |
| Refus (429, clé refusée) expliqué, jamais un plantage | AD-16 | n° 19 |
| Jamais chargé d'office | AD-21 | n° 11 |
| CAP-3 : modèle dessiné comme service réseau, avec son fournisseur | AD-12 | fidèle |
| CAP-31 : débit ; ventilation ≈ ; total API ; **sans recalcul côté front** | AD-2, AD-4 | **n° 1** (le point « sans recalcul » n'est pas tenu), 17 et 18 |
| CAP-35 : capacités déclarées | AD-6 | fidèle |
| NFR-1, NFR-2 | AD-2, AD-8 | fidèles |
| NFR-4 : trois sorties ; clé seulement vers l'hôte déclaré | AD-15 | n° 9 |
| NFR-11 : clés hors dépôt ; point d'accès interne dans `settings.json` | AD-20 | n° 8 (fusion) ; la clé dans `settings.json` n'est pas interdite (n° 7) |
| Non-objectif « chat vers serveur local possible, non visé » | Deferred l. 710 | n° 21 |

### Composants et états UX cloud

| Élément d'EXPERIENCE | Soutien dans le spine | Remarque |
|---|---|---|
| `cloud-model-row` : étiquette, fournisseur, infobulle, clé masquée « Stockée sur ce poste, jamais affichée ni tracée », boutons désactivés sans clé avec la raison | `key_set` (AD-20), intentions (AD-3, AD-21) | champs d'infobulle sans schéma (n° 7, 16) ; raison « désactivé sans clé » : texte de `content/`, à dire |
| `cloud-warning` : dans la page, trois points, « Utiliser ce modèle » ou « Annuler », à chaque nouveau choix, texte commun dans `content/` | renvoi AD-21 | confirmation non vérifiable côté session (n° 10) ; AD-19 non amendé (n° 16) |
| `model-indicator` : « RÉSEAU · {fournisseur} », infobulle, clic vers le diagnostic | aucun | n° 16 ; intentions après démarrage (n° 10) |
| Bandeau de Contexte LLM | aucun | dépend de la forme de `context_rendered` (n° 2) |
| `outbound-payload` pour un appel cloud (adresse, taille, corps dans Contexte LLM) | AD-15 | rattachement à l'étape impossible avec `turn_id = null` (n° 9) |
| `model-picker` : cloud avec CAP-34 | cohérent avec D10 | le spine ne l'écrit pas (n° 11) |
| État « Modèle cloud actif » (jauge ≈, segment gabarit, débit) | AD-4, AD-2 | n° 1, 17 et 18 |
| État « Test d'un modèle cloud » (réponse, appel d'outil reçu, débit) | non | n° 12 |
| État « 429 » (délai conseillé, pistes, aucun nouvel essai) | AD-16 | n° 19 |
| État « Clé refusée ou absente » (401) | AD-16 (401 ou 403), AD-21 (inutilisable) | fidèle |
| `token-counter` avec débit | AD-2 | composant non amendé (n° 18) |

### AD non amendés : fallait-il les amender ?

| AD | Verdict |
|---|---|
| AD-1 | Oui, indirectement : la ventilation corrigée et `active_model` doivent avoir une source (n° 1, 16) |
| AD-3 (classes) | Oui (n° 10) |
| AD-7 | Oui, une phrase : entrées cloud comme candidats `source = cloud`, sans sonde (n° 11) |
| AD-10 | Non. Les bornes s'appliquent telles quelles ; leur interaction avec le quota relève d'AD-9 (n° 6) |
| AD-11 | Non, hors `crosses_boundary` pour `core.model_sub` (n° 22) et le quota (n° 6) |
| AD-13 | Une phrase : H5 ne couvre pas l'appel au modèle (n° 22) |
| AD-14 | Oui, pour D5 (n° 4) |
| AD-17 | Non |
| AD-19 | Oui (n° 16) |
| AD-23 | Oui, ou exception explicite (n° 15) |
| AD-24 | Une phrase sur l'annulation avant le premier fragment (n° 20) |
| Table des identifiants | Oui : `model_id` et `cloud:{id}` (n° 7) |

## Contradictions entre documents

1. CAP-43 et FR-43, « à confirmer avant tout appel », contre le parcours « clé, test, puis choix » (CAP-43 intent, EXPERIENCE). Voir n° 12.
2. D6, « tout est affiché avec ≈ », contre CAP-31, « le total vient de l'API ». Voir n° 17.
3. D6, libellé « … (estimé) », contre le spine l. 180 et EXPERIENCE l. 182, qui l'omettent. Voir n° 17.
4. AD-2 l. 110 (`origin` avec `model`) contre AD-2 l. 119 (sans `model`). Voir n° 9.
5. AD-15 l. 387 (« hors brique, `turn_id = null` ») contre un appel au modèle qui a lieu dans le tour, et contre EXPERIENCE l. 142. Voir n° 9.
6. Titres et Prevents d'AD-4 et d'AD-5 contre leur Rule. Voir n° 5.
7. Conventions l. 543 (« `settings.json` écrit par la session seule ») contre AD-15 l. 386 et D3 (édité à la main). Voir n° 8.
8. D1 et CAP-43, « jamais chargé d'office », contre la story 1b, dont le choix enregistré est chargé d'office au lancement suivant. Voir n° 11.
9. AD-3, « changer de modèle » en classe (b), contre la story 1b, `select_model` en classe (a). Écart antérieur au cloud, voir n° 10.
10. EXPERIENCE l. 157 (Modèle en zone Poste dans « Aucun tour ») contre l. 182 et AD-12. Voir n° 22.
11. CAP-31 (débit pour chaque appel) contre EXPERIENCE l. 138 (`token-counter` sans débit). Voir n° 18.
12. §5, « clé absente de `settings.json` et des journaux », contre le spine, qui ne l'impose pas. Voir n° 15.

## Ordre de correction suggéré

1. Constats n° 1, 2, 3 et 5 : une seule passe sur AD-4 et AD-5 (mode chat : forme, événement, messages, titres et port).
2. Constats n° 4 et 6 : D5 et le quota par tour. Le n° 6 demande une décision du porteur.
3. Constats n° 7, 8 et 16 : un seul schéma `CloudModel`, une règle de fusion et la source des données affichées.
4. Constats n° 9 à 15 : ajustements locaux dans AD-2, AD-3, AD-15, AD-20, AD-21, AD-23 et CAP-43.
5. Constats n° 17 à 22 : hygiène, puis mise à jour de `architecture-view.html` et d'`invoke_dev_with` (story 11).
