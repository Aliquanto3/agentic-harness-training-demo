---
title: 'Scénarios métier et programme du palier 2'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_revision: '8158bf995a319fe70123da25c689843e461129c2'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/content/scenarios.yaml'
  - '{project-root}/_bmad-output/implementation-artifacts/deferred-work.md'
warnings: []
deferred:
  - summary: >-
      AD-9 sur le PC cible : instantané réel des serveurs publics (scripts/snapshot_mcp.py),
      puis jauge avant envoi de mcp_full (mémoire globale ajoutée), mcp_lazy, skills,
      subagent, compression, iam et sovereignty avec Qwen3.5.
    evidence: |-
      Estimation du test (facteur 1,3, fixtures plausibles) : mcp_full 2 228, subagent 1 513,
      skills 1 437, mcp_lazy 1 427 tokens sur 3 584. Entrée de deferred-work.md.
    location: >-
      content/scenarios.yaml, tests/fixtures/mcp_tools/
    severity: medium (unverified)
  - summary: >-
      IAM : les résultats de microsoft_docs_search (jusqu'à dix extraits) peuvent faire
      déborder la fenêtre avec un SLM local.
    evidence: |-
      Aucun réseau pendant la story ; la consigne prévoit le dépassement expliqué (NFR-8).
    location: >-
      content/scenarios.yaml (iam)
    severity: medium (unverified)
  - summary: >-
      NFR-1 : premier token des scénarios les plus chargés (mcp_full, subagent, skills,
      compression, rag_rerank, reasoning) à mesurer sur le poste de référence.
    evidence: |-
      Non mesurable sans le modèle réel ; liste et méthode dans deferred-work.md.
    location: >-
      content/scenarios.yaml
    severity: medium (unverified)
  - summary: >-
      SOC : garde-fou en validation humaine plutôt qu'en blocage, écarté (H5 réservé aux
      outils réseau par FR-27) ; variante V2.
    evidence: |-
      hooks.ask exige spec.network et un aperçu de requête ; voir la section « Revue
      indépendante ».
    location: >-
      src/wavestack/hooks.py (ask)
    severity: low
  - summary: >-
      IAM et Souveraineté : pas de repli hors ligne enregistré, seulement l'échec expliqué.
    evidence: |-
      Les outils réseau n'en ont pas non plus ; il faudrait un faux serveur MCP étiqueté.
    location: >-
      content/scenarios.yaml (iam, sovereignty)
    severity: low
  - summary: >-
      AD-9 : avertissement en direct quand tools/list s'écarte de l'instantané, non réalisé.
    evidence: |-
      Aucun instantané réel encore ; à brancher dans _mcp_connect avec un seuil [mcp].
    location: >-
      src/wavestack/session/app_session.py (_mcp_connect)
    severity: low
---

<intent-contract>

## Intent

**Problem:** Les modules du palier 2 (Raisonnement, Mémoire globale, Sous-agent, RAG, Compression) ont été ajoutés en fin de programme par convention provisoire (stories 13 à 20) : le programme ne suit pas l'ordre de FR-38, et ses premiers scénarios de module ne portent pas les briques des modules précédents (CAP-40). Aucun scénario métier n'existe (FR-40, CAP-42), alors que la V1 doit en livrer au moins trois.

**Approach:** Réordonner `content/scenarios.yaml` selon FR-38 en six modules de 45 à 60 min, rendre cumulatifs les premiers scénarios de chaque module (exceptions écrites en tête du fichier, justifiées par AD-9), puis ajouter trois scénarios métier (SOC par H1/H2, IAM par le MCP Microsoft Learn, Souveraineté par le MCP data.gouv.fr) listés après le scénario transverse. Vérifier par pytest l'ordre, le cumul et l'adéquation à la fenêtre de chaque scénario, et par le parcours E2E l'ordre affiché et les trois scénarios métier.

## Boundaries & Constraints

