---
title: 'Relecture de la passe Update cloud (FR-43) : grille et réconciliation'
date: '2026-09-24'
target: ARCHITECTURE-SPINE.md (passe « Update » du 2026-09-24, correctifs C1 à L17)
authority: .memlog.md (entrées l. 99 à 120)
inputs:
  - validation-cloud-2026-09-24.md
  - review-cloud-rubric-reconcile.md
  - review-cloud-adversary.md
  - ../../../specs/spec-agentic-harness-training-demo/SPEC.md (CAP-31, CAP-43)
  - ../../sprint-change-proposal-2026-09-24.md (D1 à D15)
  - ../../ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
---

# Relecture de la passe Update cloud : grille et réconciliation

## Verdict

La passe ferme les trois critiques et les six hautes du rapport de validation. Aucun constat ne reste de niveau Critique ou Haute. Le spine est **prêt pour la story 11 après une courte passe de retouches** : 7 constats moyens et 13 bas, tous corrigeables en une ou deux phrases, sans nouvel AD.

Les points les plus sensibles :
- `context_reconciled` ne porte pas la ventilation par type. H6 n'est donc fermé qu'en partie : le front devrait encore additionner (N1).
- La sémantique de `select_model` hors diagnostic se contredit entre AD-3, AD-8 et AD-21 (N2).
- `base_url` en https seul contredit le Deferred et la SPEC sur la boucle locale (N3).
- Le 422 par défaut de FastAPI renvoie l'entrée reçue, donc la clé (N4).

Les numéros de ligne renvoient à `ARCHITECTURE-SPINE.md` dans son état du 2026-09-24, 20:40.

## 1. État des constats de la validation

| Constat | État | Où (AD, ligne) | Remarque |
| --- | --- | --- | --- |
| **C1** Port moteur, deux « JSON exacts » | **Fermé** | AD-5 titre l. 198, Prevents l. 201, signature l. 202-203, test d'égalité l. 211 ; AD-4 titre l. 144, corps l. 183 | Reste N15 : qui écrit les champs de raisonnement et `stream_options` dans le corps. |
| **C2** `tool_call_id` | **Fermé** | AD-4 l. 155-156 ; AD-25 l. 590 ; AD-2 l. 118 ; conventions l. 598 | Rien à ajouter. |
| **C3** Clé vers un autre hôte | **Fermé** | AD-20 l. 496, l. 506 ; AD-15 l. 391, l. 420 ; AD-5 l. 212 | Azure : « Bearer » et `/openai/v1/` figurent au memlog (l. 102) mais pas dans le spine (N14). |
| **H4** Clé dans la trace | **Fermé** en règle | AD-15 l. 420-424 ; AD-23 l. 558 | Un piège d'implémentation reste ouvert : le 422 de FastAPI (N4). |
| **H5** Préréglage Mistral | **Fermé** | AD-5 l. 213-216 ; AD-6 l. 233 ; AD-20 l. 501-503 | — |
| **H6** Tokens réconciliés | **Partiel** | AD-2 l. 105 ; AD-4 l. 190-194 | `context_reconciled` n'a pas de ventilation par type (N1). Un écart négatif avant l'appel n'est pas traité (N10). La clé du `ratio` est mal choisie (N6). |
| **H7** Issues du fournisseur, D5 | **Fermé** | AD-16 l. 432-444 ; AD-10 l. 301 | L'erreur fournisseur dans un sous-agent n'est pas couverte (N8). |
| **H8** Quota par minute | **Fermé** | AD-9 l. 270-272 ; AD-20 l. 502 ; Deferred l. 773 | `max_window` a disparu du spine. Le pronom de « la surcharger (`window`) » est ambigu (N12). |
| **H9** Schéma `[[cloud.models]]` | **Fermé** | AD-20 l. 498-509 ; conventions l. 601 ; AD-21 l. 530 | `disclosure` n'est pas défini (N5), `base_url` en https seul (N3), `selected_model.kind` sans serveur local (N20). |
| **M10** Classes et diagnostic | **Fermé** | AD-3 l. 132-136 | La sémantique de `select_model` hors diagnostic se contredit (N2). |
| **M11** Confirmation | **Fermé** | AD-21 l. 529 ; AD-13 l. 357 ; CAP-43 alignée | Contournable par un `settings.json` édité à la main, et rien n'est refusé sans clé (N9). La phrase du memlog « la ligne dit ce qui part » manque (N17). |
| **M12** Origine et portée | **Fermé** | AD-2 l. 121 ; AD-15 l. 411-414 | Les ids d'un appel de test (`turn_id = null`) ne sont pas définis (N6). |
| **M13** Pas de réseau au lancement | **Fermé** | AD-21 l. 531 | — |
| **M14** Contenus | **Fermé** | AD-19 l. 483 ; carte l. 738 | La carte omet AD-11, 13, 24 et 25, pourtant amendés (N16). |
| **M15** Rendu chat | **Fermé** en principe | AD-4 l. 186-189 ; AD-6 l. 234 ; AD-25 l. 590 | Le type et l'emplacement de l'injection forcée et de l'erreur mal formée ne sont pas fixés (N7). |
| **L16** Procédure Update | **Partiel** | memlog l. 82-120 | Le memlog est à jour. `architecture-view.html` n'a pas été régénéré (0 mention de « cloud »), et aucune entrée « spine finalized » ne clôt la passe (N16). |
| **L17** Débit, `raw_output`, sous-agent | **Fermé** | AD-2 l. 116-118 ; AD-5 l. 216 ; AD-11 l. 320 ; AD-24 l. 571 | Cas limites : `gen_ms = 0` et tokens de sortie sans `usage` (N11). |
| **L18** Faux positifs du lint | Sans objet | — | — |

