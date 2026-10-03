---
title: 'V2 (6/6) : test préalable des modèles de décision'
type: 'feature'
created: '2026-10-01'
status: 'done'
route: 'dispatch'
baseline_commit: '2269793edb480b92807883613809b1b421ec92cf'
review_loop_iteration: 0
size: 'M, plus un relevé manuel sur le PC cible'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/decision-model-candidates.md'
---

> Seule story que la contrainte « Déclenchement » permet avant le pilote, sur décision d'Anaël, donnée le 2026-10-01. Elle ne livre aucune fonction.

> **Statut au 2026-10-03 : `done`.** Le relevé sur le PC cible est fait, et le rapport `_bmad-output/implementation-artifacts/rapport-test-prealable-modeles-de-decision.md` porte les mesures et les verdicts. Le passage de bmad-spec a mis à jour `decision-model-candidates.md`. Les candidats arrivés depuis (Decision 2.0 Kai, mDeBERTa, MiniLM multilingues) se mesurent dans la story 7.

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problème :** Les routages de la V2 (CAP-7 et CAP-8) dépendent d'un modèle de décision qui doit tourner sur CPU, sous Windows, sans droits admin, à côté du SLM et dans 4 Go. Au 2026-09-25, Decision 1.0 échoue à ce test : ni GGUF ni ONNX, pas de chemin CPU. Les alternatives n'ont pas été mesurées.

**Approche :** CAP-6. Un banc hors produit, sur le modèle de `tools/bench/story12_bench.py`, mesure chaque candidat de `decision-model-candidates.md` selon les six critères du test préalable. Le verdict par candidat est consigné. Le résultat fixe le candidat de chaque échelon, ou confirme le repli sur le SLM juge.

## Boundaries & Constraints

**Always :**
- Les six critères de `decision-model-candidates.md`, mesurés pour chaque candidat : RAM ajoutée, avec le SLM par défaut chargé ; latence médiane et maximale d'une décision ; tentatives réseau ; paquets ajoutés et leurs licences ; présence de torch ; `trust_remote_code` et version épinglée.
- Les entrées de mesure : une vingtaine de prompts fixes, tirés des prompts suggérés des scénarios V1. Deux tâches : une décision de coût (simple ou complexe) ; une décision de spécialité, sur trois ou quatre critères écrits.
- L'échelon 3 (SLM juge) se mesure aussi : latence d'une décision à sortie contrainte avec le SLM par défaut. C'est la référence du repli.
- Decision 1.0 : on revérifie d'abord la disponibilité d'un GGUF, d'un ONNX ou d'un chemin CPU, avec la source et la date. S'il n'y en a toujours pas, il est écarté sans mesure.
- Le verdict de chaque candidat (retenu, écarté ou à surveiller, avec la raison) va dans un rapport sous `_bmad-output/implementation-artifacts/`, et une entrée « Test préalable du modèle de décision » s'ajoute au « Deferred » d'`ARCHITECTURE-SPINE.md`.
- Les mesures du conteneur de développement sont marquées comme telles. Le verdict vient du relevé sur le PC cible.
- Critères d'acceptation de la story : `tools/bench/` gagne une commande par candidat, sa logique pure est testée ; le rapport donne, pour chaque candidat, les mesures et le verdict, avec le PC et la date du relevé ; `decision-model-candidates.md` est mis à jour par un nouveau passage de bmad-spec, pas à la main.

