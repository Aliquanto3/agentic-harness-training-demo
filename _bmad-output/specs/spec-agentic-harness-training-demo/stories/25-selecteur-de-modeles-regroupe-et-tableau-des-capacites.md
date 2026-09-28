---
title: 'Sélecteur de modèles regroupé et tableau des capacités'
type: 'feature'
created: '2026-09-28'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/24-modeles-memoire-comptee-juste-budget-dynamique-sonde-interruptible.md'
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/33-contrastes-et-code-couleur-par-discipline.md'
  - '{project-root}/tools/e2e/README.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Demande du 2026-09-28. Le sélecteur « Changer de modèle… » liste les modèles dans l'ordre de la découverte, en deux blocs (« Sur ce poste », « Réseau »). Le préfixe « Local · Ollama » n'est expliqué nulle part, et rien ne dit, avant de charger un modèle, s'il appelle des outils ou s'il raisonne toujours, jamais ou à la demande. Les modèles servis n'ont ni éditeur ni taille (`architecture` et `size_label` ne viennent que de la sonde des fichiers).

**Approach:** Un module côté Python, `models/catalog.py`, décrit chaque modèle disponible : éditeur (table en contenu YAML), taille (paramètres, sinon octets), hébergement et qui le sert, fenêtre, appel d'outils et mode de raisonnement. Les capacités sortent de `capabilities_for` et de `cloud_capabilities`, les fonctions dont la session tire les cartes des briques. Il regroupe (hébergement, puis éditeur) et trie (taille croissante). `/api/diagnostic` porte ce résultat ; le sélecteur l'affiche avec une légende du préfixe, et une nouvelle page `/models` (onglet « Modèles » à côté de « Diagnostic ») en fait un tableau.

## Boundaries & Constraints

**Always:**
- `uv`, `ruff`, `pytest` ; code et identifiants en anglais, textes d'interface en français.
- Une seule vérité des capacités. La table appelle `capabilities_for(EngineMetadata)` avec les mêmes entrées que la session au chargement :
  - fichier et blob Ollama : l'en-tête GGUF lu par `gguf_meta` ;
  - llama-server : `architecture=None` et le `chat_template` de `/props` ;
  - modèle cloud : `cloud_capabilities(entry)`, extrait de `AppSession._install_cloud` et utilisé par lui.
  La fenêtre suit la même règle que `_install` (AD-9).
- Regroupement, tri et libellés calculés en Python (AD-1). Le navigateur affiche la liste reçue ; il ne marque que « (actif) », d'après `store.activeModel`, comme aujourd'hui.
- Table des éditeurs dans `content/models/publishers.yaml` (AD-19). Un fichier invalide ne plante rien : tous les modèles vont dans « Autres éditeurs », et la page `/models` affiche la raison.
- Aucune lecture qui charge un modèle. L'en-tête GGUF est lu en Python pur (`gguf_meta.try_read_metadata`), mémorisé par (chemin, taille, mtime). Pour Ollama, seul `/api/tags` est lu (champ `details`) : ni `/api/show`, ni requête par modèle.
- Aucune dépendance nouvelle et aucun vrai modèle dans le conteneur. On utilise les doublures du dépôt : GGUF synthétiques (`tests/gguf_writer.py`), faux serveurs (`tests/test_model_servers.py`, `tools/e2e/fake_local_server.py`), faux fournisseurs (`tools/e2e/stack.py`).
- Jetons de couleur seulement, dans `models.html` comme dans `app.css` et `app.js` (story 33). Le jaune réseau toujours doublé de « RÉSEAU ».
- Mettre à jour EXPERIENCE.md, DESIGN.md (prose), SPEC.md (CAP-34, CAP-35), README et le spine (AD-6, AD-7). Compléter le parcours E2E.
- Adapter les tests existants qui figent les libellés, sans les supprimer. Garder `pytest` entièrement vert.

