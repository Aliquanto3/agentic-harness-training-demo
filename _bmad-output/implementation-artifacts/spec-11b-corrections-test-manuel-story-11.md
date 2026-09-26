---
title: 'Story 11b — clé par variable d''environnement, page ouverte au lancement, écarts du test manuel de la story 11'
type: 'bugfix'
created: '2026-09-26'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '248c2d82ea2c3215c938c10016e4f28e89073454'
context:
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/11-modeles-cloud-via-api-groq-mistral.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Trois défauts sont apparus au test manuel de la story 11 sur le PC cible.
- La clé cloud ne peut venir que d'une saisie au diagnostic. Elle ne peut pas venir de l'environnement du poste.
- Chaque lancement ouvre la page de diagnostic, même quand tout est prêt.
- En mode chat :
  - le scénario « MCP lazy loading » échoue sur trois appels refusés par Groq (`tool_use_failed`), car un outil documenté dans le tour n'entre pas dans `tools` ;
  - les refus du fournisseur perdent son message exact ;
  - Mistral gratuit renvoie un 429 dès que deux appels se suivent à moins d'une seconde ;
  - un choix fait une fois le modèle chargé ne donne aucun retour visible.

**Approach:** Quatre corrections.
- **Clé** : ajouter à la déclaration `CloudModel` un champ `key_env`, lu en repli par `config.cloud_key`.
- **Lancement** : choisir la page ouverte selon le résultat du diagnostic et un indicateur de premier lancement.
- **Mode chat** :
  - rendre les outils documentés du tour dans `tools` ;
  - faire suivre le message du fournisseur, masqué, dans la réinjection et dans chaque refus affiché ;
  - espacer d'un délai déclaré (`min_interval_s`) les appels au même modèle.
- **Diagnostic** : afficher un message persistant tant que le choix enregistré attend une relance.

## Boundaries & Constraints

**Always:**
- **Clé (`key_env`).**
  - Le champ facultatif de `CloudModel` contient un nom de variable (`^[A-Z_][A-Z0-9_]*$`), jamais une valeur.
  - `config.cloud_key(entry)` reste le seul lecteur. Il lit d'abord `api_keys.json` (clé valide pour l'hôte). Sinon, il lit `os.environ[key_env]` après `strip()`, et une valeur vide compte comme absente. Il renvoie un `SecretStr`.
  - `config.cloud_key_source(entry) → "file" | "env" | None` sert l'affichage.
  - Au diagnostic, la ligne indique « Clé fournie par la variable X » (nom de la variable seulement) quand `key_source = env`. La saisie reste possible, et une clé saisie passe avant la variable.
  - La valeur ne va jamais dans le journal, les logs, `settings.json`, `/api/*` ni une intention. Le masque d'AD-15 s'applique à la clé lue dans l'environnement comme à celle du fichier.
- **Page ouverte au lancement.**
  - Premier lancement, repéré par l'absence de la clé `diagnostic_shown` dans `settings.json` : `/diagnostic` s'ouvre au bout d'1 s, comme aujourd'hui. `diagnostic_shown = true` est écrit par l'effet `SettingWrite` ; un échec d'écriture est ignoré.
  - Lancements suivants : le navigateur s'ouvre quand `session.run()` rend son résultat, et au plus tôt 1 s après le démarrage. Il s'ouvre sur `/` si `ready` et sans `blocking_checks`, sinon sur `/diagnostic`.
  - Si le diagnostic n'a pas fini au bout de 30 s, `/diagnostic` s'ouvre.
  - Instance déjà lancée sur le port : `/` si son `GET /api/diagnostic` répond `ready`, sinon `/diagnostic`.
  - Le diagnostic reste accessible par l'indicateur de modèle (déjà là) et par une entrée « Diagnostic » dans le menu de la barre haute.
- **Outils en mode chat.**
  - À chaque appel du tour, le corps chat comprend dans `tools` les outils déjà documentés dans ce tour (`loaded_in_turn`). Ils sortent de `loadable` et du catalogue de `load_tool_doc`.
  - `load_tool_doc` disparaît de `tools` quand plus rien n'est à charger, comme dans `build_turn_state`.
  - Le mode local ne change pas : l'outil n'entre dans `tools` qu'au tour suivant, à cause du préfixe en ajout seul (`test_mcp_lazy.py` reste vert sans modification).
