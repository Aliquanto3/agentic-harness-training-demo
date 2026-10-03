---
id: SPEC-fournisseurs-natifs
companions:
  - formats-natifs.md
  - ../../planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Fournisseurs natifs : Anthropic et OpenAI comme modèles cloud

## Why

Anaël dispose d'un budget sur les API OpenAI et Anthropic (2026-10-03) et veut proposer leurs modèles dans WaveStack, à côté de Groq, Mistral, Gemini et Gemma. C'est une occasion à saisir, mais la couche cloud ne parle qu'un format, Chat Completions (`openai_chat`, AD-5), et aucun des deux fournisseurs ne s'en contente :
- les modèles GPT-6 n'appellent plus d'outils par Chat Completions (Sol aucun, Luna seulement sans raisonnement), et ne renvoient jamais le texte de leur raisonnement ;
- la couche compatible OpenAI d'Anthropic est destinée aux tests, ne renvoie pas la réflexion et ignore le cache de prompt.

Les briques Outils, MCP, Skills, Sous-agent et Raisonnement exigent donc leurs API natives : Messages pour Anthropic, Responses pour OpenAI.

## Capabilities

- **CAP-1** API déclarée par modèle (story 1)
  - **intent:** L'opérateur choisit l'API d'un modèle cloud dans sa déclaration (`api`), et la vue Contexte LLM montre le corps natif tel qu'il part.
  - **success:** Une entrée `openai_chat` produit un corps identique à l'octet près à celui d'avant l'epic. Une entrée d'une autre API passe par son adaptateur, et le corps envoyé est égal à `context_rendered.body` et à `outbound_request.body` du même appel.
- **CAP-2** Claude par l'API Messages (story 3)
  - **intent:** Le formateur utilise `claude-haiku-4-5` et `claude-sonnet-5` pour les tours, les outils, le sous-agent, « Tester » et « LLM nu », et voit la réflexion résumée de Claude au canal Raisonnement.
  - **success:** Sur un faux serveur SSE, puis en recette réelle, un tour Outils et un tour Raisonnement aboutissent, la réflexion s'affiche et les blocs `thinking` repartent signés.
- **CAP-3** GPT-6 Luna par l'API Responses (story 4)
  - **intent:** Le formateur utilise `gpt-6-luna` dans les mêmes parcours que CAP-2, avec le résumé de raisonnement au canal Raisonnement.
  - **success:** Sur un faux serveur SSE, puis en recette réelle, un tour Outils avec le raisonnement allumé aboutit et le résumé s'affiche.
- **CAP-4** Plafond de dépense de séance (story 2)
  - **intent:** Le formateur fixe un montant maximal par séance. Un appel tarifé n'est pas envoyé quand le total de la séance l'a atteint, et le coût d'un appel compte le prix réduit des tokens en cache quand l'entrée le déclare.
  - **success:** Un test avec un plafond bas montre que l'appel refusé n'atteint pas le réseau et que l'utilisateur lit pourquoi et comment relever le plafond. Un usage avec des tokens en cache donne le coût attendu.
- **CAP-5** Raisonnement abandonné rendu visible (story 3)
  - **intent:** Quand Anthropic jette des blocs de réflexion parce que le harnais a réécrit l'historique, le journal le dit, avec la cause.
  - **success:** Un test qui rejoue une réponse portant `input_transformations` produit l'événement attendu, en `fr`, `en` et `de`.

## Constraints

- **HTTP brut, sans SDK.**
  - Le client vient de `net/factory.create_client` (`test_net_single_factory.py` interdit tout autre client).
  - Aucune relance automatique : 429, 5xx et `overloaded_error` suivent la liste fermée d'AD-16.
- **Architecture.**
  - AD-5 est amendé : un adaptateur natif peut poser des en-têtes fixes déclarés (`extra_headers`), jamais secrets, et refusés s'ils sont tracés en clair.
  - Format pivot : la session garde son historique au format Chat Completions. Un traducteur par API écrit le corps natif dans le rendu segmenté (`render_chat_body`), si bien que les segments restent les octets envoyés (AD-4).
  - Une nouvelle décision AD-26 fixe le champ `api` et le format pivot. `ARCHITECTURE-SPINE.md` est mis à jour en story 1.
