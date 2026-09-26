---
title: 'Serveur local déjà lancé (Ollama, llama-server)'
type: 'feature'
created: '2026-09-26'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** La découverte repère déjà Ollama (`127.0.0.1:11434`) et llama-server (`127.0.0.1:8080`) sans les lancer, mais un serveur trouvé reste inutilisable : sans fichier GGUF chargeable, la session démarre sans modèle (« son adaptateur arrive au palier 2 »). Or sur le PC cible les Qwen3.5 d'Ollama ne se chargent pas dans llama-cpp-python 0.3.35, alors qu'un serveur déjà lancé les fait tourner. C'est la seconde moitié de CAP-36 (FR-34).

**Approach:** Deux adaptateurs de texte rendu derrière le port `Engine` (AD-5). `llama_server` envoie les ids par `/completion` et tokenise par `/tokenize`. `ollama_raw` envoie le texte par `/api/generate` en `raw: true`, avec `num_ctx` égal à la fenêtre effective, et tokenise avec le GGUF du modèle ouvert en `vocab_only`. Le harnais construit toujours le texte envoyé, gabarit compris (AD-4). Chaque modèle servi devient un candidat `{kind: server, ref}` qu'on choisit comme un fichier, au diagnostic et à chaud (story 17). En mode serveur, le modèle en processus est libéré et la mémoire du modèle servi est comptée ; en quittant un modèle Ollama, WaveStack envoie `keep_alive: 0` (AD-8). Le schéma dessine ce modèle comme un processus local distinct du harnais.

## Boundaries & Constraints

**Always:**
- Spine : AD-4 (mode texte rendu inchangé : attribution exacte, contrôles 4 et 6, `_check_prefix`), AD-5, AD-6, AD-7, AD-8, AD-9, AD-12, AD-15, AD-16, AD-20, AD-23 et AD-24. Aucune nouvelle dépendance. Code en anglais, textes en français, construits côté Python quand un événement les porte.
- Port inchangé : `complete(prompt_ids, stop, max_tokens, cancel) → Fragment`, avec `tokenize`, `token_pieces`, `metadata` et `close`. Chaque adaptateur streame en interne, teste le `CancelToken` à chaque fragment et ferme le flux HTTP à l'annulation.
- **`llama_server`** :
  - `POST /completion` avec `prompt` = liste d'ids, `n_predict = max_tokens`, `stop`, `stream: true`, `cache_prompt: true` et l'échantillonnage d'`engine.py` ;
  - fin : `stop_type` `limit` → `length`, tout autre arrêt → `stop` ;
  - `tokenize` : `POST /tokenize {content, add_special: false, parse_special: true, with_pieces: true}` ; une pièce est une chaîne UTF-8 ou une liste d'octets, gardée en cache id → octets ;
  - `token_pieces(ids)` lit ce cache ; un id absent passe par `POST /detokenize` ;
  - `metadata()` : gabarit, `bos_token` et `eos_token` de `GET /props`, contexte natif de `GET /v1/models` (`meta.n_ctx_train`), contexte du serveur de `/props` (`default_generation_settings.n_ctx`), `architecture = None` ;
  - tokens spéciaux : `bos`, `eos`, et ceux des marqueurs `[cloud] neutralize_markers` que `/tokenize` rend en un seul token.
