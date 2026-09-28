---
title: 'Lot H : scénarios et consignes du palier 2'
type: 'bugfix'
created: '2026-09-28'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/_bmad-output/implementation-artifacts/resultats-test-pc-palier-2-2026-09-27.md'
  - '{project-root}/_bmad-output/implementation-artifacts/retours-recette-palier-2-2026-09-28.md'
  - '{project-root}/tools/e2e/README.md'
warnings:
  - oversized
deferred: []
---

<intent-contract>

## Intent

**Problem:** Sur le PC cible, avec Qwen3.5-2B, plusieurs scénarios ne montrent pas l'effet voulu (tests du 2026-09-27 et recette du 2026-09-28). Sous-agent avec RAG : chaque quiz relit tout le contexte (87 à 114 s) et le modèle redélègue à tort (D5). Extraits RAG hors sujet dans `mcp_lazy`, `skills` et `compression` (H1). Aucun appel d'outil dans `mcp_lazy` ni `iam` (sens de MCP inventé). `load_tool_doc` appelé pour un skill, `load_skill` jamais appelé (H2, M5). `sovereignty` sans recherche (H5). SOC : `alerts_siem.log` demandé, et aucune escalade après le blocage de H1 (D6). Compression éteinte : le journal n'est pas lu (H4). « Où vont mes données ? » part sans la brique MCP, avec un lazy loading qui semble actif (X1).

**Approach:** Réviser le contenu seulement, au schéma des scénarios (AD-19) : configuration, prompts et consignes dans `content/scenarios.yaml`, textes des méta-outils et un préréglage d'appel forcé. Pour un petit modèle, les prompts nomment l'outil ou le skill attendu, et les consignes proposent l'action forcée de secours. Le RAG, montré au module 3, n'est reconduit dans aucun module suivant (nouvelle exception au cumul CAP-40, comme le raisonnement). Tests, parcours E2E et documents suivent.

## Boundaries & Constraints

**Always:**
- Rester dans le contenu (`content/*.yaml`) ; code touché : tests, `tools/e2e/run_e2e.py` et, seulement si un déclencheur ne correspond plus, `tools/e2e/fake_openai.py`.
- Garder le programme cumulatif (CAP-40) et tenir ses exceptions à jour à trois endroits : en-tête de `scenarios.yaml`, constantes de `tests/test_program.py`, README.
- Chaque scénario tient dans la fenêtre de 4 096 tokens avec son premier prompt (`test_every_scenario_fits_the_default_window_with_its_first_prompt`). La story 26 (fenêtre réglable) garde ce défaut ; `mcp_full` n'a qu'environ 530 tokens de marge : son prompt reste sous 120 caractères.
- Consignes et prompts en français. Une consigne qui cite un bouton, un préréglage ou un skill utilise son libellé exact.
- Aucun vrai modèle dans le conteneur : doublures du dépôt (faux moteur, faux fournisseur `fake_openai.py`, faux serveurs MCP). Aucune dépendance nouvelle. `uv`, jamais pip.
- Aucune story livrée cassée (pytest complet vert). Fusionner avec les modifications concurrentes de `run_e2e.py` (stories 23, 32, 34…), en particulier les vérifications de la story 23 dans `s_data_flows`.

**Never:**
- Aucun changement du harnais : ni message de blocage de H1 (`hooks.guard`), ni erreur de `_load_tool_doc`, ni seuil de score RAG, ni appel forcé d'un outil MCP (refusé par `arm` depuis le 2026-09-25).
- Pas de troisième prompt SOC (tests et E2E attendent deux prompts).
- Hors périmètre : guide de test et cahier de recette (story 28), boutons « Forcer » actifs quand la brique est éteinte (différé de la story 22), relecture après `load_tool_doc`, préremplissage du premier tour, raisonnement qui va jusqu'au budget.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `mcp_full`, `mcp_lazy`, `skills`, `subagent`, `compression` | Lancement | Brique `rag` non voulue ; la consigne le dit (« sauf le raisonnement et le RAG » ou « ni le RAG ») | — |
| `data_flows` | Lancement | Briques `tools` et `mcp`, serveurs `local` et `datagouv`, lazy loading ; aucune activation à la main | Sans réseau : data.gouv.fr dessiné indisponible avec sa raison, la consigne le dit |
| `skills` | Prompt 1 | Nomme `meeting_minutes` et `load_skill` ; consigne : « Déclencher le skill » sur « Compte rendu de réunion » en secours | — |
| `mcp_full`, `mcp_lazy` | Prompt 1 | Contient « veut dire MCP » et demande l'outil du glossaire WaveStack | — |
| `iam`, `sovereignty` | Prompts | Nomment `mslearn__microsoft_docs_search` / `datagouv__search_datasets` (lazy : « charge la documentation de … puis ») | Serveur injoignable : tour sans outil, inchangé |
| `soc` | Prompts 1 et 2 | 1 : `alertes_siem.log` donné comme nom exact ; 2 : « fichiers disponibles », aucun `confidentiel/`, consigne de ne pas contourner un refus | Consigne : si le modèle n'escalade pas, le formateur conclut |
| `compression` | Prompt 1, brique éteinte | Demande d'appeler `read_file` sur `journal_serveur.log` ; consigne : préréglage « Journal de sauvegarde (compression) » en secours | — |

