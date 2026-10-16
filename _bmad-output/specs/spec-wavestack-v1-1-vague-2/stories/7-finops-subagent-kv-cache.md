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

- **Règle de somme (story 9)** : les champs de `subagent_ended` sont un sous-ensemble du
  tour ; le total de `turn_ended` inclut déjà le sous-agent : ne jamais additionner les deux.
- Le débit n'est publié que si la première génération a lu au moins `READ_MIN_TOKENS` (64)
  tokens, comme `_note_read_rate` : sur un prompt presque entièrement repris, le débit mesuré
  sur une poignée de tokens est du surcoût fixe, pas un débit de lecture. La ligne garde alors
  les tokens repris, sans temps évité (`main.orch.kv.line_no_rate`).
- « Recalculés » = `prompt_tokens − cache_n` : les trois chiffres de la ligne viennent de la
  même (première) génération, jamais de la somme `evaluated_tokens` d'un appel relancé.

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
- `tests/test_reasoning_budget.py` : `test_the_kv_cache_line_is_the_first_generations_own`
  (relance après coupe : chiffres de la première génération ; rien si elle n'a rien dit).
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

Reviewer Opus, 16/10, après rebase sur `origin/main` (80e5567, sans conflit).

- MEDIUM, second avis 1 : corrigé. `kv_reuse` relu tant qu'il était `None`, donc pris sur la relance après une coupe quand la première génération n'avait rien dit ; lu désormais sur `len(evaluations) == 1` (test `test_the_kv_cache_line_is_the_first_generations_own`, rouge avant le correctif).
- MEDIUM, second avis 2 : corrigé. `cache_n` gardé même sans débit (`last_cache_reuse` → `(cache_n, None)`), ligne `line_no_rate` sans temps évité.
- MEDIUM, second avis 3 : corrigé (interface). Le backend portait bien le coût ; `subCostNode` masquait la ligne faute de tokens. Chaque partie s'affiche seule si elle est connue (`cost_tokens`) ; test backend du contrat (`..._billed_then_failed_keeps_its_cost_without_tokens`).
- MEDIUM, reviewer : corrigé. `subCostNode` masquait aussi un sous-agent local sans empreinte (tokens seuls), contraire à « seuls les tokens et l'empreinte (si connue) ».
- MEDIUM, second avis 4 : corrigé. Règle « ne pas additionner » dans `SubagentEndedPayload` et dans les Décisions.
- MEDIUM, second avis 5 : corrigé. « Recalculés » = `prompt_tokens − cache_n` (première génération) au lieu de `evaluated_tokens` (toutes les générations) ; test multi-génération ajouté.
- LOW, second avis (débit minuscule) : corrigé. Débit publié seulement au-delà de `READ_MIN_TOKENS` lus, sinon pas de temps évité.
- LOW, second avis (`_turn_call_tokens` hors tour) : corrigé. Ajout seulement quand `current().turn_id` existe, comme `_count_impact` (les ateliers n'ont pas de tour).
- LOW, second avis (`last_cache_reuse` dans le `Protocol`) : rejeté. Même convention que `dimensions` (déclarée dans le Protocol, lue par `getattr`) ; type aligné sur `float | None`.
- Parité i18n fr/en/de vérifiée (`main.orch.kv.*`, `main.orch.sub.cost_*`), aucune citation interne.
- Reporté : la ligne « Mémoire de contexte » n'a été vue sur aucun vrai llama-server (le faux serveur E2E n'envoie pas `cache_n`). À vérifier à l'œil : deux tours de suite sur llama-server, la ligne du second montre `cache_n` ≈ le préfixe commun et un temps évité plausible.
