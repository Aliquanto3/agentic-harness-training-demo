# Résultats de la batterie complète du lot du 2026-10-03

- Lot : fournisseurs natifs, stories 1 à 5 (`7f40fc1`, `69caa80`, `4dc5f23`, `c396d6a`, `b80097f`) ; V2, stories 8 et 9 (`598e44f`, `7a5a4c9`), et l'ajout de la story 9 (`9357d50`).
- Branche : `feat/stories-restantes-2026-10`, base `e09cfa6` (fusion de la PR #19). Code testé : `7a5a4c9`.
- Poste : PC cible (HP EliteBook x360 1030 G8, i5-1145G7, 15,7 Go, Windows 11 Entreprise, sans droits admin, proxy Zscaler).
- Date : 2026-10-03, de 18 h 20 à 19 h 20 (heure de Paris), sans Anaël devant le PC (points d'arrêt levés par lui).
- Règles suivies : une suite à la fois, pytest en quarts, E2E par tranches `--only`, dossier `pytest-of-anael.yahi` vidé après chaque suite, captures E2E remises (`git checkout`, `git clean`) après chaque tranche.

## 1. Lint

| Commande | Résultat |
|---|---|
| `uv run ruff check .` | **OK** : « All checks passed! » |
| `uv run ruff format --check .` | **OK** : « 211 files already formatted » |

## 2. pytest

| Suite | Résultat | Durée |
|---|---|---|
| Quart 1 (17 fichiers) | **3 755 passés** | 5 min 55 |
| Quart 2 (17 fichiers) | **693 passés**, 6 désélectionnés | 5 min 37 |
| Quart 3 (17 fichiers) | **398 passés**, 3 sautés, 6 désélectionnés | 2 min 40 |
| Quart 4 (14 fichiers) | **546 passés** | 2 min 54 |
| `-m model`, `WAVESTACK_TEST_GGUF` = Qwen3.5-2B-Q4_K_M | **10 passés**, 2 sautés | 1 min 21 |
| Les 2 sautés (`test_rag.py:546`, `test_rag_rerank.py:828`), rejoués avec `WAVESTACK_TEST_MODELS_DIR` | **2 passés** | 9 s |

Total : 5 392 tests passés, 0 échec ; les 12 tests `model` passent (les deux RAG demandent `WAVESTACK_TEST_MODELS_DIR` en plus de `WAVESTACK_TEST_GGUF`).

## 3. E2E (faux fournisseur, réseau coupé), onze tranches `--only`

| Tranche | Scénarios | Vérifications |
|---|---|---|
| T1 | programme bare_llm short_memory system_prompt native_tools | 91 OK, 0 échec |
| T2 | malformed provider_errors markdown diagnostic_wait network_tools | 69 OK, 0 échec |
| T3 | disciplines themes linked_view panes h5 | 152 OK, 0 échec |
| T4 | mcp_full mcp_lazy skills caveman hooks | 58 OK, 0 échec |
| T5 | subagent data_flows soc iam sovereignty | 103 OK, 0 échec |
| T6 | forced_native global_memory rag rag_rerank rag_lab | 140 OK, 0 échec |
| T7 | mcp_lab mcp_lab_page compression busy_and_stop reload_and_reset | 95 OK, 0 échec |
| T8 | language ui_language content_language annex_language backend_language | 86 OK, 0 échec |
| T9 | stream_resync stream_lost model_switch reasoning_locked | 58 OK, **1 échec** |
| T10 | local_server gemini_shape priced_estimate model_catalog | 136 OK, 0 échec |
| T11 | context_window llm_screen llm_live relaunch | 86 OK, 0 échec |

Total : **1 074 vérifications réussies, 1 en échec**.

**Échec E1 : `stream_resync`.** Sortie : `FAIL [stream_resync] état et flux d'instances différentes : un seul rechargement — 1 navigation(s)` (attendu : 2 navigations, la page doit se recharger une fois quand `/api/state` et le flux nomment des instances différentes). Reproduit deux fois seul. **Reproduit aussi sur `main` (`e09cfa6`)** dans un worktree jetable (même sortie) : défaut antérieur au lot, pas une régression des stories. Il passait à la batterie du 2026-10-01. Noté dans `deferred-work.md` pour un diagnostic à part (piste : la route Playwright qui réécrit `instance_id`, suivie d'un `net::ERR_FAILED` en console).

**Diagnostic et correctif (2026-10-03 au soir, `9795197`).** Défaut du test, pas du produit : `site-nav.js` (story 2, 2026-10-01) lit aussi `/api/state` au chargement, et la route Playwright `times=1` était consommée par lui ; `app.js` recevait la vraie instance et ne rechargeait pas (le cas « sans /api/state » était faussé de la même façon ; l'`ERR_FAILED` vient de ce cas, voulu). Route sans `times`, `fallback` après le rechargement, `unroute` après chaque cas ; T9 : 59 réussies, 0 échec. Le bilan ci-dessous est celui du passage d'origine.

**Constats non bloquants de l'E2E.**
- T8 : avertissements de console `i18n : clé absente du catalogue : main.gauge.segment` (et `free`, `threshold`, `figures`), alors que les clés existent dans `content/ui.yaml` : appel de `t()` avant le chargement du catalogue lors d'un changement de langue (code de Langues 2/5, antérieur au lot).
- T3, T7, T9, T10 : `Failed to load resource` (409, `ERR_FAILED`) en console, attendus par ces scénarios (refus volontaires, flux coupé).

## 4. Recette dans le navigateur (Claude in Chrome)

WaveStack lancé sur 127.0.0.1:8420 (port vérifié libre avant), clés Anthropic et OpenAI lues dans l'environnement utilisateur et passées au seul serveur, `settings.json` et `memory.json` sauvegardés avant et restaurés à l'identique après (empreintes égales). Pilotage : les intentions de l'API locale depuis la page (`fetch` même origine), lecture de l'écran par captures et par le DOM. Langue de la séance : `fr`. Scénario `native_tools`. Par fournisseur : un tour Outils (« Quelle heure est-il ? », brique Raisonnement éteinte), puis un tour Raisonnement (« Un train part à 14 h 47 et roule pendant 3 h 03… », brique allumée).

| # | Fournisseur | Outils | Raisonnement | Contexte LLM | Coût, empreinte | Verdict |
|---|---|---|---|---|---|---|
| C1 | Local, Qwen3.5-2B-Q4_K_M (fichier) | `get_datetime`, réponse juste, 13 s | 2 blocs de raisonnement visibles ; appelle `calculator("14:47 + 3:03")`, erreur réinjectée par le harnais, réponse juste « 17 h 50 » ; 47,7 s | prompt rendu, segments par brique | empreinte locale estimée (0,28 Wh, 0,012 g CO₂e) | **OK** |
| C2 | Ollama, `qwen3.5:2b` | `get_datetime`, réponse juste, 37 s | 3 blocs de raisonnement, `calculator`, « 17 h 50 » ; 28 s | idem | empreinte estimée | **OK** |
| C3 | Groq, `openai/gpt-oss-120b` | `get_datetime`, réponse juste, 3 s | raisonnement visible (toujours actif), « 17 h 50 » | corps JSON Chat Completions (`{"model":"openai/gpt-oss-120b","messages":…}`) | 0,00028 $ pour 3 appels | **OK** |
| C4 | Mistral, `mistral-small-latest` | `get_datetime`, réponse juste | 2 blocs de raisonnement, `calculator`, « 17h50 » | corps JSON Chat Completions | coût affiché par appel | **OK** |
| C5 | Gemini, `gemini-3.5-flash-lite` | `get_datetime`, réponse juste | `calculator` (3 appels), « 17 h 50 » ; **aucun bloc de raisonnement affiché** | corps JSON Chat Completions | coût affiché | **OK, constat** : comportement connu de Gemini en streaming (résumé `<thought>` rendu environ une fois sur trois, mesuré le 2026-10-01), pas un défaut du lot |
| C6 | Anthropic, `claude-haiku-4-5` | `get_datetime`, réponse juste | 1 bloc de raisonnement visible, `calculator`, « 17h50 » | corps natif Messages : `{"model":"claude-haiku-4-5","system":…}`, le bloc `thinking` renvoyé avec sa `signature`, `thinking: {type: "enabled", budget_tokens: 1024, block_binding: {prefix_mismatch_behavior: "drop_block"}}` | entrée 0,001652 $ + sortie 0,00026 $ sur l'appel final ; empreinte EcoLogits | **OK** |
| C7 | Anthropic, `claude-sonnet-5` | `get_datetime`, réponse juste | raisonnement résumé visible, `calculator`, « 17 h 50 » | corps natif : `thinking` `adaptive`, `display: "summarized"` | coût et empreinte affichés | **OK** |
| C8 | OpenAI, `gpt-6-luna` | 1er passage : erreur expliquée (« le crédit du compte est épuisé… ») ; **après la recharge d'Anaël** : `get_datetime`, réponse juste ; `calculator`, « 7 006 652 » | après la recharge : bloc de raisonnement visible, « 17 h 50 » | corps natif Responses : `"reasoning":{"effort":"low","summary":"auto"}`, `"store":false`, `"include":["reasoning.encrypted_content"]`, outils `"strict": false`, item `reasoning` renvoyé avec son `encrypted_content` | 0,00036 $ pour 6 appels | **OK** (rejoué le 2026-10-03 au soir, section 7) |
| C9 | Langues | après « Vider la conversation » : interface en anglais puis en allemand, dépense au format de chaque langue (« $0.017 + $0.0044 », « 0,017 $ + 0,0044 $ ») | — | — | — | **OK** ; le changement de langue est refusé (409) tant que la conversation a des tours : verrou prévu (`language_locked`) |
| C10 | Plafond de séance | `settings.json` temporaire : `[finops] max_session_usd = 0.001` ; Haiku, quatre tours (total 0,001166 $), puis un cinquième | le cinquième est refusé : « Session spending cap reached: $0.0012 spent against a cap of $0.001. The call was not sent and costs nothing. To raise the cap, change [finops] max_session_usd in settings.json… » ; appels restés à 4, total inchangé | — | — | **OK** |

Coût de la recette : 0,0214 $ (fournisseurs) + 0,0012 $ (plafond) ≈ **0,023 $**. Fin de recette : aucun serveur sur 8420, aucun modèle chargé par Ollama (`ollama ps` vide), onglet fermé.

**GIF par fournisseur.** Huit GIF exportés par Claude in Chrome (local, Ollama, Groq, Mistral, Gemini, Haiku, Sonnet, Luna et plafond). Chrome les a laissés en `.crdownload` dans `Téléchargements` (confirmation de téléchargement en attente) ; une copie `.gif` de chacun est dans `Téléchargements\recette-2026-10-03\`. Leur en-tête est `GIF89a` mais leur dernier octet n'est pas le terminateur `0x3B` : à confirmer dans la liste des téléchargements de Chrome (« Conserver ») si les copies ne s'ouvrent pas. Les GIF ne sont pas versionnés (taille).

## 5. Bilan

- **Vert** : ruff, pytest (5 392 tests), tests `model` (12), E2E 1 074/1 075, recette navigateur de sept fournisseurs, langues et plafond.
- **Échec** : E2E `stream_resync`, antérieur au lot (échoue aussi sur `main`), noté dans `deferred-work.md`.
- **Luna** : non joué au premier passage (crédit OpenAI épuisé), **OK** après la recharge (section 7).
- **Aucun correctif** n'a été nécessaire dans les stories du lot.

## 6. Actions d'Anaël

1. ~~Ajouter du crédit OpenAI~~ : **fait** le 2026-10-03 au soir ; rejouer Luna : voir la section 7.
2. **Console Anthropic : coût comparé** le 2026-10-03 au soir. Le tableau de bord d'Anthropic affiche **0,16 $** pour le mois. Les estimations de WaveStack pour cette clé, toutes du 2026-10-03, font **≈ 0,159 $** : mesures de la story 3 (0,0258 $), recette de la story 5 (0,1123 $), recette Chrome Haiku et Sonnet (≈ 0,0194 $, soit le total de la séance moins les 0,0021 $ de Groq, Mistral et Gemini), test du plafond (0,0012 $). Écart sous l'arrondi au centime du tableau de bord (au plus ≈ 3 %), donc dans les 10 % du Success signal de SPEC.md, en supposant que la clé n'a servi qu'à WaveStack ce mois-ci. **OK.** **Console OpenAI : comparée le 2026-10-03 au soir, voir la section 8.**
3. ~~Trancher le critère 1 de Julia-1~~ : **accepté** par Anaël le 2026-10-03 (binaire `llama-server` portable admis comme prérequis externe, comme Ollama) ; reporté dans `decision-model-candidates.md`.
4. ~~Confirmer les GIF~~ : **fait**, Anaël les a téléchargés.

## 7. Reprise de GPT-6 Luna après la recharge du crédit OpenAI (2026-10-03 au soir)

- **Mesures réelles de la story 4** (`mesures-openai-2026-10.md`, 39 appels, ≈ 0,0024 $) : l'effort n'impose pas de raisonnement (0 token sur une tâche d'outil simple, 71 à 96 sur une énigme, résumé visible) ; items `reasoning` renvoyés avec leur `id` `rs_` sous `store: false` acceptés, devant un appel, un message ou deux appels parallèles, les items `function_call` et `message` reconstruits sans `id` aussi ; résumé visible sans vérification d'organisation ; tours Outils et Raisonnement réels réussis par `AppSession`. Aucun défaut de code.
- **Recette de la story 5, lignes L1 à L8** (`resultats-fournisseurs-natifs-pc-2026-10.md`) : « Tester », Raisonnement, Outils (raisonnement éteint et allumé), MCP (`load_tool_doc` puis `local__define_term`), Sous-agent : **toutes OK** ; renvoi de l'item chiffré vérifié d'un tour à l'autre ; 20 appels, 0,001711 $ ; empreinte EcoLogits sur chaque appel ; proxy Zscaler traversé. Constat L4 : Luna ne raisonne pas sur une simple multiplication (comme Sonnet en S4).
- **Recette Chrome** (ligne C8) : OK, GIF `recette-2026-10-03-openai-luna.gif`.
- **Success signal de SPEC.md** : atteint pour les trois modèles (Haiku, Sonnet, Luna) ; coût Anthropic comparé à la console (OK). Reste la console OpenAI : 20 appels de 17:37:16 à 17:38:59 UTC, 12 289 / 965 tokens, 0,001711 $ (plus ≈ 0,0024 $ de mesures et 0,00036 $ de recette Chrome) ; au centime près, seuls les comptes de tokens peuvent montrer un écart de 10 %.
- **Précision sur le masquage** : les signatures d'Anthropic et l'`encrypted_content` d'OpenAI apparaissent en clair dans `model_call_ended.raw_output` et dans `outbound_request.body`. « Masqué » désigne, dans le code comme pour la signature de Gemini, le masquage de la clé d'API (AD-15) ; le corps tracé doit rester égal au corps envoyé (CAP-1). Ces jetons opaques du fournisseur ne sont pas des secrets du poste.

## 8. Console OpenAI : écart avec les estimations de WaveStack (2026-10-03 au soir)

Relevé par Claude in Chrome sur `platform.openai.com/usage` (organisation Wavestone, filtre « All projects », « All API keys », 7 derniers jours ; le filtre par défaut sur le projet « ProjetCommande » n'affiche rien : la clé de WaveStack n'en dépend pas). Seul le 2026-10-03 porte de l'usage.

| Mesure | Console OpenAI | WaveStack (estimation) | Écart |
|---|---|---|---|
| Dépense du jour | **0,00 $** (arrondi au centime ; « October spend » 0,00 $ / 100 $) | ≈ **0,0045 $** (0,001711 recette story 5 + 0,0024 mesures story 4 + 0,00036 recette Chrome) | non mesurable : l'estimation est sous le centime, donc sous la résolution de la console |
| Requêtes (Responses) | **64** | **65** (39 mesures + 20 recette + 6 Chrome) | -1 (≈ 1,5 %) |
| Tokens d'entrée | **27 889** | 12 289 pour la seule recette (20 appels) ; les totaux des mesures (39 appels) et de la recette Chrome (6 appels) ne sont pas consignés | non vérifiable en l'état : les 15 600 tokens restants pour 44 à 45 requêtes (≈ 350 par requête) restent plausibles |
| Tokens de sortie | non affichés par la carte « Responses and Chat Completions » | 965 pour la recette | non comparable |

Lecture : le coût ne peut pas être comparé au centime près, comme prévu (section 7) ; le décompte des requêtes concorde à une requête près, et les 7 requêtes refusées pour crédit épuisé avant la recharge n'y figurent pas (sinon la console en compterait 72). L'écart d'une requête n'a pas été expliqué (retard d'agrégation de la console ou appel compté deux fois côté WaveStack, non tranché). Le Success signal de SPEC.md (écart de coût sous 10 %) est donc **non démontrable pour OpenAI** à ces montants ; il reste démontré pour Anthropic (0,16 $ contre ≈ 0,159 $). Pour une vraie comparaison OpenAI, il faudrait un lot d'au moins 1 $ ou la page des coûts (granularité plus fine) : à décider par Anaël, sans urgence.
