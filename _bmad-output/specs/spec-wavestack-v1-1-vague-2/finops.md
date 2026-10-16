# Mesures FinOps à rendre visibles (CAP-7)

Toutes s'appuient sur des données déjà lues par WaveStack ; aucun nouvel appel API.

| Mesure | Données sources | Calcul affiché |
|---|---|---|
| Économie du cache cloud | Anthropic `cache_read_input_tokens`, `cache_creation_input_tokens` ; OpenAI `prompt_tokens_details.cached_tokens` ; Gemini `usageMetadata.cachedContentTokenCount` ; prix `cache_read_usd_per_mtok`, `cache_write_usd_per_mtok` (`config.py:168-172`) | Coût réel contre coût au prix plein d'entrée ; l'écriture en cache (Anthropic : 1,25× à 2× le prix d'entrée) est une ligne distincte. |
| Gain de la compression | Tokens du contexte avant et après Headroom | Tokens économisés × prix d'entrée du modèle actif ; zéro dollar en local, mais tokens affichés. |
| Sous-agent | Coûts et empreintes du tour (`_turn_costs`, `_turn_impacts`, `app_session.py:1031-1036`) | Ligne dédiée : tokens, coût et empreinte du sous-agent, séparés du tour principal. |
| KV-cache local | llama-server `timings.cache_n`, `prompt_n`, `prompt_per_second`, `predicted_per_second` | Tokens repris du KV-cache sans recalcul et débit de préremplissage, pendant local et gratuit du cache cloud. |

Le coût est marqué « ≈ » quand l'usage est estimé (`usage_source = estimate`), comme aujourd'hui.