## 2. Nouveaux constats (grille)

### N1. `context_reconciled` sans ventilation par type : le front devrait additionner (Moyenne)
- **Emplacement.** AD-2 l. 105 (`context_reconciled{call_id, segments: [{id, tokens}], used, percent, usage_source}`) ; AD-4 l. 192 (« le front n'additionne ni ne répartit rien ») et Prevents l. 147 ; AD-9 l. 279 (« ventilation par type de segment, tous calculés par la session ») ; AD-1 l. 78 (« ni ventilation de la jauge »).
- **Problème.** La jauge empile par type. Avec des tokens par segment seulement, le front doit rejoindre `id → kind` dans `context_rendered` puis sommer. Il recalcule donc la ventilation, ce que la règle interdit. Il manque aussi `near_limit` et `overflow`. La Rule d'AD-4 contredit son propre Prevents, et H6 n'est fermé qu'en partie (CAP-31 : « sans recalcul côté front »).
- **Correctif.** Ajouter à `context_reconciled` la ventilation par type et `near_limit`, calculés par la session avec les mêmes champs que `context_rendered` (AD-9). Écrire que les projections remplacent les deux, segments et ventilation.

### N2. `select_model` hors diagnostic : trois effets différents (Moyenne)
- **Emplacement.** AD-3 l. 136 (classe b, « changer de modèle ») et l. 142 (« un réglage modifié prend effet au tour suivant ») ; AD-8 l. 263 (« Le sélectionner libère le modèle local ») ; AD-21 l. 528 (« Un choix fait après le chargement vaut pour le prochain lancement »).
- **Problème.** Quand un modèle cloud est choisi depuis le diagnostic, session en `idle`, un modèle local étant chargé, trois lectures sont possibles : libération immédiate (AD-8), effet au tour suivant (AD-3), ou simple mémorisation pour le prochain lancement (AD-21). La session, le `LoadRegistry` et `active_model` peuvent ainsi diverger.
- **Correctif.** Une seule règle dans AD-3 ou AD-21 : hors diagnostic bloquant, et jusqu'à CAP-34, `select_model` n'écrit que `selected_model` et répond « prendra effet au prochain lancement ». AD-8 précise « quand il devient le modèle actif, au lancement ».

### N3. `base_url` en https seul, alors que la boucle locale reste « possible » (Moyenne)
- **Emplacement.** AD-20 l. 507 (« `base_url` est en https, sans paramètre de requête ») ; Deferred l. 772 (« `openai_chat` vers la boucle locale (possible, non visé) ») ; SPEC l. 183 ; AD-15 l. 406.
- **Problème.** Un serveur local se sert en `http://127.0.0.1`. Le validateur pydantic le refuse, alors que le Deferred et la SPEC le disent possible et que memlog l. 120 le traite « en cloud ». Deux unités trancheront différemment : le validateur de `config` et l'auteur d'une entrée de test.
- **Correctif.** Soit « https, ou http pour la seule boucle locale », soit refuser explicitement la boucle locale en V1 et corriger le Deferred ainsi que la note de la SPEC.

### N4. Le 422 par défaut de FastAPI renvoie l'entrée reçue, donc la clé (Moyenne)
- **Emplacement.** AD-15 l. 422 (« une réponse d'intention ne renvoie jamais ce qu'elle a reçu ») et l. 424 (test de la clé sentinelle) ; AD-18 l. 463-467.
- **Problème.** Le gestionnaire par défaut de `RequestValidationError` renvoie `detail[].input`. Pour un champ manquant, c'est le corps entier, clé comprise. pydantic ne masque pas un `SecretStr` dans `input`. La règle est juste, mais le chemin par défaut du framework la viole sans que personne ne l'écrive.
- **Correctif.** AD-18 : un gestionnaire d'erreurs de validation des intentions qui ne renvoie ni `input` ni `ctx`. Le test sentinelle d'AD-15 inclut un `set_api_key` invalide (champ `id` manquant).

### N5. `active_model.disclosure` sans forme (Moyenne)
- **Emplacement.** AD-12 l. 335 (`active_model{id, label, hosting, provider, disclosure}`) ; AD-20 l. 501 (le `CloudModel` n'a aucun champ `disclosure`) ; AD-19 l. 483.
- **Problème.** C'est la forme partagée entre la session et le front (infobulle, avertissement, `model-indicator`). Chacun composera `disclosure` à sa manière, à partir de `hosting_fr`, `training`, `trial` et `notes_fr`.
- **Correctif.** Fixer `disclosure = {hosting_fr, training, trial, notes_fr} | null` (null pour un modèle local). Les libellés des valeurs de `training` sont dans `content/`.

### N6. Identifiants d'un appel de test, et clé du `ratio` (Moyenne)
- **Emplacement.** AD-2 l. 93 (ids nuls hors portée) ; AD-21 l. 532 (le test émet `model_call_*` avec `turn_id = null` et initialise le `ratio`) ; AD-5 l. 211 (test d'égalité « du même `call_id` ») ; AD-4 l. 191 (`ratio` tenu par (modèle, `context_id`)) ; conventions l. 598 (`call_id = {turn_id}.{context_id}.c{n}`).
- **Problème.**
  - Le test fait jusqu'à deux appels, dont le `call_id` et le `step_id` sont nuls ou sans format. On ne peut ni apparier `model_call_started` et `model_call_ended`, ni relier `context_rendered` à `outbound_request` (C1).
  - Son `context_id` est nul : on ne sait pas quel `ratio` il initialise.
  - `sub{n}` est renuméroté à chaque délégation, donc un `ratio` indexé par `context_id` n'est jamais réutilisé pour un sous-agent.
- **Correctif.**
  - Conventions : pour le test, `call_id = diag.{cloud_id}.c{n}` et `step_id = diag.{cloud_id}.s{n}`, avec `turn_id` et `context_id` nuls.
  - AD-4 : `ratio` indexé par (`id` du modèle, `main` ou `sub`). Le test initialise les deux.

### N7. Action forcée rendue en injection, et erreur d'un appel mal formé : ni type ni emplacement (Moyenne)
- **Emplacement.** AD-6 l. 234 (« une action `forced` est rendue en `injection` ») ; AD-3 l. 140 (abandon seulement si `forced` est indisponible) ; AD-4 l. 162 (le message utilisateur ne contient que `hook_injection`, `rag_excerpt` et `user_message`) et l. 189 (« un message `user` qui porte l'erreur réinjectée ») ; AD-25 l. 588-590.
- **Problème.**
  - Le résultat d'outil injecté dans le message utilisateur n'a ni `SegmentKind` ni place dans la table d'emplacements. De même pour le message d'erreur d'un appel mal formé en mode chat.
  - Une unité calculera « `forced` indisponible » pour un modèle sans `tools` et abandonnera l'action (AD-3). Une autre la rendra en injection.
  - Une action forcée sur un outil MCP en lazy loading tombe entre « erreur réinjectée si doc non chargée » (l. 588) et « définition dans `tools` » (l. 590).
- **Correctif.** Compléter la table d'AD-4 :
  - injection forcée : `tool_result` de la brique de l'action, dans le message utilisateur, après `user_message` ;
  - erreur d'un appel mal formé : `tool_result`, en phase `turn`.

  Dans AD-6, écrire « `forced` reste disponible, rendu en injection ». Dans AD-25, écrire qu'une action forcée ignore l'exigence de doc chargée et ajoute la définition de son outil à `tools`.

### N8. Erreur du fournisseur dans un sous-agent (Basse)
- **Emplacement.** AD-11 l. 319 ; AD-16 l. 430 et 432.
- **Problème.** Un 429 dans `sub{n}` est probable, puisqu'une délégation fait bien plus de deux appels par minute. AD-16 dit « le tour se termine en `error` », AD-11 « jamais `turn_ended` depuis un sous-contexte », et rien ne tranche entre les deux.
- **Correctif.** AD-11 : une issue d'AD-16 dans `sub{n}` émet `harness_error` avec `context_id = sub{n}`, puis `tool_ended{status: error}` de `delegate`, avec l'erreur réinjectée en français.

### N9. Garanties laissées au seul front, et confirmation contournable (Basse)
- **Emplacement.** AD-21 l. 529-531 ; EXPERIENCE (`cloud-model-row` : « Tester » et « Choisir » désactivés sans clé).
- **Problème.**
  - Rien n'oblige la session à refuser `select_model` ou `test_cloud_model` quand `key_set = false`. Le test partirait sans en-tête et recevrait un 401.
  - Un `selected_model {kind: cloud}` écrit à la main dans `settings.json` est repris au lancement sans avoir jamais été confirmé.
  - Si la déclaration change après la confirmation (hébergement, `training`), l'avertissement n'est pas réaffiché.
- **Correctif.** La session refuse sans clé, avec la raison de `content/`. `selected_model` mémorise `acknowledged`, avec une empreinte de `disclosure`. Au lancement, si la marque manque ou si l'empreinte diffère, la session demande une nouvelle confirmation.

### N10. Écart négatif avant l'appel (Basse)
- **Emplacement.** AD-4 l. 191 (« l'écart vaut la somme des estimations × (`ratio` − 1) »).
- **Problème.** Avec un `ratio` inférieur à 1, le segment « chez le fournisseur » reçoit des tokens négatifs avant l'envoi. La règle de réduction proportionnelle n'est écrite que pour l'après-appel (l. 192).
- **Correctif.** Appliquer la même réduction, arrondie par les plus forts restes, avant l'envoi.

### N11. Débit et tokens de sortie dans les cas limites (Basse)
- **Emplacement.** AD-2 l. 116-117.
- **Problème.**
  - Avec un seul delta, `gen_ms = 0`, et `output_tps` divise par zéro.
  - Quand `usage_source = estimate`, rien ne dit comment on estime `output_tokens`.
- **Correctif.** `output_tps = null` si `gen_ms` est nul. `output_tokens` estimé vaut `ceil(caractères / chars_per_token)` sur tous les canaux.

### N12. Surcharge de fenêtre : pronom ambigu, source non transmise (Basse)
- **Emplacement.** AD-9 l. 270 (« Un modèle cloud peut la surcharger (`window`), et l'interface affiche alors la source de la fenêtre »).
- **Problème.**
  - « la » peut désigner la fenêtre effective. Dans ce cas, `window` contournerait `tpm // 2`.
  - La « source » n'a aucun champ : le front la déduirait, ce qui viole AD-1.
- **Correctif.** « `window` remplace la fenêtre configurée ; le minimum s'applique toujours. » Ajouter `window_source: configured|native|server|tpm|override` à `context_rendered` et à `context_preview`.

### N13. Liste autorisée : « entrée active » ambiguë (Basse)
- **Emplacement.** AD-15 l. 407.
- **Problème.** Si « active » veut dire « modèle choisi », la garde bloque le test d'un autre modèle déclaré.
- **Correctif.** Remplacer par « entrée `enabled` ».

### N14. Forme d'`auth_header` et cas Azure (Basse)
- **Emplacement.** AD-20 l. 501 et 507 ; AD-5 l. 212 ; memlog l. 102.
- **Problème.**
  - `auth_header` n'a pas de type. Pour exprimer `api-key: {key}` face à `Authorization: Bearer {key}`, `config` et l'adaptateur parseront chacun à leur façon.
  - « Bearer » et `/openai/v1/` pour Azure sont au memlog, pas dans le spine.
- **Correctif.** `auth_header{name = "Authorization", scheme = "Bearer" | null}`. Écrire dans AD-5 : « Azure : `base_url` en `…/openai/v1`, `Bearer` ».

### N15. Qui écrit les champs optionnels du corps (Basse)
- **Emplacement.** AD-4 l. 183 (« `context` construit le corps complet ») ; AD-6 l. 233 (« La brique raisonnement ajoute au corps ») ; AD-5 l. 213 (`stream_options`, placé dans la section de l'adaptateur).
- **Problème.** Une brique ne renvoie que des segments et des outils (paradigme, l. 26). La contribution « paramètres de requête » n'existe pas, et la phrase sur `stream_options` se lit comme un ajout de l'adaptateur, ce que C1 interdit.
- **Correctif.** La brique raisonnement contribue `reasoning.on` ou `reasoning.off` au `TurnState`, et `context` seul les écrit dans le corps. Déplacer la phrase sur `stream_options` dans AD-4, mode chat.

### N16. Traçabilité et clôture de la passe (Basse)
- **Emplacement.** Carte l. 738 ; `Binds` d'AD-8 (l. 255), AD-11 (l. 307), AD-13 (l. 345), AD-24 (l. 565) et AD-25 (l. 575) ; frontmatter l. 12-17 ; Prevents d'AD-21 l. 514.
- **Problème.**
  - La ligne FR-43 et ces `Binds` omettent AD-11, 13, 24 et 25, pourtant amendés pour le cloud (memlog l. 99), ainsi qu'AD-8.
  - Le frontmatter ne cite ni la SPEC ni la proposition.
  - `architecture-view.html` ne contient aucune mention du cloud.
  - Le Prevents d'AD-21 ne nomme ni le choix cloud d'office ni le choix sans confirmation.
  - Aucune entrée « spine finalized » ne clôt la passe dans le memlog.
- **Correctif.** Compléter la carte et les `Binds`, les `sources` et le Prevents d'AD-21. Régénérer la vue. Ajouter l'événement de clôture au memlog après ce gate.

### N17. Décisions du memlog absentes du spine (Basse)
- **Emplacement.** memlog l. 111 ; AD-21 l. 532.
- **Problème.**
  - La ligne du test dit ce qui part (requête fixe, clé, adresse IP du poste) : c'est la contrepartie de « Tester n'exige pas la confirmation », et elle manque.
  - `context_rendered.body` est décrit en octets, alors qu'un événement est du JSON.
- **Correctif.** Ajouter la phrase à AD-21. Écrire que `body` est une chaîne UTF-8 dans l'événement, et que les octets envoyés valent `body.encode("utf-8")`.

### N18. Mistral, texte et appel d'outil dans un même message : aucun défaut fixé (Basse)
- **Emplacement.** Deferred l. 771 ; AD-4 l. 188.
- **Problème.** L'assembleur du corps doit choisir entre garder `content` à côté de `tool_calls` et l'omettre. Le Deferred attend que le test tranche, mais le test utilise ce même assembleur.
- **Correctif.** Fixer un défaut dans AD-4 (par exemple : `content` omis s'il est vide, gardé sinon) et le revisiter si Tester renvoie un 422.

### N19. Débit gonflé par un raisonnement caché (Basse)
- **Emplacement.** AD-2 l. 117 ; adversaire, P12.
- **Problème.** Un raisonnement non transmis est compté dans `completion_tokens` mais n'apparaît dans aucun delta. Il retarde le premier token et fausse la comparaison du débit entre local et cloud.
- **Correctif.** Porter sur `model_call_ended` l'écart entre `completion_tokens` et les tokens vus, libellé « raisonnement non transmis », ou écrire qu'il est ignoré en V1.

### N20. `selected_model.kind` sans serveur local (Basse)
- **Emplacement.** AD-20 l. 497 ; AD-7 l. 248.
- **Problème.** `file|cloud` ne permet pas de mémoriser un serveur Ollama ou llama-server (palier 2). CAP-34 en ajoutera un troisième, sans que l'enum ait été annoncée comme extensible.
- **Correctif.** Écrire `kind: file|server|cloud` dès maintenant, ou « enum étendue par CAP-34 ».

## 3. Grille « bon spine », synthèse

- **Rules applicables.** Oui dans l'ensemble. Les règles cloud sont normatives et testables : égalité octet pour octet, clé sentinelle, `MockTransport`, formule `tpm // 2`. N1, N2, N6 et N7 sont les endroits où deux unités peuvent encore diverger.
- **Titres et Prevents.** AD-4 et AD-5 sont réalignés (C1). Le Prevents d'AD-4 est contredit par la forme de `context_reconciled` (N1). Celui d'AD-21 est incomplet (N16).
- **Deferred.** Aucun item ne laisse deux unités diverger, sauf deux. « `openai_chat` vers la boucle locale » contredit une Rule (N3). « Mistral, texte et appel d'outil » laisse le défaut de l'assembleur ouvert (N18). « Renvoi du raisonnement » et « espacement `x-ratelimit` » sont bien des révisions conditionnelles de règles déjà tranchées.
- **Contradictions nouvelles.** N2 (AD-3, AD-8 et AD-21), N3 (AD-20 et Deferred), N7 (AD-3 et AD-6 sur `forced`), N8 (AD-11 et AD-16).
- **memlog et spine.** Toutes les décisions l. 100-117 sont dans le spine, sauf deux fragments (N14 Azure, N17 « ce qui part »). Rien dans le spine ne manque au memlog, hormis « l'interface affiche la source de la fenêtre » (AD-9 l. 270), qui est sans forme (N12).

## 4. Réconciliation

### D1 à D15

| D | Couverture dans le spine | Écart |
| --- | --- | --- |
| D1 Option explicite | AD-21 l. 530 ; un scénario ne choisit pas de modèle (AD-19 l. 481) | — |
| D2 Un adaptateur, sans dépendance | AD-5 l. 210-216 ; AD-15 ; Stack (httpx déjà présent) | — |
| D3 Déclaration, en-tête configurable | AD-20 l. 498-509 | La proposition dit « `api-key` pour Azure » (l. 79 et 189). Le spine impose l'API v1 (N14). **À aligner dans la proposition.** |
| D4 Préréglages Groq et Mistral | Seed l. 654 ; `enabled` l. 509 | Les exemples en commentaire relèvent de `wavestack.toml`, pas du spine. |
| D5 Capacités, JSON invalide | AD-6 l. 232 ; AD-10 l. 301 | — |
| D6 Tokens en mode chat | AD-4 l. 190-194 | « Tout ≈ » est devenu « ≈ sauf le total quand `usage_source = api` » (aligné sur CAP-31). N1 reste à corriger. |
| D7 Fenêtre | AD-9 l. 270-272 | D7 est à jour, mais le §4.4 de la proposition (l. 200) cite encore `max_window`. **À aligner dans la proposition.** |
| D8 Sortie tracée, clé hors trace | AD-15 l. 411-424 | N4. |
| D9 `api_keys.json`, hôte déclaré | AD-20 l. 496 ; AD-15 l. 420 | — |
| D10 Choix au diagnostic | AD-21 l. 528 | N2. |
| D11 429 et autres refus expliqués | AD-16 l. 432-444 | N8. |
| D12 Tester, README | AD-21 l. 520 et l. 532 | N6, N17. |
| D13 Zone Réseau | AD-12 l. 334 ; seed l. 654 et 667 | — |
| D14 Débit mesuré | AD-2 l. 116-117 | N11, N19. |
| D15 Avertissement, indicateur, infobulle, bandeau | AD-21 l. 529 ; AD-12 l. 335 ; AD-19 l. 483 | N5, N9. Le bandeau se déduit de `active_model.hosting`. |

### CAP-43

Tous les éléments sont couverts :
- choix au diagnostic (AD-21) ;
- préréglages et points d'accès ajoutés (AD-20) ;
- clé (AD-20, AD-15) ;
- test avec une invite fixe (AD-21) ;
- pictogramme et infobulle (AD-12 `active_model`, `training`, `trial`, `notes_fr` pour les quotas) ;
- confirmation avant tout appel qui porte des données de l'utilisateur (AD-21 l. 529, formulation alignée) ;
- barre haute (AD-12) ;
- trace et clé (AD-15) ;
- refus expliqués (AD-16) ;
- « jamais choisi d'office », avec reprise sans avertissement (AD-21 l. 530).

Réserves : N5 (forme de `disclosure`) et N9 (garanties côté session).

### CAP-31

Sont couverts : le total et la ventilation, l'estimation « ≈ » avec le libellé « (estimé) », le total de l'API, le débit pour chaque appel dans les deux modes. En revanche, « sans recalcul côté front » n'est pas tenu tant que N1 est ouvert.

### EXPERIENCE

- `cloud-model-row` : « désactivé sans clé » se fait côté front seulement (N9).
- `model-indicator` : AD-12 `active_model`.
- État « Quota dépassé » : `quota_scope` et `retry_after_s` (AD-16).
- Bandeau : AD-12.

Aucune contradiction nouvelle.

## 5. Ordre de correction suggéré

1. N1, N2, N6 et N7 : formes partagées et sémantiques contradictoires, dans AD-2, 3, 4, 6, 8, 21 et 25 et les conventions.
2. N3, N4 et N5 : schéma, garde de la clé côté API et forme de `disclosure`.
3. Les basses, regroupées en une retouche. Puis le memlog (entrées N1 à N20 retenues, et l'événement de clôture), la vue HTML, et l'alignement de la proposition (D3, §4.4 l. 200).