- **`ollama_raw`** :
  - `POST /api/generate {model, prompt, raw: true, stream: true, options: {num_ctx, num_predict, stop, temperature, top_p, top_k, min_p}}` ; `num_ctx` = fenêtre effective, toujours envoyé ;
  - `prompt` = `b"".join(token_pieces(ids)).decode("utf-8")`, soit exactement le texte rendu (contrôle 6 d'AD-4) ;
  - flux NDJSON : `response` → texte ; `done_reason` `length` → `length` ; `eval_count` final = tokens de sortie ;
  - si `prompt_eval_count` ≠ `len(ids)`, l'adaptateur émet `harness_error` « transparence réduite », avec les deux comptes ;
  - un champ `thinking` non vide émet le même `harness_error`, une fois par appel ;
  - tokenizer, `token_pieces` et métadonnées viennent du GGUF (blob du manifeste Ollama) ouvert en `vocab_only`, par le même code que `LlamaCppEngine`, factorisé.
- HTTP par `net` seulement (AD-15) : un client boucle locale, sans proxy (`trust_env=False`), qui refuse tout hôte hors boucle locale ; appels sous `origin = model`, non tracés en `outbound_request` (boucle locale). Délais dans `wavestack.toml`.
- Candidats serveur (AD-7) : un candidat par modèle servi, `source = server`, `engine` (`ollama` ou `llama_server`), `server_url`, `name`, `ref`. Refs : `ollama/{nom:tag}` (`/api/tags`), `llama_server/{nom du fichier de /props model_path}`. Un modèle Ollama sans blob GGUF lisible (couche `image.tensor`, blob absent) est `incompatible`, avec la raison. `settings.json` mémorise `selected_model = {kind: server, ref}`.
- Choix : `select_model{kind: server, ref}` suit le chemin de `kind: file` (classe b ; en diagnostic, chargement immédiat ; à chaud, chemin de la story 17). Un serveur n'est jamais choisi d'office. Au lancement, un choix mémorisé est repris si le serveur répond et sert encore ce modèle ; sinon, avertissement puis règle de démarrage.
- Mode serveur (AD-8) :
  - le moteur en processus est fermé avant de préparer le serveur ;
  - coût du modèle servi : `size` de `/api/ps` si Ollama l'a chargé, sinon la taille du blob ; pour llama-server, la taille du fichier de `model_path`, sinon `meta.size` ;
  - le contrôle de budget refuse avec des chiffres en Mo, et laisse le modèle précédent actif ;
  - quitter un modèle Ollama (changement de modèle, `AppSession.close()`) envoie `POST /api/generate {model, keep_alive: 0}` ; un échec est tracé, jamais bloquant.
- Fenêtre (AD-9) = min(configurée, native, contexte du serveur) ; `window_source = server` quand c'est le contexte du serveur qui l'emporte.
- Schéma et indicateur (AD-12) :
  - `active_model` = `{id: ref, label: name, hosting: "local", provider: "Ollama" | "llama-server", server_url, disclosure: null}` ;
  - `core.model` porte `process: "external"`, `provider` et `server_url` ; l'arête `core.harness → core.model` a `crosses_boundary: false` ;
  - le front dessine le robot hors du cadre Harnais, dans la zone Poste de travail, dans une boîte « {provider} · {adresse} ».

**Never:** lancer, installer ou arrêter Ollama ou llama-server ; le format chat (`openai_chat`) vers un serveur local ; une sonde en processus enfant pour un modèle servi ; un nouvel essai automatique ; une requête hors boucle locale ; changer la signature du port `Engine` ; un réseau réel dans pytest.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Comportement attendu | Gestion d'erreur |
|---|---|---|---|
| Tour llama-server | modèle servi choisi, brique outils | ids envoyés = `context_rendered` tokenisé ; segments exacts, `usage_source = engine` ; appel d'outil parsé | — |
| Tour Ollama, comptes égaux | `prompt_eval_count = len(ids)` | texte envoyé = `rendered.prompt` ; `num_ctx` = fenêtre effective ; aucun `harness_error` | — |
| Ollama ajoute un token | `prompt_eval_count = len(ids) + 1` | le tour continue normalement | `harness_error` « transparence réduite » (Ollama n, harnais m) |
| Sortie coupée | `stop_type: limit` ou `done_reason: length` | `stop_reason = length`, voie d'AD-9 | — |
| Arrêt en plein flux | `stop` pendant le flux | flux fermé, `stop_reason = cancelled` | — |
| Serveur arrêté en plein tour | `ConnectError` ou 5xx | `turn_ended{error}`, application utilisable | `harness_error` « serveur local injoignable », avec l'adresse |
| Blob illisible | modèle Ollama en `image.tensor` | candidat `incompatible`, sans « Choisir » | raison affichée |
| `vocab_only` en échec | GGUF refusé par llama-cpp-python | modèle précédent gardé, aucun tour cassé | `harness_error` avec la cause, raison dans `select_model` |
| Budget dépassé | RSS + coût du modèle servi > budget | refus, modèle précédent actif | message chiffré en Mo |
| Quitter Ollama | changement de modèle ou fermeture | `keep_alive: 0` envoyé pour ce modèle | échec tracé, non bloquant |
| Choix mémorisé, serveur éteint | `{kind: server}`, pas de réponse | avertissement, puis règle de démarrage (story 1b) | — |
| Serveurs seuls | aucun fichier, un ou plusieurs serveurs | contrôle `model` bloquant : « Choisissez un modèle servi » | — |

</intent-contract>

## Code Map

- `src/wavestack/models/engine.py` -- `Engine` (60), `Fragment` (42), `cut_stop` (82). `LlamaCppEngine` (91) : `_read_metadata` (107), `tokenize` (129) et `token_pieces` (132) sont à factoriser dans une classe `VocabTokenizer(model_path)`, en `Llama(vocab_only=True)`, que `LlamaCppEngine` réutilise. `llama_token_to_piece` réagrandit son tampon ; `detokenize` est interdit.
- `src/wavestack/models/openai_chat.py` -- modèle de lecture en flux, de `CancelToken` et de fabrique injectable (`transport`, 204). Rien à y changer.
- `src/wavestack/models/discovery.py` -- `ModelCandidate` (25) reçoit `engine`, `ref` et `served_bytes`. `_ollama_candidates` (70) fait déjà la correspondance nom → blob, à réutiliser. `_server_candidates` (109) sonde `/api/tags` et `/health` et renvoie un candidat par serveur : il doit renvoyer un candidat par modèle servi (`transport` injectable).
- `src/wavestack/models/capabilities.py` -- `capabilities_for` (29) : sans architecture (llama-server), un gabarit qui contient `<|im_start|>` et `<tool_call>` choisit la famille `qwen3`, avec le parseur `qwen3_coder` si `<function=` est présent, sinon `hermes`.
- `src/wavestack/net/factory.py` -- `create_client` (55) : ajouter la variante boucle locale (hôte vérifié par `is_loopback` de `net/guard.py:30`).
- `src/wavestack/session/diagnostic.py` :
  - `__init__` (87) lit `selected_model` `file` ou `cloud` ;
  - `_check_model_locked` (314), branche « Serveur local trouvé » (361-369) : à remplacer par un choix bloquant ;
  - `_select_model_locked` (401), `_save_choice` (448) ;
  - `hand_to` (453) démarre `boot_cloud` ou `boot` ;
  - `next_launch_fr` (465) et `boot_finished` (495) comparent `booted_path` et `booted_cloud` : ajouter `booted_server`.
- `src/wavestack/session/app_session.py` :
  - `_CORE_MODEL` (116), `_SERVER_ONLY_FR` (128, à retirer) ;
  - `active_model` (455), `_emit_architecture` (533-541, le modèle cloud sert d'exemple) ;
  - `close` (794) ;
  - `_boot` (822) et `_boot_cloud` (885) servent de modèle à `boot_server(candidate)` : état `model_load` « Préparation du modèle servi par {provider}… », fermeture du moteur précédent, fabrique injectable `server_factory`, `capabilities_for`, fenêtre, `_emit_preview` ;
  - `_render` (1300) et `_call_model` (2661) : le mode texte rendu sert tel quel, puisque `prompt_tokens = len(rendered.ids)`.
- `src/wavestack/config.py` -- `selected_model` (302) accepte déjà `server`. Lire les délais et le budget ici.
- `wavestack.toml` -- `[net.loopback_ports]` existe. Ajouter `[model_servers]` : `connect_timeout_s = 2`, `read_timeout_s = 300`. Ajouter `[models] memory_budget_mb = 4096`, sauf si la story 17 l'a posé.
- `src/wavestack/web/app.py` -- `SelectModelIntention.kind` (31) passe à `file | server | cloud`. `/api/diagnostic` (225) ajoute `selected` et `loaded`, de forme `{kind, ref}` ou `null`, et garde les champs existants.
- `src/wavestack/web/static/diagnostic.html` -- `renderCandidates` (≈115-155) : ligne serveur (tag Local, `provider · nom`, adresse, mémoire servie), « Choisir » → `select_model{kind: server, ref}` (`chooseModel`, 344) ; retirer « utilisable au palier 2 ».
- `src/wavestack/web/static/app.js` -- `renderModelIndicator` (1095) : tag « Local · {provider} », infobulle « Modèle servi par {provider} sur ce poste ({adresse}) : processus distinct de WaveStack ; le texte envoyé est construit par le harnais. ». `buildSchema` (3209) : la boîte `arch-cloud-model` (3255) sert d'exemple pour une boîte locale `arch-server-model`. `app.css` : style de cette boîte (jetons existants).
- Tests : `tests/fake_engine.py` (moteur factice, octet = token). `tests/test_cli_diagnostic.py:601` (`test_server_only_is_ready_without_a_file_to_load`) change de comportement. Les stubs `_server_candidates` de `test_cli_diagnostic.py:40`, `test_cloud.py:398`, `test_discovery.py:46` et `test_web_app.py:27` gardent leur signature `(cfg)`.
- `_bmad-output/implementation-artifacts/deferred-work.md`, première entrée : un test de `_server_candidates` avec un transport simulé la ferme.

## Tasks & Acceptance

**Execution:**
- [ ] `src/wavestack/models/engine.py` -- extraire `VocabTokenizer` (`tokenize`, `token_pieces`, `metadata`, `close`) et le faire utiliser par `LlamaCppEngine` -- un seul code de tokenizer local (AD-5, `ollama_raw`).
- [ ] `src/wavestack/net/factory.py` -- `create_loopback_client(timeout, transport=None)` : sans proxy, refuse (`NetworkBlocked`) tout hôte hors boucle locale -- AD-15, proxy d'entreprise en boucle locale (story 1e).
- [ ] `src/wavestack/models/servers.py` (nouveau) -- `LlamaServerEngine(url, transport=None)`, `OllamaRawEngine(url, name, gguf_path, n_ctx, tokenizer=None, transport=None)`, `list_served(cfg, transport=None)`, `served_bytes(...)` et `release_ollama(url, name)` (`keep_alive: 0`). Les erreurs HTTP deviennent une exception française (adresse, cause) -- AD-5, AD-8, AD-16.
- [ ] `src/wavestack/models/discovery.py` -- `_server_candidates(cfg, transport=None)` : un candidat par modèle servi, `ref`, `engine`, `served_bytes`, blob Ollama résolu par `_ollama_candidates`, `incompatible` avec la raison -- AD-7.
- [ ] `src/wavestack/models/capabilities.py` -- détection par le gabarit quand `architecture is None` -- AD-6.
- [ ] `src/wavestack/session/diagnostic.py` -- `selected_model` `server`, `booted_server`, `select_server(ref)` (même parcours que `_select_model_locked`, candidat relu par la découverte), `DiagnosticResult.server`, `hand_to` → `boot_server`. Serveurs seuls : contrôle `model` bloquant, jamais de choix d'office. Choix mémorisé repris si servi -- AD-7, AD-21.
- [ ] `src/wavestack/session/app_session.py` -- `boot_server`, `server_factory`, budget (AD-8), `release_ollama` en quittant un modèle Ollama et dans `close`, `active_model` et `core.model` (`process: external`, arête locale), fenêtre `server`. Brancher `kind: server` dans le changement à chaud de la story 17. Retirer `_SERVER_ONLY_FR`.
- [ ] `src/wavestack/web/app.py`, `static/diagnostic.html`, `static/app.js`, `static/app.css` -- intention `kind: server`, champs `selected` et `loaded`, lignes serveur, indicateur, boîte du schéma. Le sélecteur de modèle de la story 17 liste aussi les modèles servis.
- [ ] `wavestack.toml`, `README.md` -- délais `[model_servers]`, budget, section française « Utiliser un serveur déjà lancé (Ollama, llama-server) » : lancement du serveur par l'utilisateur, ports, `raw`, transparence réduite, `keep_alive`.
- [ ] `tests/test_model_servers.py` (nouveau) -- une ligne de la matrice par test, par `httpx.MockTransport` et un tokenizer factice octet = token. À vérifier aussi : corps envoyés (ids, `num_ctx`, `raw`), `_server_candidates` (ferme l'entrée de `deferred-work.md`), refus d'un hôte non local par le client boucle locale, `keep_alive: 0` à la fermeture. Adapter `test_cli_diagnostic.py:601` au choix bloquant.

**Acceptance Criteria:**
- Given un llama-server simulé qui sert un modèle, when l'utilisateur le choisit au diagnostic puis envoie un message, then Contexte LLM montre le texte rendu par le harnais, gabarit compris, et la somme des segments égale `prompt_tokens`.
- Given un modèle servi actif, when la page est rechargée, then l'indicateur « Local · {provider} » et le robot hors du cadre Harnais, en zone Poste de travail, réapparaissent depuis `/api/state` et `/api/architecture` (AD-1).
- Given un modèle Ollama actif, when l'utilisateur choisit un autre modèle ou ferme WaveStack, then le transport simulé reçoit `keep_alive: 0` pour ce modèle, et aucun moteur en processus ne coexiste avec le modèle servi.
- Given aucun serveur, when on lance la suite, then `uv run python -m pytest` passe, et le rendu de référence Qwen3.5 et les scénarios fournis restent inchangés.

## Spec Change Log

## Review Triage Log

## Design Notes

Le port garde `complete(ids)`. `ollama_raw` rebâtit son texte par ses propres pièces, que le contrôle 6 d'AD-4 garantit égales à `rendered.prompt` : cela évite d'ajouter `RenderedPrompt` au port et de toucher le moteur factice. Même esprit pour `llama_server` : les ids qu'il reçoit sont ceux qu'il a lui-même produits par `/tokenize`, donc la jauge est exacte sans tokenizer local.

Esquisse du dispatch au démarrage :

```python
if result.cloud_model: app_session.boot_cloud(result.cloud_model)
elif result.server:    app_session.boot_server(result.server)  # ModelCandidate, engine + ref
elif result.model_path or (launch and result.ready): app_session.boot(result.model_path)
```

## Hypothèses à valider

1. **Dépendance à la story 17.** Elle est livrée avant celle-ci et fournit `select_model` à chaud (classe b), le sélecteur de modèle de la barre haute et le contrôle de budget d'AD-8. La story 18 y ajoute seulement `kind: server` et le coût du modèle servi. Si le contrôle de budget manque au démarrage de l'implémentation, créer `src/wavestack/models/budget.py`, avec `check_budget(cost_bytes, freed_bytes) -> str | None` : RSS psutil de WaveStack et de ses enfants, moins la mémoire libérée, plus le coût, comparé à `[models] memory_budget_mb`. Si le changement à chaud manque, le choix d'un serveur après chargement suit la règle « prochain lancement » existante.
2. **Jamais choisi d'office.** Un modèle servi n'entre pas dans la règle « un seul fichier utilisable » de la story 1b, car le choisir fait charger le modèle par Ollama, hors de WaveStack. Serveurs seuls : choix bloquant. Le comportement actuel « prêt sans modèle » disparaît.
3. **Texte d'Ollama.** Il est reconstruit à partir des ids (voir Design Notes), sans nouveau champ au port.
4. **Transparence réduite.** La règle est appliquée à la lettre (`prompt_eval_count` ≠ compte du harnais). Hypothèse : les versions actuelles d'Ollama renvoient le compte complet même quand le cache sert. Le message cite les deux causes possibles (tokenisation d'Ollama, cache). Un champ `thinking` reçu en `raw` déclenche le même événement.
5. **Métadonnées de llama-server.** Elles viennent du serveur seul (`/props`, `/v1/models`, `/tokenize`), sans `vocab_only`. La famille est détectée par le gabarit, puisque l'architecture n'est pas exposée. L'hypothèse s'appuie sur les champs actuels de llama-server (`model_path`, `default_generation_settings.n_ctx`, `with_pieces`, `parse_special`), non vérifiés ici faute de réseau.
6. **Qwen3.5 d'Ollama et `vocab_only`.** llama-cpp-python 0.3.35 lit les hyperparamètres même en `vocab_only` : les blobs `qwen35` d'Ollama (deferred-work, story 9) peuvent y échouer. L'échec est alors une raison affichée, pas un plantage. llama-server, qui tokenise lui-même, reste la voie pour ces modèles.
7. **Client sans proxy.** Il est réservé à la boucle locale : avec `HTTP_PROXY` défini sur le PC pro, un client `trust_env` enverrait `127.0.0.1` au proxy.
8. **`keep_alive: 0`.** Il est envoyé au changement de modèle et à la fermeture de WaveStack, lecture de « en quittant Ollama ». Au lancement, aucun préchargement : Ollama charge le modèle au premier appel, et le coût mesuré devient celui de `/api/ps` dès qu'il existe.
9. **Formes choisies ici.** Les refs `ollama/{nom}` et `llama_server/{fichier}`, ainsi que `process: "external"` sur `core.model`, sont des choix de forme de cette story : AD-12 ne fixe que `hosting`.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run python -m pytest` -- expected: tout passe, sans accès réseau
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur

**Manual checks (if no CLI):**
- Avec `ollama serve` (un modèle au GGUF lisible) puis `llama-server -m <gguf> --port 8080`, lancés à la main : les deux apparaissent au diagnostic. Choisir chacun, faire un tour avec `get_datetime` et vérifier le texte rendu, les tokens, le schéma (robot hors du Harnais), l'indicateur et `ollama ps` vide après un changement de modèle.

## Auto Run Result

Status: ready-for-dev
Blocking condition: aucune (arrêt demandé après la planification)
