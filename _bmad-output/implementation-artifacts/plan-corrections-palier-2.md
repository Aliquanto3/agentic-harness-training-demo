# Plan de correction du palier 2 (après le test sur PC cible du 2026-09-27)

Source : test du guide `guide-test-pc-palier-2.md` sur le PC cible (HP EliteBook i5-1145G7,
16 Go, Windows 11, CPU seul), branche `claude/dreamy-cerf-gdjtee` au commit `ec107b4`, avec
Qwen3.5-2B Q4_K_M (unsloth). Chaque lot se traite par un passage de `/bmad-build`, dans l'ordre
ci-dessous. Les tests manuels reprennent une fois les lots 0 à G terminés (lot H ensuite).

## Ce qui marche déjà (ne pas casser)

- Installation : `uv lock` inchangé (entrées écrites à la main confirmées), `uv sync --extra
  compression`, `UV_SYSTEM_CERTS` (uv 0.12.19), aucun blocage AppLocker ni WDAC.
- Modèles RAG : sha256 identiques à l'oid LFS de Hugging Face ; index 8 documents, 29 extraits,
  384 dimensions, 5,6 s ; vrais modèles : le document des mots de passe arrive en tête.
- Instantanés MCP : datagouv 10 outils, mslearn 3.
- Parcours réel, côté harnais : LLM nu, mémoire courte, prompt système, mémoire globale
  (`remember` appelé seul), outils natifs, jours fériés, RAG (14 caractères), reranking (étape,
  scores 0,82 contre 0,02), MCP complet, lazy loading (`load_tool_doc`, appel réel), Caveman
  (76 → 28 tokens), H1/H2, sous-agent (délégation spontanée, `sub1`, résumé seul réinjecté),
  compression (2 004 → 496 tokens, erreur gardée), SOC (H1 bloque, audit complet), schéma
  « Où vont mes données ? ».
- Modèles : relance (dernier modèle rechargé), fichier incompatible (refus expliqué, modèle
  précédent gardé), Ollama (`qwen3.5:2b` et `llama3.2:3b`, « transparence réduite » avec ses
  deux comptes, `ollama ps` vide après changement et après fermeture), llama-server (diagnostic,
  `process: external`, outils), Groq (« Toujours active », 2 464 utilisables, 17 h 50), Mistral
  (`reasoning_effort` `high` puis `none` dans les corps envoyés).
- RSS maximale mesurée : 3 314 Mo (2B + embedding + reranker), sous le plafond de 4 Go.

## Décisions à prendre avant les lots concernés

