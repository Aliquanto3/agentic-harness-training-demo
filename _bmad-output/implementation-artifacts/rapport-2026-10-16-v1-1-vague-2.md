# Rapport du 2026-10-16 : V1.1, vague 2 (ouverture aux RSSI)

Plan : [plan-2026-10-16-v1-1-vague-2.md](plan-2026-10-16-v1-1-vague-2.md). Spec : `_bmad-output/specs/spec-wavestack-v1-1-vague-2/` (SPEC, companions, `ux/`, maquette v2, `stories.yaml`, specs de story avec leurs sections « Revue »).

## En bref

- **13 stories sur 13 fusionnées** sur `main`, plus 9 correctifs (dont #72 le 17/10). Chaque story : dev-story (Sonnet) → second avis (Haiku) → reviewer (Opus) → E2E par l'orchestrateur → fusion.
- **Suite pytest complète** en quatre quarts : 6 707 réussis ; un seul échec restant, `test_rag_lab_rerankers::test_the_reasons_are_translated[en]`, antérieur à la vague 2 (rejoué rouge sur 447f26d : dépend des modèles présents sur le poste).
- **E2E finaux** sur `main` (5 tranches, 30 scénarios) : **tous verts** (66, 112, 255, 167 et 108 vérifications) après les correctifs #66 et #67.
- **Coût final de la V1.1** : **221 $** (vague 1 : 39 $, vague 2 : 183 $). Une story de la vague 2 coûte environ **9 $ médian** hors orchestration, contre 16,57 $ en V1 (−45 %) ; environ 14 $ tout compris.

## Stories

| Story | PR | Contenu | Constats (2nd avis → reviewer) | E2E |
|---|---|---|---|---|
| 1 Politique MCP et journal | #47 | règle autoriser / demander / refuser par outil, journal de sécurité, CSV | 1 high (outil refusé exécuté dans la conversation), 3 medium, 4 low → corrigés | 52/52 |
| 2 Outils MCP locaux | #50 | bac à sable, RAM, capture d'écran | 2 medium (chemin 8.3 `ANAEL~1.YAH`, disque sans plafond) + 2 en revue → corrigés | 52/52 |
| 3 GitHub par OAuth | #55 | device flow de l'OAuth App WaveStack, jeton renouvelé, refus | 5 medium (page MCP en panne derrière un proxy, état « expiré », jeton figé) + 4 en revue → corrigés | 111/111 |
| 4 Moteur des garde-fous | #48 | toxicité multilingue ONNX, Presidio + motifs FR | 4 medium (contournement après 256 tokens, numéro fiscal jamais vu, téléphone au seuil) → corrigés | 120/120 |
| 5 Garde-fous dans le tour | #54 | filtrage réel, verdicts, brique interactive | **3 high** (texte bloqué affiché, message brut renvoyé au modèle, trace en clair) → corrigés en une passe | 88/88 |
| 6 FinOps cache et compression | #51 | économie du cache (net signé), compression en $ | 1 medium (somme de séance faussée) + 1 en revue → corrigés | 95/95 |
| 7 Sous-agent et KV-cache | #56 | ligne sous-agent, mémoire de contexte locale | 5 medium + 1 en revue → corrigés | 141/141 |
| 8 Textes briques, LLM, RAG | #52 | gloses pour un non-ingénieur | 7 medium (passe trop légère, glose fausse) → corrigés | 263/263 |
| 9 Barre commune | #60 | Dépense · économisé, bilan, Journal et aperçu | 5 medium + 2 en revue → corrigés ; ancienne jauge retirée | 174/174 |
| 10 Page Sécurité | #61 | cartes, matrice, contrôles, journal, CSV, limites | **2 high** (cartes recomptées sur la fenêtre de 500, flux rejoué en double), 6 medium → corrigés | 100/100 |
| 11 Textes atelier MCP | #57 | gloses | 8 medium (passe trop légère) → corrigés | 52/52 |
| 12 Docs et guide | #62 | `docs/securite.md`, guide, installation, README | 2 high (page Sécurité décrite avant d'exister), 2 medium → corrigés | docs |
| 13 Installation et Prompt Guard | #58 | bouton « Installer », Prompt Guard 22M ONNX | 1 high (licence Llama non acceptée explicitement), 4 medium + 3 en revue → corrigés | 102/102 |

Correctifs : #67 (message détaillé de la vérification RAG), #49 (guillemets), #53 (libellés du journal, E031), #59 (fenêtre de 4 096 tokens après les 5 outils locaux ; GitHub hors des listes publiques), #63 et #64 (contrôle de fuite de français et nom propre « Microsoft Learn »), #66 (barre commune à six onglets dans les E2E ; #65 fermée par erreur).

## Décisions prises en cours de route (à relire)

- **Story 4 livrée en deux temps** : moteur seul, branchement et UI en story 5 ; installation et Prompt Guard en nouvelle story 13 (13 stories au lieu de 12).
- **Sortie des garde-fous** : en Bloquer ou Masquer, la réponse n'est plus diffusée en direct (« Vérification par les garde-fous… »).
- **Garde-fou en erreur** : le tour continue (fail-open), verdict « erreur » visible et journalisé.
- **Portée des garde-fous** : conversation principale seulement ; ateliers, sous-agent, résultats d'outils et raisonnement non contrôlés (déclaré dans la brique, la doc et les limites).
- **« Demander » dans la conversation vaut refus** : seule la page MCP sait demander l'accord.
- **Prompt Guard** : miroir ONNX `gravitee-io` (pas de torch), mais licence Llama 4 montrée, case à cocher, accès au dépôt Meta vérifié avec le jeton, « Built with Llama ».
- **Descriptions des outils locaux raccourcies** pour tenir dans la fenêtre de 4 096 tokens (#59).

## Restes et écarts

- **`rag_lab` « fin de run »** : échec intermittent (3 fois dans une tranche, puis 3/3 et 255/255 verts) ; cause non trouvée ; le message d'échec affiche maintenant les champs en cause (#67).
- **Lecture seule GitHub** : WaveStack n'envoie jamais `X-MCP-Readonly` ; ce niveau de refus n'est pas activable aujourd'hui (documenté).
- **Réponse réelle de GitHub à un compte sans droit** : 403 HTTP (géré) ou `isError` (pas encore distingué) : à vérifier.
- **`/api/state`** parcourt tout le journal de séance à chaque appel ; la barre l'appelle à l'ouverture des panneaux : à indexer si une séance devient très longue.
- **`limites-harnais.md`** porte encore « brouillon à valider par Anaël ».
- **GIF du README refait le 17/10** (#69), avec une 6e séquence sur la page Sécurité, capturé sur un dossier de données jetable.
- **Défaut vu pendant la capture, corrigé le 17/10** (#72) : les contrôles actifs de la page Sécurité se dépliaient parfois sur un corps vide (« Autorisations des outils », hooks inactifs, garde-fou désactivé) ; chaque contrôle montre maintenant son réglage exact, testé en pytest et en E2E. Documentation auditée pour toute la V1.1 (#71). Après correction : suite pytest 6 710 réussis (2 échecs sous charge, verts rejoués seuls), E2E des 5 tranches verts ; GIF refait (#73).

## Recette d'Anaël

1. Les 4 flux de `ux/EXPERIENCE.md` (RSSI en 15 min, Karim et les garde-fous, formation, première connexion GitHub).
2. **GitHub réel** : connexion par code derrière Zscaler, renouvellement du jeton sans client secret, refus d'une fusion avec un compte sans droit (403 ou `isError`), état « expiré » le lendemain.
3. **Garde-fous** : bouton « Installer » sur le PC pro sans droits admin (poste installé par `install.ps1`) ; Prompt Guard avec un jeton Hugging Face, d'abord sans licence acceptée (refus propre), puis après ; **RAM des trois garde-fous ensemble** (toxicité + données personnelles mesurées à ~0,5 Go).
4. **Mémoire de contexte** sur un vrai llama-server : deux tours de suite, la ligne doit apparaître.
5. **Capture d'écran réelle** autorisée une fois : un PNG dans `mcp_sandbox/screenshots/`.
6. **Relire le texte des 12 limites** (`limites-harnais.md`) et le valider.
7. Rendu des nouveaux écrans en thème sombre et en projection.

## Coûts finaux (mesurés le 17/10 par `mesurer_couts.py`)

Coût en équivalent API, sortie réestimée (réflexion masquée non comptée). Les sessions sont rattachées à leur jour de démarrage.

| Périmètre | Coût | Contenu |
|---|---|---|
| Projet entier (V1 + V1.1) | 1 610 $, 396 agents | |
| **V1.1** | **221 $, 80 agents** | |
| dont sessions démarrées le 15/10 (vague 1) | 38,7 $ | cadrage, 5 stories, 3 recherches, recette, rapport |
| dont session de la vague 2 | 182,6 $ | spec, UX et maquettes, 13 stories, 9 correctifs, GIF, audit des docs |
| — orchestration (session principale, Opus) | 67,8 $ | 427 appels, contexte jusqu'à 866 k tokens |
| — sous-agents du 16/10 | 110,7 $ | |
| — sous-agents du 17/10 | 4,1 $ | correctif #72, audit des docs, second avis |

Par rôle, sur toute la V1.1 :

| Rôle | Modèle | Agents | Coût | Médiane |
|---|---|---|---|---|
| Orchestration (sessions principales) | Opus | 7 | 94,2 $ (43 %) | — |
| Développement (dev-story) | Sonnet | 24 | 89,7 $ (41 %) | 2,35 $ |
| Relecture (reviewer) | Opus | 19 | 35,8 $ (16 %) | 1,67 $ |
| Recherches (deep-recon) | Sonnet | 3 | 1,1 $ | 0,36 $ |
| Second avis | Haiku | 21 | 0,41 $ | 0,02 $ |
| Recherche dans le code (lookup) | Haiku | 5 | 0,12 $ | 0,01 $ |

Par story (dev + second avis + reviewer), vague 2 : de 2,9 $ (docs) à 14 $ (story 4), **médiane ≈ 9 $**, contre 16,57 $ par story en V1 (tout sur Opus) : **−45 %**. Tout compris (cadrage, orchestration, correctifs, GIF) : 182,6 $ pour 13 stories, soit environ 14 $ par story. Contexte médian du premier appel des sous-agents : 35 k (pas de skill ni de serveur MCP superflu). Expirations médianes par agent : 0 ; le TTL d'une heure ne serait pas rentable.

## Recommandations pour optimiser les prochains projets

Classées par gain estimé, sur la base des mesures de la V1.1.

1. **Couper la session principale entre le cadrage et l'exécution** (gain estimé : 25 à 35 $ sur une vague comme celle-ci, soit environ 15 % du total). La session de la vague 2 a enchaîné spec, UX, orchestration de 13 stories et correctifs sans `/clear` : son contexte a fini à 866 k tokens et chaque appel le relisait. Faire le cadrage dans une session, écrire le plan et `stories.yaml`, puis `/rename` et `/clear` (ou une nouvelle session) pour orchestrer à partir de ces fichiers ; recommencer pour la phase de correctifs et de recette. Le plan, les specs de story et la mémoire suffisent à reprendre.
2. **Garder la chaîne Sonnet → Haiku → Opus** (déjà −45 % par story contre la V1). Le second avis Haiku coûte 2 centimes et trouve l'essentiel des défauts graves : ne jamais le supprimer. Le reviewer Opus reste justifié (1,7 $ médian) : il a trouvé et corrigé des défauts graves que le second avis avait manqués (flux rejoué en double, jeton figé après 8 h).
3. **Relire la spec des stories à risque avant le code** (`spec_checkpoint`, 10 à 15 min d'humain par story). Les deux passes de textes trop légères, la story 4 livrée à moitié et l'écart de licence de Prompt Guard ont coûté une relecture ou une story de plus chacun (3 à 14 $ et une à deux heures).
4. **Lancer la suite complète à mi-parcours, pas seulement à la fin.** Trois défauts croisés entre stories (libellés du journal, fenêtre de 4 096 tokens, fuite de français) n'ont été vus qu'à la fin et ont demandé des correctifs séparés. Une suite après 3 ou 4 fusions coûte environ 30 min de machine et aucun token.
5. **Donner les attentes E2E à mettre à jour dans le prompt de toute story qui change une structure partagée** (barre commune, liste d'outils, schéma de trace). Quatre correctifs de la vague 2 étaient des attentes E2E périmées (#53, #59, #65/#66 et l'attente « Outils 5 »).
6. **Consigne de complexité : seulement chez le reviewer** (voir l'expérience plus bas) ; elle n'a rien changé chez le dev-story.
7. **Vérifier l'état de `main` avant chaque série d'E2E** (`git log -1`) : deux fusions ratées non vérifiées ont fait perdre 30 min d'E2E.
8. **Paralléliser une story et sa documentation**, la doc décrivant la spec puis réalignée après fusion : environ une heure gagnée sur la fin de la vague 2.
9. **Ne pas activer le TTL d'une heure** du cache : 0 expiration médiane par agent, il coûterait plus qu'il ne rapporterait.

## Comparaison estimative avec la chaîne BMAD complète

Le cadrage de la vague 2 a déjà utilisé BMAD (`bmad-spec`, `bmad-ux`). La comparaison porte sur le développement et la relecture. Référence : la V1, développée avec la chaîne BMAD (dev, puis `bmad-code-review` à trois relecteurs Opus en parallèle : « cas limites », « chasseur aveugle », « trous de vérification ») et tout sur Opus.

- **Coût** : environ 16,6 $ par story en V1 contre 9 $ ici (dev, second avis, reviewer), soit **7 à 8 $ d'écart par story, environ 100 $ sur les 13 stories**. L'écart vient surtout du modèle de l'implémenteur (Sonnet au lieu d'Opus) et de la relecture : trois relecteurs Opus parallèles (environ 2 $ chacun en V1) remplacés par un second avis Haiku (2 centimes) et un seul reviewer Opus (1,7 $). Estimation, pas un A/B : les stories ne sont pas les mêmes.
- **Vitesse** : comparable. Le goulot était la relecture séquentielle et l'E2E unique, pas l'implémentation. BMAD aurait parallélisé les trois lentilles de relecture (plus rapide par story), mais au prix fort.
- **Qualité du code** : pas de perte visible. Le second avis Haiku, pour 2 centimes, a trouvé l'essentiel des défauts graves (outil refusé exécuté, texte bloqué affiché, cartes faussées, licence non acceptée), et le reviewer Opus en a ajouté sur presque chaque story (flux rejoué en double, jeton figé après 8 h). Trois défauts sont passés malgré tout et n'ont été vus qu'aux E2E finaux ou à la suite complète (libellés du journal, fenêtre de 4 096 tokens, fuite de français), soit des effets croisés entre stories qu'aucune relecture par story ne voit : une suite complète plus tôt (après 3 ou 4 fusions) les aurait attrapés avant, quelle que soit la chaîne.
- **Qualité du cadrage** : BMAD a bien servi là où il a été utilisé. La maquette et les options cliquables ont fait trancher Anaël tôt (vue unique au lieu de deux vues, page Sécurité + compteur, dépli sur place), et le test réel du device flow avant le code a évité un mauvais choix technique. Ce qui a manqué : une spec par story revue avant le code (`spec_checkpoint` de BMAD, refusé au cadrage pour aller vite). Elle aurait probablement évité les deux passes trop légères (stories 8 et 11), la story 4 livrée à moitié et l'écart de licence de Prompt Guard ; coût estimé : 10 à 15 min d'Anaël par story à risque.

**Recommandation** : voir la section « Recommandations pour optimiser les prochains projets » (points 2 à 4).

## Expérience : consigne de complexité

| Groupe | Stories | Constats du reviewer | Corrigés | Coût dev-story |
|---|---|---|---|---|
| Avec consigne | 2, 5, 7, 9, 10 | 9 | 6 (dont 1 vrai défaut de justesse : cartes recomptées sur la fenêtre de 500) | 32,6 $ (6,5 $ en moyenne) |
| Sans consigne | 1, 3, 4, 6, 13 | 5 | 2 | 36,9 $ (7,4 $ en moyenne) |

Lecture : la consigne dans le prompt de développement **n'a pas évité les défauts de complexité** ; les stories qui l'avaient en ont eu davantage, mais ce sont aussi celles qui manipulent les structures qui grossissent (journal, barre, page Sécurité) : le groupe n'est pas comparable. Son coût est négligeable (pas d'écart de coût mesurable). C'est **le reviewer, avec la consigne, qui a trouvé et corrigé** tous les constats à impact réel. Recommandation : garder la consigne dans le prompt du reviewer, la retirer du prompt de développement.

## Incidents de la journée

- Un dev-story bloqué 10 min (relancé, travail intact).
- Deux fusions ratées par l'orchestrateur (PR #65 fermée avec sa branche supprimée, puis branche périmée) et 30 min d'E2E joués sur un `main` non corrigé ; vérification de `main` ajoutée avant chaque lancement.
- Un dev-story a lancé la suite complète malgré la consigne ; deux agents ont lancé `python -` par erreur, arrêtés aussitôt.
- Dossiers de worktree non supprimables (fichier verrouillé) : à nettoyer.
