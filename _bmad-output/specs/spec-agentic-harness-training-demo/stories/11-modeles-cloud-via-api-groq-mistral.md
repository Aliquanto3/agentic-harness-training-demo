---
title: 'Modèles cloud via API (Groq, Mistral)'
type: 'feature'
created: '2026-09-25'
status: 'done'
baseline_commit: 'b49f5b1ab3682d5b582737a76df1e7a4b236e0b1'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sur le PC cible, un tour du SLM local prend 20 à 110 s et le modèle suit mal les skills et les outils ; le formateur n'a aucun modèle plus rapide ou plus capable, alors que la démonstration « où vont mes données » gagnerait à montrer un vrai appel hors du poste (CAP-43, FR-43).

**Approach:** Des modèles cloud compatibles OpenAI, déclarés en configuration (préréglages Groq et Mistral, exemples commentés Google, NVIDIA et OpenRouter), se choisissent au diagnostic avec leur clé, un test réel et un avertissement à confirmer. Le tour est le même qu'en local, en « mode chat » : le harnais écrit le corps JSON exact, l'envoie par `net` (sortie tracée, clé jamais tracée), estime les tokens puis les réconcilie avec `usage`, et explique chaque refus du fournisseur.

## Boundaries & Constraints

**Always:**
- Spine du 2026-09-24 : AD-4 (mode chat), AD-5 (`openai_chat`), AD-6, AD-9, AD-15, AD-16, AD-20, AD-21, AD-23. Aucune nouvelle dépendance.
- Déclaration `CloudModel` (AD-20, `extra = "forbid"`, aucun champ de clé) ; `[[cloud.models]]` de `wavestack.toml` et de `settings.json` fusionnent par `id` ; entrée invalide écartée avec un `diagnostic_check` d'avertissement. L'hôte de chaque entrée `enabled` rejoint la liste d'adresses autorisées (garde et `net`).
- Préréglages : `groq` = `openai/gpt-oss-120b`, `https://api.groq.com/openai/v1`, `context` 131 072, `tpm` 8 000 (fenêtre 4 000, `usable` 2 464), `stream_usage`, raisonnement `format = field`, `always = true`, `on = {reasoning_effort = "low"}`, `resend = false` ; `mistral` = `mistral-small-latest` (décision du 2026-09-25), `https://api.mistral.ai/v1`, `context` 131 072, sans `tpm`, `stream_usage = false`, raisonnement `content_blocks`, `on = {reasoning_effort = "high"}`, `off = {reasoning_effort = "none"}`, `training = opt_out`. Mentions (`hosting_fr`, `training`, `trial`, `notes_fr`) tirées de la recherche du 2026-09-24.
- Clé : `config.cloud_key(entry) → SecretStr | None` (seul lecteur, `None` si l'hôte a changé), `config.write_api_key` (seul écrivain, atomique), `api_keys.json` `{id: {host, key}}`. `SecretStr` de l'intention à l'adaptateur ; absente du journal, des logs, de `settings.json`, des réponses `/api/*` et d'intention ; toute chaîne du fournisseur passe par un masque (clé, 4 premiers, 4 derniers caractères). En-tête posé par requête, jamais sur le client partagé.
- Diagnostic : une ligne par modèle cloud déclaré à côté des candidats locaux (tag RÉSEAU, fournisseur, modèle, infobulle des mentions), champ de clé masqué (`set_api_key`), « Tester » (`test_cloud_model` : invite et outil fixes de `content/`, au plus deux appels, portée `diag`, `origin = model`, n'entraîne pas le ratio), « Choisir » qui ouvre l'avertissement `cloud-warning` dans la page puis envoie `select_model{kind: cloud, ref, acknowledged: true}` (refusé sans `acknowledged` ni clé, avec la raison). Boutons désactivés sans clé, avec la raison. Jamais choisi d'office ; choix mémorisé `selected_model = {kind, ref}` (chaîne héritée = `file`) repris au lancement sans avertissement ni requête. Après chargement, le choix vaut pour le prochain lancement.
- `select_model`, `set_api_key`, `test_cloud_model` : classe (b), refusées hors `diagnostic` ou `idle`. Effets `SettingWrite` et `ApiKeySet` (`effect_applied` = `{kind, id, key_set}`), appliqués par un seul applicateur.
- Tour en mode chat : `context` seul écrit le corps (`model`, `messages`, `tools`, `stream`, limite de sortie, `stream_options` si `stream_usage`, paramètres de raisonnement), sérialisé une fois ; `context_rendered.body` = octets envoyés = corps d'`outbound_request`. Segments par sentinelles, `estimated = true`, tokens = `ceil(caractères / chars_per_token)`, syntaxe JSON à 0 ; segment « Gabarit appliqué chez le fournisseur (estimé) » porte l'écart. Avant l'envoi : total = estimations × ratio ; blocage seulement si la somme brute dépasse `usable`, sinon « Estimation incertaine : le fournisseur tranchera ». Après : `context_reconciled` (mêmes champs de jauge) depuis `usage.prompt_tokens`, ratio mis à jour sur les appels réels, borné à [0,8 ; 1,5].
- `tool_call_id` attribué par la session à tout appel d'outil (9 caractères base 62 du hachage de `"{step_id}#{index}"`, unicité vérifiée dans le tour) ; l'identifiant du fournisseur reste dans `model_call_ended`. `arguments` gardé tel qu'émis. Arguments non JSON ou `tool_use_failed` → voie de l'appel mal formé (AD-10), jamais d'exécution partielle.
- Fenêtre cloud = min(`window` ou fenêtre configurée, `context`, `tpm // 2`), `window_source` dans tous les événements de jauge ; entrée indisponible si `tpm // 2 ≤ 1 536`. Réserve 1 536 si `reasoning.always`, sinon 512.
- Issues du fournisseur (AD-16, liste fermée) → `harness_error` français avec cause masquée, pistes, `http_status`, `retry_after_s`, `quota_scope` ; aucun nouvel essai ; `follow_redirects=False`.
- Interface : `active_model{id, label, hosting, provider, disclosure}` dans `session_state` et `/api/state` ; indicateur de modèle dans la barre haute (tag, nom, infobulle = contenu de l'avertissement, clic → diagnostic) ; nœud `core.model` en zone Réseau avec le fournisseur, arête `crosses_boundary` ; bandeau du Contexte LLM et « ≈ » sur toute valeur estimée (total compris sauf `usage_source = api`) ; `output_tps` calculé par la session.
- README : clé, test avant chaque séance, hôtes à autoriser.
- Spec gardée entière malgré ses ~4 500 tokens (décision du 2026-09-25).

**Never:** changement de modèle à chaud (CAP-34) ; brique raisonnement, sous-agent, RAG (non construits) ; renvoi du raisonnement (`resend`) ; action forcée rendue en injection pour une entrée sans `tools` (indisponible, avec la raison) ; GCP Vertex ; nouvel essai ou espacement selon `x-ratelimit-*` ; test réseau réel dans pytest.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu |
|---|---|---|
| Tour Groq avec outil | clé valide, `get_datetime` activé | deux appels ; `tool_call_id` de la session dans le 2ᵉ corps ; `context_reconciled` après chacun ; sommes = `usage.prompt_tokens`. |
| Mistral, blocs | `delta.content` en liste `thinking`/`text` | canaux `reasoning` et `text` séparés ; `usage` du dernier fragment. |
| Choisir sans confirmer | `acknowledged` absent | refus « avertissement non confirmé », rien n'est écrit. |
| Clé d'un hôte changé | `base_url` modifiée depuis la saisie | `key_set = false`, « Clé à ressaisir : l'adresse du fournisseur a changé. » |
| 429 / 413 / 401 / 404 / 5xx | réponse du fournisseur | `harness_error` expliqué, `turn_ended{error}`, application utilisable. |
| 302 | redirection | « redirection refusée », clé non renvoyée. |
| Arguments invalides | `arguments` non JSON | nouvel essai (AD-10), aucun outil exécuté. |
| Lancement mémorisé | `selected_model = {cloud, groq}`, clé | session prête sans avertissement ni requête. |
| Sans clé | aucun `api_keys.json` | Tester et Choisir désactivés avec la raison ; scénarios locaux inchangés. |
| Clé sentinelle | tout le parcours ci-dessus | absente du journal, des logs, de `settings.json`, des réponses. |

</frozen-after-approval>

## Code Map

- `wavestack.toml` -- `[cloud]` (`chars_per_token = 4`, `estimate_ratio = 1.0`, `connect_timeout_s`, `read_timeout_s`, liste de marqueurs à neutraliser) et `[[cloud.models]]` : deux préréglages, trois exemples commentés avec leur avertissement (clause EEE de Google, `trial` NVIDIA, catalogue instable d'OpenRouter).
- `src/wavestack/config.py` -- `CloudModel`, `cloud_models() → (valides, erreurs)` ; fusion par `id` dans `load_config` (146) avant `_deep_merge` (37, qui remplace les listes) ; `allowed_hosts` (68) ajoute les hôtes `enabled` ; `selected_model` (139) → `{kind, ref}` ; `api_keys_path`, `cloud_key`, `write_api_key` (`os.replace`), `cloud_window(entry, configured) → (window, source)`.
- `src/wavestack/trace/scope.py:30` -- `Origin` accepte `model`. `trace/catalog.py` -- `context_reconciled`, champs `body`, `window_source`, `estimated`, `usage_source`, `output_tps`, `active_model`, `http_status`/`retry_after_s`/`quota_scope`.
- `src/wavestack/net/factory.py:55` -- `create_client` accepte un `httpx.Timeout` et passe `follow_redirects=False` explicitement ; le hook trace déjà méthode, URL et corps, sans en-têtes (29-44).
- `src/wavestack/models/openai_chat.py` (nouveau) -- `ChatBody{body: bytes}`, `OpenAIChatEngine(entry, key, transport=None)` : `complete(ChatBody, cancel)` produit des fragments `(channel, text)` et une fin `{stop_reason, tool_calls, usage, raw_output, provider_error}` ; SSE, `usage` / `x_groq.usage`, `reasoning` / `reasoning_content` / blocs, accumulation par `index`, fin (AD-5), `ProviderError` pour la liste d'AD-16, `mask_key`. Le port local (`engine.py:56`) garde sa signature par ids.
- `src/wavestack/context/render.py` -- extraire de `render_context` (210) la préparation par sentinelles et le découpage (étapes 2 à 5) dans une fonction qui prend un rendu `(messages, tools) → str` ; `render_chat_body(...)` s'en sert avec `json.dumps(ensure_ascii=False, separators=(",", ":"))`, puis estime et ajoute le segment « chez le fournisseur ». `distribute(segments, total)` (plus forts restes) sert avant et après l'appel. `segments.py` -- `Segment.estimated`, `Segment.label_fr` facultatif. `window.py` -- `gauge` reçoit `window_source` et la somme brute qui décide du dépassement.
- `src/wavestack/session/app_session.py` :
  - `boot` 740 / `_boot` 744 : `boot_cloud(entry)` crée l'adaptateur (fabrique injectable pour les tests), `Capabilities` déclarées (`tool_call_parser = "openai_chat"` si `tools`), fenêtre et réserve cloud, `_model_name`.
  - `_set_state` 392 : `active_model` ; `_emit_architecture` 459-541 : `core.model` en `network_service` avec le fournisseur (`_CORE_MODEL` 95).
  - `_availability` 879 : raisons d'indisponibilité cloud (outils sans `tools`).
  - `_messages` 1042 / `_step_messages` 953 : `id` des appels et `tool_call_id` des réponses ; en mode chat, réponse d'outil sans `name`, `content` omis si vide, appel mal formé en `assistant` brut + `user` d'erreur.
  - `_render` 1120 / `_emit_preview` 1153 : branche chat. `_turn` 1868-1998 : `context_reconciled`, avertissement d'estimation incertaine, pas de `_check_prefix` en mode chat. Attribution du `tool_call_id` à la création du pas assistant (1940) et des actions forcées (2054-2122).
  - `_call_model` 2398 : branche `_call_model_chat` sous `scoped(origin="model")` ; `output_tps` dans les deux branches ; `ProviderError` → `harness_error` + `_ModelOutput("error")`.
- `src/wavestack/session/effects.py` -- `SettingWrite`, `ApiKeySet` et leur applicateur (écrit par `config`, émet `effect_applied`).
- `src/wavestack/session/diagnostic.py` -- `selected_model` en `{kind, ref}` (`_check_model_locked` 262, `_select_model_locked` 330) ; `set_api_key`, `test_cloud_model` (verrou, état `model_load` « Test de {modèle} », deux appels, `diagnostic_check{check: cloud_test}`) ; `DiagnosticResult.cloud_model` ; avertissement pour une entrée invalide ou un choix mémorisé inutilisable.
- `src/wavestack/cli.py:111-116` et `web/app.py:201-215` -- démarrer `boot_cloud` quand le résultat le demande.
- `src/wavestack/web/app.py` -- `SelectModelIntention{kind, ref, acknowledged}` (30), `SetApiKeyIntention{id, key: SecretStr}`, `TestCloudModelIntention{id}` ; refus 409 si `app_session` n'est pas `idle` ; gestionnaire `RequestValidationError` (`loc`, `type`, message français) ; `/api/diagnostic` liste `cloud_models` avec `key_set`, disponibilité, mentions ; `/api/state` porte `active_model`.
- `content/cloud.yaml` (nouveau) -- texte commun de l'avertissement et de l'infobulle, raison « désactivé sans clé », texte sous « Tester », invite, outil et réponse fixes du test, libellé du bandeau.
- `src/wavestack/web/static/diagnostic.html` -- lignes cloud, champ de clé, Tester, `<dialog>` `cloud-warning`, `select_model` au nouveau format.
- `src/wavestack/web/static/index.html`, `app.js`, `app.css` -- indicateur de modèle (barre haute 12-30) ; `context_reconciled` remplace `turn.context` et `store.gauge` (217-222) ; `renderContext` 1369 : bandeau et « ≈ » ; `renderGauge` 1032 : « ≈ » ; tag `hosting-tag-network` de DESIGN.md.
- Tests : `tests/fake_engine.py` (`booted_session` 85) pour le mode local ; conftest garde réseau en boucle locale seule, donc tout passe par `httpx.MockTransport`.

## Tasks & Acceptance

**Execution:**
- [x] `wavestack.toml`, `content/cloud.yaml` -- préréglages, exemples commentés, textes.
- [x] `src/wavestack/config.py` -- déclaration, fusion, clés, fenêtre, liste autorisée, `selected_model`.
- [x] `src/wavestack/trace/scope.py`, `trace/catalog.py`, `net/factory.py` -- origine `model`, événements, client sans redirection.
- [x] `src/wavestack/models/openai_chat.py` -- adaptateur, erreurs, masque.
- [x] `src/wavestack/context/render.py`, `segments.py`, `window.py` -- corps chat, estimation, répartition, jauge.
- [x] `src/wavestack/session/effects.py`, `diagnostic.py`, `app_session.py`, `cli.py` -- effets, diagnostic cloud, tour en mode chat, `tool_call_id`, `active_model`, schéma.
- [x] `src/wavestack/web/app.py`, `static/diagnostic.html`, `index.html`, `app.js`, `app.css` -- intentions, validation, lignes cloud, avertissement, indicateur, bandeau, « ≈ ».
- [x] `README.md` -- section modèle cloud.
- [x] `tests/test_cloud.py` (nouveau) -- une ligne de la matrice par test, flux SSE Groq et Mistral, corps envoyé = `context_rendered.body` = corps tracé, fusion par `id`, fenêtre, test à deux appels, clé sentinelle (invalide `set_api_key` compris) ; le rendu de référence Qwen3.5 reste identique.

**Acceptance Criteria:**
- Given aucune clé, when on lance les scénarios fournis, then ils se comportent comme avant la story (`pytest` complet vert).
- Given un modèle cloud actif, when la page est rechargée, then l'indicateur, le nœud en zone Réseau et les « ≈ » réapparaissent depuis `/api/state` et le journal (AD-1).
- Given « Tester » réussi, when on lit la ligne, then elle montre la réponse, l'appel d'outil reçu et le débit, et la trace montre deux `outbound_request` `origin = model` sans clé.

## Implementation Notes

## Spec Change Log

## Review Triage Log

Itération 0 (trois couches : aveugle B, cas limites E, trous de vérification V).

| # | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|
| B1 (+V-autre) | `_quota_scope` teste `"day"` avant la minute : « today » du 429 TPM de Groq donne `day` | medium | `openai_chat.py` `_quota_scope`, sous-chaîne `day` testée en premier | patch |
| B2 | `tool_call_id` en double signalé mais réutilisé | low | collision de 9 caractères base 62 sur des entrées distinctes : improbable, garde en plus | rejeté |
| B3 / E1 | `hold` rétablit un état périmé si un démarrage change l'état pendant « Tester » | medium | `app_session.py` `hold`, `finally` sans contrôle ; démarrage du diagnostic concurrent possible | patch |
| B4 | Message de dépassement en mode chat cite le total corrigé alors que la somme brute a bloqué | medium | `_emit_overflow` lit `payload["used"]` ; `overflow` décidé sur `raw_used` ; fenêtre Groq de 2 464 | patch |
| B5 / E13 | `cloud.yaml` invalide : `harness_error` répété à chaque rechargement | low | `@cache` ne garde pas l'exception ; fichier livré, rarement modifié ; correctif = état en plus | rejeté |
| B6 | `finish_reason = "model_length"` de Mistral traité en erreur | medium | absent de `_FINISH` | patch |
| B7 | Appels d'outils parallèles fusionnés si un fournisseur répète le même `index` | maybe-false | dépend du flux réel de Mistral/Groq pour plusieurs appels, non vérifiable sans réseau | defer |
| B8 | Corps stocké plusieurs fois par appel | low | ~16 Ko par corps avec la fenêtre Groq ; champs de jauge identiques exigés | rejeté |
| B9 | Arrêt attend la ligne suivante du flux | low | latence avant premier token < 1 s en pratique ; correctif = mécanisme nouveau | rejeté |
| B10 | Avertissement non modal (`show()`), Échap inopérant, boutons cliquables derrière | low | `diagnostic.html` `warningEl.show()` ; correction directe `showModal()` | patch |
| B11 | Raisons doublement préfixées (« Test refusé : Désactivé : … ») | low | boutons déjà désactivés avec la raison : rarement vu | rejeté |
| B12 | Exemples Google/NVIDIA/OpenRouter en TOML alors que le README dit de les recopier dans `settings.json` | low | README et commentaire de `wavestack.toml` ; correction de doc directe | patch |
| B13 | README muet sur les 2 464 tokens utilisables de Groq et le retour au modèle local | low | README section cloud ; correction de doc directe | patch |
| B14 + V1–V8 | Branches nouvelles sans test : ratio appris et borné, dépassement brut et `uncertain_fr`, action forcée en mode chat, relance CLI cloud, choix cloud après chargement, refus classe (b) occupé, avertissements `cloud` du diagnostic, `context_reconciled` dans `/api/state` | medium | recherches des relecteurs dans `tests/` ; `cli._run_diagnostic_then_boot` non testable en l'état | patch |
| B15 / E14 | `select_model` sans `ref` ni `path` accepté, chemin vide sondé | low | `SelectModelIntention` a tout facultatif ; correction directe (422) | patch |
| B15b / E15 | `selected_model{kind: server}` ignoré sans avis | low | aucun écrivain de `server` ; édition manuelle seulement | rejeté |
| B16a | Code Map de la spec en décalage | — | correctif = modifier la spec | rejeté |
| B16b / E12 | `write_api_key` sans verrou, fichier corrompu écrasé | low | intentions sérialisées par le front (`busy`) ; fichier corrompu improbable | rejeté |
| E2 | Test cloud : 1ᵉʳ appel coupé (`length`) avec appels → `KeyError` sur `call["id"]` | medium | `diagnostic.py` `test_cloud_model` ; `run_call` n'attribue d'id que sur `stop` | patch |
| E3 | Exception autre que `ProviderError` : `model_call_started` jamais terminé | low | `run_call` n'attrape que `ProviderError` ; correction directe du type | patch |
| E4 / E16 | `DecodingError` et autres échecs sans explication française | low | rares ; le tour se termine en erreur générique | rejeté |
| E5 | `index` à `None` mêlé d'entiers : `TypeError` au tri | low | flux non conforme, jamais observé | rejeté |
| E6 | `arguments` en objet JSON | low | Groq et Mistral envoient une chaîne en flux | rejeté |
| E7 | Clé collée avec caractères non ASCII | low | `strip()` retire les espaces Unicode ; reste improbable | rejeté |
| E8 | Clé très courte : masque trop large | low | clés réelles longues | rejeté |
| E9 | Texte, raisonnement, arguments et `raw_output` du fournisseur non masqués | low | la spec exige le masque sur toute chaîne du fournisseur ; correction directe dans `_read` | patch |
| E10 | Historique en mode chat : réponse vide sans `tool_calls` → 400 possible chez Mistral | maybe-false | dépend d'un tour terminé sans texte et du refus réel de Mistral | defer |
| E11 | `window` ou `context` ≤ réserve : `usable` ≤ 0 mais modèle choisissable | low | déclaration manuelle aberrante | rejeté |

## Design Notes

Le rendu par sentinelles ne dépend pas de Jinja : il suffit d'un rendu `(messages, tools) → str` appelé deux fois. `json.dumps(ensure_ascii=False)` laisse les caractères de la zone privée tels quels, et échappe de la même façon le texte simple et le texte marqué, donc le contrôle 4 d'AD-4 tient et la concaténation des segments est le corps envoyé. Un seul algorithme d'attribution sert les deux modes.

Répartition (avant et après l'appel) : `écart = total − Σ estimations` ; s'il est positif, il va au segment « chez le fournisseur » ; sinon les estimations sont réduites en proportion (plus forts restes) et l'écart vaut 0. Exemple : estimations 300 + 100, `usage` 360 → 270 + 90 + 0.

Le port local garde `complete(ids, stop, max_tokens, cancel)` : introduire `RenderedPrompt` n'apporterait rien tant qu'un seul adaptateur de texte existe. La session choisit sa branche selon le mode du modèle actif.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run python -m pytest` -- expected: tout passe
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks:**
- `uv run wavestack` avec une vraie clé Groq puis Mistral : saisir la clé, Tester, Choisir (avertissement), relancer, tour avec `get_datetime` ; vérifier l'indicateur, le schéma, le corps tracé sans clé, les « ≈ » puis la réconciliation, et une erreur 401 avec une clé fausse.
