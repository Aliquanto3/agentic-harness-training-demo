---
title: 'Recette PC des restes : fournisseurs cloud, Ollama, téléchargements'
type: 'chore'
created: '2026-10-01'
status: 'in-review'
baseline_commit: 'bccf10b0544a52cbfaadd72c9008bfb37cc42a08'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/implementation-artifacts/guide-test-pc-palier-2.md'
warnings: []
deferred: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dix entrées ne se tranchent qu'avec de vrais fournisseurs (Groq, Mistral), un vrai Ollama, un vrai téléchargement ou un vrai SLM sur le PC cible ; les doublures ne disent rien du format réel (CAP-6).

**Approach:** Jouer chaque vérification sur le PC cible, consigner geste, attendu, observé et verdict dans `_bmad-output/implementation-artifacts/resultats-restes-pc-2026-10.md`, puis appliquer le petit correctif qui suit du constat et fermer l'entrée.

## Boundaries & Constraints

**Always:**
- Préalable : accord et présence d'Anaël (clés Groq et Mistral, Ollama lancé, réseau ouvert, Edge, Outlook et Teams fermés, aucun autre test en cours).
- Vérifications et suites :
  - **E040** — scénario « Lazy loading », prompt 1 : avec Groq puis Mistral, puis avec le 2B et H3 décoché. Si un modèle cloud appelle `local__define_term`, l'entrée se ferme (limite du SLM, déjà dite par la consigne de la story 27).
  - **E048** — deux outils en un tour (`get_datetime` et `calculator`) avec Groq puis Mistral : `model_call_ended.tool_calls` porte deux appels (après la story 2).
  - **E049** — tour terminé sans texte (raisonnement seul) avec Mistral, puis second message : si 400, omettre le `content` vide de l'échange dans le corps chat (`AppSession._messages`), avec test.
  - **E054**, **E055** — `resend = true` dans `settings.json` (format `field`, puis Mistral), tour avec outil puis second tour : accepté → préréglage Mistral passé à vrai dans `wavestack.toml` ; 400 → AD-20 amendé et clé de renvoi corrigée (`reasoning` ou `reasoning_content`).
  - **E057** — si un préréglage passe `resend = true` : format figé au début du tour dans le `TurnState`, raisonnement passé renvoyé seulement si la brique Raisonnement est effective (hypothèse de `SPEC.md`), avec test ; sinon l'entrée se ferme avec E055.
  - **E062** (D9) — mémoire globale pleine (20 entrées de 300 caractères) puis `mcp_full` : jauge avant envoi ; déborde → abaisser `MAX_CHARS` à 200 (spec de la story 14 amendée) ; tient → fermer.
  - **E073** — « Arrêter » un téléchargement de modèle pendant l'établissement de la connexion : délai mesuré (≤ 10 s attendu) ; gênant selon Anaël → noter, sinon fermer.
  - **E077** — `ollama ps` vide après un changement de modèle et après la fermeture de WaveStack, pour un modèle que WaveStack a fait charger ; un modèle chargé par un autre programme y reste.
  - **E078** — « Arrêter » et fermeture de WaveStack pendant un chargement Ollama réel : main rendue en moins d'une seconde.
  - Mesures de la story 4 : `prompt_ms` du premier tour de `mcp_lazy` et `subagent`, et du tour qui suit un `load_tool_doc`, avant et après.
  - **Ajouts d'Anaël (2026-10-02, rapport de la nuit)** : **D18** — test `fits` en mode GGUF exact (`WAVESTACK_TEST_GGUF` = le 2B) : chaque prompt tient avec l'historique cumulé, sinon l'entrée reste ouverte avec le prompt et l'écart ; **E008** — premier passage de la variante `gguf` (marqueur `model`) de `tests/test_llama_engine.py` sur un vrai GGUF.
- Chaque entrée fermée cite la ligne du fichier de résultats ; une entrée qui échoue reste ouverte avec le constat chiffré.

