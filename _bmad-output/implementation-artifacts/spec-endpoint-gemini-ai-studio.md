---
title: 'Endpoint cloud Gemini (Google AI Studio) réel et activable'
type: 'feature'
created: '2026-09-29'
status: 'in-review'
baseline_commit: 'de47b144d7925f632e3303c695426337ba40b15f'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** WaveStack n'a qu'un exemple Gemini commenté (`gemini-2.5-flash`, sans raisonnement), inutilisable avec une clé AI Studio neuve. La démo du 2026-10-01 et l'usage durable demandent un vrai modèle Gemini, choisissable, avec un raisonnement qu'on allume et qu'on éteint.

**Approach:** Déclarer une entrée `[[cloud.models]]` Gemini complète dans `wavestack.toml` et un éditeur « Gemini (Google) ». Rendre l'adaptateur `openai_chat` capable de ce que Gemini 3.x exige : les balises de raisonnement réglables, et le renvoi des signatures de pensée des appels d'outils. Le rendre aussi vérifiable (signature et deltas bruts tracés), puis livrer un prompt de recette pour le PC cible, qui a la clé.

## Boundaries & Constraints

**Always:**
- Faits revérifiés sur ai.google.dev le 2026-09-29 :
  - `base_url` `https://generativelanguage.googleapis.com/v1beta/openai`, clé en `Authorization: Bearer`, outils, streaming et `stream_options.include_usage` supportés.
  - `gemini-3.5-flash-lite` est stable. Fenêtre de 1 048 576 tokens en entrée, 65 536 en sortie. Niveaux `minimal` (valeur par défaut), `low`, `medium`, `high`. Prix : 0,30 $ / 2,50 $, aucune hausse annoncée pour ce modèle.
  - `gemini-3.6-flash` accepte aussi `minimal` et coûte 0,75 $ / 3,75 $, puis 1,50 $ / 7,50 $ au 2027-01-01. Les 3.7 et 3.8 Flash n'ont pas `minimal`.
  - La 2.5 est réservée aux projets qui l'ont déjà utilisée.
  - Offre payante : données non utilisées pour l'entraînement.
  - `reasoning_effort` et `thinking_config` ne se combinent pas.
  - Le texte du raisonnement ne revient qu'avec `extra_body.google.thinking_config.include_thoughts`, et la doc ne dit pas sous quelle forme.
  - Gemini 3.x renvoie `tool_calls[].extra_content.google.thought_signature` et refuse (400) un appel du tour en cours rejoué sans elle.
- L'entrée Gemini :
  - `id = "gemini"`, `provider = "Google AI Studio"`, `model = "gemini-3.5-flash-lite"`, `key_env = "GEMINI_API_KEY"`, `tools = true`, `stream_usage = true`, `context = 1048576`, `training = "no"`, activée comme Groq et Mistral (indisponible tant qu'il n'y a pas de clé).
  - `notes_fr` dit : l'offre payante est obligatoire (clause EEE), rien n'est utilisé pour l'entraînement sur l'offre payante, et les prix sont à vérifier dans la console (hausse au 2027-01-01 pour les 3.6 à 3.8 Flash).
  - Raisonnement : `format = "think_tags"` avec `tags = ["<thought>", "</thought>"]`.
    - `on = { extra_body = { google = { thinking_config = { thinking_level = "low", include_thoughts = true } } } }`
    - `off = { reasoning_effort = "minimal" }`
    - `always = false`, `resend = false`.
  - `tool_call_extra = { extra_content = { google = { thought_signature = "skip_thought_signature_validator" } } }`, pour les appels que le harnais fabrique (actions forcées).
- La signature n'est rejouée qu'au fournisseur qui l'a émise (même `entry.id`). Groq et Mistral ne voient jamais `extra_content`.
- La clé n'apparaît ni dans le journal, ni dans les logs, ni dans les réponses d'API (test sentinelle).
- Les comportements de Groq, Mistral et du mode local restent identiques, octet pour octet.

