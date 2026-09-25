---
title: Sprint Change Proposal — dépôt privé et règle des modèles génératifs
date: 2026-09-25
author: Anaël (avec Claude, workflow bmad-correct-course)
trigger: forge de l'idée V2 (`_bmad-output/forge/wavestack-v2-demo-client-vente-formations/forged-idea.md`)
scope: mineur
status: proposée
---

# Sprint Change Proposal — dépôt privé et règle des modèles génératifs

## 1. Résumé du problème

La forge de l'idée V2 (2026-09-25) a tranché deux points qui touchent le contrat de la V1.

1. **Le dépôt est privé.** Il est hébergé sur GitHub en privé, puis migrera vers le GitLab interne de Wavestone. L'option « dépôt public servant de vitrine » est rejetée. Or NFR-10, NFR-11 et CAP-37 supposent un dépôt GitHub public : « Dépôt GitHub public », « redistribution publique », « dépôt public », « installe WaveStack depuis GitHub ». Deux exigences restent en vigueur : des licences compatibles avec une remise du code à des clients (qui se négocie au cas par cas), et un contenu non confidentiel (la démo se fait chez le client, sur le poste du consultant).
2. **La règle « jamais deux modèles chargés à la fois » (NFR-2) est trop large.** La forge la reformule en « jamais deux modèles génératifs ». Prise à la lettre, la règle actuelle interdit d'ailleurs déjà en V1 l'embedding et le reranker du palier 2 (CAP-18, CAP-19), qu'AD-8 prévoit pourtant à côté du SLM.

**Nature** : un changement de stratégie (hébergement du dépôt) et une clarification d'une exigence ambiguë. Aucun défaut d'implémentation.

**Preuves** :
- `forged-idea.md`, sections « Principes verrouillés » (« Dépôt privé », « Jamais deux modèles génératifs ») et « À corriger dans la V1 » ;
- `SPEC.md` l. 135, 157, 165, 166 ;
- le remote actuel, `github.com/Aliquanto3/agentic-harness-training-demo`, est privé.

## 2. Analyse d'impact

### Epics et stories

`stories.yaml` couvre les stories 1 à 10 (palier 1). Le palier 2 n'est pas encore découpé.