| # | Question | Recommandation | Lot |
|---|---|---|---|
| N1 | Mémoire globale : une écriture modifie-t-elle le message système dès le tour suivant ? | Non : le message système garde l'instantané pris au début de la conversation ; l'entrée écrite est visible dans le tiroir et revient après « Vider la conversation » (c'est déjà la leçon du scénario). | A |
| N2 | Sous-agent : garder le cache du contexte principal pendant la délégation ? | Oui, par sauvegarde et restauration de l'état llama.cpp (`save_state` / `load_state`), si la mesure confirme le gain ; sinon afficher le coût. | A |
| N3 | Borne des résultats d'outils (MCP publics et outils réseau) | 1 200 tokens par résultat par défaut (`[tools] result_max_tokens`), coupe visible dans Orchestration et dans le texte réinjecté. | B |
| N4 | Raisonnement du 2B qui épuise la réserve | Budget de raisonnement : à 1 024 tokens de réflexion, le harnais ferme `</think>` et laisse 512 tokens pour la réponse ; la coupe est tracée. | C |
| N5 | 4B dans le budget de 4 Go | Le refus est juste (4,3 Go réels après 3 000 tokens). Garder D4 à 4 096 Mo, corriger l'estimation, et dire dans le guide que le 4B demande de relever le budget. | E |
| N6 | Moteur conseillé pour Qwen3.5 si le lot A ne suffit pas | llama-server (réutilise son cache entre les tours : 0,8 à 1,3 s au lieu de 23 s). À décider après la mesure du lot A. | A |

Décisions du rapport du week-end, d'après le test :
- **D1** : garder la compression en cours de tour (sans elle, le scénario Compression déborde : 3 762 tokens pour 3 584).
- **D4** : garder 4 096 Mo (voir N5).
- **D5** : garder le RAG éteint dans `mcp_full` (3 204 / 3 584) ; revoir son maintien dans `skills`, `subagent` et `compression` (extraits hors sujet à chaque question, lot H).
- **D6** : la leçon « escalader » ne passe pas par la consigne avec le 2B (lot H).
- **D2, D3, D9** : non testés, à faire au test manuel.

## Lot 0 — Consigner le test (sans code, à faire en premier)

- Commiter : `wavestack.toml` (sha256, commits Hugging Face, `measured_rss_mb` 430 et 740),
  `content/mcp_snapshots/`, `data/rag_index.sqlite` (1,6 Mo, recommandé : une installation neuve
  n'a rien à construire), `bench-headroom.json` et `bench-embed.json` déplacés vers la story 12
  (section « Verdict »).
- Annuler les captures E2E réécrites par le parcours Windows : `git restore tools/e2e/screenshots`.
- Ajouter à `deferred-work.md` une entrée par écart ci-dessous (format existant), avec la preuve
  du test du 2026-09-27.

## Lot A — Premier token : réutiliser le cache entre les tours (critique, NFR-1)

**Constat.** Avec le moteur intégré (llama-cpp-python), le premier appel de chaque tour relit
tout le contexte à ≈ 35 tokens/s : 20 s à 729 tokens, 43 s à 1 466, 111 à 119 s vers 3 200.
Qwen3.5 est hybride (`llama_model_is_hybrid` vrai) : llama.cpp ne sait pas tronquer son état à un
préfixe, donc toute divergence avec les tokens en cache force une relecture complète.
`prefix_not_reused` ne contrôle que l'intérieur d'un tour et n'a rien signalé.

**Causes vérifiées** (texte rendu au tour N+1 comparé au prompt + sortie du tour N) :
1. Le gabarit retire `<think>\n\n</think>\n\n` des réponses passées de l'assistant, alors que ces
   tokens sont dans le cache (tours t12 → t13 et t13 → t14 du journal).
2. La mémoire globale réécrit le message système dès qu'une entrée est ajoutée (t10 → t11) :
   divergence au tout début du prompt.
3. Le sous-agent occupe le même contexte llama.cpp : au retour, les 2 246 tokens du contexte
   principal sont relus (67 s ; tour du sous-agent : 275 s).

**Correction.**
- A1. En mode local, rendre l'historique exactement comme il a été produit : garder le bloc de
  raisonnement (vide ou non, selon ce qui a été généré) dans les réponses passées, pour que le
  rendu du tour N+1 prolonge le tour N (AD-4, « ajout seul », étendu à la conversation). Vérifier
  que la jauge et Contexte LLM restent justes.
- A2. Mémoire globale (décision N1) : instantané par conversation.
- A3. Contrôle entre les tours : comparer les ids du premier appel du tour aux ids en cache du
  moteur ; en cas d'écart, émettre `prefix_not_reused` avec la cause (réponse passée réécrite,
  message système modifié, rejeu, changement de scénario), pour que la relecture se voie en séance.
- A4. Sous-agent (décision N2) : sauvegarder l'état du contexte principal avant la délégation et
  le restaurer au retour ; mesurer le coût mémoire de la copie.
- A5. Test `model` (vrai GGUF) : deux tours de `native_tools` ; au second, le moteur n'évalue que
  les nouveaux tokens (compte relevé côté moteur), et un test sans GGUF sur le rendu (le texte du
  tour N+1 commence par le texte du tour N plus sa sortie).

**Critère d'acceptation sur le PC cible.** Second tour de `native_tools` : `prompt_ms` sous 3 s
(23 s aujourd'hui) ; quiz du sous-agent sous 15 s (68 à 99 s aujourd'hui). Si A1 à A4 ne
suffisent pas, décision N6.

## Lot B — Débordements causés par les résultats d'outils

**Constat.** Les résultats des MCP publics ne sont pas bornés : data.gouv (547 jeux, ≈ 2 500
tokens) fait déborder `mcp_lazy` (4 680 / 3 584) et `data_flows` (5 605) ; Microsoft Learn
(≈ 5 800 tokens) fait déborder `iam` (6 864). Le message de débordement cite à tort « les
descriptions d'outils ». `journal_serveur.log` (2 004 tokens, sans compression) fait déborder
`soc` (3 586). Le test `fits` estime `mcp_full` à 1 530 tokens pour 3 204 réels (4 caractères par
token, loin du vrai tokenizer sur ce contenu).

**Correction.**
- B1. Borne des résultats d'outils (décision N3) pour les outils MCP et réseau, avant la
  compression : coupe au dernier saut de ligne, mention « résultat tronqué : N tokens sur M » dans
  le texte réinjecté et dans l'étape d'Orchestration.
- B2. Cause du débordement tirée du `breakdown` réel : résultats d'outils, documentation
  d'outils, historique, extraits RAG, mémoire ; pistes adaptées (« question plus précise »,
  « allumez la compression », « videz la conversation »).
