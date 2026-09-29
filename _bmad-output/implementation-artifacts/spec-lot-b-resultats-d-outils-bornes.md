---
title: "Lot B : résultats d'outils bornés et cause juste des débordements"
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '7b22faf19abd126ae23abaeab9603bb3ab61cafb'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/CLAUDE.md'
warnings: ['multiple-goals']
deferred:
  - summary: >-
      Le rendu de la coupe dans Orchestration (ligne « Résultat tronqué », « ≈ » en mode chat) n'est vérifié par aucun test automatique.
    evidence: |-
      Le dépôt n'a pas de banc de test JS ; seul le champ `truncated` de `tool_ended` est testé. À voir au test sur le PC cible.
    location: >-
      src/wavestack/web/static/app.js:toolBody
    severity: low
  - summary: >-
      Le second prompt de `mcp_lazy` (après le premier tour et les extraits RAG) n'est pas couvert par le test `fits`.
    evidence: |-
      Non vérifié : ≈ 2 180 + 1 200 = 3 380 sur 3 584 d'après la mesure du PC du 2026-09-27. Se tranche en rejouant `mcp_lazy` sur le PC cible.
    location: >-
      tests/test_program.py
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Sur le PC cible, les résultats des MCP publics ne sont pas bornés : data.gouv (547 jeux, ≈ 2 500 tokens) fait déborder `mcp_lazy` (4 680 / 3 584) et `data_flows` (5 605), Microsoft Learn (≈ 5 800 tokens) fait déborder `iam` (6 864), et les tours finissent sans réponse. Le message de débordement cite alors à tort « les descriptions d'outils » : il ne regarde que cinq genres de segments et ignore les résultats d'outils. Le test `fits` estime `mcp_full` à 1 530 tokens pour 3 204 réels (4 caractères par token) et ne réserve aucune place à un résultat d'outil.

**Approach:** B1 (décision N3) : borne par défaut de 1 200 tokens par résultat des outils MCP et réseau (`[tools] result_max_tokens`), appliquée avant la compression, coupe au dernier saut de ligne, mention « résultat tronqué : N tokens sur M » dans le texte réinjecté et dans l'étape d'Orchestration. B2 : la cause du débordement vient du vrai `breakdown` (résultats d'outils, documentation d'outils, historique, extraits RAG, mémoire, skills), avec des pistes adaptées. B3 : le test `fits` compte avec un tokenizer réaliste et vérifie la place du premier résultat borné.

## Boundaries & Constraints

**Always:** code et identifiants en anglais, textes en français ; `uv`, `ruff`, `pytest` ; tests verts sous Linux et Windows ; la borne s'applique aux résultats réussis des outils dont `spec.network or spec.is_mcp` (outils réseau et MCP, locaux compris), dans le tour, dans le sous-agent et pour une action forcée (chemin unique `_run_tool`) ; le texte coupé reste dans l'ordre et sans caractère coupé en deux ; la mention est visible par le modèle (texte réinjecté) et par l'humain (Orchestration) ; mode local : tokens comptés par le tokenizer du modèle ; mode chat : estimation (`_count_tokens`), marquée comme telle.

