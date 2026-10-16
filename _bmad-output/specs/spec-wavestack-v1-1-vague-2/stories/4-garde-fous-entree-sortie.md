---
title: 'WaveStack V1.1 vague 2 (4/10) : garde-fous entrée/sortie, modes et brique Garde-fous'
type: 'feature'
created: '2026-10-16'
status: 'review'
baseline_commit: '6268ac1'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/guardrails.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-5. Rien ne filtre aujourd'hui l'entrée ni la sortie du modèle : ni la
toxicité, ni les données personnelles en français. Le harnais n'a aucune brique qui montre à
un RSSI ce qu'il contrôlerait.

**Approach:** Un nouveau module `src/wavestack/guardrails/` (dépendance optionnelle
`guardrails`, comme `compression` : WaveStack démarre sans elle) avec une interface commune
(`Classifier.classify`/`mask`/`unload`) implémentée par deux garde-fous réels : la toxicité
(`gravitee-io/distilbert-multilingual-toxicity-classifier`, ONNX quantifié, `onnxruntime`,
sans torch) et les données personnelles (Microsoft Presidio + `fr_core_news_sm` + quatre
motifs français que Presidio n'a pas en natif). Un `GuardrailsManager` porte le mode par
garde-fou (bloquer / signaler / désactivé ; signaler devient masquer pour les données
personnelles) et décide seul ce qu'un verdict signifie : les classifieurs ne font que
classer. Une nouvelle brique `guardrails` est déclarée dans le schéma du harnais, après
`hooks`, avec ses trois composants (`toxicity`, `pii`, `injection`) et son contenu
(fr/en/de) ; elle est indisponible (« non installés », avec la commande) tant que la
dépendance optionnelle n'est pas là — l'installation en un clic depuis la brique et le
garde-fou `injection` (Prompt Guard) sont la story 5.

**Deferred to story 5 (explicitly out of this slice, tracked so nothing is silently
dropped):** le branchement des deux garde-fous dans la boucle d'un tour (blocage réel de
l'entrée ou de la sortie, masquage affiché) ; le `verdict-banner` sous le message dans Vue
humain ; le dépli du verdict dans Orchestration ; les boutons « Essayer : … » (CAP-6) ; le
réglage du mode depuis l'interface (aujourd'hui réglable seulement par code,
`GuardrailsManager.set_mode`). Le moteur est prêt et mesuré (ce compte rendu) ; le brancher
sur la boucle de tour touche ~60 lignes sensibles d'`app_session.py` (AD-13, le même point
que `before_model_call`/`on_turn_end` des hooks) et le rendu de la Vue humain dans `app.js` :
risque jugé trop élevé pour une seule passe sans tests de bout en bout, face au gain d'un
moteur déjà démontrable et mesuré sur les quatre exemples de `guardrails.md`.

## Boundaries & Constraints

**Always:**
- Un `Classifier` (`classify`, `mask`, `unload`) par garde-fou ; le mode (bloquer / signaler
  / désactivé) est décidé par `GuardrailsManager`, jamais par le classifieur.
- Modèles chargés à la demande (premier `classify`), déchargeables (`unload_idle`) ; mesuré à
  la main le 16/10 sur le poste de référence : toxicité ~192–285 Mo de RSS, données
  personnelles (Presidio + `fr_core_news_sm`) ~406–486 Mo, les deux ensemble ~486 Mo — sous le
  budget de 1,5 Go.
- `injection` déclaré dans l'interface commune et dans la brique, toujours `not_installed`
  tant que la story 5 n'a pas branché Prompt Guard.
- Aucun pytest ne télécharge un modèle : `tests/test_guardrails.py` n'injecte que des
  `Classifier` factices.
- Dépendance optionnelle `guardrails` dans `pyproject.toml` (`onnxruntime`, `tokenizers`,
  `presidio-analyzer`, `presidio-anonymizer`, `spacy`, le modèle `fr_core_news_sm` en wheel
  direct) : `uv sync --extra guardrails` s'installe sans droits admin.
