---
title: 'Choix du modèle au diagnostic (1b) : liste des candidats, choix mémorisé'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '75346a1082ad0c991590f5611d6fdc96a8e87304'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Au démarrage, WaveStack charge d'office le premier modèle trouvé (`first_model_path`), sans choix possible. Avec les 16 modèles Ollama du poste, c'est un `lfm2`, pour lequel la brique Outils est indisponible. Le champ de chemin n'apparaît que si aucun modèle n'est utilisable.

**Approach:** La page de diagnostic liste chaque candidat avec un nom lisible, son architecture et un bouton « Choisir ». Le champ de chemin est toujours visible. Le choix est enregistré dans `settings.json` (`selected_model`) et chargé d'office aux lancements suivants. On reste dans AD-21 (palier 1) : aucun changement de modèle à chaud (CAP-34, palier 2).

## Boundaries & Constraints

**Always:**
- AD-3 : `select_model` reste l'unique intention de choix (classe a). Elle charge exactement le fichier choisi, jamais un autre candidat ; un chemin incompatible ou introuvable n'est ni enregistré ni chargé et renvoie sa raison en français.
- Au démarrage, WaveStack charge le `selected_model` enregistré s'il est encore utilisable. Sinon, il applique la règle de démarrage (décision ci-dessous). Un choix enregistré devenu inutilisable produit un avertissement nommant le fichier.
- Une fois un modèle chargé, un nouveau choix est seulement enregistré, avec le message « pris en compte au prochain lancement » : pas de rechargement.
- Nom lisible : `modèle:étiquette` pour Ollama (tiré du chemin du manifeste), nom de fichier sinon ; architecture tirée du cache de sonde (`probed_models`).
- Les candidats `server` sont listés sans bouton (palier 2), les incompatibles avec leur raison et sans bouton.
- AD-16 : aucune exception ne traverse la session ; une écriture de `settings.json` en échec est tracée en `harness_error` et le modèle se charge quand même.

**Décision (2026-09-24, Anaël) — règle de démarrage :** sans choix enregistré utilisable, un seul fichier utilisable est chargé d'office ; avec plusieurs, le diagnostic s'arrête (`diagnostic_check` `model`, `warn`, bloquant) sur « Plusieurs modèles trouvés : choisissez-en un », et le clic « Choisir » lève le blocage.

**Never:** pas de sélecteur dans la barre haute ni de changement de modèle en cours de session (CAP-34) ; pas de nouveaux emplacements de recherche ; pas de téléchargement ; pas de nouvelle dépendance.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Choix enregistré | `selected_model` utilisable | Chargé au démarrage, sans attente | N/A |
| Choix enregistré disparu | Fichier supprimé | Avertissement nommant le fichier, puis règle de démarrage | N/A |
| Un seul candidat | Un fichier utilisable, aucun choix enregistré | Chargé au démarrage (comportement actuel) | N/A |
| Plusieurs candidats | ≥ 2 fichiers utilisables, aucun choix | Aucun chargement ; « Plusieurs modèles trouvés : choisissez-en un » | Bloquant jusqu'au choix |
| Clic « Choisir » avant chargement | Candidat utilisable | Enregistré, ce fichier chargé, lien « Ouvrir WaveStack » | N/A |
| Chemin saisi valide | GGUF hors emplacements | Sondé, enregistré, chargé | N/A |
| Chemin invalide | Introuvable ou incompatible | Raison affichée ; rien d'enregistré, aucun autre modèle chargé | N/A |
| Choix après chargement | Modèle déjà chargé | Enregistré, message « prochain lancement », aucun rechargement | N/A |
| Écriture impossible | `settings.json` non inscriptible | Modèle chargé, `harness_error` | Tracée |

</frozen-after-approval>

## Code Map

