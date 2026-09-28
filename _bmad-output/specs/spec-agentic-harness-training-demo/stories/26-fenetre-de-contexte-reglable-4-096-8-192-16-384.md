---
title: 'Fenêtre de contexte réglable (4 096, 8 192, 16 384)'
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
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/25-selecteur-de-modeles-regroupe-et-tableau-des-capacites.md'
  - '{project-root}/tools/e2e/README.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Recette du 2026-09-28 (M4). Avec les trois serveurs MCP en lazy loading, charger une documentation fait déborder la fenêtre de 4 096 tokens. La fenêtre ne se règle que dans `wavestack.toml` (`[context] window`), alors que le spine (AD-9) la dit « réglable dans l'interface ». Rien ne montre ce qu'une fenêtre plus grande coûte en mémoire et en temps de lecture sur un CPU. Décision du 2026-09-28 : 4 096 par défaut, 8 192 ou 16 384 au choix.

**Approach:** Un réglage « Fenêtre » dans la barre haute ouvre un panneau avec les trois choix. Pour chacun, la session calcule le coût (AD-1) : mémoire du cache de contexte du modèle actif, temps de lecture d'une fenêtre pleine au débit mesuré, verdict du budget mémoire (AD-8) et borne native, serveur ou quota. Un nouvel événement porte ces chiffres. Une intention applique le choix :
- modèle local ou servi : rechargement par le chemin unique `_load`, budget contrôlé avant toute libération, conversation gardée ;
- modèle cloud : nouvelle fenêtre effective, sans rechargement (AD-9).
Le choix est mémorisé dans `settings.json` et repris au lancement suivant.

## Boundaries & Constraints

**Always:**
- `uv`, `ruff`, `pytest` ; code et identifiants en anglais, textes en français.
- Aucune dépendance nouvelle. Aucun vrai modèle dans le conteneur : faux moteur (`tests/fake_engine.py`), GGUF synthétiques (`tests/gguf_writer.py`), faux serveurs (`tests/test_model_servers.py`, `tools/e2e/fake_local_server.py`), faux fournisseurs (`tools/e2e/stack.py`).
- Défaut inchangé : sans réglage enregistré, la fenêtre vaut `[context] window` (4 096). Le test `test_every_scenario_fits_the_default_window_with_its_first_prompt` reste à 4 096, sans modification.
- Tous les chiffres et textes du panneau viennent de la session (AD-1, AD-2). Le front n'additionne rien.
- Classe b (AD-3) : accepté en `idle` seulement. Local et servi : budget contrôlé avant `_release` (AD-8) ; en cas d'échec ou d'« Arrêter », le modèle revient à l'ancienne fenêtre.
- Jamais deux modèles génératifs. La réserve de sortie garde sa règle (512 ou 1 536). La jauge, `usable`, l'aperçu et `context_overflow` suivent la fenêtre effective, déjà lue dans `self._window`.
- Réutiliser les apports des stories 24 et 25 s'ils sont livrés : `MemoryBudget` et son `calc_fr()`, `served_bytes(…, window)`, `window_for(meta, configured)`, `catalog`. Sinon, leurs équivalents actuels : `effective_window` + `server_context`, `file_cost`.
- Jetons de couleur seulement (story 33, `tests/test_web_tokens.py`).
- Mettre à jour EXPERIENCE.md, DESIGN.md, SPEC.md, README, `wavestack.toml` (commentaire) et le spine (AD-2, AD-8, AD-9). Compléter le parcours E2E. `pytest` complet vert.

