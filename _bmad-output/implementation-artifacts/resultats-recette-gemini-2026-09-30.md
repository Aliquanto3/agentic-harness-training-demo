# Recette réelle de l'endpoint Gemini (nuit du 2026-09-29 au 2026-09-30)

## Conditions

- **Poste :** le PC cible (Windows 11, sans droits administrateur, i5-1145G7, 16 Go).
- **Code :** branche `feat/gemini-ai-studio` (PR #3).
- **Clé :** clé AI Studio de l'utilisateur, lue dans un fichier hors du dépôt, jamais affichée.
- **Lancement :** WaveStack réel sur un dossier de données jetable, piloté par Playwright (Chromium sans affichage) et par l'API. Les modèles locaux sont masqués (`OLLAMA_MODELS` et `HF_HUB_CACHE` vides), pour que le diagnostic ne sonde pas les modèles d'Ollama et du cache Hugging Face.
- **Coût :** sondes directes et recette ensemble, bien moins de 0,05 $.

## Résultat : 73 vérifications sur 76

| Étape | Résultat |
|-------|----------|
| Diagnostic : clé fournie par `GEMINI_API_KEY`, hôte `generativelanguage.googleapis.com` autorisé | OK |
| « Tester » : deux appels, le 2e rejoue la signature du 1er, test réussi | OK |
| Choix de Gemini, carte Raisonnement réglable sans verrou | OK |
| « Outils natifs », raisonnement éteint, 3 prompts : `get_datetime`, `calculator`, `read_file` appelés, tours `completed`, aucun `harness_error` | OK |
| Corps éteint : `reasoning_effort: "minimal"`, sans `extra_body`, `max_tokens` 512 | OK |
| Corps allumé : `extra_body…thinking_config {thinking_level: "low", include_thoughts: true}`, sans `reasoning_effort`, `max_tokens` 1 536 | OK |
| Signature rejouée au 2e appel de chaque tour (éteint et allumé) | OK |
| Texte sans balise `<thought>`, `usage_source` à `api` | OK |
| **Raisonnement allumé : réflexion reçue sur les 3 prompts d'« Outils natifs »** | **KO (3 fois)** : voir ci-dessous |
| Action forcée (calculatrice) : `skip_thought_signature_validator` envoyé, Google accepte, tour `completed` | OK |
| `/models` : groupe « Réseau · Gemini (Google) » | OK |
| Fuite de clé (journal complet et `wavestack.log`) : clé entière absente ; 4 premiers et 4 derniers caractères absents hors signatures | OK |

Réponses obtenues, par exemple :
- « Il est 00:06 (mercredi 30 septembre 2026). »
- « 1234 multiplié par 5678 font 7 006 652. »
- La liste exacte des ingrédients de `recette_crepes.txt`.

## Le seul écart : pas de réflexion à `thinking_level: "low"` sur des questions simples

Au niveau `low`, `gemini-3.5-flash-lite` ne réfléchit pas du tout sur les prompts d'« Outils natifs » : `total − prompt − completion` vaut 0. Il ne réfléchit pas non plus sur le prompt du scénario « Raisonnement » (le train de 14 h 47), sur 3 essais sur 3. La carte Raisonnement reste donc vide. Le code n'est pas en cause : le modèle juge qu'il n'a pas besoin de réfléchir.

Sondes sur le prompt du scénario « Raisonnement » :

| Niveau | Tokens de réflexion | Texte de pensée reçu (`<thought>`) |
|--------|---------------------|-----------------------------------|
| `low` (3 essais) | 0, 0, 0 | aucun |
| `medium` (2 essais) | 248, 277 | 1 fois sur 2 |
| `high` (2 essais) | 370, 587 | 2 fois sur 2 |

Tout tient dans la réserve de 1 536 tokens. Le point reporté de la revue (réserve mangée par la réflexion) n'est pas observé à ces niveaux.

**Proposition (décision de l'utilisateur) :** passer le raisonnement allumé à `medium`. La valeur `low` est dans la partie figée de la spec, qui appartient à l'utilisateur ; ce changement est donc proposé dans une PR à part, à fusionner ou non. Sans elle, le même effet s'obtient dans `settings.json` :

```json
{"cloud": {"models": [{"id": "gemini", "reasoning": {"on": {"extra_body": {"google": {"thinking_config": {"thinking_level": "medium", "include_thoughts": true}}}}}}]}}
```

## Autre constat : le premier lancement sur un dossier de données neuf

Au premier lancement, le diagnostic sonde un à un les modèles locaux trouvés (cache Hugging Face, Ollama : cinq modèles ici). Une sonde a pris jusqu'à 4,9 Go de RAM et plusieurs minutes. Pendant ce temps, « Tester » attend.

Sans effet sur la démo, qui utilise le dossier de données habituel, où les sondes sont déjà en cache (`probed_models`). À savoir pour une recette sur un dossier jetable.
