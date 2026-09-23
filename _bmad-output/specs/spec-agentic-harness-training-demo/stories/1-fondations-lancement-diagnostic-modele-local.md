---
title: 'Fondations : lancement, diagnostic, modèle local'
type: 'feature'
created: '2026-09-23'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: 'NO_VCS'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** WaveStack n'a encore aucun code : ni installation, ni lancement, ni détection de modèle. Rien ne permet à un utilisateur sans droits admin de cloner le dépôt, lancer une commande et voir un diagnostic de démarrage qui trouve un modèle GGUF déjà présent sur son poste (CAP-36 à CAP-39).

**Approach:** Poser le socle `cli`, `config` et `models` (découverte + sonde GGUF, AD-7) avec juste assez de `trace`, `net` et `web` pour qu'un diagnostic bloquant s'affiche en terminal et dans une page navigateur minimale (AD-21), sans construire l'interface à 5 volets (story 2) ni le téléchargement de modèle (hors CAP-36 à CAP-39, différé).

## Boundaries & Constraints

**Always:**
- `uv` seul pour les dépendances (`uv.lock` versionné, `requires-python = "==3.13.*"`) ; jamais `pip`.
- Toutes les données d'exécution sous le dossier unique d'AD-20 (`%LOCALAPPDATA%\WaveStack` / `~/.local/share/wavestack`), résolu uniquement par `config`.
- La garde réseau (AD-15, `sys.addaudithook`) s'installe au tout début de `cli`, avant tout import tiers.
- Le catalogue `trace` (AD-2) n'inclut que les `kind` réellement émis par cette story (`diagnostic_check`, `outbound_request`, `harness_error`, `session_state`) ; l'enveloppe complète est déjà celle d'AD-2, les autres `kind` viendront en story 2 sans jamais changer l'enveloppe.
- Diagnostic (CAP-39) : mémoire (psutil), présence de modèle (AD-7), sonde de connectivité réseau (AD-15, `origin=diagnostic`), disponibilité du port — chaque vérification émet `diagnostic_check{check, status, message_fr, action_fr, blocking}`, en français.
- Textes utilisateur (README, messages diagnostic, page `/diagnostic`) en français ; code, identifiants, docstrings en anglais (NFR-7).

**Never:**
- Pas de téléchargement de modèle ni d'intégration `huggingface_hub` (CAP-36 couvre l'usage *sans* téléchargement ; le téléchargement n'est dans aucun CAP de cette story — différé).
- Pas de brique, pas d'interface à 5 volets, pas de moteur d'inférence réel branché (`Engine`/`llama-cpp-python` arrivent en story 3) : la sonde GGUF (AD-7) suffit à qualifier un fichier, sans exposer de génération.
- Pas d'élévation de droits, pas de service Windows, pas de règle de pare-feu.
- Pas de lecture d'outils, de MCP, de skills, de hooks (stories 5 à 8).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Lancement normal | `uv run wavestack`, port libre, un GGUF valide trouvé | Serveur démarre en état `diagnostic`, navigateur ouvert sur `/diagnostic`, tous les `diagnostic_check` `blocking=false`, session prête | N/A |
| Aucun modèle trouvé | Aucun GGUF dans les emplacements AD-7 | `diagnostic_check{check: "model", status: "fail", blocking: true}` ; page liste les candidats trouvés (aucun) et un champ de chemin (`select_model`) | Aucune session complète créée (AD-21 règle 4) ; nouvelle vérification après `select_model` |
| GGUF présent mais sonde échoue | Fichier GGUF corrompu ou incompatible | Sonde (processus enfant) échoue ; fichier marqué "incompatible" avec raison ; diagnostic reste bloquant | `harness_error` en français, pas de plantage du processus principal |
| Port déjà occupé par une instance WaveStack | Port en conflit, `GET /api/health` répond | Navigateur ouvert sur l'instance existante, process quitte avec code 0 | N/A |
| Port occupé par autre chose | Port en conflit, `/api/health` ne répond pas | Message français en terminal (option `--port`), code de sortie non nul | N/A |
| Réseau indisponible | Sonde de connectivité échoue | `diagnostic_check{check: "network", status: "warn", blocking: false}` avec action corrective (voie hors ligne) | Ne bloque pas le diagnostic (CAP-14/36 restent utilisables hors ligne) |

</frozen-after-approval>

## Code Map