**Never:**
- D'autres valeurs que 4 096, 8 192 et 16 384 par l'interface : une valeur saisie à la main dans la configuration reste lue, mais n'est pas proposée.
- Recharger un modèle cloud pour une fenêtre (AD-9 : effet au tour suivant).
- Lancer, arrêter ou reconfigurer Ollama ou llama-server : `-c` reste celui de l'utilisateur, la fenêtre y est bornée.
- Modifier les scénarios, leur contenu ou leurs consignes (story 27). Rendre le débit mesuré ou le verdict bloquants hors de l'application.
- Toucher à la sonde, au calcul du budget ou au coût Ollama au-delà du paramètre de fenêtre (story 24).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Local, accepté | Fichier actif à 4 096, KV 112 Kio/token, choix 8 192, tient dans le budget | `model_load_started` puis `model_load_ended{ok}` ; moteur recréé avec `n_ctx=8192` ; conversation gardée ; aperçu `window=8192`, `usable=7680` ; `settings.json` `context.window=8192` | — |
| Local, refus au budget | Choix 16 384, coût > budget | 409 : « Fenêtre de 16 384 tokens refusée : … », avec le budget et son calcul | Rien n'est libéré, écrit ni rechargé ; le modèle reste à 4 096 |
| Échec du rechargement | `engine_factory` lève pour `n_ctx=16384` | Le même modèle est rechargé à 4 096, `model_load_ended{restored}` | Réglage non enregistré |
| « Arrêter » pendant le rechargement | Jeton armé | `cancelled` ; modèle revenu à l'ancienne fenêtre | Réglage non enregistré |
| llama-server | `-c 8192`, choix 16 384 | Choix affiché « bornée à 8 192 par llama-server (-c) » ; fenêtre effective 8 192, `window_source=server` | — |
| Ollama | Choix 8 192 | `use_window(8192)` (`num_ctx`) ; coût = fichier + KV à 8 192 + marge, même quand Ollama le tient déjà en mémoire (il recharge) | KV illisible : fichier + marge, cache « inconnu » |
| Cloud | `context` 32 768, sans `tpm` ni `window` ; choix 8 192 | Sans rechargement : aperçu à 8 192 ; cache « chez le fournisseur, aucune mémoire sur ce poste » | — |
| Cloud borné | `tpm` 8 000 | Tous les choix « bornée à 4 000 par le quota du fournisseur » | — |
| Cloud à `window` déclaré | `window = 2048` | « Appliquer » désactivé, raison « fenêtre fixée par la déclaration du modèle » | — |
| Aucun modèle actif | Choix 8 192 | Enregistré ; s'applique au prochain chargement | — |
| Hors `idle` | Tour en cours | 409 avec `_refusal_reason()` | — |
| Valeur invalide | `{window: 5000}` | 422 « Intention invalide » | — |
| Débit inconnu | Aucun appel local mesuré | « Temps de lecture : pas encore mesuré, envoyez un message » | — |

</intent-contract>

## Code Map

Numéros de ligne omis : `app_session.py` bouge avec les stories 33, 23, 34, 32, 24 et 25. On se repère aux symboles.

- `src/wavestack/config.py`
  - `Config.context_window` : lit `[context] window`, 4 096 par défaut, déjà surchargé par `settings.json` par `_deep_merge` dans `load_config`.
  - `cloud_window(entry, configured) -> (window, source)` ; `OUTPUT_RESERVE`, `MAX_RESERVE`.
  - `save_setting`, `read_settings`. `settings.json` porte déjà `selected_model`.
- `src/wavestack/context/window.py`
  - `effective_window` ; `gauge(…, window, reserve, window_source)` pour `context_rendered`, `context_preview` et `context_reconciled`.
  - La story 25 y ajoute `window_for(meta, configured)`.
- `src/wavestack/session/app_session.py`
  - `__init__` : `self._window = self.cfg.context_window`, `self._window_source`, `LoadRegistry(...)`.
  - `_cost(choice)` : lit `self.cfg.context_window`. Serveur résident : `served_bytes` ; non résident : `file_cost` du blob, que la story 24 remplace. Fichier : `file_cost(ref, window)`.
  - `_checked` : serveur résident jamais refusé.
  - `switch_model` : garde `idle`, `check` avant libération, `_load_cancel`, `executor.submit(self._load, …)`.
  - `_load(choice, previous, probe, save)` : chemin unique. `_release`, `_checkpoint`, `_install`, `_last_checkpoint`, `_load_cancelled`, `_load_failed` (réinstalle `previous`), `_save_choice`. Le bloc `finally` émet `model_load_ended`, `idle`, `_emit_architecture`, `_emit_bricks`, `_emit_preview`.
  - `_install(choice)` : `configured = self.cfg.context_window`. Appels `_engine_factory(ref, n_ctx=)` et `_server_factory(server, n_ctx=)`, puis `effective_window` et `meta.server_context`, `engine.use_window(window)` (Ollama). En fin : `grant(label, self._cost(choice), …)`.
  - `_install_cloud(entry)` : `cloud_window(entry, self.cfg.context_window)`.
  - `emit_initial` ; `_emit_preview`, qui tourne sur le worker ; `_emit_overflow`, qui cite la fenêtre et la réserve ; `_availability` (`reasoning` si `self._window <= MAX_RESERVE`) ; `_refusal_reason` ; `stop`, qui arme `_load_cancel` en `model_load`.
  - Émission locale de `model_call_ended`, dans la fonction interne `end()` de la génération. Elle a `prompt_ms` et `evaluated_tokens` : c'est là qu'on relève le débit de lecture. Le cloud passe par `models/openai_chat.py`, sans relevé.
