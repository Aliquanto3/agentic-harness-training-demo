---
title: 'Estimateur GreenOps de tous les modèles (EcoLogits pour le cloud, CodeCarbon en local)'
type: 'feature'
created: '2026-09-29'
status: 'in-review'
baseline_commit: '950ead3b3270de378912ee544e6c97ca3eaa8618'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La formation parle de sobriété, mais WaveStack ne montre ni l'énergie ni les émissions d'un appel au modèle, qu'il soit local ou cloud. L'estimateur FinOps (story précédente) couvre le coût, pas l'empreinte.

**Approach:** Estimer, pour chaque appel à un modèle, l'énergie (Wh) et les émissions (g CO₂e), puis les additionner par tour et par séance, avec le même affichage que le FinOps :
- **modèles cloud :** méthode EcoLogits, avec la bibliothèque `ecologits` (cœur seul, hors ligne) ;
- **modèles locaux :** CodeCarbon hors ligne, en dépendance optionnelle.

Décisions de l'utilisateur (2026-09-29) :
- un estimateur GreenOps en plus du FinOps ;
- CodeCarbon autorisé ;
- tous les modèles couverts, si possible ;
- la méthode EcoLogits validée pour le cloud.

La spec est approuvée par délégation, pendant la nuit, et relue le matin.

## Boundaries & Constraints

**Always:**
- **Cloud :**
  - Appel à `ecologits.tracers.utils.llm_impacts(provider, model, output_tokens, latency_s, electricity_mix_zone)` après chaque appel. La latence est `duration_ms` de l'appel, et `output_tokens` inclut le raisonnement.
  - Correspondance déclarée par entrée : champ facultatif `impacts = { provider, model, zone }`, où `zone` est facultative (par défaut, celle du fournisseur dans EcoLogits). Correspondances à déclarer :
    - Groq → `huggingface_hub` / `openai/gpt-oss-120b` ;
    - Mistral → `mistralai` / `mistral-small-latest` ;
    - Gemini → `google_genai` / `gemini-3.5-flash-lite`.
  - Sans `impacts`, ou pour un modèle inconnu d'EcoLogits, pas d'estimation, avec la raison en français dans l'infobulle.
  - Les fourchettes (`RangeValue`) sont gardées en min et max, et les avertissements d'EcoLogits (architecture non publiée, multimodal) sont repris en français.
