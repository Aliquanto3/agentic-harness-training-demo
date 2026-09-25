---
title: 'Recherche technique : API LLM cloud gratuites pour WaveStack'
type: 'technical'
topic: 'API LLM cloud gratuites (Mistral, Google AI Studio, NVIDIA Build, OpenRouter et alternatives) pour WaveStack'
decision: 'Quels fournisseurs cloud inscrire dans la spec (story LLM cloud) et avec quels avertissements'
source: 'run'
shape: 'select'
status: complete
preset: 'standard'
validation: 'normal'
created: '2026-09-24'
updated: '2026-09-24'
claims_verified: 1
claims_unverified: 18
---

# Recherche technique : API LLM cloud gratuites pour WaveStack

**Décision servie :** quels fournisseurs cloud inscrire dans la spec comme cibles de la future story « LLM cloud », et avec quels avertissements.

**Cadre d'usage retenu :** le formateur projette la démo avec **sa** clé ; les participants peuvent saisir la leur en option. Les quotas sont évalués pour un seul compte, sur environ 200 requêtes par demi-journée.

## Synthèse

**Recommandation :** inscrire dans la spec un **adaptateur unique « compatible OpenAI »** (adresse de base, clé, modèle), avec des **préréglages de fournisseurs en données** et aucun fournisseur codé en dur. Deux préréglages par défaut :

- **Groq** pour l'argument vitesse : environ 320 à 900 tokens/s mesurés [27], soit 30 à 90 fois plus que la cible de 10 tokens/s d'un SLM sur CPU. Tous ses modèles gèrent l'appel d'outils [24] et il ne conserve pas les données par défaut [25].
- **Mistral** pour l'argument souveraineté : un fournisseur français, une API compatible OpenAI avec appel d'outils [6][7] et un plan gratuit toujours actif [1][2]. Mais ce plan entraîne les modèles sur les prompts par défaut, sauf si l'on décoche l'option en console [3].

**Trois constats orientent ce choix :**

1. **Seuls trois des neuf candidats ne sont ni éliminés ni réservés au rang d'exemples :** Groq, Mistral et, en option, Cloudflare. GitHub Models a fermé le 30 juillet 2026 [30][31]. Cerebras exige une carte bancaire pour un essai de 30 jours [28]. Les 0,10 $ mensuels offerts par Hugging Face ne couvrent pas une séance [32]. OpenRouter plafonne à 50 requêtes par jour sans achat de crédits [20]. Les conditions de NVIDIA le réservent à « l'évaluation » et réutilisent les contenus [17]. Google réserve l'offre payante aux utilisateurs de l'EEE [11].
2. **La gratuité se paie presque toujours en données.** Mistral (sauf désactivation) [3], Google (sans opt-out possible) [11] et NVIDIA [17] utilisent les prompts gratuits pour améliorer leurs modèles. Seuls Groq [25] et Cloudflare [34] s'en abstiennent. C'est un **matériau pédagogique** direct pour la question centrale de WaveStack : où vont les données ? Chaque fournisseur doit donc l'afficher dans l'infobulle.
3. **Aucun quota n'est stable ni publié de façon fiable.** Plusieurs tableaux ne sont lisibles que dans une console connectée [1][14]. Les offres ont changé au cours de l'année [2][22][30]. La spec ne doit donc **fixer aucun quota** : un refus pour débit dépassé (erreur 429) doit devenir un événement visible et expliqué. Et une **vérification réelle, avec la clé du formateur,** doit avoir lieu avant chaque séance.

**Principale réserve :** la plupart des affirmations reposent sur **une seule source primaire**, la documentation du fournisseur lui-même (18 non vérifiées de façon indépendante, 1 vérifiée). Le fonctionnement réel, clé en main, n'a été testé pour aucun fournisseur. La spec doit donc exiger ce test.

## Candidats et critères éliminatoires

**Critères éliminatoires :**
- **G1** : gratuit, sans carte bancaire.
- **G2** : API compatible OpenAI, avec streaming.
- **G3** : appel d'outils disponible gratuitement.
- **G4** : utilisable depuis la France.
- **G5** : l'usage en formation interne n'est pas interdit.

