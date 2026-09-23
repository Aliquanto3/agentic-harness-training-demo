---
title: "Product Brief - WaveStack"
status: ready
created: 2026-09-22
updated: 2026-09-22
---

# Product Brief : WaveStack — Démonstrateur pédagogique de harnais agentique

## Executive Summary

Les collègues et clients de Wavestone savent déjà utiliser un chatbot. Ils ne savent pas ce qu'un harnais agentique ajoute à un LLM nu, ni pourquoi un skill, un MCP ou un hook changent radicalement ce qu'une IA peut faire — et donc où elle peut être déployée en toute confiance. WaveStack est une application locale, tournant sur CPU avec de petits modèles de langage (SLM), qui rend visible, brique par brique, ce que le harnais fait au LLM : raisonnement, mémoire, prompt système, outils, RAG, MCP, skills, hooks. Chaque brique s'active ou se désactive en direct, et l'utilisateur voit simultanément la réponse "humaine", ce qui apparaît dans le contexte du LLM, et comment le harnais orchestre l'appel. L'objectif n'est pas la qualité des réponses — de petits modèles CPU suffisent — mais la compréhension : donner aux équipes le vocabulaire et les repères pour raisonner sur l'agentique, l'hébergement des données et du LLM, et la souveraineté, puis imaginer des usages dans leur propre métier.

## The Problem

Les collègues de practices variées (voir "Who This Serves") et certains clients ont une expérience de chatbot grand public, mais pas de cadre mental pour l'agentique : ils ne distinguent pas un LLM nu d'un LLM outillé, ne savent pas ce qu'un harnais fait concrètement, et confondent souvent skill, plugin, outil et MCP. Conséquence directe : ils peinent à évaluer où sont hébergés le harnais, les données et le modèle chez un provider — un point critique pour des missions touchant à la souveraineté, la sécurité (SOC, IAM, DLP) ou la conformité — et ils n'arrivent pas à se projeter sur des cas d'usage agentiques dans leur propre pratique. Les ressources existantes (tutoriels en notebook, articles, docs officielles) expliquent l'agentique de façon abstraite ou textuelle ; aucune ne montre, dans une seule interface, l'effet incrémental de chaque brique du harnais sur un même LLM, avec la vue "humain" et la vue "harnais" côte à côte.

## The Solution

Une application web locale, pilotée par un backend Python (`uv`), qui fait tourner un petit LLM directement sur CPU/RAM (pas de GPU requis), et qui expose une interface en volets synchronisés :
- un panneau pour activer/désactiver des composants du harnais un par un ;
- un schéma d'architecture qui reflète en direct les composants actifs (avec des zones normalement masquées, comme le détail complet d'un skill ou d'un MCP, qu'on peut déplier) ;
- une vue "humain" : ce que voit un utilisateur final (prompt, réponse) ;
- une vue "LLM / harnais" : ce qui entre réellement dans le contexte du modèle (prompt système, description d'outils/MCP/skills, résultats d'outils) et comment le harnais déclenche les appels, parse les sorties, décide de s'arrêter.

La progression pédagogique suit l'ordre : LLM nu → raisonnement affichable/masquable → mémoire courte (rechargement des messages précédents) → prompt système (par défaut ou modifiable) → mémoire globale cross-conversations → outils → RAG (simple, puis reranking) → MCP (documentation complète, puis lazy loading) → skills → hooks. Les briques de base (LLM nu, mémoire, prompt système) restent présentes pour les nouveaux arrivants et les clients découvrant le sujet, mais l'effort porte sur MCP, skills et hooks, qui sont le vrai cœur pédagogique pour une audience qui maîtrise déjà les bases du LLM et de l'assistant IA.

## What Makes This Different

