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
| C8 | OpenAI, `gpt-6-luna` | erreur expliquée : « OpenAI refuse l'appel : le crédit du compte est épuisé. Ajoutez du crédit dans la console du fournisseur. Message du fournisseur : You have no credits remaining… » | même erreur | corps natif Responses (`{"model":"gpt-6-luna","instructions":…}`) | aucun coût compté | **non joué** : compte OpenAI sans crédit (action d'Anaël) |
| C9 | Langues | après « Vider la conversation » : interface en anglais puis en allemand, dépense au format de chaque langue (« $0.017 + $0.0044 », « 0,017 $ + 0,0044 $ ») | — | — | — | **OK** ; le changement de langue est refusé (409) tant que la conversation a des tours : verrou prévu (`language_locked`) |
| C10 | Plafond de séance | `settings.json` temporaire : `[finops] max_session_usd = 0.001` ; Haiku, quatre tours (total 0,001166 $), puis un cinquième | le cinquième est refusé : « Session spending cap reached: $0.0012 spent against a cap of $0.001. The call was not sent and costs nothing. To raise the cap, change [finops] max_session_usd in settings.json… » ; appels restés à 4, total inchangé | — | — | **OK** |

Coût de la recette : 0,0214 $ (fournisseurs) + 0,0012 $ (plafond) ≈ **0,023 $**. Fin de recette : aucun serveur sur 8420, aucun modèle chargé par Ollama (`ollama ps` vide), onglet fermé.

**GIF par fournisseur.** Huit GIF exportés par Claude in Chrome (local, Ollama, Groq, Mistral, Gemini, Haiku, Sonnet, Luna et plafond). Chrome les a laissés en `.crdownload` dans `Téléchargements` (confirmation de téléchargement en attente) ; une copie `.gif` de chacun est dans `Téléchargements\recette-2026-10-03\`. Leur en-tête est `GIF89a` mais leur dernier octet n'est pas le terminateur `0x3B` : à confirmer dans la liste des téléchargements de Chrome (« Conserver ») si les copies ne s'ouvrent pas. Les GIF ne sont pas versionnés (taille).

## 5. Bilan

- **Vert** : ruff, pytest (5 392 tests), tests `model` (12), E2E 1 074/1 075, recette navigateur de sept fournisseurs, langues et plafond.
- **Échec** : E2E `stream_resync`, antérieur au lot (échoue aussi sur `main`), noté dans `deferred-work.md`.
- **Non joué** : GPT-6 Luna (crédit OpenAI épuisé).
- **Aucun correctif** n'a été nécessaire dans les stories du lot.

## 6. Actions d'Anaël

1. Ajouter du crédit OpenAI, puis rejouer Luna (recette de la story 5, lignes L1 à L6 ; mesures 2, 3 et 5 de la story 4) : `deferred-work.md`.
2. Comparer les coûts de WaveStack aux consoles Anthropic (et OpenAI) : chiffres dans `resultats-fournisseurs-natifs-pc-2026-10.md`.
3. Trancher le critère 1 de Julia-1 (binaire `llama-server` portable) : `decision-model-candidates.md`.
4. Confirmer les GIF dans les téléchargements de Chrome.