- `src/wavestack/models/load_registry.py`
  - `file_cost(path, window)` : sonde (`rss_bytes`, `probe_window`, `kv_bytes_per_token`), KV au-delà de la fenêtre de sonde, marge.
  - `check`, `_without`, `_size`. La story 24 y ajoute le calcul du budget.
- `src/wavestack/models/probe.py` -- `probed_entry(path)` (`kv_bytes_per_token`) ; `gguf_kv_bytes_per_token(path)`, lecteur Python pur de l'en-tête (blob Ollama, fichier jamais sondé).
- `src/wavestack/models/servers.py`
  - `OllamaEngine.use_window`, `num_ctx`.
  - `served_bytes`, `served_kv`, pour llama-server à son `n_ctx`. La story 24 ajoute `served_bytes(…, window)` pour Ollama.
  - `context_warning_fr(n_ctx, window, slot_ctx)`.
- `src/wavestack/session/diagnostic.py` -- `_probe_candidate` sonde à `self.cfg.context_window`, la fenêtre du lancement. `discovery._server_candidates` calcule `warning_fr` de llama-server à cette même fenêtre. Ces deux points restent inchangés.
- `src/wavestack/trace/catalog.py` -- `ContextWindowPayload` (`window_source`), `ContextOverflowPayload`, `PAYLOAD_MODELS`.
- `src/wavestack/session/effects.py` -- `SettingWrite`, `apply_setting`, l'applicateur unique (AD-23).
- `src/wavestack/web/app.py`
  - Modèles d'intention (`SelectModelIntention`…) ; `select_model`, modèle de route, avec 409 sur `SendRefused` ; `_diagnostic_class_b`.
  - `diagnostic_state`, où la story 25 construit `models` avec la fenêtre de chaque modèle.
- `src/wavestack/web/static/index.html` -- `.top-bar` : `#gauge` puis `#pane-chips`, `.pane-menu` (menu déroulant à imiter), `#model-picker`.
- `src/wavestack/web/static/app.js`
  - `applyEnvelope` : `switch` sur `kind`, `isLive`, `store` ; `renderGauge` (`root.title` « Fenêtre de … ») ; `renderModelPicker`, modèle « noter puis appliquer » ; `postIntention` ; `closePaneMenu` et la touche Échap ; `fmt`, qui sépare les milliers par U+202F.
- `src/wavestack/web/static/app.css` -- `.pane-menu`, `.pane-menu-list`, à imiter. Barre haute foncée de la story 33.
- `tools/e2e/run_e2e.py`
  - `s_model_switch`, `s_local_server` : bascule vers le faux llama-server (`N_CTX = 8192`, `n_ctx_train` 32 768), retour au faux cloud A (`context` 32 768).
  - `SCENARIOS`, `Run.check`, `Run.shot`, `r.stack.data_dir`.