- `presidio-fr` n'étant pas un paquet publié, son équivalent est quatre `PatternRecognizer`
  écrits à la main (NIR, SIRET/SIREN, numéro fiscal, plaque) ; Presidio couvre déjà
  EMAIL_ADDRESS, PHONE_NUMBER et IBAN_CODE nativement.

**Never:**
- Pas de torch : le repli toxicité documenté (`textdetox`) n'a pas d'export ONNX public (son
  seul poids est un `safetensors` de 680 Mo) ; faute d'alternative sans torch, un échec de
  chargement laisse le garde-fou en statut `error` au lieu d'un second modèle (voir le
  commentaire `shortcut:` dans `toxicity.py`).
- Pas de modification de `src/wavestack/mcp/`, `mcp.html`/`mcp.js` (lane A, story 1 et 5 en
  parallèle).
- Pas d'écriture dans le journal de sécurité (CAP-3, story 1) : ce module n'émet aucun
  événement vers lui.
- Pas de contenu dangereux réel ; aucun secret.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Mode désactivé | `mode = "off"` | `GuardrailsManager.check` ne renvoie aucun verdict pour ce garde-fou | — |
| Mode bloquer, détecté | Texte toxique, `mode = "block"` | `Verdict.blocks is True`, aucun masquage | — |
| Mode signaler, détecté | Texte toxique, `mode = "flag"` | `Verdict.detected is True`, `blocks is False` | — |
| Mode signaler (masquer), PII détectées | Message avec téléphone/e-mail, `mode = "flag"` | `Verdict.masks is True`, texte avec `[TÉLÉPHONE]`/`[E-MAIL]` | — |
| Rien détecté | Texte neutre | `detected is False`, pas de masquage même en `flag` | — |
| `injection`, tout mode sauf `off` | — | `Verdict.status == "not_installed"` | — |
| Classifieur en échec (modèle absent/cassé) | `classify` lève une exception | `Verdict.status == "error"`, `blocks is False` : jamais le tour n'est bloqué par un modèle absent | exception capturée dans `_check_one` |
| Garde-fou inconnu | `set_mode("made_up", ...)` | `ValueError` | levée, pas de mode silencieusement ignoré |
| Brique indisponible | Dépendance `guardrails` absente | `_availability("guardrails")` renvoie `False` et le message « non installés » (fr/en/de) | — |

## Code Map

- `src/wavestack/guardrails/contract.py` (nouveau) — `Classifier`, `Classification`,
  `Entity`, `Verdict`, les types `GuardrailId`/`Direction`/`GuardrailMode`/`GuardrailStatus`.
- `src/wavestack/guardrails/toxicity.py` (nouveau) — `ToxicityGuardrail` (ONNX quantifié,
  téléchargé via `wavestack.models.download`, dans `models_dir()/guardrails/toxicity`).
- `src/wavestack/guardrails/pii.py` (nouveau) — `PiiGuardrail` (Presidio + `fr_core_news_sm`
  + 4 motifs français).
- `src/wavestack/guardrails/manager.py` (nouveau) — `GuardrailsManager`.
- `src/wavestack/guardrails/availability.py` (nouveau) — `missing_fr()`.
- `src/wavestack/bricks/registry.py` — brique `guardrails` ajoutée après `hooks`.
- `src/wavestack/session/app_session.py` — `_guardrails_missing`/`_guardrails` à
  l'initialisation ; `_availability("guardrails")` câblée comme `compression`. Pas d'autre
  changement (voir « Deferred to story 5 »).
- `content/bricks/guardrails.yaml` (+ `content/i18n/{en,de}/bricks/guardrails.yaml`) —
  texte de la brique.
- `content/messages.yaml` (+ `en`/`de`) — `guardrails.missing`/`guardrails.install`,
  `invalid.guardrails`, `unavailable.guardrails`.
- `pyproject.toml` — extra `guardrails`.
- `tests/test_guardrails.py` (nouveau) — le manager, factice uniquement.

</frozen-after-approval>