- `src/wavestack/config.py` -- `Config.selected_model` (lu dans la config fusionnée) ; `save_setting(key, value)` : lecture-modification-écriture de `settings_path()`, réutilisée par `probe.record_success` (L73-93) au lieu de son code dupliqué.
- `src/wavestack/models/discovery.py` -- `ModelCandidate` + `name: str | None`, `architecture: str | None` ; `_ollama_candidates` (L58) : `name` depuis `manifest_path.relative_to(manifests_dir)` (`…/library/qwen3.5/9b` → `qwen3.5:9b`). Ordre et emplacements inchangés.
- `src/wavestack/models/probe.py` -- `already_probed` (L96) : exposer l'entrée du cache (architecture) pour remplir `candidate.architecture`.
- `src/wavestack/session/diagnostic.py` -- `DiagnosticSession` : `selected_model_path` initialisé depuis `cfg.selected_model` ; `_check_model_locked` (L182) : règle de démarrage, `DiagnosticResult.model_path` = le fichier à charger (ou `None`) ; `select_model` (L220) : n'accepte que le fichier choisi, enregistre, rend `model_path` ; `booted_path` pour distinguer « avant » et « après chargement ».
- `src/wavestack/cli.py` -- `_run_diagnostic_then_boot` (L111) : `boot(result.model_path)`.
- `src/wavestack/web/app.py` -- `/api/intentions/select_model` (L137) : charge seulement si aucun modèle n'est chargé, sinon renvoie `{saved: true, next_launch: true}` ; `/api/diagnostic` (L127) : `selected_model` et candidats enrichis.
- `src/wavestack/session/app_session.py` -- `first_model_path` (L161) : supprimer si plus appelée.
- `src/wavestack/web/static/diagnostic.html` -- `renderCandidates` : nom, architecture, source, bouton « Choisir » (candidats `found`), repère « choix enregistré » ; `#select-model` toujours visible, libellé neutre.
- `tests/test_cli_diagnostic.py` -- motifs existants (`monkeypatch` de `discovery`, faux `subprocess.run` de sonde, `WAVESTACK_DATA_DIR` isolé par `conftest.py`).

## Tasks & Acceptance

**Execution:**
- [x] `config.py`, `models/probe.py` -- `selected_model`, `save_setting`, architecture du cache -- AD-20
- [x] `models/discovery.py` -- `name`, `architecture` -- AD-7
- [x] `session/diagnostic.py`, `cli.py`, `web/app.py`, `session/app_session.py` -- règle de démarrage, choix exact, enregistrement, « prochain lancement » -- AD-3, AD-16, AD-21
- [x] `web/static/diagnostic.html` -- liste avec boutons, champ toujours visible -- AD-21
- [x] `tests/test_cli_diagnostic.py` -- les 9 lignes de la matrice ; nom Ollama tiré du manifeste

**Acceptance Criteria:**
- Given 16 modèles Ollama détectés, when j'ouvre le diagnostic, then chaque modèle compatible apparaît sous un nom lisible avec son architecture et un bouton « Choisir ».
- Given un modèle choisi puis WaveStack relancé, when le diagnostic se termine, then ce modèle est chargé sans nouvelle action.

## Implementation Notes

- Implémenté par un sous-agent (dispatch), diff relu dans cette session. `ruff` propre ; `pytest` : 141 passed, 2 deselected.
- Audit de la matrice : les 9 lignes sont couvertes par `tests/test_cli_diagnostic.py` (11 nouveaux tests, dont relance et nom Ollama tiré du manifeste), tous exécutés.
- Choix : `DiagnosticResult.model_path`, `saved`, `message_fr` ; `booted_path` marque le fichier remis au chargement ; le chemin explicite n'est pas ajouté s'il figure déjà parmi les candidats ; avertissement « modèle enregistré plus utilisable » porté par le contrôle `model` (catalogue fermé) ; `config.read_settings`/`save_setting` remplacent le code dupliqué de `probe`.
- Lecture seule du dossier Ollama du poste : 25 modèles nommés comme `ollama list`.
- Correctifs de revue P1 à P11 appliqués par le même sous-agent. Écart assumé : chemin collé normalisé par `absolute()` et non `resolve()`, qui suivrait les jonctions (`OLLAMA_MODELS`) et dédoublerait les blobs. `pytest` final : 150 passed, 2 deselected ; `ruff` propre.
- Risques signalés : après un chargement échoué, un nouveau choix n'est enregistré que pour le prochain lancement ; premier diagnostic long (sonde de chaque candidat, puis cache). Vérification manuelle non faite.

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 30 constats) :

