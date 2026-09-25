# Vérification R2-1 — fournisseurs gratuits (Gemini, NVIDIA, OpenRouter)

## 1. Google Gemini API — clause EEE/Suisse/UK

**Statut : nuancée**

Citation exacte (section "Use Restrictions", `ai.google.dev/gemini-api/terms`) :
> "You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom."

Définitions trouvées dans la même page :
- **"Paid Service"** : "When a Service is being offered for a fee, it is considered to be a paid Service ('Paid Services')."
- **"Unpaid Services"** : "Any Services that are offered free of charge like direct interactions with Google AI Studio or unpaid quota in Gemini API are unpaid Services ('Unpaid Services')."
- Précision additionnelle (confirmée par recherche complémentaire, même page) : l'accès Gemini API est "Paid Service" seulement via un Cloud Project avec facturation active ; l'accès à AI Studio est "Paid Service" dès lors que le compte est rattaché à un Cloud Project avec facturation active, même si l'usage lui-même est gratuit.

Portée pour un développeur en France qui utilise l'API lui-même (pas de mise à disposition à des tiers) : la clause vise le fait de "making API Clients available to users" dans les trois zones visées — c'est-à-dire distribuer/exposer un produit à des utilisateurs finaux situés en EEE/CH/UK. Un développeur français qui appelle l'API pour lui-même, sans exposer de service à des utilisateurs situés dans ces zones, n'est a priori pas la cible directe de la restriction — mais la formulation reste ambiguë sur le point de savoir si "users" inclut le développeur lui-même en tant qu'utilisateur unique de son propre client. Un fil ouvert sur le forum officiel Google AI Developers ("Clarification on 'Only Paid Services' for EEA/CH/UK", oct. 2025, discuss.ai.google.dev/t/clarification-on-only-paid-services-for-eea-ch-uk/107860) montre que cette ambiguïté est activement débattue par la communauté ; je n'ai pas pu récupérer de réponse officielle Google confirmée dans ce fil avec citation exacte (accès non vérifié directement, voir "Cherché sans trouver").

Quotas free tier Flash et function calling : **non vérifiable avec citation exacte**. La page `ai.google.dev/gemini-api/docs/rate-limits` ne donne pas de chiffres RPM/TPM/RPD fixes dans le texte statique (elle renvoie vers un tableau de bord dynamique `aistudio.google.com/rate-limit`). La page pricing ne donne que des limites d'outils annexes (Google Search grounding : 500 RPD gratuit, partagé avec Flash-Lite), pas les limites générales de l'API, et ne précise pas explicitement si le function calling est disponible en free tier.

**Confiance** : haute sur la citation et les définitions (lues directement) ; moyenne-basse sur la portée pour un développeur solo (ambiguïté non tranchée par une source officielle citée) ; basse sur les quotas Flash (non extraits).

**Impact pour le cas d'usage** : le formateur est en France, utilise sa propre clé pour projeter une démo en salle — il n'expose pas d'API Client public à des utilisateurs situés en EEE/CH/UK au sens de la clause. Le risque contractuel semble faible pour ce scénario précis (démo unipersonnelle projetée), mais la clause reste écrite de façon large et non testée officiellement pour ce cas exact ; à traiter comme un risque résiduel plutôt qu'une élimination automatique.

---

## 2. NVIDIA API Trial Terms of Service

**Statut : vérifiée** (citation directement extraite du PDF officiel)

Citation exacte (section 1.2, "Trial Access Rights") :
> "NVIDIA will provide you access to the API Service for limited trial purposes only and without use of the API Service or Generated Content in production."

Autres clauses pertinentes lues directement dans le PDF :
- Pas de définition formelle du mot "production", mais section 1.4 précise : "Unless you purchase a Subscription from NVIDIA or a Service Provider (as applicable), you may only use the API Service for internal testing and evaluation purposes, not in production." — l'usage de démonstration/formation entre dans "internal testing and evaluation purposes", explicitement autorisé hors production.
- Section 1.3 (Pre-Release) : versions pré-release "not intended for use in production or business-critical systems".
- Logging/usage des prompts par NVIDIA (section 3.3) : "NVIDIA will collect the following data, without identifying specific users, to operate and improve the API Services and other products and services: (i) session metrics [...]; (ii) error logs and execution logs [...]; (iii) your feedback [...]; and (iv) User Content and Generated Content to improve NVIDIA products and services, including AI models. Your use of the API Services will be logged for security, fraud or abuse monitoring and shared with third party service providers for this purpose." — donc oui, logging systématique et usage des contenus pour améliorer les modèles NVIDIA.
- Rétention (section 2.3-2.4) : par défaut NVIDIA "will not store or use User Content or Generated Content at the end of each API Service session", sauf certains services (ex. Fine Tuning : 30/90 jours) ou logs de sécurité/fraude (section 3.3).
- Durée/expiration des crédits (section 1.4) : "NVIDIA will deduct Credits based on your usage" et "The API Services are available for your limited use for a limited time" — pas de durée fixe chiffrée dans le PDF (v. 19 septembre 2025).

Remplacement du modèle crédits par de simples limites de débit : **nuancée**, confirmée par recherche complémentaire (forums NVIDIA développeurs et pages tierces récapitulatives, non primaires) : le système de crédits (1000 pour compte personnel) aurait été remplacé mi-2026 par un accès "illimité" avec limite de 40 requêtes/minute par modèle (extensible à 200 RPM sur demande). Cette information vient de sources secondaires (forums, blogs "yangmao.ai", "decodethefuture.org"), pas du texte primaire des Trial Terms lui-même — le PDF officiel (daté du 19/09/2025) ne mentionne aucune limite de débit chiffrée, seulement le mécanisme de crédits.

