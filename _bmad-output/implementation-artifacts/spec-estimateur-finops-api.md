---
title: 'Estimateur FinOps des appels aux API cloud'
type: 'feature'
created: '2026-09-29'
status: 'done'
baseline_commit: 'f1567cf9a6516f95a64a4095262775b27751ce61'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Rien, dans WaveStack, ne dit ce que coûte un appel à un modèle cloud. Pourtant, c'est une question clé de la formation (FinOps), et un point à surveiller pendant les démos payantes, avec Gemini par exemple.

**Approach:** Chaque entrée `[[cloud.models]]` déclare ses prix (entrée et sortie, en dollars par million de tokens, avec la date de relevé). Le harnais calcule le coût d'entrée et le coût de sortie de chaque appel cloud, puis le total du tour et le total de la séance. L'interface les affiche séparément, toujours comme des estimations.

Décision de l'utilisateur (2026-09-29) : une story à part, après Gemini. Elle est approuvée par délégation : l'utilisateur a demandé d'enchaîner pendant la nuit, et relira cette spec le matin.

## Boundaries & Constraints

**Always:**
- Le calcul est fait par la session ou l'adaptateur, jamais par le front (AD-1 : le front met en forme, il ne calcule pas).
- Dans `CloudModel`, un nouveau champ `pricing` facultatif : `{ input_usd_per_mtok, output_usd_per_mtok, checked }`. Les deux prix sont des flottants ≥ 0, `checked` est une date ISO. Sans `pricing`, pas de coût, et aucun affichage de coût pour ce modèle.
- Prix relevés le 2026-09-29 sur les pages officielles :
  - Groq `openai/gpt-oss-120b` : 0,15 / 0,60 ;
  - Mistral `mistral-small-latest` (Small 4) : 0,15 / 0,60 ;
  - Gemini `gemini-3.5-flash-lite` : 0,30 / 2,50.
  - `notes_fr` de Mistral : sur le plan gratuit, le coût réel est nul ; le prix affiché est le prix catalogue.
- Coût d'un appel :
  - entrée = `prompt_tokens` × prix d'entrée / 10⁶ ;
  - sortie = `output_tokens` × prix de sortie / 10⁶. `output_tokens` inclut les tokens de raisonnement, même ceux que Gemini exclut de `completion_tokens` (règle total − prompt du lot Gemini).
  - Si les tokens sont estimés (`usage_source = estimate`), le coût l'est aussi : « ≈ » partout.
- Tous les appels payants comptent dans le total de la séance, dans un seul registre protégé par un verrou (`openai_chat`, à côté de `pace`) :
  - les tours, le sous-agent, « Tester » au diagnostic, l'écran « LLM nu ».
  - Ni « Vider la conversation » ni « Réinitialiser » ne le remettent à zéro : l'argent dépensé l'est. Seul un relancement de WaveStack le remet à zéro.