- `tests/fake_engine.py` -- `FakeEngine`, `booted_session(engine, window=…)`, `engine_factory=lambda path, n_ctx: engine`. `tests/test_model_switch.py` : patrons de rechargement, de refus et d'arrêt. `tests/test_program.py` : test fits, inchangé.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/config.py` -- `WINDOW_CHOICES = (4096, 8192, 16384)` et `DEFAULT_WINDOW = 4096`. `Config.context_window` inchangé : un réglage enregistré arrive par `settings.json`, sous la clé `context.window`. -- Une seule liste, lue par l'intention et par le panneau.
- `src/wavestack/models/load_registry.py` -- `check_window(label, window, current, cost) -> str | None`. Même `_without` et même budget que `check`. Texte : « Fenêtre de {window} tokens refusée : {label} demanderait environ {coût} ; WaveStack occupe {base} sans le modèle actif, pour un budget de {budget} ({calcul, story 24}). {label} reste actif avec {current} tokens. Choisissez une fenêtre plus petite. » -- Le refus chiffré d'AD-8, propre à la fenêtre.
- `src/wavestack/context/window.py` -- Fonctions pures, testables :
  - `bound_fr(source, window, provider)` : textes par source. `native` : « bornée à N par le contexte natif du modèle ». `server` : « … par llama-server (-c) ». `tpm` : « … par le quota du fournisseur ». `override` : « fixée à N par la déclaration du modèle ».
  - `read_time_fr(window, tps)` : « au moins ≈ 45 s », « ≈ 1 min 40 s » ; au-delà de 30 s, ajouter « , au-delà des 30 s visées au premier token (NFR-1) ».
  - `kv_fr(bytes)`, au format `_size`.
- `src/wavestack/trace/catalog.py` -- Deux modèles pydantic, `WindowChoicePayload` et `ContextWindowStatePayload`, puis `"context_window_state"` dans `PAYLOAD_MODELS`. -- AD-2 : l'événement qui porte la fenêtre.
  - `WindowChoicePayload` : `window`, `effective`, `source`, `bound_fr | None`, `kv_bytes | None`, `kv_fr`, `read_s | None`, `read_fr`, `fits`, `refusal_fr | None`, `current`.
  - `ContextWindowStatePayload` : `configured`, `default`, `window`, `window_source`, `model_label | None`, `hosting` (`file|server|cloud|None`), `read_tps | None`, `read_note_fr`, `locked_fr | None`, `choices`.
- `src/wavestack/session/app_session.py` --
  - `self._configured_window` part de `cfg.context_window`, avec une propriété publique `configured_window`. Tout lecteur de `self.cfg.context_window` passe par elle : `_cost`, `_install`, `_install_cloud`.
  - `_cost(choice, window=None, *, reload=False)` : sans `reload`, le comportement actuel est inchangé. Avec `reload` (changement de fenêtre) :
    - un Ollama résident coûte comme un non résident à `window` ;
    - un fichier sans `kv_bytes_per_token` dans sa sonde ajoute `gguf_kv_bytes_per_token(ref) × window`.
  - `_install(choice, window=None)` : installe à `window` ; le `grant` final utilise ce même `window`.
  - `set_context_window(window) -> (message_fr, future | None)`, sous le verrou, en `idle` seulement (sinon `SendRefused`) :
    - valeur identique : « La fenêtre est déjà de N tokens. » ;
    - aucun modèle actif : enregistre et émet ;
    - cloud : refus avec `locked_fr` si `window` est déclaré ; sinon `cloud_window`, `self._window` mis à jour, enregistrement, puis sur le worker `_emit_preview`, `_emit_bricks` et `context_window_state` ;
    - local ou servi : `check_window` avec `_cost(active, window, reload=True)`, qu'on saute pour llama-server ; un refus émet `_error` et lève `SendRefused` ; sinon `model_load` et `_load_cancel`, puis `submit(self._load, active, active, None, False, window)`.
  - `_load(..., window=None)` :
    - libellé « Rechargement de {label} avec une fenêtre de N tokens… » ;
    - `_install(choice, window)` ;
    - succès : `self._configured_window = window`, enregistrement, `reason_fr` « Fenêtre de contexte : N tokens (conversation gardée). » ;
    - échec ou arrêt : `previous` réinstallé à l'ancienne fenêtre, rien d'enregistré.
  - `_save_window(n)` : `apply_setting(SettingWrite(key="context", value={**read_settings().get("context", {}), "window": n}))`. Un échec d'écriture est signalé comme dans `_save_choice`.
  - Débit : `end()`, hors cloud, relève `evaluated_tokens` (sinon `prompt_tokens`) / `prompt_ms` quand ≥ 64 tokens évalués et `prompt_ms` > 0, rangé dans `self._read_tps[model_label]`.
  - `_emit_window_state()` : construit les trois choix avec `window_for` (ou `effective_window` + `server_context`) et `cloud_window`, le KV et le débit, et le verdict par `check_window`. Appelée par `emit_initial`, dans le `finally` de `_load`, après un changement cloud et après `turn_ended`.
