---
title: 'Lot 6, suite de la revue : le pas de l''OUTPUT lit le texte de l''INPUT'
type: 'bugfix'
created: '2026-10-05'
status: 'done'
baseline_commit: 'febd1294b370b2b28072cdcff5ae2058415d3154'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-lot-6-atelier-llm-boucle-du-modele.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le pas de l'OUTPUT (« 🎲 Tirer le token suivant », `llm_step`) fait lire au moteur le prompt rendu par le gabarit de chat (balises du message utilisateur, en-tête de la réponse de l'assistant). Or l'INPUT montre le texte brut et ses tokens, et la légende des Logits dit « les 6 plus probables après « … » » en citant la fin de ce texte. La page montre un contexte et le moteur en lit un autre (constat n° 5 de la revue du lot 6).

**Approach:** Le pas lit sans gabarit les identifiants mêmes de l'INPUT, puis les tokens ajoutés : le token tiré prolonge le texte (flux UX validé « Le chat dort sur le » → « ␣canapé »). « Générer » garde le gabarit, et une phrase de l'OUTPUT dit la différence.

**Décisions d'Anaël (2026-10-05) :**
- Option B retenue : le pas se fait sans gabarit, en prolongeant directement les tokens de l'INPUT.
- Token de début de texte (BOS) : ajouté devant quand le modèle le demande (Gemma, Llama ; pas Qwen), et nommé par une phrase de l'INPUT. Les puces et les compteurs de « Découper en tokens » ne changent pas.

## Boundaries & Constraints

**Always:** AD-1 (la page ne calcule rien, le moteur tire) ; textes dans `content/llm_lab.yaml` + `content/i18n/{en,de}/llm_lab.yaml` (parité de `tests/test_i18n.py`) ; ids et classes du lot 6 conservés ; « Générer », la comparaison et `llm_tokenize` inchangés ; `llm_distribution(0, …)` marche après un pas.

**Never:** toucher `models/catalog.py`, `models/discovery.py`, `models/servers.py`, `content/models/`, `tokens.css` ; modifier les scénarios E2E existants hors `s_llm_loop` ; changer le modèle choisi ou les réglages du dossier de données partagé ; fusionner, rebaser ou pousser.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Pas, modèle sans BOS | « Le chat dort sur le », 0 ajout | ids lus = `engine.tokenize(texte)`, aucune balise de gabarit | — |
| Pas avec ajouts | 2 ajouts | ids lus = tokenize(texte) + les 2 ids | — |
| Modèle qui demande le BOS | `adds_bos()` vrai | ids lus = [bos] + tokenize + ajouts ; `llm_tokenized.bos_token` = son texte ; phrase dans l'INPUT | — |
| Moteur sans `adds_bos` | moteur de test, serveur | pas de BOS, `bos_token = None`, pas de phrase | jamais d'échec |
| Modèle qui raisonne toujours | `reasoning_always` | le pas tire sans raisonnement | — |
| Token de fin tiré | EOG | texte de fin « le texte s'arrête là » | — |

</frozen-after-approval>

## Code Map

