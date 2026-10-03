---
title: 'Fournisseurs natifs (2/5) : plafond de séance et prix de cache'
type: 'feature'
created: '2026-10-03'
status: 'done'
baseline_commit: '7f40fc19bc930a5221a34d8aae3c2c3c34507f93'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-fournisseurs-natifs/formats-natifs.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Rien ne borne la dépense d'une séance : avec Anthropic et OpenAI, payants dès le premier appel, une boucle d'outils ou une démonstration qui s'éternise peut coûter plus que prévu. Le coût estimé ignore aussi le prix réduit des tokens lus en cache, que ces fournisseurs facturent à part.

**Approach:** Un plafond `[finops] max_session_usd` (5 $ par défaut) est vérifié dans `run_call`, avant l'envoi, sur le total de la séance que tient déjà le registre de `consumption_updated` : quand ce total l'a atteint, un appel tarifé n'est pas envoyé et l'utilisateur lit pourquoi et comment relever le plafond (fr, en, de). `CloudPricing` reçoit deux prix de cache facultatifs ; quand l'entrée les déclare et que l'usage compte des tokens en cache, le coût d'entrée les applique ; sinon, le calcul ne change pas (CAP-4).

## Boundaries & Constraints

**Always:**
- Le plafond lit `_spend` (via le même verrou que `record_spend` / `session_spend`), sans second registre. Il porte sur `total_in_usd + total_out_usd`, tous appels tarifés compris (tours, sous-agent, « Tester », « LLM nu »).
- Un appel est « tarifé » quand son entrée déclare `pricing`. Un appel sans `pricing` (Gemma, local) n'est jamais refusé.
- La vérification a lieu avant `pace` et avant `model_call_started` : un appel refusé n'émet aucun `model_call_*`, n'atteint pas le réseau (aucun `outbound_request`) et ne coûte rien. L'appel en cours n'est jamais interrompu : on peut donc dépasser le plafond de la valeur d'un appel.
- Le refus est un `ProviderError` (cause `max_session_usd`, `http_status` nul), si bien que les trois appelants l'affichent déjà (`harness_error` du tour ou du sous-agent, message de « LLM nu », échec de « Tester »). Le message dit le plafond, le total dépensé, que l'appel n'est pas parti, et comment relever le plafond : `[finops] max_session_usd` dans `settings.json`, WaveStack arrêté, puis relancer (le total ne revient à zéro qu'au relancement).
- `Config.max_session_usd` : `[finops] max_session_usd`, 5 par défaut ; une valeur illisible, non finie ou négative vaut 5 (même style que `eur_per_usd`). Il n'y a pas de valeur qui désactive le plafond.
- `run_call(..., max_session_usd: float | None = None)` : `None` ne vérifie rien (tests existants inchangés) ; les trois appelants passent `self.cfg.max_session_usd`.
- Prix de cache : `cache_read_usd_per_mtok` et `cache_write_usd_per_mtok`, facultatifs, `ge=0`, finis. Usage au format pivot : `prompt_tokens` compte TOUTE l'entrée ; `prompt_tokens_details.cached_tokens` les tokens lus en cache (forme OpenAI) ; `prompt_tokens_details.cache_write_tokens` ceux écrits en cache (clé que l'adaptateur Anthropic remplira en story 3). Coût d'entrée = (prompt − lus − écrits) × entrée + lus × lecture + écrits × écriture, chaque prix absent valant le prix d'entrée.
- Textes en `content/messages.yaml`, `content/i18n/en/messages.yaml`, `content/i18n/de/messages.yaml` ; montants au format de la langue (`usd_price_fr` ou équivalent).

