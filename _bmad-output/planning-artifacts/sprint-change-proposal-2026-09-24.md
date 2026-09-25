---
title: 'Proposition de changement : modèles cloud via API'
date: '2026-09-24'
author: Anaël
status: 'approuvée'
approved: '2026-09-24'
mode: 'lot'
branch: 'spec/cloud-llm'
scope: 'modéré'
sources:
  - research/technical-api-llm-cloud-gratuites-2026-09-24/research.md
---

# Proposition de changement : modèles cloud via API

## 1. Résumé du problème

**Déclencheur.** Nouvelle exigence du porteur, hors de toute story : ajouter des LLM cloud appelés par API, **en plus** des SLM locaux. La story 8 (hooks) est en cours sur `main` ; ce changement ne touche que les documents.

**Objectifs pédagogiques :**
- montrer que **le même harnais** fonctionne avec des modèles beaucoup plus gros ;
- montrer qu'un modèle cloud produit du texte **bien plus vite** qu'un SLM sur un PC sans GPU : 170 à 900 tokens/s, contre environ 10 tokens/s visés en local (recherche, « Enseignements croisés »).

**À terme :** un point d'accès interne Wavestone, sur Azure ou GCP, ajouté **par simple configuration**.

**Catégorie :** nouvelle exigence (changement de périmètre). Elle contredit deux non-objectifs actuels : « aucun fournisseur de modèle cloud » et « pas de format chat compatible OpenAI ».

**Base factuelle :** la recherche du 2026-09-24 retient Groq et Mistral comme préréglages. Google, NVIDIA et OpenRouter n'y figurent qu'en exemples de configuration, avec un avertissement. Cerebras, Hugging Face et GitHub Models sont écartés. Elle formule 8 recommandations. Réserve majeure : aucune affirmation n'a été testée clé en main (18 affirmations sur 19 reposent sur une seule source, celle du fournisseur).

## 2. Analyse d'impact

### Constat d'architecture qui fixe la portée

Un appel au format chat (`/chat/completions`) envoie des **messages structurés** et une liste `tools`. Le fournisseur applique alors **lui-même** le gabarit de conversation et analyse les appels d'outils. Deux conséquences :

1. **Le harnais ne voit plus le prompt réel.** Le contexte affiché devient le corps JSON exact envoyé (messages et outils). Le gabarit n'est plus visible, et les tokens ne sont plus attribués exactement (AD-4).
2. **Une partie du harnais passe dans le réseau.** C'est un matériau pédagogique direct pour SM-3 (« où est hébergé le harnais ? ») : **à présenter, pas à cacher**.

### Artefacts touchés

| Artefact | Impact | Nature |
|---|---|---|
| SPEC.md | Why, CAP-3, CAP-31, CAP-35, **CAP-43 (nouvelle)**, palier 1, NFR-1, NFR-2, NFR-4, NFR-11, non-objectifs | Amendement |
| glossary.md, risks.md | « Modèle », « Modèle cloud » ; 3 risques | Amendement |
| PRD | FR-43, NFR-1, NFR-2, NFR-4, NFR-11, non-objectifs, §7, risques | Amendement (traçabilité) |
| ARCHITECTURE-SPINE.md | AD-2, AD-4, AD-5, AD-6, AD-8, AD-9, AD-12, AD-15, AD-16, AD-20, AD-21, schéma des processus, carte, reports | Amendement |
| EXPERIENCE.md | Diagnostic, sélecteur de modèle, données sortantes, 4 états | Amendement |
| DESIGN.md | Aucun : on réutilise `hosting-tag-local` et `hosting-tag-network` | — |
| stories.yaml | Story 11 ajoutée après la 10 | Ajout |
| Stories 1 à 8 faites ou en cours | Aucune reprise. Le code existant reste valide : le cloud s'ajoute à côté du chemin local | — |
| Stories 9 et 10 | Aucun changement. Les scénarios fournis restent jouables sans clé | — |

### Checklist

