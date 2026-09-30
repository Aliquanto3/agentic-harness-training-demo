---
title: 'Langues (1/5) : socle, sélecteur de langue et défauts du LLM en anglais et en allemand'
type: 'feature'
created: '2026-09-29'
status: 'draft'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Toute l'interface de WaveStack et tous ses contenus sont en français. L'utilisateur veut l'anglais, le français et l'allemand. La langue se choisit seulement quand la conversation est vide, et les paramètres par défaut (prompt système, mémoires, descriptions d'outils…) doivent aussi être traduits (demande du 2026-09-29).

**Approach:** Cette story est la première de cinq, parce que le périmètre représente environ 2 000 textes par langue. Elle pose :
- le réglage `language` (fr, en ou de ; fr par défaut) ;
- le changement de langue, refusé tant que la conversation n'est pas vide ;
- un sélecteur dans la barre haute ;
- la résolution des contenus par langue, avec repli sur le français ;
- la traduction en anglais et en allemand de tout le contenu par défaut qui part vers le LLM.

Les stories 2 à 5 (interface principale, contenus pédagogiques, ateliers et pages annexes, messages produits par le backend) sont consignées dans `deferred-work.md`.

La story est approuvée par délégation, pendant la nuit, et relue le matin.

## Boundaries & Constraints

**Always:**
- **Le français ne bouge pas.** Les fichiers de `content/` restent où ils sont, octet pour octet. Les traductions vivent dans `content/i18n/{en,de}/`, avec la même arborescence et les mêmes noms de fichiers.
  - Un seul point de résolution, `config.content_file(rel, lang)` : il donne `content/i18n/{lang}/{rel}` s'il existe, sinon `content/{rel}`.
  - Tous les chargeurs de contenu passent par ce point (aujourd'hui `content_dir() / rel`).
  - Une langue sans traduction d'un fichier retombe sur le français, sans erreur.
- **Parité vérifiée.** Un fichier traduit est validé par le même modèle pydantic que le français. Il garde les mêmes identifiants (`id` des outils, scénarios, skills, entrées de mémoire, hooks) et les mêmes clés de gabarit (`{…}`). Un test de parité le garantit pour chaque fichier traduit.
- **Réglage :**
  - `settings.json` porte `"language": "fr" | "en" | "de"`. Une valeur inconnue vaut `fr`.
  - `/api/state` expose `language`, les langues offertes et `language_locked` (vrai si la conversation n'est pas vide).
- **Changement de langue.** L'intention de classe (b) `POST /api/intentions/language {language}` est refusée en 409 avec la raison (`SendRefused`) si :
  - la session n'est pas `idle` ;
  - ou l'historique, les documentations MCP chargées, les skills chargés ou la mémoire de démonstration déjà écrite dans le contexte ne sont pas vides.

  Acceptée, elle :
  - enregistre le réglage ;
  - recharge les contenus en cache (prompt par défaut, outils, hooks, skills, mémoire de démonstration restaurée dans la nouvelle langue, sous-agent, MCP, RAG) ;
  - émet `language_changed {language}` puis les états habituels (`bricks_changed`, `scenario_changed`, `memory_changed`).

  Le front recharge alors la page.
- **Défauts du LLM traduits en anglais et en allemand**, dans un registre naturel, avec les mêmes consignes et la même longueur à peu près :
  - `prompts/system.md` (« Réponds en français » devient « Answer in English » / « Antworte auf Deutsch ») ;
  - `prompts/subagent.md` ;
  - `tools.yaml` (descriptions et paramètres ; libellés d'interface inclus) ;
  - `hooks.yaml` ;
  - `memory/memory.yaml` ;
  - `skills.yaml` et `skills/*/SKILL.md` (sauf `NOTICE.md`) ;
  - `subagent.yaml`, `mcp.yaml`, `mcp_local/glossary.yaml` ;
  - les textes de `rag.yaml` envoyés au modèle ;
  - la date injectée par H3 (noms des jours et des mois, dans `hooks.py`).
- **Sélecteur :**
  - Dans la barre haute, un `<select>` accessible, avec les langues écrites dans leur propre langue : « Français », « English », « Deutsch ».
  - Il est désactivé, avec une infobulle qui dit pourquoi, quand `language_locked` est vrai.
  - `<html lang>` suit la langue.
  - Seuls les libellés du sélecteur et de son infobulle sont traduits dans cette story : le reste de l'interface reste français jusqu'à la story 2, ce que l'infobulle signale.
- **Documentation :** AD-19 et la section « Langue » d'`ARCHITECTURE-SPINE.md`, et la convention de `CLAUDE.md`, disent maintenant « français par défaut, anglais et allemand en surcouche sous `content/i18n/` ».

**Never:**
- Ne rien déplacer ni renommer dans `content/`.
- Ne pas renommer les champs `*_fr` du contrat d'événements.
- Ne pas traduire le corpus RAG ni reconstruire l'index : les modèles d'embedding et de reranking sont multilingues (story 5).
- Ne pas changer de langue pendant une conversation.
- Ne pas faire de traduction automatique à l'exécution ni ajouter de dépendance.
- Les tests et l'E2E existants restent en français, inchangés.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Passage à l'anglais | Session `idle`, conversation vide | 200, `settings.json` porte `en`, `language_changed`, puis un tour envoie le prompt système anglais et les descriptions d'outils anglaises | — |
| Conversation en cours | Un échange dans l'historique | 409, la raison en français et dans la langue courante, rien d'écrit | `SendRefused` |
| Tour en cours | Session non `idle` | 409 | `SendRefused` |
| Langue inconnue | `{"language": "it"}` | 422, rien d'écrit | validation |
| Fichier non traduit | `de`, fichier absent de `content/i18n/de/` | Repli sur le français, sans erreur | — |
| Fichier traduit invalide | YAML allemand qui casse le schéma | `harness_error` (comportement AD-19 existant), puis repli sur le français pour ce fichier | — |
| Mémoire de démonstration | `en`, puis restauration de la mémoire | Les entrées de démonstration sont en anglais | — |
| H3 en allemand | Hook H3 actif, langue `de` | Date avec jour et mois allemands | — |
| Retour au français | `fr` après `en` | Contexte identique octet pour octet à celui d'avant la story | — |

</frozen-after-approval>

## Code Map

- `src/wavestack/config.py` :
  - `content_dir()` (≈ :943) : ajouter `content_file(rel, lang=None)`, qui lit la langue du réglage si elle n'est pas donnée ;
  - `Config.language` (valeur bornée à fr, en, de) ;
  - `LANGUAGES = ("fr", "en", "de")`.
- Les chargeurs qui font `content_dir() / …` passent par `content_file` : `bricks/contract`, `cloud`, `compression/port`, `context/segments`, `hooks`, `mcp/servers`, `mcp/local_server`, `memory`, `models/catalog`, `rag/corpus`, `rag/lab`, `scenarios`, `session/llm_lab`, `skills`, `subagent`, `tools/*`. Leurs caches `@cache` doivent se vider au changement de langue (une fonction `clear_content_caches()` les appelle).
- `src/wavestack/session/app_session.py` :
  - `set_language` sur le modèle de `clear_conversation` (≈ :5016) et du refus hors `idle` ;
  - rechargement comme `_reconfigure` (≈ :5130), sans vider autre chose ;
  - `_default_prompt` (≈ :789) relu ;
  - l'état publié porte `language` et `language_locked`.
- `src/wavestack/web/app.py` -- ajouter la route `/api/intentions/language` à côté de `clear_conversation` et `reset` (≈ :684-753).
- `src/wavestack/trace/catalog.py` -- créer `LanguageChangedPayload`.
- `src/wavestack/hooks.py:42-54,216` -- noms des jours et des mois par langue.
- `src/wavestack/web/static/index.html`, `app.js` -- le sélecteur dans la barre haute (à côté du thème), l'état verrouillé, `location.reload()` après succès, et `document.documentElement.lang`.
- `content/i18n/{en,de}/…` -- les fichiers traduits listés dans « Always ».
- `_bmad-output/planning-artifacts/architecture/architecture-agentic-harness-training-demo-2026-09-23/ARCHITECTURE-SPINE.md` (AD-19, section « Langue ») et `CLAUDE.md` -- la convention de langue.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- les stories 2 à 5.
- Tests :
  - `tests/test_i18n.py` (nouveau) : parité par fichier et par langue, résolution avec repli, intention (200 et 409), contexte anglais et allemand d'un tour, H3 ;
  - le rendu français inchangé : les tests existants passent sans modification ;
  - `tools/e2e/run_e2e.py` : le scénario `language` (sélecteur verrouillé après un tour, passage à l'anglais une fois la conversation vidée, prompt système anglais dans « Contexte LLM », retour au français).

## Tasks & Acceptance

**Execution:**
- [ ] `src/wavestack/config.py` et tous les chargeurs -- `content_file`, la langue, le vidage des caches.
- [ ] `src/wavestack/session/app_session.py`, `src/wavestack/web/app.py`, `src/wavestack/trace/catalog.py`, `src/wavestack/hooks.py` -- l'intention, le rechargement, l'état, la date H3.
- [ ] `content/i18n/en/**`, `content/i18n/de/**` -- les traductions des défauts du LLM.
- [ ] `src/wavestack/web/static/index.html`, `app.js` -- le sélecteur.
- [ ] `tests/test_i18n.py`, `tools/e2e/*` -- la matrice et l'E2E.
- [ ] `ARCHITECTURE-SPINE.md`, `CLAUDE.md`, `deferred-work.md`, `README.md` -- la documentation.

**Acceptance Criteria:**
- Given une conversation vide, when on choisit « English » puis on envoie « What time is it? » avec la brique Outils, then le corps envoyé au modèle ne contient que des défauts anglais (prompt système, descriptions d'outils), et l'interface se recharge en `lang="en"`.
- Given un échange dans l'historique, when on ouvre le sélecteur, then il est désactivé et son infobulle dit de vider la conversation d'abord.
- Given la langue `fr`, when on joue la suite existante (pytest et E2E), then tout passe sans modifier un seul test existant.

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest -q` -- expected: tout vert, sans test existant modifié
- `$env:PYTHONUTF8=1; uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 FAIL, dont `[language]`

## Implementation Notes

## Spec Change Log

## Review Triage Log
