# Rapport de la nuit du 2026-10-03 : finition de la V1

- Branche : `feat/finition-v1`, tirée de `main` à `a5488a4` ; PR #21 vers `main` ouverte, **non fusionnée**.
- Plan suivi : `plan-nuit-2026-10-03-finition-v1.md` ; journal pas à pas : `etat-nuit-2026-10-03.md`.
- Poste : PC cible (i5-1145G7, 15,7 Go, Windows 11, sans droits admin), sans Anaël devant.
- Anti-veille : `tools/keep_awake.ps1` relancé en début de nuit (le PID 900 noté était mort), vérifié au début de chaque phase.

## En bref

- **47 entrées ouvertes au départ, 8 encore ouvertes** : les 5 bancs V2 « Hors V1 » (non touchés) et les 3 vérifications de scénarios avec le 2B, que la mémoire du poste a empêchées (voir « Phase 2 »).
- 15 entrées corrigées (code, contenu ou contrôles E2E), 8 fermées comme limites connues sur décision [A] (dont #12, pour sa partie `.brick-drift`), 16 fermées sur décision antérieure, preuve E2E ou mesure.
- Deux défauts trouvés en mesurant et corrigés : le rendu Markdown cubique sur des `*` non fermés (553 ms → 0,6 ms) et la double lecture des en-têtes GGUF au diagnostic (6,5 s → 3,5 à 4,2 s).
- Un test échouait sur `main` depuis la PR #20 (empreinte du corps Gemini, `thinking_level` passé à « high ») : empreinte mise à jour.
- Dépense cloud : ≈ 0,05 $ (sonde Sonnet 5 de #34), plafond de la nuit 1 $.

## Tableau des 47 entrées

Numéros du plan : les 11 entrées déjà tranchées n'en ont pas (lettre D ou story) ; les 36 autres sont #1 à #36 dans l'ordre de `deferred-work.md`.

| N° | Entrée | Issue | Preuve |
|---|---|---|---|
| D1 | Détail de la jauge (grille `/context`) | Fermée (décision « non » du 01/10) | `deferred-work.md` |
| D2 | Repli hors ligne de `fetch_page` | Fermée (décision « non ») | idem |
| 9b | Documentations MCP au rejeu | Fermée (story 9b livrée) | `test_replay.py` |
| 8e | Arête du schéma sous un nœud | Fermée (story 8e livrée) | E2E `h5`, `data_flows` |
| 9b | Rejeu du dernier prompt | Fermée (story 9b livrée) | `test_replay.py` |
| 11b | Front de la story 11b sans test | Fermée (obsolète) | — |
| D8 | Ajout d'entrée depuis le tiroir | Fermée (décision « non ») | — |
| D10 | `transform_context` point d'accroche | Fermée (décision « non ») | — |
| D12 | Borne de temps de `compress()` | Fermée (décision « non ») | — |
| D13 | SOC : H1 et non H5 | Fermée (décision : garder H1) | — |
| D14 | Repli hors ligne IAM / Souveraineté | Fermée (décision « non ») | — |
| #1 | D3 actions forcées difficiles à trouver | Fermée sur preuve | batterie du 03/10, T4 et T6 |
| #2 | D5 attribution des sources | Fermée sur preuve | T5, T6 |
| #3 | D7 date du tiroir de mémoire | Fermée sur preuve | T6 |
| #4 | Scénarios avec le 2B (RAG hors sujet…) | **Ouverte** | passage avec le 2B arrêté faute de mémoire |
| #5 | Sous-agent : quiz qui relisent tout | **Ouverte** | idem |
| #6 | Comportement du 2B (outils non appelés…) | **Ouverte** | idem |
| #7 | `fits` en mode exact | Fermée (mesurée) | mode exact sur le 2B : passe, `subagent` p4 3 058 / 3 584 |
| #8 | Distribution simulée non comparée | Limite connue [A] | — |
| #9 | Article du refus de budget RAG | Corrigée | `to_load` fr/en/de, `test_rag_lab.py` |
| #10 | Ordre de `conftest.py` sans proxy | Limite connue [A] | — |
| #11 | E119, retour qui échoue | Corrigée | `test_model_servers.py` |
| #12 | Contrôles E2E de la story 2 | Fermée : `stream_lost` vert ; `.brick-drift` limite connue [A] | T9 |
| #13 | Pages LLM/RAG/MCP sans indicateur | Limite connue [A] | — |
| #14 | Garde : `gethostbyaddr`, `getnameinfo` | Corrigée | `test_net_guard.py` |
| #15 | DNS d'un nom passé à `connect` | Limite connue [A] | docstring de `net/guard.py` |
| #16 | Rendu H5 sans contrôle E2E | Corrigée (6 contrôles) | E2E `h5`, `hooks`, mutations détectées |
| #17 | `eventSummary` partiel | Limite connue [A] | — |
| #18 | Markdown quadratique | Mesurée, corrigée | voir 1-D |
| #19 | `_header_kv` relu | Mesurée, corrigée | `test_probe.py`, voir 1-D |
| #20 | Arrêt d'un téléchargement RAG en rouge | Corrigée | `test_rag_download.py`, E2E `rag` |
| #21 | Sortie sans `lifespan` | Corrigée (`finally` + `atexit`) | `test_cli_launch.py` ; fenêtre fermée : à tester par Anaël |
| #22 | Premier lancement de 10 min | Limite connue [A], phrase au README | README |
| #23 | Sous-agent : résumé du 2B coupé à 512 | Corrigée (consigne bornée) | `test_program.py` |
| #24 | `_stream` : annulation pendant la connexion | Limite connue [A] | — |
| #25 | Préréglage Mistral : plan à activer | Corrigée | README, `wavestack.toml` |
| #26 | Decision 2.0 | **Ouverte, hors V1** | — |
| #27 | Plafond de séance visible | Corrigée | `test_web_app.py`, E2E `priced_estimate` |
| #28 | `reasoning_dropped` sans E2E | Corrigée | E2E `reasoning_dropped` |
| #29 | Sous-agent de Sonnet coupé à 512 | Corrigée (même consigne que #23) | non rejoué avec Sonnet |
| #30 | tev1 | **Ouverte, hors V1** | — |
| #31 | Kev-0.8B | **Ouverte, hors V1** | — |
| #32 | RSS de llama-server | **Ouverte, hors V1** | — |
| #33 | Critères de Julia-1 | **Ouverte, hors V1** | — |
| #34 | Réflexion entrelacée | Fermée (mesurée) | 3 appels Sonnet 5, jamais entrelacé |
| #35 | Front de `reasoning_dropped` | Corrigée | E2E `reasoning_dropped` |
| #36 | Anthropic sans crédit | Corrigée (forme **lue dans la documentation, non mesurée**) | `test_anthropic_messages.py` |

## Phase 0 — ménage

14 entrées fermées : 11 tranchées avant la nuit, et D3, D5, D7 prouvées par la batterie du 03/10 (noms des contrôles vérifiés dans `run_e2e.py`). `ARCHITECTURE-SPINE.md` donne le résultat des stories 8 et 9 de la V2. `formats-natifs.md` n'a plus « off = low » pour Opus et Sol ; le `sampling` de Haiku et de Luna y suit le toml.

## Phase 1 — corrections

Chaque groupe : tests d'abord, ruff, tests ciblés, revue adversariale (une passe, méthode `/bmad-code-review`, sous-agent en lecture seule), commit. Chaînes d'interface en fr, en, de.

**1-A** (`d61b294`). Revue : 9 constats mineurs, tous corrigés, dont :
- le plafond suivi en direct sur le diagnostic ;
- « ≈ » sur un total estimé ;
- « une fois le plafond atteint » plutôt que « au-delà » (cas d'un plafond à 0) ;
- le texte de l'arrêt juste pour un modèle à plusieurs fichiers ;
- l'exemple du champ de tâche borné lui aussi.

**1-B** (`d61b294`). Revue : 6 constats.
- Le principal : l'`atexit` seul arrivait après l'attente des fils de travail. Un tour en attente de H5 aurait bloqué la sortie. `main` ferme donc aussi la session dans un `finally`, sur le fil principal.
- Laissé : après un retour E119 raté, le choix enregistré reste le modèle refusé. Au lancement suivant, le cas « sans modèle précédent » l'explique.
- Limite notée dans le code : `socket.getfqdn()` sur le nom du poste serait refusé par la garde. Personne ne l'appelle.

**1-C** (`d61b294`, `0b5a50f`).
- Le faux fournisseur E2E parle l'API Messages (`POST /v1/messages`, sixième entrée `fake_a`).
- Scénario `reasoning_dropped` : 14 vérifications.
- Six contrôles H5 et H1. Deux mutations d'`app.js` (`toolLabel`, carte reconstruite à chaque rendu) font échouer leur contrôle.

**1-D, mesures** (`cfd4d43`, `8dfdded`, `9a01142`) :
- **#18** : dans Edge, `renderMarkdown` sur 5 ko, 250 rendus de flux.
  - JSON compact ou indenté : ≤ 2,9 ms, sous le seuil de 50 ms.
  - Des `*` non fermés montaient à 553 ms (rendu complet) et 356 ms (pire rendu du flux) : coût cubique, un `slice` par fermeture candidate. Corrigé : 0,6 ms au pire.
  - `[` non fermés : 19,5 ms au pire, laissés tels quels.
  - E2E `markdown` 16/16.
- **#19** : `_header_kv` faisait 82 % de `discovery.discover()` sous profileur (8,4 s sur 10,2 s, 41 candidats dont 19 modèles Ollama). Il passe par `catalog.header_metadata`. Découverte plus en-têtes du catalogue, sans profileur : 6,5 s avant, 3,5 à 4,2 s après.
- **#34** : trois appels réels à Sonnet 5 (réflexion adaptative résumée, outil `calculator`, consignes qui demandent une phrase avant l'appel puis entre deux appels).
  - Ordre reçu : `thinking, text, tool_use`, puis `thinking, text, tool_use, tool_use` ; jamais de réflexion après un texte.
  - Le renvoi dans l'ordre de WaveStack est accepté, sans `input_transformations`.
  - Ordre de rendu inchangé. ≈ 0,05 $.
- **#22** : phrase au README. En relisant, l'entrée « Diagnostic » du menu « Volets ▾ » (disparu) devient le lien de la barre de navigation.

## Phase 2 — vérifications sur le PC

- **#7** : `test_program.py`, mode exact (`WAVESTACK_TEST_GGUF` = Qwen3.5-2B), passe en 256 s.
- **#4, #5, #6, non faites.** Le script, désormais dans le dépôt (`tools/recette_scenarios_2b.py`), devait jouer les sept scénarios par l'API, sur le port 8420 et avec les données d'Anaël, préalablement sauvegardées.
  - Premier essai : refusé en 403, il manquait l'en-tête `Origin` ; aucun prompt envoyé.
  - Second essai : arrêté par Claude Code pendant le chargement du 2B, le poste manquant de mémoire (3,6 Go libres, Edge ouvert pour la recette).
  - Consigne de Claude Code : ne pas le relancer sans votre accord. Ces trois entrées restent donc ouvertes.
  - Serveur arrêté ; `settings.json` et `memory.json` d'Anaël restaurés et vérifiés à l'octet (le lancement avait changé la langue, le modèle et la mémoire de démonstration).
- **Installation à blanc (SM-5), en version légère.**
  - Procédure : `git archive` de HEAD en zip (20,6 Mo), décompression (36 s), `uv run wavestack --port 8421` avec un `WAVESTACK_DATA_DIR` vide, Ollama et le cache HF isolés, sans droits admin.
  - Santé à 19 s ; diagnostic fini à 22 s : 7 modèles cloud, 19 modèles servis par Ollama, contrôle `model` bloquant tant qu'aucun choix n'est fait.
  - Soit environ 1 min, bien sous la cible de 20 min. Mais le cache uv était chaud : un poste neuf télécharge aussi Python et les roues.
  - Choix et chargement d'un modèle non joués, pour la mémoire.
  - Aucun écart au README relevé.
- **Double Ctrl+C (#21)** : deux Ctrl+C à 0,3 s d'écart sur cette instance sans modèle. Sortie en 2,6 s, sans blocage.
  - Non mesuré : un modèle Ollama chargé, pour la mémoire.
  - La fermeture de la fenêtre de console reste à tester par vous (geste manuel).

## Phase 3 — batterie

Une suite à la fois, aucun modèle local chargé pendant pytest, dossier `pytest-of-anael.yahi` vidé après chaque suite, captures E2E remises après chaque tranche.

| Suite | Résultat |
|---|---|
| `ruff check .` / `ruff format --check .` | OK (212 fichiers) |
| pytest, quart 1 (17 fichiers) | 3 778 passés, **1 échec** : `test_openai_chat_bodies_are_byte_for_byte_those_before_the_refactoring` (corrigé, voir ci-dessous) |
| pytest, quart 2 (17 fichiers) | 697 passés, 6 désélectionnés |
| pytest, quart 3 (17 fichiers) | 414 passés, 3 sautés, 6 désélectionnés |
| pytest, quart 4 (14 fichiers) | 567 passés |
| `-m model` (2B, `WAVESTACK_TEST_GGUF` et `WAVESTACK_TEST_MODELS_DIR`) | 12 passés |
| E2E, onze tranches (T9 avec `reasoning_dropped`) | **1 091 vérifications réussies, 0 échec** (T1 91, T2 69, T3 157, T4 59, T5 103, T6 142, T7 95, T8 86, T9 66, T10 137, T11 86) |
| Recette navigateur (Edge, Claude in Chrome, pile E2E à faux fournisseur) | OK, détail ci-dessous |

**L'échec de pytest était antérieur à la nuit.** `tests/fixtures/openai_chat_bodies.json` gardait l'empreinte du corps Gemini « on » à `thinking_level` « medium ». Le passage à « high » (`1c0dbbe`, PR #20) ne l'avait pas mise à jour : le test échouait sur `main` depuis la fusion. Vérifié : en remettant « medium », l'ancienne empreinte revient à l'identique. Empreinte mise à jour (`e36870a`), `test_cloud_api.py` 18/18.

**Recette navigateur.** Faite dans Edge, sur la pile E2E avec le faux fournisseur, sans modèle local ni appel réel. Fenêtre en arrière-plan : captures impossibles, contrôles par le DOM.
- Page de diagnostic : « Plafond de dépense de la séance : 0 $ dépensés sur 5 $… ».
- Après un appel payant sur `fake_m` (prix du préréglage Mistral), la ligne se met à jour sans recharger : « ≈ 0,00001275 $ dépensés sur 5 $ ».
- Infobulle de la dépense dans l'atelier, avec « ce total » au singulier (pas d'empreinte) :
  - fr : « Plafond de dépense de la séance : ≈ 0,00001275 $ sur 5 $ ; une fois le plafond atteint, aucun appel payant ne part. »
  - en : « Session spending cap: ≈ $0.00001275 of $5; once the cap is reached, no paid call is sent. »
  - de : « Ausgabenobergrenze der Sitzung: ≈ 0,00001275 $ von 5 $; sobald sie erreicht ist, … »
- Diagnostic en allemand : la ligne du plafond est traduite.
- Les autres écrans touchés (carte RAG à l'arrêt, H5, `reasoning_dropped`) sont couverts par l'E2E de la nuit.

## Décisions prises seul (« décide, note, continue »)

- Les commits de 1-A, 1-B et du premier tiers de 1-C sont réunis en un seul (`d61b294`) : les mêmes fichiers portent les trois groupes (`app_session.py`, catalogues de messages, E2E).
- **#20** : l'arrêt devient un `effect_applied` (nouvel effet `model_download_stopped`) plutôt qu'un nouveau type d'événement. Cela évite un libellé de plus dans `main.log.kinds` en trois langues.
- **#27** : le plafond figure aussi sur le diagnostic, mis à jour par `consumption_updated` ; texte « une fois le plafond atteint » (valable pour un plafond à 0).
- **#18** : seuls les `*` sont corrigés ; les `[` non fermés restent sous le seuil (19,5 ms).
- **#29** : non rejoué avec Sonnet, pour éviter la dépense ; la borne de 80 mots fait environ 110 tokens.
- **#21** : `finally` en plus de l'`atexit` demandé par le plan, sur le constat de la revue.
- **Phase 2** : le passage avec le 2B n'est pas relancé, à cause de la consigne de Claude Code après l'arrêt pour mémoire.

## Coûts

| Poste | Dépense |
|---|---|
| Sonde Sonnet 5 (#34), 6 appels | ≈ 0,05 $ |
| Total | ≈ 0,05 $ sur 1 $ autorisé |

## Ce qui vous revient

1. **Relire la PR [#21](https://github.com/Aliquanto3/agentic-harness-training-demo/pull/21)**, puis la fusionner si elle vous convient.
2. **Rejouer #4 à #6 avec le 2B**, la mémoire libre (Edge, Teams et Outlook fermés, ≈ 4 Go libres) :
   - sauvegarder `%LOCALAPPDATA%\WaveStack\settings.json` et `memory.json` ;
   - lancer `uv run python tools/recette_scenarios_2b.py` (sept scénarios, ≈ 30 min, résultats dans `recette-scenarios-2b.json`) ;
   - restaurer les deux fichiers.
   - Critères : appels de `local__define_term`, `mslearn__microsoft_docs_search` et `datagouv__search_datasets` ; escalade SOC ; délégation au premier prompt de `subagent`, puis quiz sans redélégation ; `prompt_ms` du premier appel de chaque quiz < 15 s, aucun `prefix_not_reused` de cause `history`.
3. **Fermer la fenêtre de console** d'un WaveStack qui a un modèle Ollama chargé, puis vérifier que le modèle est déchargé (#21, geste manuel).
4. Si vous voulez la mesure : rejouer le scénario `subagent` avec Sonnet 5 pour confirmer #29 (≈ 0,02 $).

## Étape suivante

- **Skill** : `/bmad-code-review` sur la PR de la nuit (revue complète, couches multiples), puis fusion par vous.
- **Prompt** (prêt à coller) :
  ```
  /bmad-code-review Revue de la PR « feat/finition-v1 » (finition de la V1, nuit du 03/10) : diff a5488a4..feat/finition-v1, découpé en groupes (1. src/ et content/, 2. tests/ et tools/e2e/, 3. docs _bmad-output). Rapport : _bmad-output/implementation-artifacts/rapport-nuit-2026-10-03-finition-v1.md. Appliquer les correctifs validés sur la branche, sans fusionner.
  ```
- **Modèle** : Opus 5.5. Revue d'un diff moyen, sans difficulté de conception : le défaut suffit (Fable 5.1 serait surdimensionné).
- **Effort** : medium. Les revues adversariales de 1-A et 1-B ont déjà été faites pendant la nuit ; une passe de plus n'a pas besoin d'aller plus profond.
- **`/clear` avant** : oui. La session de la nuit est longue, et la revue repart du diff et du rapport.

Ensuite, une fois la PR fusionnée et #4 à #6 rejouées : la V1 est terminée, à part les 5 bancs V2 du backlog.
