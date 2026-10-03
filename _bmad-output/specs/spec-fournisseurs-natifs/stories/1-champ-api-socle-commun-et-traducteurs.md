---
title: 'Fournisseurs natifs (1/5) : champ api, socle commun et traducteurs'
type: 'refactor'
created: '2026-10-03'
status: 'done'
baseline_commit: 'e09cfa6dc892f19973ebe408e058420f94718ba0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/formats-natifs.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La couche cloud ne connaît qu'une API, Chat Completions : l'engine (`OpenAIChatEngine`), le corps (`render_chat_body`) et le code commun (erreurs AD-16, masquage, cadence, FinOps, `run_call`) sont soudés dans `openai_chat.py`. Les stories 3 (Anthropic Messages) et 4 (OpenAI Responses) n'ont nulle part où se brancher.

**Approach:** Ajouter à `CloudModel` le champ `api` (défaut `openai_chat`) et `extra_headers`, sortir le code commun d'`openai_chat.py` dans un module de base, et choisir l'engine et le traducteur du corps par `entry.api`, aux trois endroits qui créent un engine ou un corps (tour, « LLM nu », « Tester »). C'est une refactorisation sans changement de comportement : aucun fournisseur nouveau, et les corps comme les en-têtes de Groq, Mistral, Gemini et Gemma restent identiques à l'octet près. AD-5 est amendé et AD-26 est écrit dans `ARCHITECTURE-SPINE.md`.

## Boundaries & Constraints

**Always:**
- Corps `openai_chat` identiques à l'octet près avant et après, prouvés par un test qui compare à des empreintes relevées AVANT la refactorisation (même historique : système, utilisateur, appel d'outil, réponse d'outil, raisonnement renvoyé, outils déclarés ; entrées `groq`, `mistral`, `gemini`, `gemma` de `wavestack.toml`, brique Raisonnement allumée et éteinte).
- Les en-têtes envoyés par une entrée sans `extra_headers` restent `Content-Type` et l'en-tête d'authentification, rien d'autre.
- `extra_headers` : en-têtes fixes non secrets, ajoutés après l'authentification ; un nom de `PUBLIC_HEADERS`, l'en-tête d'authentification ou `Content-Type` est refusé à la validation (même style de message que `AuthHeader`).
- Les noms importés aujourd'hui depuis `wavestack.models.openai_chat` (dont `_last_start`, `_quota_scope`, `record_spend`, `CallCost`, `ProviderError`, `ChatBody`, `ChatEnd`, `run_call`, `pace`, `reset_spend`) restent importables de là : tests et appelants inchangés.
- Les clés de messages `models.openai_chat.*` gardent leur nom (aucune retraduction).
- Le client HTTP vient toujours de `net/factory.create_client`.