- `src/wavestack/session/app_session.py:8728-8826` -- `_run_lab` : nouveau paramètre `raw: bool = False`. S'il est vrai, la branche locale ne passe plus par `render_context`. Elle construit `RenderedContext(prompt=bos_text + prompt + pièces ajoutées, ids=[bos] + engine.tokenize(prompt) + continuation, segments=[Segment(kind=SegmentKind.USER_MESSAGE, …)])`, avec `reasons = False`. Le bloc `continuation` actuel (`replace(rendered, …)`) ne sert plus qu'au pas : le fondre dans la branche `raw`.
- `src/wavestack/session/app_session.py:8601-8644` -- `llm_step` : passe `raw=True` ; mettre la docstring à jour (« sans gabarit »).
- `src/wavestack/session/app_session.py:8263-8317` -- `_lab_tokenized` : ajouter `bos_token` (texte du BOS que le pas ajoute, sinon `None`) dans la branche exacte. Une seule aide `_step_bos(engine) -> int | None` sert aux deux : `getattr(engine, "adds_bos", None)` puis `llama_vocab_bos`, et le texte vient de `engine.metadata().bos_token`.
- `src/wavestack/models/engine.py:242-262` -- tokenizer en processus : ajouter `adds_bos() -> int | None` (id du BOS si `lib.llama_vocab_get_add_bos(self._vocab)`, sinon `None`). Le moteur en processus (l.~382) délègue comme pour `tokenize`.
- `src/wavestack/trace/catalog.py:1120` -- `LlmTokenizedPayload` : ajouter `bos_token: str | None = None`.
- `src/wavestack/session/llm_lab.py` -- `LabContent` (strict) : déclarer les nouvelles clés `stages.input.bos_text` et `stages.output.raw_text`.
- `content/llm_lab.yaml` (+ en, de) -- `stages.input.bos_text` : « Avant ces tokens, le moteur lit aussi {bos} : le token de début de texte que ce modèle demande. » ; `stages.output.raw_text` : « Ici, le moteur lit le texte tel quel, sans gabarit de chat : il le prolonge. « Générer » (section 4) le lit comme un message et y répond. » ; `stages.output.end_text` : « Le moteur a tiré son token de fin : pour lui, le texte s'arrête là. Rien à ajouter. »
- `src/wavestack/web/static/llm.html` -- deux éléments ajoutés : `#token-bos` (sous les compteurs de l'INPUT) et `#llm-step-raw` (dans la carte du token tiré de l'OUTPUT).
- `src/wavestack/web/static/llm.js` -- `renderInput` (l.294) remplit ou masque `#token-bos` d'après `store.tokenized.bos_token`, en marquant le BOS avec `visibleBlanks`. Le texte de `#llm-step-raw` vient du contenu. `logitsCaption` (l.1149) reste inchangé, car il devient vrai.
- `tests/test_llm_lab.py:1393-1460` -- les tests du pas. `FakeEngine` et `SpecialEngine` (l.116) servent de base à un moteur qui a `adds_bos`.
- `tools/e2e/run_e2e.py` -- `s_llm_loop` : vérifier que `#llm-step-raw` est présent, et que `#token-bos` apparaît sur un `llm_tokenized` simulé avec `bos_token`.
- `_bmad-output/planning-artifacts/ux-designs/ux-lot-6-atelier-llm-2026-10-04/notes-de-fusion.md` -- ajouter `engine.py`, `catalog.py` et le nouveau paramètre de `_run_lab`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/models/engine.py` -- `adds_bos()` sur le tokenizer et le moteur en processus.
- [x] `src/wavestack/trace/catalog.py` -- champ `bos_token` de `LlmTokenizedPayload`.
- [x] `src/wavestack/session/app_session.py` -- `_step_bos`, branche `raw` de `_run_lab`, `llm_step(raw=True)`, `bos_token` dans `_lab_tokenized`.
- [x] `src/wavestack/session/llm_lab.py` + `content/llm_lab.yaml` + en + de -- les trois textes.
- [x] `src/wavestack/web/static/llm.html`, `llm.js` -- `#token-bos`, `#llm-step-raw`.
- [x] `tests/test_llm_lab.py` -- couvrir la matrice. (1) Le pas lit `tokenize(texte)` + ajouts, sans balise de gabarit : on regarde les `prompt_ids` reçus par le faux moteur. (2) Le BOS est ajouté si `adds_bos`, et `bos_token` est servi. (3) Sans `adds_bos`, pas de BOS. (4) `reasoning_always` donne un pas sans raisonnement. (5) « Générer » garde le gabarit. Adapter `…reads_the_tokens_already_added…`.
- [x] `tools/e2e/run_e2e.py` -- assertions ajoutées à `s_llm_loop`.
- [x] `notes-de-fusion.md` -- fichiers carrefour touchés.

**Acceptance Criteria:**
- Given « Le chat dort sur le » découpé sur un GGUF chargé, when le formateur clique « Tirer le token suivant », then le moteur lit les identifiants de l'INPUT (plus le BOS nommé si le modèle le demande) et rien d'autre, et la légende des Logits cite la fin de ce texte.
- Given un token ajouté, when il tire à nouveau, then le moteur lit l'INPUT entier, ajouts compris, dans l'ordre affiché.
- Given la suite E2E de l'Atelier LLM, when elle tourne, then `s_llm_loop`, `s_llm_screen` et `s_llm_live` passent.

## Implementation Notes

