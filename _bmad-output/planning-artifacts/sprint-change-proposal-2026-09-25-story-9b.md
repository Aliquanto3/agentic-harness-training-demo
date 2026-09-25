---
title: Sprint Change Proposal — story 9b (rejeu du dernier prompt) et statut du dépôt privé
date: 2026-09-25
author: Anaël (avec Claude, workflow bmad-correct-course)
trigger: scission de la story 9 (`stories/9-declenchement-force.md`, livrée) et entrée « Rejeu » de `deferred-work.md`
scope: mineur
status: approuvée et appliquée le 2026-09-25
---

# Sprint Change Proposal — story 9b et statut du dépôt privé

## 1. Résumé du problème

La story 9 de `stories.yaml`, « Déclenchement forcé et rejeu », réunissait deux livrables indépendants. Le 2026-09-25, elle a été scindée. Seul le déclenchement forcé (CAP-8) a été livré (`stories/9-declenchement-force.md`, statut `done`). Le rejeu (CAP-7, FR-7, AD-17) attend dans `deferred-work.md` sous l'étiquette « prévu en story 9b », mais aucune story 9b n'existe dans `stories.yaml`.

La spec de la story 9 a aussi pris une décision qui n'est pas reportée dans le plan : « `remember` et `delegate` naîtront avec leurs briques (palier 2) en réutilisant ce mécanisme ». Or les stories 14 et 19 disent encore que ces méta-outils sont « posés en story 9 ».

**Nature** : un écart de planification. Aucun défaut d'implémentation.

**Preuves** :
- `stories/9-declenchement-force.md`, Approach (« Le rejeu (CAP-7) est reporté en story 9b ») et Boundaries (décision sur `remember` et `delegate`) ;
- `deferred-work.md`, entrée `source_spec: none` « Rejeu du dernier prompt… prévu en story 9b » ;
- `stories.yaml`, stories 4, 9, 10, 14, 17 et 19.

**Précision sur la demande initiale.** Parmi les stories 14, 17 et 19, seule la 17 dépend du rejeu (« un rejeu après changement utilise le nouveau modèle » ; memlog : « Dépend des stories 9 (rejeu avec le nouveau modèle, AD-17) »). Les stories 14 et 19 dépendent de la story 9 pour le forçage (`remember`, `delegate`), selon le memlog. Leur dépendance à 9 reste donc juste. C'est leur texte « posés en story 9 » qu'il faut corriger.

## 2. Analyse d'impact

### Checklist

| Section | Statut | Constat |
|---|---|---|
| 1. Déclencheur | [x] | Scission de la story 9, décidée pendant sa spécification |
| 2. Impact sur les epics | [x] | Palier 1 : une story ajoutée (9b) avant la 10, qui clôt le palier. Palier 2 : aucune story ajoutée ni retirée. |
| 3. Conflits d'artefacts | [x] | `stories.yaml`, `deferred-work.md`. SPEC, PRD, architecture et UX : aucun changement (CAP-7, AD-17 et EXPERIENCE.md décrivent déjà le rejeu). |
| 4. Voie à suivre | [x] | Ajustement direct |
| 5. Composants de la proposition | [x] | Section 4 |
| 6. Revue finale | [x] | Approuvée par Anaël le 2026-09-25, avec la proposition « dépôt privé » |

### Stories

| Story | État | Impact |
|---|---|---|
| 4 | terminée | Le texte renvoie le rejeu à la story 9. Il est aligné sur 9b. |
| 9 | terminée | Titre, description et `invoke_dev_with` sont alignés sur ce qui a été livré : forçage seul. |
| **9b** | **nouvelle** | Rejeu du dernier prompt, entre 9 et 10 |
| 10 | à faire | « un scénario par brique construite dans les stories 1 à 9 » devient « 1 à 9b ». Le scénario Caveman compare avec et sans Caveman par le rejeu (CAP-26). |
| 14 | à faire | `remember` et « Écrire en mémoire » sont créés par la story elle-même. La dépendance à 9 et 10 est inchangée. |
| 17 | à faire | La dépendance passe de « 9 et 11 » à « 9b et 11 ». |
| 19 | à faire | `delegate` et « Déléguer au sous-agent » sont créés par la story elle-même. La dépendance à 9 et 11 est inchangée. |

### Impact technique

Aucun changement de code. Les amorces existent déjà : `Session.build_turn_state(origin_turn)` (`session/app_session.py:884`) et `turn_started{replay_of}` (émis à `None`, `app_session.py:1691`).

