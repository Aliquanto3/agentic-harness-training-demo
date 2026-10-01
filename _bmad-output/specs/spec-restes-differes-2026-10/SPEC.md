---
id: SPEC-restes-differes-2026-10
companions:
  - triage.md
  - ../spec-langues/i18n-conventions.md
  - ../../planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
sources:
  - ../../implementation-artifacts/deferred-work.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Restes différés (octobre 2026) : tests, robustesse, latence, recette

## Why

`deferred-work.md` comptait 97 entrées ouvertes au 2026-10-01. Le triage (`triage.md`) en a fermé 37 : 36 déjà résolues par des lots ou des stories postérieurs, 1 devenue obsolète. Il en reste 40 petites et sans décision (B), 19 qui attendent une décision d'Anaël (C), et 1 laissée à un autre agent (mots vides BM25 de l'atelier RAG). Il s'agit de solder une dette, pas d'ajouter des fonctionnalités : des comportements livrés que rien ne protège contre une régression, quelques défauts de robustesse, la latence du premier tour sur CPU, et des vérifications qui ne se font que sur le PC cible avec de vrais fournisseurs.

## Capabilities

- **CAP-1** Tests backend manquants (story 1)
  - **intent:** Une régression sur la garde réseau, le registre des briques, H2, H5 ou la disponibilité du raisonnement fait échouer un test.
  - **success:** Chaque mutation nommée dans les entrées E008, E013, E022, E025, E027, E056 et E066 (retirer `capabilities=["tool_call_parser"]` d'une vraie brique, avancer le curseur de H2 sur échec, retirer le `replace` des arguments modifiés avant H5…) fait échouer au moins un test ; la garde refuse `gethostbyname`, `gethostbyname_ex` et `sendto` hors liste.
- **CAP-2** Robustesse des connexions (story 2)
  - **intent:** Le formateur voit une connexion perdue, une erreur de serveur local expliquée, des appels d'outils parallèles distincts et un écart entre un serveur MCP public et son instantané.
  - **success:** Flux coupé : indicateur « connexion perdue » dans la barre haute, effacé au retour ; Ollama qui répond 500 sur `qwen35` : raison en `fr`/`en`/`de` et modèle précédent rétabli ; deux appels au même `index` et d'`id` différents restent deux appels ; `tools/list` au-delà du seuil `[mcp]` : avertissement ; `back_text` n'existe plus ; vérifié par pytest.
- **CAP-3** Décisions d'Anaël appliquées (story 3)
  - **intent:** Chaque décision prise sur D1 à D19 (sauf D16) est appliquée ou l'entrée correspondante fermée avec la décision.
  - **success:** Pour chaque Dn tranché, `deferred-work.md` porte la décision ; les « oui » ont leur test ou contrôle E2E ; aucune entrée C ne reste sans `closed:` ou `resolution:`.
- **CAP-4** Premier tour moins lent sur CPU (story 4)
  - **intent:** Le premier tour d'un scénario chargé ne relit pas un contexte que le harnais pouvait évaluer pendant la lecture de la consigne, et charger une documentation en lazy loading ne force plus la relecture du contexte (D16 = oui).
  - **success:** Avec le faux moteur, le premier appel du premier tour d'un scénario réutilise les tokens préremplis (`evaluated_tokens` réduit d'autant, aucun `prefix_not_reused`) ; aucun `prefix_not_reused{cause: system}` après `load_tool_doc` ; sur PC, `prompt_ms` du premier tour de `mcp_lazy` et de `subagent` mesuré avant et après.
- **CAP-5** Front de l'atelier sous E2E (stories 5 et 6)
  - **intent:** Les interrupteurs, cartes, schéma, rail, volets et cas d'erreur listés par les entrées B « aucun test front » sont vérifiés par le parcours E2E.
  - **success:** Chaque comportement listé dans les stories 5 et 6 a un contrôle E2E nommé, qui échoue si on retire la ligne de `app.js` qui le produit ; `gemini_shape` passe cinq fois de suite dans sa tranche.
