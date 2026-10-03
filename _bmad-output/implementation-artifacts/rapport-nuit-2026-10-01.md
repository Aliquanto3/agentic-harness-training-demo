# Rapport de la nuit du 1er au 2 octobre 2026

Consigne d'Anaël (01/10, vers 22 h 30) : implémenter au maximum ses besoins exprimés, en parallèle par sous-agents, commiter sans pousser, puis relancer une batterie complète (E2E et Chrome compris).

## Résultat

Tout est sur la branche locale **`nuit/integration-2026-10-01`** (non poussée), qui part de `main` (`2269793`) : 11 commits, 84 fichiers, +8 563 / −360. Chaque story a aussi sa propre branche.

| Travail | Branche | Commit | Statut de la spec |
|---|---|---|---|
| Story 1e : la garde confisque le proxy du poste | `feat/1e-garde-proxy-local` | `d0da643` | `done`, sauf la vérification manuelle sur le PC pro |
| Restes S1 : tests backend manquants, garde élargie (`gethostbyname`, `sendto`, `sendmsg`) | `feat/restes-s1-tests-garde` | `5e2ad1e` | `done` |
| Restes S2 : flux coupé, Ollama trop ancien, appels parallèles, écart à l'instantané MCP, sous-agent, `back_text` | `feat/restes-s2-robustesse` | `c95b5fb` | `done` |
| Restes S3 : décisions D1 à D19 (sauf D16) | `feat/restes-s3-decisions` | `cd06e93` | `done` |
| Restes S4 : préremplissage du premier tour, documentation lazy dans l'historique (D16) | `feat/restes-s4-latence` | `39bba19` | `done`, mesure PC en story 7 |
| Restes S5 : E2E des options, cartes et interrupteurs | `feat/restes-s5-e2e-atelier` | `f36cc98` | `done` |
| Restes S6 : E2E du schéma, du rail, des volets, de la comparaison, des cas d'erreur ; `gemini_shape` stabilisé | `feat/restes-s6-e2e-schema` | `36304ff`, `8ca7b3e` | `done` |
| V2 S6 : banc du test préalable des modèles de décision | `feat/v2-s6-banc-decision` | `bdd8a6d` | `in-review` : attend le relevé sur le PC cible |
| Pluriel des comptes de « LLM nu » (`deferred-work.md`) | `fix/llm-lab-pluriel` | `a93e026` | entrée fermée |
| Libellés et résumés du journal pour huit types d'événements (constat de S6) | `fix/journal-libelles` | `836cd98` | entrées fermées |

Chaque story est passée par `bmad-build` : spec, implémentation, revue en trois couches (Blind Hunter, Edge Case Hunter, Verification Gap), puis correctifs. Les triages sont dans le Review Triage Log de chaque spec.

## Batterie finale (sur `836cd98`)