**Confiance** : haute sur les citations du PDF (lecture directe complète, 9 pages) ; moyenne sur le remplacement crédits→rate-limit (sources secondaires uniquement, non confirmées par un texte primaire NVIDIA daté).

**Impact pour le cas d'usage** : la formation (démo devant participants, ~200 requêtes/demi-journée) relève de "internal testing and evaluation purposes" / démonstration pédagogique, explicitement hors "production" — usage a priori toléré par les Trial Terms tels qu'écrits. Point de vigilance réel : tout contenu envoyé (prompts de démo) peut être loggé et réutilisé par NVIDIA pour améliorer ses modèles (section 3.3) — à mentionner si des données sensibles du cabinet ne doivent jamais transiter. Le doute sur crédits vs rate-limit (donc sur la capacité à tenir 200 req/demi-journée) n'est pas tranché par le texte contractuel primaire ; à vérifier empiriquement sur le compte réel avant la formation.

---

## 3. OpenRouter

### 3a. Rate limits modèles `:free`

**Statut : vérifiée**

Citations exactes (`openrouter.ai/docs/api-reference/limits`) :
- "20" RPM pour tous les modèles `:free`, quel que soit l'historique d'achat.
- Comptes ayant acheté moins de 10 $ de crédits au total : "50" requêtes/jour.
- Comptes ayant acheté 10 $ ou plus : "1000" requêtes/jour.
- Ces limites sont exposées via le champ `free_model_daily_requests` de `GET /api/v1/key`.

Ces chiffres correspondent exactement à l'affirmation du brief (20 RPM / 50 requêtes-jour sous 10 $ / 1000 requêtes-jour au-delà).

### 3b. Modèles `:free` avec support `tools` (function calling) dans le catalogue public

**Statut : non vérifiable** (contrainte d'outils rencontrée)

Deux tentatives de lecture de `https://openrouter.ai/api/v1/models` (JSON public, des centaines d'entrées) via WebFetch n'ont renvoyé qu'un sous-ensemble tronqué (10 entrées, champ `supported_parameters` absorbé en `capabilities` null par la conversion HTML→markdown de l'outil), donnant un résultat non fiable ("0 correspondance") que je ne retiens pas comme probant. Une tentative de récupération directe du JSON complet via `curl` a été bloquée par la politique de sandbox de l'environnement (refus explicite de l'outil, action non contournée conformément à la consigne reçue). Je n'ai donc **pas** de liste fiable de modèles `:free` supportant `tools`, ni de décompte, ni d'exemples avec `context_length`, ni de confirmation qu'un grand modèle frontière (≥70B) est présent avec support d'outils.

**Impact** : point bloquant pour le cas d'usage (la démo utilise l'appel d'outils) — à revérifier avec un outil capable de parser le JSON complet (script local, pas de contrainte réseau) avant de trancher sur OpenRouter comme repli gratuit pour la partie "tool calling" de la démo.

### 3c. Entraînement sur les données des modèles gratuits

**Statut : nuancée**

Citation exacte trouvée (page provider-logging) : "This setting has no bearing on OpenRouter's own policies and what we do with your prompts." — cette phrase concerne un paramètre de routage vers les providers, et ne constitue pas elle-même l'énoncé de la politique d'entraînement d'OpenRouter. La page consultée documente essentiellement les politiques des *providers* tiers (chacun avec ses propres règles de logging/training, variables par provider) plutôt qu'un engagement unique et global d'OpenRouter sur l'entraînement. Je n'ai pas pu extraire un texte primaire unique et daté affirmant explicitement "les modèles gratuits utilisent vos prompts pour l'entraînement" ou l'inverse, de façon catégorique.

**Confiance** : moyenne — la page existe et a été lue, mais l'extraction n'a pas produit l'affirmation catégorique demandée par le brief ; à confirmer par une lecture humaine directe de `openrouter.ai/docs/guides/privacy/provider-logging` et de la page privacy générale.

**Impact** : les prompts de démo transitant par des modèles `:free` d'OpenRouter dépendent de la politique du provider routé (variable), pas d'une règle OpenRouter unique — à vérifier provider par provider si des données sensibles de formation sont en jeu (peu probable pour une démo pédagogique).

---

## Cherché sans trouver

- Réponse officielle confirmée d'un employé Google sur le forum `discuss.ai.google.dev` concernant la portée de la clause EEE/CH/UK pour un développeur solo (fil identifié, contenu non extrait avec citation).
- Chiffres RPM/TPM/RPD exacts du free tier Gemini Flash sur la page de documentation statique (renvoie vers un tableau de bord dynamique nécessitant une connexion).
- Confirmation explicite (oui/non) de la disponibilité du function calling en free tier Gemini, dans un texte primaire daté.
- Liste exhaustive et fiable des modèles `:free` d'OpenRouter supportant `tools`, avec `context_length` — bloqué par une limitation d'outil (troncature WebFetch) et un refus de sandbox sur `curl`.
- Texte primaire NVIDIA daté confirmant le remplacement du modèle "crédits" par de simples limites de débit (40→200 RPM) — trouvé uniquement en sources secondaires (forums, blogs), pas dans les Trial Terms eux-mêmes.
