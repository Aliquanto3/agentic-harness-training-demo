# Mesures réelles Anthropic (fournisseurs natifs 3/5), 2026-10-03

Clé `ANTHROPIC_API_KEY` lue dans l'environnement utilisateur de Windows et passée au seul
processus de mesure (jamais affichée, journalisée, écrite ni commitée). Dossier de données
temporaire. Garde réseau installée avec `api.anthropic.com` seul. Requêtes envoyées par
l'adaptateur `anthropic_messages` de la story (en-têtes `x-api-key`, `anthropic-version:
2023-06-01`, `anthropic-beta: thinking-binding-controls-2026-08-01`). Les mesures M1, A1 et
A2 passent par `AppSession` (briques Prompt système, Mémoire courte, Outils et Raisonnement
allumées), M2 et M3 par l'engine seul avec un corps écrit à la main.

12 requêtes, 10 facturées (les deux 400 ne le sont pas). **Coût total : 0,0258 $** (somme exacte des coûts non arrondis ; les lignes, arrondies au dix-millième, totalisent 0,0259 $ ; calculé
sur l'`usage` de chaque réponse et les prix déclarés ; à comparer à la console Anthropic).

## Résultats

| # | Mesure | Requête (sans clé) | Statut | Extrait de réponse | Coût |
|---|---|---|---|---|---|
| M3 | `block_binding` avec réflexion éteinte, Haiku 4.5 | `thinking: {type: "disabled", block_binding: {prefix_mismatch_behavior: "drop_block"}}`, `max_tokens` 64 | **400** | « thinking.disabled.block_binding: Extra inputs are not permitted » | 0 $ |
| M2 | `block_binding` avec réflexion éteinte, Sonnet 5, un outil | même `thinking`, outil `calculator` | **400** | même message | 0 $ |
| M2b | Sonnet 5 réflexion éteinte, sans `block_binding`, un outil | `thinking: {type: "disabled"}`, « Combien font 1234 × 5678 ? Utilise la calculatrice. » | 200 | bloc `tool_use` natif `calculator {"expression": "1234 * 5678"}`, aucun texte, `stop_reason: tool_use` ; 486 / 54 tokens | 0,0015 $ |
| M3b | Haiku 4.5 réflexion éteinte, sans `block_binding`, un outil | idem | 200 | bloc `tool_use` natif `calculator {"expression": "1234 × 5678"}` ; 605 / 58 tokens | 0,0009 $ |
| M1+A1 | Haiku 4.5 : action forcée (appel `calculator {"expression": "17*23"}` fabriqué par le harnais, sans bloc `thinking`), réflexion allumée (`enabled`, 1 024), puis un appel d'outil du modèle | `messages`: `user`, `assistant [tool_use SmmL1x47M]`, `user [tool_result "391"]` ; `thinking: {type: "enabled", budget_tokens: 1024, block_binding: …}` | 200, 200 | 1er appel : aucun bloc `thinking` reçu (réflexion sautée par Anthropic sur ce tour), `tool_use calculator {"expression": "4321 * 89"}` ; 2e : « 4321 × 89 = 384 569 » ; 998 / 141 puis 1 153 / 44 tokens | 0,0031 $ |
| A2 | Haiku 4.5 : tour Raisonnement (historique du tour précédent) | « Un train part à 9 h et roule 150 km à 100 km/h… » | 200, 200 | réflexion au canal Raisonnement (« Temps de trajet = distance / vitesse… »), puis `tool_use` ; le 2e corps renvoie le bloc `thinking` signé (accepté) ; réponse « 10 h 30 » | 0,0046 $ |
| M1+A1 | Sonnet 5 : même action forcée, réflexion adaptative résumée | `thinking: {type: "adaptive", display: "summarized", block_binding: …}` | 200, 200 | 1er appel : réflexion résumée reçue (en anglais) + `tool_use` ; le 2e corps renvoie le bloc signé après le `tool_use` fabriqué (accepté) | 0,0085 $ |
| A2 | Sonnet 5 : tour Raisonnement | idem A2 Haiku | 200, 200 | réflexion résumée (« 150 km at 100 km/h gives 1.5 hours… »), blocs des deux tours renvoyés signés, réponse « 10 h 30 » | 0,0073 $ |

Aucun événement `reasoning_dropped` : attendu, Haiku 4.5 et Sonnet 5 ne font pas le contrôle
d'historique (propre à Opus 5.5 et Fable 5.1), et les conversations n'ont pas changé de modèle.

## Réponses aux questions ouvertes de SPEC.md (CAP-2)

1. **Appel d'outil fabriqué par le harnais avec la réflexion active** : accepté par les deux
   modèles (200). Haiku 4.5 (réflexion manuelle) ne réfléchit pas sur le tour qui suit l'appel
   fabriqué (aucun bloc `thinking` reçu, sans erreur) ; Sonnet 5 (adaptative) réfléchit. Parade
   (1) non nécessaire : rien à éteindre.
2. **Sonnet 5 réflexion éteinte** : appel d'outil natif (`tool_use`), pas écrit en texte. Parade
   (2) non nécessaire : `off` reste `{type: "disabled"}`.
3. **`block_binding` avec `{type: "disabled"}`** : refusé (400) par les deux modèles. Parade (3)
   appliquée : `block_binding` ne figure que dans `reasoning.on` (`wavestack.toml`).
4. **`display: "summarized"` sur Sonnet 5** : accepté, la réflexion résumée arrive au canal
   Raisonnement.

## Recette de l'acceptation (« clé réelle »)

Un tour Outils et un tour Raisonnement avec chaque modèle aboutissent (`turn_ended`
`completed`, aucun `harness_error`), la réflexion s'affiche (Haiku au tour Raisonnement, Sonnet
aux deux) et les blocs `thinking` repartent signés dans l'appel suivant, acceptés par Anthropic.
Coût total des mesures : 0,0258 $, sous le plafond de 1 $ de l'acceptation.