</intent-contract>

## Code Map

- `content/scenarios.yaml` -- en-tête (règles du programme et exceptions AD-9 : raisonnement, « MCP en documentation complète » sans RAG, `mcp_lazy` qui le rallume) ; scénarios `mcp_full`, `mcp_lazy`, `skills`, `subagent`, `compression`, `data_flows`, `soc`, `iam`, `sovereignty`. Seul fichier de configuration des scénarios, validé par `wavestack.scenarios.Scenario` (`extra="forbid"` : aucun champ nouveau sans code).
- `content/tools.yaml` -- `tools.read_file.presets` : préréglages SOC (story 21), à imiter pour le journal de la compression.
- `content/mcp.yaml` -- `load_tool_doc.intro` (description du méta-outil lue par le modèle, suivie d'une ligne par outil chargeable).
- `content/skills.yaml` -- `catalog_intro` (doit commencer par « Skills disponibles. », `tests/test_skills.py`), `load_skill.description`.
- `content/skills/meeting_minutes/SKILL.md` -- `name: meeting_minutes`, `label_fr: Compte rendu de réunion`.
- `content/subagent.yaml` -- consulté seulement : `delegate` et préréglages inchangés.
- `src/wavestack/tools/registry.py` -- nom vu par le modèle d'un outil MCP : `{server_id}__{tool}` (`datagouv__search_datasets`, `mslearn__microsoft_docs_search`, `local__define_term`) ; outils des instantanés dans `content/mcp_snapshots/*.json`.
- `src/wavestack/session/app_session.py` -- `arm` (kinds `tool`, `skill`, `tool_doc`, `memory`, `delegate` ; un outil MCP ne peut pas être forcé), `_load_tool_doc`, `_load_skill` : lus, pas modifiés.
- `tests/test_program.py` -- `NEVER_CARRIED`, `LEFT_OFF`, `VARIANTS`, `BY_HAND`, `FIRST_RESULT_ROOM`, `LOCAL_FIRST` ; tests `test_first_scenario_of_each_module_has_the_previous_modules_bricks`, `test_reasoning_stays_off_after_module_1_and_variants_keep_their_bricks`, `test_business_scenarios_fix_their_bricks_and_hooks`, `test_soc_presets_force_the_two_files`, `test_every_scenario_fits_the_default_window_with_its_first_prompt` (branche `BY_HAND`), `test_business_mcp_servers_are_drawn_unavailable_with_their_reason_offline` (boucle `iam`, `sovereignty`).
- `tests/test_scenarios.py` -- `test_real_content_loads_and_every_scenario_launches` (briques voulues = briques déclarées) : générique, à garder vert.
- `tools/e2e/run_e2e.py` -- `s_programme` (module 5 lancé directement, briques des modules 1 à 4 moins `reasoning`, texte « sauf le raisonnement et le RAG » de `mcp_full`), `s_mcp_lazy` (prompts écrits en dur), `s_skills` (prompt en dur), `s_subagent`, `s_compression` (`COMPRESSION_QUESTION`, `COMPRESSION_SECOND`, contrôle « extraits RAG candidats, prose inchangée »), `s_data_flows` (active MCP et data.gouv.fr à la main), `s_soc`, `s_iam`, `s_sovereignty`, aides `_prompts`, `_public_server_offline`, `_enabled_servers`.
- `tools/e2e/fake_openai.py` -- `_plan` : déclencheurs par mot-clé (« veut dire » + « mcp », « compte rendu », « journal_serveur », « alertes_siem », « fichiers disponibles », « entra id », « data.gouv », « qualité de l'air ») ; `_final_text`. Les nouveaux prompts doivent garder ces mots-clés.
- `tools/e2e/README.md` -- sections « Programme et scénarios métier (story 21) », compression, table des déclencheurs du faux fournisseur.
- `README.md` -- paragraphe des deux exceptions au cumul ; tableau des scénarios métier (SOC : escalade).
- `_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md` -- « Flow 4 — Où vont mes données ? » (activation pas à pas).
- `_bmad-output/specs/spec-agentic-harness-training-demo/user-journeys.md` -- UJ-4 (« active successivement »).
- `_bmad-output/implementation-artifacts/deferred-work.md` -- entrées du lot H (sources stories 19 et 21 : RAG hors sujet, sous-agent avec RAG, comportement du 2B).

## Tasks & Acceptance

**Execution:**
1. `content/scenarios.yaml` -- en-tête : remplacer l'exception « MCP en documentation complète laisse le RAG éteint… Lazy loading le rallume » par « le RAG, montré au module 3, n'est reconduit dans aucun module suivant : ses extraits sur Exemplia sont hors sujet dans les démonstrations suivantes, trompent le petit modèle et forcent la relecture du contexte à chaque tour (D5) ». Ajouter une règle : pour un petit modèle, les prompts nomment l'outil ou le skill attendu, et la consigne donne l'action forcée de secours -- tenir les exceptions à jour.
2. `content/scenarios.yaml` -- retirer `rag` de `mcp_lazy`, `skills`, `subagent` et `compression`. Consignes : `mcp_full` garde « sauf le raisonnement et le RAG » (sans « au point de pouvoir rallumer le RAG ») ; `mcp_lazy` dit que la place gagnée pourrait accueillir le RAG, laissé éteint parce que ses extraits n'aident pas ici ; `skills` et `subagent` : « sans le raisonnement ni le RAG » ; `compression` : phrase sur la prose reformulée sans les extraits RAG (« un texte sans redondance passe tel quel ») -- points 1 et 8.
3. `content/scenarios.yaml` -- `data_flows` : `bricks: [short_memory, system_prompt, tools, mcp]`, `mcp_servers: [local, datagouv]`, `mcp_lazy: true`. Consigne réécrite : tout est actif au lancement ; lire le schéma ; décocher puis recocher data.gouv.fr pour voir apparaître le flux qui franchit la frontière ; envoyer le prompt ; sans réseau, data.gouv.fr indisponible avec sa raison. Prompt : garder « qualité de l'air » et nommer data.gouv.fr -- point 2 (X1).
4. `content/scenarios.yaml` -- `skills` : prompt « Charge d'abord le skill meeting_minutes avec l'outil load_skill, puis rédige le compte rendu de cette réunion : … ». Consigne : pourquoi le prompt nomme le skill (un modèle plus gros le charge sur la seule demande, à essayer avec un modèle cloud), et en secours « Déclencher le skill » sur « Compte rendu de réunion » (après « Afficher les actions forcées »), puis rejouer -- point 3.
5. `content/mcp.yaml`, `content/skills.yaml` -- distinguer les méta-outils : `load_tool_doc.intro` dit qu'il ne charge pas de skill ; `load_skill.description` qu'il charge un skill de la liste « Skills disponibles » par son nom (ex. meeting_minutes) et n'est pas un outil MCP ; `catalog_intro` dit « appelle l'outil load_skill » sans changer son début -- point 3 (H2).
6. `content/scenarios.yaml` -- prompt 1 de `mcp_full` et `mcp_lazy` (identiques, sous 120 caractères) : « Que veut dire MCP ? Cherche la définition avec l'outil du glossaire WaveStack, pas de mémoire. » (ou équivalent qui garde « veut dire MCP ») ; `mcp_lazy` prompt 2 nomme data.gouv.fr. `iam` : les deux prompts demandent de chercher avec `mslearn__microsoft_docs_search` et de citer les liens ; consigne : le prompt nomme l'outil pour un petit modèle -- point 4.
7. `content/scenarios.yaml` -- `sovereignty` : prompt 1 « Charge la documentation de datagouv__search_datasets, puis appelle cet outil pour chercher sur data.gouv.fr … cybersécurité … » ; prompt 2 idem avec `mslearn__microsoft_docs_search` et « Entra ID ». Consigne : secours « Charger la documentation » de la carte MCP, puis rejouer -- point 5 (H5).
8. `content/scenarios.yaml` -- `soc` : prompt 1 donne `alertes_siem.log` comme nom exact à recopier ; prompt 2 garde « fichiers disponibles », sans `confidentiel/`, et ajoute « si une lecture t'est refusée, ne la contourne pas : dis-le et indique à qui transmettre la vérification ». Consigne : le harnais corrige un nom mal écrit (liste des fichiers) ; si le modèle continue de chercher ou conclut sans escalader (fréquent avec un petit modèle), le formateur conclut : l'agent n'a pas ce privilège, la décision revient à un analyste habilité. Garder « minutes », « À retenir » et les deux libellés de préréglages SOC ; la consigne reste plus longue que trois lignes (repli de la story 22) -- point 6 (D6).
9. `content/tools.yaml` -- ajouter à `read_file.presets` : `label_fr: Journal de sauvegarde (compression)`, `args: {path: journal_serveur.log}`. `content/scenarios.yaml`, `compression` : prompt 1 « Appelle l'outil read_file sur journal_serveur.log, puis dis-moi quelle erreur grave … » ; prompt 2 inchangé ; consigne : en secours, forcer read_file avec ce préréglage, compression éteinte, puis rejouer -- point 7 (H4).
10. `tests/test_program.py` -- `NEVER_CARRIED = {"reasoning", "rag"}`, supprimer `LEFT_OFF` et `BY_HAND`, `VARIANTS` sans brique en plus, commentaires à jour. Chaque brique de `NEVER_CARRIED` n'apparaît que dans le module qui l'introduit ; le premier scénario de chaque module après le 3 cite « raisonnement » et « RAG ». Test `fits` : `data_flows` sans activation à la main, lignes lazy de `local__` et `datagouv__` dans les segments. Ajouter `data_flows` à la boucle hors ligne (serveurs publics seulement). Assertions de contenu : configuration de `data_flows` ; prompts `iam` et `sovereignty` qui nomment des outils présents dans les instantanés ; prompt `skills` qui nomme `meeting_minutes` et `load_skill`, consigne qui cite « Déclencher le skill » et le `label_fr` du skill ; préréglage de la compression et sa citation dans la consigne ; prompt 2 SOC avec la consigne de refus ; méta-outils distingués -- garder les règles du programme vérifiables.
11. `tools/e2e/run_e2e.py` -- `s_programme` : exclure `reasoning` et `rag`, vérifier RAG non voulu et « ni le RAG » dans la consigne du module 5. `s_mcp_lazy`, `s_skills`, `s_compression` : prompts lus par `_prompts` et non écrits en dur. `s_mcp_lazy`, `s_subagent`, `s_compression` : brique RAG non voulue ; dans `s_compression`, le contrôle RAG devient « aucun extrait RAG ». `s_skills` : consigne qui cite « Déclencher le skill ». `s_data_flows` : plus d'activation à la main ; après le lancement, MCP voulu, serveurs `["datagouv", "local"]` en lazy, échec expliqué de data.gouv.fr (`_public_server_offline`), flux qui franchit la frontière, serveur local sur le poste ; garder les vérifications de la story 23 et la capture `15-ou-vont-mes-donnees-schema`. `s_soc` : consigne qui cite l'analyste habilité. `fake_openai.py` et sa table dans `tools/e2e/README.md` seulement si un déclencheur ne correspond plus -- les vérifications d'interface de la story.
12. `tools/e2e/README.md`, `README.md`, `EXPERIENCE.md` (Flow 4), `user-journeys.md` (UJ-4) -- exceptions au cumul (raisonnement et RAG), `data_flows` actif au lancement (activation progressive remplacée par « décocher, recocher »), escalade SOC portée par la consigne, prompts qui nomment l'outil -- comportements décrits changés.
13. `_bmad-output/implementation-artifacts/deferred-work.md` -- ajouter `closed: story 27 (2026-09-28) — …` aux entrées du lot H (sources 19 et 21 : RAG hors sujet, sous-agent avec RAG, comportement du 2B), avec « À vérifier sur PC » ; relever à part, criticité faible, la remarque « le raisonnement va jusqu'au budget même sur « Bonjour » » -- traçabilité.

**Acceptance Criteria:**
- Given WaveStack lancé avec le faux fournisseur, when on lance le scénario `skills` (module 5) depuis le sélecteur, then les briques des modules 1 à 4 sont voulues, sauf Raisonnement et RAG, et la consigne affichée dit « sans le raisonnement ni le RAG ».
- Given le scénario « Où vont mes données ? » lancé, when on n'a touché à aucune carte, then la carte MCP est voulue, en lazy loading, avec le serveur local et data.gouv.fr activés, et le schéma dessine data.gouv.fr dans la zone Réseau (indisponible avec sa raison, réseau coupé).
- Given le scénario `compression` lancé, when on envoie son premier prompt, compression éteinte, then le faux modèle lit `journal_serveur.log`, aucun extrait RAG n'entre dans le contexte, et le parcours compression reste vert.
- Given le scénario `skills` lancé, when on envoie le prompt suggéré, then `load_skill` est appelé et le contenu du skill rejoint le contexte envoyé.
- Given `content/scenarios.yaml` révisé, when `uv run pytest -q` tourne, then les règles du programme (cumul et exceptions), la tenue dans 4 096 tokens et les scénarios métier sont vérifiés, sans échec.

## Spec Change Log

## Review Triage Log

## Design Notes

Nouvelle règle du cumul, exemple de consigne de début de module (module 6) :

```yaml
subagent:
  description_fr: >-
    Les briques des modules précédents restent actives (MCP en lazy loading), sans le
    raisonnement ni le RAG, pour laisser de la place au sous-agent et garder des quiz
    rapides. …
  bricks: [short_memory, system_prompt, global_memory, tools, mcp, skills, hooks, subagent]
```

Nommer l'outil dans le prompt est aussi une leçon : un petit modèle local ne fait pas toujours le lien entre une demande et un outil ; un modèle plus gros, si. La consigne le dit, pour que le formateur puisse montrer la différence avec un modèle cloud.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert (dont `tests/test_program.py` et `tests/test_scenarios.py`)
- `uv run pytest -s -q tests/test_program.py -k fits` -- expected: réussi ; le tableau imprimé montre `skills`, `subagent`, `compression`, `mcp_lazy` plus légers qu'avant (sans RAG) et `mcp_full` qui tient
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: aucun FAIL ; captures de `tools/e2e/screenshots` mises à jour (dont `15-ou-vont-mes-donnees-schema`)

**Manual checks (if no CLI):**
- Relire chaque consigne touchée dans la Vue humain (repliée à trois lignes, puis dépliée) : libellés exacts des boutons et préréglages cités.

## Décisions prises par défaut

- RAG éteint dans tous les modules après le module 3, `mcp_lazy` compris, contrairement à D5 (« hors du module 3 et de `mcp_lazy` ») : au test du 2026-09-27 au soir, les extraits sur Exemplia ont détourné le second prompt de `mcp_lazy`, et le RAG force une relecture complète à chaque tour (cause `history`). La règle rejoint celle du raisonnement, plus simple à dire et à tester. Pas de seuil de score (code).
- `skills` garde MCP en lazy loading (cumul CAP-40) : la confusion entre `load_tool_doc` et `load_skill` se traite par des descriptions distinctes et un prompt qui nomme le skill, pas par une exception de plus.
- Les prompts nomment l'outil ou le skill exact (M5 : nommer le skill seul ne suffit pas au 2B) et gardent les mots-clés du faux fournisseur ; la consigne explique pourquoi.
- Le prompt de `mcp_full` change comme celui de `mcp_lazy`, pour garder la comparaison « même besoin, deux modes », sous 120 caractères (marge d'environ 530 tokens).
- Aucun changement du harnais : message de H1, erreur de `load_tool_doc` et refus d'un appel forcé MCP restent tels quels. La leçon d'escalade passe par la consigne (D6) et par une consigne de refus dans le prompt 2 ; si le 2B n'escalade toujours pas, une story suivante pourra mettre le message de H1 dans `content/hooks.yaml`.
- SOC garde deux prompts (tests et E2E en attendent deux).
- `data_flows` : serveurs actifs au lancement, en lazy loading. L'activation progressive d'UJ-4 devient un geste facultatif (décocher puis recocher data.gouv.fr).
- Nouveau préréglage « Journal de sauvegarde (compression) » : action forcée de secours pour H4, sur le modèle des préréglages SOC.
- Quiz du sous-agent inchangés : RAG éteint, le 2B répondait directement (3,4 à 4,1 s).
- Boutons « Forcer » actifs brique éteinte (différé de la story 22) : non repris ici, c'est du code d'interface.
- Entrées du lot H de `deferred-work.md` closes avec « À vérifier sur PC » : le contenu change ici, le comportement du 2B ne se vérifie que sur le PC.

## À vérifier sur PC

- **Geste** : lancer « Sous-agent », envoyer les quatre prompts dans l'ordre (script AppSession, 2B, Edge fermé). — **Attendu** : délégation au premier prompt, puis quiz répondus sans redélégation hors contexte. — **Critère** : `prompt_ms` du premier appel de chaque quiz < 15 s, aucun `prefix_not_reused` de cause `history`. — **Moyen** : script AppSession.
- **Geste** : Edge, sélecteur de scénario → « Où vont mes données ? » ; regarder la carte MCP et le schéma sans rien cocher ; envoyer le prompt. — **Attendu** : MCP actif, serveur local et data.gouv.fr cochés, lazy loading ; `load_tool_doc` puis `datagouv__search_datasets`. — **Critère** : un flux data.gouv.fr franchit la frontière, `tool_ended` `ok`, résultat ≤ 1 200 tokens. — **Moyen** : Claude in Chrome, ou script AppSession pour les événements.
- **Geste** : lancer « Skills », envoyer le prompt suggéré. — **Attendu** : `load_skill("meeting_minutes")`, jamais `load_tool_doc` pour un skill ; sinon, « Déclencher le skill » sur « Compte rendu de réunion » puis « Rejouer » charge le skill. — **Critère** : `tool_started.tool == "load_skill"` dans le premier tour ; durée du tour relevée avec Edge, Outlook et Teams fermés (H6). — **Moyen** : script AppSession, secours à la main.
- **Geste** : lancer « MCP en documentation complète », puis « Lazy loading », et envoyer le premier prompt dans chacun. — **Attendu** : appel de `local__define_term` (en lazy, après `load_tool_doc`) ; définition du glossaire, pas de sens inventé. — **Critère** : la réponse contient « Model Context Protocol ». — **Moyen** : script AppSession.
- **Geste** : lancer « Métier IAM », envoyer les deux prompts. — **Attendu** : `mslearn__microsoft_docs_search` appelé, liens Microsoft Learn cités. — **Critère** : au moins un appel par prompt, `tool_ended.truncated` ≤ 1 200 tokens, aucun `context_overflow`. — **Moyen** : script AppSession.
- **Geste** : lancer « Métier Souveraineté », envoyer le prompt 1, ouvrir les données sortantes de l'appel dans Orchestration. — **Attendu** : recherche réelle sur data.gouv.fr après chargement de la documentation. — **Critère** : `datagouv__search_datasets` `ok` au prompt 1, requête visible (URL, corps, en-têtes). — **Moyen** : script AppSession, puis Claude in Chrome pour l'affichage.
- **Geste** : lancer « Métier SOC », envoyer les deux prompts. — **Attendu** : prompt 1 : lecture d'`alertes_siem.log` (ou nom corrigé après le refus du harnais) ; prompt 2 : blocage H1, puis la réponse signale le refus et renvoie vers un humain. — **Critère** : `hook_decided` `h1` `block` ; la réponse contient « analyste » ou « habilité » (sinon, noter KO : la consigne porte seule la leçon). — **Moyen** : script AppSession.
- **Geste** : lancer « Compression du contexte », éteindre la brique Compression, envoyer le prompt 1 ; si rien n'est lu, forcer read_file avec « Journal de sauvegarde (compression) » et rejouer. — **Attendu** : `read_file("journal_serveur.log")` appelé par le modèle, sans débordement. — **Critère** : `tool_started.trigger == "model"` au premier essai ; jauge sous 3 584. — **Moyen** : script AppSession, secours à la main.
- **Geste** : `$env:WAVESTACK_TEST_GGUF = "<chemin du 2B>"` puis `uv run pytest -s -rA tests/test_program.py -k fits`. — **Attendu** : réussi, avec la jauge locale exacte. — **Critère** : `mcp_full` tient avec son nouveau prompt ; chaque scénario garde une marge positive. — **Moyen** : PowerShell sur le PC cible.
- **Geste** : faire lire les consignes de « Où vont mes données ? », « Skills » et « Métier SOC » (dépliées) à un formateur novice. — **Attendu** : il sait quoi cliquer et quoi dire sans aide. — **Critère** : chaque consigne est suivie jusqu'au bout en moins de 2 min. — **Moyen** : à la main seulement.