**Never:**
- Pas d'appel réseau réel dans les tests.
- Pas de clé dans le dépôt.
- Pas de nouvelle dépendance.
- Pas de dépôt de la 2.5 comme valeur par défaut (seulement documentée en commentaire, comme le secours 3.6).
- Pas de modification des SLM locaux ni de l'atelier « LLM nu ».

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Outil + signature | Gemini, brique Outils, un `tool_call` portant `extra_content` | Le 2e corps rejoue `extra_content` tel quel dans `assistant.tool_calls[0]`. Tour `completed` | Sans signature, le faux fournisseur répond 400 → le test échoue |
| Raisonnement allumé | Brique Raisonnement active | Corps avec `extra_body…include_thoughts`, sans `reasoning_effort`. `<thought>…</thought>` va au canal reasoning, la réponse au canal text. `max_tokens` 1 536 | — |
| Raisonnement éteint | Brique éteinte | `reasoning_effort: "minimal"`, sans `extra_body`, `max_tokens` 512 | — |
| Pensée marquée | Delta `content` avec `extra_content.google.thought = true` | Texte au canal reasoning (forme alternative possible) | — |
| Changement de fournisseur | Historique Gemini avec signature, puis Groq | Aucun `extra_content` dans le corps envoyé à Groq | — |
| Action forcée sur Gemini | Appel fabriqué par le harnais | Porte `tool_call_extra`. Aucune autre entrée n'en porte | — |
| « Tester » au diagnostic | Gemini, 2 appels | Le 2e appel rejoue la signature du 1er | — |

</frozen-after-approval>

## Code Map

- `wavestack.toml` -- section `[cloud]` : ajouter l'entrée après Mistral. Remplacer l'exemple Google commenté par un commentaire sur le secours 3.6 et la 2.5 (`on = {reasoning_effort="low"}` : 1 024 tokens dans la réserve de 1 536 ; `off = {reasoning_effort="none"}`). Mettre à jour la mention `key_env` (« GOOGLE_API_KEY »).
- `src/wavestack/config.py:102 CloudReasoning` -- ajouter `tags`, deux chaînes non vides, `<think>`/`</think>` par défaut. `:141 CloudModel` -- ajouter `tool_call_extra: dict[str, Any] = {}`.
- `src/wavestack/models/openai_chat.py` :
  - `:419` : le `ChannelSplitter` prend `entry.reasoning.tags`.
  - `:505-537 _channels` : capturer `call["extra_content"]` (un dict) dans l'accumulateur, et envoyer le `content` marqué `extra_content.google.thought` au canal reasoning.
  - `:642` : ajouter `extra_content` à la trace `model_call_ended.tool_calls`, pour que la recette puisse le vérifier.
  - Les deltas bruts restent dans `raw_output`, masqués.
- `src/wavestack/session/app_session.py` :
  - `:454 _ModelOutput`, `:7001-7033 _call_model_chat` : une liste parallèle `extras`, vidée sur le chemin tronqué.
  - `:4557 _assistant_step` : `extra_content` et `extra_for` (l'`id` de l'entrée).
  - `:3517-3534 _step_messages`, branche `chat` : n'ajouter `extra_content` que si `extra_for == self._cloud.id`.
  - `:6245-6260` actions forcées : ajouter `entry.tool_call_extra` en mode chat.
  - L'historique vit en mémoire seulement, et `render.py` recopie tel quel un dict qui n'est pas un `Part`.
- `src/wavestack/session/diagnostic.py:1047-1053` -- ajouter l'`extra_content` de `out.calls[0]` à l'appel rejoué.
- `content/models/publishers.yaml` -- éditeur `gemini`, « Gemini (Google) », `names: ['gemini']`, juste après `gemma`.
- `README.md:662,708` -- Gemini déclaré, clé `GEMINI_API_KEY`.
- `tools/e2e/fake_openai.py` -- mode Gemini quand `model` commence par `gemini` :
  - signature sur le premier appel de chaque réponse (comme la vraie API), et 400 « missing a thought_signature » si le premier appel rejoué du tour n'en porte pas ;
  - `<thought>…</thought>` dans `content` si `include_thoughts`, aucun raisonnement sinon.