## 3. Voie recommandée

**Ajustement direct** : une story ajoutée et quelques textes alignés dans `stories.yaml`. Pas de rollback, pas de révision du MVP.

- **Effort** : faible (8 modifications de texte).
- **Risque** : faible. La story 9b arrive avant la 10, qui clôt le palier 1 : le rejeu reste au palier 1, comme le prévoit CAP-7.
- **Calendrier** : une story de plus au palier 1.

## 4. Propositions de modification détaillées

### `stories.yaml`

**S1 — Story 4, `invoke_dev_with`**

OLD : `rejeu (rejeu lui-même en story 9).`
NEW : `rejeu (rejeu lui-même en story 9b).`

**S2 — Story 9, alignée sur la livraison**

OLD :
```yaml
  title: Déclenchement forcé et rejeu
  description: >-
    L'utilisateur peut forcer toute action (outil, mémoire, skill, MCP) et rejouer
    le dernier prompt avec une autre configuration (CAP-7, CAP-8). S'appuie sur le rail
    par tour (8d) : un tour rejoué devient un nouveau groupe de tour avec le badge
    « Rejeu » ; une action forcée porte « Forcé par l'utilisateur » sur sa ligne d'étape.
    La mémoire globale s'ajoute au bac Fichiers du schéma (8e). Dépend de 8d et 8e.
  ...
  invoke_dev_with: >-
    Implémenter les actions armées (AD-3), les méta-outils remember/load_tool_doc/
    delegate restants (AD-25) et l'instantané/rejeu complet (AD-17). Dépend des
    stories 4 à 8 pour être démontrable sur toutes les briques du palier 1.
```

NEW :
```yaml
  title: Déclenchement forcé
  description: >-
    L'utilisateur arme une action (appel d'un outil natif avec ses arguments,
    « Charger la documentation » d'un outil MCP en lazy loading, « Déclencher le
    skill ») que le tour suivant exécute avant le premier appel au modèle (CAP-8).
    Une action forcée porte « Forcé par l'utilisateur » sur sa ligne d'étape du rail
    (8d). Le rejeu (CAP-7) est scindé en story 9b ; remember et delegate naissent avec
    leurs briques (stories 14 et 19). Dépend de 8d et 8e.
  ...
  invoke_dev_with: >-
    Implémenter les actions armées (AD-3) et leur consommation par l'exécuteur
    unique, hooks compris, avec trigger = user (AD-25). Dépend des stories 4 à 8
    pour être démontrable sur toutes les briques du palier 1.
```

Justification : la story terminée décrit ce qui a été livré (spec de la story 9, Approach et Boundaries).

**S3 — Nouvelle story 9b, insérée entre 9 et 10**

```yaml
- id: "9b"
  title: Rejeu du dernier prompt
  description: >-
    L'utilisateur rejoue le dernier prompt après avoir changé la configuration, pour
    comparer deux tours (CAP-7, FR-7). Le contexte du rejeu repart de l'état antérieur
    au tour d'origine, sans la question ni la réponse d'origine. Le tour rejoué devient
    un nouveau groupe de tour du rail (8d), avec le badge « Rejeu » qui figure aussi
    sur son message dans la Vue humain, et il est lui-même rejouable. « Comparer », en
    tête de Contexte LLM, montre deux tours côte à côte : contextes, tokens d'entrée et
    de sortie, temps. Une action armée (story 9) s'applique au tour rejoué. Scindée de
    la story 9 le 2026-09-25 (deferred-work.md).
  spec_checkpoint: true
  done_checkpoint: true
  invoke_dev_with: >-
    Implémenter la branche et le rejeu d'AD-17 avec build_turn_state(origin_turn),
    déjà amorcé : historique de la branche active jusqu'au tour qui précède l'origine ;
    skills et documentations MCP chargés (_loaded_docs) suivant la branche rejouée,
    pas la conversation entière (deferred-work, story 6b) ; tout le reste lu dans la
    configuration courante (briques, hooks, modèle, actions armées). Rejouer t3 crée
    t4, qui fait suite à t2 ; t3 reste consultable et turn_started{replay_of} les
    relie. Rejouer est une intention de classe (b), refusée hors idle (AD-3). La liste
    armée est prise au moment du rejeu, sous le verrou de l'envoi (correctif BH4 de
    la story 9). Front : bouton de rejeu et badge « Rejeu » dans la Vue humain, badge
    sur le groupe de tour du rail, « Comparer » désactivé avec moins de deux tours
    (EXPERIENCE.md). Dépend des stories 8d et 9.
```