**Never:**
- Aucun adaptateur Anthropic ou Responses, aucune entrée nouvelle dans `wavestack.toml`, pas de prix de cache (story 2).
- `api` n'accepte que `openai_chat` dans cette story : les stories 3 et 4 élargissent le `Literal` avec leur adaptateur, pour qu'aucune entrée ne puisse viser une API sans adaptateur.
- Ne pas modifier `chat_fields` ni l'ordre des champs du corps.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Corps inchangé | Entrées groq, mistral, gemini, gemma ; historique de référence | `render_chat_body(..., api=entry.api).body` égal à l'empreinte d'avant | N/A |
| Engine choisi | Entrée `api = "openai_chat"` | La fabrique rend un `OpenAIChatEngine` | N/A |
| API inconnue du registre | Registre de test avec une API factice et son traducteur | Corps écrit par le traducteur factice ; corps envoyé = `context_rendered.body` = `outbound_request.body` | N/A |
| En-tête fixe | `extra_headers = {"anthropic-version": "2023-06-01"}` | Envoyé sur chaque requête, masqué dans `outbound_request` (hors `PUBLIC_HEADERS`) | N/A |
| En-tête refusé | `extra_headers = {"Content-Type": …}` ou `{"accept": …}` ou le nom de `auth_header` | Validation refusée, message clair | ValidationError |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/openai_chat.py` -- tout aujourd'hui. Commun à extraire : `ChatBody`, `ChatEnd`, `ProviderError`, `mask_key`, `_mask_value`, `_clip`, `_provider_message`, `_quota_scope`, `_no_quota`, `_QUOTA_FR`, `pace` (+ `_pace_lock`, `_last_start`), FinOps (`CallCost`, `call_cost`, `_spend*`, `record_spend`, `session_spend`, `reset_spend`), `ChatCall`, `_reinjected`, `_check_calls`, `output_tokens`, `output_tps`, `run_call`, et dans la classe : `__init__`, `mask`, `tokenize`/`token_pieces`/`close`, cache/snapshot/prefill, `_text`, `_error`, `complete` (URL et en-têtes à paramétrer), `_refused`. Propre à `openai_chat` : `_FINISH`, `_CONTEXT_WORDS` (peut rester commun pour `_refused`), `_is_thought`, `_read`, `_channels`, le chemin `/chat/completions`.
- `src/wavestack/config.py:204` `CloudModel` -- ajouter `api` et `extra_headers` ; `PUBLIC_HEADERS` (l. 99) et `AuthHeader` (l. 120) pour la règle de refus.
- `src/wavestack/context/render.py:432` `render_chat_body` -- la closure `render` sérialise `{model, messages, tools, …tail}` ; la remplacer par un traducteur choisi par `api` (registre de traducteurs), sans toucher à `_attribute` (méthode des sentinelles : le traducteur doit garder chaque texte comme chaîne JSON).
- `src/wavestack/session/app_session.py:765` (fabrique d'engine), `:4184` (tour), `:8583` (« LLM nu ») ; `src/wavestack/session/diagnostic.py:175` (fabrique), `:1088` (« Tester ») -- passer `api=entry.api` et utiliser la fabrique commune.
- `tests/conftest.py:142`, `tests/test_cloud.py:1001` -- touchent `openai_chat._last_start` : le même objet doit rester visible depuis `openai_chat`.
- `tests/test_e2e_fake_openai.py` -- modèle du test « corps envoyé = `context_rendered.body` = `outbound_request.body` ».
- `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md:215` (AD-5), après `:652` (AD-25) pour AD-26.

## Tasks & Acceptance

**Execution:**
- [x] `tests/fixtures/openai_chat_bodies.json` + `tests/test_cloud_api.py` -- AVANT toute refactorisation : écrire l'historique de référence et relever les corps (sha256 et longueur) des quatre entrées, raisonnement on/off ; le test compare -- preuve de non-régression à l'octet.
- [x] `src/wavestack/config.py` -- `api: Literal["openai_chat"] = "openai_chat"`, `extra_headers: dict[str, str] = {}` avec validateur (PUBLIC_HEADERS, `content-type`, nom de `auth_header`, insensible à la casse) ; docstring -- CAP-1.
- [x] `src/wavestack/models/cloud_base.py` -- module nouveau : code commun ci-dessus et classe `CloudEngine` (en-têtes : `Content-Type`, authentification, `extra_headers` ; URL par `endpoint` de la sous-classe ; `_read` abstrait) -- socle des stories 3 et 4.
- [x] `src/wavestack/models/openai_chat.py` -- `OpenAIChatEngine(CloudEngine)` avec `_read`, `_channels`, `/chat/completions` ; réexporter les noms communs -- compatibilité.
- [x] `src/wavestack/models/cloud_api.py` -- registre `api → classe d'engine` et `create_cloud_engine(entry, key, *, connect_timeout_s, read_timeout_s, transport=None)` -- choix par `entry.api`.
- [x] `src/wavestack/context/render.py` -- registre `api → traducteur` (`openai_chat` = sérialisation actuelle), paramètre `api: str = "openai_chat"` de `render_chat_body` -- format pivot.
- [x] `src/wavestack/session/app_session.py`, `src/wavestack/session/diagnostic.py` -- fabriques par défaut via `create_cloud_engine`, `api=entry.api` aux trois appels de `render_chat_body` -- CAP-1.
- [x] `tests/test_cloud_api.py` -- cas de la matrice (traducteur et engine factices enregistrés le temps du test, `extra_headers` envoyés et masqués, refus de validation).
- [x] `ARCHITECTURE-SPINE.md` -- AD-5 amendé (`extra_headers`, en-têtes fixes non secrets, masqués) ; AD-26 (champ `api`, format pivot Chat Completions, traducteur par API dans `render_chat_body`, engine par API, module de base) -- contrainte « Architecture » de SPEC.md.

**Acceptance Criteria:**
- Given la branche après la story, when on joue `pytest` en quarts, then tout est vert, et `test_net_single_factory.py` passe sans exception nouvelle.
- Given les entrées de `wavestack.toml` inchangées, when on charge la configuration, then chacune a `api == "openai_chat"` et `extra_headers == {}`.

## Implementation Notes