- `tools/e2e/stack.py`, `tools/e2e/run_e2e.py`, `tools/e2e/README.md` -- une entrée `fake_g` (`gemini-e2e-flash-lite`, raisonnement déclaré comme l'entrée réelle), le scénario `gemini_shape`, le groupe « Réseau · Gemini (Google) » dans les attentes des groupes (`:5281`).
- Tests à modèle : `tests/test_cloud.py:119` (tour Groq à deux appels), `:363` et `:433` (listes d'ids, à mettre à jour), `tests/test_model_catalog.py:325`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/config.py` -- ajouter `tags` et `tool_call_extra` -- le format Gemini et le contournement des appels fabriqués.
- [x] `src/wavestack/models/openai_chat.py` -- balises réglables, capture et trace de `extra_content`, pensée marquée -- capture vérifiable.
- [x] `src/wavestack/session/app_session.py`, `src/wavestack/session/diagnostic.py` -- rejouer la signature au même fournisseur ; `tool_call_extra` sur les actions forcées -- sinon Gemini 3.x répond 400.
- [x] `wavestack.toml`, `content/models/publishers.yaml`, `README.md` -- l'entrée, l'éditeur, la doc.
- [x] `tests/test_cloud.py` -- les lignes de la matrice, la sentinelle de clé, les listes d'ids mises à jour ; `tests/test_model_catalog.py` -- le groupe Gemini.
- [x] `tools/e2e/*`, `tests/test_e2e_fake_openai.py` -- le mode Gemini du faux fournisseur et le scénario `gemini_shape` (tour outils, raisonnement allumé puis éteint, carte Raisonnement, corps relus par `/_e2e/requests`).
- [x] `_bmad-output/implementation-artifacts/prompt-recette-gemini-2026-09-29.md` -- le prompt pour le Claude Code du PC cible (voir Design Notes).

**Acceptance Criteria:**
- Given la configuration livrée, when on ouvre le sélecteur ou `/models`, then « RÉSEAU · Google AI Studio · gemini-3.5-flash-lite » figure dans le groupe « Réseau · Gemini (Google) », avec un raisonnement « activable ». Sans clé, il est indisponible et la raison est donnée.
- Given `GEMINI_API_KEY` définie, when on lance WaveStack, then l'entrée est choisissable sans rien saisir, et `generativelanguage.googleapis.com` fait partie des hôtes autorisés.
- Given une valeur réelle différente (format, `minimal` refusé, `extra_body` refusé), when la recette la constate, then elle se corrige par `settings.json` (fusion par `id`), sans modifier le code.

## Design Notes

**Pourquoi `think_tags` :** les champs `reasoning`/`reasoning_content` et les blocs de contenu sont lus quel que soit le format. `think_tags` avec des balises réglables couvre donc les trois formes possibles, et `<thought>` est l'hypothèse la plus citée. Si la recette voit la pensée arriver ailleurs, il suffit de changer `tags` ou `format` dans `settings.json`.

**Pourquoi `extra_body` en JSON brut :** l'exemple REST de Google envoie la clé `extra_body` telle quelle dans le corps. Le repli, si elle est refusée, est `on = { reasoning_effort = "low" }` : le raisonnement est alors actif mais invisible.

**Le prompt de recette** (même forme que `prompt-recette-lot-k-suite-2026-09-29.md`) demande de :
- faire tourner `uv run pytest` et l'E2E ;
- mettre la clé dans `GEMINI_API_KEY` (jamais dans un fichier du dépôt) ;
- lancer « Tester » au diagnostic ;
- jouer le scénario « Outils natifs » avec ses trois prompts, raisonnement éteint puis allumé, en contrôlant pour chaque tour `outbound_request.body`, `model_call_ended` (`reasoning`, `text`, `tool_calls[].extra_content`, `raw_output`, `stop_reason`, `usage_source`) et la carte Raisonnement ;
- relire le tableau `/models` ;
- chercher la clé dans le journal (`/api/events`), `wavestack.log` et `audit.log` : zéro occurrence, 4 premiers et 4 derniers caractères compris ;
- appliquer les replis si besoin (tags, `reasoning_effort` pour allumer, `gemini-3.6-flash`) ;
- consigner les résultats dans `resultats-recette-gemini-2026-09-29.md`.

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` -- expected: tout vert
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 FAIL, dont `[gemini_shape]` ; puis `git restore tools/e2e/screenshots`

## Implementation Notes

- `settings.json` fusionne champ par champ (`_deep_merge`) : le repli `on = {reasoning_effort = "low"}` aurait gardé `extra_body` hérité (combinaison refusée par Gemini). `reasoning_params` omet donc un champ à `null` : `"on": {"extra_body": null, "reasoning_effort": "low"}`. Aucun préréglage existant n'a de `null` : Groq et Mistral inchangés.
- `extra_content` est rejoué tel que reçu (non masqué) : un morceau masqué casserait la signature. Il est masqué dans la trace `model_call_ended` et dans `raw_output`. Il figure en clair dans le corps rejoué (`context_rendered`, `outbound_request`) : une collision avec les 4 premiers ou derniers caractères de la clé y est possible en théorie (rare). Le faux fournisseur de l'E2E signe `signature-fausse-…`, car `e2e-` est le début de sa clé.
- Dans un pas d'assistant, un appel porte `extra` (champs ajoutés à l'appel envoyé, sans jamais remplacer `id`, `type` ni `function`) et `extra_for` (l'`id` de l'entrée). Un appel du fournisseur : `extra = {extra_content: …}` ; une action forcée : `extra = tool_call_extra`.
- Le faux Gemini ne refuse que les appels non signés du tour en cours (comme Gemini), pas ceux de l'historique.
- Sonde de l'API réelle (2026-09-29, `gemini-3.5-flash-lite`), reproduite par le faux fournisseur et les tests unitaires :
  - `extra_body` avec `include_thoughts` et `reasoning_effort: "minimal"` acceptés. La pensée arrive dans `content` : `<thought>` et la pensée dans des fragments marqués `extra_content.google.thought = true`, puis un fragment non marqué `</thought>` + le début de la réponse. Avec `think_tags`, tout `content` passe donc par le séparateur de balises ; la marque seule ne décide qu'en l'absence de balises (repli `format = "field"`).
  - Une réponse texte se clôt par un fragment dont le delta porte `extra_content.google.thought_signature`, sans contenu, `finish_reason: "stop"` : ignoré sans effet.
  - L'appel d'outil arrive en un fragment, sans `index`, puis `{"role": "assistant"}` avec `finish_reason: "stop"` (jamais `tool_calls`). Rejoué sans signature : 400 dont le corps est un tableau JSON `[{"error": …}]` ; `_provider_message` en lit le premier élément, pour que le message français finisse par le vrai message. Rejoué avec la signature reçue ou avec `skip_thought_signature_validator` : 200. L'`id` de session suffit.
  - `usage` sur chaque fragment, cumulé. `completion_tokens` exclut les tokens de réflexion, que `total_tokens` compte (facturés en sortie, et comptés dans `max_tokens`). `run_call` prend `total_tokens − prompt_tokens` quand il dépasse `completion_tokens`, sinon `completion_tokens` : Groq et Mistral (`total = prompt + completion`) sont inchangés.

## Spec Change Log

## Review Triage Log

Revue 1 (2026-09-29, trois relecteurs : aveugle, cas limites, trous de vérification). Constats vérifiés dans le code, et sur l'API réelle pour l'ordre des appels.

| # | Constat | Verdict | Preuve | Suite |
|---|---------|---------|--------|-------|
| 1 | Le sous-agent sur Gemini n'est couvert par aucun test (VG, B11) | medium | Aucun test ne délègue avec l'entrée `gemini` ; retirer `cloud_id=` au rendu du sous-agent ne ferait échouer aucun test | patch : test de délégation, et test d'un 2e tour Gemini avec mémoire courte |
| 2 | Le renvoi `think_tags` écrit `<think>` même avec d'autres `tags` (VG, EC) | low | `_assistant_message` code `<think>` en dur ; aucune entrée livrée n'a `resend` avec `tags`, mais la correction est directe | patch |
| 3 | Appels parallèles sans `index`, triés par ordre alphabétique d'`id` (B1, EC1) | low | Sonde réelle : les `id` croissent (`call_118265`, `call_118268`…) ; le tri alphabétique inverse `call_99999` et `call_100002`. Google accepte le renvoi quel que soit l'appel signé (200 dans les deux cas), donc pas de 400, seulement l'ordre | patch : garder l'ordre d'arrivée |
| 4 | Le faux Gemini signe chaque appel, le vrai ne signe que le premier d'une série parallèle (B1) | low | Sonde réelle : signature sur le premier appel seulement | patch : faux fournisseur et docs alignés |
| 5 | « `null` retire un champ hérité » : vrai seulement pour les clés de premier niveau de `reasoning.on` et `off` (B2, EC6, EC7, EC8) | low | `reasoning_params` ne filtre que ce niveau ; `_deep_merge` garde les `null` imbriqués | patch : docs précises (toml, README) |
| 6 | Signature brute dans `context_rendered` et `outbound_request`, masquée seulement dans `model_call_ended` (B4, EC10) | low | AD-5 impose le corps tracé identique aux octets envoyés ; un fragment de 4 caractères pris au hasard dans une signature base64 n'est pas une fuite (`AIza` est public), mais peut déclencher le comptage de fuite de la recette | patch : docstring et prompt de recette |
| 7 | Prompt de recette : la clé ne passe pas d'une commande de Claude Code à l'autre, et rien ne vérifie que `main` porte Gemini (B12, B13) | medium | Chaque appel PowerShell de Claude Code est un nouveau processus | patch : clé lue depuis un fichier hors dépôt dans la même commande, lancement en arrière-plan, vérification d'entrée |
| 8 | Repli 3.7 / 3.8 avec `off = low` : le modèle raisonne brique éteinte (B8) | low | Commentaire du toml sans avertissement | patch : avertissement |
| 9 | Prix du README sans date de relevé (B7) | low | README sans « relevé le » | patch |
| 10 | Réserve de 1 536 tokens juste avec la réflexion cachée, et coupure non expliquée (B5) | maybe-false | Sonde : 986 tokens de réflexion à `low` sur une question dure ; à mesurer en recette réelle sur les scénarios | defer (moyenne, non vérifiée) |
| 11 | `training = "no"` affiché même avec une clé de l'offre gratuite (B6) | false | L'intention figée impose `training = "no"` et `notes_fr` dit que l'offre payante est obligatoire | rejeté |
| 12 | `notes_fr` cite les 3.6 à 3.8 (B7) | false | Texte imposé par l'intention figée | rejeté |
| 13 | Règle `total − prompt` appliquée à tout fournisseur (B9, EC11) | maybe-false | Groq, Mistral et OpenAI donnent `total = prompt + completion` ; aucun fournisseur déclaré n'est touché | rejeté (hypothétique) |
| 14 | Débit gonflé par la réflexion cachée (EC12) | low | Réflexion `minimal` quasi nulle brique éteinte, et visible brique allumée | rejeté (rare, correction à branches) |
| 15 | Signature de fin de réponse texte ignorée (B10) | false | Google la dit facultative pour une partie texte ; seuls les appels d'outils sont validés (sonde : 200) | rejeté |
| 16 | Pensée marquée sans balise en mode `think_tags` (B3, EC4) | maybe-false | Google écrit les balises (sonde) ; la garde ajouterait une branche pour un cas non observé | rejeté |
| 17 | Appel sans `index` ni `id` fusionné (EC2) | false | Gemini envoie toujours un `id` (sondes) ; les autres fournisseurs un `index` | rejeté |
| 18 | `extra_content` réparti sur deux fragments (EC3) | false | Gemini l'envoie en un fragment (sondes) | rejeté |
| 19 | `tags` identiques ou préfixes l'un de l'autre (EC9) | low | Erreur de configuration manuelle, improbable | rejeté |
| 20 | `_provider_message` sur tableau vide (B11) | false | `data and …` le garde : repli sur `str(data)` | rejeté |
| 21 | Faux fournisseur : appel qui n'est pas un objet (EC13), `stack.py` sans entrée `gemini` (EC14) | low | Outils de test, entrées contrôlées | rejeté |
