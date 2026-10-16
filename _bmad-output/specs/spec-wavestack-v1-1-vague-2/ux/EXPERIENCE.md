---
title: EXPERIENCE — WaveStack V1.1 vague 2 (sécurité, garde-fous, FinOps)
status: final
created: 2026-10-16
updated: 2026-10-16
sources:
  - ../SPEC.md
  - ../../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
  - DESIGN.md
---

# WaveStack vague 2 — Experience Spine (delta)

Delta sur l'[EXPERIENCE.md principal](../../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md). Composants visuels : [DESIGN.md](DESIGN.md). Maquette de référence : [../maquette-vague-2.html](../maquette-vague-2.html) (v2) ; ce fichier l'emporte en cas de conflit.

## Foundation

Appli web locale, bureau, Edge ou Chrome sous Windows, souvent projetée. Système d'interface : celui de WaveStack (static/tokens.css, composants du DESIGN.md principal). **Une seule vue** pour tous les publics (RSSI, apprenants, formateur) : tout est visible au niveau de détail le plus élevé, et le détail technique (noms d'outils, champs d'API, JSON, scores) est replié derrière un chevron. Il n'y a pas de bascule de public.

## Information Architecture

| Surface | Où | Contenu | CAP |
|---|---|---|---|
| Page **Sécurité** (nouvelle) | Entrée « Sécurité » de la barre commune, entre MCP et Diagnostic | 4 cartes-questions (peut écrire, autorisé par vous, bloqué, non couvert) ; matrice des risques avec lien « Régler dans MCP » ; contrôles actifs dépliables (autorisations, 3 garde-fous, hooks, liste blanche, connexion GitHub) ; journal complet avec « Télécharger (CSV) » ; 10 limites dépliables | CAP-3, CAP-9 |
| Bouton **Journal** de la barre | Barre commune, toutes les pages | « Journal » + compteur rouge des refus et blocages de la séance ; au clic, panneau des 5 derniers événements dépliables et lien « Tout le journal » vers la page Sécurité | CAP-3 |
| Bouton **Dépense** de la barre | Remplace « Dépense estimée » | « Dépense 0,033 $ · économisé 0,029 $ » ; au clic, panneau « Bilan de la séance » (barres sans optimisation / coût réel, pourcentage, répartition cache / compression, temps évité en local) et lien « Détail par appel » | CAP-7 |
| Brique **Garde-fous** (nouvelle) | Panneau des briques du Harnais, après Hooks | Toxicité, Données personnelles, Injection de prompt ; mode par garde-fou ; boutons « Essayer : … » ; installation de Prompt Guard repliée ; mémoire chargée | CAP-5, CAP-6 |
| Verdicts des garde-fous | Vue humain (bandeau sous le message) et Orchestration (étape) | Bloqué, masqué, rien détecté ; détail repliable (garde-fou, score, seuil, entités, mode) | CAP-5 |
| **Serveurs et outils** (MCP) | Volet existant | Un sélecteur Autoriser / Demander / Refuser par outil ; niveau de risque ; bloc GitHub (connexion par code, état, détail repliable) | CAP-1, CAP-2, CAP-4 |
| **Séquence** (MCP) | Volet existant | Refus et demande d'autorisation comme étapes de la séquence ; JSON dans le détail déplié | CAP-2 |
| Compteur d'appel | Orchestration, sous chaque appel | Lignes nouvelles et dépliables : cache de prompt, compression, sous-agent (cloud) ; mémoire de contexte (local) | CAP-7 |

## Voice and Tone

Règles du principal (vouvoiement, phrases courtes, nommer qui décide, nombres précis). Ajouts :
- Toujours dire **qui** a décidé : « refusé par la politique WaveStack », « autorisé une fois par vous », « bloqué par le garde-fou toxicité », « refusé par GitHub (403) ».
- Toujours dire **ce qui n'est pas parti** : « Le modèle ne l'a pas reçu », « L'outil n'a pas été exécuté », « Envoyé à GitHub : non ».
- Libellés d'exemples : « Essayer : message insultant », jamais le texte de l'exemple dans le bouton.
- Pas de jargon hors du détail déplié : « Créer fichier ou dossier » en ligne, `create_file` dans le détail.

## Component Patterns

- **Dépli sur place** (disclosure-row) : seul motif de détail technique. Plusieurs détails ouverts à la fois. Le refus le plus récent de la Séquence et le verdict bloquant d'Orchestration arrivent dépliés ; le reste arrive replié.
- **Panneaux de la barre** (bar-flyout) : non modaux, un seul ouvert à la fois ; se ferment par Échap, un clic ailleurs ou un changement de page.
- **Sélecteur de règle** : le changement prend effet au prochain appel, sans confirmation, et s'inscrit au journal.
- **Demande d'autorisation** : étape « à décider » dans la Séquence avec « Autoriser une fois » et « Refuser » ; l'appel attend la décision ; pas de modale.
- **Exemples des garde-fous** : un clic envoie l'exemple comme message de l'utilisateur, avec le mode en cours ; changer le mode puis relancer montre la différence.

## State Patterns

