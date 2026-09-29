# Rapport des corrections du palier 2 (lots A à G et I)

Branche `claude/dreamy-cerf-gdjtee`, du commit `373d30a` (lot 0) au commit `cb3a20e`, suivi de ce rapport. Source :
`plan-corrections-palier-2.md`. Décisions appliquées : N1, N2, N3 (1 200 tokens), N4 (budget de
raisonnement 1 024), N5 (budget mémoire gardé à 4 096 Mo). N6 reste ouverte : le moteur par
défaut n'a pas changé. Le lot H n'est pas traité (il attend le prochain test).

Chaque lot a suivi `bmad-build-auto` : spec, implémentation, quatre relectures (aveugle, cas
limites, écarts de vérification, alignement sur l'intention), tri, correctifs. La spec de chaque
lot (`spec-lot-*.md`) garde son journal de tri et ses points différés. Après chaque lot :
`ruff check`, `ruff format --check` et `pytest -q` verts, un commit, un push.

| Lot | Commit | Tests (Linux, sans l'extra) |
|---|---|---|
| A | `7b22faf` | 799 réussis, 4 sautés |
| B | `0f54120` | 824 réussis, 4 sautés |
| C | `dc193ca` | 854 réussis, 4 sautés |
| D | `8afb1d5` | 868 réussis, 4 sautés ; E2E complet : 327 vérifications, 0 échec |
| E | `12faad6` | 911 réussis, 4 sautés ; E2E `model_switch` et `local_server` : 55, 0 échec |
| F | `515c858` | 922 réussis, 7 sautés ; tests Headroom avec l'extra : verts |
| G | `2abad49` | 930 réussis, 7 sautés ; avec la garde Windows simulée : 928 réussis, 9 sautés |
| I | `e2b399c` | inchangé (documentation) ; E2E complet : 336 vérifications sans l'extra, 356 avec, 0 échec |
| Correctif | `cb3a20e` | 930 réussis, 7 sautés |

Point de départ : 771 réussis, 4 sautés.

## Lot A — Premier token : réutiliser le cache entre les tours

**Fait.**
- A1 : en mode local, les réponses passées sont rendues telles qu'elles ont été produites. Le harnais déduit du gabarit le bloc de raisonnement qu'il écrit dans le tour (`reasoning_wrap`, Qwen3.5 : `<think>\n` … `\n</think>\n\n`) et le remet dans l'historique.
- A2 (N1) : la mémoire globale est figée par conversation. Les ajouts entrent à la conversation suivante ; une suppression ou une modification s'applique tout de suite.
- A3 : le premier appel de chaque tour est comparé aux ids en cache du moteur. Une relecture émet `prefix_not_reused` avec sa cause (`system`, `history`, `template`, `reset`, `replay`, `abandoned`, `subagent`, `in_turn`) et le nombre de tokens relus. `model_call_ended.evaluated_tokens` donne les tokens réellement évalués.
- A4 (N2) : l'état du moteur est sauvegardé et restauré autour du sous-agent, sans la copie des logits (≈ 500 Mo évités sur Qwen3.5). La taille et la durée sont affichées.

**Tests ajoutés.**
- `tests/test_turn_cache.py` : une ligne par cas.
- `tests/test_engine_cache.py` : vrai moteur sur `tiny-llama.gguf`.
- Tests `model` dans `tests/test_render_reference.py` (deux tours, sauvegarde et restauration).
- Tests serveurs et changement de modèle.

**À vérifier sur PC.**
- Second tour de `native_tools` : `prompt_ms` sous 3 s.
- Quiz du sous-agent : premier token sous 15 s.
- `prefix_not_reused` ne doit apparaître qu'avec une cause attendue.
- Taille de la copie d'état (`subagent_ended.state_saved_bytes`).
- Restauration de l'état récurrent de Qwen3.5 : lancer les tests `model` avec `WAVESTACK_TEST_GGUF`.
- Deux tours avec le raisonnement.

**Décisions par défaut.**
- Les extraits RAG restent hors de l'historique (choix de la story 15). Dans les scénarios avec RAG, chaque tour relit donc le contexte (cause `history`). C'est à revoir au lot H (D5).
- Le raisonnement passé reste dans l'historique : c'est le prix du cache, et le lot C borne sa taille.

## Lot B — Débordements causés par les résultats d'outils

**Fait.**
- B1 (N3) : les résultats des outils réseau et MCP (locaux compris) sont bornés à `[tools] result_max_tokens = 1200`, avant la compression. Cela vaut dans le tour, dans le sous-agent et pour les actions forcées.
- La coupe est visible par le modèle (mention) et dans Orchestration (« Résultat tronqué par le harnais : N tokens sur M »). En mode chat, la borne tient compte du ratio réel du fournisseur.
- B2 : la cause d'un débordement est tirée de tous les segments, et ne cite plus à tort les descriptions d'outils.
- B3 : le test `fits` compte à 2 caractères par token, ou avec le vrai tokenizer via `WAVESTACK_TEST_GGUF`, et réserve la place du premier résultat borné.

**Tests ajoutés.** `tests/test_tool_result_bound.py`, et le test `fits` renforcé (`tests/test_program.py`).

**À vérifier sur PC.**
- `mcp_lazy`, `data_flows`, `iam` et `sovereignty` jusqu'au bout avec le 2B, sans débordement.
- Le second prompt de `mcp_lazy` (≈ 3 380 / 3 584 estimés) et celui de `sovereignty`.
- `soc` déborde encore sur `journal_serveur.log` (outil local non borné, lot H), mais avec la bonne cause.

**Décisions par défaut.**
- `data_flows` démarre en lazy loading : sans lui, documentation complète plus un résultat borné dépasse encore la fenêtre.
- `read_file` n'est pas borné : c'est la matière du scénario Compression.

## Lot C — Raisonnement du 2B sans réponse

**Fait (N4).** En mode local, quand l'appel raisonne, la réflexion est bornée par `[reasoning] budget_tokens = 1024`.
- Au-delà, le harnais arrête la génération et ferme la réflexion avec le texte exact du gabarit.
- Il relance ensuite le modèle sur les ids en cache, avec le reste de la réserve de 1 536 tokens (≈ 512, au moins 128).
- La coupe est tracée (`reasoning_cut`, « Raisonnement coupé par le harnais à N tokens »), et la carte donne le budget.
- Le mode chat est inchangé.

**Tests ajoutés.** `tests/test_reasoning_budget.py` (29 cas, dont le repli sans cache, le cache en retard d'un token et la balise à cheval sur le budget).

**À vérifier sur PC.**
- Le prompt du train doit donner une réponse en moins de 120 s. C'est serré : ≈ 11 tokens/s, soit ≈ 90 s pour 1 024 tokens. Si besoin, baisser le budget.
- La relance ne doit pas relire tout le contexte.
- Le tour suivant ne doit pas afficher `prefix_not_reused`.

## Lot D — Outils réseau et parcours E2E

**Fait.**
- D1 : l'User-Agent porte un contact tiré de `[net] contact` (défaut : l'URL du dépôt, réglable pour GitLab).
- D2 : le lanceur E2E coupe lui-même le réseau sortant de WaveStack. Il fait pointer ses proxys vers un port de boucle locale fermé et laisse la boucle locale contournée. La requête est donc tracée, puis échoue « Service injoignable », sur un poste connecté comme hors ligne. `stack.py --network` garde le vrai réseau pour explorer à la main.

**Tests ajoutés.** `tests/test_e2e_stack.py` (dont un faux proxy qui enregistre le `CONNECT`), tests d'User-Agent.

**À vérifier sur PC.**
- Wikipédia répond 200.
- Parcours E2E sur le poste Windows connecté : 0 échec attendu. Un refus en boucle locale y prend 1 à 2 s.

**Décision par défaut.** Le réseau est coupé par un proxy fermé et non par `allowed_hosts` : la garde refuserait avant la trace, ce qui casserait les vérifications « requête tracée ».

## Lot E — Modèles : mémoire, refus et arrêt

**Fait.**
- E1 : un modèle servi par llama-server est compté avec le KV de tout son contexte. Le KV est lu par un lecteur d'en-tête GGUF en Python pur, qui gère les tableaux par couche des modèles hybrides, sans llama.cpp dans le processus principal. Le diagnostic conseille `-np 1 -c 4096`.
- E2 : la sonde mesure la RSS de pointe après l'évaluation d'un lot complet, au contexte de la fenêtre. Les anciennes entrées sont resondées (au lancement pour le modèle enregistré, les autres au moment du choix). Un échec passager n'est plus mémorisé comme incompatibilité. Le délai de la sonde passe à 300 s.
- E3 : le refus donne la vraie mémoire de WaveStack, en Mo sous 1 Go.
- E4 : « Arrêter » agit pendant un chargement, aux points d'étape, et le modèle précédent revient.
- E5 : les briques du scénario indisponibles avec le modèle actif sont signalées au lancement, avec leur raison.
- E6 : les raisons d'incompatibilité sont en français, et le message brut reste en cause technique.
- N5 est respectée.

**Tests ajoutés.**
- `tests/test_probe.py`, dont un GGUF hybride synthétique (`tests/gguf_writer.py`).
- `tests/test_model_switch.py`, `tests/test_model_servers.py`, `tests/test_cli_diagnostic.py`, `tests/test_scenarios.py`.
- E2E « Arrêter » pendant le chargement lent de `fake_b`.

**À vérifier sur PC.**
- RSS de la nouvelle sonde pour le 2B et le 4B : le 4B doit être refusé pour 4 096 Mo.
- llama-server avec et sans `-c` : environ 5 Go comptés sans `-c`.
- Lecture du KV du vrai GGUF Qwen3.5 (clés `qwen35.*`).
- « Arrêter » pendant un chargement Ollama ou GGUF.
- `llama3.2:3b` dans `native_tools` : l'encadré des briques indisponibles doit s'afficher.
- Raison française du blob Ollama refusé.
- Durée de la première sonde (≈ 15 à 30 s par modèle).

**Décision par défaut.** E5 est signalé au lancement du scénario, en plus des cartes qui donnaient déjà la raison. Aucun analyseur d'appels d'outils n'a été ajouté pour la famille Llama.

**Suivi.** Une relecture complémentaire est recommandée sur le lecteur GGUF, car un constat grave a été corrigé à la revue.

## Lot F — Headroom hors ligne et banc de la story 12

**Fait.**
- F1 : Headroom compte avec `gpt-4` (`cl100k_base`, présente sur le PC). Un test en sous-processus prouve qu'il n'y a aucune tentative réseau à l'import ni à la compression, avec un contrôle négatif sur `gpt-4o`.
- F3 : le banc mesure la RSS ajoutée au pic moins la base (`VmHWM` sous Linux), pour tous les candidats et pour Headroom. Les rapports portent `rss_added_method: "pic"`.
- F4 : `e5small_q8` est retiré, avec sa raison.

**Tests ajoutés.** Test hors ligne, test de la table livrée, tests du banc (`_embed_child`, faux `headroom`, verdicts sur les pics du PC).

**À vérifier sur PC.**
- Banc `headroom` sous Windows : « RETENU », et la mémoire ajoutée avec `gpt-4`.
- Banc `embed` au pic : bge-m3 et Qwen3-Embedding dépasseront le budget de 600 Mo, granite reste retenu.

**Décision par défaut (F2).** `cost_mb` est gardé à 130. Avec `gpt-4`, Headroom ajoute 107 Mo au pic sous Linux, soit plus que les 80 envisagés. Les 57 Mo du PC avaient été mesurés avec `gpt-4o`, la table étant absente.

## Lot G — Tests sous Windows et tests `model`

**Fait.**
- G1 : les tests d'index remplacé ont une variante portable, où la connexion est fermée avant la reconstruction. La variante « remplacé encore ouvert » reste active hors Windows.
- Un index tenu par un autre programme donne `IndexInUse`, avec un message clair pour le script et pour la carte. Les autres refus gardent leur erreur d'origine.
- Garde facultative `WAVESTACK_TEST_WINDOWS_FILES=1` : elle applique à la suite, sous Linux, la règle de fichiers de Windows. Sans échec.
- G2 : `WAVESTACK_TEST_MODELS_DIR` pour les tests `model` du RAG, et comparaison sur `s.score`.
- G3 : fait au lot I.

**Tests ajoutés.** Refus en français (index, script, carte), cas lecture seule, sérialisation, garde simulée.

**À vérifier sur PC.**
- `uv run pytest -q` sous Windows : 0 échec.
- `-m model` avec `WAVESTACK_TEST_MODELS_DIR` et `WAVESTACK_TEST_GGUF`.

## Lot I — Guide de test et documentation

**Fait.** Le guide `guide-test-pc-palier-2.md` est réécrit pour la prochaine séance.
- Les sept écarts du lot I sont corrigés : 2 560 utilisables avec le raisonnement ; llama-server avec `-c 4096` et RSS attendue ; Ollama `qwen3.5:2b` accepté ; E2E sans échec sur un poste connecté ; 4B refusé par le budget de 4 096 Mo, avec la raison ; Edge, Outlook et Teams fermés pendant les mesures ; un 429 de Mistral au premier appel de « Tester » signale un quota épuisé.
- G3 : 937 tests collectés hors `model`. Sous Windows avec l'extra, on attend 934 réussis et 3 sautés, chaque saut avec sa raison.
- Nouvelle section de vérification des lots A à G : pour chaque lot, le geste, l'attendu, le critère du plan et les hypothèses.
- Décisions à trancher (N6, D2, D3, D9, F2) et attentes du lot H.
- Tableau des résultats à remplir.
- Le README est aligné.

La revue du lot I a relevé deux textes de code contradictoires : la phrase « modèle hybride » en double dans `prefix_not_reused`, et la raison du tokenizer refusé qui citait Qwen3.5. Ils sont corrigés dans le commit `cb3a20e`, pour que le lot I reste documentaire.

**À vérifier sur PC.** Le nombre de tests sous Windows (934 réussis, 3 sautés) et l'ensemble de la section 5 du guide.

**Décision par défaut.** Le critère « quiz du sous-agent sous 15 s » est jugé RAG éteint. Avec le RAG, chaque tour relit le contexte par conception (D5, lot H). Les deux mesures sont consignées.

## Ce qui reste ouvert

- Le lot H (scénarios et consignes) passe après le prochain test, comme prévu.
- N6 (moteur conseillé pour Qwen3.5) : à trancher après la mesure du lot A sur le PC.
- Mesures sur le PC : voir la section 5 du guide (`guide-test-pc-palier-2.md`).
- Nouvelle entrée ouverte dans `deferred-work.md` : avec un Ollama trop ancien pour servir `qwen35`, le modèle est accepté, puis le premier tour échoue avec une erreur brute « HTTP 500 », sans raison en français ni retour au modèle précédent. Un correctif de code est à planifier.
- Relecture complémentaire recommandée sur le lot E : le lecteur d'en-tête GGUF (`src/wavestack/models/gguf_meta.py`), à confirmer sur le vrai fichier Qwen3.5.
- Proposition, non faite : pour un modèle hybride, toute divergence coûte une relecture complète. Des points de reprise de l'état (sauvegarde au début de la dernière question, comme les « context checkpoints » de llama-server) rendraient ces relectures partielles. C'est à envisager si la mesure du lot A ne suffit pas, avant de trancher N6.