- `src/wavestack/web/app.py` -- Intention et route :
  - `ContextWindowIntention(window: Literal[4096, 8192, 16384])` ;
  - `POST /api/intentions/context_window` : `_diagnostic_class_b()`, puis `app_session.set_context_window`, avec 409 sur `SendRefused` ; réponse `{switching, message_fr}`.
  - Si `diagnostic_state` construit la colonne Fenêtre (story 25), lui passer `app_session.configured_window` au lieu de `cfg.context_window`.
- `src/wavestack/web/static/index.html`, `app.css`, `app.js` -- `window-picker` :
  - Après `#gauge`, un bouton `#window-toggle` « Fenêtre {effective} ▾ », avec `aria-haspopup="dialog"` et `aria-expanded`. Son infobulle donne la borne s'il y en a une.
  - Le panneau `#window-panel`, `role="dialog"`, fermé par Échap, « Fermer » ou un clic dehors. Il contient :
    - le titre « Fenêtre de contexte » ;
    - l'aide « Les scénarios sont conçus pour 4 096 tokens. Une fenêtre plus grande coûte de la mémoire et du temps de lecture. » ;
    - trois radios `name="window-choice"`, avec « (actuelle) » sur le choix courant ; sous chacune, `kv_fr`, `read_fr` et `bound_fr`, puis « Tient dans le budget » ou `refusal_fr` en style danger ;
    - `read_note_fr` ;
    - « Appliquer », désactivé hors `idle`, sur la valeur courante, sur un choix refusé, ou avec `locked_fr` ; la raison va dans l'infobulle.
  - Une réponse 409 s'affiche dans le panneau et dans `#top-status`. Sinon le panneau se ferme, et le chargement suit le modèle de `model-picker`.
  - Réducteur : `case "context_window_state"` met à jour `store.windowState` quand l'événement est live. Jetons seulement.
- `tests/test_context_window_setting.py` (nouveau), `tests/test_web_app.py`, `tests/test_trace_architecture.py` (ou le test du catalogue) -- Couvrir :
  - toute la matrice I/O, avec `FakeEngine` qui note `n_ctx`, un GGUF synthétique pour le KV, un faux llama-server et un faux Ollama, et un cloud avec `tpm`, puis avec `window` ;
  - le texte de `context_overflow` à la nouvelle fenêtre ;
  - les fonctions pures de `window.py` ;
  - la validation de l'événement ;
  - la route : 200, 409 et 422.
- `tools/e2e/run_e2e.py`, `tools/e2e/README.md` -- Nouveau scénario `s_context_window`, entre `local_server` et `relaunch`. Il vérifie, avec U+202F :
  - (a) sur le faux cloud A, après un message : trois choix, « chez le fournisseur », « (actuelle) » sur 4 096 ;
  - (b) 8 192 appliqué : bouton « Fenêtre 8 192 », infobulle de `#gauge` « Fenêtre de 8 192 tokens », chiffres « / 7 680 tokens », message toujours dans la Vue humain, `settings.json` `context.window == 8192` ;
  - (c) sur le faux llama-server, 16 384 noté : « bornée à 8 192 par llama-server » visible avant d'appliquer ;
  - (d) retour au faux cloud A et à 4 096, pour que `relaunch` reste inchangé.
  Capture `fenetre-contexte-reglage`, numérotée à la suite, ajoutée au README des captures.
