# Résultats de la recette PC des fournisseurs natifs (story 5/5)

- Story : [5-recette-sur-le-pc-cible.md](../specs/spec-fournisseurs-natifs/stories/5-recette-sur-le-pc-cible.md)
- Poste : HP EliteBook x360 1030 G8, Intel Core i5-1145G7, 15,7 Go de RAM, Windows 11 Entreprise (build 26200), session sans droits admin. Proxy du poste : Zscaler (`ZSATunnel`, à l'écoute sur 127.0.0.1:9000), déclaré par `HTTPS_PROXY=http://127.0.0.1:9000` dans l'environnement utilisateur ; aucun proxy WinINET (`ProxyEnable = 0`).
- Date : 2026-10-03 : Anthropic de 15:08 à 15:11 UTC (17:08 à 17:11, heure de Paris) ; OpenAI de 17:37 à 17:39 UTC (19:37 à 19:39), après la recharge du crédit par Anaël.
- Code : branche `feat/stories-restantes-2026-10`, base `c396d6a` (stories 1 à 4 des fournisseurs natifs).
- Modèles : `claude_haiku` (`claude-haiku-4-5`), `claude_sonnet` (`claude-sonnet-5`), `openai_luna` (`gpt-6-luna`), réglages de `wavestack.toml` sans surcharge. Plafond de séance : 5 $ (préréglage).
- Méthode :
  - Serveur `wavestack` lancé dans sa propre console (masquée), piloté par l'API (`/api/intentions/*`) et le flux SSE (`/api/stream`) par un script jetable hors du dépôt. Chaque relevé vient des événements du journal (`diagnostic_check`, `model_call_ended`, `model_delta`, `outbound_request`, `outbound_response`, `tool_started`, `subagent_ended`, `consumption_updated`, `turn_ended`).
  - Les connexions TCP du serveur ont été échantillonnées par `netstat -ano` toutes les 0,4 s.
  - Langue de la session : `fr`. Les clés `ANTHROPIC_API_KEY` et `OPENAI_API_KEY` ont été lues dans l'environnement utilisateur (registre) et passées au seul processus serveur ; `api_keys.json` n'a pas été modifié.
  - `settings.json` et `memory.json` ont été sauvegardés avant, puis restaurés après chaque lancement.
  - Par modèle : « Tester », puis le scénario `reasoning` (prompt 1), `native_tools` prompt 1 (brique Raisonnement éteinte) et prompt 2 (brique Raisonnement allumée), `mcp_lazy` prompt 1 et `subagent` prompt 1.
- Quatre lancements :
  - Le premier a joué Haiku, puis le « Tester » et le tour Raisonnement de Sonnet. Le script s'est alors arrêté sur une erreur d'encodage de sa propre console, sans lien avec WaveStack : le serveur a été arrêté proprement et les fichiers ont été restaurés.
  - Le deuxième a rejoué Sonnet depuis « Tester », puis le « Tester » de Luna (crédit encore épuisé).
  - Le troisième, crédit OpenAI rechargé, a joué toutes les lignes de Luna.
  - Le quatrième a ajouté deux tours Outils de Luna avec la brique Raisonnement (ligne L4b) : au prompt 2 de `native_tools`, Luna n'a pas raisonné, et aucun item `reasoning` n'était à renvoyer.
  - Le total de la séance repart à zéro à chaque lancement : les totaux s'additionnent.

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
| L1 | Luna | « Tester » | réponse et appel d'outil | `diagnostic_check{cloud_test: ok}` : « Test réussi : OpenAI répond, 179 tokens/s. Appel d'outil reçu : get_datetime. » ; 2 appels, 0,000032 $. (Avant la recharge, à 15:10 UTC : « Test en échec : OpenAI refuse l'appel : le crédit du compte est épuisé… », sans coût compté.) | **OK** |
| L2 | Luna | `reasoning`, prompt 1 | résumé du raisonnement au canal `reasoning` | corps : `reasoning: {effort: "low", summary: "auto"}`, `store: false`, `include: ["reasoning.encrypted_content"]` ; 19 `model_delta{reasoning}` (430 caractères de résumé), réponse « 17 h 50 » (juste) ; 41 / 66 tokens, 0,000037 $, 2,7 s ; 0,0109 à 0,0116 Wh, 0,0051 à 0,0053 g CO₂e | **OK** : le résumé s'affiche, l'organisation n'a pas besoin d'être vérifiée |
| L3 | Luna | `native_tools`, prompt 1, brique Raisonnement éteinte | appel d'outil natif | corps : `reasoning: {effort: "none"}` ; `get_datetime` (source `native`) → « Il est 19 h 37, samedi 3 octobre 2026. » ; 2 appels, 0,000097 $, 2,1 s ; 0,0067 à 0,0070 Wh, 0,0032 à 0,0033 g CO₂e | **OK** |
| L4 | Luna | `native_tools`, prompt 2, brique Raisonnement allumée | appel d'outil, raisonnement, item `reasoning` renvoyé avec son `encrypted_content` | corps : effort « low » ; `calculator {"expression": "1234*5678"}` → « 1 234 × 5 678 = **7 006 652**. » ; Luna ne raisonne pas sur ce tour (aucun item `reasoning`, aucun résumé) : rien à renvoyer au second appel ; 2 appels, 0,000117 $, 3,0 s ; 0,0091 à 0,0095 Wh, 0,0045 à 0,0046 g CO₂e | **constat** : à l'effort « low », Luna ne raisonne pas sur une multiplication (comme Sonnet en S4) ; le renvoi est vérifié en L4b |
| L4b | Luna | `native_tools`, brique Raisonnement allumée : « Un train part maintenant et roule 2 h 38, puis subit 25 minutes de retard… appelle d'abord get_datetime… », puis « … calcule avec l'outil calculator… multiplie ce nombre par 37 » | item `reasoning` renvoyé avec son `encrypted_content`, accepté | tour 1 : `get_datetime`, `calculator` (deux fois), puis réponse « 22 h 41 » (juste : 19 h 38 + 183 min) ; Luna ne raisonne qu'au dernier appel (13 deltas, 344 caractères de résumé) ; 4 appels, 0,000261 $. Tour 2 : les deux corps renvoient cet item tel quel, avec `id` (`rs_…`), `encrypted_content` et `summary`, entre le dernier `function_call_output` et la réponse du tour 1 ; OpenAI l'accepte avec `store: false` (aucun `outbound_response`, aucun `harness_error`) ; `calculator {"expression": "(2*60+38+25)*37"}` → « 6 771 » ; 2 appels, 0,000163 $ | **OK** : renvoi d'un tour à l'autre vérifié. Le renvoi dans le même tour (raisonnement, puis appel, puis appel suivant) ne s'est pas présenté : Luna n'a raisonné avant aucun appel d'outil |
| L5 | Luna | `mcp_lazy`, prompt 1 | `load_tool_doc` puis `local__define_term` | `load_tool_doc {"tool": "local__define_term"}` → `local__define_term {"term": "MCP"}` → « MCP signifie **Model Context Protocol**… » ; 3 appels, 0,000314 $, 4,2 s ; 0,0163 à 0,0173 Wh, 0,0076 à 0,0080 g CO₂e | **OK** |
| L6 | Luna | `subagent`, prompt 1 | délégation, résumé réinjecté | `delegate` → sous-agent : `read_file guide_harnais.md`, résumé en cinq points (225 tokens, sous la réserve de 512) → réponse ; `subagent_ended` : `completed`, 2 appels, 1 795 tokens gardés, 255 réinjectés, 1 540 économisés ; 4 appels, 0,000691 $, 7,7 s ; 0,0628 à 0,0677 Wh, 0,0266 à 0,0285 g CO₂e | **OK** |
| L7 | Luna | coût | coût par appel et total, fidèles aux prix déclarés | 20 appels facturés (14 au troisième lancement, 6 au quatrième), tous `usage_source = api`, `cost_source = api`, aucun token en cache ; 12 289 tokens d'entrée, 965 de sortie : 0,001711 $ (= 12 289 × 0,10 $ + 965 × 0,50 $ par million) | **OK** ; comparaison à la console : action d'Anaël |
| L8 | Luna | empreinte | `impact_method = ecologits`, fourchettes | les 20 appels portent `ecologits` et une fourchette ; total Luna : 0,145 à 0,154 Wh, 0,065 à 0,069 g CO₂e | **OK** |
| P1 | — | proxy, `api.anthropic.com` | 200 ou refus du proxy relevé | les 34 requêtes vers Anthropic, « Tester » compris, aboutissent, aucun `outbound_response`. Pendant tout le lancement, les sockets du serveur hors boucle locale ne vont qu'à **127.0.0.1:9000** (Zscaler) : 90 et 91 échantillons, aucune connexion directe vers Internet | **OK** : le proxy du poste laisse passer `api.anthropic.com` |
| P2 | — | proxy, `api.openai.com` | idem | avant la recharge, la requête traverse le proxy et la réponse vient d'OpenAI (son message de crédit épuisé), pas du proxy ; après, les 20 requêtes facturées aboutissent, aucun `outbound_response`, et les sockets du serveur ne vont qu'à 127.0.0.1:9000 (48 et 18 échantillons) | **OK** : le proxy laisse passer `api.openai.com` |
| C | — | coût total de la recette | moins de 2 $, sous le plafond de 5 $ | premier lancement : 0,035447 $ (17 appels, 0,0305 €) ; deuxième : 0,076806 $ (17 appels, 0,0661 €) ; troisième : 0,001288 $ (14 appels) ; quatrième : 0,000424 $ (6 appels) ; **total : 0,113964 $** (Anthropic 0,112253 $, OpenAI 0,001711 $). Empreinte des quatre lancements : 3,02 à 4,79 Wh, 1,26 à 1,95 g CO₂e | **OK** |

Le serveur s'arrête par Ctrl+Break dans sa console en 2,22 s, 2,52 s, 2,53 s et 2,29 s, flux SSE ouvert, dont le délai de grâce de 2 s.

## Success signal de SPEC.md

- **Atteint dans l'application**, plafond de 5 $, sur le PC cible : un scénario Outils (`native_tools`) et un scénario Raisonnement (`reasoning`) aboutissent avec Haiku (H2 à H4), Sonnet (S2 à S4) et Luna (L2 à L4b), et la réflexion de chacun s'affiche au canal Raisonnement (H2, S2, L2).
- **Coût dans 10 % de la console** :
  - Anthropic : vérifié par Anaël (action 1).
  - OpenAI : reste à vérifier (action 2).
- Le Success signal est donc complet pour Anthropic. Pour OpenAI, il ne manque plus que la comparaison avec la console.

## Correctifs appliqués

Aucun : aucune anomalie des stories 1 à 4 n'a été trouvée. Le constat S6 relève du sous-agent (story 19), pas des fournisseurs natifs : il est noté dans `deferred-work.md`.

## Actions d'Anaël

1. **Console Anthropic : comparer le coût** (SPEC.md demande un écart d'au plus 10 %). **Fait le 2026-10-03 au soir** : 0,16 $ au tableau de bord pour le mois, ≈ 0,159 $ estimés par WaveStack sur la journée (stories 3 et 5, recette Chrome, plafond) ; écart sous l'arrondi au centime : OK (détail dans `resultats-batterie-2026-10-03.md`, section 6).
   - Page Usage ou Cost, journée du 2026-10-03, par modèle. Les appels de la recette vont de 15:08:44 à 15:10:42 UTC (17:08 à 17:11, heure de Paris).
   - Chiffres de WaveStack à comparer :

     | Modèle | Requêtes | Tokens d'entrée | Tokens de sortie | Coût WaveStack |
     |---|---|---|---|---|
     | `claude-haiku-4-5` | 14 | 20 837 | 1 828 | 0,029977 $ |
     | `claude-sonnet-5` | 20 | 29 228 | 2 382 | 0,082276 $ |
     | Total | 34 | 50 065 | 4 210 | 0,112253 $ |

   - La même journée compte aussi les mesures de la story 3 (10 requêtes facturées, 0,0258 $ ; `mesures-anthropic-2026-10.md`) et tout autre usage de la clé. Si la console ne filtre pas à la minute, comparer le total du jour à 0,1381 $ (0,112253 + 0,0258), plus les autres usages éventuels.
2. **Console OpenAI : comparer le coût.** Crédit rechargé et lignes L1 à L8 jouées le 2026-10-03 au soir.
   - Page Usage, journée du 2026-10-03, modèle `gpt-6-luna`. Les appels facturés vont de 17:37:16 à 17:38:59 UTC (19:37 à 19:39, heure de Paris).
   - Chiffres de WaveStack à comparer :

     | Modèle | Requêtes facturées | Tokens d'entrée | Tokens de sortie | Coût WaveStack |
     |---|---|---|---|---|
     | `gpt-6-luna` | 20 | 12 289 | 965 | 0,001711 $ |

   - La requête de 15:10:45 UTC (crédit épuisé) n'est pas facturée. La console arrondit au centime : à ce volume (moins d'un dixième de centime), seuls les tokens permettent la comparaison à 10 %.
   - Le résumé du raisonnement s'affiche (L2) : la vérification de l'organisation n'est pas nécessaire.

## Remarques de méthode

- `netstat` affiche ses en-têtes dans la page de code OEM : sans `encoding="oem"`, la lecture de sa sortie échoue (`UnicodeDecodeError`). Ses états (`LISTENING`, `ESTABLISHED`) restent en anglais sur ce poste francisé.
- Une console Windows en cp1252 ne sait pas écrire certains caractères des réponses des modèles (émojis) : il faut lancer le script avec `PYTHONIOENCODING=utf-8`. C'est la cause de l'arrêt du premier lancement.
- Les en-têtes `anthropic-version` et `anthropic-beta` sont masqués dans `outbound_request`, comme tout en-tête hors `PUBLIC_HEADERS` (story 1, AD-5 amendé) : le journal ne permet pas de voir l'en-tête `thinking-binding-controls-2026-08-01`. Le corps, lui, montre `block_binding`, qui n'est accepté qu'avec cet en-tête.
- Les signatures des blocs `thinking` d'Anthropic et l'`encrypted_content` des items `reasoning` d'OpenAI figurent en clair dans `model_call_ended.raw_output`, comme dans `outbound_request.body`. Le masquage du flux brut (`mask_key`) ne vise que la clé d'API. La spec de la story 3 dit les signatures « masquées dans `model_call_ended` » : il faut trancher entre deux lectures. Soit masquer veut dire passer par `mask_key`, et c'est le comportement du code. Soit masquer veut dire cacher la valeur, et le code ne le fait pas. Rien n'est corrigé ici : `outbound_request.body` doit rester égal au corps envoyé (CAP-1), et ces valeurs sont des jetons opaques du fournisseur, pas des secrets du poste.
- Le « Tester » de chaque modèle répond « 1er janvier 2026 à 9 h » : c'est le résultat fixe de l'outil de test (`content/`), pas l'heure réelle.

## Vérification

- `Get-NetTCPConnection -LocalPort 8420` : rien à l'écoute à la fin (seules des connexions `TIME_WAIT`).
- `settings.json` et `memory.json` : identiques octet pour octet à la sauvegarde d'avant la recette (`cmp`). `api_keys.json` n'a pas changé (date de modification : 2026-10-01).
- `git grep -nE "sk-ant-|sk-proj-"` : aucun résultat. Les journaux de la recette, hors du dépôt, n'en contiennent pas non plus.
