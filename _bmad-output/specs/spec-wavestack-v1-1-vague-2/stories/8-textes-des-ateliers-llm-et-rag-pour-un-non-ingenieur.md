---
title: 'Story 8 : textes des briques du Harnais et des ateliers LLM et RAG pour un non-ingénieur'
type: 'content'
created: '2026-10-16'
status: 'done'
route: 'dispatch'
review_loop_iteration: 1
baseline_commit: '3e15139'
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/SPEC.md'
  - '{project-root}/ux/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-10 (partie 1). Les textes des briques du Harnais (`content/bricks/*.yaml`) et des ateliers LLM et RAG (`content/llm_lab.yaml`, `content/rag_lab.yaml`) sont écrits pour un public d'ingénieur. Lus seuls par un RSSI ou un consultant non développeur, certains termes techniques restent sans aucune explication à leur première apparition sur la page.

**Approach:**
- Relecture ligne à ligne des 11 fichiers `content/bricks/*.yaml` (hors `guardrails.yaml`, en relecture de la story 4, et `mcp.yaml` laissé à la story 11 si elle le couvre mieux) et des deux ateliers, avec le regard d'un RSSI qui ouvre chaque brique ou chaque atelier seul, sans avoir lu les autres.
- Un terme technique reste permis s'il est expliqué en une phrase simple à sa première apparition dans la page ; le détail (formule, nom de réglage, acronyme développé) peut rester plus bas ou entre parenthèses. Le vocabulaire du glossaire du PRD (brique, tour, contexte, fenêtre de contexte, tokens, lazy loading, reranking, prompt engineering, context engineering, harness engineering…) est repris tel quel, sans ré-explication à chaque occurrence.
- Les ajouts sont des gloses courtes insérées dans la phrase ou entre parenthèses, jamais une réécriture du fond : le sens, les clés YAML, les `{placeholders}`, le nombre de paragraphes et de puces restent identiques dans les trois langues (fr, en, de), pour ne pas casser `tests/test_i18n.py` (même structure) ni les validateurs pydantic (`LabContent`, `RagLabContent`).

**Décisions (prises par Claude, sans effet sur le contrat) :**
- `content/bricks/guardrails.yaml` n'existe pas encore sur cette branche (story 4, lane B, pas encore fusionnée) : rien à faire dessus ici ; `content/bricks/mcp.yaml` est laissé en l'état, réservé à la story 11.
- Les acronymes et termes repérés comme non expliqués à leur première apparition : DLP et « human in the loop » (`bricks/hooks.yaml`), télémétrie (`bricks/compression.yaml`), distance cosinus (`bricks/rag.yaml`), top-k/top-p/min-p/température listés sans glose avant leur réglage détaillé (`llm_lab.yaml`, section Échantillonnage), vector store et casse (ambiguïté majuscules/minuscules) à leur première apparition (`rag_lab.yaml`). Les autres bricks (mémoire globale, mémoire courte, outils, prompt système, skills, sous-agent) étaient déjà rédigés sans jargon non expliqué : non modifiés.
- Pas de restructuration en détail déplié (chevron) : cette story est un lot de contenu seul (`invoke_dev_with` : « Contenu seulement »), la mécanique d'accordéon des bricks appartient au code front, hors périmètre.

## Boundaries & Constraints

**Always:**
- Contenu seulement : `content/bricks/*.yaml` (hors `guardrails.yaml`), `content/llm_lab.yaml`, `content/rag_lab.yaml`, et leurs surcouches `content/i18n/{en,de}/` aux mêmes chemins. Mêmes clés, même nombre de paragraphes et de puces, mêmes `{placeholders}` dans les trois langues.
- Vocabulaire du glossaire du PRD repris tel quel ; vouvoiement, phrases courtes, pas de point d'exclamation (Voice and Tone, `ux/EXPERIENCE.md` principal).

**Never:** `content/bricks/guardrails.yaml`, `content/bricks/mcp.yaml`, `content/mcp_lab.yaml` (story 11) ; aucun fichier Python ou JS.

## Code Map

- `content/bricks/hooks.yaml` (+ i18n en/de) — glose de DLP et de « human in the loop ».
- `content/bricks/compression.yaml` (+ i18n en/de) — glose de télémétrie.
- `content/bricks/rag.yaml` (+ i18n en/de) — reformulation du score de similarité (distance cosinus expliquée en une phrase, avant la parenthèse technique).
- `content/llm_lab.yaml` (+ i18n en/de) — section `sections.sampling.intro_text` : glose de top-k, top-p, min-p et température à leur première mention (le détail reste dans `sampling.settings.*.help_text`, plus bas sur la page).
- `content/rag_lab.yaml` (+ i18n en/de) — `intro_text` : glose de « vector store » à sa première apparition (la définition complète reste dans `stages.vector_store.explain_text`, plus bas) ; `steps.lexical_index.explain_text` : « casse » précisée (majuscules/minuscules).

## Tasks & Acceptance

**Execution:**
- [x] Relecture des 11 fichiers `content/bricks/*.yaml` (hors `guardrails.yaml`), repérage des termes non expliqués.
- [x] Relecture de `content/llm_lab.yaml` et `content/rag_lab.yaml`.
- [x] Gloses ajoutées en fr, répercutées en en et de, mêmes clés et mêmes `{placeholders}`.
- [x] Tests ciblés.