- **Raisonnement conservé d'Anthropic.**
  - Sur un compte créé après le 2026-08-31, un historique réécrit rend un 400. WaveStack réécrit l'historique par conception : fenêtre, troncature des résultats d'outils, compression, mémoire, briques changées en séance.
  - Toute requête `anthropic_messages` envoie donc l'en-tête `thinking-binding-controls-2026-08-01` avec `prefix_mismatch_behavior: "drop_block"`, et trace `input_transformations` (CAP-4). Mesuré en story 3 (2026-10-03) : `block_binding` est refusé (400) avec `{type: "disabled"}`, il ne part donc qu'avec la réflexion allumée ; l'en-tête part toujours.
- **Renvoi verbatim.**
  - Les signatures des blocs `thinking` et les items `reasoning` chiffrés repartent tels quels, à leur seul fournisseur, comme `extra_content` de Gemini.
  - Ils ne sont masqués que dans les événements (AD-15).
- **Plafond.**
  - `[finops] max_session_usd = 5` par défaut, réglable.
  - Il porte sur le total de la séance (le registre de `consumption_updated`, tous les appels tarifés compris) et se vérifie avant l'envoi. L'appel en cours n'est pas interrompu.
- **Non-régression.**
  - La batterie existante reste verte, et les corps `openai_chat` sont identiques à l'octet près.
  - Exécution sur le PC cible : `pytest` en quarts, E2E par tranches `--only`, au premier plan, jamais deux suites à la fois.
- **Textes.**
  - Le français va dans `content/messages.yaml`, l'anglais et l'allemand sous `content/i18n/{en,de}/`.
  - `hosting_text`, `training` et `notes_text` sont relus sur les conditions de chaque fournisseur au moment de l'écriture.
- **Données relevées le 2026-10-03.** Prix, noms et paramètres des modèles sont à revérifier à l'écriture des entrées (`pricing.checked`). Le détail par modèle est dans `formats-natifs.md`.

## Non-goals

- Pas de SDK, pas de couche compatible OpenAI d'Anthropic, pas de GPT-6 par Chat Completions.
- Pas d'activation du cache de prompt d'Anthropic (`cache_control`), pas de `count_tokens`, pas d'outils serveur (recherche web, exécution de code), pas de Batches, pas de Bedrock, Vertex ni Azure.
- Opus 5.5 et GPT-6.1 Sol ne sont pas activés : ils restent en commentaire dans `wavestack.toml`.

## Success signal

- Sur le PC cible, avec un plafond de 5 $, le formateur joue un scénario Outils et un scénario Raisonnement avec Haiku, Sonnet et Luna, réflexion visible pour chacun. Le coût affiché par WaveStack reste dans 10 % du coût relevé dans la console du fournisseur.

## Assumptions

- Haiku 4.5 et Sonnet 5 ne font pas le contrôle d'historique du raisonnement conservé (propre à Opus 5.5 et Fable 5.1). L'en-tête `drop_block` leur est envoyé quand même, sans effet.
- Le plafond est remis à zéro seulement au relancement, comme le total de la séance.
- Une démonstration complète coûte environ 0,60 $ avec Haiku, 1,25 à 3,80 $ avec Sonnet et 0,06 à 0,20 $ avec Luna, pour environ 120 appels (estimation du 2026-10-03).

## Open Questions

- Avec la réflexion active, Anthropic accepte-t-il un tour assistant `tool_use` fabriqué par le harnais (actions forcées) sans bloc `thinking` en tête ? À mesurer en story 3 : éteindre la réflexion pour ce tour, ou trouver une autre parade. **Réponse (story 3, mesuré le 2026-10-03) :** oui, Haiku et Sonnet l'acceptent ; Haiku ne réfléchit simplement pas sur cet appel. Aucune parade.
- Sonnet 5 sans réflexion écrit-il ses appels d'outils en texte, défaut connu d'Opus 5 ? À mesurer en story 3. Sinon, garder la réflexion à faible effort. **Réponse (story 3) :** non, appels d'outils natifs ; `off = {type: "disabled"}` gardé.
- EcoLogits 0.11 connaît-il `gpt-6-luna`, `claude-haiku-4-5` et `claude-sonnet-5` ? Sinon, estimer par un modèle proche avec `note_text`, comme pour Groq. **Réponse :** oui, EcoLogits 0.11.2 connaît les trois (vérifié le 2026-10-03).
- `gpt-6-luna` accepte-t-il `temperature` et `top_p` par l'API Responses ? Le champ `sampling` reste vide tant que ce n'est pas mesuré.
- Le proxy du PC pro laisse-t-il passer `api.anthropic.com` et `api.openai.com` ? À tester en story 5.