| Élément | États |
|---|---|
| Appel d'outil | autorisé · à décider · autorisé une fois · refusé par vous · refusé par la politique · refusé par GitHub (403) · chemin hors du bac à sable |
| Garde-fou | actif (bloquer, signaler/masquer) · désactivé · non installé (Prompt Guard sans jeton) · chargement · erreur de chargement (message + marche à suivre) |
| Verdict | rien détecté · bloqué · masqué (données personnelles) · signalé (toxicité, injection) |
| Connexion GitHub | non connecté · en attente du code (code affiché, délai de 15 min) · connecté (expire dans …) · expiré (bouton « Se reconnecter ») · erreur réseau |
| Compteur Journal | 0 : bouton sans compteur rouge · n > 0 : compteur rouge |
| Lignes FinOps | absente si la donnée n'existe pas (pas de cache, pas de compression, pas de sous-agent) ; « ≈ » si l'usage est estimé |

## Interaction Primitives

- Chevron : clic, Entrée ou Espace ; `aria-expanded` et `aria-controls`.
- Panneaux de la barre : Échap ferme et rend le focus au bouton.
- Sélecteurs (règle, mode) : groupe de boutons à `aria-pressed`, flèches gauche/droite entre segments.
- Lien « Régler dans MCP », « Tout le journal », « Détail par appel » : naviguent vers la surface qui porte le réglage ou le détail.

## Accessibility Floor

Règles du principal. Ajouts : chaque état a un mot en plus de sa couleur ; le compteur Journal a un libellé complet pour les lecteurs d'écran (« Journal, 3 refus ou blocages ») ; les verdicts arrivent dans une région `aria-live="polite"` ; le code GitHub est lisible en texte, sélectionnable.

## Key Flows

### Flux 1 — Anaël devant un client RSSI (démo pilotée, 15 min) — temps fort : le RSSI lit lui-même le refus

1. Page MCP. Anaël met « Créer fichier ou dossier » sur Refuser et demande au modèle de créer `notes.txt`.
2. La Séquence montre « Refusé par la politique de sécurité », déplié avec le JSON ; le compteur Journal passe à 1.
3. Il met la règle sur Demander, relance : l'étape « à décider » apparaît, il clique « Autoriser une fois ».
4. Il connecte GitHub (code sur github.com/login/device), demande les alertes de secrets exposés, puis une fusion de PR : refusée par la politique, compteur à 2.
5. Harnais, brique Garde-fous : « Essayer : message insultant » en Bloquer (bandeau rouge, « Le modèle ne l'a pas reçu »), puis « Essayer : coordonnées » en Masquer (le modèle reçoit `[TÉLÉPHONE]`).
6. Il ouvre « Dépense » : bilan de séance, −47 % grâce au cache.
7. **Temps fort** : il tend la souris au RSSI, qui ouvre « Journal », clique « Tout le journal », déplie la ligne de la fusion refusée et lit « Envoyé à GitHub : non ».
8. Page Sécurité : la section « Ce que le harnais ne protège pas » cadre la discussion ; Anaël télécharge le CSV pour le client.

### Flux 2 — Karim, consultant SOC, seul sur son poste après la session — temps fort : l'injection détectée

1. Harnais, brique Garde-fous : Injection de prompt est « non installé » ; il déplie « Comment l'installer ».
2. Il crée un compte Hugging Face, accepte la licence Meta, colle son jeton, clique Installer ; état « chargement », puis actif.
3. Il rejoue les exemples ; il déplie chaque verdict dans Orchestration pour lire score et seuil.
4. **Temps fort** : avec le document RAG piégé, le garde-fou injection signale la consigne cachée ; sans lui, il voit le modèle répondre BANANE.
5. Il vérifie dans la page Sécurité que la mémoire des garde-fous reste sous 1,5 Go.

### Flux 3 — Anaël en formation, douze consultants en salle — temps fort : le cache rend 21 secondes

1. Il pose deux questions de suite sur le modèle local ; le compteur de l'appel montre « Mémoire de contexte : 1 820 tokens repris sans recalcul ».
2. Il déplie la ligne : 230 tokens recalculés en 2,7 s contre 24 s sans cache.
3. Il passe à un modèle cloud ; la ligne « Cache de prompt » apparaît, il déplie le calcul prix plein / payé.
4. Il active le sous-agent ; la ligne « Sous-agent » montre son coût à part.
5. **Temps fort** : « Dépense » dans la barre, bilan de séance projeté : sans optimisation contre coût réel.

### Flux 4 — Léa, consultante cloud, la veille d'une démo — temps fort : le jeton expire comme prévu

1. Page MCP, bloc GitHub : « Se connecter à GitHub » ; le code s'affiche, elle le saisit sur github.com/login/device.
2. Connecté ; elle déplie le détail : droits, serveur, 46 outils.
3. Elle vérifie dans la page Sécurité la ligne « Connexion GitHub » : lecture, expire dans 8 h.
4. **Temps fort** : le lendemain, l'état est « expiré » avec « Se reconnecter » ; un appel GitHub sans connexion est refusé avec ce message, pas une erreur obscure.

## Responsive & Platform

Bureau d'abord (1 280 px de large sur le PC pro). Sous 1 000 px, les trois volets du Harnais s'empilent ; les panneaux de la barre gardent 460 px au plus et ne dépassent pas l'écran.

## Open Questions

- Le compteur Journal compte les refus et blocages de la séance : se remet-il à zéro au rechargement de la page, ou au redémarrage de l'appli ? Proposé : au redémarrage, comme le journal.