| Candidat | G1 | G2 | G3 | G4 | G5 | Statut |
|---|---|---|---|---|---|---|
| **Groq** | incertain (aucune page officielle, mais rien n'indique de carte) | passe [25] | passe [24] | incertain | plutôt passe [26] | **finaliste** |
| **Mistral** | passe, 10 $/mois de crédits [2] ; absence de carte non confirmée | passe [6] | probable [7] | probable | plutôt passe [5] | **finaliste** |
| **Cloudflare Workers AI** | passe [33] | passe [35], streaming non confirmé | partiel [36] | incertain | probable [34] | finaliste secondaire |
| **Google AI Studio** | passe [10] | passe [13] | non confirmé | **clause EEE** [11][12] | risque | exemple de configuration, avec avertissement |
| **NVIDIA Build** | incertain (téléphone exigé) [19] | probable | passe [18] | incertain | « évaluation interne » seulement [17] | exemple de configuration, avec avertissement |
| **OpenRouter `:free`** | passe [20] | passe [20] | non vérifié | passe | données à risque [21] | exemple de configuration, avec avertissement |
| **Cerebras** | **échoue** : carte bancaire, 30 jours [28] | — | — | — | — | écarté |
| **Hugging Face** | **échoue** en pratique : 0,10 $/mois [32] | passe | — | — | — | écarté |
| **GitHub Models** | **service arrêté** [30][31] | — | — | — | — | écarté |

### Grille pondérée (finalistes et exemples)

Notes de 1 à 3. Une absence de preuve vaut 1, et cette note est signalée (« n.p. », non prouvé). La grille peut être repondérée librement.

| Critère (poids) | Groq | Mistral | Cloudflare | Google | NVIDIA | OpenRouter |
|---|---|---|---|---|---|---|
| Quotas pour une séance (3) | 2 : 1 000 req/jour, 8 000 tokens/min [23] | 2 : 10 $/mois [2] | 2 : environ 100 à 200 réponses/jour [33] | 2 : n.p. [14] | 2 : environ 40 req/min [16] | 1 : 50 req/jour [20] |
| Données, UE (3) | 3 [25] | 2 : désactivable [3] | 3 [34] | 1 : sans opt-out [11] | 1 [17] | 1 [21] |
| Vitesse (2) | 3 [27] | 2 [9] | 1 (n.p.) | 2 [15] | 1 (n.p.) | 1 (n.p.) |
| Modèles et contexte (2) | 2 [24] | 3 [8] | 2 [37] | 3 | 3 [18] | 1 : outils non vérifiés |
| Stabilité (2) | 2 | 2 : tarifs remaniés [2] | 2 | 2 | 1 : de crédits à limite de débit [38] | 1 [22] |
| Inscription (1) | 2 | 2 | 2 : identifiant de compte [35] | 3 [10] | 2 : téléphone [19] | 3 [20] |
| **Total /39** | **31** | **28** | **27** | **26** | **21** | **15** |

**Choix : Groq**, pour la vitesse et le respect des données. **Deuxième : Mistral**, qui l'emporte dès que l'argument souveraineté (fournisseur français) pèse plus que la vitesse. Le meilleur argument contre Groq : l'absence de carte bancaire et l'accès depuis la France ne sont confirmés par aucune source primaire. **Solution de repli la moins coûteuse** : l'adaptateur unique compatible OpenAI (recommandation 1). Changer de fournisseur ne demande alors que de la configuration.

## Détail par fournisseur

### Mistral : La Plateforme, plan gratuit

- **Offre.** Le plan gratuit de l'API existe toujours : « Free mode lets you create API keys and use included monthly usage within the limits shown on the Limits page » [1]. La page des tarifs affiche désormais **« $10/mo in API credits »** [2]. Des agrégateurs citent encore un plafond d'environ 1 milliard de tokens par mois. La page officielle ne le montre plus, et la documentation des tarifs redirige vers la page commerciale [2]. Le plafond réel se lit dans la console. Confiance moyenne.
- **Données.** Sur le plan gratuit, les prompts peuvent servir à l'entraînement **par défaut**. On le désactive dans Admin Console > Privacy [3]. Ce n'est pas le cas sur les plans payants [4]. Hébergement dans l'UE plausible, mais non confirmé par une source primaire (la page de confidentialité renvoie une erreur 404).
- **Conditions.** Les conditions commerciales ne réservent pas le plan gratuit à l'évaluation. Seuls les produits Beta et les modèles Labs/Preview sont restreints [5].
- **API.** Elle est compatible avec le client OpenAI : il suffit de changer `base_url` (`https://api.mistral.ai/v1`) et le nom du modèle [6]. Le streaming est géré. L'appel d'outils accepte `tool_choice` et `parallel_tool_calls` sur Large et Small [7], mais sa disponibilité sur le plan gratuit n'est pas confirmée à part.
- **Modèles** (septembre 2026) : Mistral Medium 3.5, Small 4, Large 3 et Ministral 3 (14B, 8B, 3B) [8]. Fenêtres de contexte non relevées.
- **Vitesse.** Environ 169 tokens/s pour Mistral Small 4 sur l'API Mistral [9]. Confiance moyenne.

### Groq

- **Quotas gratuits** (tableau officiel, lu en partie) : `openai/gpt-oss-120b` à 30 requêtes/min, 1 000 requêtes/jour, 8 000 tokens/min et 200 000 tokens/jour [23]. **Un prompt de plus de 8 000 tokens dépasse la limite par minute.** Le contexte envoyé à Groq doit donc être plafonné. Les lignes des autres modèles ne se sont pas chargées.
- **Appel d'outils.** « All models hosted on Groq support tool use » [24]. L'association streaming et appel d'outils n'est pas confirmée explicitement.
- **Données.** Aucune rétention des entrées et sorties par défaut, 30 jours au plus pour le débogage ou la lutte contre les abus, et une option de rétention nulle [25]. Le contrat interdit l'usage grand public, mais pas l'usage interne en entreprise [26].
- **Vitesse** (Artificial Analysis) : environ 900 tokens/s pour gpt-oss-20b, 470 pour gpt-oss-120b et 320 pour Llama 3.3 70B [27]. Confiance moyenne : la page n'indique pas de date de mesure.
- **Point non établi :** l'absence de carte bancaire. Aucune page officielle ne traite ce sujet, et seuls des agrégateurs l'affirment.

### Cloudflare Workers AI

- **Quota.** 10 000 « neurons » par jour, gratuits sur le plan Free, sans carte bancaire [33]. Cela représente peut-être 100 à 200 réponses par jour selon le modèle : **juste pour une séance**. Confiance basse sur cette conversion.
- **API.** Point d'accès compatible OpenAI : `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions` [35]. **L'identifiant de compte est dans l'URL** : la configuration doit donc permettre une adresse de base propre à chaque compte.
- **Données.** Le contenu client n'est pas utilisé pour l'entraînement sans consentement [34].
- **Appel d'outils.** Documenté [36]. Le catalogue lu par l'outil [37] contient des noms qu'il faut revérifier à la main. Le même nom, `qwen3.8-27b`, apparaît aussi chez Groq [23], où il est signalé comme douteux lui aussi. Le même outil de lecture a pu se tromper deux fois : une relecture à la main reste nécessaire.

### Google AI Studio : offre gratuite de l'API Gemini

- **Gratuit sans carte bancaire** [10]. Point d'accès compatible OpenAI : `https://generativelanguage.googleapis.com/v1beta/openai/` [13].
- **Clause EEE, vérifiée mot pour mot** : « You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom » [11]. Un fil du forum officiel montre que sa portée est débattue [12]. Pour **un formateur qui projette sa propre démo**, le risque paraît faible, car il ne met rien à disposition d'utilisateurs. En revanche, la clause viserait directement des **participants qui saisiraient leur propre clé gratuite dans WaveStack** (une option du cadre d'usage). Confiance moyenne.
- **Données.** Sur l'offre gratuite, les contenus servent à améliorer les produits Google et **peuvent être lus par des relecteurs humains, sans opt-out possible** [11].
- **Vitesse.** Environ 195 tokens/s pour Gemini 2.5 Flash [15]. Quotas et appel d'outils sur l'offre gratuite non vérifiés : ils ne s'affichent que dans le tableau de bord [14].