**Never:**
- Pas de plafond par appel ni d'estimation prédictive du coût de l'appel à venir.
- Pas d'interface pour régler le plafond (fichier seulement).
- Ne pas changer le coût des entrées actuelles (aucune ne déclare de prix de cache).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Sous le plafond | Plafond 0,01 $, total 0,005 $, entrée tarifée | Appel envoyé normalement | N/A |
| Plafond atteint | Plafond 0,01 $, total ≥ 0,01 $ | Aucune requête au transport, aucun `model_call_started` ; tour terminé par `harness_error` qui dit plafond, total et `max_session_usd` | `ProviderError` |
| Entrée sans prix | Plafond atteint, entrée sans `pricing` | Appel envoyé | N/A |
| Langues | Plafond atteint, session en `en` puis `de` | Message traduit, montants au format de la langue | N/A |
| Valeur illisible | `max_session_usd = "abc"`, `nan`, `-1` | 5 | N/A |
| Cache lu | Prix 1 / 5 / lecture 0,10 ; usage `prompt_tokens = 1000`, `cached_tokens = 800` | Entrée = 200 × 1 + 800 × 0,10 (par 10⁶) | N/A |
| Cache sans prix | Même usage, entrée sans prix de cache | Entrée = 1000 × 1 (inchangé) | N/A |
| Cache écrit | `cache_write_tokens = 100`, écriture 1,25 | Écrits comptés à 1,25 | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/cloud_base.py` -- `CloudPricing` est lu par `call_cost` ; `_spend`, `_spend_lock`, `record_spend`, `session_spend` (registre unique) ; `run_call` : point unique des appels tarifés ; y ajouter la vérification (avant `pace`) et lire les tokens en cache dans `ended()` pour `call_cost`. `ProviderError` pour le refus.
- `src/wavestack/config.py:152` `CloudPricing` -- deux champs facultatifs ; `:686` `eur_per_usd` -- modèle de la propriété `max_session_usd`.
- `src/wavestack/session/app_session.py:7905` (tour et sous-agent), `:8722` (« LLM nu ») ; `src/wavestack/session/diagnostic.py:1101` (« Tester ») -- passer `max_session_usd=self.cfg.max_session_usd`. Leurs `except ProviderError` affichent déjà l'erreur : ne pas les changer.
- `src/wavestack/cloud.py` `usd_price_fr` -- format des montants par langue.
- `content/messages.yaml:1164` `models.openai_chat.*` -- y placer `session_cap` (et ses traductions en/de au même endroit) ; clés lues par `Message(...)`.
- `wavestack.toml:208` `[finops]` -- ajouter `max_session_usd = 5` commenté ; corriger le commentaire qui dit que les remises de cache ne sont pas prises en compte.
- `tests/test_cloud.py:1575-1720` -- tests FinOps existants (modèle pour les nouveaux) ; `tests/conftest.py` remet le registre à zéro (`reset_spend`).

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/config.py` -- `CloudPricing.cache_read_usd_per_mtok`, `cache_write_usd_per_mtok` (`float | None`, `ge=0`, finis) ; propriété `Config.max_session_usd` -- CAP-4.
- [x] `src/wavestack/models/cloud_base.py` -- `call_cost(..., cached_read=0, cached_write=0)` ; `run_call` lit `prompt_tokens_details` de l'usage et refuse avant l'envoi au-delà de `max_session_usd` -- CAP-4.
- [x] `src/wavestack/session/app_session.py`, `src/wavestack/session/diagnostic.py` -- passer le plafond aux trois `run_call`.
- [x] `content/messages.yaml`, `content/i18n/en/messages.yaml`, `content/i18n/de/messages.yaml` -- message du plafond (et indication si utile).
- [x] `wavestack.toml` -- `max_session_usd = 5` et commentaires à jour.
- [x] `tests/test_cloud_cap.py` (ou `tests/test_cloud.py`) -- cas de la matrice, dont un tour complet sur `httpx.MockTransport` qui prouve qu'aucune requête n'est partie.

**Acceptance Criteria:**
- Given une séance dont le total a atteint le plafond, when l'utilisateur relance un tour avec un modèle tarifé, then il lit le message du plafond dans sa langue, et la jauge de dépense ne bouge pas.
- Given `pytest` en quarts, when on le joue, then tout est vert.

### Review Findings

Revue de la PR #20 du 2026-10-03, groupe 4a (tests), quatre couches.

- [x] [Review][Patch] La vérification du plafond AVANT `pace` (Always : « avant `pace` » ; docstring : « a refused call takes no slot ») n'est pas testée : les tests de refus utilisent `gemini` et `gemma`, sans `min_interval_s`, et `test_the_cap_is_checked_again_after_the_spacing_wait` part sous le plafond. Supprimer la première vérification (`cloud_base.py:859-860`) ne fait échouer aucun test. Ajouter un `run_call` sur une entrée espacée (copie avec `min_interval_s = 1`, ou `mistral`), plafond déjà atteint : `pace` jamais appelé, `_last_start` sans créneau. [`tests/test_cloud_cap.py:220`]
- [x] [Review][Patch] Sessions de `test_cloud_cap.py` jamais fermées (`_cloud_session`, six tests), alors que la story 1 l'a corrigé pour `test_cloud_api.py` (triage #6). Fait par une fixture du module qui ferme toute session ouverte par le test (`_session`, et l'`AppSession` de `_app`). [`tests/test_cloud_cap.py:84`]

