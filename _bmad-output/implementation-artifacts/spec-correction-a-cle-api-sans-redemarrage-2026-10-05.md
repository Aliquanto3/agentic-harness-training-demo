---
title: 'Correction A du 2026-10-05 : une clé API changée au Diagnostic est prise en compte sans redémarrer'
type: 'bugfix'
created: '2026-10-05'
status: 'done'
route: 'dispatch'
baseline_commit: 'd239b094e8b10bebdae0f13d878532dea1626d34'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Quand Anaël change la clé API d'un modèle cloud dans l'onglet Diagnostic, le modèle cloud déjà actif dans l'onglet Harnais continue d'envoyer l'ancienne clé jusqu'au redémarrage : le moteur cloud garde la clé reçue à sa création (`CloudEngine._key`), et re-choisir le même modèle est un no-op (`already_active`). La page Harnais ne relit pas non plus sa liste de modèles après l'enregistrement d'une clé.

**Approach:** Après un `set_api_key` réussi, la session d'application remet la clé relue par `config.cloud_key` au moteur actif si c'est ce modèle cloud (même `id`) : un `use_key` sur l'adaptateur, sans recharger le modèle. La page Harnais relit sa liste de modèles sur `effect_applied {effect: "api_key_set"}`. Le message `cloud.key_saved` (fr, en, de) et la doc utilisateur disent que la clé s'applique tout de suite.

## Boundaries & Constraints

**Always:** la clé n'apparaît jamais dans une réponse, un événement ou un texte affiché (AD-15) ; l'ancienne clé reste masquée par le moteur après le changement (une réponse encore en route ne la laisse pas fuir). `config.cloud_key` reste le seul lecteur de clé (AD-20) ; une clé du fichier passe avant la variable d'environnement, comme aujourd'hui. Les intentions de classe (b), dont `set_api_key`, restent refusées hors `idle` et `diagnostic` (garde existante `_diagnostic_class_b`) : aucune génération ne tourne quand la clé change.

**Never:** recharger le modèle (pas de `model_load_started`/`ended`, pas de libération) pour un simple changement de clé ; prendre en compte une variable d'environnement définie après le lancement (hors champ, déjà documenté `docs/modeles.md`) ; toucher aux parties Atelier LLM/RAG/MCP d'`app_session.py`, `rag/lab.py`, `rag.js`, `llm.js`, `llm_lab.py` (travaux parallèles) ; nouveau type d'événement ou nouveau champ dans `effect_applied`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Clé du modèle actif changée | modèle cloud `groq` actif avec clé A ; `set_api_key groq B` | 200, `key_set: true` ; la requête suivante du Harnais part avec B | N/A |
| Même modèle re-choisi | après le cas ci-dessus, `select_model groq` | `already_active`, pas de rechargement ; requête suivante avec B | N/A |
| Clé d'un autre modèle | `groq` actif ; `set_api_key mistral X` | moteur actif inchangé (toujours A) | N/A |
| Aucun modèle cloud actif | modèle local ou aucun modèle ; `set_api_key groq B` | clé enregistrée, rien d'autre ; un choix ultérieur de `groq` charge avec B | N/A |
| Écriture impossible | `api_keys.json` non inscriptible | 409 `cloud.key_not_saved`, moteur actif inchangé | refus existant |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/cloud_base.py` -- `CloudEngine.__init__` (~l.450) garde `self._key` ; `_headers` (~l.528) le lit à chaque requête ; `mask` (~l.464) masque via `mask_key`. Seul endroit du moteur qui touche la clé (sous-classes `openai_chat`, `openai_responses`, `anthropic_messages` n'y touchent pas).
- `src/wavestack/session/app_session.py` -- `_install_cloud` (~l.2442) crée le moteur avec `config.cloud_key(entry)` ; `self._cloud` (entrée active), `self._engine`, `self._lock`. `switch_model` (~l.1908) : `same_as` → `already_active` (ne pas changer).
- `src/wavestack/web/app.py` -- route `set_api_key` (~l.896) : `session.set_api_key(...)` puis réponse ; `app_session` y est disponible.
- `src/wavestack/session/diagnostic.py` -- `set_api_key` (~l.1022) : écrit via `apply_setting(ApiKeySet)` qui émet `effect_applied {effect: "api_key_set", id, key_set}`. Ne pas changer.
- `src/wavestack/web/static/app.js` -- `case "effect_applied"` (~l.614) ; `scheduleModelList()` (~l.2537) relit `/api/diagnostic` (débouncé 150 ms).
- `content/messages.yaml` (~l.1219), `content/i18n/en/messages.yaml` (~l.1210), `content/i18n/de/messages.yaml` (~l.1213) -- `cloud.key_saved`.
- `docs/modeles.md` (~l.332-335) -- étape « Clé » ; aucune doc ne parle aujourd'hui de redémarrer après une clé.
- `tests/test_cloud.py` -- `Provider` (faux fournisseur, `requests` enregistrées), `_app(monkeypatch, provider)`, `_cloud_session`, `_turn`, `SENTINEL`, `ORIGIN`, `GROQ_TEXT`.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/models/cloud_base.py` -- ajouter `CloudEngine.use_key(key)` : la clé des requêtes suivantes ; garder les clés précédentes et les masquer aussi dans `mask` -- AD-15 même pour une réponse partie avec l'ancienne clé.
- [x] `src/wavestack/session/app_session.py` -- ajouter `use_api_key(model_id) -> bool` : si l'entrée cloud active a cet `id`, relire `config.cloud_key(entry)` et la passer au moteur (`use_key`) sous `self._lock` ; `False` sinon -- point unique côté session, sans rechargement.
- [x] `src/wavestack/web/app.py` -- route `set_api_key` : après le succès de `session.set_api_key`, appeler `app_session.use_api_key(intention.id)`.
- [x] `src/wavestack/web/static/app.js` -- `effect_applied` avec `p.effect === "api_key_set"` : `scheduleModelList()` puis `break`.
- [x] `content/messages.yaml`, `content/i18n/en/messages.yaml`, `content/i18n/de/messages.yaml` -- `cloud.key_saved` : la clé est prise en compte tout de suite, sans relancer.
- [x] `docs/modeles.md` -- étape « Clé » : une phrase, la clé s'applique tout de suite, y compris au modèle cloud déjà actif.
- [x] `tests/test_cloud.py` -- tests de la matrice : clé changée → en-tête `Authorization` de la requête suivante = nouvelle clé ; même modèle re-choisi → `already_active` et nouvelle clé ; autre `id` → inchangé ; `use_key` masque l'ancienne et la nouvelle clé.

