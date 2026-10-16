---
id: SPEC-wavestack-v1-1-vague-2
companions: [brownfield.md, mcp-tools.md, guardrails.md, finops.md, limites-harnais.md, ux/DESIGN.md, ux/EXPERIENCE.md]
sources:
  - ../../planning-artifacts/research/recon-mcp-en-ligne-2026-10-15.md
  - ../../planning-artifacts/research/recon-guardrails-cpu-2026-10-15.md
  - ../../planning-artifacts/research/recon-finops-harnais-2026-10-15.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# WaveStack V1.1, vague 2 : ouverture aux RSSI

## Why

La vague 1 rend WaveStack installable sans accompagnement. La vague 2 l'ouvre à un second public, les RSSI clients, à côté des apprenants. Aujourd'hui l'onglet MCP est trop abstrait (un glossaire, deux serveurs publics sans authentification), aucun contenu n'est filtré en entrée ni en sortie, les optimisations du harnais sont invisibles en coût, et les ateliers sont trop techniques pour un non-ingénieur. Un RSSI doit voir ce qu'un harnais contrôle, refuse, journalise et coûte, sans lire de code.

## Capabilities

- **CAP-1**
  - **intent:** Le MCP local (stdio) propose des outils concrets : créer un fichier ou un dossier dans un bac à sable, lire la RAM et l'état du système, faire une capture d'écran, et le glossaire existant.
  - **success:** Dans l'atelier MCP, chaque outil s'appelle depuis une question en français et produit un effet visible ; la capture est enregistrée dans le bac à sable et le modèle ne reçoit que son chemin et sa taille.
- **CAP-2**
  - **intent:** Chaque outil MCP porte un niveau de risque et une règle autoriser, demander ou refuser, réglable dans l'interface.
  - **success:** Avec la règle « refuser » sur la création de fichier, l'appel n'est pas exécuté, la Séquence montre le refus et sa raison, et le modèle reçoit une erreur qu'il restitue à l'utilisateur.
- **CAP-3**
  - **intent:** Un journal de sécurité consigne chaque appel d'outil, chaque décision d'autorisation et chaque verdict de garde-fou.
  - **success:** Après une démo, le journal liste ces événements horodatés avec outil ou garde-fou, décision et raison, sans aucun secret, et se télécharge en un clic.
- **CAP-4**
  - **intent:** L'atelier MCP se connecte au serveur MCP distant de GitHub par OAuth (flux device code d'une OAuth App WaveStack), avec un jeton fin en lecture seule en repli.
  - **success:** Le consentement GitHub s'affiche puis la question « y a-t-il des alertes de sécurité ouvertes sur ce dépôt ? » renvoie une liste lisible ; une demande d'écriture (fusion de PR) est refusée, par la politique WaveStack ou par GitHub (403), et ce refus est visible et journalisé.
- **CAP-5**
  - **intent:** Des garde-fous filtrent l'entrée et la sortie du modèle : toxicité, données personnelles en français, injection de prompt (optionnel). Ils se règlent dans une brique « Garde-fous » du Harnais. Chacun a un mode bloquer, signaler ou désactivé ; pour les données personnelles, signaler devient masquer (remplacement par `[TÉLÉPHONE]`, `[E-MAIL]`… avant envoi).
  - **success:** Un même exemple neutre est refusé en mode bloquer, passe annoté (ou masqué) avec son verdict en mode signaler, et passe sans annotation en mode désactivé ; le verdict apparaît dans la conversation et dans Orchestration ; sans jeton Hugging Face, le garde-fou injection apparaît « non installé » avec la marche à suivre.
- **CAP-6**
  - **intent:** Chaque garde-fou dispose d'exemples prêts à l'emploi : un qui déclenche, un qui passe.
  - **success:** Les exemples se lancent d'un clic, donnent le verdict attendu sur le poste de référence, et aucun ne contient de contenu dangereux réel.
- **CAP-7**
  - **intent:** Les optimisations du harnais deviennent visibles en tokens et en coût : économie du cache de prompt cloud, gain de la compression, coût et empreinte du sous-agent, réutilisation du KV-cache local.
  - **success:** Sur un tour avec cache cloud, compression et sous-agent, le compteur de l'appel affiche pour chacun le gain ou le surcoût en tokens et en dollars, avec son calcul déplié ; sur un modèle local, il affiche les tokens repris du KV-cache et le temps évité ; la barre affiche « économisé » à côté de la dépense, et son clic ouvre le bilan de la séance (sans optimisation / coût réel).