| Item | Statut | Note |
|---|---|---|
| 1.1 Story déclencheuse | [N/A] | Nouvelle exigence, pas une story |
| 1.2 Problème | [x] | Nouvelle exigence, changement de périmètre |
| 1.3 Preuves | [x] | Recherche du 2026-09-24 |
| 2.1 à 2.5 Épopées | [x] | Pas d'épopée : liste plate de stories. Une story ajoutée, placée en 11, aucune réordonnée |
| 3.1 PRD | [!] | Deux non-objectifs levés, NFR-4 élargie : voir §4 |
| 3.2 Architecture | [!] | 12 AD amendées le 2026-09-24 (AD-3 compris), puis une passe Update après validation (§6) ; aucune nouvelle AD, aucune nouvelle dépendance |
| 3.3 UX | [!] | Diagnostic et états : changement léger, comme demandé |
| 3.4 Autres | [!] | README (clé API, test avant séance), `wavestack.toml` : relèvent de la story 11 |
| 4.1 Ajustement direct | Viable | Effort moyen, risque moyen (réseau et secrets) |
| 4.2 Retour arrière | Non viable | Rien à annuler |
| 4.3 Revue du MVP | Non nécessaire | Le cloud reste une option : le produit tient sans elle |

## 3. Approche recommandée : ajustement direct

Une story 11 et des amendements aux documents. Aucune reprise de code livré.

**Décisions** (les vôtres, puis celles que je propose, marquées *prop.*) :