**Never:** borner `read_file` ni les autres outils natifs locaux (le journal `journal_serveur.log`, ≈ 2 000 tokens, est la matière du scénario Compression, qui montre l'erreur gardée) ; borner un message d'erreur d'outil ou le résultat du sous-agent (`delegate`) ; toucher à la compression, qui s'applique après la borne ; changer la valeur de N3 (1 200) ; ajouter une dépendance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Résultat MCP long | Outil `is_mcp`, résultat de ≈ 2 500 tokens, borne 1 200 | Texte réinjecté ≤ 1 200 tokens, coupé au dernier saut de ligne, suivi de « [Résultat tronqué par le harnais : N tokens sur M …] » ; `tool_ended` porte le résultat borné et `truncated {tokens, total_tokens, estimated}` ; Orchestration affiche « Résultat tronqué : N tokens sur M » | — |
| Résultat court | Résultat ≤ borne | Inchangé, pas de `truncated` | — |
| Résultat sans saut de ligne | Une seule longue ligne | Coupé au plus près de la borne, sur une frontière de caractère | — |
| Outil natif local | `read_file` de `journal_serveur.log` | Inchangé (non borné) | — |
| Erreur d'outil | `Erreur : …` | Inchangé | — |
| Mode chat | Modèle cloud | Même borne, tokens estimés, `estimated: true`, « ≈ » dans l'interface | — |
| Borne invalide | `result_max_tokens` absent, non entier ou trop petit | Valeur par défaut 1 200 ; plancher 200 | — |
| Débordement par un résultat | Résultat d'outil = plus gros segment | Message : « Cause : un résultat d'outil … » avec pistes (question plus précise ; compression si la brique est disponible et éteinte ; vider la conversation), jamais « descriptions d'outils » | — |
| Débordement par la mémoire ou les skills | Mémoire globale ou skills chargés = plus gros | Cause nommée, piste adaptée (retirer des entrées ; vider la conversation pour décharger les skills) | — |

</intent-contract>

## Code Map

- `src/wavestack/tools/executor.py:95-162` -- `ToolExecutor.run` : émet `tool_started` puis `tool_ended{status, result, error_fr, duration_ms}` ; paramètre `apply=` existant (modèle pour un `bound=` appliqué au résultat réussi avant `tool_ended`).
- `src/wavestack/session/app_session.py` :
  - `_run_tool` (l.~5188) : chemin unique (tour, sous-agent, action forcée), appel `self._tool_executor.run(..., apply=self._apply_now)` ; `spec.network or spec.is_mcp` y est déjà testé.
  - `_count_tokens(text) -> (tokens, estimated)` (l.~3560) : tokenizer local ou estimation en mode chat, ne lève jamais.
  - `_transform_context` / `_compressible` / `_compress_one` : compression après l'exécution, donc après la borne.
  - `_OVERFLOW_CAUSES_FR` (l.~245), `_TOOL_CATALOG_FULL_FR` (l.~269), `_OVERFLOW_STRATEGIES_FR` (l.~301), `_emit_overflow` (l.~5687 : ne somme que les genres de `_OVERFLOW_CAUSES_FR`).
  - Disponibilité et état effectif de la brique `compression` (`_effective()`, raisons de disponibilité) pour la piste « allumez la compression ».
- `src/wavestack/tools/registry.py:16,44-68` -- `ToolSpec` (`source`, `network`, `is_mcp`) ; natifs `tools/native.py:113-128`, réseau `tools/network.py:150-165` (`fetch_page` garde sa coupe en caractères, l.145-147).
- `src/wavestack/config.py` -- `_int` (l.~440), `tool_max_calls`, `fetch_page_max_chars` (l.~477) : modèle pour `tool_result_max_tokens`.
- `wavestack.toml:103-111` -- section `[tools]` commentée en français.
- `src/wavestack/trace/catalog.py` -- `ToolEndedPayload` (l.~376).
- `src/wavestack/web/static/app.js` -- `toolBody` (l.~2748, « Résultat » l.~2771), résumé de la ligne d'outil (l.~3293), `overflowCard` (l.~2805).
- `content/scenarios.yaml` -- `data_flows` (l.~300 : briques `short_memory, system_prompt, tools`, MCP activé à la main), `mcp_full`, `mcp_lazy`, `iam`, `sovereignty`.
- `tests/test_program.py` -- `CHARS_PER_TOKEN = 4`, `SAFETY = 1.3` (l.~52), `_verdict` (l.~279), `test_every_scenario_fits_the_default_window_with_its_first_prompt` (l.~300 : session cloud `mistral`, aperçu `context_preview`). `VocabTokenizer(model_path)` (`models/engine.py`) ouvre un GGUF sans poids ; `WAVESTACK_TEST_GGUF` déjà lu par `tests/test_render_reference.py`.
- `tests/test_mcp.py`, `tests/test_tools.py`, `tests/test_compression.py` -- sessions et faux serveurs MCP / réseau à réutiliser.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- trois entrées du 2026-09-27 du lot B (résultats non bornés, message de débordement, test `fits`), à fermer.

## Tasks & Acceptance

**Execution:**
- `wavestack.toml`, `src/wavestack/config.py` -- `[tools] result_max_tokens = 1200` commenté (outils MCP et réseau, avant la compression) ; propriété `tool_result_max_tokens` (défaut 1 200, plancher 200).
- `src/wavestack/tools/executor.py` -- paramètre `bound` (appelable `texte -> (texte borné, infos | None)`) appliqué au seul résultat réussi, avant `tool_ended` ; `truncated` dans `tool_ended` quand il coupe.
- `src/wavestack/session/app_session.py` -- dans `_run_tool`, `bound` pour `spec.network or spec.is_mcp` (hors `delegate`) : compte avec `_count_tokens`, coupe au plus grand préfixe qui tient avec la mention (recherche par dichotomie sur les caractères), recule au dernier saut de ligne s'il est dans la seconde moitié du préfixe, ajoute « [Résultat tronqué par le harnais : {gardés} tokens sur {total}. Posez une question plus précise pour obtenir la suite.] ». `_emit_overflow` : somme de tous les genres de segments hors `template`, `user_message` gardant la priorité à égalité ; textes ajoutés pour `tool_result`, `global_memory`, `skill_catalog`/`skill_body`, `subagent_result` ; `tool_result` propose la compression seulement si la brique est disponible et éteinte.
- `src/wavestack/trace/catalog.py` -- `ToolEndedPayload.truncated: ToolResultTruncated | None` (`tokens`, `total_tokens`, `estimated`).
- `src/wavestack/web/static/app.js` -- `toolBody` : ligne « Résultat tronqué par le harnais : N tokens sur M » (« ≈ » si estimé) au-dessus du résultat ; « tronqué » dans le résumé de la ligne d'outil.
- `content/scenarios.yaml` -- `data_flows` en lazy loading (`mcp_lazy: true`) et description qui le dit : sans cela, la documentation complète de data.gouv plus un résultat borné dépasse encore la fenêtre (≈ 3 100 + 1 200 > 3 584).
- `tests/test_tool_result_bound.py` (nouveau) -- une ligne par cas de la matrice (MCP long, court, sans saut de ligne, `read_file` non borné, erreur non bornée, mode chat estimé, borne invalide), réinjection et `tool_ended` ; causes de débordement (`tool_result`, `global_memory`, skills) et piste compression conditionnelle.
- `tests/test_program.py` -- tokenizer réaliste : `VocabTokenizer(WAVESTACK_TEST_GGUF)` quand la variable est posée (compte du texte des segments de l'aperçu), sinon `[cloud] chars_per_token = 2` dans les valeurs de la session de test et facteur de sécurité recalibré (≈ 1,1) ; place du premier résultat borné (`used × sécurité + prompt + result_max_tokens ≤ usable`) pour les scénarios dont le premier prompt vise un serveur MCP public ou un outil réseau (`data_flows` avec les serveurs `local` et `datagouv` activés comme le dit sa description, `iam`, `sovereignty`, `network_tools`) ; `mcp_full` en reste exempté (son premier prompt vise le serveur local, écrit dans le test).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer les trois entrées du lot B, avec « à vérifier sur PC » pour les scénarios réels.

**Acceptance Criteria:**
- Given data.gouv qui renvoie ≈ 2 500 tokens, when le modèle l'appelle dans `mcp_lazy`, then le texte réinjecté fait au plus 1 200 tokens et Orchestration affiche la coupe.
- Given un tour qui déborde à cause d'un résultat d'outil, when `context_overflow` est émis, then son `message_fr` cite un résultat d'outil et jamais « les descriptions d'outils ».
- Given la suite de tests sans GGUF, when `test_every_scenario_fits…` tourne, then `mcp_full` est compté à plus de 2 800 tokens et `data_flows`, `iam` et `sovereignty` laissent la place d'un résultat borné.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 20 findings (constats des quatre couches, doublons regroupés avec leurs sources) — high 0, medium 3, low 12, false 2, maybe-false 3
- findings:
  - `[medium]` `[patch]` Mention de coupe adressée à l'humain (« Posez une question… ») et sans « suite » possible pour `fetch_page` (blind) — mention adressée au modèle.
  - `[medium]` `[patch]` Mode chat : ratio plafonné à 1 dans `_count_tokens`, un résultat « borné » peut dépasser 1 200 tokens réels (edge) — ratio non plafonné pour la borne, test.
  - `[medium]` `[patch]` Groupements `hook_injection`→message et `assistant_turn`→historique non testés ; H3 dominant renvoie à « raccourcissez le message » (verification-gap, edge) — cause propre à H3, deux tests.
  - `[low]` `[patch]` Texte `tool_result` au singulier alors qu'il somme tous les résultats, `read_file` compris (blind) — reformulé.
  - `[low]` `[patch]` Seconde boucle de raccourcissement jamais exercée (verification-gap) — test avec compteur simulé.
  - `[low]` `[patch]` Commentaire de `wavestack.toml` inexact sur la coupe (blind) — réécrit.
  - `[low]` `[patch]` `tool_result_max_tokens` hors du modèle `_int`, défaut répété (blind) — constante nommée.
  - `[low]` `[patch]` Ligne « Résultat tronqué » sans la raison (blind) — nom du réglage ajouté.
  - `[low]` `[patch]` Sous-agent, action forcée, MCP local et exclusion de `delegate` non testés (blind, intent) — tests ajoutés.
  - `[low]` `[patch]` Test `fits` en mode GGUF : `usable`/`overflow` de l'estimation, pas de `try/finally` (blind, edge) — verdict cohérent, fermeture garantie.
  - `[low]` `[patch]` Exemption de `mcp_full`/`mcp_lazy` justifiée par une réponse locale « petite » non mesurée (blind) — taille mesurée dans le test.
  - `[low]` `[patch]` `booted_session(values=…)` fusion superficielle (edge) — `_deep_merge`.
  - `[low]` `[defer]` Rendu de la coupe dans Orchestration non testé automatiquement (verification-gap) — pas de banc JS dans le dépôt ; vérification visuelle au test sur PC.
  - `[low]` `[reject]` Texte original perdu dans la trace (blind) — N3 demande une coupe visible, pas l'original ; ajout de surface sans demande.
  - `[low]` `[reject]` Cause nommée par genre de segment, pas par groupe de la jauge (intent) — les skills (catalogue + corps) regroupés donnent la bonne piste ; écart visuel mineur.
  - `[maybe-false]` `[defer]` Second prompt de `mcp_lazy` (après l'historique du premier tour) non couvert par `fits` (blind, edge, intent) — si vrai : medium ; ≈ 2 180 + 1 200 = 3 380 sur 3 584 d'après la mesure du PC ; se tranche sur le PC cible.
  - `[maybe-false]` `[reject]` La borne avant compression prive la démo Compression de ses gros résultats réseau (blind) — la démo Compression repose sur `read_file` (non borné) ; l'ordre est la décision N3 ; si vrai : low.
  - `[maybe-false]` `[reject]` `data_flows` en lazy loading empiète sur le lot H (intent) — sans ce réglage, le critère du lot B est inatteignable (3 100 + 1 200 > 3 584) ; décision consignée ; si vrai : low.
  - `[false]` `[reject]` Chemins sous-agent et action forcée non bornés (edge, claims) — ils passent par `_run_tool` (vérifié par la couche verification-gap).
  - `[false]` `[reject]` Exclusion de `delegate` inopérante (verification-gap) — redondante mais juste : `delegate` n'est ni réseau ni MCP.

## Design Notes

- Borne en tokens (N3) plutôt qu'en caractères : c'est ce que la jauge montre. La dichotomie coûte une quinzaine de tokenisations d'un texte de quelques dizaines de Ko, négligeable en local ; avec llama-server ou Ollama, ce sont des requêtes locales.
- `soc` déborde de 2 tokens sur `journal_serveur.log` (outil natif, non borné par choix) : le nouveau message nomme la bonne cause ; le scénario est revu au lot H.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert
- `node --check src/wavestack/web/static/app.js` -- expected: pas d'erreur

## Auto Run Result

Status: done

**Résumé.** Les résultats réussis des outils réseau et MCP (locaux compris) sont bornés à `[tools] result_max_tokens` (1 200 par défaut, N3) avant la compression, dans le tour, le sous-agent et les actions forcées : coupe près de la borne (au dernier saut de ligne s'il est dans la seconde moitié), mention adressée au modèle, champ `truncated` dans `tool_ended` et ligne « Résultat tronqué par le harnais : N tokens sur M » dans Orchestration. En mode chat, la borne tient compte du ratio réel du fournisseur. La cause d'un débordement vient de tous les genres de segments (résultats d'outils, sous-agent, mémoire, skills, H3 ajoutés) et ne cite plus à tort les descriptions d'outils ; la compression n'est proposée que si la brique est disponible et éteinte. Le test `fits` compte à 2 caractères par token (ou avec le vrai tokenizer via `WAVESTACK_TEST_GGUF`) et réserve la place du premier résultat borné. `data_flows` démarre en lazy loading (décision par défaut : sans elle, documentation complète + résultat borné dépassent la fenêtre).

**Fichiers.** `wavestack.toml`, `src/wavestack/config.py` (borne), `src/wavestack/tools/executor.py` (`bound`), `src/wavestack/session/app_session.py` (`_bound_result`, causes de débordement), `src/wavestack/trace/catalog.py` (`truncated`), `src/wavestack/web/static/app.js` (affichage), `content/scenarios.yaml` (`data_flows`), `tests/test_tool_result_bound.py` (nouveau), `tests/test_program.py`, `tests/test_tools.py`, `tests/test_compression.py`, `tests/fake_engine.py`, `deferred-work.md` (trois entrées fermées).

**Revue.** 12 patchs (3 medium, 9 low), 2 différés (rendu JS non testé ; second prompt de `mcp_lazy`, medium si vrai), 6 rejetés (voir le journal). `followup_review_recommended: false` : aucun high, les trois medium sont corrigés et testés.

**Vérification.** `ruff check`, `ruff format --check`, `node --check app.js` : OK ; `pytest -q` : 824 réussis, 4 sautés.

**Risques résiduels (à vérifier sur PC).** `mcp_lazy`, `data_flows`, `iam` et `sovereignty` jusqu'au bout avec le 2B ; second prompt de `sovereignty` (deux résultats bornés dans l'historique) ; `soc` déborde encore sur `journal_serveur.log` (outil natif non borné, lot H) avec la bonne cause désormais.