**Acceptance Criteria:**
- Given un modèle cloud actif et une nouvelle clé enregistrée au Diagnostic, when on envoie un message au Harnais, then la requête part avec la nouvelle clé, sans redémarrage ni rechargement du modèle.
- Given la page Harnais ouverte, when une clé est enregistrée au Diagnostic, then elle relit `/api/diagnostic` (le sélecteur de modèles montre le nouvel état `key_set`).
- Given une clé changée, when le texte d'une erreur du fournisseur contient l'ancienne ou la nouvelle clé, then aucune des deux n'apparaît dans l'événement.

## Design Notes

`use_key` plutôt qu'un rechargement : la clé n'entre que dans `_headers` et `mask` ; un rechargement passerait par `_load` (libération, événements de chargement, sauvegarde du choix) pour rien et ferait clignoter le Harnais. L'affectation d'attribut est atomique ; la garde de classe (b) écarte déjà toute génération en cours, et le masquage des anciennes clés couvre la course résiduelle (vérification d'état faite hors verrou dans la route).

## Verification

**Commands:**
- `uv run pytest tests/test_cloud.py -q` -- expected: tout vert.
- `uv run ruff check` et `uv run ruff format --check` sur les fichiers Python touchés -- expected: aucun écart.
- `node --check src/wavestack/web/static/app.js` -- expected: syntaxe valide.
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --only diagnostic` -- expected: 15 vérifications réussies, dont « clé enregistrée au diagnostic : « sans relancer », l'atelier relit sa liste de modèles ».

**Manual checks (if no CLI):**
- Recette PC : Diagnostic, changer la clé du modèle cloud actif ; Harnais, sans recharger la page, le message suivant part avec la nouvelle clé.

## Implementation Notes

- Décisions prises à la place d'Anaël (travail en sous-agents parallèles, propriétaire injoignable) : aucune question ouverte ; au point d'arrêt 1, option recommandée « Approuver et continuer » ; implémentation faite directement par l'agent de build, sans sous-agent d'implémentation (machine partagée par trois agents, RAM limitée, tests ciblés seulement).
- Pas d'E2E : aucun scénario existant ne saisit de clé au Diagnostic.
- Après revue (correctifs `patch`) : `mask_key` prend les clés remplacées (`former`) et reste le seul chemin de masquage ; `use_key` garde chaque ancienne clé une fois ; test de masquage renforcé (préfixes distincts, une clé contenant un morceau de l'autre) ; E2E ajouté en fin de scénario `diagnostic` (`_key_applied_at_once` : POST `set_api_key` avec `e2e-fake-key`, la page Harnais relit `/api/diagnostic`) ; doc précisée (la variable d'environnement demande toujours une relance) ; libellé anglais reformulé.
- Fichiers touchés : `src/wavestack/models/cloud_base.py`, `src/wavestack/session/app_session.py` (seulement `use_api_key`, à côté de `_install_cloud`), `src/wavestack/web/app.py`, `src/wavestack/web/static/app.js`, `content/messages.yaml`, `content/i18n/{en,de}/messages.yaml`, `docs/modeles.md`, `tests/test_cloud.py`, `tools/e2e/run_e2e.py`.

## Spec Change Log

## Review Triage Log

Revue du 2026-10-05 : Blind Hunter (B), Edge Case Hunter (E), Verification Gap (V).

| # | Constat | Verdict | Preuve | Suite |
|---|---------|---------|--------|-------|
| B1 | Deux modèles d'un même fournisseur (gemini/gemma) : la clé saisie sur l'un ne touche pas l'autre actif, le message dit « tout de suite » | low | Les clés sont par `id` (`_file_key`) ; l'autre modèle garde sa propre clé enregistrée, comme avant. Message juste pour la ligne saisie | rejeté (peu probable, la correction ajouterait une règle) |
| B2/E4 | Valeur de retour de `use_api_key` ignorée, message inconditionnel | low | Hors course, la clé est effectivement prise tout de suite : par le modèle actif, ou au prochain choix | rejeté |
| B3/E1/E2/E6 | Clé enregistrée pendant le chargement du même modèle cloud : moteur installé avec l'ancienne clé | low | `_diagnostic_class_b` refuse `set_api_key` en `model_load` ; seule une fenêtre de quelques ms entre la garde et le passage en `model_load` (deux requêtes simultanées) l'atteint | rejeté (rare, garde supplémentaire) |
| E3 | Deux `set_api_key` concurrents : moteur et fichier divergent | low | Même fenêtre, deux saisies simultanées du même modèle | rejeté |
| B4 | Propagation dans la couche web, hors de l'applicateur unique | low | Seul `DiagnosticSession.set_api_key` applique `ApiKeySet` ; même schéma que `session.switch(app_session, …)` dans la route | rejeté |
| B5 | `use_api_key` hors `try` : 500 après écriture | false | `config.cloud_key` capte `OSError`/`ValueError` ; `use_key` n'affecte que des attributs | rejeté |
| B6 | `hasattr(engine, "use_key")` silencieux | low | Même idiome que `use_window` dans `_install` | rejeté |
| B7/E5 | `_former_keys` sans dédoublonnage | low | A→B→A empilait les doublons | patch : dédoublonné, clé en cours exclue |
| B8 | `mask` trie à chaque appel | low | Tri de 1 à 3 chaînes par fragment, négligeable | rejeté |
| B9 | Masquage multi-clés dupliquant `mask_key` | low | Deux chemins pouvaient diverger | patch : `mask_key(text, key, former)` seul chemin |
| B10/V1 | Test de masquage : préfixes identiques, `[:4]` non vérifié, ordre non éprouvé | medium | Reproduit par V : sans le terme `[:4]`, le test passait | patch : préfixes distincts, une clé contient la fin de l'autre, toutes les pièces vérifiées |
| V2/B11a | Rafraîchissement du sélecteur (`app.js`) non vérifié | medium | Aucun test front ni E2E | patch : `_key_applied_at_once` dans le scénario E2E `diagnostic` |
| B11b | Doc ambiguë pour la variable d'environnement | low | La phrase précédait le paragraphe `setx` | patch : renvoi explicite |
| B11c | Libellé anglais maladroit | low | Correction directe | patch |
| V3 | Hôte de l'entrée active différent de celui de la saisie | maybe-false | Il faudrait deux `Config` divergents ; `create_app` partage `session.cfg` | rejeté (au plus low) |
| V4 | `set_api_key` hors `hold` : changement pendant un tour juste lancé | low | Couvert par le masquage des anciennes clés | rejeté |
