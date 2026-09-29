---
title: 'Estimateur GreenOps de tous les modèles (EcoLogits pour le cloud, CodeCarbon en local)'
type: 'feature'
created: '2026-09-29'
status: 'draft'
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
- `src/wavestack/web/static/app.js`, `index.html` -- ajouter la ligne « Empreinte estimée » et compléter la zone « Consommation ».
- `README.md` -- ajouter une section GreenOps : méthode, limites, installation de l'extra.
- Tests :
  - `tests/test_greenops.py` (nouveau) : EcoLogits réel, hors ligne ; CodeCarbon simulé si l'extra est absent ; `importorskip` pour la mesure réelle ;
  - les tests cloud et tour ;
  - `tools/e2e/run_e2e.py` : la ligne d'empreinte, sur le scénario cloud Gemini et sur le faux llama-server.

## Tasks & Acceptance

**Execution:**
- [ ] `pyproject.toml`, `uv.lock`, `wavestack.toml`, `src/wavestack/config.py` -- dépendances et déclarations.
- [ ] `src/wavestack/greenops.py` -- les estimateurs, isolés.
- [ ] `src/wavestack/models/openai_chat.py`, `src/wavestack/session/app_session.py`, `src/wavestack/trace/catalog.py`, le budget mémoire -- le branchement et les sommes.
- [ ] `src/wavestack/web/static/*` -- l'affichage.
- [ ] `tests/*`, `tools/e2e/*`, `README.md` -- la matrice, l'E2E et la documentation.

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