## Implementation Notes

- Le refus est construit par `cloud_base.session_cap_error(entry, max_session_usd)`, appelé en tête de `run_call` (avant `pace`) ; il lit `_spend` sous `_spend_lock`. Montants en `Lazy(usd_price_fr)`, rendus dans la langue de la séance.
- Le message (`models.openai_chat.session_cap`) porte le plafond, le total, « l'appel n'est pas parti » et la marche à suivre (`[finops] max_session_usd` dans `settings.json`, WaveStack arrêté, relance) ; indications : `hint.free_models` (modèles sans prix utilisables) puis `back_to_local`.
- `call_cost` borne les tokens en cache à `prompt_tokens` (lus d'abord, puis écrits) ; `_cached_tokens` lit `prompt_tokens_details.cached_tokens` et `cache_write_tokens`, 0 si absents ou illisibles.
- `wavestack.toml` : `max_session_usd = 5` actif (même valeur que le défaut), commentaire FinOps corrigé sur le cache.
- Tests : `tests/test_cloud_cap.py` (matrice, tour, « LLM nu », « Tester », langues en/de, prix de cache, usage pivot lu de bout en bout).

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-03) : blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG).

| # | Source | Constat | Verdict | Preuve | Route |
|---|---|---|---|---|---|
| 1 | BH, EC | Plafond vérifié avant `pace` seulement : un appel concurrent qui se termine pendant l'attente laisse partir l'appel ; plusieurs appels concurrents passent ensemble, alors que les textes promettent « un appel » de dépassement | medium | `cloud_base.py:767-775`, attente de `pace` jusqu'à 60 s ; commentaire `wavestack.toml` et docstring | patch (revérifier après `pace` ; dire « un appel par appel en cours ») |
| 2 | VG, BH | Gardes de `_cached_tokens` (non-dict, bool, chaîne, négatif) et bornes de `call_cost` non testées | medium | Seuls des entiers bien formés sont testés (`test_cloud_cap.py:193-244`) | patch |
| 3 | EC | `cached_tokens` NaN ou infini (accepté par `json.loads`) : `int()` lève dans `ended()` | low | `cloud_base.py:281-285` ; correction directe (`math.isfinite`) | patch |
| 4 | EC | `max_session_usd` entier géant : `OverflowError` non rattrapé ; booléen lu 1 $ ou 0 $ | low | `config.py:708-711` ; corrections directes | patch |
| 5 | BH | README (FinOps) et commentaire `pricing` de `wavestack.toml` muets sur le plafond et les prix de cache ; `0` non documenté | low | README l. ~920-935 | patch |
| 6 | BH | Docstring de `ProviderError.payload` : « `cause` est le texte du fournisseur » faux pour ce refus | low | `cloud_base.py` `payload` | patch |
| 7 | VG, BH | `test_run_call_without_a_cap_checks_nothing` n'appelle pas `run_call` ; l'assertion de langue accepte les deux formats | low | `test_cloud_cap.py:181-187` | patch |
| 8 | BH | Plafond invisible avant le refus (jauge sans « x $ sur 5 $ ») | low | Hors intention de la story ; amélioration pédagogique | defer |
| 9 | BH | Comptes de tokens en cache absents de `model_call_ended` | low | Champs publics nouveaux, non demandés | rejeté |
| 10 | BH | Prix de cache non affichés (`price_fr`) | low | Inoffensif ; ajout de surface | rejeté |
| 11 | BH, EC | Mistral (gratuit en pratique) compte au plafond ; prix nuls refusés ; indication qui nomme Gemma | low | Le total affiché le compte déjà ; aucune entrée à prix nuls | rejeté |
| 12 | BH | Format des montants différent de la jauge ; conseil de relance incomplet | low | Cosmétique ; le message dit déjà que le total revient à zéro au relancement | rejeté |
| 13 | EC | Égalité flottante au plafond ; plafond inférieur à 0,00005 $ affiché 0,00 $ | low | Négligeable | rejeté |
| 14 | BH | Contrat de la story 3 : `prompt_tokens` doit inclure les tokens de cache d'Anthropic | low | Se règle dans la spec de la story 3 | rejeté (repris en story 3) |
| 15 | BH | Chemin du sous-agent non testé | low | Même `run_call`, même `except` que le tour | rejeté |

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest tests/test_cloud.py tests/test_cloud_api.py tests/test_backend_messages.py tests/test_content_language.py -q` -- expected: vert (le contrôle des textes couvre les trois langues)
- `pytest` complet en quatre quarts, un à la fois -- expected: vert