- B3. Test `fits` : compter avec un tokenizer réaliste (le vrai GGUF quand `WAVESTACK_TEST_GGUF`
  est posé, sinon un ratio calibré sur ce test : ≈ 2 caractères par token) et vérifier aussi la
  place laissée au premier résultat d'outil borné.

**Critère.** `mcp_lazy`, `data_flows`, `iam` et `sovereignty` aboutissent sans débordement avec le
2B ; le message cite la bonne cause.

## Lot C — Raisonnement du 2B sans réponse

**Constat.** Scénario Raisonnement : 1 536 tokens de réflexion, `output_truncated` sur le canal
`reasoning`, bulle vide, 137 s.

**Correction** (décision N4). Budget de raisonnement en mode local : au-delà du budget, le
harnais ferme la réflexion (`</think>`) et laisse la réserve restante à la réponse ; événement
tracé et affiché (« raisonnement coupé par le harnais à N tokens »). Carte de la brique : budget
et réserve. Test sans GGUF avec le faux moteur (`[raisonne]` long).

**Critère.** Le prompt du train donne une réponse, même courte, en moins de 120 s.

## Lot D — Outils réseau et parcours E2E

- D1. **Wikipédia répond 403** à `wikipedia_summary` et `fetch_page` : la politique robots de
  Wikimedia exige un contact dans l'User-Agent. Ajouter l'URL du dépôt à `USER_AGENT`
  (`src/wavestack/net/factory.py:28`) ; vérifié à la main : 200 avec
  `WaveStack/0.1 (demonstrateur pedagogique; https://github.com/Aliquanto3/agentic-harness-training-demo)`.
  Test : l'User-Agent contient une URL ou une adresse.
- D2. **E2E sur un poste connecté** : 30 échecs, tous dus à l'hypothèse « pas d'Internet »
  (`public_holidays`, data.gouv, Microsoft Learn répondent). Le lanceur E2E doit couper le réseau
  sortant lui-même (liste `allowed_hosts` réduite à la boucle locale dans le `settings.json`
  temporaire), pour que le parcours donne le même résultat partout.

## Lot E — Modèles : mémoire, refus et arrêt

- E1. **llama-server lancé sans `-c`** occupe 5 137 Mo (contexte par défaut très large), alors que
  WaveStack ne compte que la taille du fichier (1,28 Go). Lire `n_ctx` dans `/props` : si elle
  dépasse nettement la fenêtre, le signaler au diagnostic (« relancez llama-server avec
  `-c 4096` ») et compter une mémoire estimée réaliste. Guide et README : `-c 4096`.
- E2. **Estimation du 4B trop basse** : 3,4 Go estimés (`rss_bytes` 2,88 Go +
  `kv_bytes_per_token` × 4 096), 4,27 Go mesurés après 3 000 tokens (tampons de calcul non
  comptés). Ajouter les tampons de calcul au sondage (RSS après une évaluation réelle), puis
  resonder. Le 2B n'a ni `rss_bytes` ni `kv_bytes_per_token` (sondé avant la story 17) : resonder
  les entrées incomplètes.
- E3. **Message de refus** : « WaveStack occupe 0,0 Go sans le modèle actif » alors que le
  processus pèse ≈ 200 Mo. Afficher la vraie valeur (en Mo sous 1 Go).
- E4. **« Arrêter » pendant un chargement** : l'intention `stop` répond `stopping: false` pendant
  `model_load` (Ollama). Rendre le chargement annulable (le modèle précédent revient), ou masquer
  « Arrêter » pendant un chargement ; test E2E avec le faux Ollama lent.
- E5. **Ollama `llama3.2:3b`** : jauge à 141 tokens dans `native_tools` au lieu de ≈ 724, aucun
  outil proposé. À diagnostiquer (gabarit non reconnu ? briques ignorées sans le dire ?) ; si les
  briques ne peuvent pas s'appliquer, la carte doit le dire.
- E6. Raison d'un fichier incompatible en français : aujourd'hui « Chargement impossible :
  Failed to load model from file: … » (message brut de llama.cpp).

## Lot F — Headroom hors ligne et banc de la story 12

- F1. Headroom tente de joindre `openaipublic.blob.core.windows.net` : `COUNTING_MODEL = "gpt-4o"`
  demande `o200k_base`, que litellm 1.102.1 n'embarque pas (il n'a que `cl100k_base` et
  `p50k_base`). Passer à un modèle dont la table est livrée (`gpt-4`, `cl100k_base`), corriger le
  commentaire de `headroom_adapter.py:34` et le banc (variante configurée) ; test hors ligne :
  aucune tentative réseau à l'import et à la compression.