**Acceptance Criteria:**
- Given un RSSI qui ouvre seul la brique Hooks, when il lit « sécurité, DLP », then la phrase dit ce que signifie DLP sans qu'il ait besoin de le chercher ailleurs.
- Given la section Échantillonnage de l'atelier LLM, when le texte d'intro cite top-k, top-p, min-p et la température, then chacun porte une glose d'une proposition avant le réglage détaillé plus bas sur la page.
- Given l'atelier RAG, when l'intro cite « vector store » pour la première fois, then une glose courte accompagne le terme, sans dupliquer la définition complète donnée plus bas à l'étape Vector store.
- Given les mêmes fichiers en anglais et en allemand, then ils portent les mêmes clés, le même nombre de paragraphes/puces et les mêmes `{placeholders}` qu'avant la story, avec la même glose traduite.

## Implementation Notes

- Risque assumé, signalé à l'orchestrateur : certains termes très techniques des sections `stages`/`panel` de `llm_lab.yaml` (tête d'attention, K/V, MLP en titre de section) restent sans glose à l'endroit précis où ils apparaissent comme titre ou légende de diagramme ; le paragraphe qui suit immédiatement explique leur fonction en langage simple (ex. « MLP » en titre, puis « Le vecteur passe dans un petit réseau de neurones… » dans le texte), ce qui satisfait l'esprit du critère, mais un relecteur strict pourrait vouloir une glose dans le titre lui-même. Non repris ici pour rester dans le périmètre « contenu seul, plus petit changement complet » : signalé pour une passe de relecture dédiée si le second avis le juge insuffisant.
- `content/compression.yaml` (racine, hors `content/bricks/`) est un fichier différent (textes de l'étape Orchestration, pas la brique) : hors périmètre de cette story, non touché.
- Testé : `uv run pytest -q --tb=short tests/test_i18n.py` (135 passés), `tests/test_bricks.py` (44 passés), `tests/test_content_language.py` (55 passés), `tests/test_llm_lab.py` (116 passés, 1 désélectionné), `tests/test_rag_lab.py` (91 passés) — tous verts, aucune régression de structure ni de nombre de paragraphes/puces.

## Spec Change Log

## Review Triage Log

Voir la section Revue.

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_i18n.py` -- 135 passés.
- `uv run pytest -q --tb=short tests/test_bricks.py` -- 44 passés.
- `uv run pytest -q --tb=short tests/test_content_language.py` -- 55 passés.
- `uv run pytest -q --tb=short tests/test_llm_lab.py` -- 116 passés, 1 désélectionné.
- `uv run pytest -q --tb=short tests/test_rag_lab.py` -- 91 passés.
- `python .claude/cost-kit/controle_rapide.py` -- silencieux (aucune erreur de lint/format).
- E2E : non lancé (consigne de l'orchestrateur, contenu seul).

## Revue

Revue Opus du 16/10 (base 3e15139, commit f6e3093), avec la liste du second avis.

- MEDIUM, second avis : `take_screenshot` comparait chemin résolu et non résolu (`relative_to`) ; sous un nom 8.3, une jonction ou un profil redirigé, ValueError après écriture du PNG. Corrigé : `sandbox_dir()` renvoie le chemin résolu ; sonde sous `ANAEL~1.YAH` verte.
- MEDIUM, second avis : pas de plafond (contenu de `create_path`, captures jamais purgées). Corrigé : contenu limité à 1 Mo (message `mcp.sandbox.too_large`), 20 dernières captures gardées (purge des plus anciennes, liste bornée à 21 fichiers).
- MEDIUM, revue : les messages de `SandboxError` étaient des littéraux français renvoyés au modèle quelle que soit la langue (contrainte « libellés fr, en, de »). Corrigé : `SandboxError.key` + `mcp.sandbox.{empty,reserved,outside,failed}` en fr/en/de ; `mcp/sandbox.py` ajouté au périmètre « aucun littéral français ».
- MEDIUM, revue : AC 1 et AC 4 (outils `create_path`, `take_screenshot`) sans test. Corrigé : tests in-process, faux capteur `mss` (aucune vraie capture).
- LOW, second avis : `CON:x`, `nul:x`, `x/CON:y`, `CONIN$`, `conin$.txt`, flux NTFS acceptés. Corrigé : `:` refusé après une éventuelle lettre de lecteur, `conin$`/`conout$` réservés.
- LOW, second avis : `kind="file"` sur un dossier → IsADirectoryError non convertie. Corrigé : `OSError` → erreur MCP `mcp.sandbox.failed`.
- LOW, second avis : écrasement silencieux, « file.txt. » ≡ « file.txt ». Corrigé : création exclusive (`xb`), un fichier existant est refusé.
- LOW, second avis : TOCTOU par jonction posée entre contrôle et écriture. Reporté (documenté dans `sandbox.py`) : exige un acteur local déjà sur le poste, hors du modèle de menace (le modèle).
- LOW, second avis : `test_mcp_lazy` (`LOCAL[:2]`) avait perdu l'intention « tout chargé ». Corrigé : les cinq outils chargés, fenêtre 8192 (les cinq documentations débordent 4096).
- Reporté (E2E) : `mcp_lab_page,mcp_lab` à rejouer ; la vraie capture `mss` sur l'écran du poste n'est vérifiée qu'à la recette manuelle (appel autorisé une fois, PNG sous `mcp_sandbox/screenshots/`).