- Écart : `stages.output.raw_text` dit « (section 6) » et non « (section 4) » : « Générer » est dans la section 6 de `/llm` depuis la renumérotation du lot 6 (EXPERIENCE.md, Information Architecture).
- `_run_lab(raw=True)` passe par une aide `_step_context` (ajoutée avant `_lab_release`) ; `_step_bos_text` donne le texte du BOS (`metadata().bos_token`, sinon sa pièce). `continuation` n'est plus lu qu'avec `raw`.
- `_LoopLab.drawn` (E2E) envoie désormais `rendered = _LOOP_TEXT` (5 tokens), comme le pas réel.
- Vérifié sur de vrais GGUF (tokenizer seul) : Gemma 4 12B → `adds_bos() = 2` (`<bos>`), Qwen3.5-2B → `None`.
- Vérification : ruff propre ; pytest 5 489 réussis + 1 échec préexistant (README) ; E2E `llm_loop llm_screen llm_live` 84/84. Captures de l'Atelier LLM régénérées (52-54, 64, 65, 72-74), `01-diagnostic` remise à sa version.
- Revue (step-04) : 14 constats triés (journal ci-dessous), 4 corrigés par patch (test de `adds_bos` sur deux vrais GGUF, phrase BOS atténuée au pas 1 de l'INPUT avec une ligne de `llm.css`, `#llm-step-raw` masqué quand « Tirer » est indisponible, E2E lu dans le contenu), 10 rejetés, rien de différé. Ligne « token de fin » de la matrice couverte par l'E2E `_llm_loop_end`, ajouté au step-03.
- Vérification finale : ruff propre ; pytest 5 490 réussis + 1 échec préexistant (README) ; E2E `llm_loop llm_screen llm_live` 85/85.

## Spec Change Log

## Review Triage Log

| # | Source | Constat | Verdict | Preuve | Route |
| --- | --- | --- | --- | --- | --- |
| 1 | verification-gap, blind | `VocabTokenizer.adds_bos()` jamais exécuté par un test sur un vrai GGUF | medium | vérifié par le relecteur : `tiny-llama.gguf` → `None`, `tiny-bert-rank.gguf` → `2`, rien ne le fige | patch |
| 2 | verification-gap, edge-case, blind | `_step_bos_text` : `token_pieces` non protégé | low | seul un moteur en processus a `adds_bos` (le serveur, non), et `VocabTokenizer.token_pieces` ne lève pas ; la correction ajoute une garde | rejet |
| 3 | edge-case | `int(token)` hors du `try` de `_step_bos` | false | `adds_bos` renvoie `int \| None` par contrat (`engine.py`) | rejet |
| 4 | blind, edge-case | `continuation` ignoré sans `raw`, `raw` ignoré pour le cloud | low | seul appelant : `llm_step`, qui passe les deux et refuse le cloud (`_candidates_info`) | rejet |
| 5 | blind | BOS, texte et ajouts dans un seul segment `USER_MESSAGE` | low | l'appel de l'Atelier n'émet pas de `context_rendered` : aucune vue ne montre ces segments | rejet |
| 6 | blind | BOS sans texte lisible : phrase masquée alors que le BOS est lu | low | il faudrait un `bos_token` vide et une pièce vide à la fois : cas non démontré | rejet |
| 7 | blind | `adds_bos` absent du Protocol `Engine`, `llama_vocab_bos` appelé sans `getattr` | low | lu par `getattr` comme `dimensions` ; `llama_vocab_bos` existe dès que `get_add_bos` existe | rejet |
| 8 | blind, edge-case | Texte qui commence par le BOS (`<bos>`) : deux BOS lus | low | la page montre les deux (la phrase et la puce spéciale) : l'affichage reste exact ; cas rare, la correction ajoute une branche | rejet |
| 9 | blind | `#token-bos` visible au pas 1 de l'INPUT (texte seul) | low | `showInputStep` atténue les compteurs, pas la phrase | patch |
| 10 | blind | `prompt_tokens` du pas compte le BOS en plus | false | le `llm_generation_started` du pas va à `stepEvent` (OUTPUT seul) ; le schéma de la fenêtre lit le couloir de « Générer » | rejet |
| 11 | blind | `#llm-step-raw` visible pour un modèle cloud ou servi, où « Tirer » est grisé | low | aucune bascule `hidden` ; une ligne dans `renderStep` | patch |
| 12 | blind | E2E : phrase BOS codée en dur, `_llm_loop_end` appelé depuis `_llm_loop_bos`, contrôle redondant | low | `run_e2e.py`, `_llm_loop_bos` | patch |
| 13 | blind | Pas de test unitaire du token de fin | low | la ligne de matrice porte sur le texte de la page, couvert par l'E2E `_llm_loop_end` ; le chemin EOG de la session est préexistant | rejet |
| 14 | edge-case | Texte qui finit par `<think>` : token tiré classé « raisonnement » | low | il faut que le formateur tape la balise ; la correction touche `_call_model_local`, partagé avec la conversation | rejet |

## Verification

**Commands:**
- `uv run ruff check . && uv run ruff format --check .` -- expected: aucun écart
- `uv run pytest -q` -- expected: tout vert (hors échec préexistant README)
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only llm_loop llm_screen llm_live --channel msedge` -- expected: tout vert

**Manual checks (if no CLI):**
- `uv run wavestack --port 8426`, page `/llm`, sans changer le modèle choisi : « Le chat dort sur le », puis « Tirer ». Le token tiré prolonge la phrase, et la phrase « sans gabarit » est visible.
