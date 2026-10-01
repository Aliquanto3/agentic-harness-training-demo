---
title: "Décisions d'Anaël appliquées"
type: 'feature'
created: '2026-10-01'
status: 'draft'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-restes-differes-2026-10/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-langues/i18n-conventions.md'
warnings: ['multiple-goals']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Dix-neuf entrées de `deferred-work.md` attendent une décision d'Anaël (section « Décisions à prendre par Anaël » de `SPEC.md`, D1 à D19). Tant qu'elles restent ouvertes, le fichier ne dit pas ce qui est voulu (CAP-3).

**Approach:** Pour chaque Dn tranché (sauf D16, story 4), appliquer la décision, ou fermer l'entrée avec la décision quand elle est « non » ou « garder ». Chaque point ci-dessous ne s'applique **que si Anaël a choisi l'option indiquée** ; un autre choix est spécifié au plan à partir de sa réponse.

## Boundaries & Constraints

**Always:**
- Préalable : la réponse d'Anaël à chaque Dn est consignée (`SPEC.md` ou `.memlog.md`). Un Dn sans réponse reste ouvert, sans code.
- Fermetures sans code si la recommandation « non / garder » est suivie : **D1** (E007), **D2** (E010), **D8** (E061), **D10** (E079), **D12** (E081), **D13** (E087), **D14** (E088) — `resolution: décision d'Anaël du <date> — <décision>`.
- **D3 = oui** (E038) — quand « Afficher les actions forcées » passe à vrai, les listes d'options des briques qui ont un bouton « Forcer » se déplient ; l'interrupteur porte un titre de section et l'icône ✋, distinct des interrupteurs de briques. EXPERIENCE.md à jour.
- **D4 = prévenir** (E045) — la consigne de `mcp_full` (`content/scenarios.yaml` et surcouches) annonce un tour d'environ deux minutes sur un poste sans GPU et dit pourquoi.
- **D5 = oui** (E051) — sous la réponse d'un tour qui a appelé des outils, la Vue humain affiche « Outils consultés pendant ce tour : … », chaque nom lié à son étape d'Orchestration ; rien si aucun outil. EXPERIENCE.md à jour.
- **D6 = oui** (E052) — un 429 dont l'en-tête `x-ratelimit-limit-req-minute` vaut `0` donne « aucun quota actif sur ce compte : vérifiez le plan dans la console du fournisseur » ; ni attente ni nouvel essai ; section Never de `spec-11b-corrections-test-manuel-story-11.md` amendée (lecture permise pour ce message seul).
- **D7 = oui** (E060) — le tiroir de la mémoire globale affiche la date d'écriture (`created_at`) de chaque entrée, format court, fuseau du poste, langue de la session.
- **D9 = garder 300** (E062) — rien ici ; la mesure est faite par la story 7.
- **D11 = valider** (E080) et **D15 = valider** (E093) — retirer « à valider » d'AD-4 (H-1) et d'AD-21 dans ARCHITECTURE-SPINE ; fermer les entrées.
- **D17 = consigne** (E124) — la consigne du scénario Raisonnement annonce qu'un petit modèle réfléchit jusqu'au budget même pour un message simple.
- **D18 = réponses mesurées** (E126) — `tests/test_program.py` (`fits`) simule l'historique cumulé avec des réponses de la taille relevée au lot K (`resultats-lot-k-2026-09-29.md:127`, ≈ 500 tokens au plus) au lieu de la réserve ; le commentaire « deferred (spec of lot K) » est retiré.
- **D19 = accepter** (E139) — commentaire dans `wavestack.toml` et README : `hosting_text` et `notes_text` sont saisis par l'opérateur et affichés tels quels, dans toutes les langues.
- Tout texte nouveau en `fr`, `en`, `de`.

**Never:**
- Appliquer un Dn sans réponse d'Anaël, ou une option qu'il n'a pas choisie.
- Toucher à D16 / E121 (story 4) ou à la mesure de D9 (story 7).
- Changer le comportement de H1, H5, du budget de raisonnement ou de `MAX_CHARS`.

</intent-contract>

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucun écart.
- `uv run pytest -q` sur les fichiers touchés (`test_program.py`, `test_cloud*.py`, `test_global_memory.py`, `test_i18n.py`, `test_ui_texts.py`), en quarts -- expected: tout passe.
- E2E (avec l'accord d'Anaël) : tranches des écrans touchés (`forced_native`, `global_memory`, `cloud`, `ui_language`) -- expected: 0 échec, contrôles ajoutés pour D3, D5, D7.
