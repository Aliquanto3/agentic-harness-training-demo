---
title: 'LLM nu, compteur de tokens, jauge'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: 'd210a26c422d0d0563a2acdd6259530ee6bde587'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'interface à 5 volets (story 2) n'envoie rien au modèle : aucun tour, aucun contexte rendu, aucun compte de tokens, pas de jauge (CAP-9, CAP-31, CAP-33, CAP-35).

**Approach:** Premier tour de bout en bout sans brique : la session charge le modèle découvert par le diagnostic, rend le prompt par le gabarit du modèle, l'attribue en segments par sentinelles (AD-4) et le tokenise exactement. Elle l'envoie par le port `Engine` llama-cpp-python (AD-5) en streamant, puis émet compteur et jauge calculés côté session (AD-9). Le front ne fait que projeter.

## Boundaries & Constraints

**Always:**
- AD-4 : le prompt envoyé est le rendu du gabarit (`ImmutableSandboxedEnvironment` configuré comme transformers). Attribution selon les 6 étapes normatives de `context/render.py` : normalisation, neutralisation des tokens spéciaux avec événement, sentinelles U+E000–E002, contrôle octet pour octet, découpage disjoint, 1 token = segment de son 1er octet. La somme par segment est égale au total.
- AD-5 : `Engine` synchrone (`complete`, `tokenize`, `token_pieces`, `metadata`, `close`). `tokenize(add_bos=False, special=True)`, `token_pieces` via `llama_token_to_piece(special=True)` avec retaille du tampon. `Llama.detokenize` interdit. `CancelToken` testé à chaque fragment.
- AD-6 : registre par famille (`general.architecture` + gabarit) : `tool_call_parser` (nom seulement), `stop_sequences`, variable de raisonnement, contexte natif, séparateur incrémental `reasoning`/`text`. Famille inconnue : données lues dans le GGUF. Sans `chat_template` : incompatible, avec la raison.
- AD-9 : fenêtre effective = min(config, natif) ; réserve de 512 ; `max_tokens = réserve` ; dépassement = appel non envoyé (`context_overflow` puis `turn_ended{overflow}`) ; `stop_reason=length` = `output_truncated` puis `turn_ended{limit}`. `context_rendered`/`context_preview` portent `window, reserve, usable, used, percent, near_limit, overflow` et la ventilation, calculés par la session.
- AD-2/AD-3/AD-16/AD-24 : `kind` ajoutés au catalogue sans toucher `Envelope` ; paires `*_started`/`*_ended` sur le même `step_id` ; envoi refusé hors `idle` avec la raison ; un seul thread de travail ; toute erreur devient `harness_error` + `turn_ended{error}`.
- Libellés français des `SegmentKind` dans `content/` (AD-19), messages français construits côté Python.

**Décisions (2026-09-24) :**
- Détail de la jauge (grille `context-gauge-detail`) différé : jauge empilée dans la barre haute, ventilation au survol.
- Bouton « Arrêter » inclus : intention préemptive `POST /api/intentions/stop` (classe c), qui arme le `CancelToken` ; le tour finit en `turn_ended{cancelled}`, texte partiel conservé.
- La vue humain garde l'affichage des échanges précédents ; seul le contexte envoyé est réduit au dernier message.