- F2. `[compression] cost_mb` : 57 Mo mesurés sur le PC cible (130 déclarés). Garder 130 par
  prudence ou passer à 80, à trancher avec F1.
- F3. Banc : le RSS « ajouté » est mesuré après la libération du modèle (3 à 6 Mo affichés).
  Mesurer au pic, modèle chargé (vraies valeurs : granite +428 Mo, reranker +736 Mo).
- F4. Candidat `e5small_q8` : « Failed to load model » avec llama-cpp-python 0.3.35, à retirer ou
  expliquer.

## Lot G — Tests qui ne tournent pas ou pas sous Windows

- G1. `test_an_index_replaced_during_the_session_is_read_again` et
  `test_an_index_replaced_with_the_reranker_loaded_closes_it` échouent sous Windows
  (`WinError 5` : `os.replace` sur un index ouvert). La carte RAG gère déjà ce cas (elle libère
  l'index avant). Pour le script : message clair (« WaveStack utilise l'index : construisez-le
  depuis la carte RAG, ou arrêtez WaveStack ») ; tests adaptés (fermer la connexion avant, ou
  vérifier le message sous Windows).
- G2. Tests `model` du RAG : `_isolated_data_dir` cache toujours les vrais modèles, ils sont
  toujours sautés. Ajouter une variable (`WAVESTACK_TEST_MODELS_DIR`) qui pointe vers le vrai
  dossier des modèles. Corriger `test_real_reranker_puts_the_password_document_first` :
  `score()` renvoie des `RerankScore` (`NamedTuple`), `0 <= s` lève `TypeError` ; comparer
  `s.score`. Vérifié à la main : scores 0,0 / 0,919 / 0,0.
- G3. Guide de test : 770 tests attendus, 774 collectés sous Windows (772 réussis, 2 échecs,
  1 sauté) ; mettre à jour après G1.

## Lot H — Scénarios et consignes (après les lots A à C, puis nouveau test)

Le comportement du 2B changera avec un contexte plus court et plus rapide : revoir ces points
après le test suivant, pas avant.
- H1. RAG hors sujet dans `mcp_lazy`, `skills`, `subagent`, `compression` : extraits sans rapport
  à chaque question (≈ 600 tokens), qui trompent le 2B (quiz répondus avec les extraits). D5 :
  éteindre le RAG hors du module 3 et de `mcp_lazy`, ou seuil de score.
- H2. Skills : le 2B appelle `load_tool_doc("meeting_minutes")` au lieu de `load_skill`.
  Descriptions des deux méta-outils à distinguer nettement (ou `load_tool_doc` absent quand le
  MCP n'a rien à charger dans ce scénario).
- H3. SOC (D6) : premier prompt, le 2B conclut « aucune attaque » ; second, après le blocage de
  H1, il continue d'explorer au lieu d'escalader. Consigne ou message de blocage de H1 qui dit
  explicitement quoi faire (« transmets à un analyste habilité »), ou validation humaine H5.
- H4. Compression, brique éteinte : le 2B ne lit pas le journal (il demande à l'utilisateur de le
  faire) ; prompt à rendre plus directif, ou action forcée proposée dans la consigne.
- H5. Souveraineté : le 2B charge la documentation mais n'appelle pas la recherche (aucun flux
  sortant réel) ; revoir après B1 en documentation complète.
- H6. Mesure Skills (248 s pour 1 760 tokens) faite sous pression mémoire (Edge ouvert,
  compression mémoire Windows ≈ 1 Go) : à refaire.

## Lot I — Guide de test et documentation

- Utilisables avec le raisonnement : 2 560 (le guide dit 3 072).
- llama-server : `-c 4096` dans la commande ; RSS attendue.
- Ollama `qwen3.5` : accepté et fonctionnel avec l'Ollama du poste (le guide attend un refus) ;
  garder le cas de refus pour une version d'Ollama qui ne sert pas `qwen35`.
- E2E : résultat attendu sur un poste connecté (après D2).
- 4B : refusé par le budget de 4 Go, et pourquoi (N5).
- Conditions de mesure : fermer Edge, Outlook et Teams.
- Mistral : un 429 dès « Tester » signale un quota épuisé (console Mistral).

## Tests manuels restants (après les lots)

Vérifications visuelles (raisonnement replié, schéma, tiroir mémoire, chronomètre, « Comparer »
par modèle), D2 (sans le fichier du reranker), D3 (lancement avec seulement un serveur), D9 et
Mistral avec un quota disponible, « Arrêter » pendant un chargement, puis le guide complet.
