---
title: Revue adverse de la passe « Update » cloud (FR-43) du spine WaveStack
target: ../ARCHITECTURE-SPINE.md
scope: "Passe Update du 2026-09-24 (C1–C3, H4–H9, M10–M15, L16–L17) : AD-2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 15, 16, 19, 20, 21, 23, 24, 25 et conventions"
lens: "Deux unités conformes à la lettre de chaque AD, qui se construisent pourtant de façon incompatible (forme de données, propriétaire, chemin de mutation, fuite de secret)"
date: 2026-09-24
previous: review-cloud-adversary.md (P1–P13)
sources:
  - ../ARCHITECTURE-SPINE.md (état du 2026-09-24, 20:40)
  - ../.memlog.md (entrées C1 à L17)
  - src/wavestack/trace/scope.py, net/factory.py, tools/network.py, session/diagnostic.py, session/effects.py, config.py (code livré, pour les points d'ancrage)
---

# Revue adverse : passe « Update » des amendements cloud

## Verdict

La passe ferme sur le fond les trois critiques de la revue précédente (port `Engine`, `tool_call_id`, clé liée à l'hôte) et la plupart des majeurs. Elle en ouvre pourtant de nouveaux, surtout dans les mécanismes qu'elle vient d'inventer :
- le **ratio d'estimation** appris sur l'invite minuscule de « Tester » peut bloquer tous les tours en dépassement, sans jamais se corriger ;
- un `tool_call_id` « dérivé du `step_id` » entre en **collision** dès que le modèle émet deux appels parallèles ;
- en mode chat, `segment.text` a **deux sens** (fragment JSON échappé ou texte d'origine) ;
- `context_reconciled` ne porte ni la **ventilation par type** ni `near_limit`, que la jauge doit donc recalculer.

Deux contradictions entre AD apparaissent aussi : AD-8 (« le sélectionner libère le modèle local ») contre AD-21 (« vaut pour le prochain lancement ») ; AD-4 (« chaque identifiant reçoit exactement une réponse d'outil ») contre la voie « appel mal formé » du mode chat.

Échelle (reprise des revues précédentes) : **Critique** = incompatibilité certaine à l'intégration, fuite de secret, ou règle qui échoue en démonstration. **Majeur** = incompatibilité probable, ou défaut visible. **Mineur** = ambiguïté qu'une story tranchera, au risque de mal la trancher.

---

## 1. Statut des paires P1 à P13

| # | Statut | Justification | Résidu |
| --- | --- | --- | --- |
| P1 Port `Engine` / deux corps exacts | **Fermée** | Union `RenderedPrompt \| ChatBody`, corps complet construit par `context`, sérialisé une seule fois, égalité testée avec `outbound_request`. Titre et Prevents réécrits. | La brique raisonnement « ajoute au corps » des champs (AD-6) : un second écrivain du corps (N12). Représentation de `body: bytes` dans un événement JSON (N12). |
| P2 `tool_call_id` | **Fermée en principe, rouverte** | Identifiant attribué par la session, format `[A-Za-z0-9]{9}`, historique `{id, name, arguments}`, une réponse par identifiant. | La dérivation depuis le `step_id` crée des collisions sur les appels parallèles (N2). La règle « une réponse par identifiant » contredit la voie « mal formé » du mode chat (N5). |
| P3 Clé vers un autre hôte | **Fermée pour P3a et P3b sur la lettre** | `id` WaveStack unique, `api_keys.json = {id: {host, key}}`, `follow_redirects=False` pour `origin = model`, en-tête posé par requête. Le client httpx livré a `follow_redirects=False` par défaut, donc l'adaptateur est sûr s'il ne le force pas. | Le contrôle d'hôte n'a pas de propriétaire : AD-5 fait lire le fichier par l'adaptateur, et AD-20 rattache le contrôle à `key_set`. « Tester » peut donc envoyer une clé périmée (N7). |
| P4 Clé dans la trace | **Fermée en grande partie** | `SecretStr`, `effect_applied{kind, id, key_set}`, filtre des chaînes du fournisseur, loggers au niveau WARNING, test sentinelle. | Une persistance générique par `model_dump(mode="json")` écrit `**********` dans `api_keys.json` (N8). L'erreur 422 de FastAPI renvoie l'entrée reçue (N13). |
| P5 Classes d'intentions | **Fermée** | Classe (b) « hors `idle` et hors `diagnostic` pour les quatre » ; `set_api_key` en (b) ; `test_cloud_model` tient `model_load`. | `select_model` en diagnostic charge un GGUF sans état de verrou déclaré (Mineur, N11). |
| P6 Avertissement et choix persistant | **Fermée sur la confirmation, rouverte sur l'application** | `acknowledged: true` exigé par la session ; `selected_model = {kind, ref}` ; règle de lancement sans réseau. | AD-8 contre AD-21 sur le moment où le choix s'applique (N6). `kind: file\|cloud` n'a pas de valeur pour un modèle servi, et l'ancien format chaîne n'a pas de migration (N11). |
| P7 Schéma et fusion | **Fermée sur le propriétaire, rouverte sur la fusion** | `CloudModel` unique dans `config`, `extra = "forbid"`, fusion par `id`. | « Remplace l'entrée » et « `enabled = false` masque un préréglage » sont incompatibles avec un modèle aux champs obligatoires (N9). La sémantique de `window` n'est pas fixée (N10). |
| P8 Portée d'`outbound_request` | **Fermée** | `origin = model` dans la portée de l'appel ; `turn_id = null` réservé à la sonde, au téléchargement et au test. | La portée du test (`turn_id`, `call_id` et `step_id` nuls) casse l'appariement et la clé du ratio (N4). `origin` est hérité par `scoped()` (N14). |
| P9 Réconciliation | **Fermée sur l'événement, rouverte sur le contenu** | `context_reconciled` en Python, cas sans `usage` traité, ratio tenu par contexte. | Il manque la ventilation par type, `near_limit` et `overflow` (N3). Le ratio peut se verrouiller (N1). |
| P10 Quota par minute | **Fermée par décision** | `tpm // 2`, 429 assumé et expliqué. | `window` peut contourner le plafond, et `tpm // 2` peut être inférieur à la réserve (N10). |
| P11 Rendu chat de l'historique | **Fermée** | Raisonnement jamais renvoyé, action forcée rendue en injection sans `tools`, liste de marqueurs en chat. | La normalisation (étape 2) touche-t-elle `arguments`, déclaré « jamais re-sérialisé » ? (N5, Mineur.) |
| P12 `model_call_ended` en chat | **Fermée en grande partie** | `prompt_ms`, `gen_ms`, `output_tps` et `raw_output` en JSON Lines définis ; table `finish_reason`. | Le raisonnement caché gonfle le débit (Mineur, N15). « Sortie brute » a deux sens pour la voie « mal formé » (N5). |
| P13 Sous-agent et rejeu | **Fermée, sauf un point** | AD-11 : contexte toujours renvoyé en chat ; les identifiants sont dans l'historique. | Le cas H1 désactivé avec un modèle cloud n'est pas traité (Mineur, non repris). |

---

## 2. Nouvelles paires

### N1 — Le ratio d'estimation, appris sur le test, verrouille la session en dépassement — **Critique**

**Unité A : `session/diagnostic` (test d'un modèle cloud, AD-21).**
- « Tester » envoie une invite fixe et un outil fixe : environ 40 à 80 tokens estimés.
- Le fournisseur y ajoute son gabarit fixe : pour gpt-oss (format harmony), en-tête système, date, bloc d'outils, soit plus de 100 tokens.
- `usage.prompt_tokens / Σ estimations` donne un ratio de 2,5 à 4.
- AD-21 : « Son `usage` initialise le `ratio` d'AD-4 ». Conforme.

**Unité B : `session`, contrôle de dépassement (AD-9) en mode chat (AD-4).**
- Avant l'envoi, total = Σ estimations × ratio.
- Le premier tour réel compte 1 500 tokens estimés (prompt système, catalogue d'outils, message). Avec un ratio de 3, cela donne 4 500, alors que `usable` vaut 4 000 − 1 536 = 2 464 pour Groq gpt-oss-120b.
- Le tour se termine par `context_overflow`, et l'appel n'est pas envoyé. Conforme.

**Où ça casse.**
- Le surcoût du gabarit chez le fournisseur est surtout **fixe**. Un ratio proportionnel appris sur une petite invite le multiplie sur une grande.
- Comme l'appel n'est pas envoyé, aucun `usage` ne revient, et le ratio n'est jamais corrigé. **Tous les tours débordent** jusqu'au redémarrage, et même après, si le test est refait comme le demande le README.
- Le même biais vaut dans l'autre sens : un ratio appris sur un grand contexte sous-estime un petit, sans conséquence grave.
- Aggravant : la clé du ratio `(modèle, context_id)` ne dit pas sous quel `context_id` le test l'enregistre (N4).
- Aggravant : `sub{n}` est numéroté par session, donc chaque délégation a un nouveau `context_id` et **ne réutilise jamais** son ratio. Elle retombe toujours sur `estimate_ratio`.

**AD à resserrer :** AD-4 (Estimation), AD-9 (Dépassement), AD-21 (Test).

**Règle proposée.**
> - Le modèle d'écart est **affine** : `total = Σ estimations × ratio + overhead`. Le test mesure `overhead` avec son premier appel (invite minimale, sans outil) et `ratio` avec le second. Sinon, prendre `estimate_ratio` et `estimate_overhead` de `wavestack.toml`. Le ratio est borné à [0,8 ; 1,5].
> - La clé est `(id du modèle, contexte principal | sous-agent)`, et non `context_id` : tous les `sub{n}` partagent la même.
> - En mode chat, un dépassement calculé sur une **estimation** n'est bloquant que si `Σ estimations` brute (ratio 1, sans overhead) dépasse déjà `usable`. Sinon, l'appel part avec un avertissement « estimation incertaine », et le 400 « contexte dépassé » du fournisseur (AD-16) fait foi. Un test : ratio de 4 venu du test, puis premier tour de 1 500 tokens estimés, et l'appel doit partir.

---

### N2 — `tool_call_id` « dérivé du `step_id` » : collision sur les appels parallèles — **Critique**

**Unité A : `session`, boucle de tour.**
- L'identifiant est attribué « à la création de chaque appel ». Or l'appel naît pendant l'étape de l'appel au modèle : c'est le seul `step_id` qui existe quand `model_call_ended.tool_calls` est émis.
- A dérive donc l'identifiant de ce `step_id`. Deux appels parallèles (gpt-oss sur Groq : `parallel_tool_calls` actif par défaut ; Qwen3.5 en local) reçoivent **le même identifiant**.

**Unité B : exécuteur (AD-14).**
- Il ouvre un `step_id` par exécution d'outil (`tool_started` et `tool_ended`), et il dérive l'identifiant de ce `step_id` d'exécution.
- Mais cette étape n'existe pas encore quand `model_call_ended` doit porter l'identifiant de la session (AD-2 : « l'identifiant d'origine du fournisseur à côté de celui de la session »).

**Où ça casse.**
- Avec A, le message `assistant.tool_calls` contient deux fois le même `id`, et les deux réponses `tool` sont ambiguës. Le fournisseur répond 400, ou pire, associe les deux réponses au premier appel.
- Avec B, `model_call_ended` est émis sans identifiant de la session, ou bien la session réserve des `step_id` d'avance, ce que l'enveloppe ne prévoit pas.
- Même problème dans le test (AD-21) : `step_id = null`, donc l'identifiant est le hachage de `null`, constant.

**AD à resserrer :** AD-4 (Identifiant d'appel d'outil), table des identifiants.

**Règle proposée.**
> `tool_call_id` = les 9 premiers caractères en base 62 du hachage de `"{step_id de l'appel au modèle}#{index de l'appel dans la sortie}"` (index = position dans `tool_calls`, 0 pour une action forcée, qui a son propre `step_id`). Pour le test, `step_id` vaut `diag.{n}.s{k}` (voir N4). L'unicité par tour est vérifiée par la session, avec un `harness_error` en cas de collision. Test : deux appels parallèles, puis deux identifiants distincts et deux réponses `tool` appariées.

---

### N3 — `context_reconciled` n'a ni ventilation par type, ni `near_limit`, ni `overflow` — **Majeur**

**Unité A : `session`.** Elle émet `context_reconciled{call_id, segments: [{id, tokens}], used, percent, usage_source}`, champ pour champ (AD-2, AD-4).

**Unité B : jauge du front (AD-1, AD-9).**
- La jauge empile par `SegmentKind`, et `context_rendered` lui donne « la ventilation par type de segment ». `near_limit` (seuil 0,8 défini dans `wavestack.toml`) et `overflow` viennent aussi de la session.
- Après la réconciliation, B n'a que des tokens par `id`. Pour empiler, il doit **additionner par type**, ce qu'interdit AD-4 (« le front n'additionne ni ne répartit rien »). Pour la couleur de la jauge, il doit comparer `percent` au seuil, ce qui est un recalcul interdit par AD-1.
- Ou bien il garde la ventilation de `context_rendered`, désormais périmée.

**Où ça casse.** Selon la lecture, la jauge est fausse après chaque appel cloud, ou le front recalcule avec son propre arrondi. Par exemple, un « ≈ 79 % » réconcilié à 82 % reste vert.

**AD à resserrer :** AD-2 (catalogue), AD-4 (Après l'appel), AD-9 (Calcul côté session).

**Règle proposée.**
> `context_reconciled` porte **les mêmes champs de jauge que `context_rendered`** : `window`, `reserve`, `usable`, `used`, `percent`, `near_limit`, `overflow`, la ventilation par type, et `segments [{id, tokens}]`. Tous sont calculés par la session. Une seule fonction Python `gauge(segments, window, reserve)` produit ces champs pour `context_rendered`, `context_preview` et `context_reconciled`.

---

### N4 — Portée du test d'un modèle cloud : `call_id` et `step_id` nuls, appariement et ratio impossibles — **Majeur**

**Unité A : `session/diagnostic`.** Elle suit AD-2 : hors portée, `turn_id`, `context_id`, `call_id` et `step_id` valent `null`. Le test émet `model_call_started`, `model_delta` et `model_call_ended` avec `step_id = null`.

**Unité B : magasin de projection et `session`.**
- Les paires `*_started` / `*_ended` s'apparient par `step_id` (AD-2). Les deltas se regroupent par `call_id`.
- Deux tests successifs, ou les deux appels d'un même test, se mélangent.
- Le ratio est tenu par `(modèle, context_id)`, et le test l'initialise avec `context_id = null` : il est rangé sous une clé que `main` ne lit jamais, ou bien une story choisit d'initialiser toutes les clés.

**Où ça casse.** Le volet « sortie brute » du test affiche des deltas mélangés, et l'initialisation du ratio (AD-21) est sans effet ou arbitraire. Le hachage d'un `step_id` nul donne un `tool_call_id` constant (N2).

**AD à resserrer :** AD-2 (enveloppe), AD-21 (Test), table des identifiants.

**Règle proposée.**
> Le test a sa propre portée : `turn_id = null`, `context_id = diag`, `call_id = diag.{n}.c{k}`, `step_id = diag.{n}.s{k}`, où `n` est numéroté par processus. Le ratio et l'overhead qu'il mesure sont rangés sous la clé du contexte principal du modèle testé (N1). Ajouter `diag` à la table des identifiants.

---

### N5 — « Une réponse par identifiant » contre la voie « mal formé » du mode chat ; « sortie brute » à deux sens — **Majeur**

**Unité A : `session` (AD-4, Identifiant d'appel d'outil).**
- Le fournisseur renvoie un `tool_call` structuré, dont les `arguments` ne sont pas du JSON valide. C'est un appel issu de la sortie du modèle, donc la session lui attribue un identifiant.
- « Chaque identifiant reçoit exactement une réponse d'outil, quelle que soit l'issue. » A envoie donc `assistant.tool_calls` (avec les arguments invalides) suivi d'une réponse `tool` d'erreur.

**Unité B : `context/chat_body` (AD-4, Emplacements propres au mode chat).**
- « Un appel mal formé part en message `assistant` dont `content` est la sortie brute, suivi d'un message `user` qui porte l'erreur. » Il n'y a ni `tool_calls` ni réponse `tool`.
- Et la « sortie brute » en chat est, selon AD-2, `raw_output` : la suite JSON Lines des deltas `choices[0].delta`. B met donc du JSON Lines de deltas SSE dans le `content` de l'assistant.
- Une unité C reconstruit plutôt `name(arguments)`, ou prend `failed_generation` pour `tool_use_failed` (AD-10).

**Où ça casse.**
- A et B produisent deux corps différents pour le même tour. Le cas mixte (un appel valide et un appel invalide dans la même sortie) ne peut pas satisfaire B : un seul message ne peut pas être à la fois `tool_calls` et `content` brut.
- Certains fournisseurs refusent en 400 des `arguments` invalides dans l'historique (voie A).
- Le texte réinjecté diffère selon la lecture de « sortie brute ».

**AD à resserrer :** AD-4 (Identifiant, Mode chat), AD-10.

**Règle proposée.**
> - Un appel dont les `arguments` sont invalides, ou refusé par `tool_use_failed`, **ne reçoit pas d'identifiant** et n'est pas un appel au sens de l'historique. La règle « une réponse par identifiant » ne vaut que pour les appels valides.
> - Si la sortie contient au moins un appel invalide, toute la sortie suit la voie « mal formé », et aucun des appels n'est exécuté.
> - La « sortie brute » réinjectée en chat est un texte défini : `failed_generation` s'il existe, sinon `content` suivi, pour chaque appel, de `name` et de la chaîne `arguments` telle qu'émise. Jamais `raw_output`.
> - Test : un appel valide et un appel invalide dans la même sortie, puis un seul corps attendu.

---

### N6 — AD-8 (« le sélectionner libère le modèle local ») contre AD-21 (« vaut pour le prochain lancement ») et AD-3 (« prend effet au tour suivant ») — **Majeur**

**Unité A : `models` et `LoadRegistry`.** Elle suit AD-8 : sélectionner un modèle cloud libère le modèle local (`close()`), tout de suite, en `idle`.

**Unité B : `session`.** Elle suit AD-21 : un choix fait après le chargement « vaut pour le prochain lancement ». Elle persiste `selected_model`, et `active_model` reste le modèle local. Une unité C suit AD-3 (« un réglage modifié prend effet au tour suivant ») et bascule au tour suivant, ce qui anticipe CAP-34.

**Où ça casse.** Avec A et B, le moteur local est fermé, mais `active_model` l'annonce toujours : le tour suivant finit en `harness_error`. Avec C, le changement à chaud existe sans CAP-34, sans rechargement du registre (AD-6), sans nouvelle fenêtre, sans nouveau schéma.

**AD à resserrer :** AD-8 (Modèle cloud), AD-3 (Réglages), AD-21.

**Règle proposée.**
> AD-8 : « Quand un modèle cloud devient le **modèle actif** (au lancement), le modèle local n'est pas chargé ». AD-3 : `select_model` hors diagnostic ne change que `selected_model` et prend effet au prochain lancement ; l'interface l'indique (« Prochain lancement : {modèle} »). Seul `select_model` en diagnostic change le modèle actif.

---

### N7 — Qui lit `api_keys.json` et applique le contrôle d'hôte ? « Tester » envoie une clé périmée — **Majeur (secret)**

**Unité A : adaptateur `openai_chat`.** AD-5 : « La clé est lue dans `api_keys.json` (AD-20) et placée, requête par requête, dans l'en-tête ». A lit `keys[id]["key"]` et l'envoie à `base_url`.

**Unité B : `session` et diagnostic.** AD-20 : « Si l'hôte déclaré a changé depuis, la clé est ignorée (`key_set = false`) ». B calcule `key_set` pour l'affichage et pour la règle de lancement (AD-21). Le front désactive « Tester » quand `key_set` est faux.

**Où ça casse.**
- Le contrôle d'hôte n'existe que dans le calcul de `key_set`. Un `test_cloud_model` envoyé par un client local (script, `Origin` correct), ou par un front qui n'a pas désactivé le bouton, fait lire la clé brute par l'adaptateur, puis l'envoie au **nouvel hôte**. C'est le cas qu'AD-20 voulait empêcher : `base_url` modifiée à la main dans `settings.json`.
- « `SecretStr` de bout en bout : intention, effet, adaptateur » contre « lue dans `api_keys.json` requête par requête » : deux sources de la clé en mémoire. Laquelle fait foi après un `set_api_key` ?

**AD à resserrer :** AD-5, AD-15 (Clé), AD-20.

**Règle proposée.**
> Une seule fonction `config.cloud_key(entry: CloudModel) -> SecretStr | None` lit `api_keys.json`. Elle renvoie `None` si l'hôte enregistré diffère de `urlsplit(entry.base_url).hostname`. L'adaptateur, `key_set` et `test_cloud_model` n'ont pas d'autre accès. La session refuse `test_cloud_model` et `select_model` quand elle renvoie `None`, avec la raison. Test : hôte modifié, puis `test_cloud_model` refusé, sans aucune requête vers le nouvel hôte dans `MockTransport`.

---

### N8 — Écrire `api_keys.json` et `settings.json` : un effet `SecretStr` sérialisé en `**********`, et un second chemin d'écriture en diagnostic — **Majeur**

**Paire 1 : `session/effects.py` (applicateur générique) × `ApiKeySet{id, host, key: SecretStr}`.**
- L'applicateur persiste les effets de fichier par un motif commun, `model_dump(mode="json")`, puis écrit le JSON. Pour `SecretStr`, pydantic sérialise `"**********"`.
- `api_keys.json` reçoit la chaîne masquée, et toute clé saisie devient « Clé refusée » (401). La lettre est respectée : la clé n'est jamais sortie en clair.
- Une autre unité appelle `get_secret_value()` dans l'applicateur. Rien ne dit laquelle est attendue.

**Paire 2 : `session/diagnostic.py` (code livré, story 1b) × AD-20 et AD-23.**
- AD-20 : « Seule la session écrit ces fichiers, par les effets ». Or l'union d'AD-23 n'a **aucun effet pour `settings.json`** (`selected_model`, `cloud_warning`, réglages, succès de la sonde d'AD-7).
- La session minimale de diagnostic écrit déjà par `config.save_setting(...)` en direct. Elle écrira `api_keys.json` de la même façon, tandis que la session complète passera par `ApiKeySet`. On a deux chemins de mutation du même fichier.

**AD à resserrer :** AD-23, AD-20.

**Règle proposée.**
> - Ajouter à l'union `SettingWrite{path: list[str], value}` (jamais de secret) ; `settings.json` et la mémorisation de la sonde passent par lui.
> - `ApiKeySet` est appliqué par un chemin dédié, `config.write_api_key(id, host, key.get_secret_value())`, écriture atomique. C'est le seul endroit du code qui appelle `get_secret_value()` pour une écriture ; l'autre est l'en-tête posé par l'adaptateur.
> - La session minimale de diagnostic utilise le même applicateur d'effets que la session complète.
> - Test : `set_api_key("sentinelle")`, puis `api_keys.json` contient la sentinelle, et aucun événement ne la contient.

---

### N9 — Fusion par `id` : « remplace l'entrée » et « `enabled = false` masque » exigent une entrée partielle que `CloudModel` refuse — **Majeur**

**Unité A : `config`.** Chaque entrée de `settings.json` est validée comme `CloudModel` (`extra = "forbid"`, champs obligatoires `base_url`, `model`, etc.), puis **remplace** l'entrée de même `id`, comme le dit AD-20 à la lettre.

**Unité B : le formateur, ou une story de documentation.** Pour masquer Groq, il écrit dans `settings.json` `{"id": "groq_gpt_oss_120b", "enabled": false}` : c'est ce que promet « `enabled = false` masque un préréglage ».

**Où ça casse.**
- L'entrée partielle échoue à la validation. Selon l'unité, toute la configuration échoue (plantage au lancement, sans `harness_error`, puisqu'AD-19 ne couvre que `content/`), ou bien l'entrée est ignorée en silence, et Groq reste visible.
- Si une unité C fusionne champ par champ, une autre entrée de `settings.json` hérite de champs du préréglage qu'elle croyait remplacer (par exemple `tpm`, `stream_usage`).
- La convention « la session réécrit `settings.json` en gardant les clés inconnues » s'oppose à `extra = "forbid"` dans les entrées : une clé retirée du schéma, ou une faute de frappe, rend l'entrée invalide pour toujours.

**AD à resserrer :** AD-20 (Fusion), conventions (Configuration).

**Règle proposée.**
> La fusion se fait **champ par champ, par `id`**, sur les dictionnaires bruts. La validation `CloudModel` s'applique au résultat fusionné. Une entrée de `settings.json` sans équivalent dans `wavestack.toml` doit être complète. Une entrée fusionnée invalide est écartée avec un `diagnostic_check` d'avertissement (raison en français, champ en cause), sans jamais bloquer le lancement.

---

### N10 — `window` « surcharge » la fenêtre : dans le `min` ou à sa place ? Et `tpm // 2` inférieur à la réserve — **Majeur**

**Unité A : `context/window`.** `window` remplace le terme « fenêtre configurée » dans `min(configurée, native, serveur, tpm // 2)`, et reste donc plafonnée par `tpm // 2`.

**Unité B : `session`, `config`.** « Un modèle cloud peut la surcharger (`window`), et l'interface affiche alors la source » : B remplace la fenêtre **effective**. Un préréglage Groq avec `window = 8000` contourne `tpm // 2`, et on retrouve le 429 au second appel qu'H8 avait fermé.

**Où ça casse aussi.**
- Avec `tpm = 2000` (quota d'essai), `tpm // 2 = 1000` est inférieur à la réserve de 1 536 (`reasoning.always` de gpt-oss). On obtient `usable < 0`, et chaque appel déborde, sans raison compréhensible.
- AD-9 : changer la fenêtre « recharge le modèle (classe b) ». Pour un modèle cloud, il n'y a rien à recharger : une unité passe par `model_load` et le `LoadRegistry`, une autre applique la fenêtre directement.
- Avec `window` déclaré, le réglage de l'interface est sans effet.
- La promesse « un tour à deux appels tient dans la minute » ignore le tour précédent, les nouveaux essais (AD-10) et la délégation. C'est assumé (« au-delà, 429 »), mais le texte du 429 doit le dire.

**AD à resserrer :** AD-9.

**Règle proposée.**
> - Fenêtre effective = `min(window ?? configurée, context, tpm // 2)` pour un modèle cloud. `window` ne remplace que la valeur configurée, et la source affichée est le terme retenu par le `min`.
> - Au chargement de la configuration, `tpm // 2 ≤ réserve maximale` rend l'entrée indisponible, avec la raison.
> - Pour un modèle cloud, un changement de fenêtre ne recharge rien. Il prend effet au tour suivant, et le réglage de l'interface est désactivé si `window` est déclaré, avec la raison.

---

### N11 — `selected_model = {kind: file|cloud, ref}` : pas de valeur pour un modèle servi, pas de migration de la chaîne livrée — **Mineur**

- **Unité A : story 1b (code livré).** Elle écrit `selected_model = "C:\\…\\model.gguf"` (une chaîne), et `_usable(candidates, saved)` compare des chemins.
- **Unité B : `config` (AD-20).** Elle valide `{kind, ref}`. Sur un poste déjà installé, la chaîne est invalide : plantage au lancement ou choix perdu, selon l'unité.
- **Modèle servi.** AD-7 découvre des serveurs lancés (Ollama, llama-server), et AD-5 a leurs adaptateurs, mais `kind` n'a pas de valeur `server`. Une unité enregistre un modèle Ollama en `file` (chemin du blob, chargé en processus), une autre invente `server`.
- **Verrou.** `select_model` en diagnostic charge un GGUF (plusieurs secondes) sans état de verrou déclaré, alors que `download_model` et `test_cloud_model` en ont un.

**AD à resserrer :** AD-20, AD-3.

**Règle proposée.**
> `selected_model = {kind: file|server|cloud, ref}` ; une chaîne héritée est lue comme `{kind: file, ref}`. `select_model` en diagnostic tient `model_load` (raison « Chargement de {modèle} »).

---

### N12 — Le corps chat a deux écrivains et une forme ambiguë — **Mineur**

- **Unité A : brique raisonnement (AD-6).** « La brique raisonnement ajoute au corps les paramètres `reasoning.on` ou `reasoning.off` ». Une brique ne renvoie pourtant que des contributions (segments, outils) et des effets (paradigme, AD-12) : A invente une contribution « champ de corps ».
- **Unité B : `context` (AD-4).** « `context` construit le corps complet », et lit lui-même `reasoning.on` et `reasoning.off` dans l'entrée, selon l'état de la brique.

Selon l'unité, les champs sont ajoutés deux fois (collision de clé JSON) ou jamais.

- **Représentation.** `ChatBody{body: bytes}` et `context_rendered.body` : un événement pydantic en JSON ne transporte pas des `bytes` bruts. Une unité les encode en base64, une autre les décode en UTF-8 (comme `net/factory.py`, qui fait `decode("utf-8", "replace")`). Le test d'égalité « octet pour octet » compare alors deux représentations différentes.

**Règle proposée.**
> `context` est le seul à écrire le corps. Il lit l'état effectif de la brique raisonnement et l'entrée cloud. Dans les événements, le corps est une chaîne UTF-8 (le corps est de l'UTF-8 valide par construction). L'égalité se teste sur `body.decode("utf-8")`.

---

### N13 — `SecretStr` et l'erreur 422 de FastAPI : l'intention renvoie ce qu'elle a reçu — **Mineur (secret)**

- **Unité A : `web`.** Elle déclare `SetApiKeyIntent{id, key: SecretStr}` et laisse la validation à FastAPI.
- **Unité B : front, ou script.** Il envoie une intention incomplète : `id` manquant ou faute de frappe dans un champ.

**Où ça casse.** Le gestionnaire par défaut de `RequestValidationError` renvoie `detail[].input`. Pour une erreur `missing`, l'entrée est **l'objet entier, clé en clair comprise**. AD-15 promet qu'« une réponse d'intention ne renvoie jamais ce qu'elle a reçu ». La clé ne part que vers le navigateur qui l'a envoyée, mais le test sentinelle, s'il ne couvre que le cas nominal, ne le voit pas.

**Règle proposée.**
> `web` installe un gestionnaire de `RequestValidationError` qui renvoie un message français, avec `loc` et `type`, **sans `input`**, pour toutes les intentions. Le test sentinelle couvre aussi une intention `set_api_key` invalide.

---

### N14 — `origin = model` hérité par les étapes filles — **Mineur**

- **Unité A : `session`.** Elle pose `origin = model` « dans la portée de chaque appel au modèle » par `scoped(origin="model", …)`. Comme le code livré `scoped()` dérive de la portée courante (`replace(current(), …)`), une story qui exécute les outils **à l'intérieur** de la portée de l'appel (analyse en flux, exécution dès qu'un appel est complet) hérite de `origin = model`.
- **Unité B : `net`.** Pour `origin = model`, elle applique `follow_redirects=False` et compte la sortie comme « données envoyées au modèle ». `fetch_page` échoue alors sur toute redirection, et le décompte FR-22 range les sorties des briques sous le modèle.

AD-2 dit que `trigger` est hérité de l'étape parente. Rien ne dit qu'`origin` ne l'est pas.

**Règle proposée.**
> `origin` n'est jamais hérité : l'exécuteur (AD-14) pose `origin = brick` à chaque exécution d'outil, et `net` refuse `origin = model` hors d'une étape `model_call_*`, avec un `harness_error`.

---

### N15 — Résidus sans nouvelle incompatibilité — **Mineur**

- **Liste d'adresses autorisées.** Elle contient « l'hôte de chaque entrée `[[cloud.models]]` **active** ». Une unité lit « active » comme `enabled`, une autre comme « le modèle choisi ». Avec la seconde lecture, « Tester » un modèle non choisi lève `NetworkBlocked`. Règle : toute entrée `enabled`.
- **Découpage par sentinelles d'un JSON échappé.** En chat, un texte de segment qui contient `"`, `\` ou un saut de ligne apparaît échappé dans le corps (`\"`, `\n`). Comme la concaténation doit redonner le corps (AD-4), `segment.text` est le fragment **échappé**, alors que l'estimation porte sur « le texte d'origine ». Les `arguments` et les résultats JSON sont doublement échappés. Le schéma de `Segment` n'a pas de champ pour le texte d'origine : une unité l'ajoute, une autre déséchappe côté front (recalcul), une troisième estime sur le texte échappé. La compression (`compressed_from.text_before`) hérite du même doute. Par ailleurs, « la syntaxe JSON donne des segments `template` à 0 token » ne dit rien des morceaux `template` qui sont **dans** une chaîne : les séparateurs entre `hook_injection`, `rag_excerpt` et `user_message`, concaténés dans un seul `content`, sont tokenisés par le fournisseur. Règle : ajouter à `Segment` le champ `display_text?`, présent en chat seulement et égal au texte d'origine, affiché par le front et base de l'estimation. `text` reste le fragment du corps. Un `template` situé dans une chaîne JSON est estimé comme un segment ; seul un `template` hors chaîne vaut 0. *Sévérité relevée à **Majeur** si le volet Contexte LLM affiche `text` : tout message à plusieurs lignes y apparaît avec des `\n` littéraux.*
- **Débit en cloud.** Un raisonnement caché par le fournisseur (compté dans `completion_tokens` mais non streamé) raccourcit `gen_ms` et gonfle `output_tps`. Reprendre la proposition de P12 : afficher `completion_tokens − tokens vus` comme « raisonnement non transmis », et calculer le débit sur les tokens vus.
- **Normalisation et `arguments`.** L'étape 2 (blancs, zone privée Unicode, marqueurs) s'applique « à chaque texte de segment ». Appliquée à la chaîne `arguments`, elle contredit « jamais re-sérialisée ». Règle : `arguments` n'est pas normalisée ; seul le résultat de l'outil l'est.
- **H1 désactivé avec un modèle cloud (P13).** Toujours non traité ; mention à ajouter dans l'avertissement, ou refus par le chargeur de scénarios.

---

## Synthèse

| # | Paire | Sévérité | AD à resserrer |
| --- | --- | --- | --- |
| N1 | Ratio proportionnel appris sur le test : dépassement permanent, jamais corrigé ; `sub{n}` sans ratio | Critique | AD-4, AD-9, AD-21 |
| N2 | `tool_call_id` dérivé du `step_id` de l'appel : collision sur appels parallèles | Critique | AD-4, identifiants |
| N3 | `context_reconciled` sans ventilation par type, `near_limit` ni `overflow` : front forcé de recalculer | Majeur | AD-2, AD-4, AD-9 |
| N4 | Test cloud : `call_id` et `step_id` nuls, appariement et clé du ratio impossibles | Majeur | AD-2, AD-21, identifiants |
| N5 | « Une réponse par identifiant » contre voie « mal formé » ; « sortie brute » = `raw_output` JSON Lines ? | Majeur | AD-4, AD-10 |
| N6 | AD-8 libère le modèle local à la sélection, AD-21 applique au prochain lancement, AD-3 au tour suivant | Majeur | AD-3, AD-8, AD-21 |
| N7 | Adaptateur lit `api_keys.json` sans contrôle d'hôte : « Tester » envoie une clé périmée au nouvel hôte | Majeur (secret) | AD-5, AD-15, AD-20 |
| N8 | `SecretStr` sérialisé en `**********` dans `api_keys.json` ; aucun effet pour `settings.json`, second chemin d'écriture en diagnostic | Majeur | AD-20, AD-23 |
| N9 | Fusion par `id` : entrée partielle (`enabled = false`) refusée par `CloudModel` | Majeur | AD-20, conventions |
| N10 | `window` dans ou hors du `min` ; `tpm // 2` < réserve ; fenêtre cloud « rechargée » | Majeur | AD-9 |
| N11 | `selected_model` sans `server`, chaîne livrée sans migration ; `select_model` sans état de verrou | Mineur | AD-20, AD-3 |
| N12 | Deux écrivains du corps (brique raisonnement, `context`) ; `bytes` dans un événement | Mineur | AD-4, AD-6 |
| N13 | 422 FastAPI qui renvoie la clé reçue | Mineur (secret) | AD-15, AD-18 |
| N14 | `origin = model` hérité par `scoped()` | Mineur | AD-2, AD-14 |
| N15 | Allowlist « active », JSON échappé dans `segment.text`, débit cloud, normalisation d'`arguments`, H1 et cloud | Mineur (un point potentiellement Majeur) | AD-4, AD-15 |

**Priorité avant la story 11 :** N1 et N2, qui font échouer la démonstration ; puis N7 et N8, qui touchent au secret et au propriétaire des fichiers ; puis N3, N5 et N6, trois contrats de données que la story ne peut pas trancher seule sans créer une seconde convention.