- Empreintes relevées avant toute modification de `src/` : `tests/test_cloud_api.py` (historique de référence) écrit et `tests/fixtures/openai_chat_bodies.json` généré sur le code de `e09cfa6`, test vert, puis refactorisation ; le test est resté vert sans régénération. L'historique donne au raisonnement renvoyé la forme du `format` de chaque entrée (`field`, `content_blocks`, `think_tags`), que l'entrée le renvoie ou non, et les appels portent `tool_call_extra` (Gemini, Gemma). Groq raisonne toujours (`always`) : ses empreintes on et off sont égales.
- `openai_chat` réexporte les noms publics de `cloud_base` plus `_last_start` et `_quota_scope` (`__all__`) ; `_last_start` est le même objet que celui de `cloud_base`.
- Refus de `extra_headers` : deux messages (en-tête posé par l'adaptateur ; en-tête tracé en clair), exception ajoutée dans `tests/test_backend_messages.py` (message de validation de configuration, comme ceux d'`AuthHeader`).

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-03), trois couches : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Source | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|---|
| 1 | VG, EC | Un `extra_headers` refusé, chargé par `cloud_models`, s'affiche « (entrée) » sans raison | medium | Validateur de modèle : `loc == ()`, et `config.py:647` ne garde la raison que pour `auth_header` | patch |
| 2 | EC | `models/cloud_base.py` hors du PERIMETER de `test_backend_messages.py` | medium | Le code des refus a quitté `openai_chat.py`, seul inscrit (l. 329) : le contrôle statique ne le couvre plus | patch |
| 3 | BH, EC | Les trois listes d'API (`Literal`, `ENGINES`, `TRANSLATORS`) ne sont pas gardées en phase | low | Rien ne le teste ; correction directe d'une ligne, utile aux stories 3 et 4 | patch |
| 4 | BH | Schéma `CloudModel{…}` d'AD-20 et arborescence `models/` sans `api`, `extra_headers`, `cloud_base`, `cloud_api` | low | `ARCHITECTURE-SPINE.md:572` et l. 816 | patch |
| 5 | BH | `cloud_base` garde les clés `models.openai_chat.*` sans dire pourquoi | low | Choix gelé de la spec, non commenté ; une ligne | patch |
| 6 | BH, EC | Sessions des tests jamais fermées ; `llm_generate(..., None)` contre le type `Sampling` | low | `test_cloud_api.py:270-303`, `:336` ; correction directe | patch |
| 7 | BH | Pas de retrait d'un en-tête par `null` dans `settings.json` | low | Aucun préréglage n'a d'`extra_headers` ; correction = règle de fusion nouvelle | rejeté (peu probable, ajoute de la complexité) |
| 8 | BH, EC | Syntaxe des noms et valeurs (espaces, non-ASCII, CR/LF) non vérifiée | low | Entrée écrite à la main, rare ; correction = gardes nouvelles | rejeté |
| 9 | BH, EC | Deux noms égaux à la casse près acceptés | low | Idem | rejeté |
| 10 | BH | `api` par défaut dans `render_chat_body` | low | Les trois appelants le passent ; défaut voulu pour les tests existants | rejeté |
| 11 | BH, EC | `CloudEngine` pas abstrait (`endpoint` oublié) | low | Une sous-classe sans `endpoint` échoue dès son premier test | rejeté |
| 12 | BH | Appelants importent par la réexportation d'`openai_chat` | low | Fonctionne ; cosmétique | rejeté |
| 13 | BH | Empreintes peu lisibles en cas d'échec ; formes non épinglées (sans outils, plusieurs appels, sampling) | low | Sans outils couvert par `test_cloud.py:196` ; le reste est couvert par la suite existante | rejeté |
| 14 | BH | « LLM nu » et « Tester » : seule la forme du corps est vérifiée | low | Même traducteur que le tour, dont l'égalité est testée | rejeté |
| 15 | BH | `monkeypatch` de `cloud_model` pour tous les ids ; import d'aides privées de `test_cloud` | low | Motif déjà employé par 9 modules de tests | rejeté |
| 16 | BH | En-têtes fixes masqués dans le journal, contre la transparence | low | Imposé par SPEC.md (« refusés s'ils sont tracés en clair ») : correction = changer la spec | rejeté |
| 17 | BH | Messages de validation en français seulement | false | Catégorie d'exceptions existante pour la validation de configuration (`AuthHeader`, l. 368-370) | rejeté |

## Design Notes

Traducteur : `translate(model: dict, messages: list, tools: list | None, tail: dict) -> dict`, puis `json.dumps(..., ensure_ascii=False, separators=(",", ":"))` commun. Pour `openai_chat` : `{**model, "messages": messages, **({"tools": tools} if tools else {}), **tail}`, exactement l'actuel. Le registre vit dans `context/render.py` pour que `context` reste le seul écrivain du corps (AD-4) ; les stories 3 et 4 y ajoutent leur traducteur.

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest tests/test_cloud_api.py tests/test_cloud.py tests/test_e2e_fake_openai.py tests/test_llm_lab.py -q` -- expected: vert
- `pytest` complet en quatre quarts (au premier plan ou en arrière-plan un à la fois) -- expected: vert