- `ruff check` et `ruff format --check` : propres (203 fichiers).
- pytest en quatre quarts : 3 629 + 706 + 336 (3 sautés) + 387 passés, **aucun échec**.
- E2E complet en dix tranches `--only` (faux modèle, réseau coupé) : **1 048 vérifications réussies, 0 échec, 0 anomalie connue**.
- Passe dans Google Chrome 154 (Playwright, canal `chrome`, sans fenêtre) : 9 scénarios (programme, outils natifs, thèmes, RAG, reranking, atelier RAG, atelier MCP, langue de l'interface, LLM nu), puis captures de chaque page. **228 vérifications réussies, 0 échec**. Les seules erreurs de console viennent du réseau coupé et d'un 409 provoqué exprès.
- Story 1e, en plus : la suite complète a aussi tourné avec `HTTPS_PROXY=http://127.0.0.1:9000`, avec les mêmes résultats. Les nouveaux tests « hors fabrique » et « SDK MCP sous Proactor » échouent bien sur l'ancien code.

L'extension Claude in Chrome n'était pas reliée à la session : Chrome a été piloté par Playwright.

## Choix faits en mode nuit, à confirmer

Chaque spec les consigne dans son Spec Change Log, sous la mention « validé en mode nuit ».

**Confirmés par Anaël le 2026-10-02, tels quels :** D3, D5, D7, D16, S2 et 1e (entrée datée dans chaque Spec Change Log, « confirmé par Anaël » dans `deferred-work.md`). Les seuils de V2 S6 se valident sur le relevé du banc.

- **D3** : la liste d'options se déplie quand « Afficher les actions forcées » passe à vrai, mais pas au rechargement ni après « Réinitialiser ».
- **D5** : « Outils consultés » ne cite que les outils terminés `ok` (natifs, MCP, délégation), sans les outils du harnais. Un outil appelé deux fois apparaît deux fois.
- **D7** : date et heure courtes.
- **D16** : la ligne d'un outil chargé reste dans le catalogue de `load_tool_doc`. L'appel MCP forcé en lazy loading ne définit l'outil qu'en mode chat.
- **S2, E119** : quand Ollama est trop ancien, rien ne se voit au chargement. Le retour au modèle précédent se fait donc après le tour. Valeurs retenues : 3 essais avant « connexion perdue », seuil d'écart MCP de 0,2.
- **V2 S6** : seuils de latence (médiane ≤ 1 000 ms, maximum ≤ 3 000 ms) et critères bloquants, à valider sur le relevé.
- **1e** : `tools/bench/story12_bench.py` remet le proxy dans l'environnement du banc, qui télécharge hors fabrique.

## Incident

Pendant une vérification de mutation de la story S1, la première version d'un test a envoyé une requête DNS pour `example.org` et un datagramme UDP vers `203.0.113.5`, une adresse de documentation non routée. Le test a été corrigé aussitôt : un hook arrête l'appel même sous régression. Rien d'autre n'est sorti.

## Reste à faire par Anaël

**Mise à jour du 2026-10-03** : la story 7 des restes est `done` (`resultats-restes-pc-2026-10.md`) : plan Mistral activé par Anaël, E040, E048, E049, E055, E057 vus avec Mistral ; correctifs « Arrêter » pendant un chargement Ollama, fermeture avec une page ouverte, renvoi du raisonnement de Mistral (sans lui, il bouclait sur un outil) et échange passé sans texte. Décisions d'Anaël données (E062, E073, délai de grâce, seuils de V2 S6). Relevé du banc V2 S6 fait. Restent : bmad-spec sur `decision-model-candidates.md` (V2 S6), puis la mise à jour de la PR #19 (rien n'est poussé).

- **Story 1e sur le PC pro**, avec `uv run wavestack` :
  - le diagnostic affiche « Accès réseau disponible » ;
  - Wikipédia et le calendrier répondent ;
  - data.gouv.fr se connecte en MCP ;
  - le test de clé cloud répond ;
  - un téléchargement Hugging Face démarre ;
  - un second lancement affiche « déjà lancée ».
- **Story 7 des restes** (recette PC avec Groq, Mistral, Ollama et téléchargements). Il faut y ajouter :
  - les mesures de S4 (`prompt_ms` du premier tour de `mcp_lazy` et `subagent`) ;
  - le test `fits` en mode GGUF (D18) ;
  - le premier passage du test `model` de `LlamaCppEngine.complete` (E008).
- **V2 S6** : lancer les commandes du rapport `rapport-test-prealable-modeles-de-decision.md`, puis bmad-spec pour mettre à jour `decision-model-candidates.md`.
- **Relecture, puis une PR** de `nuit/integration-2026-10-01` vers `main`. Une seule PR évite le piège des PR empilées.

## Nouvelles entrées de `deferred-work.md`

- **1e** : le test de session sans proxy ne prouve rien sur un poste sans proxy.
- **S1** : `gethostbyaddr` et `getnameinfo` ne sont pas filtrés ; la requête DNS d'un nom passé à `connect` ou `sendto` part avant le refus.
- **S2** :
  - le retour au modèle précédent peut échouer lui-même ;
  - l'avertissement `.brick-drift` n'a pas de contrôle E2E ;
  - les pages annexes n'ont pas d'indicateur de connexion perdue.
- **S3** : D18 n'est cumulé qu'en mode GGUF.
- **S5** : une part du rendu H5 de la story 8c n'a pas de contrôle E2E.
- **S6** : les résumés du journal ne s'exécutent que pour les événements de `native_tools`.