- **CAP-8**
  - **intent:** Une seule vue sert tous les publics, au niveau de détail le plus élevé : le détail technique (noms d'outils, champs d'API, JSON, scores) est replié derrière un chevron et se déplie sur place.
  - **success:** Aucune bascule de public n'existe ; sur chaque nouvel écran, tout détail technique s'ouvre et se ferme à la souris et au clavier sans quitter la page.
- **CAP-9**
  - **intent:** Une page « Sécurité » de la barre commune présente la matrice de risques des outils, les contrôles actifs (autorisations, garde-fous, hooks, liste blanche réseau, connexion GitHub), le journal et les limites de ce que le harnais ne protège pas ; un bouton « Journal » de la barre, sur toutes les pages, compte les refus et ouvre un aperçu.
  - **success:** Un RSSI répond, depuis la page Sécurité, à « quels outils peuvent écrire, qui l'a autorisé, qu'est-ce qui a été bloqué, et qu'est-ce qui n'est pas couvert ? » ; depuis n'importe quelle page, le bouton Journal montre les 5 derniers événements.
- **CAP-10**
  - **intent:** Les textes des ateliers LLM, RAG et MCP sont réécrits pour un non-ingénieur ; le jargon passe dans le détail déplié.
  - **success:** Une relecture par un non-ingénieur ne relève aucun terme technique non expliqué à sa première apparition dans chaque atelier.

## Constraints

- PC pro de 16 Go sans GPU : garde-fous sur CPU, chargés à la demande et déchargeables, 1,5 Go de RAM au plus pour l'ensemble, à côté du SLM.
- Aucun modèle gated requis par défaut : seul Prompt Guard 2 en demande un, et il reste optionnel. L'utilisateur le télécharge lui-même sous la licence Llama 4 Community ; WaveStack ne le redistribue pas.
- Aucune bibliothèque d'inférence ML (onnxruntime, torch, spaCy) n'est aujourd'hui une dépendance : les garde-fous vont dans une dépendance optionnelle, comme `compression`, installable sans droits admin.
- Dépôt public : aucun contenu dangereux réel, aucun secret. Le jeton GitHub n'apparaît ni dans le dépôt, ni dans le journal, ni dans la Séquence.
- Démo GitHub sur un compte en lecture seule et un dépôt public.
- Bac à sable : l'écriture est limitée à un dossier WaveStack ; tout chemin qui en sort une fois résolu est refusé. La capture d'écran n'est jamais envoyée au modèle et passe toujours par l'autorisation.
- Chiffres tiers non vérifiés (multiplicateur multi-agents « 15× », prix de cache OpenAI et Gemini) absents de l'interface tant qu'une source primaire ne les confirme pas.
- L'installation de la vague 1 reste sans accompagnement : rien de nouveau n'exige de compte ni de saisie pendant l'installeur.
- Code en anglais ; textes d'interface en français, avec surcouche en et de sous `content/i18n/`.
- Exécution autonome en lanes parallèles sur des fichiers disjoints, fusion automatique sur `main` après relecture et tests verts. Une suite pytest à la fois, en quarts ; E2E en série par tranches de 4 à 6.

## Non-goals

- Hébergement web avec API gratuites, multi-utilisateur, authentification de l'appli : perte du on-prem, clause EEE de Gemini (offre payante obligatoire pour des utilisateurs de l'EEE).
- Serveurs MCP Atlassian et Notion.
- NeMo Guardrails, Llama Guard, ShieldGemma et les guardrails 2B et plus.
- Routage ou cascade automatique de modèles.
- Plafond de dépense nouveau et lecture des factures fournisseur.

## Success signal

Devant un RSSI, sur un PC pro de 16 Go, une démo de 15 minutes montre un outil d'écriture refusé puis autorisé, un appel GitHub refusé, un garde-fou qui bloque puis masque le même exemple, l'économie du cache et de la compression, puis le journal téléchargé depuis la page Sécurité, sans terminal (flux 1 de `ux/EXPERIENCE.md`).

## Assumptions

- La capture d'écran peut ajouter une dépendance Python légère, installable sans droits admin.

## Open questions

- Prompt Guard 2 est publié en poids PyTorch : torch CPU (lourd) ou conversion ONNX hors ligne ? À trancher dans la story CAP-5.
- Peut-on renouveler le jeton (refresh token) d'une OAuth App sans client secret ? Sinon, l'utilisateur se reconnecte toutes les 8 h. À vérifier dans la story CAP-4.
- Portées de l'OAuth App WaveStack : les portées d'une OAuth App sont grossières (pas de lecture seule pure sur les dépôts). Quel minimum pour lire les alertes d'un dépôt public ? À trancher dans la story CAP-4.
