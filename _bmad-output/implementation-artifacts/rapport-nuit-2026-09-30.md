# Rapport de la nuit du 2026-09-30 et de sa reprise (2026-10-01)

Plan : `plan-nuit-2026-09-30.md` ; état détaillé, étape par étape : `etat-nuit-2026-09-30.md`. Spec découpée en sept stories : `_bmad-output/specs/spec-corrections-2026-09-30/` (`SPEC.md`, `stories.yaml`, `stories/1-…` à `7-…`).

## 1. Résumé

- **Les sept stories sont livrées et fusionnées dans `main`.**
  - Stories 1 à 4 : version de démo, **PR #15**, fusionnée le 2026-10-01.
  - Stories 5 à 7 : **PR #16**, fusionnée à la suite de ce rapport.
- **Phase 1** (avant la nuit) : la branche Langues 2 à 5 a été fusionnée par la **PR #14**. pytest donnait 4 701 tests passés ; l'E2E, 842 vérifications et un échec connu instable (`gemini_shape`).
- **Phase 2** : les stories ont été menées par `/bmad-build-auto`. Les stories 3 à 6 ont été implémentées en parallèle, dans des working trees séparés. Chacune a ensuite eu une revue à quatre relecteurs, un triage écrit dans sa spec et des correctifs.
- **Interruption** : le 2026-10-01 au matin, Anaël a arrêté la nuit après la story 4 pour une démo dans la journée. La suite s'est faite dans une autre session, sur le working tree `wt-suite`. Jusqu'à la fin de la recette manuelle d'Anaël, elle n'a lancé ni serveur, ni E2E, ni modèle local. Elle a ensuite eu son accord pour les tests avec processus et le point de contrôle complet.
- **Phase 3** (recette Claude in Chrome dans Edge) : annulée. Anaël a fait une recette manuelle sur la version de démo. Ses deux correctifs (infobulle de consigne, arbre JSON des outils) sont dans `main`.

## 2. Stories