- **CAP-6** Recette PC des restes (story 7)
  - **intent:** Les comportements qui ne se jugent qu'avec Groq, Mistral, Ollama ou un téléchargement réel sont constatés sur le PC cible, et le code suit le constat.
  - **success:** Un fichier `resultats-restes-pc-2026-10.md` consigne chaque mesure de la story 7 (geste, attendu, observé, verdict) ; chaque entrée concernée est fermée ou rouverte avec un constat chiffré ; les préréglages `resend` suivent ce que Mistral accepte.

## Constraints

- **PC de 16 Go, CPU** : une seule suite à la fois (pytest en quarts l'un après l'autre, E2E par tranches `--only` de 4 à 6 scénarios), aucun modèle local chargé pendant pytest ; serveur, E2E et modèles réels seulement avec l'accord d'Anaël et jamais pendant ses tests manuels.
- **Front vérifié par l'E2E seulement** : pas de banc de test JS (décision de `spec-corrections-2026-09-30`) ; un contrôle E2E peut appeler une fonction globale d'`app.js` par `page.evaluate`.
- **Langues** : tout texte nouveau en `fr`, `en`, `de` (`ui.yaml` + `t()`, `messages.yaml` + `msg()`, ou `content/` avec surcouche), selon `i18n-conventions.md`.
- **Aucune dépendance nouvelle**, `uv` pour tout, rien qui demande des droits d'administrateur.
- **Une entrée n'est fermée qu'avec sa preuve** (`closed: <date> (<story>) — <fichier:ligne, test ou mesure>`), sans réécrire son texte.
- **Les entrées C ne s'implémentent qu'après la décision d'Anaël** : les stories 3 et 4 ne traitent un point conditionnel que si sa décision est consignée dans ce SPEC.
- **Entrées laissées à l'autre agent** : BM25 de l'atelier RAG (E132), `session.compression.the_compressor` en allemand, blocs `deferred` des stories 5 et 6 de `spec-corrections-2026-09-30`.

## Non-goals

- Un banc de test JS (`node:test`, `node:vm`) : les pistes des entrées sont remplacées par des contrôles E2E.
- Les entrées que le triage recommande de fermer sans suite (D1, D2, D8, D10, D12, D13, D14) : rien à construire, Anaël a suivi la recommandation le 2026-10-01.
- Changer de version de llama-cpp-python, ou un analyseur d'appels d'outils pour Llama.
- Un budget de raisonnement adaptatif à la longueur du message (D17 recommande une consigne).

## Success signal

- `deferred-work.md` n'a plus d'entrée ouverte hors BM25, hormis les vérifications de la story 7 qu'Anaël n'a pas encore pu jouer ; `ruff`, `pytest` (quarts) et l'E2E complet (tranches) passent sur `main`.

## Décisions à prendre par Anaël

Chaque décision ferme une entrée C (`triage.md`). « Fermer » = noter la décision dans l'entrée, sans code.

**Tranchées le 2026-10-01 : Anaël suit les dix-neuf recommandations, D16 = oui compris.** La colonne « Décision » fait foi pour les stories 3 et 4.