**Never:**
- Lancer un serveur, un modèle ou l'E2E sans l'accord d'Anaël, ou pendant ses tests manuels.
- Écrire une clé d'API dans un fichier versionné.
- Corriger au-delà de ce que le constat impose : un défaut plus large devient une entrée de `deferred-work.md`.

</frozen-after-approval>

## Code Map

- `_bmad-output/implementation-artifacts/deferred-work.md` -- entrées sans identifiant écrit : E*nnn* = rang de l'entrée dans le fichier. E040 l.195, E048 l.234 (fermée sur doublure, « réel en story 7 »), E049 l.239, E054 l.263, E055 l.267, E057 l.276, E062 l.300 (résolution D9 l.303), E073 l.355, E077 l.373, E078 l.377, E008 l.36 (fermée, variante GGUF jamais jouée), D18 l.719. Fermeture : ligne `closed: 2026-10-02 (story 7 des restes) — resultats-restes-pc-2026-10.md:<ligne>`, sans réécrire le texte.
- `tests/test_program.py:604` `test_every_scenario_fits_the_default_window_with_every_prompt` -- non marqué `model` ; mode GGUF exact quand `WAVESTACK_TEST_GGUF` désigne un fichier (`_gguf_tokenizer`, l.529).
- `tests/test_llama_engine.py` -- fixture `subject` (l.99), paramètre `gguf` marqué `model` (`pyproject.toml:75-79`, `addopts = "-m 'not model'"`) ; `-m model` en ligne de commande le sélectionne.
- `src/wavestack/trace/catalog.py:410` `ModelCallEndedPayload` -- `prompt_ms`, `prompt_tokens`, `tool_calls`, `stop_reason`, `usage_source` ; produit en local (`app_session.py:7630`) et en cloud (`openai_chat.py:891`).
- `wavestack.toml` -- Groq l.273-285 (`reasoning.format = "field"`, `resend = false`), Mistral l.299-310 (`format = "content_blocks"`, `resend` absent = faux, `config.py:145`). Surcharge : `settings.json` → `cloud.models[id="mistral"].reasoning.resend`, fusion par `id` (`_merge_cloud_models`, `config.py:384`) ; bloc PowerShell prêt dans `guide-test-pc-palier-2.md:1007-1022`.
- `src/wavestack/session/app_session.py` -- `_resend` (l.3633, lu à chaque rendu : objet d'E057), `_assistant_message` (l.3838 : `omit_empty`, formes `content_blocks` / `think_tags` / `field`), `_messages` (l.3934).
- `src/wavestack/memory.py:27-28` -- `MAX_ENTRIES = 20`, `MAX_CHARS = 300` (E062).
- `src/wavestack/web/app.py` -- API : tout POST exige `Origin: http://127.0.0.1:<port>` et `Content-Type: application/json`. `GET /api/state`, `GET /api/diagnostic` (`candidates`, `ref` Ollama = `ollama/<nom:tag>`), `POST /api/intentions/{select_model {kind,ref,acknowledged}, scenario {scenario_id}, brick {brick,wanted}, hook {hook:"h3",enabled}, send {message}, stop, clear_conversation, download_model {target:"rag_embedding"}}` ; flux `GET /api/stream` (SSE, enveloppe `seq, kind, context_id, payload`). Événements utiles : `session_state`, `model_load_ended`, `model_call_ended`, `turn_ended`, `harness_error.http_status`, `outbound_response.status`, `tool_ended`.
- `tools/e2e/run_e2e.py` -- `class Events` (l.63-107) et `Run.api` (l.166) : modèle du lecteur SSE et des POST pour le script jetable ; `launch` (l.206) : attendre `scenario_changed` puis chaque `mcp_connect_ended`.
- Téléchargement (E073) : seuls les modèles RAG se téléchargent (`download_model`, brique `rag` active) ; ils sont déjà présents dans le dossier d'Anaël, donc second serveur sur `--port 8421` avec `WAVESTACK_DATA_DIR` jetable (méthode de la vérification 4 du 02/10).
- `%LOCALAPPDATA%\WaveStack\settings.json` et `memory.json` -- sauvegardés avant la recette (bloc-notes de la session) et restaurés à la fin : langue `en`, modèle cloud `gemma`.

## Tasks & Acceptance

**Execution:**
- [x] pytest à modèle réel (sans serveur) -- D18 avec le 2B, E008 avec le 2B -- constats chiffrés.
- [x] Serveur `uv run wavestack` sur 8420 (processus vérifié sur le port), piloté par l'API HTTP et le flux SSE (script jetable dans le bloc-notes, rien de versionné) -- E040, E048, E049, E054, E055, E062, mesures S4.
- [x] Ollama réel -- E077, E078 (`ollama ps` avant, pendant, après ; temps de rendu de la main mesuré).
- [x] Téléchargement réel -- E073 (« Arrêter » pendant la connexion, délai mesuré).
- [x] `_bmad-output/implementation-artifacts/resultats-restes-pc-2026-10.md` -- une ligne par vérification : geste, attendu, observé, verdict.
- [x] Correctifs conditionnels, seulement si le constat l'impose : `app_session.py` + test (E049 ; E057 si `resend` passe à vrai), `wavestack.toml` (E055), `memory.py` + spec story 14 (E062), AD-20 dans `ARCHITECTURE-SPINE.md` (E054/E055 refusés).
- [x] `deferred-work.md` -- chaque entrée fermée avec sa ligne de résultats, ou complétée d'un constat chiffré.

**Acceptance Criteria:**
- Given la recette terminée, when on lit `resultats-restes-pc-2026-10.md`, then chaque vérification du bloc gelé a geste, attendu, observé et verdict, avec le poste et la date.
- Given un constat qui impose un correctif, when le correctif est commité, then un test le couvre et `uv run pytest` sur les fichiers touchés passe.
- Given la fin de la recette, when on relit `settings.json` et `memory.json`, then ils sont revenus à leur état d'avant (langue `en`, modèle `gemma`), et aucun serveur ni modèle Ollama lancé par la recette ne reste en mémoire.

## Implementation Notes

- Recette jouée directement par l'agent qui a planifié, sans sous-agent d'implémentation : un seul processus lourd à la fois sur 16 Go (serveur, modèle local, Ollama), des constats à juger au fil de l'eau, et les réglages d'Anaël à restaurer.
- Pilotage par un script jetable du bloc-notes (`drive.py` : lecteur SSE, POST avec `Origin`), rien de versionné. Langue `fr` le temps de la recette ; `settings.json` et `memory.json` sauvegardés puis restaurés (langue `en`, modèle cloud `gemma`, 3 entrées de démonstration) ; Ollama vide, aucun serveur à l'écoute à la fin.
- **Bloqué** : le compte Mistral n'a aucun plan actif (`x-ratelimit-limit-req-minute: 0`, clé valide) ; E040 et E048 côté Mistral, E049, E055 et E057 restent ouvertes avec ce constat. Aucun correctif conditionnel de `app_session.py`, `wavestack.toml` ou AD-20 n'est donc déclenché.
- **E054 fermée sans correctif** : Groq accepte `reasoning` au format `field` ; le préréglage Groq garde `resend = false` (le bloc gelé ne fait passer à vrai que Mistral, E055).
- **E062** : déborde (127 %), mais le correctif prévu (`MAX_CHARS` à 200) ne réglerait pas le débordement (≈ 113 %) : non appliqué, question posée à Anaël, entrée laissée ouverte avec la mesure.
- **Deux défauts trouvés et corrigés (le constat l'imposait)** :
  - E078 : `src/wavestack/models/servers.py`, `_stream` démarre sa veille avant la requête et coupe la socket connue dès `connection.connect_tcp.complete` (extension `trace`) ; `_shut` ferme aussi la socket (sous Windows, `shutdown` seul ne réveille pas le `recv` : 10 s mesurées contre 0,3 s) ; `_client` envoie `Connection: close` ; `_stream` rend `None` quand l'appel est arrêté avant toute réponse, `_lines(None)` ne rend rien. Test `test_stop_unblocks_a_server_silent_before_its_headers`, rouge sur l'ancien code.
  - E077 : `src/wavestack/cli.py`, `SHUTDOWN_GRACE_S = 2.0` passé à `uvicorn.run(timeout_graceful_shutdown=…)` ; sans lui, une page ouverte bloque Ctrl+C indéfiniment, et le second Ctrl+C saute le `lifespan` (modèle Ollama laissé chargé). Tests `test_main_gives_uvicorn_the_shutdown_grace`, `test_shutdown_with_an_open_stream_ends_and_runs_the_lifespan`.
- Questions laissées à Anaël (fichier de résultats, « Décisions ») : plan Mistral, E062, E073 (10 s gênantes ?), délai de grâce (2 s ou 0,5 s).

## Spec Change Log

- 2026-10-02 -- plan (bmad-build step-02) : bloc d'intention repris tel quel, sous la balise `frozen-after-approval` ; seuls ajouts, les vérifications D18 et E008 demandées par Anaël (rapport de la nuit, invocation du 02/10). Approbation : Anaël a répondu « Lance tout maintenant » à la question de lancement de la recette (02/10), avec consigne de ne pas l'attendre ; tenu pour « Approve and continue ».
- 2026-10-03 -- fin du workflow (step-05) : le statut reste `in-review` au lieu de `done`, comme V2 S6 la nuit du 01/10 : les vérifications Mistral (E040, E048 côté Mistral, E049, E055, E057) sont bloquées par le compte sans quota, et quatre décisions attendent Anaël (plan Mistral, E062, E073, délai de grâce). Revue faite, patchs appliqués (journal de triage).

## Review Triage Log

Revue du 2026-10-03 (Blind Hunter, Edge Case Hunter, Verification Gap) sur le diff depuis `bccf10b`.

| # | Couche | Constat | Verdict | Preuve et suite |
|---|---|---|---|---|
| 1 | aveugle, cas limites, écarts | E078 marquée `closed` alors que la fermeture prend 2,89 s (cible : moins d'une seconde) | medium | Réel : contraire à « une entrée qui échoue reste ouverte » ; patch : `recette:` à la place, entrée laissée ouverte pour la fermeture. |
| 2 | aveugle, cas limites | E048 reste `closed` (doublure) sans appel parallèle réel observé | low | Réel : la ligne `closed:` vient de la story 2, le texte ne se réécrit pas ; patch : nouvelle entrée de `deferred-work.md` (appel parallèle réel jamais vu). |
| 3 | aveugle | Option (c) d'E062 fausse (8 entrées ne tiennent pas) | medium | Réel : 3 049 + 8 × 75 = 3 649 > 3 584 ; patch : 7 entrées, sans marge. |
| 4 | aveugle | Option (a) d'E062 : « 17 entrées » au lieu de ≈ 5 | medium | Réel : 380 tokens de marge / ≈ 75 par entrée ; patch du texte de la décision. |
| 5 | aveugle | Décision 4 : 0,5 s ne tient pas la seconde | medium | Réel : 0,55 à 0,9 s hors délai (R16, R18) ; patch : options reformulées, 2 s recommandées. |
| 6 | cas limites | Le correctif prescrit d'E062 (`MAX_CHARS` 200) n'est pas appliqué | intent_gap | Le bloc gelé prescrit 200, la mesure montre que 200 ne règle pas le débordement : décision d'Anaël (question 2 du fichier de résultats) ; aucun code à défaire. |
| 7 | aveugle | Défauts vus pendant la recette non consignés (`subagent` en `limit`, diagnostic de 10 min sur dossier vide, second Ctrl+C) | low | Réels ; defer : trois entrées de `deferred-work.md`. `BROWSER` et ses antislashs : comportement de `webbrowser` (bibliothèque standard), pas de WaveStack : rejeté. |
| 8 | aveugle | Fermeture de la fenêtre de console non testée | maybe-false | Non mesuré ; si vrai, medium (modèle Ollama laissé chargé jusqu'au `keep_alive`) ; defer, dans l'entrée du second Ctrl+C. |
| 9 | aveugle | Critères 2 et 3 sans preuve écrite (pytest, ruff, restauration, ports) | low | Réel : faits mais non consignés ; patch : section « Vérification » du fichier de résultats. |
| 10 | aveugle | Liste de tâches qui ne nomme pas les correctifs livrés | false | Le correctif serait d'éditer la spec de cette story (rejeté par règle) ; les Implementation Notes nomment `servers.py` et `cli.py`. |
| 11 | aveugle | Numéros de ligne de la Code Map périmés, citations fragiles | low | Code Map : édition de la spec, rejeté par règle ; citations : patch, l'identifiant R*n* suit chaque numéro de ligne dans `deferred-work.md`. |
| 12 | aveugle, écarts, cas limites | Annulation pendant la connexion TCP : docstring trop large, aucun test | low | Réel, fenêtre de quelques millisecondes sur la boucle locale ; patch de la docstring ; tests : defer (une entrée avec les deux autres chemins non testés). |
| 13 | aveugle, cas limites | `_shut` ferme la socket depuis un autre fil (réutilisation de handle) | false | httpcore tient le même objet `socket` Python (`get_extra_info("socket")`) : après `close()`, son `fileno` vaut -1 et sa propre fermeture ne fait rien ; le `recv` bloqué rend une erreur, avalée car annulé. Docstring complétée. |
| 14 | aveugle, cas limites | `Connection: close` sur tout le client (`_json`, `/detokenize`) | low | Réel mais négligeable : quelques appels `_json` par tour sur la boucle locale ; `/detokenize` seulement pour les ids que `/tokenize` n'a pas vus. Le borner aux générations demande un second client (complexité). Rejeté. |
| 15 | cas limites | Annulation pendant la lecture d'un corps d'erreur ≥ 400 : `ServerError` au lieu de `cancelled` | false | Le serveur a déjà répondu en erreur : le tour rapporte cette erreur, comme avant le correctif (la veille ne démarrait qu'après ce contrôle). |
| 16 | cas limites | Test uvicorn : `IndexError` si le serveur ne démarre pas | low | Patch : `assert server.started`. |
| 17 | aveugle | Le test d'arrêt gracieux n'utilise pas l'application WaveStack | low | Réel ; la recette R16 l'a mesuré sur le vrai serveur (modèle Ollama déchargé) et le test de câblage vérifie `main`. Rejeté (un test avec `create_app` demande sessions et diagnostic). |
| 18 | aveugle | Commentaires mêlant du français (« restes », « 7,6 s ») | low | Patch : « deferred leftovers », « 7.6 s » ; « Arrêter » reste, comme ailleurs dans le code (libellé de l'interface). |
| 19 | aveugle | `decision10.json` (banc V2 S6) dans le diff | low | Fichier du banc, non suivi ; commité à part avec le relevé V2 S6. |
| 20 | écarts | `close()` de `_shut` protégé seulement sous Windows | low | Réel mais sans effet : la suite tourne sur le PC Windows, aucune CI Linux. Rejeté. |

## Design Notes

Le pilotage passe par l'API plutôt que par Chrome : l'écran du PC pro fait 1 280 × 672 et la fenêtre en arrière-plan rend les clics muets (mémoire de la recette du 02/10). Les jugements d'interface qui restent (E073 « gênant ») sont signalés à Anaël dans le fichier de résultats.

## Verification

**Commands:**
- `$env:WAVESTACK_TEST_GGUF="$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf"; uv run pytest -s tests/test_program.py -k fits` -- expected: passe en mode GGUF exact.
- `uv run pytest -m model tests/test_llama_engine.py -v` (même variable) -- expected: les cas `gguf` passent.
- `uv run pytest -q` sur les fichiers touchés par un correctif -- expected: tout passe ; `uv run ruff check .` propre.

**Manual checks (if no CLI):**
- `resultats-restes-pc-2026-10.md` complet ; `deferred-work.md` : chaque entrée de la story fermée ou complétée d'un constat.