| # | Décision |
|---|---|
| D1 | Le modèle cloud est une **option explicite, jamais un défaut**. Aucun modèle cloud n'est chargé d'office, et les scénarios fournis restent jouables sans clé, en local. |
| D2 | **Un seul adaptateur `openai_chat`** : adresse de base, clé, modèle, streaming, `tools`. Il ouvre ses connexions par la fabrique `net` (httpx) : pas de SDK OpenAI, **aucune nouvelle dépendance** (*prop.*). |
| D3 | **Modèles cloud déclarés en configuration** : `[[cloud.models]]` dans `wavestack.toml` pour les préréglages publics, ajouts dans `settings.json` pour tout point d'accès qui ne doit pas figurer dans le dépôt public (Wavestone interne, NFR-11). L'en-tête d'authentification est configurable : `Authorization: Bearer` par défaut, y compris pour Azure par son API v1 ; un autre nom d'en-tête reste possible pour une passerelle interne (*prop.*). Les entrées fusionnent par `id` : un ajout dans `settings.json` n'efface pas les préréglages. *Précisée après validation (C3, H9).* |
| D4 | **Préréglages actifs : Groq et Mistral.** En commentaire, avec leur avertissement : Google (clause EEE, entraînement sans opt-out), NVIDIA (offre d'essai, réutilisation des contenus), OpenRouter (50 requêtes/jour, catalogue instable). Cloudflare, retenu comme exemple par la recherche, est écarté (décision d'Anaël, 2026-09-24). |
| D5 | **Capacités déclarées** par modèle (AD-6) : appel d'outils, raisonnement, contexte natif. Les appels d'outils arrivent déjà structurés par l'API : pas de parseur. Des arguments JSON invalides, et le refus `tool_use_failed` du fournisseur, suivent la voie de l'appel mal formé (CAP-16). |
| D6 | **Tokens en mode chat** : une estimation par segment, et le total fourni par l'API (`usage.prompt_tokens`). L'écart entre les deux va au segment `template`, libellé « Gabarit appliqué chez le fournisseur (estimé) ». Les valeurs estimées sont affichées avec « ≈ » ; le total ne l'est pas quand il vient de l'API (CAP-31). Pas de nouveau `SegmentKind`. |
| D7 | **Fenêtre effective** = min(fenêtre configurée, contexte natif déclaré, `tpm // 2` du modèle). Un tour avec un appel d'outil tient ainsi dans le quota par minute (Groq gpt-oss-120b : 8 000/min, soit 4 000). Au-delà, le 429 en plein tour est assumé comme matériau pédagogique. La fenêtre configurée peut être surchargée par modèle. *Amendée après validation (H8).* |
| D8 | **Données sortantes** : l'appel au modèle cloud devient une troisième sortie hors brique, `origin = model`, tracée (adresse et corps JSON exact). La clé n'apparaît **jamais** dans la trace, les journaux ni les réponses de l'API locale. |
| D9 | **Clé** : saisie au diagnostic, stockée dans `api_keys.json` du dossier de données (AD-20), séparé de `settings.json` (*prop.*), liée à l'hôte au moment de la saisie. Elle n'est envoyée qu'à cet hôte, et jamais sur une redirection. *Précisée après validation (C3).* |
| D10 | **Choix au diagnostic**, comme la story 1b. Le changement à chaud reste pour CAP-34 (palier 2). |
| D11 | **Erreur 429** : un événement expliqué en français (quota par minute ou par jour, `Retry-After`, pistes), sans nouvel essai automatique. 401, 404 et délai dépassé suivent la même voie. |
| D12 | **Test réel** : un bouton « Tester » par modèle cloud au diagnostic, qui envoie une invite fixe, sans donnée de l'utilisateur, avec le corps réel du modèle (outil compris), et affiche réponse, appel d'outil et débit. Le README demande ce test avant chaque séance. |
| D13 | **Schéma** : un modèle cloud est dessiné comme service réseau, dans la zone Réseau, avec son fournisseur (CAP-3). |
| D14 | **Latence** : NFR-1 reste une borne du local. En cloud, premier token, durée et **débit (tokens/s)** sont mesurés et affichés : c'est la démonstration. |
| D15 | **Conséquences visibles dans l'interface** (ajout d'Anaël à l'approbation) : un **avertissement** au choix d'un modèle cloud, avant tout appel qui porte des données de l'utilisateur, qui doit être confirmé ; le harnais refuse un choix cloud non confirmé (M11). Il est complété de trois repères permanents : le **modèle actif dans la barre haute** avec l'étiquette « RÉSEAU » et le fournisseur, une **infobulle** (même contenu que l'avertissement) et un **bandeau dans Contexte LLM**. L'avertissement liste les données qui partent, l'hébergement, l'usage pour l'entraînement, le gabarit et les appels d'outils traités chez le fournisseur, et les tokens estimés. Le texte commun est dans `content/` (AD-19) ; la partie propre au fournisseur vient de sa déclaration. |

**Effort :** moyen, une story. **Risque :** moyen (secrets, quotas instables, test clé en main absent). **Calendrier :** aucun effet sur les stories 8 à 10.

## 4. Propositions de modification détaillées

### 4.1 SPEC.md

**Why**, dernière phrase.
- ANCIEN : « Tourne entièrement en local sur CPU avec des petits modèles (SLM), incarnant ce qu'il enseigne sur la souveraineté et le numérique responsable. »
- NOUVEAU : « Tourne par défaut entièrement en local sur CPU avec des petits modèles (SLM), incarnant ce qu'il enseigne sur la souveraineté et le numérique responsable. En option, un modèle cloud appelé par API montre que le même harnais pilote des modèles plus gros, beaucoup plus vite, au prix de données qui quittent le poste. »

**CAP-3**, success.
- NOUVEAU (ajout) : « … ; un modèle cloud est dessiné comme service réseau, avec son fournisseur. »

**CAP-31**, intent.
- ANCIEN : « … les tokens de sortie et le temps écoulé. »
- NOUVEAU : « … les tokens de sortie, le temps écoulé et le débit de sortie (tokens/s). Pour un modèle cloud, la ventilation par segment est une estimation marquée « ≈ », et le total vient de l'API. »

**CAP-35**, success.
- ANCIEN : « … un modèle inconnu est lu depuis son fichier ; … »
- NOUVEAU : « … un modèle inconnu est lu depuis son fichier ; les capacités d'un modèle cloud sont déclarées dans la configuration ; … »

**Nouvelle capacité, après CAP-42 :**
```
- **CAP-43** Modèle cloud via API (FR-43, palier 1)
  - **intent:** L'utilisateur choisit au diagnostic un modèle cloud déclaré en configuration (préréglages Groq et Mistral, ou point d'accès ajouté, comme un endpoint interne), saisit sa clé API, le teste, puis mène les mêmes tours qu'en local.
  - **success:** Chaque modèle cloud affiche un pictogramme réseau et une infobulle (hébergement, usage des données pour l'entraînement, offre d'essai, quotas renvoyés vers la console du fournisseur) ; le choisir affiche un avertissement sur ses conséquences, à confirmer avant tout appel qui porte des données de l'utilisateur, et la barre haute signale ensuite un modèle réseau ; « Tester » prouve streaming et appel d'outils avec une invite fixe, sans donnée de l'utilisateur ; chaque appel est tracé comme donnée sortante, clé jamais tracée ; un refus du fournisseur (429, clé refusée) est un événement expliqué, jamais un plantage ; un modèle cloud n'est jamais choisi d'office : un choix explicite mémorisé est repris au lancement, sans réafficher l'avertissement.
```

**Constraints, palier 1** : ajouter « modèle cloud optionnel (CAP-43) » à la liste du socle.

**NFR-1**, ajout en fin : « Ces bornes visent les modèles locaux. Pour un modèle cloud, aucune borne : premier token, durée et débit sont mesurés et affichés. »

**NFR-2**, ajout : « Un modèle cloud ne coûte rien en mémoire ; quand il est actif, le modèle local est libéré. »

**NFR-4**
- ANCIEN : « … ou de deux sorties limitées et tracées comme données sortantes (sonde de connectivité du diagnostic, téléchargement de modèle sur demande explicite). … Aucune clé d'API requise pour les scénarios fournis. »
- NOUVEAU : « … ou de trois sorties limitées et tracées comme données sortantes (sonde de connectivité du diagnostic, téléchargement de modèle sur demande explicite, appel à un modèle cloud choisi explicitement, test compris). La clé d'un modèle cloud n'est envoyée qu'à l'hôte déclaré de ce modèle et n'apparaît jamais dans la trace. … Aucune clé d'API requise pour les scénarios fournis. »

**NFR-11**, ajout : « Les clés API sont stockées hors du dépôt, dans le dossier de données ; un point d'accès interne se déclare dans `settings.json`, jamais dans le dépôt. »

**Non-goals**
- ANCIEN : « Aucun fournisseur de modèle cloud. »
- NOUVEAU : « Aucun fournisseur de modèle cloud par défaut ni requis : le cloud reste une option explicite. »
- ANCIEN : « Pas de serveur local au format chat compatible OpenAI — texte brut natif seulement en V1, V2 pour le format chat. »
- NOUVEAU : « Le format chat compatible OpenAI sert aux modèles cloud et aux points d'accès déclarés. Pour un serveur local, WaveStack garde le texte brut natif, qui montre le gabarit : pointer l'adaptateur chat vers un serveur local reste possible par configuration, sans être visé. »

### 4.2 glossary.md, risks.md

**Modèle**
- ANCIEN : « le modèle de langage local (SLM) qui génère les réponses. »
- NOUVEAU : « le modèle de langage qui génère les réponses : un SLM local par défaut, ou un modèle cloud. »

**Nouveau terme :** « **Modèle cloud** : un modèle hébergé par un fournisseur et appelé par API au format chat. Le fournisseur applique lui-même le gabarit et analyse les appels d'outils : cette part du harnais est alors hébergée hors du poste. »

**Nouveaux risques :**

| Risque | Parade |
|---|---|
| Une offre gratuite change, ferme ou épuise son quota en séance (429). | Aucun fournisseur en dur (CAP-43), refus expliqué, test avant chaque séance, repli sur le modèle local. |
| Les prompts envoyés servent à entraîner le modèle du fournisseur. | Infobulle par fournisseur ; scénarios sans donnée sensible (NFR-11) ; désactivation en console quand elle existe (Mistral). |
| Une clé API fuit (trace, dépôt, capture d'écran). | Clé hors dépôt, jamais tracée ni renvoyée au navigateur, champ masqué. |

### 4.3 PRD (traçabilité)

Les modifications reprennent celles de SPEC.md :
- **§4.11**, nouvelle exigence **FR-43 : Modèle cloud via API**, même texte que CAP-43 ;
- **NFR-1, NFR-2, NFR-4 et NFR-11** : mêmes ajouts ;
- **§6, non-objectif « aucun fournisseur cloud »** : remplacé comme dans la SPEC ;
- **§7.1, palier 1** : ajout de « modèle cloud optionnel (FR-43) » ;
- **§7.2** : la ligne « Serveur local au format chat » est remplacée par la formulation de la SPEC ;
- **table des risques** : les trois lignes de §4.2.

### 4.4 ARCHITECTURE-SPINE.md

> Texte d'origine, tel qu'appliqué le 2026-09-24. Plusieurs règles ont été resserrées ensuite par la passe Update décrite au §6 ; le spine fait foi.

**Frontmatter :** `binds` + FR-43, `updated: '2026-09-24'`.

**AD-2**, catalogue.
- ANCIEN : `outbound_request{origin: brick|diagnostic|download}`
- NOUVEAU : `outbound_request{origin: brick|diagnostic|download|model}`
- `model_call_ended` ajoute `output_tps` (débit calculé par la session) et `usage_source: engine|api|estimate`.

**AD-4**, nouveau paragraphe après « Attribution des tokens » :
> **Mode chat (moteur `openai_chat`).**
> - Les segments sont assemblés par la même table d'emplacements. Au lieu du rendu Jinja, `context` construit le corps JSON (`messages`, `tools`), et `context_rendered` le porte tel qu'envoyé.
> - Les tokens de chaque segment sont **estimés** (octets UTF-8 / `chars_per_token`, réglable dans `wavestack.toml`).
> - Après l'appel, `usage.prompt_tokens` fait foi pour le total. L'écart va à un unique segment `template`, « gabarit appliqué chez le fournisseur ». S'il est négatif, les estimations sont réduites en proportion et `template` vaut 0. La somme reste égale au total.
> - Avant l'envoi, la jauge et le contrôle de dépassement (AD-9) utilisent l'estimation, plus l'écart du dernier appel.
> - Le contrôle d'ajout seul ne s'applique pas.
> - Les valeurs estimées sont marquées « ≈ » dans l'interface : c'est un matériau pédagogique (un harnais cloud compte sans tokenizer local).

**AD-5**
- ANCIEN : « Aucun adaptateur au format chat ni « compatible OpenAI » en V1. »
- NOUVEAU :
> - **`openai_chat`** (`POST {base_url}/chat/completions`, `stream: true`, `stream_options.include_usage`) : reçoit messages et outils structurés (AD-4, mode chat). `metadata()` déclare `input: chat`. `tokenize` et `token_pieces` sont indisponibles.
> - Le client HTTP vient de `net` (AD-15). La clé est lue dans `api_keys.json` (AD-20) et placée dans l'en-tête déclaré (`Authorization: Bearer` par défaut, `api-key` pour Azure).
> - Les deltas `content`, `reasoning` ou `reasoning_content` et `tool_calls` donnent les canaux `text`, `reasoning` et `tool_call`.
> - Un code HTTP d'erreur termine l'appel par `stop_reason: error` (AD-16). L'annulation ferme le flux.
> - Les autres adaptateurs reçoivent toujours du texte rendu.

**AD-6**, ajout : « Un modèle cloud n'a pas de fichier. Ses capacités (`tools`, `reasoning`, `context`) sont **déclarées** dans son entrée `[[cloud.models]]`. Son parseur d'appels d'outils est le format structuré de l'API. Une capacité non déclarée est absente. »

**AD-8**, ajout : « Un modèle cloud a un coût mémoire nul. Le sélectionner libère le modèle local ; les composants locaux (embedding, reranker) restent comptés. »

**AD-9**
- ANCIEN : « **Fenêtre effective** = min(fenêtre configurée, contexte natif, contexte du serveur). »
- NOUVEAU : « **Fenêtre effective** = min(fenêtre configurée, contexte natif, contexte du serveur, `max_window` du modèle cloud). La fenêtre configurée peut être surchargée par modèle cloud (`window`). `max_window` tient compte du quota de tokens par minute du fournisseur. »

**AD-12**, nœuds fixes : « `core.model` et `core.model_sub` prennent `hosting = network_service` quand le modèle actif est cloud. Ils sont alors dessinés en zone Réseau avec le nom du fournisseur, et l'arête `core.harness → core.model` porte `crosses_boundary`. »

**AD-15**
- Sorties hors brique, ajout : « l'appel au modèle cloud choisi explicitement, et son test au diagnostic, avec `origin = model`. Le corps tracé est le JSON exact ; aucun en-tête n'est tracé. »
- Liste d'adresses autorisées, ajout : « l'hôte de chaque entrée `[[cloud.models]]`, lu dans la même configuration (jamais d'une intention). »
- Ajout : « La clé n'accompagne jamais une redirection vers un autre hôte. »

**AD-16**, ajout : « Un refus du fournisseur devient `harness_error`, avec cause et pistes en français, sans nouvel essai automatique :
- 429 : quota par minute ou par jour, `Retry-After` s'il est fourni ;
- 401 ou 403 : clé refusée ;
- 404 : modèle retiré ;
- délai dépassé. »

**AD-20**, contenu du dossier : ajouter `api_keys.json`, `{model_id: key}`, écrit par la session seule. Il n'est jamais lu par `trace` ni renvoyé par l'API locale : le front ne reçoit que `key_set: bool`.

**AD-21**, étape 4 du lancement, ajout :
> - Les modèles cloud déclarés sont listés parmi les candidats, avec un champ de clé masqué (intention `set_api_key`) et un bouton « Tester » (intention `test_cloud_model`, classe b, sortie `origin = model`).
> - Un modèle cloud n'est jamais chargé d'office : il n'entre pas dans la règle « un seul fichier utilisable » de la story 1b.
> - Un modèle cloud enregistré devenu inutilisable (pas de clé, pas de réseau) produit un avertissement, puis la règle de démarrage s'applique.

**Schéma des processus :** ajouter dans la zone Réseau le nœud `llmcloud["Fournisseur LLM cloud<br/>Groq, Mistral, point d'accès déclaré"]` et `worker == "net, sortie tracée, clé hors trace" ==> llmcloud`.

**Carte des capacités :** `FR-43 : modèle cloud` → `models`, `context`, `net`, `config` → AD-4, AD-5, AD-6, AD-9, AD-15, AD-20, AD-21.

**Reports**
- Ligne V2 : « adaptateur de serveur au format chat » devient « serveur local au format chat, comme voie visée ».
- Ajout : « **GCP Vertex** : son point d'accès compatible OpenAI exige un jeton OAuth de courte durée, pas une clé statique. Il est hors de la story 11. Un point d'accès interne Wavestone derrière une passerelle à clé fonctionne par simple configuration. »

### 4.5 EXPERIENCE.md

**Surface « Diagnostic de démarrage »**, rôle, ajout : « … et les modèles cloud déclarés, avec saisie de la clé et test (FR-43). »

**Nouveau composant `cloud-model-row`** (dans « Ligne de diagnostic ») :
> Un modèle cloud déclaré, dans la liste des candidats. On y trouve :
> - l'étiquette `hosting-tag-network` (globe, « RÉSEAU »), les candidats locaux portant `hosting-tag-local` : **c'est le pictogramme cloud/local**, sans nouveau code visuel ;
> - le nom du fournisseur et du modèle ;
> - une infobulle (hébergement, usage des données pour l'entraînement, « offre d'essai » le cas échéant, quotas à lire dans la console du fournisseur, et pour Google la clause EEE) ;
> - le champ « Clé API », masqué, avec la mention « Stockée sur ce poste, jamais affichée ni tracée » ;
> - les boutons « Tester » et « Choisir ».
>
> Sans clé, « Choisir » et « Tester » sont désactivés, avec la raison.

**Nouveau composant `cloud-warning`** (D15) :
> Au clic sur « Choisir » d'un modèle cloud, un avertissement s'ouvre dans la page, sans boîte de dialogue du navigateur. Titre : « Ce modèle tourne hors de votre poste ». Il liste :
> - **ce qui part** : chaque appel envoie tout le contexte (messages, prompt système, résultats d'outils, mémoire) à {fournisseur}, {hébergement} ;
> - **ce qu'en fait le fournisseur** : usage pour l'entraînement (oui, non, désactivable en console), « offre d'essai » le cas échéant ;
> - **ce que le harnais ne voit plus** : le gabarit et l'analyse des appels d'outils se font chez le fournisseur, et les tokens par segment sont estimés.
>
> Deux boutons : « Utiliser ce modèle » et « Annuler ». L'avertissement se montre à chaque nouveau choix d'un modèle cloud, pas à chaque lancement.

**Nouveau composant `model-indicator`** (barre haute, D15) :
> Le nom du modèle actif, précédé de `hosting-tag-local` ou `hosting-tag-network` (« RÉSEAU · {fournisseur} »). Au survol ou au focus clavier, une infobulle reprend le contenu de l'avertissement. Il est cliquable vers le diagnostic.

**Bandeau de Contexte LLM** (mode chat, D15) : « Modèle cloud : ce contexte est le corps JSON envoyé à {fournisseur}. Le gabarit y est appliqué hors du poste ; les tokens par segment sont estimés (≈). »

**Sélecteur de modèle (`model-picker`)**, ajout : « Les modèles cloud y apparaîtront avec CAP-34 (palier 2). D'ici là, le choix se fait au diagnostic. »

**Données sortantes (`outbound-payload`)**, ajout : « Pour un appel à un modèle cloud : adresse, taille, et corps JSON exact dans Contexte LLM. Jamais la clé. »

**Nouveaux états :**

| État | Surface | Traitement |
|---|---|---|
| Modèle cloud actif | Schéma, Contexte LLM, barre haute | Barre haute : `model-indicator` en « RÉSEAU · {fournisseur} ». Nœud Modèle en zone Réseau, avec le fournisseur ; le flux Harnais → Modèle franchit la frontière à chaque appel. Contexte LLM : bandeau, corps JSON envoyé, tokens « ≈ » et segment « Gabarit appliqué chez le fournisseur ». Le compteur affiche le débit (tokens/s). |
| Test d'un modèle cloud | Diagnostic | Ligne « En cours », puis OK (réponse, appel d'outil reçu, débit) ou Échec avec la raison du fournisseur. |
| Quota dépassé (429) | Orchestration, vue humain | Carte d'erreur : « Le fournisseur refuse l'appel : quota dépassé (par minute ou par jour). » Suivent le délai conseillé s'il est connu, puis les pistes : attendre, réduire le contexte (lazy loading), revenir au modèle local au prochain lancement. Aucun nouvel essai automatique. |
| Clé refusée ou absente | Diagnostic, Orchestration | « Clé refusée par {fournisseur} (401). Vérifiez-la dans le diagnostic. » |

### 4.6 stories.yaml (ajout après la story 10)

```yaml
- id: "11"
  title: Modèles cloud via API (Groq, Mistral)
  description: >-
    Modèles cloud déclarés en configuration (préréglages Groq et Mistral, exemples
    Google, NVIDIA et OpenRouter avec avertissement), choisis au diagnostic avec
    saisie de la clé, test réel et infobulle par fournisseur ; mêmes tours qu'en
    local, appels tracés comme données sortantes, refus du fournisseur expliqués
    (CAP-43, CAP-3, CAP-31, CAP-35).
  spec_checkpoint: true
  done_checkpoint: true
  invoke_dev_with: >-
    Implémenter l'adaptateur openai_chat derrière le port Engine (AD-5) avec le
    client de net (AD-15, origin model, hôtes des modèles cloud autorisés, clé hors
    trace), le mode chat du contexte avec tokens estimés et total de l'API (AD-4),
    les capacités déclarées (AD-6), la fenêtre plafonnée par modèle (AD-9),
    api_keys.json (AD-20), la liste, la clé, le bouton Tester et l'avertissement
    au diagnostic (AD-21), l'indicateur de modèle et le bandeau de Contexte LLM
    (EXPERIENCE.md), et les refus expliqués (AD-16). Aucune nouvelle dépendance. Point
    sensible (secrets, sortie réseau) : faire vérifier la garde et l'absence de
    clé dans la trace avant la clôture.
```

## 5. Transmission

**Portée : modérée.** Aucune refonte du plan : une story ajoutée et des amendements de documents. Aucun code ne change avant la story 11.

| Qui | Responsabilité |
|---|---|
| Anaël (PO) | Approuver cette proposition, puis fusionner `spec/cloud-llm` dans `main` une fois la story 8 terminée. Créer les comptes Groq et Mistral avec sa clé, pour lever les questions ouvertes (carte bancaire, quotas réels). |
| Développeur (story 11, après la 10) | Implémenter selon `invoke_dev_with`. Vérifier en réel les deux préréglages. |

**Critères de succès :**
- les scénarios fournis passent sans clé ;
- un tour Groq ou Mistral fonctionne avec outils ;
- la clé est absente de la trace, de `settings.json`, des journaux et de `/api/*` (vérifié par test) ;
- un 429 simulé par le moteur factice produit un événement expliqué ;
- le schéma montre le modèle en zone Réseau ;
- choisir un modèle cloud affiche l'avertissement avant tout appel, et la barre haute signale un modèle réseau.

**Péremption :** la compatibilité de Mistral et l'appel d'outils de Groq sont à revérifier au 2026-10-01 (carte de péremption de la recherche). Le bouton « Tester » en tient lieu en séance.

## 6. Application

Approuvée par Anaël le 2026-09-24, avec l'ajout D15 ; Cloudflare écarté. Amendements appliqués sur la branche `spec/cloud-llm` : SPEC.md, glossary.md, risks.md, stories.yaml, PRD, ARCHITECTURE-SPINE.md, EXPERIENCE.md. Aucun code modifié.

**Update après validation (2026-09-24).** La validation des amendements du spine (`architecture/.../reviews/validation-cloud-2026-09-24.md`) a conclu qu'ils ne suffisaient pas pour la story 11. Une passe Update du spine a appliqué les correctifs C1 à C3, H4 à H9 et M10 à M15 :
- port `Engine` à requête entièrement construite ;
- `tool_call_id` attribué par la session ;
- clé liée à l'hôte, en `SecretStr`, sans redirection ;
- préréglages déclaratifs (`stream_usage`, format du raisonnement) ;
- événement `context_reconciled` ;
- liste fermée des erreurs du fournisseur ;
- schéma `CloudModel` fusionné par `id` ;
- classes d'intentions du diagnostic ;
- confirmation vérifiée par la session.

Ont été amendés AD-2 à AD-6, AD-9 à AD-13, AD-15, AD-16, AD-19 à AD-21 et AD-23 à AD-25. Aucun AD n'est nouveau ni renuméroté.

Deux décisions ont été déléguées :
- **H8** : la fenêtre est plafonnée à `tpm // 2`, et un 429 au-delà reste un matériau pédagogique ;
- **M11** : `select_model{acknowledged: true}` est vérifié par la session, et « Tester » envoie une invite fixe, sans donnée de l'utilisateur.

La SPEC (CAP-31, CAP-43), le PRD (FR-43) et EXPERIENCE.md ont été alignés en conséquence.
