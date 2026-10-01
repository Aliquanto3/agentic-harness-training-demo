---
title: 'Robustesse : flux, serveurs locaux, appels cloud parallèles, instantanés MCP'
type: 'bugfix'
created: '2026-10-01'
status: 'draft'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Six défauts de robustesse restent ouverts (CAP-2 de `SPEC.md`) : un flux SSE coupé ne se voit pas, un Ollama trop ancien pour `qwen35` donne une erreur brute « HTTP 500 » au premier tour, deux appels d'outils parallèles au même `index` seraient fusionnés, l'avertissement d'écart à l'instantané MCP d'AD-9 n'existe pas, la composition du contexte du sous-agent est écrite en dur, et `back_text` survit sans usage.

**Approach:** Corriger chaque point au plus près de son module, avec ses tests pytest, ses textes en trois langues, et fermer les entrées.

## Boundaries & Constraints

**Always:**
- Entrées fermées (`closed: <date> (story 2 des restes différés) — <preuve>`) :
  - **E003** — après N échecs consécutifs de `streamEvents` (N petit, par exemple 3), la barre haute affiche « Connexion au serveur perdue, nouvel essai… » (texte `ui.yaml`, trois langues) ; il disparaît au premier événement reçu ; la reprise par `Last-Event-ID` est inchangée.
  - **E048** — `openai_chat` : un fragment d'appel qui arrive avec un `id` différent sur une clé (`index`) déjà prise ouvre un nouvel appel ; deux appels au même `index` (ou sans `index`) et d'`id` différents restent deux appels. Test avec `httpx.MockTransport`. La vérification réelle (Groq, Mistral) est faite par la story 7 : noter dans l'entrée « vérifié avec doublure, réel en story 7 ».
  - **E067** — le contexte `sub{n}` est composé en itérant sur les briques effectives qui déclarent `sub` dans `contributes_to` ; aucune brique nouvelle n'y entre : un test montre que le contexte du sous-agent est identique avant et après.
  - **E089** — seuil `[mcp] snapshot_drift_threshold` dans `wavestack.toml` (valeur à choisir au plan, documentée) ; à la connexion d'un serveur public qui a un instantané dans `content/mcp_snapshots/`, si `tools/list` s'en écarte au-delà du seuil (outils ajoutés ou retirés, ou poids de la documentation), un avertissement est émis et affiché sur la carte MCP ; sans instantané, rien.
  - **E119** — un modèle servi par Ollama dont `/api/generate` répond 500 parce que l'architecture n'est pas prise en charge : raison française (et `en`, `de`) qui nomme la cause et propose llama-server ou une mise à jour d'Ollama ; le modèle précédent est rétabli, ou le modèle refusé dès le chargement si une requête de vérification légère le permet (choix au plan, consigné).
  - **E142** — `back_text` retiré de `content/llm_lab.yaml`, `content/rag_lab.yaml`, de leurs surcouches `en`/`de` et de `LlmLabContent` / `RagLabContent` (et des tests qui le citent).
- Textes nouveaux par `t()` / `msg()`, en `fr`, `en`, `de` ; ARCHITECTURE-SPINE (AD-9) et README à jour pour E089.

**Never:**
- Retenter ou espacer automatiquement les appels après une erreur de serveur.
- Faire entrer une brique de plus dans le contexte du sous-agent (E067 est un refactor sans effet).
- Toucher aux blocs `deferred` des stories 5 et 6 de `spec-corrections-2026-09-30` (autre agent) : rebaser après sa fusion si `llm_lab.yaml` ou `rag_lab.yaml` ont bougé.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Deux appels même index | fragments `index: 0, id: a` puis `index: 0, id: b` | deux `tool_calls` | aucune |
| Fragments d'un même appel | `index: 0, id: a` puis `index: 0` sans `id` | un appel, arguments concaténés | aucune |
| Ollama sans `qwen35` | 500 « unknown model architecture » | raison expliquée, modèle précédent actif | `harness_error` avec la cause |
| Instantané absent | serveur public sans fichier d'instantané | aucun avertissement | aucune |
| Flux coupé | serveur arrêté | indicateur après N échecs, effacé au retour | aucune |

</intent-contract>

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q` sur les fichiers touchés (`test_cloud*`, `test_model_servers.py`, `test_mcp*.py`, `test_subagent*.py`, `test_llm_lab.py`, `test_rag_lab.py`, `test_i18n.py`), en quarts -- expected: tout passe.
- E2E (avec l'accord d'Anaël) : tranche qui couvre la barre haute et MCP (`--only themes mcp_full mcp_lazy llm_screen rag_lab`) -- expected: 0 échec.