- `EXPERIENCE.md`, `DESIGN.md`, `SPEC.md`, `README.md`, `wavestack.toml`, `ARCHITECTURE-SPINE.md` --
  - EXPERIENCE : ligne `window-picker` ; barre haute (ligne 32 et schéma ASCII) ; `context-gauge`.
  - DESIGN : composant `window-picker`, fait de jetons existants.
  - SPEC : CAP-33, fenêtre réglable et coût affiché.
  - README : « Fenêtre de contexte » ; `-c` de llama-server égal à la fenêtre choisie.
  - `wavestack.toml` : commentaire de `[context] window`.
  - Spine : AD-2 (`context_window_state`), AD-8 (contrôle avant rechargement pour la fenêtre, Ollama recompté à la nouvelle fenêtre), AD-9 (choix, mémorisation, bornes, débit mesuré).

**Acceptance Criteria:**
- Given WaveStack lancé sans réglage, when on ouvre le panneau « Fenêtre », then 4 096 est « (actuelle) » et chaque choix montre son cache de contexte, son temps de lecture ou « pas encore mesuré », et son verdict.
- Given un modèle local actif et un choix qui tient, when on clique « Appliquer », then le modèle est rechargé avec la nouvelle fenêtre, la conversation reste, la jauge montre la nouvelle fenêtre, et le choix est repris au lancement suivant (`Config.context_window`).
- Given un choix qui dépasse le budget, when on l'applique, then le refus chiffré s'affiche, et le modèle actif reste chargé à l'ancienne fenêtre, sans écriture.
- Given la pile E2E, when le parcours joue `s_context_window`, then les vérifications (a) à (d) passent, sans FAIL ailleurs.

## Spec Change Log

## Review Triage Log

## Design Notes

- Mémoriser sous `context.window` dans `settings.json` : `load_config` fusionne déjà `settings.json` sur `wavestack.toml`. Au relancement, la sonde, la découverte et l'avertissement `-c` de llama-server suivent donc la fenêtre choisie, sans nouveau lecteur. En cours de session, seule l'application fait foi, par `configured_window`.
- Le coût d'un choix est un coût total, poids compris, comme pour un changement de modèle : `check_window` compare `base + coût(fenêtre) ≤ budget`, le modèle actif étant retiré par `_without`. Le cache affiché, lui, est le KV complet à la fenêtre effective, soit `kv_bytes_per_token × effective`, calculé en f16 : c'est une borne haute.
- Le débit de lecture est mesuré sur un appel qui a évalué au moins 64 tokens, pour ne pas mesurer un succès du cache (lot A). Le temps affiché est une borne basse, car le débit baisse quand le contexte s'allonge.
- Exemple de choix : `{window: 16384, effective: 8192, source: "server", bound_fr: "bornée à 8 192 par llama-server (-c)", kv_fr: "Cache de contexte : réservé par llama-server (-c 8 192), inchangé", read_fr: "au moins ≈ 55 s, au-delà des 30 s visées au premier token (NFR-1)", fits: true}`.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, test fits compris, toujours à 4 096
- `node --check src/wavestack/web/static/app.js` -- expected: pas d'erreur
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; captures de `tools/e2e/screenshots` mises à jour et commitées

## Décisions prises par défaut

