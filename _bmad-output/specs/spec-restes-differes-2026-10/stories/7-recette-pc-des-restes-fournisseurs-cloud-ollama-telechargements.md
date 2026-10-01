---
title: 'Recette PC des restes : fournisseurs cloud, Ollama, téléchargements'
type: 'chore'
created: '2026-10-01'
status: 'draft'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/implementation-artifacts/guide-test-pc-palier-2.md'
warnings: []
deferred: []
---

<intent-contract>

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
- Chaque entrée fermée cite la ligne du fichier de résultats ; une entrée qui échoue reste ouverte avec le constat chiffré.

**Never:**
- Lancer un serveur, un modèle ou l'E2E sans l'accord d'Anaël, ou pendant ses tests manuels.
- Écrire une clé d'API dans un fichier versionné.
- Corriger au-delà de ce que le constat impose : un défaut plus large devient une entrée de `deferred-work.md`.

</intent-contract>

## Verification

**Commands:**
- `uv run pytest -q` sur les fichiers touchés par les correctifs (`test_cloud*.py`, `test_reasoning*.py`, `test_global_memory.py`) -- expected: tout passe.

**Manual checks (if no CLI):**
- `resultats-restes-pc-2026-10.md` : une ligne par vérification, avec verdict ; `deferred-work.md` : chaque entrée de la story fermée ou complétée d'un constat.