**Never:**
- Charger, sonder ou tokeniser un modèle pour remplir la table.
- Deviner une capacité hors de `Capabilities` : pas de « toujours » local tant que `capabilities_for` ne le dit pas.
- Changer le comportement des briques.
- Toucher au budget mémoire, à la sonde ou au coût des modèles (story 24), à la fenêtre réglable (story 26) ou au mode sombre (story 31).
- Nouvel événement du journal ; nouveau jeton de couleur.
- Supprimer « Autre fichier ou clé API… », qui reste la dernière entrée.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fichier Qwen | `Qwen3.5-2B-Q4_K_M.gguf`, en-tête `general.architecture=qwen35`, `size_label=2B`, gabarit avec `enable_thinking` et `<tool_call>` | Groupe « Sur ce poste · Qwen (Alibaba) », option « Local · fichier · Qwen3.5-2B-Q4_K_M.gguf · 2B », outils « oui », raisonnement « activable » | — |
| Ollama sans blob lisible | `faux-ollama:latest`, `details {family: qwen3, parameter_size: 0.6B}` | Qwen, 0.6B, option grisée « (incompatible) » ; outils et raisonnement « inconnu », avec la raison de la découverte (« introuvable ») | — |
| llama-server | `/props` : gabarit Qwen3.5, `model_path` absent du disque ; nom `faux-llama-server.gguf` | Qwen, par la famille `qwen3` de `capabilities_for` (jamais Llama pour « llama-server ») ; taille = `meta.size` en Go ; fenêtre = min(configurée, native, contexte d'un emplacement) | En-tête illisible : éditeur par la famille, puis par le nom |
| Cloud qui raisonne toujours | `reasoning.always = true`, `tools = true` | Raisonnement « toujours », outils « oui (déclaré) » | — |
| Cloud sans déclaration | `reasoning` absent, `tools = false` | « jamais », « non » avec la raison « non déclaré » | — |
| Gabarit `<think>` sans variable | famille inconnue, `<think>` dans le gabarit | « inconnu » : « raisonne peut-être de lui-même, WaveStack ne sait ni l'allumer ni l'éteindre » | Brique Raisonnement indisponible, comme aujourd'hui |
| Sans gabarit | GGUF sans `tokenizer.chat_template` | « inconnu » avec `incompatible_reason` | — |
| Tri | 4B, 0.6B, taille inconnue de 1,5 Go, taille inconnue sans octets | 0.6B, 4B, puis 1,5 Go, puis le reste par nom | Égalité : par nom, insensible à la casse |
| Taille dans le nom | `openai/gpt-oss-120b`, `llama3.2:3b`, `mistral-small-latest` | 120B, 3B, inconnue | `Q4_K_M`, `3.5` ne sont pas des tailles |
| Éditeur inconnu | `wavestack-fake` | Groupe « Autres éditeurs », dernier de son hébergement | — |
| YAML invalide | regex fausse ou clé manquante | Tous en « Autres éditeurs », `publishers_error_fr` dans la réponse | Jamais d'exception |

</intent-contract>

## Code Map

Numéros de ligne indicatifs : les stories 33, 23, 34, 32 et 24 modifient `app.js`, `app.css`, `diagnostic.html`, `diagnostic.py`, `app_session.py` et `run_e2e.py` avant celle-ci. Se repérer aux symboles.

- `src/wavestack/web/static/app.js`
  - `renderModelIndicator` (l.~1952 ; tags « Local », « Local · {provider} », « RÉSEAU · {provider} », inchangés).
  - `PICK_OTHER`, `modelKey`, `loadModelList` (`GET /api/diagnostic`, rechargé par `scheduleModelList`), `pickerOption`, `renderModelPicker` (libellé du bouton d'application selon la valeur notée).
  - `rebuildModelPicker` (l.~2045) : deux `optgroup` construits dans le navigateur. Serveurs : « Local · {provider} · {name} » plus « (actif) » ou « (incompatible) ». Fichiers : `{name} · {size_label}`, dédoublonnés par `path`. Cloud : « RÉSEAU · {provider} · {model} » plus « (indisponible) ». Aucun tri.
  - `applyPick` : `kind:ref`, `cloud:` passe par `openCloudWarning`.
- `src/wavestack/web/app.py` -- `create_app` : `index_page` et `diagnostic_page` (`FileResponse`, `_revalidate_pages`) ; `diagnostic_state` (l.~264 : `candidates`, `loaded`, `cloud = session.cloud_rows(...)`, `app_session.active_choice()`).
- `src/wavestack/models/discovery.py`
  - `ModelCandidate` (l.~24 ; `architecture` et `size_label` viennent seulement du cache de sonde).
  - `_ollama_candidates` (blobs `found`, `name` = `model:tag`).
  - `_server_candidates` : `ServedModel` en main, `candidate.gguf_path` (blob Ollama ou `model_path` de llama-server). La story 24 y passe `cfg.context_window` à `served_bytes`.
  - `discover()` : ordre AD-7 (fichiers, cache HF, LM Studio, Ollama, serveurs), et `name` = nom du fichier.
- `src/wavestack/models/servers.py`
  - `ServedModel` (dataclass) ; `_served_by` : Ollama `/api/tags` (ignore `details`) et `/api/ps` ; llama-server `/props` (`model_path`, `chat_template` lus puis jetés) et `/v1/models` (`meta.size`, `n_ctx_train`).
  - `LlamaServerEngine._read_metadata` : `EngineMetadata(architecture=None, chat_template=props…, native_context=n_ctx_train, server_context=…)`, la référence à imiter.
- `src/wavestack/models/capabilities.py` -- `Capabilities`, `capabilities_for`. Famille `qwen3` par l'architecture ou par le gabarit : `tool_call_parser` hermes ou qwen3_coder, `reasoning` = variable `enable_thinking`. Sinon `tool_call_parser=None` et `reasoning_tags` si `<think>`.
- `src/wavestack/models/gguf_meta.py` -- `try_read_metadata(path)`, lecteur Python pur qui saute le vocabulaire. `probe.gguf_kv_bytes_per_token` l'utilise déjà dans le processus principal.
- `src/wavestack/session/app_session.py`
  - `_install` : `capabilities_for(engine.metadata())`, `effective_window(configured, native)`, puis `meta.server_context`.
  - `_install_cloud` : `Capabilities(...)` en ligne, à extraire.
  - `_capability_reason`, `_no_reasoning_fr`, `_always_fr`, `_CAPABILITIES_FR` : textes des cartes, à garder cohérents avec la table.
- `src/wavestack/context/window.py` -- `effective_window`. `config.py` -- `CloudModel` (`tools`, `reasoning`, `always_reasons`, `context`), `cloud_window`, `Config.cloud_models`, `Config.context_window`, `content_dir()`.
- `src/wavestack/session/diagnostic.py` -- `_discover` (état final des candidats : incompatibles par la sonde) ; `cloud_rows` (`disabled_fr`, `loaded`).
- `src/wavestack/cloud.py` -- `load_cloud_content` (`@cache`, pydantic) : le modèle de chargeur à suivre.
- `src/wavestack/web/static/diagnostic.html` -- page autonome : style en ligne, `#checks`, `#candidates`, `#cloud-models`, `#open-link`.
- `src/wavestack/web/static/index.html` -- `#model-picker`, `#model-picker-apply` dans `.top-bar`. `tokens.css` et `fonts.css` sont réutilisables par une nouvelle page.
- `tools/e2e/fake_local_server.py` -- `tags` (Ollama : un modèle, `size`, sans `details`), `props`, `models`. `tools/e2e/stack.py` -- `settings` : trois entrées cloud A, B et R (R raisonne toujours, story 33), noms sans éditeur connu.
- `tools/e2e/run_e2e.py`
  - `_picker_options` (libellé vers désactivé).
  - `s_model_switch` : `a_label`, `b_label` ; vérifie que la dernière entrée est « Autre fichier ou clé API… ».
  - `s_local_server` : `LLAMA_OPTION`, « Local · Ollama · faux-ollama:latest (incompatible) ».
  - `SCENARIOS`, `Run.shot`.
- Tests :
  - `tests/test_discovery.py`, `tests/test_model_servers.py` (`FakeServer._ollama` et `_llama`, `_candidate`) ;
  - `tests/test_web_app.py` (routes de pages) ;
  - `tests/test_web_tokens.py` (`test_app_css_and_js_write_no_color_outside_the_tokens`) ;
  - `tests/fake_engine.py` (`FakeEngine.metadata`) ;
  - `tests/test_reasoning.py` (cloud qui raisonne toujours).

## Tasks & Acceptance

**Execution:**
- `content/models/publishers.yaml` (nouveau) -- Écrire la liste ordonnée `publishers: [{id, label_fr, architectures: [préfixes], names: [regex]}]` :
  - Qwen (Alibaba) ; Llama (Meta), par le nom seul (`llama[-_. ]?\d`), car l'architecture `llama` est ambiguë ;
  - Gemma (Google), Granite (IBM), Phi (Microsoft) ;
  - Mistral (Mistral AI), sur les noms `mistral`, `ministral`, `magistral`, `devstral`, `codestral` ;
  - LFM (Liquid AI), Nemotron (NVIDIA), gpt-oss (OpenAI), MiniCPM (OpenBMB) ;
  - `other_fr: Autres éditeurs`.
  Ajouter les textes de légende (`legend_fr`, `served_by_fr` : fichier, Ollama, llama-server) et un commentaire d'en-tête. La table reste en contenu, pas en code (AD-19).
- `src/wavestack/models/capabilities.py` --
  - `cloud_capabilities(entry: CloudModel) -> Capabilities`, déplacé depuis `_install_cloud`.
  - `reasoning_mode(caps | None) -> Literal["never","always","toggle","unknown"]`, avec sa raison en français :
    - `None` ou `incompatible_reason` : `unknown` ;
    - `reasoning_always` : `always` ;
    - `reasoning` : `toggle` ;
    - `reasoning_tags` sans `reasoning` : `unknown` ;
    - sinon `never`.
  - `tools_summary(caps)`, qui reprend le texte de `_CAPABILITIES_FR` pour « non ».
  Ce sont les règles des cartes, en un seul endroit.
- `src/wavestack/context/window.py` -- `window_for(meta: EngineMetadata, configured) -> tuple[int, str]` : `effective_window`, puis `server_context`. `_install` l'utilise. La même fenêtre s'affiche dans la table et dans la jauge.
- `src/wavestack/session/app_session.py` -- `_install_cloud` appelle `cloud_capabilities(entry)`, et `_install` appelle `window_for`. Comportement inchangé.
- `src/wavestack/models/servers.py` -- `ServedModel` reçoit `family`, `parameter_size` (depuis `details` de `/api/tags`), `chat_template` et `n_ctx_train` (depuis `/props` et `/v1/models` de llama-server). Aucune requête en plus.
- `src/wavestack/models/catalog.py` (nouveau) --
  - `load_publishers()` : `@cache`, pydantic, regex compilées ; en cas d'erreur, table vide et `error_fr`.
  - `publisher_for(architectures, names) -> Publisher` : d'abord les préfixes d'architecture (en-tête, `details.family`, `caps.family` hors `unknown` et `openai_chat`), puis les regex sur les noms (`general.basename`, `general.name`, nom affiché, `model` cloud), puis « Autres ».
  - `parse_params(text) -> float | None` : « 2B », « 0.6B », « 270M », « 8x7B » = 56, « 30B-A3B » = 30, ou dans un nom avec des bornes non alphanumériques.
  - `header_metadata(path)` : `EngineMetadata` et en-tête brut, mémorisés par (chemin, taille, `mtime_ns`).
  - `ModelEntry` (pydantic) : `value` (`file:`, `server:` ou `cloud:` + ref), `kind`, `ref`, `hosting` (`local` ou `network`), `served_by_fr`, `prefix_fr` (« Local · Ollama », « RÉSEAU · Groq »), `name`, `label_fr` (préfixe · nom · taille), `publisher_id`, `publisher_fr`, `params_b`, `params_label`, `size_bytes`, `window`, `native_context`, `tools`, `tools_fr`, `reasoning`, `reasoning_fr`, `reason_fr`, `usable`, `disabled_fr`.
  - `local_entries(candidates, cfg)`, qui dédoublonne les fichiers par chemin comme aujourd'hui, et `cloud_entries(cfg, rows)`, où `disabled_fr` vient de `cloud_rows`.
  - `group_models(entries) -> [{hosting, publisher_id, label_fr, models}]` : Local avant Réseau, éditeurs dans l'ordre du YAML, Autres en dernier, groupes vides omis. Tri par (taille en paramètres inconnue, paramètres, octets inconnus, octets, nom insensible à la casse).
  Tout le calcul reste en Python, une fonction par règle, testable.
- `src/wavestack/models/discovery.py` -- `ModelCandidate` reçoit plusieurs champs, que `_server_candidates` et `discover()` remplissent :
  - `publisher_hint` (famille Ollama), `params_label` (`parameter_size`), `size_bytes` (taille du fichier, ou `size` du serveur) ;
  - `server_template` et `native_context` (llama-server), déclarés `Field(default=None, exclude=True)` : le gabarit ne part pas dans le JSON de `/api/diagnostic`.
  Aucune lecture d'en-tête ici : le catalogue la fait et la mémorise.
- `src/wavestack/web/app.py` -- Dans `diagnostic_state`, ajouter `"models": {"legend_fr", "groups", "publishers_error_fr"}`, construit par `catalog` à partir de `result.candidates`, `cfg` et `cloud_rows`. Ajouter `@app.get("/models")`, qui sert `models.html`. Une seule réponse sert le sélecteur et la page.
- `src/wavestack/web/static/app.js` -- `rebuildModelPicker` lit `store.modelList.models.groups`.
  - Un `optgroup` par groupe, libellé « Sur ce poste · {éditeur} » ou « Réseau · {éditeur} ».
  - Chaque option porte `label_fr`, suivi de « (actif) » d'après `modelKey`, ou « (incompatible) » / « (indisponible) » avec `disabled_fr` en infobulle.
  - Juste après « Changer de modèle… », une option désactivée de légende : `legend_fr`.
  - Avant « Autre fichier ou clé API… », l'entrée « Tableau des modèles et de leurs capacités… » (`PICK_MODELS`) : le bouton affiche « Ouvrir le tableau », et `applyPick` ouvre `/models` dans le même onglet. L'infobulle du sélecteur reprend la légende.
  - Repli sur l'ancienne construction si `models` est absent.
  Aucune couleur écrite en dur.
- `src/wavestack/web/static/models.html` (nouveau) -- La page « Modèles disponibles » :
  - `fonts.css` et `tokens.css`, style en jetons seulement ;
  - `<nav class="page-tabs">` : « Diagnostic » (`/diagnostic`), « Modèles » (`aria-current="page"`), « Ouvrir WaveStack » (`/`) ;
  - la légende ;
  - un `<table>` avec une `<caption>`, un `<tbody>` par groupe et son en-tête `th scope="rowgroup"`. Colonnes : Modèle (préfixe en `hosting-tag-local`, ou `hosting-tag-network` avec 🌐 RÉSEAU), Éditeur, Taille (« 2B · 1,3 Go », « — » si inconnue), Hébergement (qui le sert, et `hosting_fr` pour le cloud), Fenêtre (« 4 096 tokens », native en infobulle), Appel d'outils, Raisonnement (mot, et raison visible sous le mot quand elle est inconnue), État (actif, incompatible ou indisponible, avec la raison) ;
  - une ligne sous la table : « Capacités lues comme au chargement : mêmes règles que les cartes des briques. » ;
  - l'erreur de `publishers.yaml` affichée en tête si présente ;
  - un seul `fetch("/api/diagnostic")` au chargement, lecture seule.
- `src/wavestack/web/static/diagnostic.html` -- Ajouter la même `nav.page-tabs` en haut (« Diagnostic » courant), additive. Le reste de la page ne change pas.
- `tools/e2e/fake_local_server.py` -- `tags` : ajouter `details: {family: "qwen3", parameter_size: "0.6B"}` au faux modèle Ollama. Le tri et l'éditeur deviennent observables sans vrai Ollama.
- `tools/e2e/run_e2e.py`, `tools/e2e/README.md` --
  - Mettre à jour les libellés figés : faux Ollama « Local · Ollama · faux-ollama:latest · 0.6B (incompatible) ». `LLAMA_OPTION` et les libellés cloud restent inchangés (taille inconnue).
  - Nouveau scénario `s_model_catalog`, après `local_server`, pour les vérifications ci-dessous.
  - Captures `modeles-selecteur` (liste ouverte, ou `optgroup` lus) et `modeles-tableau`, numérotées à la suite des captures existantes, ajoutées à la liste du README.
- `tests/test_model_catalog.py` (nouveau), `tests/test_discovery.py`, `tests/test_model_servers.py`, `tests/test_web_app.py`, `tests/test_web_tokens.py` --
  - Toute la matrice I/O : éditeurs, dont un cas par éditeur de la liste ; tailles ; tri ; groupes ; modes de raisonnement, sur des GGUF synthétiques avec gabarit ; cloud ; YAML invalide ; mémorisation de l'en-tête.
  - `details` d'Ollama et gabarit de llama-server gardés dans `ServedModel`.
  - `/api/diagnostic.models`, et `/models` qui répond 200.
  - Cohérence : pour une même `EngineMetadata` (`FakeEngine`) ou une même entrée cloud, `reasoning_mode` vaut `toggle` si et seulement si la carte Raisonnement est disponible après le chargement dans `AppSession`, et `always` si et seulement si `always_fr` est non vide.
  - Ajouter `models.html` à l'interdiction des couleurs hors jetons.
- `EXPERIENCE.md`, `DESIGN.md` (prose), `SPEC.md`, `README.md`, `ARCHITECTURE-SPINE.md` --
  - EXPERIENCE : ligne `model-picker` (groupes, préfixe, légende, tri, entrée « Tableau… »), et nouvelles lignes `models-page` et `page-tabs`.
  - DESIGN : composants `model-table` et `page-tabs`, faits de jetons existants.
  - SPEC.md : CAP-34 (sélecteur regroupé et trié), CAP-35 (tableau des capacités de tous les modèles disponibles).
  - README : section « Changer de modèle ».
  - Spine : AD-6 (table et session partagent `capabilities_for` et `cloud_capabilities`), AD-7 (`details` d'Ollama et gabarit de llama-server gardés), AD-19 (`content/models/publishers.yaml`).

**Acceptance Criteria:**
- Given la pile E2E (faux llama-server, faux Ollama avec `details`, trois faux cloud), when on lit `#model-picker`, then :
  - la deuxième option est la légende désactivée, qui contient « où tourne le modèle » et « qui le sert » ;
  - les `optgroup` sont « Sur ce poste · Qwen (Alibaba) », « Sur ce poste · Autres éditeurs » s'il existe, puis « Réseau · Autres éditeurs », dans cet ordre ;
  - dans le groupe Qwen, « Local · Ollama · faux-ollama:latest · 0.6B (incompatible) » précède `LLAMA_OPTION` ;
  - chaque option de modèle commence par « Local · » ou « RÉSEAU · » ;
  - l'avant-dernière option est « Tableau des modèles et de leurs capacités… », la dernière « Autre fichier ou clé API… ».
- Given l'entrée « Tableau des modèles… » notée, when on clique « Ouvrir le tableau », then `/models` s'affiche, l'onglet « Modèles » a `aria-current="page"`, et l'onglet « Diagnostic » mène à `/diagnostic`, qui porte les mêmes onglets.
- Given la page `/models`, when on lit les lignes, then :
  - `faux-llama-server.gguf` : éditeur « Qwen (Alibaba) », outils « oui », raisonnement « activable », fenêtre « 4 096 tokens » ;
  - le faux modèle R : « toujours » ;
  - `wavestack-fake` : « jamais » ;
  - `faux-ollama:latest` : « inconnu », avec une raison visible qui contient « introuvable » ;
  - chaque ligne réseau montre « RÉSEAU » ;
  - la ligne du modèle actif dit « actif ».
- Given le faux modèle R activé depuis le sélecteur, when on compare la carte Raisonnement (verrouillée, story 33) et la ligne R de `/models`, then les deux disent qu'il raisonne toujours. Revenu à l'entrée A, sa ligne dit « jamais », et la carte Raisonnement est indisponible avec la raison « ne déclare pas de raisonnement ».
- Given un `content/models/publishers.yaml` invalide, when `/api/diagnostic` est lu, then la réponse est 200, tous les groupes sont « Autres éditeurs », et `publishers_error_fr` nomme le fichier.

## Spec Change Log

## Review Triage Log

## Design Notes

- Un `<select>` natif n'imbrique pas les `optgroup` : le niveau hébergement passe dans le libellé du groupe (« Sur ce poste · Qwen (Alibaba) »), et l'option garde le préfixe complet. On garde le `select` natif, accessible au clavier, avec le modèle « noter puis Charger » de la story 17.
- Légende en option désactivée : visible exactement quand la liste est ouverte, sautée par les flèches du clavier, et sans place à trouver dans la barre haute foncée de la story 33.
- L'éditeur passe d'abord par l'architecture, puis par le nom. L'architecture `llama` sert aussi à Mistral 7B et à SmolLM : Llama (Meta) se reconnaît donc au nom seul. « llama-server » ne ressemble pas à `llama[-_. ]?\d`.
- La fenêtre de la table est celle que WaveStack utiliserait au chargement (`window_for`, `cloud_window`) ; la native passe en infobulle. La story 26 (fenêtre réglable) n'aura qu'à changer `configured`.
- Exemple de `ModelEntry` : `{value: "server:llama_server/faux-llama-server.gguf", prefix_fr: "Local · llama-server", label_fr: "Local · llama-server · faux-llama-server.gguf", publisher_fr: "Qwen (Alibaba)", params_label: null, size_bytes: 1500000000, window: 4096, tools: true, tools_fr: "oui (hermes)", reasoning: "toggle", reasoning_fr: "activable"}`.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, `test_model_catalog.py` compris
- `node --check src/wavestack/web/static/app.js` -- expected: pas d'erreur
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; `s_model_catalog` passe ; captures de `tools/e2e/screenshots` mises à jour et commitées

**Manual checks (if no CLI):**
- Captures `modeles-selecteur` et `modeles-tableau` : groupes lisibles, légende visible, aucune couleur hors jetons, « RÉSEAU » présent sur chaque ligne jaune.

## Décisions prises par défaut

- **Page dédiée plutôt qu'un onglet dans `diagnostic.html`.** L'onglet « Modèles » est une page `/models`, reliée au diagnostic par une barre d'onglets commune. Raisons : la page de diagnostic (640 px, style en ligne) est modifiée par la story 24 et figée par l'E2E, et un tableau à huit colonnes demande de la largeur.
- **Regroupement et tri côté Python, livrés dans `/api/diagnostic`.** Une seule réponse sert le sélecteur et la page, les règles sont testables par `pytest` (AD-1), et aucun appel HTTP ne s'ajoute.
- **Deux niveaux dans un seul libellé de groupe.** « Sur ce poste · {éditeur} », parce que le `select` natif n'imbrique pas les groupes. On garde le `select` natif plutôt que d'écrire une liste personnalisée : accessibilité, E2E existant, portée de la story.
- **Même préfixe pour toutes les options.** « Local · fichier » (y compris un blob Ollama chargé par WaveStack), « Local · Ollama », « Local · llama-server », « RÉSEAU · {fournisseur} ». L'indicateur de modèle garde ses textes actuels : hors périmètre, et figé par l'E2E.
- **Légende en option désactivée**, doublée de l'infobulle du sélecteur et d'un paragraphe de la page `/models` : aucune place dans la barre haute.
- **Taille** : le libellé de paramètres (`general.size_label`, puis `parameter_size` d'Ollama, puis le nom), sinon les octets. Le sélecteur n'affiche que les paramètres ; la table montre les deux. Tri : paramètres connus d'abord, puis octets, puis nom.
- **Ollama : `/api/tags` seul.** `details.family` et `parameter_size` suffisent, sans N requêtes `/api/show` à chaque diagnostic.
- **llama-server : les capacités par `/props`** (`architecture=None`), comme `LlamaServerEngine`, même si l'en-tête du fichier est lisible. C'est la seule façon d'avoir une seule vérité ; l'en-tête ne sert qu'à l'éditeur et à la taille.
- **Raisonnement « inconnu » pour un gabarit `<think>` sans variable.** Dérivé de `Capabilities` sans le changer : `capabilities_for` ne connaît pas de modèle local « toujours », et la carte reste indisponible comme aujourd'hui.
- **Cloud non déclaré = « jamais »**, avec la raison « non déclaré dans la configuration » (AD-6 : une capacité non déclarée est absente).
- **Taille d'un modèle cloud lue dans son nom seulement.** `mistral-small-latest` reste « — » : aucun champ de configuration nouveau.
- **Table des éditeurs en YAML dans `content/models/`**, avec des regex. Un fichier invalide range tout en « Autres éditeurs », jamais de plantage (AD-19).
- **Ouverture de `/models` dans le même onglet**, comme « Ouvrir le diagnostic ». Le rechargement restitue l'état (AD-1).
- **Fausse doublure Ollama enrichie de `details`** plutôt qu'un nouveau faux modèle : le tri et l'éditeur deviennent visibles en E2E au prix d'un seul libellé figé à changer.

## À vérifier sur PC

- **Geste** : Qwen3.5-2B et 4B en GGUF dans `models\`, Ollama lancé avec au moins `llama3.2:3b` et un modèle Qwen ; lancer WaveStack, ouvrir « Changer de modèle… » dans Chrome puis dans Edge. — **Attendu** : groupes « Sur ce poste · Qwen (Alibaba) » puis « Sur ce poste · Llama (Meta) », 2B avant 4B, préfixes « Local · fichier » et « Local · Ollama », légende lisible en tête de liste. — **Critère** : ordre et libellés exacts, aucun modèle dans « Autres éditeurs » parmi Qwen, Llama et Gemma ; légende entière visible sans troncature dans les deux navigateurs. — **Moyen** : Claude in Chrome ; Edge à la main.
- **Geste** : cliquer « Tableau des modèles et de leurs capacités… » puis « Ouvrir le tableau ». — **Attendu** :
  - Qwen3.5-2B et 4B : outils « oui », raisonnement « activable » ;
  - `llama3.2:3b` : outils « non », avec la raison, et raisonnement « jamais » ;
  - Groq gpt-oss-120b : « toujours », 120B ;
  - Mistral : « activable ».
  — **Critère** : chaque valeur correspond à l'état de la carte Raisonnement et de la carte Outils après avoir chargé le modèle (4 modèles au moins). — **Moyen** : script AppSession pour la comparaison, Claude in Chrome pour la page.
- **Geste** : lire la colonne « Fenêtre » du 2B, puis le charger et lire la jauge. — **Attendu** : même fenêtre. — **Critère** : égalité exacte. — **Moyen** : Playwright.
- **Geste** : en PowerShell, mesurer le temps de `/api/diagnostic` avec un cache Hugging Face ou LM Studio de 10 GGUF ou plus : `Measure-Command { Invoke-RestMethod http://127.0.0.1:<port>/api/diagnostic }`, deux fois. — **Attendu** : lecture des en-têtes rapide, mémorisée. — **Critère** : moins de 2 s au premier appel, moins de 200 ms au second. — **Moyen** : script ou à la main.
- **Geste** : Ollama avec un modèle dont le blob n'a pas de gabarit GGUF, ou un modèle de famille inconnue. — **Attendu** : ligne « inconnu » avec une raison compréhensible. — **Critère** : aucune ligne vide, aucune exception dans le terminal. — **Moyen** : Claude in Chrome.
- **Geste** : llama-server lancé avec `-c 4096` sur le 2B, puis le tableau. — **Attendu** : éditeur Qwen (par l'en-tête ou le gabarit), taille 2B si `model_path` est lisible, fenêtre 4 096. — **Critère** : valeurs exactes. — **Moyen** : Claude in Chrome.
- **Geste** : zoom à 125 % dans Chrome, page `/models`, depuis le fond de la salle. — **Attendu** : table lisible, onglets visibles, 🌐 RÉSEAU sur les lignes cloud. — **Critère** : aucune colonne coupée à 1600 × 1000 ; contraste jugé suffisant à l'œil. — **Moyen** : à la main.