| Story | État | Impact |
|---|---|---|
| 1 — Fondations | terminée | La tâche `README.md` porte CAP-37. Le README est corrigé (voie d'accès au code), et la ligne du fichier de la story est alignée. Le code n'est pas touché. |
| 6 — MCP local et public | terminée | Cite NFR-10 pour vérifier les licences des dépendances. L'exigence est conservée : rien à changer. |
| 7 — Skills, dont Caveman | terminée | Cite NFR-10 (proxy BSL-1.1 écarté, attribution MIT). Rien ne change. |
| 10 — Scénarios, programme, réinitialisation | à faire | Le contenu des scénarios reste soumis à NFR-11 (« contenu non confidentiel »). Le texte de la story ne change pas. |
| Palier 2 (RAG, reranking, compression, changement de modèle) | pas encore découpé | La nouvelle rédaction de NFR-2 lève la contradiction avec CAP-18 et CAP-19. Les futures stories s'appuieront sur « un seul modèle génératif à la fois ; tokenizer, embedding et reranker coexistent dans le budget ». |

Aucune epic n'est ajoutée, retirée ni réordonnée.

### Conflits d'artefacts

| Artefact | Passage | Action |
|---|---|---|
| `SPEC.md` | CAP-37, NFR-2, NFR-10, NFR-11 | Réécrire (P1 à P4) |
| `success-metrics.md` | SM-7 : « ni pour la publication du dépôt public » | Supprimer le membre de phrase (P5) |
| `ARCHITECTURE-SPINE.md` | AD-8 Prevents et Rule ; convention Dépendances ; CI « quand le dépôt est publié » | Réécrire (P6 à P8) |
| PRD `addendum.md` | Section « Dépôt public (NFR-10, NFR-11) » | Réécrire (P9) |
| `README.md` | Prérequis et `git clone https://github.com/<votre-org>/…` | Réécrire (P10) |
| Story 1 | Ligne `README.md` du plan de fichiers | Aligner (P11) |
| `CLAUDE.md` du projet | « Doit s'installer depuis GitHub » | Aligner (P12) |
| PRD `prd.md` | NFR-10, NFR-11, NFR-2 | **Non modifié** : c'est une source de traçabilité, et le SPEC est le contrat canonique (voir son frontmatter). Cette proposition documente l'écart. |
| UX (`DESIGN.md`, `EXPERIENCE.md`) | — | Aucun impact |
| Code, tests | — | Aucun impact. `LoadRegistry` n'impose pas aujourd'hui de règle « un seul modèle » à l'embedding ni au reranker, qui ne sont pas encore construits. |

Les domaines `github.com` du README et d'AD-21 servent au téléchargement de Python par `uv`, pas à l'hébergement du dépôt. Ils restent.

### Impact technique

Aucun changement de code, d'infrastructure ni de déploiement. Le seul effet visible est la procédure d'installation du README, qui ne dépend plus de l'hébergeur.

## 3. Voie recommandée

**Ajustement direct.** Il s'agit de corrections de texte dans le contrat, l'architecture et le README. Pas de rollback ni de révision du MVP.

- **Effort** : faible (environ 12 modifications de texte).
- **Risque** : faible. Seul point à surveiller : l'accès des participants au code (SM-5, UJ-3). La procédure prévoit deux voies, un clone authentifié pour qui a accès au dépôt, sinon une archive zip remise par le formateur sur un partage interne.
- **Calendrier** : aucun effet sur le sprint.

## 4. Propositions de modification détaillées

### SPEC — `_bmad-output/specs/spec-agentic-harness-training-demo/SPEC.md`

**P1 — CAP-37**

OLD :
```
- **CAP-37** Installation sans droits admin (FR-35, palier 1)
  - **intent:** Un utilisateur installe WaveStack depuis GitHub (clone ou zip) sans droits administrateur.
  - **success:** Aucune étape ne demande d'élévation, de service ni de règle de pare-feu ; procédure documentée en français, une commande une fois les prérequis (Git ou zip, `uv`) en place.
```

NEW :
```
- **CAP-37** Installation sans droits admin (FR-35, palier 1)
  - **intent:** Un utilisateur installe WaveStack sans droits administrateur, par un clone authentifié du dépôt privé (GitHub privé, puis GitLab interne Wavestone) ou depuis une archive zip (téléchargée depuis le dépôt, ou remise par le formateur sur un partage interne).
  - **success:** Aucune étape ne demande d'élévation, de service ni de règle de pare-feu ; procédure documentée en français, indépendante de l'hébergeur du dépôt, une commande une fois les prérequis (accès au dépôt et Git, ou archive zip ; `uv`) en place.
```

Justification : le dépôt n'est plus public. Un participant sans accès au dépôt doit pouvoir installer WaveStack avec une archive zip (UJ-3, SM-5). Ne nommer aucun hébergeur évite une nouvelle correction lors de la migration vers GitLab.

**P2 — NFR-2**

OLD :
```
… Un modèle servi en externe est compté tant qu'il répond ; jamais deux modèles chargés à la fois.
```

NEW :
```
… Un modèle servi en externe est compté tant qu'il répond ; jamais deux modèles génératifs chargés à la fois. Les modèles non génératifs (tokenizer, embedding, reranker) coexistent avec le modèle génératif dans le même budget.
```

Justification : c'est la décision de la forge V2. En V1, elle lève aussi la contradiction avec CAP-18, CAP-19 et AD-8, qui chargent un embedding et un reranker à côté du SLM. En V2, les classifieurs de routage entreront dans la catégorie des modèles non génératifs sans nouvelle modification.

**P3 — NFR-10**

OLD :
```
- **NFR-10 Licences.** Dépôt GitHub public, toutes dépendances et modèles embarqués sous licence compatible avec redistribution publique et démonstration client ; licences restrictives signalées avant adoption (Caveman proxy BSL-1.1 écarté, LM Studio propriétaire).
```

NEW :
```
- **NFR-10 Licences.** Dépôt privé (GitHub privé, puis GitLab interne Wavestone), dont le code peut être remis à un client au cas par cas : toutes dépendances et modèles embarqués sous licence compatible avec une redistribution à des clients et une démonstration client ; licences restrictives signalées avant adoption (Caveman proxy BSL-1.1 écarté, LM Studio propriétaire).
```

Justification : l'exigence de licence ne change pas. Seule sa raison change : ce n'est plus une publication, c'est une remise possible du code à des clients.

**P4 — NFR-11**

OLD :
```
- **NFR-11 Contenu publiable.** Rien de confidentiel dans le dépôt public (corpus RAG, scénarios, mémoire globale de démo, hooks) ; aucune donnée client, document interne Wavestone, secret ni clé d'API.
```

NEW :
```
- **NFR-11 Contenu non confidentiel.** Rien de confidentiel dans le dépôt (corpus RAG, scénarios, mémoire globale de démo, hooks), car il est montré et peut être remis à des clients ; aucune donnée client, document interne Wavestone, secret ni clé d'API. Le caractère privé du dépôt n'autorise aucune exception.
```

Justification : un dépôt privé ne rend pas le contenu confidentiel acceptable. Le contenu passe sous les yeux des clients pendant les démos, et le code peut leur être remis. La dernière phrase empêche de relâcher l'exigence au motif que le dépôt est privé.

### Indicateurs — `success-metrics.md`

**P5 — SM-7**

OLD :
```
… La validation par Wavestone de l'usage en clientèle n'est pas requise pour l'usage interne ni pour la publication du dépôt public ; à obtenir avant toute présentation client (V2).
```

NEW :
```
… La validation par Wavestone de l'usage en clientèle n'est pas requise pour l'usage interne ; à obtenir avant toute présentation client (V2).
```

Justification : il n'y a plus de publication. La condition 3 de déclenchement de la V2 (validation Wavestone avant toute présentation client) est inchangée.

### Architecture — `ARCHITECTURE-SPINE.md`

**P6 — AD-8, Prevents et Rule**

OLD :
```
- **Prevents:** des composants qui se chargent sans se voir ; un dépassement de budget découvert trop tard ; deux modèles de langage en mémoire.
- **Rule:** Tout composant lourd passe par le `LoadRegistry` : modèle, tokenizer `vocab_only`, embedding, reranker, compresseur, modèle d’un serveur externe.
```

NEW :
```
- **Prevents:** des composants qui se chargent sans se voir ; un dépassement de budget découvert trop tard ; deux modèles génératifs en mémoire.
- **Rule:** Tout composant lourd passe par le `LoadRegistry` : modèle, tokenizer `vocab_only`, embedding, reranker, compresseur, modèle d’un serveur externe.
  - **Un seul modèle génératif (NFR-2).** Charger un modèle génératif, en processus ou servi, libère d’abord le précédent. Les composants non génératifs (tokenizer, embedding, reranker, compresseur) coexistent avec lui dans le budget.
```

Justification : l'architecture reprend la nouvelle règle de NFR-2. Le comportement est déjà celui du mode serveur (le modèle en processus est libéré), et le rendre explicite guidera les stories du palier 2.

**P7 — Conventions, ligne Dépendances**

OLD :
```
| Dépendances | Licence compatible avec une redistribution publique (NFR-10), vérifiée avant ajout, et règle d’adoption réseau d’AD-15. |
```

NEW :
```
| Dépendances | Licence compatible avec une redistribution à des clients (NFR-10), vérifiée avant ajout, et règle d’adoption réseau d’AD-15. |
```

**P8 — Décisions reportées, intégration continue**

OLD :
```
- **Intégration continue** (GitHub Actions, `ruff` et `pytest` sous Windows) : quand le dépôt est publié.
```

NEW :
```
- **Intégration continue** (`ruff` et `pytest` sous Windows) : à monter sur l’hébergeur définitif (GitLab interne), plutôt que sur GitHub puis une seconde fois après la migration.
```

Justification : l'événement déclencheur, « quand le dépôt est publié », n'arrivera plus.

### PRD — `prds/prd-agentic-harness-training-demo-2026-09-22/addendum.md`

**P9 — Section « Dépôt public »**

OLD :
```
### Dépôt public (NFR-10, NFR-11)

- Ajouter un fichier de licence au dépôt.
- Vérifier la licence de chaque modèle proposé au téléchargement :
```

NEW :
```
### Dépôt privé, code remis à des clients (NFR-10, NFR-11)

- Regrouper les mentions des tiers (licences OFL des polices, attribution MIT du skill Caveman). La licence de WaveStack lui-même relève de Wavestone ; la fixer avant toute remise du code à un client.
- Vérifier la licence de chaque modèle proposé au téléchargement :
```

Le reste de la section est inchangé : licences des modèles et corpus libre de droits.

Justification : le « fichier de licence » visait une licence open source pour un dépôt public. Un dépôt privé a besoin des mentions des tiers, qui existent déjà en partie (`web/static/fonts/*-OFL.txt`, `content/skills/caveman/NOTICE.md`), et d'une décision de Wavestone sur la licence de WaveStack elle-même.

### README — `README.md`

**P10 — Prérequis et procédure**

OLD :
````
**Prérequis :**
- Git (pour cloner le dépôt) ou un téléchargement en zip depuis GitHub.
- [`uv`](https://docs.astral.sh/uv/) installé pour l'utilisateur courant (aucun droit administrateur requis).

**Procédure :**

```bash
git clone https://github.com/<votre-org>/wavestack.git
cd wavestack
uv run wavestack
```
````

NEW :
````
**Prérequis :**
- Un accès au dépôt privé WaveStack et Git, ou une archive zip de WaveStack (téléchargée depuis le
  dépôt, ou remise par votre formateur sur un partage interne).
- [`uv`](https://docs.astral.sh/uv/) installé pour l'utilisateur courant (aucun droit administrateur requis).

**Procédure :**

```bash
git clone <adresse-du-dépôt>
cd <dossier-cloné>
uv run wavestack
```

Au premier clone, Git vous demande de vous authentifier auprès de l'hébergeur du dépôt. Avec
l'archive zip, décompressez-la, ouvrez un terminal dans le dossier obtenu, puis lancez
`uv run wavestack`.
````

Justification : la procédure ne dépend plus de l'hébergeur et couvre les deux voies retenues. Le reste du README (proxy, domaines pour `uv`) est inchangé.

### Story — `stories/1-fondations-lancement-diagnostic-modele-local.md`

**P11 — Plan de fichiers, ligne `README.md`**

OLD :
```
- `README.md` -- section installation en français (CAP-37) : prérequis (Git ou zip, `uv`), une commande, domaines à autoriser derrière un proxy (AD-21).
```

NEW :
```
- `README.md` -- section installation en français (CAP-37) : prérequis (accès au dépôt privé et Git, ou archive zip ; `uv`), une commande, domaines à autoriser derrière un proxy (AD-21).
```

Justification : la story terminée sert de référence de non-régression. Elle doit décrire le README tel qu'il sera.

### Instructions du projet — `CLAUDE.md`

**P12 — Contraintes**

OLD :
```
- Doit s'installer depuis GitHub sur un PC pro sans droits administrateur (objectif).
```

NEW :
```
- Doit s'installer depuis le dépôt privé (GitHub, puis GitLab interne) ou une archive zip, sur un PC pro sans droits administrateur (objectif).
```

## 5. Passation

- **Portée** : **mineure**. Les modifications sont appliquées directement par l'agent Developer.
- **Destinataire** : Developer (Anaël avec Claude), pour appliquer P1 à P12 et committer sur `spec/v2`.
- **Critères de succès** :
  - `grep -rn -i "dépôt public\|redistribution publique\|dépôt GitHub public\|Contenu publiable"` ne renvoie plus rien dans le SPEC, ses compagnons, l'architecture, l'addendum ni le README. Les rapports de revue historiques (`reviews/`, `review-*.md`) et `prd.md` sont exclus.
  - NFR-2 et AD-8 disent « modèles génératifs ».
  - Le README décrit les deux voies d'installation (clone authentifié, zip), sans adresse GitHub codée en dur.
  - Aucune modification de code ni de test : `uv run pytest` et `uv run ruff check` restent verts.
- **Hors périmètre** (issu de la forge, à traiter avec la V2) : question « envie d'approfondir » à ajouter au questionnaire du pilote ; message d'attente lors du déchargement et du rechargement d'un modèle génératif (routage V2) ; migration effective vers GitLab.