### NVIDIA Build (API Catalog)

- **Conditions** (PDF officiel lu en entier, version de septembre 2025) : « NVIDIA will provide you access to the API Service for limited trial purposes only and without use of the API Service or Generated Content in production ». Sans abonnement, l'usage se limite à « internal testing and evaluation purposes » [17]. Une démo de formation s'y rattache, mais **l'offre n'est pas conçue pour un usage durable**.
- **Données.** Le §3.3 prévoit la collecte de « User Content and Generated Content to improve NVIDIA products and services, including AI models » [17].
- **Quotas.** Environ 40 requêtes/min par modèle, selon un modérateur du forum [16]. Le système de crédits aurait été remplacé par cette limite de débit à la mi-2026 : cela ne ressort que de sources secondaires [38], le PDF de 2025 ne parle que de crédits. Inscription avec vérification par téléphone, et certains pays refusés [19]. Aucun blocage signalé pour la France.
- **Appel d'outils.** Documenté pour Llama 3.x, Nemotron, Mistral, Qwen 2.5 72B, GLM, Kimi K2 et Mixtral [18]. C'est **le catalogue de gros modèles le plus large**.

### OpenRouter, modèles `:free`

- **Quotas** (documentation officielle, relue deux fois) : 20 requêtes/min ; **50 requêtes par jour tant qu'on a acheté moins de 10 $ de crédits**, 1 000 au-delà [20]. Le chiffre de 200 par jour, cité par des agrégateurs, est obsolète.
- **Données.** La politique dépend du fournisseur vers lequel la requête est routée. Des réglages permettent d'exclure les points d'accès gratuits qui entraînent sur les entrées [21]. Aucune formulation catégorique n'a été relevée.
- **Stabilité.** Le catalogue gratuit change presque chaque jour. `deepseek-r1:free` et `qwen3-coder:free` ont disparu [22].
- **Non vérifié :** la liste des modèles `:free` qui acceptent `tools`. Le JSON public `api/v1/models` a été tronqué par l'outil de lecture, et le recours à `curl` a été refusé par le bac à sable.