| D | Entrée | Question | Décision (recommandation suivie le 2026-10-01) |
|---|---|---|---|
| D1 | E007 | Ajouter la grille détaillée de la jauge (`context-gauge-detail`) dans Contexte LLM ? | **Non**, fermer : la jauge empilée et son survol suffisent (décision du 24/09, reconduite par la story 32). |
| D2 | E010 | Repli hors ligne de `fetch_page` (fichier long de `demo_files/`, « contenu de remplacement ») ? | **Non**, fermer : aucun scénario ne s'en sert ; l'échec expliqué est lui-même pédagogique. |
| D3 | E038 | Rendre les actions forcées plus visibles ? | **Oui** (S3) : quand « Afficher les actions forcées » s'active, déplier la liste d'options de chaque brique qui a un bouton « Forcer » ; titre de section et icône ✋ sur l'interrupteur pour le distinguer des interrupteurs de briques. |
| D4 | E045 | `mcp_full` : 109 à 128 s par tour sur le PC cible. Que faire ? | **Prévenir** (S3) : la consigne du scénario annonce un tour d'environ deux minutes et dit pourquoi (documentation complète = long contexte) ; c'est la leçon du scénario. Ne pas retirer la mémoire de démonstration. |
| D5 | E051 | Montrer qu'une réponse s'appuie sur un résultat d'outil ? | **Oui, côté interface** (S3) : sous la réponse, « Outils consultés pendant ce tour : … » (noms, liés à leurs étapes) ; pas de consigne « cite tes sources », que le 2B suit mal. |
| D6 | E052 | Lever l'interdiction de lire `x-ratelimit-*` (spec 11b) pour expliquer un 429 sans quota ? | **Oui, pour le message seul** (S3) : `x-ratelimit-limit-req-minute: 0` → « aucun quota actif sur ce compte : vérifiez le plan dans la console du fournisseur » ; ni attente ni nouvel essai. |
| D7 | E060 | Afficher la date d'écriture des entrées de mémoire globale ? | **Oui** (S3) : date courte, fuseau du poste, dans la langue de la session. |
| D8 | E061 | Ajouter une entrée de mémoire depuis le tiroir ? | **Non**, fermer : l'action forcée « Écrire en mémoire » montre mieux le mécanisme. |
| D9 | E062 | Abaisser `MAX_CHARS` (300) de la mémoire globale ? | **Garder 300** ; S7 mesure `mcp_full` mémoire pleine ; abaisser à 200 seulement s'il déborde. |
| D10 | E079 | Faire de `transform_context` un point d'accroche de hook ? | **Non**, fermer : aucun hook de démonstration n'en a besoin. |
| D11 | E080 | Valider H-1 (compression avant chaque appel qui lit le texte) ? | **Valider** (S3) : retirer « à valider » d'AD-4 dans ARCHITECTURE-SPINE ; c'est le comportement livré et testé. |
| D12 | E081 | Borner le temps de `compress()` de Headroom ? | **Non**, fermer : 2,2 s au pire mesuré, annulation impossible proprement. |
| D13 | E087 | SOC : passer le garde-fou de H1 (blocage) à H5 (validation humaine) ? | **Garder H1**, fermer : H5 reste réservé au réseau (FR-27) ; la leçon passe par la consigne. |
| D14 | E088 | Repli hors ligne enregistré pour IAM et Souveraineté ? | **Non**, fermer : le README demande d'ouvrir les deux hôtes ; un faux serveur embarqué coûte cher. |
| D15 | E093 | Valider AD-21 amendé (sans reranker, seule la sous-option est indisponible) ? | **Valider** (S3) : c'est le code livré ; retirer « à valider » de l'architecture. |
| D16 | E121 | Lazy loading : placer la documentation chargée en résultat d'outil (historique) plutôt que dans `tools` ? | **Oui** (S4) : évite ≈ 40 s de relecture par documentation chargée sur Qwen3.5 ; Contexte LLM et la jauge le montrent comme un résultat d'outil, ce qui reste juste pédagogiquement. Validation par Anaël car cela change AD-25 et ce que le modèle voit. |
| D17 | E124 | Raisonnement qui va jusqu'au budget même sur « Bonjour » ? | **Consigne** (S3) : la consigne du scénario Raisonnement l'annonce (un petit modèle réfléchit même pour rien) ; pas de budget adaptatif. |
| D18 | E126 | Test `fits` : `subagent` p4 déborde de 9 tokens avec des réponses « au pire ». | **Réponses mesurées** (S3) : le test simule des réponses de la taille relevée au lot K (≈ 500 tokens au plus), quiz inchangés. |
| D19 | E139 | `hosting_text` et `notes_text` de `[[cloud.models]]` restent en français en `en`/`de`. | **Accepter et documenter** (S3) : texte saisi par l'opérateur dans `wavestack.toml`, affiché tel quel ; commentaire dans `wavestack.toml` et README. |

## Assumptions

- Si Mistral accepte `resend = true` (S7), le format de renvoi est figé au début du tour et le raisonnement passé ne repart que si la brique Raisonnement est effective pour ce tour (une brique éteinte ne contribue rien, AD-12).
- Le préremplissage (S4) n'a lieu qu'en mode local, moteur libre, et cède la place à tout tour, chargement ou réglage ; il ne change pas la jauge ni le contexte envoyé.
- Le fichier de résultats de S7 s'appelle `_bmad-output/implementation-artifacts/resultats-restes-pc-2026-10.md`.