**Never:**
- Pas de brique, de mémoire courte, d'outil ni de parseur d'appel d'outil (stories 4-5). Pas de `LoadRegistry`/budget mémoire AD-8, pas d'adaptateurs `llama_server`/`ollama_raw` (palier 2) : un candidat serveur seul rend l'envoi indisponible, avec la raison. Pas de `prefix_not_reused` (un seul appel par tour en LLM nu).
- Le front ne recalcule ni tokens, ni pourcentages, ni ventilation (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Tour LLM nu | `idle`, message « Bonjour » | Segments `user_message` + `template` seuls, somme = total ; streaming en vue humain et en sortie brute ; compteur entrée/sortie/temps | N/A |
| Envoi pendant un tour | État `turn` | 409, raison française, composer désactivé | N/A |
| Dépassement | Message > `usable` | Appel non envoyé, jauge > 100 % en rouge, carte de dépassement en français | `context_overflow` + `turn_ended{overflow}` |
| Sortie coupée | Génération atteint 512 | Texte conservé, mention « sortie coupée » | `output_truncated` + `turn_ended{limit}` |
| Texte avec token spécial | Message contenant `<\|im_start\|>` | Chaîne neutralisée, structure inchangée | Événement de neutralisation |
| Attribution approximative | Rendu d'attribution ≠ prompt | Prompt envoyé inchangé, texte non localisé en `template` | `harness_error` « attribution approximative » |
| Arrêt | Clic « Arrêter » pendant la génération | Génération interrompue au fragment suivant, texte partiel conservé | `model_call_ended{stop_reason: cancelled}` + `turn_ended{cancelled}` |
| Erreur moteur | Exception de `complete` | L'application reste utilisable | `harness_error` + `turn_ended{error}` |

</frozen-after-approval>

## Code Map

- `src/wavestack/trace/catalog.py` -- ajouter les payloads : `turn_started{replay_of, message}`, `turn_ended{status}`, `context_rendered`/`context_preview{segments, window, reserve, usable, used, percent, near_limit, near_limit_ratio, overflow, breakdown[{group, label_fr, tokens}]}`, `context_overflow{used, usable, message_fr, strategies_fr}`, `output_truncated`, `model_call_started{phase_label}`, `model_first_token`, `model_delta{channel, text}`, `model_call_ended{raw_output, reasoning, text, tool_calls, prompt_tokens, output_tokens, prompt_ms, gen_ms, stop_reason, duration_ms}`, `special_token_neutralized`. `Envelope` intouchée.
- `src/wavestack/context/` (nouveau) -- `segments.py` : `SegmentKind` (ordre AD-4), `Segment`. `render.py` : environnement Jinja, rendu, attribution. `window.py` : fenêtre, réserve, ventilation (`user_message`+`template` = groupe « Message et gabarit »).
- `src/wavestack/models/engine.py` (nouveau) -- port `Engine`, `CancelToken`, adaptateur `LlamaCppEngine` (`Llama.generate` avec les ids du harnais, décodage UTF-8 incrémental des `token_pieces`, arrêt sur EOG ou `stop_sequences` sans fuite de préfixe). `models/capabilities.py` (nouveau) -- registre AD-6 (famille Qwen3/Qwen3.5 connue, repli GGUF).
- `src/wavestack/session/app_session.py` -- devient la session unique (décision sur l'item différé de la story 2) : `boot(model_path)` (état `model_load` → `idle`, puis `context_preview`), `send(message)` sur un `ThreadPoolExecutor(max_workers=1)`, état protégé par un verrou. Garder `emit_initial` et les nœuds fixes.
- `src/wavestack/cli.py`, `web/app.py` -- créer un seul `AppSession` et le passer à `create_app`. Après diagnostic prêt (thread et `select_model`) : `boot(premier candidat usable avec path)`. Ajouter `POST /api/intentions/send` (JSON `{message}`, 409 + `detail` hors `idle`) et `POST /api/intentions/stop` (classe c, sans effet hors tour). `/api/state` renvoie aussi le dernier `context_preview`/`context_rendered`.
- `src/wavestack/web/static/{index.html,app.js,app.css}` -- jauge dans la barre haute (empilée, seuil, rouge au dépassement, « prochain tour » sur l'aperçu), composer actif en `idle` (sinon désactivé avec la raison de `session_state`, et bouton « Arrêter » pendant un tour), bulles avec streaming et indicateur « Lecture du contexte… » jusqu'au 1er token, segments étiquetés (brique + tokens) et sortie brute dans Contexte LLM, étape « Appel au modèle » avec compteur dans Orchestration, carte de dépassement. Couleurs : `--color-segment-*` déjà dans `tokens.css`.
- `content/labels/segment_kinds.yaml` (nouveau) -- libellés français, validés par pydantic ; `pyyaml` passe en dépendance runtime (`uv add pyyaml`), et `jinja2` en dépendance directe.
- `tests/fixtures/qwen3_5_chat_template.jinja` (nouveau) -- gabarit Qwen3.5 récupéré sur le Hub HF (lecture seule), pour le test de rendu de référence. Récupération interdite avant 11 h 20 (voir Verification) : si elle n'est pas encore possible, écrire le test, le laisser sauté faute de fixture et le signaler.
- Accès aux fichiers : dans cette session, une règle de permission obsolète bloque l'outil Read sur `src/wavestack/models/`. Lire ces fichiers avec `Get-Content -Encoding utf8` (autorisé par Anaël) ; l'outil Edit/Write reste utilisable.

## Tasks & Acceptance

**Execution:**
- [x] `trace/catalog.py` -- nouveaux `kind` et payloads -- AD-2
- [x] `context/{segments,render,window}.py` + `content/labels/segment_kinds.yaml` -- rendu, attribution, fenêtre -- AD-4, AD-9
- [x] `models/{engine,capabilities}.py` -- port, adaptateur, registre -- AD-5, AD-6
- [x] `session/app_session.py` -- boot, tour, états, erreurs -- AD-3, AD-16, AD-24
- [x] `cli.py`, `web/app.py` -- session unique, route `send`, `/api/state` étendu -- AD-3, AD-18
- [x] `web/static/*` -- jauge, composer, streaming, segments, compteur, dépassement -- AD-1, CAP-1/2/31/33
- [x] `tests/` -- moteur factice (tokenizer octet par octet) : somme = total, contrôle 4, neutralisation, dépassement, sortie coupée, arrêt, erreur moteur, 409 hors `idle` ; rendu Qwen3.5 contre une chaîne de référence (outils, accents, apostrophe) ; test marqué `model` : contrôles 4 et 6 sur un vrai GGUF, dont un token de 128 espaces

**Acceptance Criteria:**
- Given un modèle chargé et aucune brique, when l'utilisateur envoie un message, then le volet Contexte LLM montre uniquement « Message et gabarit » et la somme des tokens par segment est égale au total affiché.
- Given un tour terminé, when on regarde l'étape « Appel au modèle », then elle affiche tokens d'entrée, tokens de sortie et temps écoulé, tous reçus du journal.
- Given le démarrage terminé, when aucun tour n'a eu lieu, then la jauge affiche l'aperçu « prochain tour » issu de `context_preview`.

## Implementation Notes

- Implémenté par un sous-agent (dispatch), diff relu dans cette session. `ruff check`, `ruff format --check` : propres. `pytest` : 56 passed, 1 skipped (rendu Qwen3.5 de référence, fixture absente), 2 deselected (tests `model`).
- Choix de l'implémentation : « envoi indisponible » = état `idle` avec un `reason_fr` (candidat serveur seul, chargement en échec, gabarit absent) ; tokens spéciaux neutralisés par une espace sans chasse après le 1er caractère (tokens CONTROL et USER_DEFINED du vocabulaire, lus au chargement) ; `percent` en pourcentage (ex. 51,2) ; cache KV dimensionné sur la fenêtre configurée. Ajouts au catalogue : `kinds` dans chaque groupe de la ventilation, `duration_ms` dans `turn_ended`.
- Test `model` : `WAVESTACK_TEST_GGUF` doit pointer vers un GGUF ; pas de chemin par défaut, pour que pytest ne touche jamais `D:`.
- Audit de la matrice I/O : les 8 lignes sont couvertes par `tests/test_turn.py` et passent (tour LLM nu, 409, dépassement, sortie coupée, token spécial, attribution approximative, arrêt, erreur moteur). La partie affichage (streaming, jauge, carte) reste à vérifier à la main.
- Fixture Qwen3.5 extraite du GGUF local (`tokenizer.chat_template` de `Qwen3.5-9B-UD-Q3_K_XL.gguf`, architecture `qwen35`) ; rendu de référence produit indépendamment par `transformers` (`render_jinja_template`, environnement `uv run --isolated`). `test_qwen3_5_render_matches_reference` et le test `model` (`WAVESTACK_TEST_GGUF` = ce GGUF) passent.
- Vérification manuelle dans Chrome (Qwen3.5-9B puis MiniCPM5-2B, famille inconnue) : « Bonjour » streamé ; segments 3 + 1 + 9 = 13 = total affiché ; compteur entrée/sortie/temps ; jauge « prochain tour » puis réelle ; dépassement à 5 413 / 3 584 tokens (appel non envoyé, carte, jauge rouge, marqueur masqué) ; « Arrêter » (texte partiel conservé, badge « arrêté ») ; rechargement qui rejoue les 3 tours ; aucune erreur console. Découverte isolée (`OLLAMA_MODELS`, `HF_HOME`, `WAVESTACK_DATA_DIR` vers des dossiers vides, pour ce seul processus) pour ne pas sonder les blobs Ollama.
- Correctif issu de la vérification manuelle : tous les segments s'affichaient « Message et gabarit », message et gabarit indiscernables. Chaque segment porte désormais `label_fr` (libellé de son type, calculé par la session) ; accord « 1 token ». `pytest` final : 63 passed, 2 deselected.
## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 41 constats) :

- [VG1] Tokens par segment jamais vérifiés un à un, seulement en somme — `medium`, écart pré-vérifié (un `bisect_left` passerait). → G1 `patch`.
- [VG2] `near_limit` et `near_limit_ratio` jamais vérifiés — `medium`, pré-vérifié. → G1 `patch`.
- [VG3] Branche `qwen3` de `capabilities_for` et démarrage en canal `reasoning` non testés — `medium`, pré-vérifié. → G1 `patch`.
- [VG5] `select_model` avec un candidat `found` : chemin transmis au moteur jamais vérifié — `medium`, pré-vérifié. → G1 `patch`.
- [BH10] Chemins d'échec du boot (fabrique qui lève, libellés invalides) et `harness_error` du contrôle 6 non testés — `low`, confirmé (grep). → G1 `patch`.
- [VG4/BH9/EC20] Test de rendu Qwen3.5 toujours sauté (fixtures absentes) — `medium`, confirmé. Tâche déjà ouverte, bloquée jusqu'à 11 h 20 (mesures d'Anaël) ; traitée avant le passage à `done`, pas un nouveau correctif.
- [VG6] `LlamaCppEngine.complete` (EOG, `length`, stop, annulation) sans test sur le vrai adaptateur — `medium`, pré-vérifié ; exige un vrai GGUF. → `defer`.
- [BH3/EC16] Rechargement de la page : `store.turns` vide, deltas d'un tour en cours perdus (le snapshot ne rejoue pas les tours) — `medium`, confirmé (`app.js:643-649`, flux repris à `body.seq`). → G2 `patch` (rejouer le journal depuis 0 au démarrage).
- [BH4] Attribution approximative (contrôles 4/6) invisible sur un tour terminé : `turn.errors` n'est affiché qu'au statut `error` — `medium`, confirmé (`turnNote`). → G2 `patch`.
- [BH2] `render()` complet, journal compris, reconstruit à chaque `model_delta` : O(n) par delta, l'interface ralentit au fil des tours — `medium`, confirmé (`applyEnvelope` → `render()` → `renderJournal()`). → G2 `patch` (regrouper les rendus par `requestAnimationFrame`).
- [BH5] Au dépassement, le marqueur de seuil est placé à 80 % de `used` au lieu de `usable` — `low`, confirmé ; scénario de démo prévu (module MCP), correction directe. → G2 `patch` (masquer le marqueur au dépassement).
- [EC17] Après un 409 (double Entrée), « Un tour est déjà en cours » reste affiché après la fin du tour — `low`, confirmé (`composerError` jamais effacé sur `session_state`), correction d'une ligne. → G2 `patch`.
- [BH14] `.sr-only` incomplet (`margin: -1px; padding: 0; border: 0`) — `low`, correction directe. → G2 `patch`. Le reste du constat (annonce du texte partiel, réponse de `stop` ignorée) : `low`, rejeté (rare, ajoute des branches).
- [EC7] Token spécial d'un seul caractère : la boucle de neutralisation ne termine jamais (le worker se bloque) — `low`, inatteignable avec `LlamaCppEngine` (filtre `len >= 2`) mais le port ne le garantit pas ; correction d'une ligne. → G3 `patch` (filtrer dans `render_context`).
- [BH1] Fuite du moteur si `metadata()`/`capabilities_for()` lèvent après la fabrique — `false` : `metadata()` renvoie une valeur mise en cache dans `__init__` (`engine.py:96,122`), `capabilities_for` est pure ; `_caps` périmé n'est jamais lu car `send` exige `_engine`.
- [BH6] Le front calcule `usable - used` et `near_limit_ratio * 100` — `false` : AD-1 autorise « les écarts entre deux valeurs reçues » et la mise en forme.
- [BH7/EC4/EC5/EC6] Fenêtre ≤ 512, `near_limit_ratio` hors (0,1], gabarit seul en dépassement, cause « message trop long » figée — `low`, rejetés : mauvaise configuration écrite à la main dans `settings.json`, la correction ajoute des gardes.
- [BH8/EC3] `SendIntention` accepte un message de blancs, sans longueur maximale — `low`, rejeté : le front élague déjà, l'appel direct à l'API ne plante rien, et le dépassement couvre les textes longs.
- [BH11/EC15] `boot(None)` après un modèle chargé laisse l'ancien moteur en mémoire — `low`, rejeté : exige un nouveau `select_model` après le passage à `/`, qui ne trouverait plus aucun fichier.
- [EC1] `select_model` pendant `idle` peut chevaucher un `send` — `low`, rejeté : la page de diagnostic n'est plus utilisée une fois l'interface ouverte.
- [BH12] Types `str` au lieu de `SegmentKind` dans le catalogue — `false` : le spine interdit à `trace` d'importer un module du projet.
- [BH13/EC18] `GROUP_COLORS` sans `hook_injection`/`assistant_turn`, canal `tool_call` ajouté au texte — `false` pour cette story : ni ces types ni ce canal ne sont émis avant les stories 4-5.
- [EC2] `Fragment` final à `stop_reason: error` donnerait `turn_ended{completed}` — `false` : aucun moteur ne produit ce fragment, une erreur lève une exception.
- [EC8] `strftime_now` à cheval sur une frontière de temps entre les deux rendus — `low`, rejeté (rarissime).
- [EC9] Caractères U+E000–E002 dans le gabarit lui-même — `low`, rejeté (aucun gabarit connu ; le repli approximatif s'applique).
- [EC10] Préfixe partiel d'une séquence d'arrêt émis à l'arrêt ou à la limite — `low`, rejeté : les séquences d'arrêt Qwen sont des tokens EOG uniques.
- [EC11] Second `llama_token_to_piece` négatif — `false` : le premier appel renvoie la taille exacte requise.
- [EC12] `max_tokens <= 0` — `false` : toujours égal à la réserve (512).
- [EC13] Texte retenu par le séparateur perdu des canaux sur une erreur en cours de flux — `low`, rejeté (quelques caractères, la sortie brute les garde).
- [EC14] Fermeture pendant la lecture du contexte bloquée jusqu'au premier token — `low`, rejeté (limite AD-24 assumée).
- [EC19] Libellés invalides : le groupe message prend le libellé technique `user_message` — `low`, rejeté (repli déjà signalé par `harness_error`).

Groupes routés en `patch` : G1 (tests), G2 (front), G3 (`render.py`) ; aucun `intent_gap` ni `bad_spec`, pas de loopback.
## Design Notes

Échantillonnage par défaut du moteur fixé en constante (temp 0,7, top_p 0,8, top_k 20, recommandations Qwen hors raisonnement) : pas de réglage tant qu'aucune story ne l'expose. `enable_thinking=False` est passé si le registre connaît la variable (brique raisonnement absente). L'aperçu rend un message utilisateur vide : le texte vide ne produit pas de segment (AD-4 étape 3), donc tout le rendu est `template`. Le test de rendu de référence ne couvre pas encore l'assistant vide avec outil ni les tours à deux appels : ils arrivent avec la story 5.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)

**Manual checks (if no CLI):**
- Pas avant 11 h 20 le 2026-09-24 (mesures en cours sur ce poste) : ni accès à `D:`, ni téléchargement, ni lancement de l'application, dont la découverte parcourt `HF_HOME`/`OLLAMA_MODELS` sur `D:`. Ensuite, GGUF locaux dans `D:\ia\gguf` (ex. `Qwen3.5-9B-UD-Q3_K_XL.gguf`, `MiniCPM5-2B-Q4_K_M.gguf` pour une famille inconnue) et blobs Ollama sans extension dans `D:\ia\ollama\models\blobs`.
- `uv run wavestack`, choisir le GGUF par son chemin sur `/diagnostic`, envoyer « Bonjour » sur `/`. Vérifier le streaming, le segment unique, le compteur et la jauge. Puis coller un texte de plus de 4 000 tokens : l'appel n'est pas envoyé et une carte de dépassement s'affiche.