### Écartés

- **Cerebras.** « Free Trial » de 5 $ de crédits, qui expirent au bout de 30 jours. « If you skip adding a payment method at sign-up, Playground and API access remain inactive » [28]. Dommage pour la démo, car c'est le plus rapide : environ 1 770 tokens/s sur gpt-oss-120b [29].
- **GitHub Models.** Fermé aux nouveaux clients le 16 juin 2026, arrêté le 30 juillet 2026 [30]. Migration vers Microsoft Foundry, sans offre gratuite équivalente [31].
- **Hugging Face Inference Providers.** 0,10 $ de crédits par mois pour un compte gratuit, 2 $ pour un compte PRO [32].

## Enseignements croisés

- **La vitesse l'emporte partout, même chez les plus lents.** Les finalistes produisent entre 170 et 900 tokens/s [9][15][27], contre environ 10 tokens/s visés pour un SLM sur CPU (hypothèse de NFR-1). L'argument « plus rapide qu'en local » tient pour tous les candidats. Il n'impose donc pas de fournisseur.
- **La gratuité se paie en données et en fragilité, pas en argent.** On le voit en croisant les données (points 2 et 3) et la stabilité de l'offre : GitHub Models a fermé en six semaines, le catalogue d'OpenRouter change chaque jour, Mistral a remanié ses tarifs, NVIDIA est passé des crédits à une limite de débit. **Aucun fournisseur ne doit être codé en dur.** Une liste en données, une vérification avant la séance et un repli sur le modèle local sont le seul montage durable.
- **Les quotas en tokens par minute limitent la taille du contexte.** Chez Groq, 8 000 tokens par minute sur gpt-oss-120b [23] plafonnent le contexte envoyé. La jauge et la fenêtre (AD-9) doivent donc tenir compte d'une **fenêtre effective par fournisseur**, pas seulement de la taille native du modèle.
- **La clause EEE de Google entre en tension avec l'option « chaque participant saisit sa clé ».** Pour le seul formateur, le risque est faible. Pour des participants qui utiliseraient des clés gratuites, la clause vise précisément ce cas.

