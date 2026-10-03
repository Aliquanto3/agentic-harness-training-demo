# Résultats de la recette PC des fournisseurs natifs (story 5/5)

- Story : [5-recette-sur-le-pc-cible.md](../specs/spec-fournisseurs-natifs/stories/5-recette-sur-le-pc-cible.md)
- Poste : HP EliteBook x360 1030 G8, Intel Core i5-1145G7, 15,7 Go de RAM, Windows 11 Entreprise (build 26200), session sans droits admin. Proxy du poste : Zscaler (`ZSATunnel`, à l'écoute sur 127.0.0.1:9000), déclaré par `HTTPS_PROXY=http://127.0.0.1:9000` dans l'environnement utilisateur ; aucun proxy WinINET (`ProxyEnable = 0`).
- Date : 2026-10-03, de 15:08 à 15:11 UTC (17:08 à 17:11, heure de Paris).
- Code : branche `feat/stories-restantes-2026-10`, base `c396d6a` (stories 1 à 4 des fournisseurs natifs).
- Modèles : `claude_haiku` (`claude-haiku-4-5`), `claude_sonnet` (`claude-sonnet-5`), `openai_luna` (`gpt-6-luna`), réglages de `wavestack.toml` sans surcharge. Plafond de séance : 5 $ (préréglage).
- Méthode :
  - Serveur `wavestack` lancé dans sa propre console (masquée), piloté par l'API (`/api/intentions/*`) et le flux SSE (`/api/stream`) par un script jetable hors du dépôt. Chaque relevé vient des événements du journal (`diagnostic_check`, `model_call_ended`, `model_delta`, `outbound_request`, `outbound_response`, `tool_started`, `subagent_ended`, `consumption_updated`, `turn_ended`).
  - Les connexions TCP du serveur ont été échantillonnées par `netstat -ano` toutes les 0,4 s.
  - Langue de la session : `fr`. Les clés `ANTHROPIC_API_KEY` et `OPENAI_API_KEY` ont été lues dans l'environnement utilisateur (registre) et passées au seul processus serveur ; `api_keys.json` n'a pas été modifié.
  - `settings.json` et `memory.json` ont été sauvegardés avant, puis restaurés après chaque lancement.
  - Par modèle : « Tester », puis le scénario `reasoning` (prompt 1), `native_tools` prompt 1 (brique Raisonnement éteinte) et prompt 2 (brique Raisonnement allumée), `mcp_lazy` prompt 1 et `subagent` prompt 1.
- Deux lancements :
  - Le premier a joué Haiku, puis le « Tester » et le tour Raisonnement de Sonnet. Le script s'est alors arrêté sur une erreur d'encodage de sa propre console, sans lien avec WaveStack : le serveur a été arrêté proprement et les fichiers ont été restaurés.
  - Le second a rejoué Sonnet depuis « Tester », puis Luna.
  - Le total de la séance repart à zéro à chaque lancement : les deux totaux s'additionnent.

## Tableau

| # | Modèle | Geste | Attendu | Observé | Verdict |
|---|---|---|---|---|---|
| H1 | Haiku | « Tester » | réponse et appel d'outil | `diagnostic_check{cloud_test: ok}` : « Test réussi : Anthropic répond, 113 tokens/s. Appel d'outil reçu : get_datetime. » ; 2 appels, 0,001584 $ | **OK** |
| H2 | Haiku | `reasoning`, prompt 1 (train de 14 h 47) | `model_delta` au canal `reasoning`, réponse, coût | 20 `model_delta{reasoning}` (322 caractères de réflexion), puis réponse « 17 h 50 » (juste) ; 82 / 327 tokens, 0,001717 $, tour de 3,3 s | **OK** |
| H3 | Haiku | `native_tools`, prompt 1, brique Raisonnement éteinte | appel d'outil natif, résultat, réponse | `get_datetime` (source `native`) → `samedi 2026-10-03T17:08:54+02:00` → « Il est actuellement 17h08… » ; 2 appels, 0,002786 $, 2,0 s | **OK** |
| H4 | Haiku | `native_tools`, prompt 2, brique Raisonnement allumée | appel d'outil, réflexion visible, bloc `thinking` renvoyé signé | 1er appel : réflexion (3 deltas, 111 caractères) puis `calculator {"expression": "1234 * 5678"}` ; 2e appel : le corps (`outbound_request`) renvoie 1 bloc `thinking` avec sa `signature`, accepté (aucun `outbound_response`) ; réponse « 7 006 652 » ; 0,003360 $, 2,0 s | **OK** |
| H5 | Haiku | `mcp_lazy`, prompt 1 | `load_tool_doc` puis `local__define_term` | `load_tool_doc {"tool": "local__define_term"}` → `local__define_term {"term": "MCP"}` → réponse fondée sur la définition ; 3 appels, 0,007212 $, 4,7 s | **OK** |
| H6 | Haiku | `subagent`, prompt 1 | délégation, résumé réinjecté | `delegate` → sous-agent : `read_file guide_harnais.md`, résumé en cinq points (394 tokens) → réponse ; `subagent_ended` : `completed`, 2 appels, 1 795 tokens gardés chez le sous-agent, 312 réinjectés, 1 483 économisés ; 4 appels, 0,013318 $, 10,4 s | **OK** |
| H7 | Haiku | coût | coût par appel et total, fidèles aux prix déclarés | 14 appels, tous `usage_source = api`, `cost_source = api` ; 20 837 tokens d'entrée, 1 828 de sortie : 0,029977 $ (= 20 837 × 1 $ + 1 828 × 5 $ par million) | **OK** ; comparaison à la console : action d'Anaël |
| H8 | Haiku | empreinte | `impact_method = ecologits`, fourchettes | les 14 appels portent `ecologits` et une fourchette (ex. tour Raisonnement : 0,0188 à 0,0500 Wh, 0,0078 à 0,0203 g CO₂e) ; note : « architecture non publiée, précision moindre » ; total Haiku : 0,046 à 0,118 g CO₂e | **OK** |
| S1 | Sonnet | « Tester » | réponse et appel d'outil | « Test réussi : Anthropic répond, 278 tokens/s. Appel d'outil reçu : get_datetime. » (169 tokens/s au premier lancement) ; 2 appels, 0,002492 $ | **OK** |
| S2 | Sonnet | `reasoning`, prompt 1 | réflexion visible | 2 `model_delta{reasoning}` (99 caractères de réflexion résumée ; 111 au premier lancement), réponse « 17 h 50 » ; 64 / 258 tokens, 0,002708 $, 2,8 s | **OK** |
| S3 | Sonnet | `native_tools`, prompt 1, brique Raisonnement éteinte | appel d'outil natif | `get_datetime` → « Il est actuellement 17h10, ce samedi 3 octobre 2026. » ; 2 appels, 0,005236 $, 2,3 s | **OK** |
| S4 | Sonnet | `native_tools`, prompt 2, brique Raisonnement allumée | appel d'outil, réflexion | le corps envoyé porte `thinking: {type: "adaptive", display: "summarized", block_binding: {prefix_mismatch_behavior: "drop_block"}}` ; Sonnet ne réfléchit pas (aucun bloc `thinking`), appelle `calculator {"expression": "1234*5678"}`, réponse « 7 006 652 » ; 0,005792 $, 2,0 s | **constat** : en réflexion adaptative, le modèle décide de ne pas réfléchir sur une multiplication ; la réflexion est visible au tour Raisonnement (S2) |
| S5 | Sonnet | `mcp_lazy`, prompt 1 | `load_tool_doc` puis `local__define_term` | même enchaînement que H5 ; 3 appels, 0,014364 $, 3,9 s | **OK** |
| S6 | Sonnet | `subagent`, prompt 1 | délégation, résumé réinjecté | 1re délégation : le résumé du sous-agent est coupé à la réserve de sortie de 512 tokens (`stop_reason = length`) ; l'outil rend `limit` : « La délégation au sous-agent a échoué : sa sortie a été coupée à 512 tokens… ». L'agent principal redélègue de lui-même avec une consigne plus courte (« cinq points, une phrase de 15 mots au plus ») → `completed`, 179 tokens. `subagent_ended` : 1 795 tokens gardés, 111 réinjectés, 1 684 économisés ; 7 appels, 0,046214 $, 16,7 s | **OK**, avec un **constat** : la réserve de 512 tokens du sous-agent est courte pour Sonnet (noté dans `deferred-work.md`) |
| S7 | Sonnet | coût | idem H7 | 20 appels (3 au premier lancement, 17 au second), tous `api` ; 29 228 tokens d'entrée, 2 382 de sortie : 0,082276 $ (= 29 228 × 2 $ + 2 382 × 10 $ par million) | **OK** ; comparaison à la console : action d'Anaël |
| S8 | Sonnet | empreinte | `ecologits`, fourchettes | les 20 appels portent `ecologits` et une fourchette (tour Raisonnement : 0,288 à 0,459 Wh, 0,118 à 0,184 g CO₂e, environ 15 fois Haiku) ; total Sonnet : 1,15 à 1,76 g CO₂e | **OK** |
| L1 | Luna | « Tester » | savoir si le blocage du compte dure | `diagnostic_check{cloud_test: fail}` : « Test en échec : OpenAI refuse l'appel : le crédit du compte est épuisé. Ajoutez du crédit dans la console du fournisseur. Message du fournisseur : You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/. » ; réponse HTTP sous 400 (aucun `outbound_response`), puis l'erreur dans le flux ; `model_call_ended{stop_reason: error}`, aucun coût compté | **non joué** (compte OpenAI sans crédit) ; message de WaveStack clair et juste |
| L2 à L6 | Luna | Raisonnement, Outils (prompts 1 et 2), MCP, Sous-agent | — | non lancés : le blocage dure | **non joué** (même raison) |
| P1 | — | proxy, `api.anthropic.com` | 200 ou refus du proxy relevé | les 34 requêtes vers Anthropic, « Tester » compris, aboutissent, aucun `outbound_response`. Pendant tout le lancement, les sockets du serveur hors boucle locale ne vont qu'à **127.0.0.1:9000** (Zscaler) : 90 et 91 échantillons, aucune connexion directe vers Internet | **OK** : le proxy du poste laisse passer `api.anthropic.com` |
| P2 | — | proxy, `api.openai.com` | idem | la requête traverse le proxy (même échantillonnage) et la réponse vient d'OpenAI (son message de crédit épuisé), pas du proxy | **OK** : le proxy laisse passer `api.openai.com` |
| C | — | coût total de la recette | moins de 2 $, sous le plafond de 5 $ | premier lancement : 0,035447 $ (17 appels, 0,0305 €) ; second : 0,076806 $ (17 appels, 0,0661 €) ; **total : 0,112253 $**. Empreinte : 0,51 à 0,91 Wh puis 2,37 à 3,73 Wh, soit 2,87 à 4,64 Wh et 1,20 à 1,88 g CO₂e | **OK** |

Le serveur s'arrête par Ctrl+Break dans sa console en 2,22 s puis en 2,52 s, flux SSE ouvert, dont le délai de grâce de 2 s.

## Correctifs appliqués

Aucun : aucune anomalie des stories 1 à 4 n'a été trouvée. Le constat S6 relève du sous-agent (story 19), pas des fournisseurs natifs : il est noté dans `deferred-work.md`.

## Actions d'Anaël

1. **Console Anthropic : comparer le coût** (SPEC.md demande un écart d'au plus 10 %).
   - Page Usage ou Cost, journée du 2026-10-03, par modèle. Les appels de la recette vont de 15:08:44 à 15:10:42 UTC (17:08 à 17:11, heure de Paris).
   - Chiffres de WaveStack à comparer :

     | Modèle | Requêtes | Tokens d'entrée | Tokens de sortie | Coût WaveStack |
     |---|---|---|---|---|
     | `claude-haiku-4-5` | 14 | 20 837 | 1 828 | 0,029977 $ |
     | `claude-sonnet-5` | 20 | 29 228 | 2 382 | 0,082276 $ |
     | Total | 34 | 50 065 | 4 210 | 0,112253 $ |

   - La même journée compte aussi les mesures de la story 3 (10 requêtes facturées, 0,0258 $ ; `mesures-anthropic-2026-10.md`) et tout autre usage de la clé. Si la console ne filtre pas à la minute, comparer le total du jour à 0,1381 $ (0,112253 + 0,0258), plus les autres usages éventuels.
2. **OpenAI : ajouter du crédit**, puis rejouer les lignes L1 à L6. La comparaison avec la console d'OpenAI se fera alors de la même façon. Il faudra aussi rejouer les mesures 2, 3 et 5 de `mesures-openai-2026-10.md` (déjà dans `deferred-work.md`). Si le canal Raisonnement reste vide alors que `reasoning_tokens` est positif, vérifier l'organisation dans la console OpenAI.

## Remarques de méthode

- `netstat` affiche ses en-têtes dans la page de code OEM : sans `encoding="oem"`, la lecture de sa sortie échoue (`UnicodeDecodeError`). Ses états (`LISTENING`, `ESTABLISHED`) restent en anglais sur ce poste francisé.
- Une console Windows en cp1252 ne sait pas écrire certains caractères des réponses des modèles (émojis) : il faut lancer le script avec `PYTHONIOENCODING=utf-8`. C'est la cause de l'arrêt du premier lancement.
- Les en-têtes `anthropic-version` et `anthropic-beta` sont masqués dans `outbound_request`, comme tout en-tête hors `PUBLIC_HEADERS` (story 1, AD-5 amendé) : le journal ne permet pas de voir l'en-tête `thinking-binding-controls-2026-08-01`. Le corps, lui, montre `block_binding`, qui n'est accepté qu'avec cet en-tête.
- Le « Tester » de chaque modèle répond « 1er janvier 2026 à 9 h » : c'est le résultat fixe de l'outil de test (`content/`), pas l'heure réelle.

## Vérification

- `Get-NetTCPConnection -LocalPort 8420` : rien à l'écoute à la fin (seules des connexions `TIME_WAIT`).
- `settings.json` et `memory.json` : identiques octet pour octet à la sauvegarde d'avant la recette (`cmp`). `api_keys.json` n'a pas changé (date de modification : 2026-10-01).
- `git grep -nE "sk-ant-|sk-proj-"` : aucun résultat. Les journaux de la recette, hors du dépôt, n'en contiennent pas non plus.