- **Message du fournisseur.**
  - Pour `tool_use_failed`, `ChatEnd` transporte aussi `error.message`, masqué. `failed_generation` reste la sortie brute réinjectée.
  - Le détail devient « le fournisseur a refusé l'appel d'outil : {message} ». Il sert à la fois à `tool_call_malformed.detail_fr` et au texte réinjecté (« Erreur : … Corrige l'appel ou réponds sans outil. »).
  - Tout `ProviderError` dont la réponse porte un message termine `message_fr` par « Message du fournisseur : {message masqué} ». Cela vaut pour 3xx, 413, 429, 400 (contexte ou non), 401/403, 404, 5xx, les statuts inattendus et les erreurs dans le flux.
  - Le message est tronqué à 500 caractères avec « … ». Le délai dépassé et l'échec réseau restent tels quels : ils n'ont pas de message du fournisseur.
- **Espacement (`min_interval_s`).**
  - Champ facultatif de `CloudModel` (`> 0`, `≤ 60`). Le préréglage `mistral` vaut `1`.
  - Deux envois au même `entry.id` (tour ou « Tester », toutes instances d'adaptateur confondues) sont séparés d'au moins `min_interval_s`, compté entre leurs départs.
  - L'attente se fait dans `run_call`, avant `model_call_started` et le chronomètre, donc elle n'entre ni dans `prompt_ms` ni dans `duration_ms`. Elle s'interrompt sur annulation : l'appel finit alors `cancelled`, sans envoi.
  - L'attente n'est jamais déduite des en-têtes `x-ratelimit-*`, et aucun appel n'est réessayé.
- **429 « par seconde ».**
  - `_quota_scope` reconnaît aussi la seconde (`per second`, `/s`, `rps`, `(rps)`) et renvoie `second` ; le `Literal` de `quota_scope` du catalogue l'accepte.
  - Texte du 429 : « quota dépassé par seconde » quand la portée est `second`. Si elle est inconnue : « quota dépassé (par seconde, par minute ou par jour) ».
  - Si l'entrée déclare `min_interval_s`, une piste propose de l'augmenter dans sa déclaration.
- **Choix après chargement.**
  - `select_model` (fichier ou cloud) une fois un modèle chargé renvoie `message_fr = "Choix enregistré : relancez WaveStack pour l'utiliser."`.
  - `/api/diagnostic` porte `next_launch_fr` (le même texte) tant que le choix enregistré diffère du modèle chargé.
  - `diagnostic.html` l'affiche dans un bloc `role="status"` en haut de la page, qui survit au rechargement.
- **Documentation.** README : `key_env` (avec `setx NOM valeur`, sans droits administrateur, puis un nouveau terminal), `min_interval_s`, page ouverte au lancement. Spine : AD-20 (`key_env`), AD-21 (étape 2 du lancement), AD-16 (`second`, `min_interval_s`, message du fournisseur).
- Aucune nouvelle dépendance, aucun test réseau réel.
- Décisions du 2026-09-26 :
  - Les préréglages déclarent `key_env` : `GROQ_API_KEY` pour `groq`, `MISTRAL_API_KEY` pour `mistral`.
  - L'entrée « Diagnostic » est un lien en bas de la liste du menu « Volets ▾ », après un séparateur.
  - Un poste utilisé avant cette story compte comme premier lancement une seule fois, par la seule clé `diagnostic_shown`.
  - La spec est gardée entière malgré ses ~5 000 tokens.

**Never:** changement de modèle à chaud (CAP-34) ; espacement ou nouvel essai déduits de `x-ratelimit-*` ; valeur de clé dans `wavestack.toml`, `settings.json` ou une réponse ; modification du rendu local ou du préfixe en ajout seul ; nouvel événement de catalogue.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu |
|---|---|---|
| Clé par variable | pas d'`api_keys.json`, `GROQ_API_KEY` posée | `key_set = true`, `key_source = env`, « Clé fournie par la variable GROQ_API_KEY » ; Tester et Choisir actifs ; valeur absente du journal et de `/api/diagnostic` |
| Fichier et variable | les deux présents | la clé du fichier est envoyée |
| Variable vide | `GROQ_API_KEY="  "` | comme sans clé : boutons désactivés avec la raison |
| Hôte changé et variable | clé du fichier pour un autre hôte, variable posée | la clé de la variable est utilisée, sans « Clé à ressaisir » |
| Lancement prêt | `diagnostic_shown` présent, diagnostic `ready` | `webbrowser.open(".../")` une fois, après le résultat |
| Premier lancement | pas de `diagnostic_shown` | `/diagnostic` ouvert, `diagnostic_shown = true` écrit |
| Lancement bloqué | deux GGUF, aucun choix | `/diagnostic` |
| Lazy loading en chat | `load_tool_doc(local__list_terms)` puis appel de l'outil | le 2ᵉ corps a `local__list_terms` dans `tools` ; l'outil s'exécute ; aucun `tool_call_malformed` |
| `tool_use_failed` | `error.message` et `failed_generation` | `detail_fr` et texte réinjecté contiennent `error.message`, masqué ; la sortie brute = `failed_generation` |
| Refus 401 | corps `{"error":{"message":"Invalid API Key"}}` | `message_fr` se termine par « Message du fournisseur : Invalid API Key » |
| Mistral, deux appels rapprochés | `min_interval_s = 1` | le 2ᵉ envoi part ≥ 1 s après le 1ᵉʳ ; `prompt_ms` sans l'attente |
| Annulation pendant l'attente | arrêt demandé | appel `cancelled`, aucun envoi |
| 429 par seconde | « Requests rate limit exceeded per second » | `quota_scope = second`, texte « par seconde » |
| Choix après chargement | GGUF chargé, choix cloud confirmé | message « Choix enregistré : relancez WaveStack pour l'utiliser. », visible après rechargement de la page |

</frozen-after-approval>

## Code Map

- `src/wavestack/config.py`
  - `CloudModel` 86-105 : ajouter `key_env: str | None` (motif) et `min_interval_s: float | None` (`gt=0`, `le=60`).
  - `cloud_key` 402 : ajouter le repli sur l'environnement ; ajouter `cloud_key_source`.
  - `api_key_host_changed` 410 : inchangé ; le diagnostic ne l'affiche plus quand la variable fournit la clé.
  - `read_settings` 355 : utilisé pour lire `diagnostic_shown`.
- `wavestack.toml` 72-99 : `min_interval_s = 1` dans `mistral` ; `key_env = "GROQ_API_KEY"` et `"MISTRAL_API_KEY"` ; mentionner les deux champs dans le commentaire des exemples.
- `src/wavestack/models/engine.py:25-34` `CancelToken` : ajouter `wait(timeout) → bool`, qui renvoie vrai si l'annulation arrive.
- `src/wavestack/models/openai_chat.py` :
  - `ChatEnd` 50 : ajouter `provider_message: str | None`.
  - `_refused` 206-275 et flux 322-331 : `tool_use_failed` remplit `provider_message = mask(error.message)` ; un suffixe commun « Message du fournisseur : … » (tronqué) pour chaque `ProviderError` ; la 400/422 garde son texte sans doublon.
  - `_quota_scope` 117 : ajouter `second`.
  - Le texte du 429 dépend de la portée ; piste `min_interval_s`.
  - Registre d'espacement au niveau du module : dictionnaire `entry.id → dernier départ` sous verrou, avec `pace(entry, cancel) → bool`.
  - `run_call` 445 : appeler `pace` avant `started` et `model_call_started` (l'adaptateur expose `entry`). Si l'appel est annulé, rendre un `ChatCall` `cancelled` sans appeler `complete`. Lignes 534-535 : le détail cite `end.provider_message`.
- `src/wavestack/trace/catalog.py:48` : ajouter `second` à `quota_scope`.
- `src/wavestack/session/app_session.py`
  - Boucle du tour vers 2091-2112 : en mode chat, `self._render(...)` reçoit l'état complété par `loaded_in_turn`, en réutilisant la règle de `build_turn_state` 1066-1072 (`tools` + outils documentés, `loadable` diminué, `LOAD_TOOL_DOC` retiré si `loadable` est vide). `_render` 1284 et `_render_chat` 1320 ne changent pas.
  - Mode local : garder `state` tel quel.
- `src/wavestack/tools/executor.py:80` `reject` : aucun changement si le texte réinjecté reprend déjà `detail_fr`, sinon l'aligner.
- `src/wavestack/session/diagnostic.py`
  - `_cloud_refusal` 466 : inchangé une fois que `cloud_key` lit la variable.
  - `cloud_rows` 491 : ajouter `key_source` et `key_env`.
  - `_select_model_locked` 396-439 et `select_cloud` 553-564 : texte après chargement.
  - Ajouter `next_launch_fr()`, qui compare `selected_*` et `booted_*`.
  - Ajouter `launch_page(result) → "/" | "/diagnostic"` et `first_launch() → bool`, qui écrit `diagnostic_shown` par `apply_setting(SettingWrite(...))`, comme `_save_choice` 441.
- `src/wavestack/cli.py`
  - Lignes 102-107 : pour l'instance existante, lire `/api/diagnostic` et choisir la page.
  - `_run_diagnostic_then_boot` 89 : signaler le résultat, par exemple par un `threading.Event` et le résultat.
  - `_open_browser` 129-133 : premier lancement, ouverture de `/diagnostic` à 1 s ; sinon, attente du résultat (30 s au plus) puis `launch_page`.
- `src/wavestack/web/app.py:225-264` : `/api/diagnostic` porte `next_launch_fr`, et chaque ligne cloud porte `key_source` et `key_env`.
- `src/wavestack/web/static/diagnostic.html`
  - Lignes cloud 193-218 : ligne « Clé fournie par la variable X » ; placeholder adapté.
  - Ajouter le bloc `#next-launch` près de `#open-link` (42), rempli par `loadDiagnostic` (313).
- `src/wavestack/web/static/app.js` `renderMenu` 2482 (ou `index.html` 22-30) : lien « Diagnostic » en bas de la liste, après un séparateur.
- `README.md` section modèle cloud ; `ARCHITECTURE-SPINE.md` AD-20, AD-21 (ligne 536, étape 2), AD-16.
- Tests à réutiliser :
  - `tests/test_cloud.py` : `Provider`, `sse`, `delta`, `_cloud_session` 80, `_app` 334, `_no_sentinel` 103, `SENTINEL` 25. Adapter `test_tool_use_failed_follows_the_malformed_path` 257, `test_provider_refusals_become_explained_errors` 201 et `test_a_choice_after_a_model_is_loaded_waits_for_the_next_launch` 531.
  - `tests/test_cli_diagnostic.py:485` (« prochain lancement »).
  - `tests/test_cli_launch.py:17` : `/diagnostic` devient `/` si prêt.
  - `tests/test_mcp_lazy.py` : `lazy_session`, `load`, `definition_names`, à reprendre avec `cloud_factory`.
  - `conftest._isolated_data_dir` isole déjà `settings.json` ; utiliser `monkeypatch.setenv` et `delenv` pour les variables.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/config.py`, `wavestack.toml` : `key_env`, `min_interval_s`, repli de `cloud_key`, `cloud_key_source`, préréglages.
- [x] `src/wavestack/models/engine.py`, `src/wavestack/models/openai_chat.py`, `src/wavestack/trace/catalog.py` : `CancelToken.wait`, registre d'espacement dans `run_call`, `provider_message`, suffixe « Message du fournisseur », 429 par seconde.
- [x] `src/wavestack/session/app_session.py` (et `tools/executor.py` si besoin) : `tools` du corps chat complété par `loaded_in_turn`, détail du refus réinjecté.
- [x] `src/wavestack/session/diagnostic.py`, `src/wavestack/web/app.py` : `key_source`, `key_env`, `next_launch_fr`, texte après chargement, `first_launch`, `launch_page`.
- [x] `src/wavestack/cli.py` : page ouverte selon le premier lancement, le résultat et l'instance existante.
- [x] `src/wavestack/web/static/diagnostic.html`, `app.js` / `index.html` : ligne de clé par variable, bloc `#next-launch`, entrée « Diagnostic ».
- [x] `README.md`, `ARCHITECTURE-SPINE.md` : documentation et spine.
- [x] `tests/test_cloud.py`, `tests/test_cli_launch.py`, `tests/test_cli_diagnostic.py` : une ligne de la matrice par test. L'espacement se teste avec un petit `min_interval_s` ou une horloge remplacée. La clé sentinelle, posée en variable d'environnement, est absente du journal et des réponses.

**Acceptance Criteria:**
- Given aucune variable ni clé, when on lance `pytest`, then tout reste vert, en particulier le rendu local de référence et `test_mcp_lazy.py`.
- Given le scénario « MCP lazy loading » avec Groq, when le tour documente puis appelle `local__list_terms`, then aucun appel n'est refusé et la réponse cite le glossaire.
- Given un choix enregistré après chargement, when on recharge `/diagnostic`, then « Choix enregistré : relancez WaveStack pour l'utiliser. » reste affiché.

## Implementation Notes

- Écarts assumés avec la Code Map :
  - Le spine reçoit aussi une phrase dans AD-25 : le lazy loading en mode chat y contredisait « `tools` aux tours suivants ».
  - Deux retouches de cohérence dans AD-3 et AD-9.
- `pace` réserve le créneau sous verrou, attend l'heure réelle (un minuteur Windows peut réveiller quelques ms trop tôt), puis horodate le départ effectif. Sur annulation, il rend le créneau.
- `_quota_scope` : `/s` ne compte que seul, pour que le lien `console.groq.com/settings` ne déclenche pas la portée « seconde ». Ordre des tests : minute, seconde, jour.
- La `cause` du `harness_error` est aussi tronquée à 500 caractères.
- `tools/executor.py` n'a pas changé : le texte réinjecté reprend déjà `detail_fr`.
- Deux fixtures automatiques dans `tests/conftest.py` : l'une retire `GROQ_API_KEY` et `MISTRAL_API_KEY` de l'environnement, l'autre vide le registre d'espacement.
- Les tests d'espacement mesurent le temps réel (0,4 s), avec une tolérance de 20 ms côté fournisseur.
- `EXPERIENCE.md` (l. 152) cite encore l'ancien « Prochain lancement : {modèle} » : il n'est pas dans le périmètre de la spec.
- Vérification : `ruff check` et `ruff format --check` propres ; `node --check` OK ; `pytest` : 368 passés, 2 désélectionnés, comme avant la story.

## Spec Change Log

## Review Triage Log

Itération 0 (trois couches : aveugle B, cas limites E, trous de vérification V).

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| B1 / E7 | `first_launch` écrase un `settings.json` illisible | medium | `read_settings` rend `{}` sur `JSONDecodeError` ; `save_setting` réécrit alors `{"diagnostic_shown": true}` au lancement, sans geste de l'utilisateur | patch |
| E1 | `/api/diagnostic` bloqué pendant une sonde | medium | `next_launch_fr` prend `self._lock`, tenu par `check_model` pendant la sonde (jusqu'à 120 s) ; `loadDiagnostic` du premier lancement attend | patch |
| E3 + E2 + B10 | Bannière « relancez » erronée | medium | Déduite de l'état, pas du geste : après un repli au lancement (cloud sans clé, fichier disparu), `selected_*` ≠ `booted_*` pour toujours ; elle s'affiche aussi si `settings.json` n'a pas pu être écrit ; elle compare des chemins bruts | patch |
| B2 / E6 | Instance existante : règle différente de `launch_page` | low | `_existing_instance_ready` lit `ready` seul ; correction directe | patch |
| B5 | `per sec`, `/sec` non reconnus | low | `_SECOND` ; motif à élargir, correction directe | patch |
| B6 | Test de lancement fragile sous Windows | low | `>= 0.4` contre `threading.Timer(0.4)`, qui peut se réveiller tôt | patch |
| B8 | Aucune piste quand `key_env` est déclaré mais la variable absente | low | Piège `setx` du README, fréquent ; une ligne conditionnelle | patch |
| B12 | README muet sur le stockage de `setx` et sur l'IDE à relancer | low | Clé en clair dans `HKCU\Environment` ; les terminaux d'IDE héritent de l'IDE | patch |
| B13 | `ChatEnd` positionnel dans le flux | low | `provider_error` et `provider_message` voisins, de même type | patch |
| E9 | Page HTML d'un proxy collée au message français | low | `_provider_message` rend `response.text` ; proxy d'entreprise plausible sur le PC cible | patch |
| V1 | `_run_diagnostic_then_boot` avec `_Launched` non testé | medium | Supprimer `launched.set` ne casse aucun test | patch |
| V2 | Premier lancement : attente et page non épinglées | medium | Retirer `not first and` passe les tests | patch |
| V3 | `_existing_instance_ready` jamais exécuté | low | Remplacé par un lambda dans le seul test | patch |
| V4 | Message du fournisseur des 400 et 422 non testé | medium | Paramétrage limité à 429/413/401/404/503 | patch |
| V5 | `tool_use_failed` dans le flux non testé | medium | Seul le chemin HTTP 400 est couvert | patch |
| V6 | Créneau rendu après annulation non vérifié | low | Le test ne lit pas `_last_start` | patch |
| V7 | Retrait de `load_tool_doc` en mode chat non testé | low | Le test charge un outil sur deux | patch |
| B3 | Attente d'espacement invisible | low | Nouvel événement exclu par l'intention (Never) ; 1 s pour Mistral | rejeté |
| B4 | Message du fournisseur dans `message_fr` et `cause` | low | Doublon au terminal seulement ; cosmétique | rejeté |
| B7 | `key_env` sans longueur maximale | low | Nom saisi par le formateur ; improbable | rejeté |
| B11 | Marque écrite avant l'ouverture du navigateur | low | Conforme à la spec ; échec de `webbrowser.open` improbable | rejeté |
| B14 | Spec absente du diff | false | Exclue à dessein, transmise à la couche cas limites | rejeté |
| E4 | Choisir le modèle déjà chargé répond « relancez » | low | Bannière masquée dans ce cas ; correctif = branche en plus | rejeté |
| E5 | Chargement échoué après un diagnostic prêt : `/` | false | Conforme à l'intention (« prêt sans blocage ») | rejeté |
| E8 | Avertissements non bloquants invisibles sur `/` | false | Conforme à l'intention | rejeté |
| E10 | Ordre des outils différent de `build_turn_state` | low | Sans effet : pas de contrôle de préfixe en mode chat | rejeté |
| E11 | Ligne non SSE sans suffixe fournisseur | low | Cas rare ; la ligne reste dans `cause` | rejeté |
| V-autre | Front sans test automatique | low | Écart préexistant (stories 5b à 11), pas de banc JS | defer |

## Design Notes

Le registre d'espacement vit dans le module et non dans l'adaptateur, parce que « Tester » crée son propre adaptateur à chaque clic (`diagnostic._cloud_factory`). Le départ est horodaté dans `pace`, juste avant l'envoi. Une valeur de 1 s suffit pour une limite d'une requête par seconde. Une marge éventuelle se déclare dans `min_interval_s`.

La page d'ouverture n'attend le résultat qu'après le premier lancement : au premier lancement, le formateur voit défiler les vérifications, ce qui est l'intention d'AD-21.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run python -m pytest` -- expected: tout passe
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks:**
- PC cible :
  - `setx GROQ_API_KEY …`, nouveau terminal, sans `api_keys.json` pour Groq : la ligne indique la variable, puis Tester.
  - Relancer : l'interface principale s'ouvre directement.
  - Scénario MCP lazy loading avec Groq : aucun refus.
  - Mistral, Tester : deux appels sans 429.
  - Choisir un autre modèle : le message de relance est visible.