## Recommandations

À reprendre dans `bmad-correct-course`, puis dans la spec et l'architecture. Leur niveau de confiance figure entre parenthèses.

1. **Architecture (AD-5).** Un seul adaptateur `openai_chat` : adresse de base, clé, modèle, streaming, `tools`. Ajouter un fournisseur ne demande que de la configuration. Cela couvre aussi les futurs points d'accès Wavestone sur Azure ou GCP. (Haute pour Mistral [6], OpenRouter [20] et Groq [25] ; moyenne pour Google [13] et Cloudflare [35], dont le streaming n'est pas confirmé.)
2. **Préréglages par défaut : Groq et Mistral**, dans les données de `content/`. Google, NVIDIA, OpenRouter et Cloudflare y figurent en **exemples de configuration**, avec leurs avertissements. (Moyenne : absence de carte bancaire non confirmée par une source primaire pour Groq et Mistral.)
3. **Infobulle par fournisseur.** Elle affiche le lieu d'hébergement, l'usage des données pour l'entraînement (oui, non, désactivable), les quotas renvoyés vers la console et la nature « offre d'essai » le cas échéant. Cela sert directement le signal de succès SM-3. (Haute sur les politiques de données [11][17][25][34] ; moyenne pour Mistral [3], lu à travers un résumé.)
4. **Aucun quota fixé dans la spec.** Un refus pour débit dépassé (erreur 429) devient un événement tracé et expliqué, jamais un plantage (NFR-8). (Haute.)
5. **Fenêtre effective par fournisseur**, réglable dans la configuration, pour respecter les limites de tokens par minute. (Moyenne [23].)
6. **Vérification réelle avant chaque séance.** Un bouton ou une commande envoie un appel minimal avec appel d'outils et streaming au fournisseur choisi, et affiche le résultat. C'est la seule preuve de fonctionnement, puisque cette recherche n'a rien testé clé en main. (Haute.)
7. **Clé API.** Saisie dans l'interface et stockée hors du dépôt (AD-20). Jamais écrite dans la trace ni envoyée vers une autre adresse que celle du fournisseur (NFR-4, NFR-11). Les scénarios fournis restent jouables sans clé, en local. (Haute : contraintes du projet.)
8. **Clés des participants.** Si l'option est gardée, l'infobulle de Google signale la clause EEE [11]. (Moyenne.)

## Questions ouvertes

- **Carte bancaire et téléphone chez Groq et Mistral** : non confirmés par une source primaire. Pour trancher, il faut créer un compte avec la clé du formateur.
- **Quotas exacts de Mistral, Gemini et Groq pour les autres modèles** : visibles seulement en console connectée ou sur une page qui se charge en JavaScript. Il faut les relever à la main dans la console.
- **Modèles `:free` d'OpenRouter qui acceptent `tools`** : il suffit d'une commande locale sur `https://openrouter.ai/api/v1/models`, en filtrant `supported_parameters`.
- **Streaming combiné à l'appel d'outils chez Groq et Cloudflare** : à confirmer par la vérification avant séance (recommandation 6).
- **Hébergement UE de Mistral** : la page de confidentialité renvoie une erreur 404. Il faut chercher sa nouvelle adresse, ou poser la question au support.
- **Portée de la clause EEE de Google** : aucune réponse officielle n'a été trouvée. Il faudrait un avis juridique Wavestone si les participants doivent utiliser leurs propres clés.
- **Passage de NVIDIA des crédits à une limite de débit** : connu seulement par des sources secondaires. Le compte réel le montrera.

## Sources

