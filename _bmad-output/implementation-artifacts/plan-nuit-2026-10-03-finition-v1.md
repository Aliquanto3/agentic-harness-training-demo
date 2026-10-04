# Plan de la nuit du 2026-10-03 : finition de la V1

État de départ : `main` à `a5488a4` (PR #20 fusionnée, `stream_resync` corrigé, console OpenAI
comparée). `deferred-work.md` compte 47 entrées sans `closed:` ; ce plan les trie toutes.
Numéros = ordre d'apparition des entrées ouvertes dans `deferred-work.md` (hors entrées déjà
tranchées « non » par Anaël le 2026-10-01, reprises par 8e/9b ou obsolètes : on leur ajoute
seulement `closed:` en phase 0).

Décisions : celles marquées **[A]** sont les recommandations de Claude, validées par Anaël si
ce fichier n'a pas été modifié avant la nuit. Toute autre question : décider, noter au rapport,
continuer.

## Phase 0 — Ménage (sans code)

Branche `feat/finition-v1` tirée de `main`. Committer ce plan en premier.

1. Ajouter `closed:` (date, preuve) aux entrées déjà tranchées : D1, D2, D8, D10, D12, D13,
   D14, 11b obsolète, 9b et 8e (plans réalisés).
2. Fermer sur preuve de la batterie du 03/10 (`resultats-batterie-2026-10-03.md`, tranches T4,
   T6, T9 vertes) : D3 actions forcées (`_forced_section`, `s_mcp_lazy`), D5 outils consultés
   (`_consulted_tools`), D7 date du tiroir (`s_global_memory`), et la partie `stream_lost` de
   l'entrée « Contrôles E2E de la story 2 » (le reste, `.brick-drift`, voir phase 1-C).
   Vérifier chaque nom de contrôle dans `tools/e2e/run_e2e.py` avant de fermer.
3. Docs périmées : `ARCHITECTURE-SPINE.md` l. 866 (« tev1 … reste à mesurer dans la story 8 »
   → résultat des stories 8 et 9) ; `spec-fournisseurs-natifs/formats-natifs.md` (« off = low »
   pour Opus/Sol, retiré le 03/10).

## Phase 1 — Corrections

Chaque groupe : spec courte en tête de commit ou dans ce fichier, tests d'abord, ruff, tests
ciblés, revue adversariale (méthode `/bmad-code-review`, une passe), commit. Toute chaîne
d'interface en fr, en, de.

### 1-A Démo visible
- **#23 et #29, réserve du sous-agent [A]** : pas de réserve plus grande (budget CPU). Consigne
  dans le prompt 1 du scénario `subagent` (`content/scenarios.yaml` et surcouches en, de) :
  résumé en cinq points d'une ligne, 80 mots au plus. Vérifier `tests/test_program.py`.
- **#27, plafond de séance visible [A]** : « x $ sur 5 $ » dans l'infobulle de la jauge de
  dépense et dans le diagnostic ; pas d'alerte à l'approche.
- **#25, préréglage Mistral [A]** : README et `notes_text` disent qu'un plan (« Experiment »
  gratuit ou payant) s'active dans la console avant le premier appel, et que le coût n'est
  nul que sur le plan gratuit.
- **#20, arrêt volontaire d'un téléchargement RAG [A]** : distinguer `StopToken` d'une panne ;
  carte neutre « Téléchargement arrêté », sans consigne de copie manuelle.
- **#9, article manquant dans le refus de budget de l'atelier RAG [A]** : corriger fr, en, de.
- **#36, Anthropic sans crédit [A]** : reconnaître la forme documentée (400
  `invalid_request_error`, « credit balance is too low ») dans `no_credit`, test à l'appui ;
  noter au rapport « forme lue dans la documentation, non mesurée ».

### 1-B Robustesse
- **#11, E119 [A]** : `previous=None` pour le rechargement du retour, et un effet qui dit
  l'échec du retour ; test où le rechargement de A échoue.
- **#14, garde réseau [A]** : appliquer la règle de `getaddrinfo` à `socket.gethostbyaddr` et
  `socket.getnameinfo`, test sous `_run_guarded`.
- **#21, sortie sans `lifespan` [A]** : repli `atexit` qui appelle `app_session.close()` une
  seule fois (idempotent) ; mesurer le double Ctrl+C sur le PC ; la fermeture de la fenêtre
  reste à tester par Anaël (geste manuel, noté au rapport).

### 1-C Contrôles automatiques manquants
- **#28 et #35, `reasoning_dropped` [A]** : point API Messages dans le faux fournisseur E2E
  (`tools/e2e/fake_openai.py` ou voisin), étape E2E au tour et au sous-agent.
- **#16, rendu H5 [A]** : contrôles E2E du libellé de l'outil, du focus après réponse et de
  l'étape H5 d'Orchestration.
- Fermer comme **limites connues [A]** (`closed:` avec la mention « limite connue, décision
  d'Anaël du 2026-10-03 ») : #8, #10, #13, #15, #17, #24, et `.brick-drift` de #12.

### 1-D Mesurer, puis décider seul
- **#18 Markdown** : mesurer `renderMarkdown` sur 5 ko de JSON hors bloc pendant le flux ;
  corriger si plus de 50 ms par rendu, sinon fermer.
- **#19 `_header_kv`** : chronométrer `discovery.discover()` ; passer par
  `catalog.header_metadata` si sa part dépasse 20 %, sinon fermer.
- **#34 réflexion entrelacée** : un appel Sonnet 5 (texte avant `tool_use`), relever l'ordre
  des blocs et le renvoi ; corriger l'ordre si Claude entrelace, sinon fermer avec la mesure.
- **#22 premier lancement à 10 min [A]** : limite connue, une phrase au README (dossier de
  données vide et nombreux modèles Ollama).

## Phase 2 — Vérifications sur le PC (Qwen3.5-2B, CPU)

- **#4, #5, #6** : jouer `mcp_lazy`, `iam`, `sovereignty`, `soc`, `subagent`, `compression`,
  `skills` avec le 2B ; fermer chaque entrée sur le relevé (appels attendus, `prompt_ms` du
  premier appel de chaque quiz < 15 s, pas de `prefix_not_reused` de cause `history`), ou la
  laisser ouverte avec le constat.
- **#7** : `tests/test_program.py` en mode exact (`WAVESTACK_TEST_GGUF` sur le 2B).
- **Installation à blanc** (objectif SM-5) : `git archive` de la branche en zip, décompression
  dans un dossier temporaire, procédure du README à la lettre avec un `WAVESTACK_DATA_DIR`
  vide, sans droits admin ; chronométrer jusqu'à l'atelier prêt (cible < 20 min hors
  téléchargement du modèle) ; noter chaque écart au README.

## Phase 3 — Batterie et PR

ruff, pytest en quarts, `-m model`, E2E par tranches (T1 à T11), recette Claude in Chrome des
écrans touchés. Rapport `rapport-nuit-2026-10-03-finition-v1.md` : tableau des 47 entrées
(fermée, corrigée, limite connue, restée ouverte et pourquoi), décisions prises, coûts. Push,
PR vers `main` sans fusion, bloc « Étape suivante ».

## Hors V1 (ne pas toucher cette nuit)

#26, #30, #31, #32, #33 (bancs V2 : Decision 2.0, tev1, Kev-0.8B, RSS de llama-server,
critères de Julia-1) restent ouvertes, comme backlog de la V2. Stories 1 à 5 de la V2 : non
déclenchées.