| # | Story | État | Revue |
|---|---|---|---|
| 1 | R0 : `/api/health` donne dossier et commit, le CLI dit d'où vient l'instance réutilisée | `done` (#15) | 7 correctifs, 13 rejets |
| 2 | Barre de navigation commune, barre de l'atelier en bas | `done` (#15) | 18 correctifs, 16 rejets |
| 3 | Pages Diagnostic et Modèles : tri, filtres, progression de la recherche | `done` (#15) | 35 constats, 9 correctifs, 2 différés |
| 4 | Constats différés : `rag_rerank` sous charge, table `cl100k_base` hors ligne | `done` (#15) | 27 constats ; vraie cause : course de notification du journal |
| 5 | « LLM nu » pédagogique : distribution vivante, comparaison A/B, schémas | `done` (#16) | 35 constats : 17 corrigés, 5 différés, 13 rejetés ; suivi : 3 corrigés |
| 6 | Atelier MCP (`/mcp`) : le protocole à manipuler | `done` (#16) | 44 constats : 21 corrigés, 3 différés, 20 rejetés ; suivi : 1 corrigé |
| 7 | Traductions restantes : messages du backend en `en` et `de` | `done` (#16) | suivi : 9 constats, 8 corrigés, 1 rejeté ; plus 1 défaut trouvé par l'E2E |

### Ce qui change pour le stagiaire (stories 5 à 7)

- **`/llm`** :
  - la section 2 montre les candidats d'un token avec leurs barres. La probabilité du modèle reste fixe, la chance d'être tiré bouge à chaque curseur ; le serveur fait le calcul (AD-1) ;
  - « Comparer » génère le même prompt avec deux réglages, A puis B, côte à côte ;
  - chaque section a ses questions ;
  - la section 4 dessine la fenêtre glissante.
- **`/mcp`**, nouvelle page en cinq sections, sixième lien de la barre commune :
  - les serveurs et leur transport ;
  - la poignée de main JSON-RPC, capturée réellement sur le transport ;
  - la documentation des outils et son poids en contexte, en documentation complète et en lazy loading ;
  - un appel à la main, avec la réponse brute et le texte réinjecté ;
  - ce que le modèle voit.

  L'atelier ouvre ses propres connexions : celles de la brique MCP ne changent jamais.
- **Langues** : en `en` et `de`, tous les messages produits par le harnais suivent la langue de la session : erreurs, raisons d'indisponibilité, erreurs d'outils lues par le modèle, troncature, refus des hooks, diagnostic, note GreenOps. Il y a 1 020 clés par langue. L'allemand vouvoie l'utilisateur et tutoie le modèle, comme le prompt système. Le terminal reste en anglais.

## 3. Vérification finale

- `ruff check` et `ruff format --check` : verts.
- pytest complet en quatre quarts : 3 559 + 666 + 313 (3 ignorés) + 311 passés, après correction de 6 tests de langue qui attendaient encore du français.
- Tests avec processus :
  - `test_engine_candidates` : 4 ;
  - `test_mcp_lab` : 19 ;
  - `test_mcp` et `test_mcp_lazy` : 35.
- E2E, 0 échec au dernier passage :

  | Tranches | Vérifications |
  |---|---|
  | `llm_screen bare_llm` | toutes passées |
  | `annex_language` | 29 |
  | `mcp_lab mcp_full mcp_lazy` | 39 |
  | `ui_language` | 28 |
  | `backend_language` | 16 |
  | `model_catalog rag rag_rerank rag_lab compression` | 163 |
  | `content_language language` | 34 |

  Nouvelles captures : 61, 62 (atelier MCP), 64 (comparaison A/B) et `backend-language-de-*`.

### Défauts trouvés par les tests avec processus et l'E2E, après la reprise (tous corrigés)

- `last_session` de l'atelier MCP reprenait des échanges d'une connexion antérieure du même journal. Il est maintenant borné au début de la dernière connexion.
- Après un changement de langue, les contrôles du diagnostic de démarrage et la note GreenOps d'un appel restaient en français. Un texte déjà rendu (`Said`) est maintenant rendu de nouveau dans la langue demandée. `run_call` et `Impact.fields` reçoivent la langue de la session.
- Le refus de mémoire de l'atelier RAG figeait le nom du modèle en français.

## 4. Décisions prises en cours de route

- **Tests réduits pendant la nuit**, décision validée par Anaël : niveau rapide par story. Deux points de contrôle lourds étaient prévus. Le second, la batterie de la phase 3, est remplacé par la recette manuelle et par le point de contrôle de la reprise.
- **Pas de PR empilée** : #16 visait `main` dès son ouverture, pour qu'elle ne soit pas fermée quand la branche de #15 serait supprimée.
- **Historique du journal dans l'E2E de langue** : les étapes du dernier chargement et les contrôles du diagnostic de démarrage sont des événements rejoués tels qu'ils ont été émis. Ils restent dans la langue de leur émission et sont les seuls mis de côté par la vérification. Dans un vrai usage, ils sont produits dans la langue réglée au lancement.
- **Working trees** : `wt-story3` à `wt-story6` et les branches `wip/story-*` sont supprimés. `wt-suite` reste en place jusqu'à la clôture.

## 5. Constats différés (voir les specs)

- **Story 5** : la logique de page de la distribution et du schéma de fenêtre n'est pilotée par aucun test avec des données positives. Une piste : `page.route` sans moteur. L'arrêt par le bouton pendant une comparaison et la comparaison avec un modèle cloud ne sont pas testés non plus.
- **Story 6** : plusieurs fonctions de la page `/mcp` ne sont vérifiées que côté session :
  - préréglages ;
  - champs JSON ;
  - troncature ;
  - page hors ligne ;
  - bandeau « Occupé » d'un vrai tour ;
  - bouton « Arrêter » pressé.

  L'arrêt pendant un appel au glossaire local (stdio) n'est pas testé.
- **Préexistant** : la recherche BM25 de l'atelier RAG n'ignore que des mots vides français (`deferred-work.md`).
- **Petits restes** :
  - trois captures non suivies produites par d'anciennes tranches (`language-01`, `language-02`, `ui-language-de-barre-commune`) ;
  - le libellé allemand `session.compression.the_compressor` au nominatif, dans un chemin jamais pris.

## 6. Étape suivante

Recette manuelle des stories 5 à 7 sur `main` : l'écran « LLM nu », l'atelier MCP, l'interface et les messages en anglais et en allemand. Seule la démo, c'est-à-dire les stories 1 à 4, a été testée à la main.

- **Skill** : `/bmad-walkthrough`.
- **Prompt** :

  > Walkthrough des stories 5 à 7 des corrections du 2026-09-30 (PR #16, fusionnée dans main) : `/llm` (distribution vivante, comparaison A/B, schéma de la fenêtre), `/mcp` (poignée de main, poids des outils, appel, arrêt) et l'application en `en` puis `de` (messages du harnais, diagnostic, cartes). Specs : `_bmad-output/specs/spec-corrections-2026-09-30/stories/5-*.md`, `6-*.md`, `7-*.md`. Je teste sur le PC avec un vrai modèle local et un modèle cloud.

- **Modèle** : Opus 5.5. C'est le défaut pour un travail supervisé, et la recette se fait avec Anaël.
- **Effort** : `high`. Il faut vérifier des cas limites (arrêts, changement de langue, modèles serveur et cloud) que les tests automatiques ne couvrent pas tous.
- **`/clear`** : oui. Le contexte de cette session est très long et sans utilité pour la recette.