| # | Affirmation appuyée | Éditeur | Publication | Consultation | Confiance |
|---|---|---|---|---|---|
| [1] | Plan gratuit de l'API toujours actif | [Mistral Docs, Usage and limits](https://docs.mistral.ai/admin/billing-usage/usage-limits) | non daté | 2026-09-24 | haute |
| [2] | « $10/mo in API credits », redirection des tarifs | [mistral.ai, Pricing](https://mistral.ai/pricing) | non daté | 2026-09-24 | haute |
| [3] | Entraînement par défaut sur le plan gratuit, désactivable | [Mistral Help Center](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training) | non daté | 2026-09-24 | moyenne |
| [4] | Pas d'entraînement sur les plans payants | [Mistral Docs, Privacy and data controls](https://docs.mistral.ai/admin/monitor-comply/privacy-data-controls) | non daté | 2026-09-24 | moyenne |
| [5] | Conditions commerciales : restrictions sur Beta et Labs seulement | [legal.mistral.ai, Commercial ToS](https://legal.mistral.ai/terms/commercial-terms-of-service) | non daté | 2026-09-24 | haute |
| [6] | Compatibilité OpenAI, streaming | [Mistral Docs, Migration guides](https://docs.mistral.ai/resources/migration-guides) | non daté | 2026-09-24 | haute |
| [7] | Appel d'outils, `tool_choice`, `parallel_tool_calls` | [Mistral Docs, Function calling](https://docs.mistral.ai/studio/conversations/function-calling) | non daté | 2026-09-24 | moyenne |
| [8] | Gamme de modèles, septembre 2026 | [Mistral Docs, Models](https://docs.mistral.ai/models) | non daté | 2026-09-24 | haute |
| [9] | Vitesse de Mistral Small 4 | [Artificial Analysis](https://artificialanalysis.ai/models/mistral-small-4) | non daté | 2026-09-24 | moyenne |
| [10] | Offre gratuite Gemini sans carte bancaire | [Google AI for Developers, Billing](https://ai.google.dev/gemini-api/docs/billing) | 2026-09 | 2026-09-24 | haute |
| [11] | Clause EEE, usage des données sur l'offre gratuite | [Google AI for Developers, Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) | non daté | 2026-09-24 | haute |
| [12] | Portée de la clause EEE débattue | [Google AI Developers Forum](https://discuss.ai.google.dev/t/clarification-on-only-paid-services-for-eea-ch-uk/107860) | 2025-10 | 2026-09-24 | moyenne |
| [13] | Point d'accès compatible OpenAI | [Google AI for Developers, OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai) | non daté | 2026-09-24 | moyenne |
| [14] | Quotas renvoyés vers le tableau de bord | [Google AI for Developers, Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) | non daté | 2026-09-24 | moyenne |
| [15] | Vitesse de Gemini 2.5 Flash | [Artificial Analysis](https://artificialanalysis.ai/models/gemini-2-5-flash) | non daté | 2026-09-24 | moyenne |
| [16] | Environ 40 requêtes/min, pas d'augmentation possible | [NVIDIA Developer Forums](https://forums.developer.nvidia.com/t/api-credit-rate-limit-increase-request-for-build-nvidia-com-free-tier/382934) | non daté | 2026-09-24 | haute |
| [17] | Offre d'essai hors production ; collecte des contenus (§3.3) | [NVIDIA, API Trial Terms of Service (PDF)](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf) | 2025-09 | 2026-09-24 | haute |
| [18] | Appel d'outils par famille de modèles | [NVIDIA Docs, NIM function calling](https://docs.nvidia.com/nim/large-language-models/1.10.0/function-calling.html) | non daté | 2026-09-24 | haute |
| [19] | Vérification par téléphone, pays refusés | [NVIDIA Developer Forums](https://forums.developer.nvidia.com/t/unable-to-register-on-build-nvidia-com-turkey-90-not-supported/367723) | non daté | 2026-09-24 | haute |
| [20] | Quotas `:free`, streaming, compatibilité OpenAI | [OpenRouter Docs, Limits](https://openrouter.ai/docs/api-reference/limits) | non daté | 2026-09-24 | haute |
| [21] | Politique de données des fournisseurs, réglages d'exclusion | [OpenRouter Docs, Provider logging](https://openrouter.ai/docs/guides/privacy/provider-logging) | non daté | 2026-09-24 | moyenne |
| [22] | Instabilité du catalogue gratuit | [GitHub, cyclez2000/openrouter-free-models #76](https://github.com/cyclez2000/openrouter-free-models/issues/76) | 2026-09 | 2026-09-24 | moyenne |
| [23] | Quotas gratuits de Groq (gpt-oss-120b) | [GroqDocs, Rate limits](https://console.groq.com/docs/rate-limits) | non daté | 2026-09-24 | moyenne |
| [24] | Appel d'outils sur tous les modèles | [GroqDocs, Tool use](https://console.groq.com/docs/tool-use) | non daté | 2026-09-24 | moyenne |
| [25] | Données non conservées ; API compatible OpenAI | [GroqDocs, Your data](https://console.groq.com/docs/your-data) | non daté | 2026-09-24 | haute |
| [26] | Contrat : pas d'usage grand public | [Groq, Services Agreement](https://console.groq.com/docs/legal/services-agreement) | non daté | 2026-09-24 | moyenne |
| [27] | Vitesses de Groq | [Artificial Analysis, Groq](https://artificialanalysis.ai/providers/groq) | non daté | 2026-09-24 | moyenne |
| [28] | Offre d'essai Cerebras avec carte bancaire, 30 jours | [Cerebras Inference Docs, Rate limits](https://inference-docs.cerebras.ai/support/rate-limits) | non daté | 2026-09-24 | haute |
| [29] | Vitesse de Cerebras | [Artificial Analysis, Cerebras](https://artificialanalysis.ai/providers/cerebras) | non daté | 2026-09-24 | moyenne |
| [30] | Arrêt de GitHub Models | [GitHub Changelog](https://github.blog/changelog/2026-06-16-github-models-is-no-longer-available-to-new-customers/) | 2026-06 | 2026-09-24 | haute |
| [31] | Migration vers Foundry | [Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/quickstart-github-models) | non daté | 2026-09-24 | haute |
| [32] | 0,10 $/mois de crédits gratuits | [Hugging Face, Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing) | non daté | 2026-09-24 | haute |
| [33] | 10 000 neurons/jour, sans carte bancaire | [Cloudflare, Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) | non daté | 2026-09-24 | moyenne |
| [34] | Pas d'entraînement sur le contenu client | [Cloudflare, Data usage](https://developers.cloudflare.com/workers-ai/platform/data-usage/) | non daté | 2026-09-24 | haute |
| [35] | Point d'accès compatible OpenAI avec identifiant de compte | [Cloudflare, OpenAI compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/) | non daté | 2026-09-24 | moyenne |
| [36] | Appel d'outils documenté | [Cloudflare, Function calling](https://developers.cloudflare.com/workers-ai/features/function-calling/) | non daté | 2026-09-24 | moyenne |
| [37] | Catalogue de modèles (à revérifier) | [Cloudflare, Workers AI models](https://developers.cloudflare.com/workers-ai/models/) | non daté | 2026-09-24 | basse |
| [38] | NVIDIA : sans carte bancaire, environ 40 requêtes/min (source secondaire) | [yangmao.ai](https://yangmao.ai/en/providers/nvidia-build/no-credit-card/) | non daté | 2026-09-24 | moyenne |

## Carte de péremption

Calculée avec `recon_kit staleness`. Durées de validité : quotas, tarifs, stabilité et vitesse 3 mois ; compatibilité et modèles 1 mois ; données et conditions juridiques 6 mois.

- **Déjà périmées (3) :**
  - les deux clauses NVIDIA [17], car le PDF date de septembre 2025. Il faut relire la version en ligne avant la première séance ;
  - l'arrêt de GitHub Models [30], date de validité dépassée mais sans conséquence, car l'arrêt est définitif.
- **2026-10-01 :** compatibilité Mistral [6][7] et appel d'outils Groq [24].
- **2026-12-01 :** tous les quotas, tarifs et vitesses (Mistral, Groq, Cloudflare, OpenRouter, NVIDIA, Cerebras, Hugging Face).
- **2027-03-01 :** politiques de données et conditions juridiques (Mistral, Google, Groq, Cloudflare).

**Première revérification : immédiate pour NVIDIA [17].** Pour le reste, le 1er octobre 2026. Un rapport de sélection de plus de deux trimestres doit être rafraîchi avant toute décision.