- **Emplacement du réglage.** Il va dans la barre haute, par un bouton et un panneau déroulant, sur le modèle de « Volets ▾ ». Le panneau reste visible pendant la démo et n'est pas modal (EXPERIENCE : seuls les tiroirs et les listes se superposent). Le diagnostic reste une page du lancement.
- **Mémorisation.** Le choix est rangé sous `context.window` dans `settings.json`, et non sous une clé de premier niveau. Il est ainsi relu sans nouveau code et reste visible comme une surcharge de `wavestack.toml` (AD-20).
- **Modèle cloud.** Pas de rechargement, et « Appliquer » désactivé quand `window` est déclaré : c'est ce que dit déjà AD-9.
- **Chemin de rechargement.** Local et servi rechargent par `_load` (`previous` = le même modèle) : un seul chemin, avec retour arrière et « Arrêter » gratuits. Pour llama-server, aucun contrôle du budget : sa mémoire est fixée par son `-c`.
- **Ollama.** Quand la fenêtre change, il est recompté comme non résident, parce qu'il recharge le modèle à un nouveau `num_ctx`. C'est la borne sûre.
- **Réserve de sortie.** Inchangée (512 ou 1 536) : « la réserve suit la fenêtre » se lit comme `usable = fenêtre − réserve`. Changer la règle d'AD-9 déborde la story.
- **Diagnostic de lancement.** Sonde, liste et avertissement `-c` gardent la fenêtre du lancement jusqu'au relancement. Ils ne sont ni redécouverts ni ressondés. `file_cost` compte déjà le KV au-delà de la fenêtre de sonde.
- **Temps de lecture.** Il n'est estimé que pour un modèle local ou servi. Pour le cloud, `prompt_ms` mesure surtout le réseau.
- **« Réinitialiser ».** La fenêtre n'y revient pas à 4 096 : c'est un réglage mémorisé, comme le modèle choisi. L'aide du panneau rappelle que les scénarios sont conçus pour 4 096.
- **Valeur hors liste.** Une valeur de la configuration hors des trois choix reste lue et affichée comme fenêtre actuelle. Aucune radio n'est alors « (actuelle) ».
- **Rafraîchissement du panneau.** Il se fait sur événement (lancement, chargements, tours), sans requête à l'ouverture. Le verdict est recontrôlé à l'application.

## À vérifier sur PC

- **Geste** : Edge, Outlook et Teams fermés. Qwen3.5-2B actif, envoyer « Bonjour », ouvrir « Fenêtre ▾ » et lire les trois choix. — **Attendu** : cache, temps de lecture et verdict pour 4 096, 8 192 et 16 384. — **Critère** : le cache du 2B égale `kv_bytes_per_token × fenêtre`, à comparer à l'entrée `probed_models` de `settings.json`. Le débit affiché est à ±20 % de `evaluated_tokens / prompt_ms` du dernier `model_call_ended`, lu dans le journal. — **Moyen** : script AppSession et Claude in Chrome.
- **Geste** : choisir 8 192, cliquer « Appliquer ». — **Attendu** : rechargement, conversation gardée, jauge à 8 192. — **Critère** : rechargement en 30 s au plus ; RSS de WaveStack après rechargement à ±30 % du coût annoncé ; `settings.json` contient `"context": {"window": 8192}`. — **Moyen** : script AppSession et PowerShell (`Get-Process`).
- **Geste** : 2B à 16 384, remplir le contexte (MCP complet, trois serveurs), puis envoyer. — **Attendu** : pas de débordement là où 4 096 débordait (M4). — **Critère** : premier token mesuré face au temps annoncé ; noter s'il dépasse 30 s (NFR-1). — **Moyen** : script AppSession, puis Claude in Chrome pour la jauge.
- **Geste** : 4B actif, choisir 16 384. — **Attendu** : refus chiffré si le budget ne suffit pas. — **Critère** : texte « Fenêtre de 16 384 tokens refusée » avec budget et calcul ; le 4B reste actif à la fenêtre précédente. — **Moyen** : Claude in Chrome.
- **Geste** : Ollama avec `llama3.2:3b` choisi, passer à 8 192 puis envoyer un message ; relever `ollama ps`. — **Attendu** : Ollama recharge le modèle avec `num_ctx` 8192. — **Critère** : la taille de `ollama ps` augmente d'environ le KV annoncé (±30 %). — **Moyen** : PowerShell et script AppSession.
- **Geste** : llama-server lancé avec `-c 4096`, puis choisir 8 192. — **Attendu** : « bornée à 4 096 par llama-server (-c) ». — **Critère** : la jauge reste à 4 096, `window_source=server`. — **Moyen** : Claude in Chrome.
- **Geste** : relancer WaveStack après avoir choisi 8 192. — **Attendu** : 8 192 repris ; le diagnostic conseille `-c 8192` pour llama-server. — **Critère** : bouton « Fenêtre 8 192 » au premier affichage. — **Moyen** : Playwright ou à la main.
- **Geste** : lire le panneau vidéoprojeté, sous Chrome et Edge, à 125 % et à 150 %. — **Attendu** : barre haute sur une ligne, panneau lisible et non coupé. — **Critère** : aucune commande de la barre haute sur deux lignes à 1280×650. — **Moyen** : à la main seulement.