**Always:**
- Ordre de FR-38 : LLM nu, raisonnement, mémoire courte, prompt système, mémoire globale, outils, RAG (simple puis reranking), MCP (documentation complète puis lazy loading), skills, hooks, sous-agent, compression.
- Convention cumulative (en-tête de `content/scenarios.yaml`) : le premier scénario d'un module active les briques de tous les modules précédents, sauf exceptions écrites en tête du fichier et dans la consigne du scénario : le raisonnement n'est pas reconduit après le module 1 (réserve de 1 536 tokens, NFR-1) ; `mcp_full` laisse le RAG éteint (documentation complète déjà près de la limite : 3 018 / 3 584 tokens mesurés sur le PC cible, story 10b).
- Chaque scénario tient dans la fenêtre par défaut (4 096 tokens, réserve comprise) avec son premier prompt, compté comme les tests existants (estimation à 4 caractères par token d'un modèle cloud, extraits RAG à leur maximum, serveur MCP local réel ; serveurs publics injoignables).
- Scénarios métier : contenu seulement, au schéma pydantic de la story 10 ; fictifs et non confidentiels (NFR-11) ; listés dans `transverse`, après « Où vont mes données ? » (EXPERIENCE.md, `scenario-picker`) ; chacun fixe ses briques et ses hooks.
- Textes en français, code en anglais ; `uv`, `ruff`, `pytest`.
- Parcours E2E : chaque nouveau scénario se lance seul (`--only`).

**Never:**
- Nouveau champ de scénario, nouvelle brique, nouveau hook ou nouvel outil.
- Toucher au code de la story 16 (reranking) au-delà de la configuration du scénario `rag_rerank` et du test qui la vérifie ; ses prompts restent les siens.
- Un scénario métier qui exige une clé d'API ou un modèle cloud (NFR-4).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Programme | Lancement de WaveStack | Sélecteur : 6 modules dans l'ordre de FR-38, puis « Transverses et métier » : `data_flows`, `soc`, `iam`, `sovereignty` | Fichier invalide : `harness_error`, programme vide (inchangé) |
| Début de module | Lancer le premier scénario du module N | Briques des modules 1 à N-1 actives, sauf les exceptions écrites | — |
| SOC | `soc`, prompt 1 puis prompt 2 | `read_file` sur `alertes_siem.log` journalisé par H2 ; lecture de `confidentiel/comptes_privilegies.txt` bloquée par H1 ; journal d'audit ouvert depuis le schéma | Le modèle n'appelle pas l'outil : forçage `read_file` (préréglage existant) |
| IAM hors ligne | `iam` sans réseau | Microsoft Learn dessiné indisponible avec sa raison ; le tour aboutit sans outil | Décocher puis recocher le serveur pour réessayer |
| Souveraineté hors ligne | `sovereignty` sans réseau | data.gouv.fr dessiné indisponible, son arête franchit la frontière du poste ; le tour aboutit | Idem |

</intent-contract>

## Code Map

- `content/scenarios.yaml` -- programme, en-tête de la convention cumulative, 20 scénarios après la story.
- `src/wavestack/scenarios.py` -- schéma pydantic (inchangé) : `Scenario`, `Module` (30 à 60 min), `transverse`.
- `src/wavestack/session/app_session.py:3979` `launch_scenario` / `_apply_launch_config:632` -- valeurs de lancement : outils hors ligne, serveur MCP `local`, hooks h1 h2 h3 ; `_emit_preview:2865` compte les extraits RAG à leur maximum (AD-9).
- `src/wavestack/web/static/app.js:2224` -- libellé du groupe « Transverse » du sélecteur.
- `src/wavestack/hooks.py:38` -- H1 bloque tout chemin sous `confidentiel/`.
- `content/demo_files/` -- fichiers lus par `read_file` (nouveau : `alertes_siem.log`, `confidentiel/comptes_privilegies.txt`).
- `tests/test_scenarios.py` -- compte et ordre du programme ; `tests/test_reasoning.py:530`, `tests/test_global_memory.py:453`, `tests/test_rag.py:~505`, `tests/test_compression.py:702` -- briques attendues des scénarios déplacés.
- `tests/test_mcp.py` -- `McpWeb`, boucle `loop`, serveur MCP local réel ; `tests/test_rag.py` -- `rag_values`, `build`, `place_model`, `Embedders` ; `tests/test_cloud.py` -- `Provider`, `SENTINEL`.
- `tools/e2e/run_e2e.py` -- `SCENARIOS`, `Run.launch`, `s_hooks`, `s_data_flows` (modèles des nouveaux scénarios) ; `tools/e2e/fake_openai.py` `_plan`/`_final_text` -- déclencheurs du faux modèle ; `tools/e2e/README.md` -- table des déclencheurs.

## Tasks & Acceptance

**Execution:**
- `content/scenarios.yaml` -- réordonner en 6 modules (1 « Du LLM nu au harnais » 60 min : bare_llm, reasoning, short_memory, system_prompt, global_memory ; 2 « Outils » 45 ; 3 « RAG » 45 ; 4 « MCP » 45 ; 5 « Skills et hooks » 60 ; 6 « Sous-agent et compression » 60), rendre cumulatifs native_tools, rag, mcp_full, skills, subagent (et alignés network_tools, rag_rerank, mcp_lazy, compression), écrire les exceptions en tête, réécrire les consignes qui citaient l'ancien ordre ; ajouter `soc`, `iam`, `sovereignty` dans `transverse`.
- `content/demo_files/alertes_siem.log`, `content/demo_files/confidentiel/comptes_privilegies.txt` -- fichiers fictifs du scénario SOC.
- `src/wavestack/web/static/app.js` -- groupe « Transverses et métier ».
- `tests/test_scenarios.py` -- ordre de FR-38, compte, cumul avec exceptions, adéquation à la fenêtre de chaque scénario, configuration des trois scénarios métier ; mettre à jour les tests des autres fichiers qui figeaient l'ancien ordre ou l'ancienne configuration.
- `tools/e2e/fake_openai.py`, `tools/e2e/run_e2e.py`, `tools/e2e/README.md` -- déclencheurs SOC/IAM/Souveraineté ; scénarios E2E `programme`, `soc`, `iam`, `sovereignty` ; capture 26.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- clore les reports de placement (stories 13, 14, 15, 19, 20) ; consigner les tests réseau et de fenêtre pour le PC cible.

**Acceptance Criteria:**
- Given WaveStack lancé, when on ouvre le sélecteur de scénario, then les modules suivent l'ordre de FR-38 et les scénarios métier suivent « Où vont mes données ? ».
- Given un module N > 1, when on lance son premier scénario, then les briques des modules précédents sont voulues, hors exceptions écrites en tête de `content/scenarios.yaml`.
- Given chaque scénario fourni, when on le lance, then l'aperçu de la jauge ne déborde pas et laisse la place du premier prompt.
- Given le scénario SOC, when on envoie ses deux prompts, then la lecture du journal d'alertes est journalisée par H2 et la lecture du fichier confidentiel est bloquée par H1, visible dans le journal d'audit.
- Given aucun réseau, when on lance IAM ou Souveraineté, then le serveur public est dessiné indisponible avec sa raison et un tour aboutit sans plantage.

## Spec Change Log

### 2026-09-26 — Revue indépendante (trois relecteurs, triage du coordinateur)

- **Déclencheur.** Triage de la revue indépendante (contenu pédagogique, cas limites, écarts de vérification). Le coordinateur a demandé d'appliquer tous les points, sauf ceux qui se révèlent faux après vérification.
- **Amendé hors du contrat d'intention.** Deux champs facultatifs et rétrocompatibles s'ajoutent au schéma des scénarios, ce que la section Never du contrat excluait (« Nouveau champ de scénario ») : la revue l'a demandé explicitement.
  - `restore_memory` : lancer le scénario restaure la mémoire globale de démonstration.
  - `expects_overflow` : dépassement volontaire, au sens d'AD-9.

  S'y ajoutent deux préréglages de `read_file` (SOC) et le script `scripts/snapshot_mcp.py`.
- **État évité.**
  - Un module démarré directement avec une mémoire pleine, qui déborderait la fenêtre.
  - Un test d'adéquation aveugle aux outils des serveurs publics.
  - Un scénario SOC qui dicte le fichier confidentiel au modèle.
  - Un scénario Souveraineté qui assimile « service de l'État » à souveraineté.
- **KEEP.**
  - L'ordre de FR-38 et ses deux exceptions au cumul (raisonnement ; RAG dans `mcp_full`).
  - Les scénarios métier dans `transverse`, groupe « Transverses et métier ».
  - Le test d'adéquation par estimation, tel que le lance `pytest`.

## Revue indépendante : suite donnée à chaque point

| Point de la revue | Suite |
|---|---|
| AD-9 : script d'instantané des outils MCP publics | `scripts/snapshot_mcp.py` écrit `content/mcp_snapshots/{server_id}.json` (à lancer sur le PC cible) ; testé contre des serveurs simulés, en réussite et en échec. |
| AD-9 : fixtures `tools/list` servies en ligne | `tests/fixtures/mcp_tools/{datagouv,mslearn}.json`, marquées plausibles et à régénérer. Pour data.gouv.fr : noms et paramètres du serveur public, descriptions étoffées pour peser comme la mesure de la story 10b. Le test d'adéquation lit l'instantané en priorité et affiche sa source. |
| « Ne pas inventer de schémas » (intention) contre « schémas plausibles » (cas limites) | Tranché : rien d'inventé dans `content/`, où ne va que l'instantané réel. Les schémas plausibles restent dans `tests/fixtures/`, étiquetés. |
| `expects_overflow` pour `mcp_full` avec data.gouv.fr | **Champ ajouté et honoré par le test, mais non posé sur `mcp_full`** : la story 10b a mesuré sur le PC cible 3 018 / 3 584 tokens sans dépassement ; déclarer un dépassement contredirait cette mesure. À poser si le PC cible déborde avec la mémoire globale (report). |
| Test d'adéquation : facteur de sécurité ou marge | Facteur de 1,3 sur l'aperçu, marge affichée par `pytest -s`. |
| Cumul : sous-options, variantes alignées, raisonnement vraiment éteint | Testés par règles : hooks déjà montrés restent actifs ; MCP en lazy loading après son module ; variantes (`network_tools`, `rag_rerank`, `mcp_lazy`) aux briques et sous-options de leur premier scénario ; aucune brique `reasoning` hors du module 1 ; E2E : brique Raisonnement non voulue. |
| « Sans modifier le code » | Tests fondés sur des règles (ordre FR-38, scénarios métier repérés par leur titre « Métier … », parcours E2E lisant `content/scenarios.yaml`) ; le README le dit. |
| Mémoire globale portée par tous les modules | Choix : le premier scénario de chaque module et le scénario Mémoire globale restaurent la mémoire de démonstration (`restore_memory`) ; les autres n'y touchent pas. Testé ; EXPERIENCE.md disait « la mémoire globale n'est pas touchée » (`[ASSUMPTION]`), écart assumé. `mcp_full` garde donc la mémoire globale (démonstration seulement). |
| SOC : préréglages des deux fichiers, consigne qui les nomme | Préréglages « Alertes SIEM (SOC) » et « Comptes à privilèges (SOC, confidentiel) » ; la consigne les nomme ; testé. |
| SOC : chronologie, incident, MITRE ATT&CK | Premier prompt réécrit ; réponse attendue au README. |
| SOC : le modèle cherche le fichier, pas l'utilisateur | Second prompt sans nom de fichier (« en t'aidant des fichiers disponibles ») ; test pytest et E2E : liste du dossier, puis blocage. |
| SOC : H5 (validation humaine) plutôt que blocage | **Non appliqué, faux après vérification** : H5 ne s'applique qu'aux outils réseau (FR-27, `hooks.ask` exige `spec.network` et un aperçu de requête) ; l'étendre à un fichier local change le contrat d'un hook du palier 1. La leçon « moindre privilège, puis escalade » passe par la consigne, la réponse du faux modèle et le corrigé. Report V2. |
| SOC : fuseau, fenêtre de maintenance, nombre de lignes | Heures en UTC (suffixe Z, en-tête) ; début et fin de fenêtre, alertes en sourdine, point pédagogique ; en-tête « 10 événements », vérifié par test. |
| Souveraineté refondue | Deux serveurs (data.gouv.fr, Microsoft Learn) en lazy loading ; juridictions (Cloud Act), hébergement et SecNumCloud à vérifier flux par flux, ce que révèle la requête ; « un service public n'est pas souverain par nature ». |
| `mcp_full` aux mesures du PC cible | Ajouté au report AD-9 (mémoire globale ajoutée depuis la 10b). |
| IAM et Souveraineté hors ligne / proxy | Consignes et README : proxy à ouvrir vers les deux hôtes. **Repli enregistré non réalisé** : les outils réseau n'en ont pas non plus (`fetch_page` interroge ou échoue, vérifié), et il faudrait un faux serveur MCP étiqueté. Report. |
| Scénarios métier : durée, corrigé, message clé ; total du programme | Durée et « À retenir » dans chaque consigne (NIS2/DORA pour le SOC, réponse sourcée pour l'IAM) ; corrigé formateur et total (5 h 15) au README. |
| Module 1 : remember | Phrase ajoutée (« un outil propre au harnais, détaillé au module 2 »). |
| Cohérences (19 → 20, practice, « en pratique ») | Corrigées (Code Map ; « practice » partout, README reformulé). |
| Faux modèle : déclencheurs, seconds prompts, lazy, `[]` prématuré, sous-dossiers | Appels comparés avec leurs arguments ; recherche MCP en lazy (`load_tool_doc` d'abord) ; un serveur absent laisse passer les déclencheurs suivants ; chemins confidentiels avec sous-dossiers ; les prompts des scénarios métier sont lus dans le YAML et tous testés. |
| E2E `s_soc` : attendre le texte de l'audit, garde si `fake_calls()` vide ; E2E `programme` : attente des optgroups | Faits. |
| `tests/test_program.py` : `started`/`ended` initialisés | Fait. |
| Courses du rejeu du flux (`local_server`, `relaunch`) | Hors de cette story (autre agent) ; report clos avec la cause. |

## Review Triage Log

### 2026-09-26 — Review pass

Revue brève faite par l'agent d'implémentation lui-même (aucun outil de sous-agent dans cette exécution, consigne de l'appelant) : les quatre angles (chasse aveugle, cas limites, écarts de vérification, alignement sur l'intention) passés en revue sur le diff ; une revue indépendante doit suivre.

- verdicts: 9 findings — high 0, medium 0, low 5, false 1, maybe-false 3
- findings:
  - `[low]` `[patch]` La capture 26 montrait le haut du journal d'audit, pas les lignes du scénario SOC (le journal cumule tout le parcours) — le parcours fait défiler la boîte jusqu'en bas avant la capture.
  - `[maybe-false]` `[defer]` « Lazy loading » avec le RAG rallumé et data.gouv.fr connecté pourrait approcher la limite sur le PC cible — mesure impossible sans réseau ni Qwen3.5 ; à relever (jauge avant envoi), entrée de deferred-work.md et `deferred`.
  - `[maybe-false]` `[defer]` IAM : les résultats de Microsoft Learn peuvent déborder la fenêtre — à tester avec le réseau ; la consigne prévoit le dépassement expliqué.
  - `[maybe-false]` `[defer]` NFR-1 : le RAG porté par les modules 5 et 6 allonge les tours — à mesurer sur le poste de référence.
  - `[low]` `[reject]` Les exceptions au cumul vivent à la fois dans l'en-tête YAML et dans `tests/test_program.py` (`NEVER_CARRIED`, `LEFT_OFF`) — voulu : le test est la garde, et il vérifie aussi que chaque consigne nomme l'exception ; une nouvelle exception doit passer par lui.
  - `[low]` `[reject]` La consigne de « Compression » dit « les briques du scénario Sous-agent » alors que ses hooks actifs diffèrent (H3 éteint) — la phrase parle des briques, exacte ; ajouter les sous-options alourdirait la consigne.
  - `[low]` `[reject]` Conflit possible avec les correctifs parallèles de la story 16 sur `rag_rerank` — seules les lignes de briques et d'options changent, pas les prompts ; conflit de fusion trivial le cas échéant.
  - `[false]` `[reject]` Intention « contenu seulement » contredite par la modification de `app.js` — le schéma des scénarios est inchangé ; seul le libellé du groupe devient « Transverses et métier » (EXPERIENCE.md), hypothèse H1.
  - `[low]` `[defer]` Parcours E2E complet instable en fin de séance (`local_server`, `relaunch`, deux parcours sur quatre), jamais reproduit sur les scénarios lancés seuls — scénarios non touchés, journal plus long ; consigné dans deferred-work.md et `deferred`.

### 2026-09-26 — Revue indépendante (trois relecteurs)

Triage fait par le coordinateur (`notes-21.md`) : 26 points appliqués, 3 non appliqués ou appliqués en partie après vérification. H5 ne s'applique qu'aux outils réseau. `expects_overflow` n'est pas posé sur `mcp_full`, que la story 10b a mesuré sans dépassement. Aucun repli hors ligne enregistré, les outils réseau n'en ayant pas non plus. Le détail de chaque point est dans la section « Revue indépendante : suite donnée à chaque point » ; les reports sont dans `deferred` et deferred-work.md.

## Auto Run Result

**Résumé.** Programme réordonné selon FR-38 en six modules (Du LLM nu au harnais 60 min, Outils 45, RAG 45, MCP 45, Skills et hooks 60, Sous-agent et compression 60) ; premiers scénarios de module cumulatifs, avec deux exceptions écrites en tête de `content/scenarios.yaml` et dans les consignes (raisonnement jamais reconduit ; RAG éteint dans « MCP en documentation complète ») ; trois scénarios métier après « Où vont mes données ? » : `soc` (H1 + H2, fichiers fictifs), `iam` (Microsoft Learn, documentation complète), `sovereignty` (data.gouv.fr, lazy loading).

**Fichiers.**
- `content/scenarios.yaml` : programme, convention et exceptions, consignes réécrites, trois scénarios métier.
- `content/demo_files/alertes_siem.log`, `content/demo_files/confidentiel/comptes_privilegies.txt` : fichiers fictifs du SOC.
- `src/wavestack/web/static/app.js` : groupe « Transverses et métier » du sélecteur.
- `tests/test_program.py` (nouveau) : ordre FR-38, cumul, adéquation à la fenêtre de chaque scénario (estimation, RAG au maximum, serveur MCP local réel), SOC de bout en bout, serveurs publics indisponibles.
- `tests/test_scenarios.py`, `test_reasoning.py`, `test_global_memory.py`, `test_rag.py`, `test_compression.py` : nouvel ordre et nouvelles briques ; `tests/test_e2e_fake_openai.py` : déclencheurs métier.
- `tools/e2e/run_e2e.py`, `fake_openai.py`, `README.md` : scénarios `programme`, `soc`, `iam`, `sovereignty`, capture 26.
- `README.md` : section « Programme de formation ».
- `_bmad-output/implementation-artifacts/deferred-work.md` : placement provisoire clos ; tests PC cible et instabilité E2E consignés.

**Revue.** 1 correctif (capture 26), 4 reports (fenêtre et latence sur PC cible, résultats Microsoft Learn, instabilité E2E), 4 rejets motivés dans le journal de tri. Revue faite par l'agent lui-même (pas d'outil de sous-agent) ; une revue indépendante doit suivre. Nouvelle revue recommandée : non (aucun correctif high ni medium).

**Vérification.** `uv lock --check --offline` OK ; `ruff check` et `ruff format --check` OK ; `pytest -q` : 742 passés, 4 sautés (Headroom installé) ; `node --check` OK ; E2E `--only programme soc iam sovereignty` : 31/31 ; E2E complet : 337 vérifications, 0 échec (quatrième parcours ; deux parcours antérieurs avec une instabilité en fin de séance, voir report).

**Risques résiduels.** Adéquation réelle à la fenêtre et latence avec Qwen3.5 ; comportement réel de Microsoft Learn et data.gouv.fr (aucun réseau ici) ; conflit de fusion possible avec les correctifs parallèles de la story 16 sur `rag_rerank` (lignes de briques seulement).

## Design Notes

- Placement des scénarios métier : `transverse` plutôt qu'un nouveau champ `business`, pour rester « contenu seulement » ; seul le libellé du groupe change (« Transverses et métier »), ce qui répond à EXPERIENCE.md (« puis les scénarios transverses et métier »).
- Exceptions au cumul, par AD-9 : le raisonnement retire 1 024 tokens utiles et allonge chaque tour ; le RAG ajoute ses trois plus longs extraits (≈ 530 tokens estimés) à une documentation complète déjà à 3 018 / 3 584 sur le PC cible. `mcp_lazy`, qui suit, rallume le RAG : la place libérée par le lazy loading devient visible.
- IAM en documentation complète (trois outils Microsoft Learn, AD-9 « la documentation complète s'y illustre avec Microsoft Learn »), briques minimales pour laisser la place aux résultats de recherche ; Souveraineté en lazy loading (AD-9).

## Verification

**Commands:**
- `uv lock --check --offline` -- expected: lockfile à jour.
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q` -- expected: suite complète verte.
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur.
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 échec ; puis `--only programme soc iam sovereignty`.

## Hypothèses à valider

- H1 — Scénarios métier listés dans `transverse` (groupe renommé « Transverses et métier »), hors modules : ils ne suivent pas la convention cumulative et fixent une configuration minimale autour de leur brique.
- H2 — Le raisonnement n'est reconduit dans aucun module après le module 1 ; `mcp_full` laisse le RAG éteint (AD-9). Exceptions écrites en tête de `content/scenarios.yaml` et dans les consignes.
- H3 — Le module 6 regroupe Sous-agent et Compression (60 min) : la compression, second scénario du module, n'a pas à activer le sous-agent.
- H4 — Adéquation à la fenêtre vérifiée par estimation (4 caractères par token, facteur 1,3), avec des fixtures plausibles des serveurs MCP publics tant que `scripts/snapshot_mcp.py` n'a pas été lancé sur le PC cible : à mesurer avec Qwen3.5 et le réseau.
- H5 (revue indépendante) — Le premier scénario de chaque module, et le scénario Mémoire globale, restaurent la mémoire globale de démonstration (`restore_memory`) ; EXPERIENCE.md supposait la mémoire intouchée au lancement d'un scénario.
- H6 (revue indépendante) — Le garde-fou du SOC reste un blocage H1 ; H5 reste réservé aux outils réseau (FR-27).
- H7 (revue indépendante) — `expects_overflow` existe mais n'est posé sur aucun scénario : `mcp_full` tenait sur le PC cible (story 10b).
