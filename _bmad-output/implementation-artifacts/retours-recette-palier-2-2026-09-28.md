# Retours de la recette manuelle du palier 2 (2026-09-28)

Source : cahier de recette interactif (`cahier-recette-palier-2.html`, version en ligne), rempli
par Anaël sur le PC cible (Windows 11, CPU, 16 Go), branche `claude/dreamy-cerf-gdjtee` au commit
`6664df9`. Edge ouvert pendant la séance (lecture du cahier et interface WaveStack). Chaque
retour renvoie à la story qui le traite (`stories.yaml`, ids 22 à 32). Décisions prises le
2026-09-28 : fenêtre de contexte réglable (4 096 par défaut, 8 192, 16 384) ; budget mémoire
dynamique plafonné ; écran RAG avec FAISS et LanceDB ; tout est implémenté par Claude Code dans
le cloud.

## Bilan

| Test | Statut | Retour | Story |
|---|---|---|---|
| P1, P2 | OK | Carte Raisonnement conforme (768). | — |
| C1 Mémoire globale (N1) | KO (interface) | Lot A tenu : pas de relecture au 2e tour, 1,3 s (574 tokens en entrée). Mais : consigne du scénario trop longue dans la Vue humain (elle cache le prompt et la réponse) ; tiroir de la mémoire sans croix de fermeture, boutons « Tout effacer » et « Fermer » en bas, hors de vue, et trop semblables à « Enregistrer » et « Supprimer ». Question : les numéros de tour continuent après « Réinitialiser » (t4) ; est-ce voulu ? | 22 |
| C2 Raisonnement | OK | 134,3 s dans l'interface avec le budget 768 (111 s par script, Edge fermé) ; réponse juste. Délai accepté : on voit la réflexion s'afficher en direct. | — |
| C3 User-Agent | KO | « Données sortantes » (`outbound_request`) ne montre que `method`, `url`, `body` : aucun en-tête, donc pas d'User-Agent visible. | 23 |
| C4 Arrêter pendant un chargement | KO | Arrêt effectif après ≈ 25 s (fin de la sonde). Second essai : « WaveStack occupe 0 Mo sans le modèle actif » (faux ; le script mesurait 118 Mo après libération). Suggestion : budget mémoire calculé selon la RAM du poste. | 24 |
| C5 Briques indisponibles | OK | Mais llama3.2:3b (Ollama) est refusé : « demande environ 4,0 Go ; WaveStack occupe 149 Mo », alors qu'il tournait le 2026-09-27. L'encadré s'affiche avec minicpm5:1b-q4_k_m. | 24 |
| C6 Fichier incompatible | OK | Raison en français, mais avec un texte mal décodé : « abÃ®mÃ© », « modÃ¨le » (UTF-8 lu en cp1252). | 24 |
| C7 Compression | OK | 2 004 → 496 tokens ; un premier appel à Headroom rend 525 → 525 (texte non compressible, attendu). | — |
| C8 Script de l'index | OK | Message attendu, code 1. | — |
| C9, C10 llama-server | KO (poste) | `llama-server` n'est pas installé : « n'est pas reconnu comme nom d'applet de commande ». Le guide doit expliquer comment l'obtenir sans droits d'administrateur. | 28 |
| M1 Module 1 | OK | LLM nu : 2 000 ms. Avec Groq gpt-oss-120b : 2 464 utilisables (attendu pour Groq). « Enregistrer » du prompt système : aucun retour visuel. D11 et « Réinitialiser » de la mémoire : consigne du cahier incompréhensible. | 22, 28 |
| M2 Module 2 | KO (découverte) | « Avec quel outil puis-je voir des données sortantes ? Je n'en ai trouvé aucun. » | 23 |
| M3 RAG | KO (interface) | Le bouton « Reranking » reste violet quand la brique RAG est éteinte ; le griser ou le masquer comme « Lazy loading ». Autres vérifications non comprises (cahier). | 22, 28 |
| M4 MCP | KO | Groq : 1 307 / 2 464 avec deux serveurs complets, 395 en lazy loading ; trois serveurs : 2 221, 526 en lazy loading ; avec les trois en lazy loading, charger une documentation fait déborder. Demande : fenêtre plus grande. | 26 |
| M5 Skills | OK | gpt-oss-120b appelle `load_skill` (1,2 s) ; Qwen3.5-2B ne l'appelle pas, même quand on nomme le skill. | 27 |
| M6 Sous-agent | Non fait | Contexte LLM : alterner clairement entre l'agent principal et le sous-agent (onglets). « Annuler » du formulaire « Déléguer au sous-agent » ne fait rien. Consignes du cahier non comprises. | 22, 28 |
| X1 Où vont mes données ? | Non fait | Lazy loading affiché actif alors que la brique MCP est éteinte au lancement ; consigne du cahier non comprise. | 22, 27, 28 |
| X2 SOC | — | Non renseigné. | 27 |
| X3 IAM, Souveraineté | Non fait | « Que dois-je tester ici ? » | 28 |
| X4 NFR-2 | OK | Pic 3 270 Mo, sous 4 096. | — |
| D1, D2m | Non fait | « Que dois-je tester ici ? » | 28 |
| D3m Groq, Mistral | OK | Mistral : 429 « Rate limit exceeded » (quota). | — |
| D4m Relance | OK | — | — |
| Z1 D2 | Non fait | « Que dois-je tester ici ? » | 28 |
| Z2 D3 | Non fait | « Comment vider les clés API ? » | 28 |
| Z3 D9 | Non fait | Pas de quota Mistral. | — |

## Demandes de fonctionnalités (2026-09-28)

1. **Sélecteur de modèles** (story 25) : expliquer le préfixe « Local · Ollama » ; regrouper par
   éditeur et trier par taille ; un onglet qui dit, pour chaque modèle disponible, s'il raisonne
   (jamais, toujours, ou les deux modes).
2. **Panneau des briques** (story 22) : la brique Raisonnement en premier.
3. **Écran « LLM nu »** (story 29) : un écran à part, centré sur l'architecture d'un LLM sans
   l'agentique : tokenisation et vectorisation, réglages d'échantillonnage (température, top-k,
   top-p), chargement du modèle en mémoire, lecture du prompt (temps jusqu'au premier token), puis
   génération token par token en direct ; focus possible sur le raisonnement.
4. **Écran « RAG »** (story 30) : un écran à part, centré sur l'architecture RAG : ajouter,
   retirer et déplacer des composants, choisir la base vectorielle (dont FAISS et LanceDB), le
   modèle de recherche et le reranker.
5. **Mode sombre** (story 31) : sélecteur Système, Clair, Sombre.
6. **Contexte LLM lisible** (story 32) : texte groupé avec sa source en marge, JSON formatés,
   texte lu et texte produit distincts, appels successifs d'un tour lisibles.

## Réponses données en séance

- Numéros de tour après « Réinitialiser » : les identifiants `t{n}` restent uniques pour toute
  la session, car le journal et les traces s'y réfèrent. C'est voulu ; la story 22 décide
  s'il faut afficher un numéro de tour qui repart de 1 par conversation.
- 2 464 utilisables avec Groq gpt-oss-120b : attendu (réserve de sortie propre à ce modèle,
  raisonnement toujours actif).
- Compression 525 → 525 : un texte sans redondance (prose, extrait RAG) n'est pas réduit ; le
  journal, lui, passe de 2 004 à 496 tokens en gardant les lignes WARN et ERROR (transformation
  « search » de Headroom). C'est le comportement attendu.