- Les montants restent en dollars (la devise de facturation). Le total de la séance donne aussi sa conversion en euros, au taux de `[finops] eur_per_usd` (0,86 par défaut, borné de 0,5 à 2).
- Affichage en français :
  - « Coût estimé : entrée … $ · sortie … $ » dans le corps déplié de chaque appel cloud (le compteur de tokens) ;
  - le total du tour dans l'en-tête du tour d'Orchestration ;
  - dans la barre haute, un total « Dépense API » (entrée et sortie séparées, conversion en euros dans l'infobulle), visible dès le premier appel payant ;
  - une colonne « Prix » dans `/models`, une ligne « Prix » au diagnostic.
  - Les montants ont 4 chiffres significatifs, avec la virgule française.
- Aucun nouveau jeton de design : seulement les classes existantes (`.number`, `.token-counter`, `.gauge-figures`).

**Never:**
- Pas de coût pour les modèles locaux (pas de « 0 $ » affiché).
- Pas de plafond de dépense qui bloque un tour (hors périmètre).
- Pas de lecture des en-têtes de facturation du fournisseur.
- Pas de persistance du total sur disque.
- Pas de nouvelle dépendance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Appel avec usage | Gemini, `prompt_tokens` 65, `total_tokens` 1 065, `completion_tokens` 14 | `cost_in_usd` = 65×0,30/10⁶, `cost_out_usd` = 1 000×2,50/10⁶, `cost_source = api` | — |
| Appel sans usage | Mistral (`stream_usage = false`) | Coûts calculés sur l'estimation, `cost_source = estimate`, « ≈ » affiché | — |
| Entrée sans prix | `pricing` absent | Aucun champ de coût, aucun affichage, le total inchangé | — |
| Tour à plusieurs appels | Outil, 2 appels, plus le sous-agent | `turn_ended` porte la somme entrée et sortie de tous les appels du tour | — |
| « Tester » et « LLM nu » | Appels hors tour | Comptés dans le total de la séance (`consumption_updated`) | — |
| Réinitialiser | Après des appels payants | Le total de la séance est inchangé | — |
| Prix invalide | `input_usd_per_mtok = -1` | Entrée écartée au chargement, raison en français (comportement existant) | déjà géré par `cloud_models` |

</frozen-after-approval>

## Code Map

- `wavestack.toml` -- ajouter `pricing` aux entrées groq, mistral et gemini, et la section `[finops] eur_per_usd` avec son commentaire.
- `src/wavestack/config.py` :
  - `CloudModel` (`extra="forbid"`) : ajouter `pricing: CloudPricing | None` ;
  - `Config` : ajouter la propriété `eur_per_usd` (bornée, sur le modèle de `_float`).
- `src/wavestack/models/openai_chat.py` :
  - `run_call` (`ended()`) : calculer les coûts quand `isinstance(entry, CloudModel) and entry.pricing` ;
  - les écrire dans `model_call_ended` (`cost_in_usd`, `cost_out_usd`, `cost_source`) et sur `ChatCall` ;
  - mettre à jour le registre de la séance, puis émettre `consumption_updated` (`total_in_usd`, `total_out_usd`, `calls`, `approx`).
- `src/wavestack/trace/catalog.py` -- ajouter à `ModelCallEndedPayload` les champs facultatifs à `None`, et à `TurnEndedPayload` `cost_in_usd`/`cost_out_usd`, facultatifs. Créer `ConsumptionUpdatedPayload`, enregistré dans `PAYLOAD_MODELS`.
- `src/wavestack/session/app_session.py` :
  - ajouter au tour les coûts des `ChatCall` (principal et sous-agent) ;
  - `turn_ended` (≈ :5542) les porte quand le tour a coûté quelque chose ;
  - `/api/state` expose le total de la séance, pour le rechargement de la page.
- `src/wavestack/web/static/app.js` :
  - `callBody()` (compteur de tokens), `headParts` (en-tête de tour) ;
  - la barre haute (`#consumption` près de `#gauge-figures`, zone « Consommation » que la story GreenOps complétera) ;
  - la gestion de `consumption_updated`, et le rechargement depuis l'état.
- `src/wavestack/web/static/index.html` -- ajouter l'emplacement `#consumption`.
- `src/wavestack/models/catalog.py` `ModelEntry` et `cloud_entries` -- ajouter `price_fr`. Dans `models.html`, ajouter la colonne « Prix » (et passer `colSpan` de 8 à 9).
- `src/wavestack/session/diagnostic.py` `cloud_rows`, `diagnostic.html` -- ajouter la ligne « Prix ».
- `README.md` -- ajouter une section FinOps courte : prix déclarés, estimation, mise à jour des prix.
- Tests :
  - `tests/test_cloud.py` : le modèle Provider/MockTransport, lignes de la matrice ;
  - `tests/test_model_catalog.py`, `tests/test_web_app.py` ;
  - `tools/e2e/run_e2e.py` : vérifier la ligne de coût et le total dans un scénario cloud existant (`s_gemini_shape`), le faux fournisseur donnant `usage`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/config.py`, `wavestack.toml` -- `pricing` et `[finops]` -- les prix déclarés et datés.
- [x] `src/wavestack/models/openai_chat.py`, `src/wavestack/trace/catalog.py` -- coûts par appel, registre de la séance, `consumption_updated` -- un seul endroit calcule.
- [x] `src/wavestack/session/app_session.py` -- le total du tour et l'état -- pour l'en-tête du tour et le rechargement.
- [x] `src/wavestack/web/static/*`, `src/wavestack/models/catalog.py`, `src/wavestack/session/diagnostic.py` -- affichages.
- [x] `tests/*`, `tools/e2e/*` -- la matrice, l'affichage et l'E2E.
- [x] `README.md` -- la documentation.

**Acceptance Criteria:**
- Given un tour Gemini avec outil, when il se termine, then chaque appel montre son coût d'entrée et son coût de sortie, l'en-tête du tour leur somme, et la barre haute le total de la séance, entrée et sortie séparées.
- Given un rechargement de la page, when l'état est relu, then le total de la barre haute est le même qu'avant.
- Given `/models` ouvert, when la page s'affiche, then chaque modèle cloud avec `pricing` montre « 0,30 $ / 2,50 $ » par million de tokens (entrée / sortie), et un modèle local « — ».

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` -- expected: tout vert
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 FAIL ; puis `git restore tools/e2e/screenshots`

## Implementation Notes

## Spec Change Log

## Review Triage Log

Revue 1 (2026-09-30, trois relecteurs : aveugle (B), cas limites (EC), trous de vérification (VG)).

| # | Constat | Verdict | Preuve | Suite |
|---|---------|---------|--------|-------|
| 1 | Appel coupé après une sortie, facturé : aucun test, et le total du tour et celui de la séance peuvent diverger (VG, B) | medium | Aucun test ne diffuse du contenu avant une erreur ; retirer `exc.cost = out.cost` ne fait échouer aucun test | patch : test |
| 2 | Taux `[finops] eur_per_usd` configuré jamais observé dans un événement (VG) | medium | Tous les tests utilisent 0,86, qui est aussi la valeur par défaut du paramètre | patch : test à 0,92 |
| 3 | Taux `nan` ramené à 0,5, garde `isfinite` morte (VG, B, EC) | low | `_float` borne avant le test : `max(0.5, nan)` vaut 0,5 | patch : tester la finitude avant de borner, et tester `nan`, `inf` et 0,1 |
| 4 | `consumption_updated` émis hors du verrou : deux appels concurrents (« Tester » pendant un tour) peuvent émettre dans le désordre (EC) | low | `record_spend` rend la charge sous verrou, mais l'émission se fait après | patch : émettre sous le verrou |
| 5 | Barre haute : « Dépense API » sans marque d'estimation quand les tokens viennent de `usage`, alors que l'intention dit « toujours comme des estimations » (EC) | medium | `renderConsumption` n'écrit « Estimation » que dans l'infobulle | patch : libellé visible « Dépense API estimée », et « estimé » dans l'en-tête du tour |
| 6 | README : l'annulation facturée à l'entrée, les remises de cache et les prix par paliers ignorés, le taux de change sans date (B) | low | Le README ne dit rien de ces cas | patch : trois phrases dans le README et un commentaire daté dans le toml |
| 7 | Libellé « relevé le … ; coût d'un appel estimé » ambigu (B) | low | Texte de `price_reason_fr` | patch : « le coût de chaque appel en est une estimation » |
| 8 | « ≈ » jamais vérifié dans l'interface (VG) | maybe-false | Aucun faux fournisseur tarifé sans `usage` dans l'E2E | defer |
| 9 | Refus `tool_use_failed` (HTTP 400) facturé à l'entrée (EC) | maybe-false | Groq peut facturer l'entrée d'un appel refusé en génération ; non vérifiable ici | rejeté (hypothétique) |
| 10 | `usage` sans `prompt_tokens` marqué `api` (EC) | false | Les trois fournisseurs déclarés donnent `prompt_tokens`, ou pas d'`usage` du tout | rejeté |
| 11 | La mise en garde du plan gratuit de Mistral n'apparaît pas dans l'interface (B) | false | L'intention figée la place dans `notes_fr`, affiché à l'avertissement | rejeté |
| 12 | Infobulle seulement accessible au survol ; élément réductible à zéro (B) | low | Même motif que les autres éléments de la barre haute ; les largeurs sont vérifiées par l'E2E complet | rejeté |
| 13 | Tenue de la spec (notes vides, statut) (B) | false | La correction consiste à éditer la spec | rejeté (règle) |
| 14 | Prix de plus de 4 décimales arrondi (B, EC) | low | Prix réels à 2 décimales | rejeté |
| 15 | `CallCost.source` typé `str` (B) | low | Cosmétique | rejeté |
| 16 | « Tester » ne montre pas son coût au diagnostic ; aucun contenu pédagogique FinOps (B) | false | Hors de l'intention (affichage demandé : appel, tour, séance, `/models`, ligne « Prix ») | rejeté |
| 17 | Exception autre que `ProviderError` : comptée dans la séance, pas dans le tour (B) | low | Seules des erreurs de programmation passent par là, et le tour échoue alors | rejeté |

## Vérification finale (2026-09-30, nuit)

- `ruff check`, `ruff format --check` : propres.
- `pytest` complet, joué en deux moitiés au premier plan (mémoire du poste) : 845 et 501 réussis, 9 sautés.
- E2E complet, joué en quatre tranches : 715 vérifications réussies, 0 échec. La tranche finale est rejouée après le correctif de la barre haute.
- Correctif pendant la vérification : la dépense sur une ligne était coupée à 1 600 px (378 px demandés, 35 disponibles). Elle devient un bloc de deux lignes, « Dépense estimée » puis « 0,0008 $ + 0,0003 $ », de 102 × 29 px. La phrase complète est dans `title` et `aria-label`.
- Contrepartie : quand une dépense s'affiche, les chiffres de la jauge et le sélecteur de scénario se resserrent. Le texte complet reste dans l'infobulle. La vérification de la barre haute passe à 1 280, 1 440 et 1 600 px, en mode normal et en projection.