Justification : la story reprend l'entrée de `deferred-work.md`, CAP-7, AD-17 et EXPERIENCE.md (« Comparaison de tours », état « Moins de deux tours », comportement « Rejeu »). `spec_checkpoint: true` parce que la story touche la session (branche, instantané) et trois volets.

**S4 — Story 10, `invoke_dev_with`**

OLD : `Un scénario par brique construite dans les stories 1 à 9.`
NEW : `Un scénario par brique construite dans les stories 1 à 9b.`

**S5 — Story 14, `invoke_dev_with`**

OLD :
```
Écriture par le méta-outil remember (réponse tool_result de la brique global_memory) et par l'action forcée « Écrire en mémoire », tous deux posés en story 9 (AD-25) ;
```
NEW :
```
Écriture par le méta-outil remember (réponse tool_result de la brique global_memory) et par l'action forcée « Écrire en mémoire », tous deux créés ici sur le mécanisme d'actions armées de la story 9 (AD-3, AD-25) ;
```
La dépendance « Dépend des stories 9 et 10 » est inchangée.

**S6 — Story 17, `invoke_dev_with`**

OLD : `… un rejeu après changement utilise le nouveau modèle. … Dépend des stories 9 et 11.`
NEW : `… un rejeu après changement utilise le nouveau modèle (story 9b). … Dépend des stories 9b et 11.`

**S7 — Story 19, `invoke_dev_with`**

OLD :
```
Méta-outil delegate et action forcée « Déléguer au sous-agent » posés en story 9 (AD-25) ;
```
NEW :
```
Méta-outil delegate et action forcée « Déléguer au sous-agent » créés ici sur le mécanisme d'actions armées de la story 9 (AD-3, AD-25) ;
```
La dépendance « Dépend des stories 9 et 11 » est inchangée.

### `deferred-work.md`

**S8 — Deux entrées reprises par 9b**

- Entrée « Rejeu du dernier prompt… » (`source_spec: none`) : ajouter `resolution: Planifié en story 9b (stories.yaml), sprint-change-proposal-2026-09-25-story-9b.md.`
- Entrée de la story 6b « Au rejeu… `_loaded_docs` doivent suivre la branche rejouée » : ajouter la même `resolution`.

Précédent : l'entrée 6c reprise par la story 8e.

### SPEC, PRD, architecture, UX

Aucun changement.

## 5. Statut de la proposition « dépôt privé »

`sprint-change-proposal-2026-09-25-depot-prive.md` est au statut `proposée`. Les passages OLD de P1 à P12 correspondent toujours au texte actuel des fichiers. Deux points de cette proposition ont vieilli depuis :

- Elle dit que « le palier 2 n'est pas encore découpé ». Or les stories 11 à 21 existent maintenant. Trois d'entre elles écrivent « publiable » en citant NFR-11 (14 : « Mémoire de démonstration publiable », 15 : « Corpus publiable », 21 : « Contenu publiable »). Ajouter **P13** : remplacer « publiable » par « non confidentiel » dans ces trois stories, pour que le critère de succès (`grep … "Contenu publiable"`) passe.
- Sa passation prévoit un commit « sur `spec/v2` ». Cette branche est déjà fusionnée dans `main`. Il faut donc appliquer la proposition sur la branche de travail courante.

**Recommandation : approuver et appliquer**, avec P13 et la correction de la passation. La décision de fond a été prise pendant la forge V2, et le remote est déjà privé. L'impact se limite à du texte, sans code. Laisser la proposition en attente garde le contrat en contradiction avec la réalité, et la NFR-2 actuelle contredit les stories 12, 15 et 16 (embedding et reranker à côté du SLM).

## 6. Passation

- **Portée** : **mineure**. L'agent Developer applique directement les modifications.
- **Destinataire** : Developer (Anaël avec Claude). Appliquer S1 à S8, puis, si c'est approuvé, P1 à P13 de la proposition « dépôt privé ».
- **Critères de succès** :
  - `stories.yaml` contient la story 9b entre 9 et 10, et le YAML se charge sans erreur.
  - Plus aucune occurrence de « rejeu » ne renvoie à la story 9 seule dans `stories.yaml`, et 17 dépend de 9b.
  - Les stories 14 et 19 ne disent plus que `remember` et `delegate` sont « posés en story 9 ».
  - Les deux entrées de `deferred-work.md` portent leur `resolution`.
  - Aucune modification de code ni de test.