- **Transparence à double vue, en direct** : personne d'autre ne montre, sur le même écran et pour le même prompt, la vue "ce que voit l'humain" et la vue "ce que voit réellement le LLM/harnais" — la recherche de marché n'a trouvé aucun projet équivalent avec une UI à composants activables un par un ; l'existant est du tutoriel texte/notebook.
- **Tout tourne en local, sur CPU** : le démonstrateur incarne lui-même ce qu'il enseigne sur la souveraineté et le numérique responsable — pas de dépendance cloud, pas de coût d'inférence, installation visée sans droits admin.
- **Progressivité assumée** : chaque brique du harnais est isolable et observable séparément, plutôt que livrée comme un framework agentique monolithique à comprendre d'un bloc.
- Honnêteté sur la limite : la qualité des réponses du SLM n'est pas l'objectif ; l'avantage est pédagogique, pas une performance technique.

## Who This Serves

**Utilisateurs primaires** : collègues Wavestone de practices variées (cloud, cyber, agile, PO, BA, IAM, DLP, SOC, souveraineté, numérique responsable, transformation numérique) qui connaissent déjà les chatbots mais pas l'agentique — objectif : qu'ils repartent avec le vocabulaire et les repères pour situer une solution agentique (hébergement, données, LLM) et imaginer des cas d'usage dans leur métier.

**Utilisateurs secondaires** : nouveaux arrivants internes découvrant à la fois le LLM et l'agentique (les briques de base leur servent directement) ; clients, une fois le démonstrateur jugé assez abouti pour sortir en clientèle.

## Success Criteria

Après une session de formation, les participants doivent pouvoir :
- Expliquer ce qu'est un skill, un MCP, un hook, un harnais, et ce que chacun ajoute à un LLM nu.
- Distinguer prompt engineering, context engineering et harness engineering.
- Se poser la bonne question sur une solution agentique tierce : où est hébergé le harnais, où sont hébergées les données, où est hébergé le LLM.
- Formuler au moins une idée d'application agentique concrète pour leur propre métier.

Signal secondaire de traction : le démonstrateur est jugé assez solide pour être montré en clientèle sans adaptation majeure.

## Scope

**Dans le périmètre V1** :
- Les 10 briques pédagogiques listées dans "The Solution" (LLM nu → hooks), avec MCP, skills et hooks traités avec un niveau de profondeur comparable aux briques de base, pas comme un bonus superficiel.
- Au moins un MCP local et un MCP public, montrés d'abord en documentation complète, puis avec lazy loading.
- RAG simple + reranking (une architecture RAG plus avancée est explicitement hors V1).
- Un jeu d'outils suffisant pour illustrer le concept (le brief ne fige pas la liste ; les exemples cités — calcul/graphique, heure, email, recherche web, API publique, fichier local — sont des candidats, pas un engagement).
- L'interface à volets synchronisés (activation, schéma d'architecture, vue humain, vue LLM/harnais), la fusion ou non des vues LLM et harnais restant une décision UX à trancher lors de l'atelier UX, pas dans ce brief.
- Installation visée sans droits admin sur poste professionnel Windows ; objectif à atteindre du mieux possible, avec un repli assumé en mode démo pilotée si l'installation complète s'avère trop complexe.

**Explicitement hors V1 (repoussé en Vision / V2+)** :
- Le multi-agent avec plusieurs agents qui dialoguent entre eux, et le routage vers des modèles spécialisés (modèles de décision type Decision 1.0, modèle d'image).
- Les architectures RAG avancées au-delà du reranking (HyDE et au-delà).
- L'exposition client dès la première version — elle vient après validation interne.

## Vision

À terme, le démonstrateur peut monter en sophistication sans perdre sa lisibilité pédagogique : plusieurs agents qui collaborent et dont on peut inspecter le contexte échangé, un routage vers des modèles spécialisés (décision, image) pour montrer l'hétérogénéité des architectures agentiques modernes, des architectures RAG avancées interchangeables (HyDE, self-RAG...). Une fois éprouvé en interne, il devient un outil de démonstration client crédible sur l'agentique et la souveraineté — cohérent avec l'ADN "IA locale responsable" déjà porté par des initiatives internes comme wavelocalai.
