---
title: 'Lot J : suites simples du test sur PC du palier 2 (journal du tokenizer, test fits, budget de raisonnement, coût de Headroom, documentation)'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le test sur PC du 2026-09-27 au soir (`resultats-test-pc-palier-2-2026-09-27.md`,
synthèse d) a relevé des anomalies simples. (1) `VocabTokenizer`, quand il ouvre seul un GGUF
(`vocab_only`, chemin de llama-server et d'Ollama, et test `fits`), laisse le journal de
llama.cpp partir en entier sur stderr, ce qui lève `UnicodeEncodeError` sur une console cp1252.
(2) Le test `fits`, avec `WAVESTACK_TEST_GGUF`, compte avec le tokenizer du 2B le rendu du mode
chat (session cloud) : il sous-estime le mode local d'environ 20 % (`mcp_full` : 2 572 comptés,
3 204 dans la jauge locale) et échoue sur son garde-fou `mcp_full > 2800`. (3) Le budget de
raisonnement de 1 024 tokens dépasse le critère de 120 s (127 à 134 s ; 768 : 111 s). (4)
`[compression] cost_mb = 130` alors que Headroom ajoute 84 Mo au pic sous Windows. (5) Le guide
de test contient des attendus inexacts.

**Approach:** Décisions de l'utilisateur (2026-09-27) : périmètre « correctifs simples +
documentation » ; budget de raisonnement par défaut **768** ; `cost_mb` **110** (84 × 1,3,
arrondi à la dizaine ; au-dessus des 107 Mo mesurés sous Linux). (1) couper le journal de
llama.cpp au niveau ERROR quand `VocabTokenizer` ouvre seul le fichier, avec un test. (2) avec
`WAVESTACK_TEST_GGUF`, le test `fits` démarre ce GGUF en mode local et lit la jauge exacte
(`ctx["used"]`, facteur de sécurité 1,0 puisque le compte est exact) ; sans la variable, rien
ne change (session cloud, 2 caractères par token, facteur 1,1) ; le garde-fou `mcp_full > 2800`
reste. (3) et (4) changer les valeurs par défaut partout où elles sont écrites (configuration,
repli dans `config.py`, texte de la brique, README, tests). (5) corriger le guide
(`guide-test-pc-palier-2.md`), consigner les résultats et décisions dans
`plan-corrections-palier-2.md`, et les anomalies non simples dans `deferred-work.md`, avec leur
criticité : sous-agent avec RAG (relecture et redélégation, moyenne, lot H / D5), comportement
du 2B (moyenne, lot H), premier tour lent (faible à moyenne, spec future), relecture après
chargement d'une documentation en lazy loading (faible, spec future). Pas de commit ni de push
sans accord.

</frozen-after-approval>

## Implementation Notes

- (1) `src/wavestack/models/engine.py` : `VocabTokenizer`, ouvert seul, met le logger
  `llama-cpp-python` au niveau ERROR (celui que pose `Llama(verbose=False)`). Constat en
  implémentant : l'erreur naît dans le fichier nul que llama-cpp-python substitue à stderr
  pendant le chargement, ouvert en cp1252 sous Windows (pièces « Ċ », « Ġ » de Qwen3.5) ;
  rien n'apparaît sur la console, d'où un test qui espionne `print` en sous-processus, avec
  contrôle négatif (45 appels sans correctif, 0 avec). Test :
  `tests/test_model_servers.py::test_vocab_tokenizer_opened_alone_keeps_llama_cpp_quiet`.
- (2) `tests/test_program.py` : avec `WAVESTACK_TEST_GGUF`, session locale sur ce GGUF, jauge
  exacte, facteur `EXACT` = 1,0 (`_verdict(..., safety)`). Sur le PC cible : `mcp_full`
  3 204 / 3 584, identique à la jauge de l'interface ; le test passe dans les deux modes.
- (3) Budget 768 : `wavestack.toml`, `config.DEFAULT_REASONING_BUDGET`,
  `content/bricks/reasoning.yaml`, `tests/test_reasoning_budget.py` (valeurs dérivées de 768,
  réponse longue `LEFT + 100`, balise à cheval `[:764]`), `tests/test_reasoning.py`.
- (4) `cost_mb` 110 : `wavestack.toml`, `config.compression_cost_bytes`, README,
  `tests/test_compression.py` (`test_compression_cost_is_110_mb_by_default`), story 12
  (nouvelle section de mesures), `tools/bench/results/2026-09-27-pc-cible-lot-f/`.
- (5) Guide (sections 0, 3, 4.1, 4.4, 5.1, 5.3, 5.5, 5.6, 5.7, 7), plan (section du test du
  soir, ligne N4), `deferred-work.md` (quatre entrées avec criticité).
- Vérification : ruff propre ; `pytest -q` 935 réussis, 3 sautés, 6 désélectionnés (Windows,
  avec l'extra) ; `-m model` 6 réussis ; `fits` avec le vrai GGUF réussi.

## Review Triage Log

Revue « Blind Hunter » (1 passe, 12 constats) :
- medium, corrigé : nombres de tests du guide (934 → 935, 937 → 938, 930 → 931 sans l'extra).
- low, corrigé : avec `WAVESTACK_TEST_GGUF`, `fits` charge le vrai modèle (≈ 20 s, ≈ 1,3 Go) ;
  documenté dans le guide (section 3).
- false : enveloppe du premier prompt non comptée. La jauge locale compte déjà l'enveloppe du
  tour et l'invite de génération (« Message et gabarit », 12 tokens pour `bare_llm` sans
  brique).
- medium, corrigé : le test du journal ne prouvait pas que l'espion voit la sortie ; contrôle
  négatif ajouté dans le test.
- low, corrigé : import privé `llama_cpp._logger` remplacé par le logger public
  `logging.getLogger("llama-cpp-python")` ; l'effet global est celui de
  `Llama(verbose=False)`, déjà posé par le moteur.
- false : spec réduite. C'est la voie `oneshot` du workflow ; la vérification est consignée
  ci-dessus.
- low, corrigé en partie : ligne N4 du plan annotée. Rejeté : réécrire les rapports, les
  specs des lots C et F et les anciennes entrées de `deferred-work.md`, qui sont des
  historiques datés (règle : ne pas modifier les anciennes entrées).
- low, corrigé : guide 5.1 (hypothèse des blancs, décision du sous-agent) et 4.1 (84 Mo).
- low, rejeté : 768 sur une mesure. Deux passages valides encadrent la décision (768 : 111 s ;
  1 024 : 134 et 127 s), prise par l'utilisateur ; le repli est documenté dans
  `wavestack.toml` et le guide.
- low, corrigé : story 12, limite de Windows (ni `strace` ni `unshare`) précisée.
- low, corrigé : chemins complets du fichier de résultats dans `deferred-work.md`. Le script de
  mesure reste hors dépôt, à la demande de l'utilisateur ; le fichier de résultats sera commité
  avec le lot.
- low, corrigé : deux lignes trop longues (README, guide).