- `pyproject.toml`, `uv.lock`, `wavestack.toml` -- nouveaux ; script `wavestack`, index CPU `llama-cpp-python` épinglé même si non encore utilisé (AD-21), liste d'adresses réseau autorisées par défaut (AD-15).
- `src/wavestack/config.py` -- résout le dossier de données (AD-20), charge `wavestack.toml` puis surcharge par `settings.json`.
- `src/wavestack/trace/` -- `envelope.py` (modèle pydantic AD-2), `scope.py` (`TraceScope` contextvar), `journal.py` (liste en mémoire + verrou), `catalog.py` (seulement les `kind` listés dans Boundaries).
- `src/wavestack/net/` -- `factory.py` (client `httpx.Client` avec `truststore`, proxy, hook `outbound_request`), `guard.py` (`sys.addaudithook`, liste autorisée depuis `config`).
- `src/wavestack/models/discovery.py` -- une fonction listant les candidats GGUF (fichier saisi, `models/`, cache HF, LM Studio, manifestes Ollama, serveurs déjà lancés sondés jamais lancés) selon AD-7.
- `src/wavestack/models/probe.py` -- module exécutable (`python -m wavestack.models.probe <path>`), chargement complet en processus enfant, mesure mémoire résidente, résultat mémorisé dans `settings.json`.
- `src/wavestack/session/diagnostic.py` -- session minimale, seul état `diagnostic`, traite `select_model` (AD-3) ; base que les stories suivantes étendront, ne pas préconstruire les autres états.
- `src/wavestack/web/app.py`, `web/static/diagnostic.html` -- FastAPI minimal : `GET /api/health`, `GET /diagnostic`, `GET /api/diagnostic`, flux SSE des `diagnostic_check`, `POST` intention `select_model`. Pas de volets, pas de `tokens.css` complet (story 2).
- `src/wavestack/cli.py` -- entrée `wavestack` : garde réseau puis `truststore.inject_into_ssl()` puis `HF_HUB_DISABLE_XET`/`HF_HUB_DISABLE_TELEMETRY`, réservation de port (AD-21 étape 1), lancement thread de travail (AD-24) qui exécute les vérifications, ouverture du navigateur.
- `README.md` -- section installation en français (CAP-37) : prérequis (Git ou zip, `uv`), une commande, domaines à autoriser derrière un proxy (AD-21).
- `tests/` -- `test_discovery.py`, `test_probe.py` (sonde sur un GGUF factice ou squelette invalide), `test_net_guard.py` (host hors liste bloqué, y compris sous `ProactorEventLoop`), `test_config_paths.py`, `test_cli_diagnostic.py` (diagnostic complet avec moteur/réseau factices).

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock`, `wavestack.toml` -- créer le projet `uv`, épingler l'index CPU `llama-cpp-python`, poser les valeurs par défaut (dossier de données, adresses autorisées) -- socle requis par tout le reste
- [x] `src/wavestack/config.py` -- résolution du dossier de données et fusion `wavestack.toml`/`settings.json` -- AD-20, lu par `net`, `models`, `session`
- [x] `src/wavestack/trace/*` -- enveloppe, `TraceScope`, journal en mémoire, catalogue restreint -- AD-2, requis par `diagnostic_check`
- [x] `src/wavestack/net/*` -- garde réseau + fabrique de client tracée -- AD-15, installée avant tout import tiers dans `cli`
- [x] `src/wavestack/models/discovery.py` -- énumération des candidats GGUF -- AD-7
- [x] `src/wavestack/models/probe.py` -- sonde en processus enfant, mémorisation du succès -- AD-7
- [x] `src/wavestack/session/diagnostic.py` -- état `diagnostic` minimal, intention `select_model` -- AD-3
- [x] `src/wavestack/web/app.py`, `web/static/diagnostic.html` -- API santé/diagnostic, SSE, page minimale -- AD-18 (sous-ensemble), AD-21
- [x] `src/wavestack/cli.py` -- séquence de lancement complète, réservation de port, ouverture navigateur -- AD-21, AD-24
- [x] `README.md` -- procédure d'installation sans droits admin -- CAP-37
- [x] `tests/*` -- couvrir découverte, sonde, garde réseau, chemins de config, diagnostic bout en bout -- non-régression AD-7/AD-15/AD-20/AD-21

**Acceptance Criteria:**
- Given un GGUF valide déjà présent dans `models/`, when `uv run wavestack` s'exécute, then le diagnostic passe sans blocage et la page `/diagnostic` s'ouvre automatiquement.
- Given aucun GGUF trouvé, when le diagnostic s'exécute, then le blocage est explicite en français avec les emplacements cherchés, et aucune session complète n'est créée.
- Given un hôte hors liste autorisée, when un code du processus tente une connexion, then la garde réseau la refuse (`NetworkBlocked`), y compris sous `ProactorEventLoop`.
- Given le port déjà utilisé par une instance WaveStack, when on relance `uv run wavestack`, then le navigateur s'ouvre sur l'instance existante et le nouveau process quitte en code 0.

## Implementation Notes

- Implémenté par un sous-agent d'implémentation (dispatch), puis vérifié et complété dans cette session.
- `.gitignore` avait une règle `models/` non ancrée qui excluait silencieusement `src/wavestack/models/` (le package Python) du suivi git ; corrigée en `/models/` (racine du dépôt seulement). `.claude/settings.json` a la même règle non ancrée sur `Read(./models/**)`, qui bloque encore l'outil `Write` sur `src/wavestack/models/*` -- non corrigée ici (hors périmètre de cette story), signalé pour une story ultérieure ou un ajustement de configuration.
- `net/factory.py` ne trace plus les requêtes vers la boucle locale (Ollama/llama-server sondés en AD-7), pour respecter AD-15 (« hors boucle locale » seulement).
- Audit de la matrice I/O de la spec : 4 des 6 lignes n'avaient pas de test automatisé au premier passage (sonde qui échoue, réseau indisponible, port occupé par une instance WaveStack, port occupé par autre chose). Ajoutés : `test_probe_failure_marks_candidate_incompatible_and_stays_blocking`, `test_probe_subprocess_crash_marks_candidate_incompatible`, `test_network_unreachable_warns_without_blocking` (tests/test_cli_diagnostic.py) et `tests/test_cli_launch.py` (réservation de port, instance existante, conflit).
- Correction AD-16 : `session/diagnostic.py::check_network` ne rattrapait que `httpx.HTTPError`, pas `NetworkBlocked` (levée par la garde réseau quand l'hôte n'est pas autorisé) -- une exception aurait pu traverser la frontière de la session. Le test de la garde réseau en environnement de test (hôtes autorisés vides) l'a révélé.
- Correction Windows : `cli.py::_try_reserve_port` utilisait `SO_REUSEADDR`, qui sous Windows permet à un second processus de se lier silencieusement à un port déjà écouté par WaveStack -- cassant la détection de conflit de port exigée par AD-21 sur la plateforme cible principale (NFR-6). Remplacé par `SO_EXCLUSIVEADDRUSE` sous `win32`.
- Non implémenté, hors périmètre confirmé par les CAP de cette story (CAP-36 couvre l'usage *sans* téléchargement) : téléchargement de modèle, brique, interface à 5 volets, moteur d'inférence réel.

## Spec Change Log

## Review Triage Log

Pass 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 layers, 27 findings) :

- [BH1] Course entre `run()` (thread de fond) et `select_model` (thread de requête FastAPI) qui écrivent tous deux `last_result`/`candidate.status` sans verrou — `medium` : violation réelle d'AD-24 (« un seul thread exécute... le diagnostic »), confirmé en lisant `cli.py` (thread dédié) vs `web/app.py::select_model` (route synchrone, thread de requête). → groupe G7, `patch`.
- [BH2] Journal en mémoire non borné, sans commentaire `ponytail:` — `low` : rejeté, croissance négligeable sur la durée de vie d'une démo, correction non triviale (rotation) pour un bénéfice marginal ici.
- [BH3] Catalogue restreint qui n'échoue pas sur un `kind` inconnu — `low`/`false` : rejeté, la règle AD-2 n'exige pas ce rejet, seulement que chaque `kind` connu ait son modèle pydantic.
- [BH4] `near_limit_ratio` non lu par `Config` — `false` : ce n'est pas du code mort, AD-9 exige explicitement que ce seuil vive dans `wavestack.toml` (« seuil 0,8, défini dans wavestack.toml ») en avance de son consommateur (story 3).
- [BH5] Bypass CSRF/same-origin quand `Origin` est absent — `high`, confirmé en lisant `web/app.py:41` (`if origin is not None and origin not in expected`) : contredit AD-18 littéralement (« tout POST dont l'Origin n'est pas celle de l'application est refusé »). → groupe G1, `patch`.
- [BH6] `harness_error` jamais affiché dans `diagnostic.html` — `medium`, confirmé : le JS n'écoute que `diagnostic_check`. → groupe G3, `patch`.
- [BH7] `starlette` importé en test sans dépendance déclarée — `low` : correction triviale (ajout au groupe `dev`), gardé. → groupe G10, `patch`.
- [BH8] Pas d'accessibilité (ARIA) dans `diagnostic.html` — `low` : rejeté, hors périmètre explicite (page minimale, story 2 construit l'interface réelle), correction non triviale.
- [BH9] Pas de retour visuel après soumission du chemin modèle — `medium`, confirmé : le handler JS `fetch` ignore la réponse. → groupe G3, `patch`.
- [BH10] `config.load_config()` relit le disque à chaque appel — `low` : rejeté, coût négligeable pour la fréquence d'appel du diagnostic, mise en cache non triviale à faire correctement.
- [BH11] README ne documente pas comment étendre `allowed_hosts` — `low` : correction triviale (paragraphe), gardé. → groupe G11, `patch`.
- [BH12] `already_probed` compare `mtime` en égalité stricte de flottant — `low` : rejeté, improbable en usage local mono-poste, correction robuste (hash) non triviale pour le bénéfice.
- [EC1] `--port` hors 0-65535 lève `OverflowError` non capturée — `low`, confirmé (`except OSError` seul) : correction triviale (élargir le tuple). → groupe G8, `patch`.
- [EC2] Fenêtre de course release-puis-rebind du port — `false` : déjà un compromis assumé et documenté (`# ponytail: ...` dans `cli.py`), pas une nouvelle défaillance.
- [EC3] `settings.json`/`wavestack.toml` invalide fait planter le lancement — `medium`, confirmé (`json.loads`/`tomllib.loads` sans try/except) : `settings.json` est destiné à l'édition manuelle (AD-15, pour `allowed_hosts`). → groupe G5, `patch`.
- [EC4] `server.port`/`context.window` non numérique fait planter `Config` — `medium`, confirmé (`int(...)` sans garde) : même cause profonde que EC3. → groupe G5, `patch`.
- [EC5] `net.loopback_ports` non-dict lève `AttributeError` dans `discover()` — `medium`, confirmé : tue le thread de fond sans retour utilisateur. → groupe G6, `patch`.
- [EC6] Fichier non-UTF8 sous l'arborescence des manifestes Ollama lève `UnicodeDecodeError` non capturée (`except (OSError, json.JSONDecodeError)` ne couvre pas ce cas) — `medium`, confirmé par lecture du code. → groupe G6, `patch`.
- [EC7] Entrée `probed_models` non-dict lève `AttributeError` — `medium`, confirmé, même cause profonde que EC5/EC6. → groupe G6, `patch`.
- [EC8] `probe.record_success` (écriture disque) hors du `try/except` qui protège l'appel sonde voisin — `medium`, confirmé, même cause profonde que EC5-EC7. → groupe G6, `patch`.
- [EC9] Hôte vide toujours autorisé par la garde réseau (`if not host or is_loopback(host): return True`) — `medium`, confirmé (`guard.py:49`) : la suppression du cas spécial suffit, le comportement par défaut refuse déjà une chaîne vide. → groupe G4, `patch`.
- [EC10] Même défaut que BH5 (Origin absente) — `high`, doublon de BH5, fusionné dans le groupe G1.
- [EC11] `Last-Event-ID` non numérique lève `ValueError` → 500 au lieu de reprendre à 0 — `low`, confirmé (`web/app.py:74`), correction triviale. → groupe G9, `patch`.
- [EC12] Aucun événement `diagnostic_check` n'est jamais imprimé en terminal — `high`, confirmé (aucun `print`/`logging` sur ces événements dans `cli.py`/`diagnostic.py`) : viole la clause « Always » gelée de cette spec et AD-21 règle 3 (« écrit dans le terminal et poussé dans le flux »). → groupe G2, `patch`.
- [EC13] Message de blocage générique, candidats jamais rendus dans la page — `medium`, confirmé (`diagnostic.html` n'affiche pas `candidates`), même cause profonde que BH6/BH9. → groupe G3, `patch`.
- [VG1] Aucun test sur les chemins de rejet de `_same_origin_post` (403/415) — pré-vérifié par la couche verification-gap, disposition déposée `patch` ; respectée. → groupe G1 (ajout de tests), `patch`.
- [VG2] La branche « serveur déjà lancé » de `check_model` n'est jamais exercée par un test — pré-vérifié, disposition déposée `defer` (les tests isolent délibérément la découverte de l'état réel de la machine pour le déterminisme) ; respectée. → `defer`.

Groupes routés en `patch` (G1-G11, détail dans les instructions de correction envoyées au sous-agent) ; aucun `intent_gap` ni `bad_spec` — pas de loopback, `review_loop_iteration` reste à 0.

## Design Notes

La story empiète volontairement sur AD-2, AD-3, AD-15 et AD-18 avant leurs stories "propriétaires" (2, 5) : AD-21 exige un diagnostic terminal *et* navigateur dès cette story, ce qui suppose un minimum de `trace`, `net` et `web`. Le principe qui évite tout conflit futur : chaque module ne pose ici que le sous-ensemble strictement nécessaire au diagnostic (catalogue de `kind` restreint, une seule route web, un seul état de session), et les stories suivantes *ajoutent* sans jamais réécrire cette base (AD-2 le formule explicitement pour le catalogue : « une story ajoute ses kind, mais ne change jamais l'enveloppe »).

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur
- `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (les tests marqués `model` sont sautés en l'absence de GGUF)
- `uv run wavestack` (manuel, avec un GGUF de test copié dans le dossier de données) -- expected: diagnostic non bloquant, navigateur ouvert sur `/diagnostic`

**Manual checks (if no CLI):**
- Vérifier que `uv run wavestack` sans aucun GGUF affiche un message de blocage clair en français, avec le champ de sélection de chemin.
