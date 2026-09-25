# Alternatives cloud gratuites — Groq, Cerebras, GitHub Models, HF Inference Providers, Cloudflare Workers AI

Recherche du 2026-09-24. Budget : 16 appels d'outils, ~13 sources consultées.

## 1. Groq (GroqCloud free tier)

- Le "Free tier" GroqCloud n'exige pas de carte bancaire (opposé au "Developer tier" payant) et donne accès à tous les modèles hébergés, limité uniquement par le rate limiting — source : [Groq API Free Tier: Real Rate Limits and Free Models](https://localaimaster.com/blog/groq-api-free-guide) (localaimaster, non daté, consulté 2026-09-24) — confiance : moyenne — classe : tarif (agrégateur, pas de vérif primaire directe).
- Quotas indicatifs par modèle (agrégés, non vérifiés sur la doc officielle car le fetch primaire n'a pas exposé le tableau complet) : ~30 RPM / 6 000 TPM / 1 000 RPD pour la plupart des modèles, jusqu'à 200K TPD pour GPT-OSS-120B — source : [Groq Free Tier Limits 2026](https://tokenmix.ai/blog/groq-free-tier-limits-2026) (TokenMix, non daté, consulté 2026-09-24) — confiance : basse — classe : quota (agrégateur uniquement, chiffres non confirmés sur console.groq.com).
- Un prompt de 15 000 tokens en entrée risque de dépasser le TPM de 6 000 sur les modèles au quota par défaut — à vérifier avec la page de compte réelle avant la démo.
- Groq ne conserve pas les données client par défaut pour les requêtes d'inférence ; les métadonnées d'usage collectées ne contiennent pas les entrées/sorties client ; rétention max 30 jours si conservée pour debug/abus, avec option "Zero Data Retention" — source : [Your Data — Groq Docs](https://console.groq.com/docs/your-data) (Groq, non daté, consulté 2026-09-24) — confiance : haute — classe : données (source primaire officielle).
- API compatible OpenAI confirmée via les endpoints `/openai/v1/chat/completions` et `/openai/v1/responses` — source : [Your Data — Groq Docs](https://console.groq.com/docs/your-data) (Groq, non daté, consulté 2026-09-24) — confiance : haute — classe : compatibilité.
- Vitesse mesurée par un tiers : Groq atteint environ 293,6 tokens/s sur Llama 3.3 70B sous les conditions de test standardisées d'Artificial Analysis, et ~493 tokens/s sur GPT-OSS-120B selon des agrégats citant Artificial Analysis — source : synthèse WebSearch citant Artificial Analysis, page non lue directement (consulté 2026-09-24) — confiance : basse — classe : vitesse (source secondaire, pas la page Artificial Analysis elle-même).

## 2. Cerebras (Cerebras Inference free tier)

- **Contradiction trouvée** entre deux pages : la doc officielle des rate limits (`inference-docs.cerebras.ai/support/rate-limits`) décrit un "Free Trial" avec carte bancaire obligatoire ("$5 de crédits après ajout d'un moyen de paiement vérifié", API inactive sans CB) — source : [Rate Limits — Cerebras Inference](https://inference-docs.cerebras.ai/support/rate-limits) (Cerebras, non daté, consulté 2026-09-24) — confiance : haute — classe : tarif (source primaire).
- Plusieurs agrégateurs (LinkedIn, blogs) décrivent un "Free Tier" distinct sans carte bancaire, 1 million de tokens/jour, renouvelé chaque jour, actif depuis juin 2025 — source : [Cerebras Free Tier: 1M Tokens/Day, API Limits, and Speed Benchmarks](https://adam.holter.com/cerebras-opens-a-free-1m-tokens-per-day-inference-tier-and-ccerebras-now-offers-free-inference-with-1m-tokens-per-day-real-speed-benchmarks-show-2600-tokens-sec-on-llama4scout-here-are-the-actual-n/) (Adam Holter, non daté, consulté 2026-09-24) — confiance : moyenne — classe : tarif (source secondaire, mais recoupée par plusieurs agrégateurs indépendants).
- **Point bloquant potentiel pour la démo** : plusieurs sources indiquent que le contexte du free tier est plafonné à 8 192 tokens — cela exclurait des prompts de 15 000 tokens — source : [Cerebras API Key: How to Get & Rate Limits Explained (2026)](https://tokenmix.ai/blog/cerebras-api-key-rate-limits-free-tier-2026) (TokenMix, non daté, consulté 2026-09-24) — confiance : basse — classe : quota (non confirmé sur doc primaire, à revérifier).
- Vitesse mesurée par un tiers : Cerebras atteint environ 2 500-3 000 tokens/s sur GPT-OSS-120B et Llama, et jusqu'à 1 800 tokens/s sur Llama3.1-8B — présenté comme "over 6x plus rapide que Groq" sur Artificial Analysis — source : synthèse WebSearch citant Artificial Analysis, page non lue directement (consulté 2026-09-24) — confiance : basse — classe : vitesse (secondaire, non lu en primaire).
- Aucune mention trouvée de restriction d'usage commercial/formation interne dans la doc de rate limits consultée — source : [Rate Limits — Cerebras Inference](https://inference-docs.cerebras.ai/support/rate-limits) (Cerebras, non daté, consulté 2026-09-24) — confiance : moyenne — classe : juridique (absence de mention n'est pas une confirmation).

## 3. GitHub Models (models.github.ai)

- **GitHub Models est entièrement retiré depuis le 30 juillet 2026** : playground, catalogue de modèles, API d'inférence et support BYOK ne sont plus disponibles pour aucun client. La phase d'arrêt avait commencé le 16 juin 2026 (plus de nouveaux clients) — source : [GitHub Models Retirement 2026: July 30 Shutdown, Alternatives](https://tokenmix.ai/blog/github-models-retirement-july-30-2026) (TokenMix, non daté, consulté 2026-09-24) — confiance : moyenne — classe : stabilité.
- Confirmé indépendamment par une deuxième source : [GitHub Models is no longer available to new customers](https://github.blog/changelog/2026-06-16-github-models-is-no-longer-available-to-new-customers/) (GitHub Changelog, publié 2026-06, consulté 2026-09-24) — confiance : haute — classe : stabilité (source primaire officielle GitHub).
- Migration recommandée vers Microsoft Foundry Models (ex-Azure AI Foundry), qui n'a pas d'offre "gratuite" équivalente documentée dans cette recherche — source : [Migrate from GitHub Models to Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/quickstart-github-models) (Microsoft Learn, non daté, consulté 2026-09-24) — confiance : haute — classe : stabilité.
- **Conclusion : GitHub Models est éliminé d'office, le service n'existe plus.** Toutes les autres questions (G1-G5, quotas, compatibilité) sont sans objet.

## 4. Hugging Face Inference Providers

- Les comptes gratuits ("Free Users") reçoivent 0,10 $ de crédits mensuels pour les Inference Providers, "sujet à changement" ; les comptes PRO reçoivent 2,00 $/mois — source : [Pricing and Billing — Inference Providers](https://huggingface.co/docs/inference-providers/pricing) (Hugging Face, non daté, consulté 2026-09-24) — confiance : haute — classe : tarif (doc primaire officielle).
- **0,10 $/mois est très insuffisant pour l'usage visé** (quelques dizaines à ~200 requêtes de 2 000-15 000 tokens par séance) : à un tarif typique de fournisseur tiers routé (souvent plusieurs $/M tokens), ce crédit couvre à peine quelques requêtes. Sans achat de crédits additionnels, le compte gratuit HF ne peut pas soutenir une démo complète — déduction à partir de la source primaire ci-dessus, non vérifiée par un calcul de coût détaillé pendant cette recherche — confiance : moyenne — classe : quota.
- Au-delà des crédits, l'usage pay-as-you-go nécessite l'achat de crédits supplémentaires (contrairement aux comptes PRO/Enterprise qui continuent en pay-as-you-go direct) — source : [Pricing and Billing — Inference Providers](https://huggingface.co/docs/inference-providers/pricing) (Hugging Face, non daté, consulté 2026-09-24) — confiance : haute — classe : tarif.
- L'API est routable via un client compatible OpenAI (`base_url: https://router.huggingface.co/v1`) — source : [Pricing and Billing — Inference Providers](https://huggingface.co/docs/inference-providers/pricing) (Hugging Face, non daté, consulté 2026-09-24) — confiance : haute — classe : compatibilité.
- Aucune information trouvée pendant cette recherche sur la politique de rétention/entraînement des données pour Inference Providers ni sur le support natif du tool calling sur les modèles gratuits — non vérifié.

## 5. Cloudflare Workers AI

- Allocation gratuite de 10 000 "neurons" par jour, disponible aussi bien sur le plan Free que sur le plan payant Workers, réinitialisée à 00:00 UTC — source : synthèse WebSearch citant la doc Cloudflare (consulté 2026-09-24) — confiance : moyenne — classe : quota (non lu directement en primaire, mais cohérent entre plusieurs agrégateurs).
- 10 000 neurons permettent environ 100-200 réponses LLM par jour selon le modèle — quota potentiellement juste pour ~200 requêtes/séance selon le modèle choisi — source : synthèse WebSearch (consulté 2026-09-24) — confiance : basse — classe : quota.
- Cloudflare ne crée ni n'entraîne les modèles disponibles sur Workers AI, et n'utilise pas le "Customer Content" (prompts, sorties) pour entraîner des produits ML sans consentement explicite — source : [Your Data and Workers AI](https://developers.cloudflare.com/workers-ai/platform/data-usage/) (Cloudflare, non daté, consulté 2026-09-24) — confiance : haute — classe : données (doc primaire, via synthèse WebSearch — page non lue en fetch direct).
- Le function/tool calling est documenté nativement pour certains modèles (ex. Llama fine-tunés function-calling), avec une page dédiée — source : [Function calling · Cloudflare Workers AI docs](https://developers.cloudflare.com/workers-ai/features/function-calling/) (Cloudflare, non daté, consulté 2026-09-24) — confiance : moyenne — classe : compatibilité (titre de page confirmé, contenu détaillé non lu).
- Compatibilité OpenAI et streaming non confirmés par une source primaire lue directement pendant cette recherche — à vérifier.

## Autre fournisseur mentionné en une ligne
- Aucun fournisseur européen sérieux distinct n'a été identifié pendant cette recherche budgétée ; à creuser si besoin (ex. Scaleway, OVHcloud AI Endpoints ont des offres payantes mais leur gratuité n'a pas été vérifiée ici).

---

## Verdicts provisoires G1-G5

### Groq
- G1 Gratuité réelle : **passe (incertain sur détail)** — pas de CB pour le free tier selon agrégateurs (confiance moyenne), non confirmé sur doc primaire de pricing.
- G2 API OpenAI-compatible + streaming : **passe** — endpoints OpenAI confirmés (doc primaire `/docs/your-data`) ; streaming non vérifié directement mais standard sur ce type d'API.
- G3 Tool calling natif : **incertain** — non confirmé par une source primaire pendant cette recherche.
- G4 Accessible France/UE : **incertain** — aucune restriction géographique trouvée ni vérifiée activement.
- G5 Usage formation interne autorisé : **incertain** — CGU non consultées directement.

### Cerebras
- G1 Gratuité réelle : **incertain / contradiction** — la doc officielle de rate limits mentionne une carte bancaire obligatoire pour le "Free Trial" (5 $ de crédit), alors que des sources secondaires décrivent un "Free Tier" séparé sans CB (1M tokens/jour). Nécessite vérification directe sur cloud.cerebras.ai avant de choisir ce candidat.
- G2 API OpenAI-compatible + streaming : **incertain** — non vérifié directement dans cette recherche (implicite dans écosystème AI SDK mais pas confirmé sur doc primaire).
- G3 Tool calling natif : **incertain** — non vérifié.
- G4 Accessible France/UE : **incertain**.
- G5 Usage formation interne : **incertain**.
- Point spécifique critique : contexte plafonné à 8K sur le free tier selon une source secondaire (confiance basse) — si confirmé, **élimine Cerebras** pour les prompts de 15 000 tokens visés par la démo.

### GitHub Models
- G1-G5 : **échoue (hors sujet)** — service entièrement retiré depuis le 30 juillet 2026, confirmé par le changelog officiel GitHub et par Microsoft Learn (migration vers Foundry Models). **Candidat à retirer de la liste.**

### Hugging Face Inference Providers
- G1 Gratuité réelle : **échoue probable** — pas de CB nécessaire pour démarrer, mais le crédit gratuit (0,10 $/mois) est trop faible pour l'usage visé (quelques dizaines à 200 requêtes/séance) ; achat de crédits nécessaire au-delà.
- G2 API OpenAI-compatible + streaming : **passe** — `base_url` OpenAI confirmé sur doc primaire ; streaming non vérifié explicitement.
- G3 Tool calling natif : **incertain** — dépend du modèle/fournisseur routé, non vérifié en détail.
- G4 Accessible France/UE : **incertain** — aucune restriction trouvée.
- G5 Usage formation interne : **incertain** — CGU non consultées directement.

### Cloudflare Workers AI
- G1 Gratuité réelle : **passe (incertain sur CB)** — 10 000 neurons/jour gratuits documentés, y compris sur plan Free ; exigence de CB non confirmée pendant cette recherche.
- G2 API OpenAI-compatible + streaming : **incertain** — non confirmé par une source primaire lue directement.
- G3 Tool calling natif : **passe (partiel)** — une page de doc dédiée au function calling existe pour certains modèles.
- G4 Accessible France/UE : **incertain**.
- G5 Usage formation interne : **passe probable** — politique de non-entraînement sur les données client documentée (doc primaire citée via synthèse), plutôt favorable pour un usage entreprise/formation, mais CGU complètes non lues.

## Pistes à creuser
- Cerebras : résoudre la contradiction "Free Trial avec CB" (doc officielle rate-limits) vs "Free Tier sans CB, 1M tokens/jour" (agrégateurs) — vérifier directement sur cloud.cerebras.ai/pricing ou une page de doc distincte des rate limits.
- Cerebras : confirmer ou infirmer le plafond de contexte à 8K sur le free tier (bloquant potentiel pour les prompts 15K tokens).
- Groq, HF, Cloudflare : vérifier le support natif du tool calling sur une source primaire (doc API), pas seulement des agrégateurs.
- Tous les candidats : vérifier explicitement dans les CGU/Terms of Service si l'usage "formation interne en entreprise" est couvert par l'offre gratuite (aucune des CGU officielles n'a été lue directement pendant cette recherche, faute de budget).
- Tous les candidats : vérifier l'absence de restriction géographique pour la France/UE (aucune preuve positive ni négative trouvée).
- Vérifier les chiffres de vitesse Artificial Analysis en lisant directement artificialanalysis.ai plutôt que des résumés d'agrégateurs (aucun fetch direct effectué faute de budget).

## Cherché sans trouver
- Confirmation primaire des quotas exacts Groq (tableau RPM/TPM/RPD par modèle) — le fetch direct de la doc n'a pas exposé le tableau complet.
- CGU explicites autorisant/interdisant l'usage "formation interne en entreprise" sur l'offre gratuite, pour les 4 candidats restants.
- Confirmation de l'exigence (ou non) de carte bancaire pour Cloudflare Workers AI free tier.
- Support natif du tool calling confirmé sur source primaire pour Groq et Hugging Face Inference Providers.
- Données de vitesse Artificial Analysis lues directement à la source (uniquement vues via résumés de recherche web).