- [BH1/EC1] Écriture de `settings.json` en échec : `saved` reste vrai et le message annonce « Choix enregistré » — `low`, confirmé (`_persist` avale l'`OSError`) ; correction directe. → P1 `patch`.
- [BH2/EC4] Plusieurs étiquettes Ollama sur un même blob comptent pour plusieurs fichiers : un seul modèle bloque le démarrage — `low`, confirmé (`files` non dédoublonné) ; correction directe. → P2 `patch`.
- [BH3] Chaque clic « Choisir » resonde tous les candidats non sondés ou en échec (processus enfant, poids complets, jusqu'à 120 s chacun) — `medium`, confirmé (`_select_model_locked` → `_discover`, `probe_file` charge `Llama`). → P3 `patch`.
- [BH4] Après chargement, choisir un autre modèle le sonde : poids d'un second modèle en mémoire à côté du premier — `medium`, confirmé (`probe_file`, cible CPU/RAM). → P4 `patch`.
- [BH5/EC2-part] `booted_path` posé avant le chargement : après un chargement raté, tout nouveau choix n'est enregistré que pour le prochain lancement — `medium`, confirmé ; la spec parle de « modèle chargé », pas de « remis au chargement ». → P5 `patch`.
- [BH7/EC5/EC6] Chemin collé entre guillemets (« Copier en tant que chemin d'accès »), `~` ou relatif : refusé ou enregistré non résolu — `medium`, confirmé ; correction directe (`strip`, `expanduser`, `resolve`, qui normalise aussi la casse sous Windows). → P6 `patch`.
- [BH9/EC13/EC14] Front : aucun verrou pendant une requête (double clic), aucune gestion d'erreur (statut figé) — `low`, confirmé ; correction directe. → P7 `patch`.
- [BH10] La page ne dit pas quel modèle est chargé ; le modèle chargé garde son bouton — `low`, confirmé ; correction directe. → P8 `patch`.
- [BH11/EC15] `renderCheck` insère des chemins par `innerHTML` — `low`, confirmé (noms de fichiers dans `message_fr`) ; correction directe (`textContent`). → P9 `patch`.
- [BH12] `already_probed` n'a plus que des tests pour appelants — `low`, confirmé ; suppression. → P10 `patch`.
- [VG1] Aucun test ne vérifie que `save_setting` garde les autres clés — `medium`, pré-vérifié. → P11 `patch`.
- [VG2] Dédoublonnage du chemin explicite (blob Ollama) non testé — `medium`, pré-vérifié. → P11 `patch`.
- [VG3] Branche « serveur seul » réécrite sans test — `medium`, pré-vérifié. → P11 `patch`.
- [VG5] `_ollama_name` testé seulement pour `library/` — `low`, pré-vérifié. → P11 `patch`.
- [VG4] Démarrage CLI (`boot(result.model_path)`) non testé : fermeture dans `main()` bloqué par uvicorn — `medium`, pré-vérifié. → `defer` (écart déjà consigné pour la story 2).
- [EC2] `select_model` avant que `run()` atteigne `check_model` : double remise — `low`, rejeté : fenêtre de quelques millisecondes avant l'affichage des candidats.
- [EC3] Serveur seul, fichier choisi pendant le contrôle réseau puis `boot(None)` du CLI — `low`, rejeté : fenêtre de 3 s, cas serveur seul sans aucun fichier.
- [BH6] Choix enregistré obsolète jamais effacé, ligne fantôme — `low`, rejeté : l'avertissement répété est le comportement voulu par la spec jusqu'à un nouveau choix.
- [BH8/EC7/EC8/EC9] Écriture non atomique, fichier illisible écrasé, `OSError`/`UnicodeDecodeError` à la lecture — `low`, rejeté : comportement préexistant (`record_success` d'avant), arrêt en pleine écriture improbable.
- [EC10/EC11/EC12] `probed_models` ou une entrée non dictionnaire (édition manuelle) — `low`, rejeté : fichier écrit par la session seule.

Groupes routés en `patch` : P1 à P11 ; `defer` : VG4 ; aucun `intent_gap` ni `bad_spec`.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)

**Manual checks (if no CLI):**
- `uv run wavestack` avec `OLLAMA_MODELS` visible : choisir un Qwen3.5 (`qwen35`), vérifier qu'il se charge et que la brique Outils est disponible ; relancer et vérifier qu'il se recharge seul.
