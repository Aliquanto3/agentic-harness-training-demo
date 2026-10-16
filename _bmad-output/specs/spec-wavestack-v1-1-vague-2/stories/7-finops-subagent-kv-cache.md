---
id: SPEC-wavestack-v1-1-vague-2-story-7
status: review
companions:
  - SPEC.md
  - finops.md
  - ux/DESIGN.md
  - ux/EXPERIENCE.md
  - stories/6-finops-cache-compression.md
---

# Story 7 : FinOps du sous-agent isolé et KV-cache local (partie 2 de CAP-7)

## Ce qui est livré

- **Sous-agent** : `session/app_session.py` (`_delegate`) prend l'empreinte de `_turn_costs`,
  `_turn_impacts` et de la nouvelle liste `_turn_call_tokens` (tokens de chaque appel, main et
  sous-agent, dans le même ordre) avant `_run_subagent`, puis la différence après : le
  `subagent_ended` porte désormais, seulement quand la délégation a fait au moins un appel
  qui en a un :
  - `input_tokens`, `output_tokens` : la somme de ses propres appels, jamais ceux de
    `delegate` lui-même ni du reste du tour ;
  - `cost_in_usd`, `cost_out_usd`, `cost_source` : le même calcul que `turn_ended`
    (`_turn_cost`, réutilisé sur la tranche), absent sur un sous-agent local (pas de prix) ;
  - `energy_wh_min/max`, `gco2e_min/max` : idem avec `_turn_impact`, absent sans empreinte
    estimée.
  - `_turn_cost`/`_turn_impact` acceptent désormais une liste optionnelle (au lieu de
    toujours lire `self._turn_costs`/`_turn_impacts`), pour éviter de dupliquer le calcul.
- **KV-cache local** : `models/servers.py` (`LlamaServerEngine.complete`) lit en plus,
  quand le dernier bloc de `/completion` les donne, `timings.cache_n` et
  `timings.prompt_per_second` (`_last_cache_n`/`_last_prompt_per_second`, exposés par la
  propriété `last_cache_reuse`) ; `None` sur un ancien serveur qui ne les envoie pas, sur
  Ollama ou sur le moteur en cours de processus (aucun des deux ne les a). `app_session.py`
  (`_call_model_local`) les lit sur la première génération de l'appel (celle qui lit vraiment
  le contexte, comme `_note_read_rate`) et les ajoute à `model_call_ended` :
  `kv_cache_tokens`, `kv_prompt_per_second` — absents sans eux, jamais à 0 par défaut.
- **Interface** (`web/static/app.js`) :
  - `delegateBody` (ligne « Délégation au sous-agent ») gagne une ligne dépliable
    (`subCostNode`) : « Sous-agent : 3 210 tokens · 0,0134 $ · 0,3 Wh », dépliée sur
    Entrée/Sortie (tokens + $ chacun) et Empreinte ; sans coût (sous-agent local), seuls les
    tokens et l'empreinte (si connue) apparaissent ; absente sans aucun des deux ;
  - `callBody` (compteur de l'appel) gagne la ligne « Mémoire de contexte » (`kvCacheNode`),
    arrivant dépliée (flux 3) : « *n* tokens repris sans recalcul · environ *x* s évitées »,
    son dépli donnant « Recalculés » et « Sans cache » (tokens, débit, temps) et la source
    (`timings.cache_n`, `timings.prompt_per_second`) ; absente sans `timings`.
- Schémas de traçabilité (`trace/catalog.py`) : `SubagentEndedPayload` et
  `ModelCallEndedPayload` déclarent les nouveaux champs, tous optionnels.
- `models/engine.py` : la propriété optionnelle `last_cache_reuse` documentée dans le
  `Protocol Engine` (lue par `getattr`, comme `dimensions`).
- i18n : clés `main.orch.sub.cost_*` et `main.orch.kv.*` ajoutées en fr, en, de.

## Décisions

- Les montants du sous-agent sont pris par différence de longueur des listes du tour
  (`_turn_costs`/`_turn_impacts`/`_turn_call_tokens`) avant/après `_run_subagent`, bornée par
  `subagent_max_calls` : pas de parcours de la séance, un slice de la tranche du tour.
- Le débit de préremplissage retenu est celui de la **première** génération de l'appel (comme
  `_note_read_rate`) : une génération suivante du même appel (après une coupe de raisonnement)
  relit un contexte déjà presque tout en cache, donc un `cache_n`/`prompt_per_second` qui ne
  dirait plus rien d'utile.
- Le calcul affiché (`finops.md`) est seulement « tokens repris ÷ débit » = temps évité ;
  pas de ré-estimation du temps de lecture complet côté harnais (le dépli le montre quand
  même, à partir des mêmes deux champs, pour que le calcul reste vérifiable à l'œil).
- Le serveur de test E2E (`tools/e2e/fake_local_server.py`) n'envoie toujours pas `cache_n`
  (commentaire existant : « no cache here ») : aucun scénario n'affiche donc la ligne
  « Mémoire de contexte » aujourd'hui, comme pour la ligne « Cache de prompt » de la story 6.

## Hors périmètre (reste à faire)

- Le bilan de séance (barres sans optimisation / coût réel) : story 9. Les champs du
  sous-agent et de la KV-cache sont déjà des nombres simples dans des événements du tour,
  sommables sans changement supplémentaire côté backend.
- Aucune mention d'un facteur (« 15× » ou autre) : aucune source primaire du fournisseur
  n'a été trouvée pour l'écart cache/sans-cache ; la story reste au calcul vérifiable
  (prix/débit déclarés), jamais à un chiffre tiers non sourcé.

## Tests

- `tests/test_model_servers.py` : `test_llama_server_kv_cache_reuse_in_model_call_ended`
  (`timings.cache_n`/`prompt_per_second` → `kv_cache_tokens`/`kv_prompt_per_second`) et
  `test_llama_server_no_kv_cache_timings_is_absent` (un serveur qui n'en envoie pas : les
  deux champs absents, jamais à 0).
- `tests/test_subagent.py` : `test_cloud_sub_agent_has_its_own_tokens_and_cost_line`
  (tokens et coût de la délégation seule, hors l'appel de `delegate` et le reste du tour) et
  `test_local_sub_agent_has_tokens_but_no_cost_line` (tokens présents, aucune clé
  `cost_*`/`energy_*`/`gco2e_*` sur un sous-agent local).

## E2E à rejouer

Aucun scénario E2E ajouté ou modifié (changement backend + zone JS déjà couvert par les
tests Python de bout en bout, comme la story 6). À vérifier à l'oeil au prochain passage E2E
de l'atelier LLM cloud avec sous-agent activé : la ligne « Sous-agent » se déplie dans
Orchestration sous la délégation.

## Revue

En attente (second avis puis reviewer).
