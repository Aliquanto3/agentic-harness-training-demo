---
title: 'V2 (6/6) : test préalable des modèles de décision'
type: 'spike'
created: '2026-10-01'
status: 'draft'
size: 'M, plus un relevé manuel sur le PC cible'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v2/decision-model-candidates.md'
---

> Seule story que la contrainte « Déclenchement » permet avant le pilote, sur décision d'Anaël. Elle ne livre aucune fonction.

## Intent

**Problème :** Les routages de la V2 (CAP-7 et CAP-8) dépendent d'un modèle de décision qui doit tourner sur CPU, sous Windows, sans droits admin, à côté du SLM et dans 4 Go. Au 2026-09-25, Decision 1.0 échoue à ce test : ni GGUF ni ONNX, pas de chemin CPU. Les alternatives n'ont pas été mesurées.

**Approche :** CAP-6. Un banc hors produit, sur le modèle de `tools/bench/story12_bench.py`, mesure chaque candidat de `decision-model-candidates.md` selon les six critères du test préalable. Le verdict par candidat est consigné. Le résultat fixe le candidat de chaque échelon, ou confirme le repli sur le SLM juge.

## Ce qui existe déjà (V1)

Le banc de la story 12 a déjà fait ce travail pour d'autres composants :
- mesure dans un processus enfant propre, avec la garde réseau d'AD-15 avant tout import tiers ;
- dépendances de mesure par `uv run --with`, sans en ajouter au projet ;
- logique pure testée (`tests/test_story12_bench.py`) ;
- verdict consigné dans le « Deferred » d'`ARCHITECTURE-SPINE.md`.

## Boundaries & Constraints

**Always :**
- Les six critères de `decision-model-candidates.md`, mesurés pour chaque candidat :
  - RAM ajoutée, avec le SLM par défaut chargé ;
  - latence médiane et maximale d'une décision ;
  - tentatives réseau ;
  - paquets ajoutés et leurs licences ;
  - présence de torch ;
  - `trust_remote_code` et version épinglée.
- Les entrées de mesure : une vingtaine de prompts fixes, tirés des prompts suggérés des scénarios V1. Deux tâches :
  - une décision de coût : simple ou complexe ;
  - une décision de spécialité, sur trois ou quatre critères écrits.
- L'échelon 3 (SLM juge) se mesure aussi : latence d'une décision à sortie contrainte avec le SLM par défaut. C'est la référence du repli.
- Decision 1.0 : on revérifie d'abord la disponibilité d'un GGUF, d'un ONNX ou d'un chemin CPU, avec la source et la date. S'il n'y en a toujours pas, il est écarté sans mesure.
- Le verdict de chaque candidat (retenu, écarté ou à surveiller, avec la raison) va dans un rapport sous `_bmad-output/implementation-artifacts/`, et une entrée « Test préalable du modèle de décision » s'ajoute au « Deferred » d'`ARCHITECTURE-SPINE.md`.
- Les mesures du conteneur de développement sont marquées comme telles. Le verdict vient du relevé sur le PC cible.

**Never :**
- Une dépendance ajoutée au projet, ou un fichier modifié sous `src/wavestack/`.
- Exécuter `trust_remote_code` sans avoir relu et épinglé le code.
- Retenir un candidat génératif comme classifieur coexistant (règle d'un seul modèle génératif).

## Critères d'acceptation

- `tools/bench/` gagne une commande par candidat. Sa logique pure est testée.
- Le rapport donne, pour chaque candidat, les mesures et le verdict, avec le PC et la date du relevé.
- `decision-model-candidates.md` est mis à jour par un nouveau passage de bmad-spec, pas à la main.

## Vérification

- `ruff`, puis `pytest` sur le test du banc.
- Lancement manuel du banc par Anaël sur le PC cible : une commande par candidat.