- **Local :**
  - Un `OfflineEmissionsTracker(country_iso_code="FRA", save_to_file=False, log_level="error", measure_power_secs=1)` par appel, démarré et arrêté autour de la génération.
  - Deux modes de mesure :
    - `tracking_mode="process"` pour le moteur intégré (llama-cpp-python, dans le processus) ;
    - `"machine"` pour Ollama et llama-server, processus externes, avec la mention « poste entier ».
  - On ne garde que l'énergie (`energy_consumed`, en kWh). Les émissions viennent de l'intensité `[greenops] local_gco2e_per_kwh` (41,4 par défaut : mix France d'EcoLogits, cycle de vie, cohérent avec le cloud).
  - Le commentaire du toml cite aussi les chiffres RTE 2025 (19,6 g direct, environ 29 g en cycle de vie).
  - L'interface dit « estimation (TDP × charge, sans droits administrateur) » : sous Windows sans RAPL, c'est une estimation, pas une mesure.
- **Dépendances :**
  - `ecologits` devient une dépendance normale (quelques centaines de Ko, cœur pydantic, wrapt et packaging).
  - `codecarbon` est un extra `greenops` (`uv sync --extra greenops`), environ 150 Mo installé et environ 70 Mo de RSS au premier usage.
  - Ce coût est compté une seule fois, à vie, par le budget mémoire (`[greenops] codecarbon_cost_mb = 80`), comme FAISS dans l'atelier RAG. Refusé par le budget, il rend l'estimation locale indisponible, avec la raison.
  - Sans l'extra, l'estimation locale est indisponible et l'infobulle donne la commande d'installation. Le reste fonctionne.
- **Aucun appel réseau :** EcoLogits et le tracker hors ligne n'en font aucun. Un test doit le prouver en passant par la garde réseau existante.
- **Même registre et mêmes emplacements que le FinOps :**
  - `model_call_ended` gagne `energy_wh_min`, `energy_wh_max`, `gco2e_min`, `gco2e_max`, `impact_method` (`ecologits` ou `codecarbon`) et `impact_note_fr` ;
  - `turn_ended` et `consumption_updated` portent les sommes min et max ;
  - dans le corps déplié d'un appel : « Empreinte estimée : 0,11 Wh · 0,046 g CO₂e », ou une fourchette « 0,035–0,23 Wh » ;
  - l'en-tête de tour et la zone « Consommation » de la barre haute sont complétés.
- Le calcul se fait dans la session ou l'adaptateur (AD-1). Les chiffres suivent le format français, avec 2 chiffres significatifs.

**Never:**
- Pas d'appel réseau, et pas d'`EcoLogits.init()` : aucune instrumentation des SDK.
- Pas de fichier `emissions.csv`.
- Pas d'estimation GPU.
- Pas d'estimation GreenOps pour l'embedding ou le reranker du RAG (hors périmètre de cette story).
- Pas de blocage d'un tour si l'estimation échoue : on trace un avertissement, et l'appel n'a pas d'empreinte.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Cloud connu | Gemini, 1 000 tokens de sortie, 5 s | `energy_wh_min < energy_wh_max` (fourchette), `impact_method = ecologits`, avertissement « architecture non publiée » en français | — |
| Cloud Groq | gpt-oss via `huggingface_hub` | Estimation non vide, `impact_method = ecologits` | — |
| Cloud sans `impacts` | Entrée sans correspondance | Aucun champ d'empreinte, raison dans l'infobulle | — |
| Modèle inconnu d'EcoLogits | `impacts.model` inconnu | Pas d'empreinte, `impact_note_fr` donne la raison | Exception d'EcoLogits attrapée |
| Local intégré | 2B dans le processus, extra installé | `impact_method = codecarbon`, énergie > 0, g CO₂e = kWh × 41,4 | — |
| Local sans extra | CodeCarbon absent | Pas d'empreinte, commande `uv sync --extra greenops` dans l'infobulle | — |
| Local sur serveur | Ollama ou llama-server | Mode `machine`, note « poste entier » | — |
| Budget mémoire | CodeCarbon refusé par le budget | Estimation locale indisponible, raison du budget | — |
| Pas de réseau | EcoLogits et tracker | Aucune `outbound_request`, aucune connexion | — |

</frozen-after-approval>

## Code Map

- `pyproject.toml` / `uv.lock` -- `uv add ecologits` et `uv add --optional greenops codecarbon`, à la manière de l'extra `compression` (Headroom). Voir `src/wavestack/compression/env.py` pour la détection d'un extra absent.
- `wavestack.toml` :
  - ajouter `impacts` aux trois entrées cloud ;
  - créer la section `[greenops]` (`local_gco2e_per_kwh`, `codecarbon_cost_mb`), commentée avec les sources : EcoLogits, CodeCarbon, RTE.
- `src/wavestack/config.py` -- ajouter `CloudImpacts` et le champ `impacts` à `CloudModel`, plus les propriétés de `[greenops]`.
- Nouveau module `src/wavestack/greenops.py`, le seul endroit qui importe EcoLogits et CodeCarbon (imports paresseux) :
  - `cloud_impacts(entry, output_tokens, latency_s) -> Impact | None` ;
  - `LocalMeter` (start/stop, mode process ou machine, budget) ;
  - la dataclass `Impact` (min, max, méthode, note).
- `src/wavestack/models/openai_chat.py` `run_call` -- empreinte cloud à côté du coût FinOps, dans le même registre (`consumption_updated`).
- `src/wavestack/session/app_session.py` :
  - l'émission locale de `model_call_ended` (≈ :6794, moteur local) : entourer la génération locale du `LocalMeter` ;
  - les sommes du tour ;
  - l'état pour le rechargement.
- `src/wavestack/trace/catalog.py` -- ajouter les nouveaux champs facultatifs.
- `src/wavestack/memory.py` (ou l'endroit où `faiss_cost_mb` est compté) -- ajouter le coût de CodeCarbon au premier usage.
- `src/wavestack/web/static/app.js`, `index.html`, `app.css` -- ajouter la ligne « Empreinte estimée » dans le corps de l'appel et l'en-tête du tour, et compléter le bloc `#consumption` du FinOps. Ce bloc fait deux lignes (« Dépense estimée », puis « 0,0008 $ + 0,0003 $ »), avec la phrase complète dans `title` et `aria-label`. La barre haute est déjà pleine à 1 600 px : la vérification E2E « barre haute : toutes les commandes entières » doit rester verte à 1 280, 1 440 et 1 600 px, en mode normal et en projection. L'empreinte de la séance y est visible seulement si elle tient, par exemple « · 0,12 g CO₂e » en fin de deuxième ligne ; sinon, dans la phrase de `title` et `aria-label`.
- Le FinOps (déjà livré sur cette branche) fournit le registre de la séance (`record_spend`, `session_spend`, `consumption_updated`, sous `_spend_lock`, dans `models/openai_chat.py`), les coûts par appel (`CallCost`, `model_call_ended.cost_*`), les sommes du tour (`_turn_costs` dans `app_session.py`, `turn_ended.cost_*`) et leur affichage (`costText`, `renderConsumption` dans `app.js`). Les étendre, sans les dupliquer. Un appel local n'a pas de coût, mais il a une empreinte : le registre et l'événement doivent l'accepter.
- `README.md` -- ajouter une section GreenOps : méthode, limites, installation de l'extra.
- Tests :
  - `tests/test_greenops.py` (nouveau) : EcoLogits réel, hors ligne ; CodeCarbon simulé si l'extra est absent ; `importorskip` pour la mesure réelle ;
  - les tests cloud et tour ;
  - `tools/e2e/run_e2e.py` : la ligne d'empreinte, sur le scénario cloud Gemini et sur le faux llama-server.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock`, `wavestack.toml`, `src/wavestack/config.py` -- dépendances et déclarations.
- [x] `src/wavestack/greenops.py` -- les estimateurs, isolés.
- [x] `src/wavestack/models/openai_chat.py`, `src/wavestack/session/app_session.py`, `src/wavestack/trace/catalog.py`, le budget mémoire -- le branchement et les sommes.
- [x] `src/wavestack/web/static/*` -- l'affichage.
- [x] `tests/*`, `tools/e2e/*`, `README.md` -- la matrice, l'E2E et la documentation.

**Acceptance Criteria:**
- Given un tour Gemini puis un tour du modèle local, when les deux sont finis, then chaque appel montre son empreinte (fourchette pour Gemini, mesure CodeCarbon pour le local) et la barre haute cumule les deux.
- Given WaveStack lancé sans l'extra `greenops`, when on fait un tour local, then le tour aboutit, l'empreinte locale est « indisponible », et la commande d'installation est donnée.

## Verification

**Commands:**
- `uv sync --extra compression --extra greenops` -- expected: installation sans erreur
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` -- expected: tout vert
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 FAIL ; puis `git restore tools/e2e/screenshots`

## Implementation Notes

## Spec Change Log

## Review Triage Log

Revue 1 (2026-09-30, trois relecteurs : aveugle (B), cas limites (EC), trous de vérification (VG)).

| # | Constat | Verdict | Preuve | Suite |
|---|---------|---------|--------|-------|
| 1 | Tracker CodeCarbon jamais arrêté si une exception survient hors des chemins `end()` (B, EC) | medium | `start()` avant le `try`, `stop()` seulement dans `end()` | patch : `try/finally` |
| 2 | `LocalMeter.start` peut lever (`_tracker()` hors `try`), et fait alors échouer le tour local ; `_grant` avant la recherche de la classe (EC) | medium | Relu dans `greenops.py` | patch |
| 3 | `codecarbon_cost_mb = inf` : `OverflowError` non rattrapé (EC) | low | `_int` ne rattrape que `TypeError` et `ValueError` | patch |
| 4 | Appel local en échec avant tout token compté dans l'empreinte, contrairement au cloud (EC) | low | `end('error')` mesure toujours | patch : même règle que le cloud |
| 5 | `energy_consumed` infini non filtré : `Infinity` dans le JSON (EC) | low | `max(0.0, kwh)` laisse passer `inf` | patch |
| 6 | Séance seulement locale : l'empreinte n'est pas soumise au contrôle de place et peut déborder de la barre à 1 280 px ou en projection (EC) | medium | `footprintOptional = paid && green` | patch : toujours contrôler la place |
| 7 | Décision de place figée avant le chargement des polices (EC) | low | Clé sans les polices | patch : `document.fonts.ready` |
| 8 | Premier appel local : 5 à 7 s d'attente sans rien à l'écran (B) | medium | Import de CodeCarbon et détection du processeur sur le chemin du tour | patch : préchauffage en arrière-plan |
| 9 | Groq estimé par un substitut (gpt-oss chez Hugging Face) sans explication dans l'interface (B) | low | L'explication n'est que dans le toml | patch : `note_fr` facultatif dans `impacts` |
| 10 | Local (électricité du poste seulement) et cloud (cycle de vie, fabrication comprise) additionnés sans le dire ; « cohérent avec le cloud » (B) | low | README, toml, infobulle | patch : le dire |
| 11 | Appel court affiché « 0 Wh » (B) | low | Pas de seuil d'affichage | patch : « < 0,001 Wh » |
| 12 | 41,4 g/kWh non relié aux données d'EcoLogits (B) | low | Constante en dur | patch : test qui compare au facteur FRA d'EcoLogits |
| 13 | Résumé du journal d'une séance seulement locale : « entrée 0 $ · sortie 0 $ · 0 appel » (B) | low | `eventSummary` | patch |
| 14 | README : l'extra demande le réseau ou un cache local de paquets (B) | low | Non dit | patch |
| 15 | Tests manquants : empreinte d'un appel cloud coupé après une sortie dans le tour ; empreinte visible au moins à la plus grande largeur ; libellé « Empreinte estimée » d'une séance seulement locale ; branche « sans l'extra » jamais jouée (drapeau `--no-greenops`) ; empreinte du sous-agent dans le tour ; « Tester » et « LLM nu » dans la séance (VG, B) | medium | Aucune suppression correspondante ne fait échouer un test | patch |
| 16 | Projection laissée allumée si l'E2E échoue entre les deux clics (EC) | low | `finally` ne remet que la fenêtre | patch |
| 17 | Empreinte estimée sans « ≈ » quand les tokens sont estimés (B) | low | Le libellé visible dit déjà « estimée » | rejeté |
| 18 | Cache du comptage des processeurs non vérifié ; verrou d'instance unique de CodeCarbon (B) | maybe-false | Mesuré par l'implémentation (environ 50 ms après le premier appel) | rejeté |
| 19 | Explications seulement dans les infobulles (B) | low | Même motif que le reste de l'interface | rejeté |
| 20 | `fitFootprint` provoque deux recalculs de mise en page par rendu (B) | low | Coût modeste, mesure sous la clé | rejeté |
| 21 | En-tête de tour long à 1 280 px (B) | low | L'en-tête passe à la ligne dans Orchestration | rejeté |
| 22 | Import d'EcoLogits hors budget mémoire ; `Impact.method` typé `str` (B) | low | Environ 5 Mo ; cosmétique | rejeté |
| 23 | Concurrence : classe de journalisation d'EcoLogits, budget vérifié sans le verrou du registre (EC) | low | Fenêtres étroites, premier appel seulement | rejeté |
| 24 | Appel cloud annulé avant toute sortie avec une empreinte (EC) | low | La requête est partie et a consommé ; même règle que le coût (entrée facturée) | rejeté |