**Never :**
- Une dépendance ajoutée au projet, ou un fichier modifié sous `src/wavestack/`.
- Exécuter `trust_remote_code` sans avoir relu et épinglé le code.
- Retenir un candidat génératif comme classifieur coexistant (règle d'un seul modèle génératif).

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Sortie attendue | Erreur |
|---|---|---|---|
| Candidat mesuré | `measure <id>` avec le modèle sur le disque et `--slm` | mesures (RAM, latences, réseau, paquets, torch, révision) et verdict | — |
| Modèle absent | `measure <id>` sans `--download`, rien en cache | statut « absent (lancer avec --download …) », pas de mesure | message en français, code 0 |
| Paquet de mesure absent | `measure <id>` sans le `--with` requis | statut « non mesuré (<module> absent) » avec la commande | — |
| SLM introuvable | ni `--slm`, ni un seul GGUF dans le dossier des modèles | arrêt, liste des GGUF trouvés | code 2 |
| Hors PC cible | mesure sous Linux (conteneur) | verdict marqué « indicatif, hors PC cible » | — |
| Decision 1.0 sans chemin | `decision10 --checked-on … --source …` sans `--gguf/--onnx/--cpu` | « écarté sans mesure » | relevé sans date ou source : code 2 |
| Candidat génératif ou rejeté | Llama-Guard, Qwen3Guard, Arch-Router | verdict d'office dans `list`, jamais mesuré | — |
| Identifiant inconnu | `measure foo` | liste des candidats | code 2 |

</frozen-after-approval>

## Code Map

- `tools/bench/story12_bench.py` -- modèle à suivre et source des aides réutilisées par import (sans les copier) : `_record_and_guard` (garde AD-15 avant tout import tiers, proxy retiré), `_strip_proxy_env`, `_run_child`, `_rss_mb`, `_baseline_rss`, `_loaded_rss`, `added_rss_mb` (pic moins base, lot F), `dependency_closure`, `classify_license`, `summarize_attempts`, `_blocked_host`. Ne pas le modifier.
- `tests/test_story12_bench.py` -- modèle du test : module chargé par `importlib.util.spec_from_file_location`, chemins lourds remplacés par des faux injectés.
- `content/scenarios.yaml` -- `scenarios.<id>.prompts` : source des vingt prompts (copiés dans le banc ; le test vérifie qu'ils y figurent toujours).
- `src/wavestack/config.py` -- `models_dir()` (lecture seule) : dossier où chercher le GGUF du SLM par défaut quand `--slm` manque.
- `pyproject.toml` / `uv.lock` -- `huggingface-hub` 1.33.0, `tokenizers` 0.23.2, `llama-cpp-python` 0.3.35, `psutil`, `numpy` déjà présents ; `onnxruntime`, `torch`, `transformers`, `gliformer`, `fast-gliner` arrivent par `uv run --with`. Ne rien ajouter.
- `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md` -- section `## Deferred`, entrée « Test préalable de Headroom » comme modèle de forme.
- `tools/bench/README.md` -- titre story 12 ; y ajouter une courte section qui renvoie au nouveau banc et au rapport.
- Faits lus sur Hugging Face (MCP) le 2026-10-01, sans téléchargement : `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` (MIT, `onnx/model.onnx` 739 Mo, id2label `entailment`/`not_entailment`) ; `MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33` (MIT, `onnx/model_quantized.onnx` 87 Mo) ; `nvidia/prompt-task-and-complexity-classifier` (licence « other », NVIDIA Open Model License, safetensors seuls, code du modèle dans la carte, dorsale `microsoft/DeBERTa-v3-base`, huit têtes) ; `knowledgator/gliformer-base-v1` (Apache-2.0, `pytorch_model.bin`, bibliothèque `gliformer`) ; `talmago/gliformer-base-v1-onnx` (ONNX tiers pour `fast_gliner`, licence non déclarée). Tous en anglais.

## Tasks & Acceptance

**Execution:**
- [x] `tools/bench/v2s6_decision_bench.py` -- créer le banc : vingt prompts, deux tâches à critères écrits, catalogue des candidats, sous-commandes `list`, `decision10`, `measure <id>` (`--download`, `--slm`, `--models-dir`, `--out`, `--json`), enfant de mesure propre (garde réseau, SLM chargé et chaud, base RSS, chargement du candidat, échauffement, 40 décisions chronométrées), verdicts purs -- mesure reproductible sur le PC cible, sans dépendance ajoutée.
- [x] `tests/test_v2s6_decision_bench.py` -- tester la logique pure : jeu de prompts, décodages (NLI, nvidia, gliformer, grammaire du juge), latences, verdicts, Decision 1.0, flux `run_measure` avec faux, CLI `list` et identifiant inconnu -- critère d'acceptation « logique pure testée ».
- [x] `_bmad-output/implementation-artifacts/rapport-test-prealable-modeles-de-decision.md` -- squelette du rapport : poste et date à remplir, commandes exactes par candidat, tableau des mesures vide, verdicts d'office déjà écrits, relevé Decision 1.0, suite (bmad-spec) -- le relevé d'Anaël le remplit.
- [x] `ARCHITECTURE-SPINE.md` -- ajouter au « Deferred » l'entrée « Test préalable du modèle de décision » : banc prêt, verdict en attente du relevé, repli SLM juge -- exigé par la story.
- [x] `tools/bench/README.md` -- section courte vers le nouveau banc et le rapport.

**Acceptance Criteria:**
- Given le dépôt sans paquet de mesure, when `uv run python tools/bench/v2s6_decision_bench.py list` est lancé, then chaque candidat de `decision-model-candidates.md` apparaît avec sa commande ou son verdict d'office, sans aucun accès réseau.
- Given le test du banc, when `uv run pytest tests/test_v2s6_decision_bench.py` est lancé, then il passe sans modèle, sans réseau et sans paquet de mesure.
- Given le diff, when on le relit, then `pyproject.toml`, `uv.lock` et `src/wavestack/` sont inchangés, et `decision-model-candidates.md` aussi.

## Implementation Notes

- 2026-10-01 (mode nuit) : implémenté directement par l'agent qui a planifié, sans sous-agent d'implémentation. Le contexte d'investigation était déjà chargé, et le PC de 16 Go est partagé avec d'autres agents.
- Les aides de `story12_bench.py` sont chargées par `importlib` sous le nom privé `_v2s6_story12_helpers`, enregistré dans `sys.modules` (les dataclasses résolvent leurs annotations par lui). `story12_bench.py` est inchangé.
- Les commandes du rapport passent par `--out` (JSON en UTF-8) : sous PowerShell 5.1, `>` écrirait de l'UTF-16.
- Rien n'a été téléchargé ni mesuré. La seule exécution réelle est `measure deberta_xsmall` sans onnxruntime, qui répond « non mesuré » sans réseau. Les chemins lourds (`_load_nli`, `_load_nvidia`, `_load_gliformer`, `_load_slm_judge`, `_measure_child`, `download_candidate`) ne sont exercés que par le relevé d'Anaël.
- Fichiers : `tools/bench/v2s6_decision_bench.py`, `tests/test_v2s6_decision_bench.py`, `tools/bench/README.md`, `ARCHITECTURE-SPINE.md` (Deferred), `_bmad-output/implementation-artifacts/rapport-test-prealable-modeles-de-decision.md`.

## Spec Change Log

- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : point d'arrêt 1 (approbation de la spec) -- « Approve and continue », la spec respecte la story. Choix tranchés sans question, à valider sur le relevé : seuils de latence (médiane ≤ 1 000 ms, maximum ≤ 3 000 ms), partage bloquant / non bloquant des critères, torch chargé → « à surveiller », seuil de complexité nvidia 0,3, accord avec l'étiquette attendue affiché sans valoir critère. Périmètre de la nuit : aucun téléchargement, aucune mesure réelle ; revérification de Decision 1.0 laissée au relevé d'Anaël.
- 2026-10-01 -- validé en mode nuit (Anaël absent, autorisation du 01/10 au soir) : revue (step-04), 25 constats ; tous les correctifs de type patch sont appliqués, sans loopback ni report. Fin du workflow (step-05) : le statut reste `in-review` au lieu de `done`, parce que le critère d'acceptation « mesures et verdict par candidat, avec le PC et la date » attend le relevé manuel sur le PC cible.
- 2026-10-03 -- relevé sur le PC cible (lancé par Anaël le 02/10, joué par l'agent) : SLM juge « repli (référence) », `deberta_xsmall` et `deberta_base` « retenu », `nvidia` « à surveiller » (torch), `gliformer` non mesuré (mémoire du poste), `gliformer_onnx` « écarté sur le PC cible » (`fast-gliner` sans roue Windows), Decision 1.0 « à surveiller » (chemin CPU par Transformers). Défaut du banc trouvé et corrigé : `classify_license` lisait `BSL-1.0` (Boost) comme Business Source License, d'où un faux « écarté » pour `nvidia` ; verdict recalculé sur les mêmes mesures. Le statut reste `in-review` : seuils de latence à valider par Anaël, puis bmad-spec sur `decision-model-candidates.md`.
- 2026-10-03 -- seuils de latence validés par Anaël au vu du relevé (médiane ≤ 1 000 ms, maximum ≤ 3 000 ms). Reste : bmad-spec sur `decision-model-candidates.md`, puis la story passe à `done`.
- 2026-10-03 -- passage de bmad-spec fait. Choix d'Anaël :
  - `deberta_xsmall` est le candidat par défaut de l'échelon 2, et `deberta_base` ne sert que RAG éteint ;
  - `gliformer` est écarté (RAM, mesure indicative) ;
  - Decision 2.0 Kai, mDeBERTa et MiniLM multilingues s'ajoutent aux candidats et se mesurent dans la story 7.

  Le « Deferred » d'`ARCHITECTURE-SPINE.md` porte le verdict. Statut : `done`.

## Review Triage Log

Passe 1 (2026-10-01, trois couches : Blind Hunter, Edge Case Hunter, Verification Gap). Aucun intent_gap ni bad_spec. Tous les correctifs retenus sont appliqués (patch), et 58 tests passent.

| # | Couche | Constat | Verdict | Preuve et suite |
|---|---|---|---|---|
| 1 | VG | La sortie de `_measure_child` vers `decision_verdict` et `print_measure` n'est pas testée | medium | Vrai : aucun test n'exécutait l'enfant. Patch : `test_measure_child_report_feeds_the_verdict_and_the_printout` (faux llama_cpp, RSS et chargeur) et `test_child_command_line_matches_its_parser`. |
| 2 | VG, BH | Un réseau bloqué au chargement donne « non mesuré », pas « écarté » | medium | Vrai : retour anticipé sur `status != measured`. Patch : `blocked` ou des hôtes tentés sur une erreur donnent « écarté » (Hors ligne). Testé. |
| 3 | VG | `resolve_slm` ne cherche qu'à la racine du dossier des modèles | low | Vrai, mais les commandes du rapport passent toujours `--slm`, et l'échec est explicite. La correction ajouterait une recherche récursive à exclusions : rejeté. |
| 4 | ECH | `--out` illisible (`$OUT` non défini) : trace d'erreur, mesure perdue | medium | Vrai. Patch : affichage d'abord, puis écriture protégée, message sur stderr. Testé. |
| 5 | ECH | `top_label([[]])` lève IndexError | low | Vrai. Patch direct (lot vide déballé). Testé. |
| 6 | ECH | Formes `{labels, scores}` ou chaînes nues de `classify` | maybe-false | Aucune des deux bibliothèques ne documente ces formes (GLiFormer : liste de dicts ; fast_gliner : couples). Au pire low : rejeté. |
| 7 | ECH | `rss_peak_mb` à None compte comme KO bloquant | low | Vrai. Patch direct : critère « non vérifiable ». Testé. |
| 8 | ECH, BH | L'échauffement ne couvre que la tâche de coût | medium | Vrai : la première décision de spécialité était chronométrée à froid, avec un maximum bloquant. Patch : échauffement par tâche. Testé. |
| 9 | ECH, BH | N'importe quel Windows passe le critère 1, sans contrôle des droits admin | medium | Vrai. Patch : `windows_release` et `admin` (`IsUserAnAdmin`) relevés ; critère 1 ok seulement sous Windows 11 sans droits admin, sinon « indicatif ». Testé. |
| 10 | ECH, BH | Un instantané partiel passe pour présent | low | Vrai. Patch : chaque fichier requis est vérifié, et les erreurs de téléchargement apparaissent dans le statut. Testé. |
| 11 | ECH | Une exception du téléchargeur hors de sa boucle n'est pas rattrapée | low | Vrai (import manquant, garde). Patch : erreur consignée dans `download.errors`. Testé. |
| 12 | ECH | GLiFormer irait chercher la configuration de sa dorsale en ligne | false | `gliner_config.json` embarque `encoder_config` (lu sur HF le 2026-10-01). Si une tentative avait lieu, la garde la bloquerait et le constat 2 l'écarterait, ce qui est correct. |
| 13 | ECH, BH | « sans objet » affiché pour un modèle programmable qui ne répond rien | low | Vrai. Patch : « sans objet » réservé aux étiquettes fixes (spécialité de nvidia), sinon décompte. Testé. |
| 14 | ECH | `--json` avec `--out` : stdout n'est plus du JSON pur | low | Vrai. Patch direct : message sur stderr. |
| 15 | ECH | Une URL faite d'espaces passe Decision 1.0 « à surveiller » | low | Vrai. Patch direct (`strip`). Testé. |
| 16 | BH | Le critère RAM ignore l'embedding et le reranker de NFR-2 | medium | Vrai, mais l'intention fixe « avec le SLM par défaut chargé ». Patch : le détail donne le total avec le RAG V1 (`measured_rss_mb` de `wavestack.toml`, 1 170 Mo). Le rapport laisse au passage de bmad-spec le choix « routage démontré RAG éteint ». |
| 17 | BH | « Révision épinglée » ne peut jamais échouer, et rien n'est épinglé | medium | Vrai. Patch : critère renommé « commit et versions consignés » ; versions des paquets relevées dans l'enfant et exigées ; le rapport explique l'épinglage par consignation. Testé. |
| 18 | BH | tokenizers et huggingface-hub ne viennent que de l'extra `compression` | medium | Vrai (`requires` du cœur, sans eux). Patch : ajoutés aux `--with` et aux racines des « paquets ajoutés » (NLI, GLiFormer). Rapport et test mis à jour. |
| 19 | BH | SLM chargé avec d'autres réglages que le moteur de WaveStack | low | Vrai (`engine.py` : `n_ctx` de la fenêtre, threads par défaut). Patch : mêmes réglages, fenêtre lue dans `wavestack.toml` et consignée. Testé. |
| 20 | BH | Seuil de GLiFormer différent entre les deux variantes | false | D'après son README, fast_gliner `classify` rend toutes les étiquettes, triées ; le volet « aucune » est traité au constat 13. |
| 21 | BH | Licence nvidia forcée à « ok » sans source | low | La source est `decision-model-candidates.md`. Patch du rapport : clauses à relire avant tout « retenu », support GPU et Ubuntu seulement d'après la carte. |
| 22 | BH | Le verdict du SLM juge ignore un KO de RAM | low | Vrai. Patch : tout critère bloquant donne « à revoir ». Testé. |
| 23 | BH | Le type et le bloc gelé du fichier de story | — | La correction modifierait la spec de ce build : rejeté (règle de tri). Le statut final dit que la story attend le relevé. |
| 24 | BH | Le JSON manque de provenance (commit, banc, llama-cpp) | low | Vrai. Patch : `repo_commit`, `bench_sha256`, `llama_cpp_version`. |
| 25 | BH | Tests plus faibles qu'il n'y paraît | medium | Couvert par les constats 1, 2, 10 et 22. Le test conditionnel à onnxruntime garde son pendant inconditionnel (`test_run_measure_without_measurement_package`). |

## Design Notes

**Critères en verdict.** Chaque critère vaut ok, KO ou « non vérifiable par le banc ». Bloquants (KO → **écarté**) : RAM (pic total, SLM compris, ≤ 4 096 Mo, NFR-2), latence, hors ligne, licence interdite. Non bloquants (KO → **à surveiller**, avec ce qui manque) : torch chargé, licence non déclarée ou à vérifier, révision non épinglée. Tout ok → **retenu**. Hors Windows, le verdict porte « indicatif, hors PC cible ». Le critère « roues précompilées » ne s'observe pas depuis Python : le rapport demande de vérifier dans la sortie de `uv` qu'aucun paquet n'a été compilé.

**Seuils de latence (validés par Anaël le 2026-10-03, sur le relevé).** Médiane ≤ 1 000 ms, maximum ≤ 3 000 ms par décision : une décision de routage ne doit pas peser plus qu'une fraction du tour. Le SLM juge n'a pas de seuil : il est la référence, verdict « repli (référence) » s'il fonctionne hors ligne.

**Qualité indicative.** Chaque prompt porte une étiquette attendue (coût, spécialité), écrite par l'agent et discutable. L'accord est affiché, jamais critère : la story ne mesure pas la qualité, et les candidats sont entraînés en anglais face à des prompts français.

**Décodage par candidat.** NLI (DeBERTa) : ONNX Runtime et `tokenizers`, une paire (prompt, critère) par étiquette, l'étiquette au plus fort taux d'implication. nvidia : code de la carte relu et reproduit (dorsale construite depuis sa configuration, poids chargés depuis `model.safetensors`, huit têtes, score de complexité pondéré), coût = complexité ≥ 0,3 ; sa spécialité est son `task_type` fixe. GLiFormer : `classify` avec des libellés courts ; deux variantes, officielle (torch) et ONNX tiers (`fast_gliner`). SLM juge : `create_chat_completion` avec une grammaire GBNF limitée aux étiquettes.

**Révision.** Le téléchargement suit `main` et le rapport consigne le commit résolu (dossier `snapshots/<sha>`) ; la mesure tourne hors ligne sur ce commit. Aucun `trust_remote_code`.

## Verification

**Commands:**
- `uv run ruff check tools/bench/v2s6_decision_bench.py tests/test_v2s6_decision_bench.py` -- expected: aucun écart
- `uv run ruff format --check tools/bench/v2s6_decision_bench.py tests/test_v2s6_decision_bench.py` -- expected: aucun écart
- `uv run pytest tests/test_v2s6_decision_bench.py -q` -- expected: tout passe
- `uv run python tools/bench/v2s6_decision_bench.py list` -- expected: les candidats et leurs commandes, sans réseau

**Manual checks (if no CLI):**
- Relevé d'Anaël sur le PC cible : une commande par candidat, telles qu'écrites dans le rapport.
