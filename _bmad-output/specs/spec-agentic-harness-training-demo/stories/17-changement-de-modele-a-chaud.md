---
title: 'Changement de modèle à chaud (CAP-34)'
type: 'feature'
created: '2026-09-26'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/specs/spec-agentic-harness-training-demo/stories/11-modeles-cloud-via-api-groq-mistral.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-11b-corrections-test-manuel-story-11.md'
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Une fois un modèle chargé, choisir un autre modèle (fichier ou cloud) ne fait qu'enregistrer le choix : « Choix enregistré : relancez WaveStack pour l'utiliser. » (AD-3, AD-21, story 11b). Le formateur ne peut donc pas montrer, dans la même conversation, le même harnais piloter un autre modèle (CAP-34, FR-32), ni rejouer un prompt sur un autre modèle pour comparer (CAP-7).

**Approach:** `select_model` hors diagnostic devient un changement à chaud, en classe (b) : la session vérifie le budget mémoire (AD-8), libère l'ancien modèle, sonde le GGUF s'il n'a jamais été chargé (AD-7), charge le nouveau, puis réévalue capacités, briques, fenêtre et aperçu, en gardant la conversation. L'interface offre un sélecteur de modèle dans la barre haute (`model-picker`) et un indicateur « Chargement du modèle… » avec chronomètre ; la mention « Prochain lancement » disparaît.

## Boundaries & Constraints

**Always:**
- **Classe (b), AD-3.** `select_model` est accepté en `diagnostic` (démarrage, inchangé) et en `idle`, même quand `idle` porte une raison (chargement raté, serveur seul). Refusé en `turn`, `awaiting_human`, `model_load`, `download`, `reset`, en 409 avec la raison française. Le passage en `model_load` se fait sous le verrou de la session, dans l'appel qui accepte l'intention : deux choix concurrents ne peuvent pas passer tous les deux.
- **Un seul modèle génératif, AD-8, NFR-2.** Tout chargement de modèle (démarrage compris) passe par un `LoadRegistry` à une place générative. Ordre fixe : contrôle du budget, libération (`close()`) de l'ancien, sonde si besoin, chargement du nouveau. Jamais deux modèles génératifs en mémoire, sonde comprise.
- **Budget chiffré.** Refus si `RSS mesuré (psutil, WaveStack et ses enfants) − coût du modèle actif + coût du nouveau > budget` (`[memory] budget_mb = 4096` dans `wavestack.toml`). Coût d'un fichier : `rss_bytes` mémorisé par la sonde, sinon taille du fichier ; plus le cache KV à la fenêtre effective (métadonnées GGUF mémorisées par la sonde, 0 si inconnues) ; plus `[memory] load_margin_mb = 256`. Coût d'un modèle cloud : 0. Un refus est décidé avant toute libération : l'ancien modèle reste actif, rien n'est écrit, `harness_error` est émis et l'intention répond 409 avec le message chiffré (Go, virgule décimale), par exemple : « Changement refusé : Qwen3.5-4B demande environ 3,1 Go ; WaveStack occupe 1,9 Go sans le modèle actif, pour un budget de 4,0 Go. Qwen3.5-2B reste actif. Choisissez un modèle plus petit. »
- **Sonde, AD-7.** Un GGUF jamais sondé avec succès est sondé dans un processus enfant, après la libération de l'ancien modèle. La sonde enregistre désormais aussi `rss_bytes`, `size_label` (`general.size_label`) et les métadonnées du cache KV. Le code de sonde reste unique (celui du diagnostic).
- **Échec après libération, AD-3.** Sonde ou chargement en échec : le modèle précédent est rechargé (retour arrière), avec `harness_error` qui nomme la cause et le retour. Si le retour échoue aussi, la session passe `idle` avec `_LOAD_FAILED_FR`. Le choix n'est mémorisé (`SettingWrite selected_model`) qu'après un changement réussi.
- **Vers un modèle cloud.** Mêmes règles qu'au diagnostic : `acknowledged: true` exigé (avertissement `cloud-warning` confirmé), clé valide pour l'hôte (`config.cloud_key`), sinon 409 avec la raison actuelle. Le modèle local est libéré ; la fenêtre et la réserve cloud s'appliquent (`config.cloud_window`, `entry.reserve`). Le `ratio` d'estimation est tenu par `id` de modèle cloud et survit à un aller-retour (AD-4).
- **Réévaluation, AD-6, AD-9, AD-12.** Après chaque changement (réussi ou retour arrière) : capacités recalculées, `bricks_changed` (disponibilité au point unique `_availability`, `wanted` jamais modifié), `architecture_changed` (`core.model` local ou réseau, nom du modèle), `context_preview` avec la nouvelle fenêtre.
- **Conversation conservée, AD-17.** Historique de la branche, skills et documentations chargés, actions armées, dernier prompt rejouable : inchangés. Le contexte est re-rendu à chaque appel par le gabarit (ou le corps chat) du modèle actif. Un rejeu après changement utilise le nouveau modèle.
- **Trace, AD-2.** Nouveaux `kind` : `model_load_started{model: ActiveModel, phase_label}` et `model_load_ended{model, status: ok|restored|error, duration_ms, reason_fr}`, portée hors tour (`turn_id`, `step_id` nuls), émis aussi par le chargement du démarrage. `turn_started` porte `active_model`. `ActiveModel` gagne `kind: file|cloud` et `ref` (chemin ou `id` cloud) pour marquer le modèle actif dans les listes.
- **Interface, EXPERIENCE.md.** `model-picker` dans la barre haute (après `model-indicator`) : liste « Sur ce poste » (candidats `found`, nom et `size_label` quand connu), « Réseau » (modèles cloud déclarés, désactivés avec `disabled_fr`), dernière entrée « Autre fichier ou clé API… » qui ouvre `/diagnostic`. Le modèle actif est marqué « (actif) » et non choisissable. Désactivé hors `idle` avec la raison. Un choix cloud ouvre l'avertissement `cloud-warning` dans la page (un `<dialog>`, textes de `/api/diagnostic.cloud.models[].warning`), puis envoie `select_model{kind: cloud, ref, acknowledged: true}`. Pendant le chargement : `top-status` et un `working-indicator` en fin de Vue humain affichent « Chargement du modèle {label}… {s} », chronomètre ancré sur le `ts` de `model_load_started` ; composeur, rejeu et vider désactivés (état `model_load`). Dans la Vue humain, une ligne « Modèle : {label} » précède tout tour dont `active_model` diffère du tour précédent ; « Comparer » affiche le modèle de chaque tour.
- **Diagnostic.** « Choisir » (fichier ou cloud) après le chargement déclenche le même changement à chaud et affiche « Chargement de {modèle}… » puis l'état « chargé »/« actif » lu dans la session applicative (source unique du modèle actif). `NEXT_LAUNCH_FR`, `next_launch_fr`, `next_launch` et le bloc `#next-launch` sont supprimés.
- Messages en français construits côté Python (conventions) ; code, identifiants et commentaires en anglais ; `uv`, `ruff`, `pytest`, aucune nouvelle dépendance, aucun test réseau.

**Never:** adaptateurs `llama_server` et `ollama_raw`, ni choix d'un serveur local déjà lancé (story 18) ; téléchargement de modèle (`download_model`) ; réglage de la fenêtre dans l'interface ; interruption d'un chargement en cours (non interruptible, AD-24) ; changement de modèle pendant un tour ou une validation H5 ; re-découverte ou re-sonde de tous les candidats à l'ouverture du sélecteur ; saisie de clé dans la barre haute (reste au diagnostic) ; surveillance de `settings.json` à chaud ; modification du rendu local, du préfixe en ajout seul ou de l'enveloppe des événements.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Local vers local, sondé | `idle`, modèle A chargé, B sondé, budget suffisant | `model_load` → A libéré → B chargé → `model_load_ended{ok}` → `idle` ; briques, schéma, aperçu réémis ; `selected_model = {file, B}` | Aucune |
| GGUF jamais sondé | B inconnu du cache de sonde | A libéré, sonde enfant de B, puis chargement ; sonde mémorisée avec `rss_bytes` | Voir ligne suivante |
| Sonde ou chargement en échec | B incompatible ou erreur de chargement | A rechargé, `model_load_ended{restored}`, B marqué incompatible si la sonde a échoué, choix non mémorisé | `harness_error` (cause + retour) ; si A échoue aussi : `idle` + `_LOAD_FAILED_FR` |
| Budget dépassé | Coût estimé au-delà du budget | 409, message chiffré ; A reste actif, rien libéré ni écrit | `harness_error` |
| Local vers cloud | Entrée avec clé, `acknowledged: true` | Modèle local libéré, adaptateur `openai_chat`, fenêtre cloud, `active_model` réseau | Aucune |
| Cloud sans confirmation ou sans clé | `acknowledged` absent ou `key_set = false` | 409 « avertissement non confirmé » ou raison de clé ; rien ne change | Aucune |
| Cloud vers local | Cloud actif, fichier B | Adaptateur cloud fermé, B chargé ; ratio du modèle cloud gardé pour un retour | Aucune |
| Intention hors `idle` | `turn`, `awaiting_human`, `model_load` | 409 avec la raison ; rien ne change | Aucune |
| Même modèle | `ref` = modèle actif | Aucun rechargement ; réponse « {modèle} est déjà actif. » | Aucune |
| Capacité perdue | A a un parseur d'outils, B non ; brique Outils voulue | Outils indisponible avec sa raison, `wanted` inchangé ; retour à A : de nouveau disponible | Aucune |
| Conversation et rejeu | 2 tours avec A, puis B | Tour suivant : historique des 2 tours rendu par le gabarit de B ; rejeu du dernier prompt joué par B, `turn_started.active_model` = B | Aucune |
| `settings.json` non inscriptible | Écriture en échec | Changement effectif ; message « choix non mémorisé pour les prochains lancements » | `harness_error` |

</intent-contract>

## Code Map

- `src/wavestack/session/app_session.py` -- `boot` (L818) / `_boot` (L822) et `boot_cloud` (L879) / `_boot_cloud` (L883) : à fondre dans un seul chemin de chargement sur le thread de travail (libération, sonde, chargement, retour arrière, `model_load_*`). `_set_state` (L449), `active_model` (L455, ajouter `kind`, `ref`), `_emit_state` (L464). `hold` (L861) : modèle du passage d'état sous verrou et du refus `SendRefused`. `_availability` (L1030), `_emit_bricks` (L732), `_emit_architecture` (L533, `_CORE_MODEL` L116), `_emit_preview` (L1376) : à réémettre après changement. `_start` (L1418) et émission de `turn_started` (L2053) : ajouter `active_model`. `_ratio` (L338, L925, L2797, L2820) : le tenir par `id` cloud. `_refusal_reason` (L1994), `_LOAD_FAILED_FR` (L133). `close` (L794) : ferme le moteur actif.
- `src/wavestack/session/diagnostic.py` -- `NEXT_LAUNCH_FR` (L59), `_next_launch_saved` (L102), `next_launch_fr` (L465) : à supprimer. `_select_model_locked` (L401) : après chargement, ne sonde pas (L404) et remet le fichier choisi à la session applicative au lieu d'enregistrer pour le prochain lancement. `select_cloud` (L560) : même chose côté cloud, refus `Refused` inchangés. `hand_to` (L453) : route vers le changement à chaud quand un modèle est chargé. `_probe_candidate` (L179) : le code de sonde unique, à passer à la session applicative comme fonction (sans importer `web`). `booted_path` / `booted_cloud` et `cloud_rows()["loaded"]` (L553) : l'état « chargé » vient de la session applicative.
- `src/wavestack/models/probe.py` -- `probe_file` (L38) : lire `general.size_label` et les métadonnées KV (`{arch}.block_count`, `{arch}.attention.head_count_kv`, `{arch}.attention.key_length` ou `embedding_length / head_count`) ; `record_success` (L74) : mémoriser `rss_bytes`, `size_label`, `kv_bytes_per_token`. `probed_entry` (L136) les relit.
- `src/wavestack/models/load_registry.py` (nouveau) -- `LoadRegistry(budget_bytes, margin_bytes, rss_fn)` : `check(label, cost_bytes) -> str | None` (message chiffré), `grant(cost_bytes)`, `release()`, `file_cost(path, window) -> int` depuis `probe.probed_entry`. `rss_fn` par défaut : `psutil.Process()` + enfants récursifs ; injectable en test. Si une story antérieure (15 ou 16) a déjà créé ce module, l'étendre au lieu d'en créer un second.
- `src/wavestack/models/discovery.py` -- `ModelCandidate` (L25) : champ `size_label` rempli depuis le cache de sonde, comme `architecture`.
- `src/wavestack/config.py` -- propriétés `memory_budget_bytes` et `load_margin_bytes` (section `[memory]`), à côté de `context_window` (L239).
- `wavestack.toml` -- section `[memory]` commentée en français (`budget_mb = 4096`, `load_margin_mb = 256`).
- `src/wavestack/trace/catalog.py` -- `ActiveModel` (L56) : `kind`, `ref` ; `TurnStartedPayload` (L127) : `active_model` ; payloads et entrées de `PAYLOAD_MODELS` (L447) pour `model_load_started` et `model_load_ended`.
- `src/wavestack/web/app.py` -- `/api/intentions/select_model` (L241) : réponse `{ready, saved, switching, message_fr}` sans `next_launch`, 409 sur refus (budget, état, cloud) ; `/api/diagnostic` (L224) : sans `next_launch_fr`, `loaded_model` tiré de la session applicative ; `_diagnostic_class_b` (L142) reste le filtre d'état, doublé du contrôle atomique côté session.
- `src/wavestack/web/static/index.html` -- barre haute (L12-30) : `<select id="model-picker">` après `#model-indicator` ; `<dialog id="cloud-warning">`.
- `src/wavestack/web/static/app.js` -- `renderModelIndicator` (L1094) : voisin du nouveau `renderModelPicker` (liste tirée de `GET /api/diagnostic`, rechargée au focus du sélecteur) ; reprendre le dialogue d'avertissement de `diagnostic.html` (L161-L320). `renderComposer` (L1226) et `working-indicator` de la Vue humain (L1166-L1172) : état `model_load` et chronomètre sur `model_load_started.ts`. `KIND_LABELS` (L2787) et `eventSummary` (L2833) : libellés des deux nouveaux `kind`. Ligne « Modèle : … » entre tours et modèle par colonne dans « Comparer ».
- `src/wavestack/web/static/app.css` -- styles `model-picker` (jetons de DESIGN.md : `surface-raised`, `ink`, `line`, `rounded.md`) et ligne de changement de modèle.
- `src/wavestack/web/static/diagnostic.html` -- supprimer `#next-launch` (L38, L43, L325-L327) ; message « Chargement de {modèle}… » après « Choisir » ; marques « chargé »/« actif » (L136, L191) depuis la réponse.
- `tests/fake_engine.py` -- `FakeEngine` (L21), `booted_session` (L85) ; `engine_factory=lambda path, n_ctx: …` permet deux moteurs factices de métadonnées différentes. `tests/test_cloud.py` (fabrique cloud factice) et `tests/test_replay.py` : motifs à réutiliser.
- `tests/test_cli_diagnostic.py` L416, L485-L505, L638, L681-L699 et `tests/test_cloud.py` L591-L625 -- assertions « prochain lancement » à réécrire en changement à chaud.
- Documentation : `README.md`, `ARCHITECTURE-SPINE.md` (AD-3 « Choix du modèle », AD-21 « Modèles cloud au diagnostic »), `EXPERIENCE.md` (L125 `model-picker`, L152 fin de `cloud-model-row`), `SPEC.md` (dernière phrase de CAP-43).

## Tasks & Acceptance

**Execution:**
- [ ] `wavestack.toml`, `src/wavestack/config.py` -- section `[memory]` et ses deux propriétés -- budget réglable (AD-8)
- [ ] `src/wavestack/models/probe.py`, `src/wavestack/models/discovery.py` -- `rss_bytes`, `size_label`, `kv_bytes_per_token` mémorisés ; `size_label` sur les candidats -- coût mesuré (AD-7, AD-8), taille affichée (DESIGN.md)
- [ ] `src/wavestack/models/load_registry.py` -- registre à une place générative, coût, contrôle chiffré, `rss_fn` injectable -- AD-8
- [ ] `src/wavestack/trace/catalog.py` -- `model_load_started`, `model_load_ended`, `ActiveModel.kind/ref`, `TurnStartedPayload.active_model` -- AD-2, AD-12
- [ ] `src/wavestack/session/app_session.py` -- chemin de chargement unique (démarrage et changement) : verrou et refus hors `idle`, budget, libération, sonde injectée, chargement, retour arrière, `SettingWrite` après succès, réémission briques/schéma/aperçu, ratio par modèle cloud, `turn_started.active_model` -- AD-3, AD-6, AD-8, AD-9, AD-12, AD-17
- [ ] `src/wavestack/session/diagnostic.py`, `src/wavestack/web/app.py` -- `select_model` fichier et cloud après chargement routés vers le changement à chaud ; suppression de « prochain lancement » ; modèle chargé lu dans la session applicative -- AD-3, AD-21
- [ ] `src/wavestack/web/static/index.html`, `app.js`, `app.css`, `diagnostic.html` -- `model-picker`, `cloud-warning` dans l'application, indicateur « Chargement du modèle… » et chronomètre, composeur désactivé, ligne « Modèle : … », modèle par colonne dans « Comparer », libellés des nouveaux événements, retrait de `#next-launch` -- EXPERIENCE.md
- [ ] `tests/test_model_switch.py` (nouveau) -- une fonction de test par ligne de la matrice, avec deux `FakeEngine`, une fabrique cloud factice, un `rss_fn` et une sonde injectés ; test `LoadRegistry` (coût depuis le cache de sonde, message chiffré à virgule décimale) ; test « jamais deux moteurs ouverts » (le moteur A est fermé avant l'appel à la fabrique de B et avant la sonde)
- [ ] `tests/test_cli_diagnostic.py`, `tests/test_cloud.py`, `tests/test_web_app.py` -- réécrire les tests « prochain lancement » ; `/api/diagnostic` sans `next_launch_fr` ; `select_model` en `turn` → 409 ; `/api/state.active_model` porte `kind` et `ref`
- [ ] `README.md` -- « Changer de modèle » (barre haute ou diagnostic, conversation gardée, budget `[memory]`) et « Modèle par défaut » (Qwen3.5-2B Q4_K_M, GGUF amont unsloth, Apache-2.0, à copier dans le dossier `models/` ; les GGUF `qwen35` d'Ollama ne se chargent pas avec llama-cpp-python 0.3.35)
- [ ] `ARCHITECTURE-SPINE.md`, `EXPERIENCE.md`, `SPEC.md` -- retirer « prochain lancement tant que CAP-34 n'est pas livré » (AD-3, AD-21, `model-picker`, `cloud-model-row`, CAP-43) et décrire le changement à chaud, `model_load_*` dans le catalogue d'AD-2

**Acceptance Criteria:**
- Given un tour terminé avec le modèle A, when je choisis B dans le `model-picker`, then la barre haute et la Vue humain affichent « Chargement du modèle B… » avec un chronomètre, le champ de saisie est désactivé avec la raison, puis l'indicateur de modèle affiche B, la jauge affiche l'aperçu calculé sur la fenêtre de B et mes messages précédents restent affichés.
- Given un modèle cloud déclaré avec clé, when je le choisis dans le `model-picker`, then l'avertissement « Ce modèle tourne hors de votre poste » s'affiche dans la page, et aucun changement n'a lieu avant « Utiliser ce modèle » ; « Annuler » laisse le modèle actif inchangé.
- Given WaveStack lancé avec un modèle chargé, when j'ouvre `/diagnostic` et que je clique « Choisir » sur un autre modèle, then le modèle change sans relance et la page n'affiche jamais « Choix enregistré : relancez WaveStack pour l'utiliser. ».
- Given un changement réussi vers B, when je relance WaveStack, then B est chargé au démarrage sans nouvelle action (et, pour un modèle cloud, sans nouvel avertissement).
- Given un tour en cours, when j'ouvre le `model-picker`, then il est désactivé et son infobulle donne la raison.

## Spec Change Log

## Review Triage Log

## Design Notes

Séquence d'un changement (thread de travail, après acceptation sous verrou) :

```text
select_model(B) ─ idle? ─ budget ok? ─(non)→ 409 chiffré, A actif
  └→ model_load, model_load_started(B)
     A.close(); registry.release()
     [B jamais sondé] sonde enfant ─(échec)→ restaurer A
     B = factory(B) ─(échec)→ restaurer A
     registry.grant(coût B); SettingWrite(selected_model)
     model_load_ended(ok|restored) → idle → bricks_changed, architecture_changed, context_preview
```

Le contrôle du budget précède la libération : c'est la seule façon de tenir à la fois « un seul modèle génératif » (AD-8) et « un rechargement refusé laisse actif le modèle précédent » (AD-3). Une erreur de sonde ou de chargement, elle, n'est connue qu'après la libération : d'où le retour arrière.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)
- `node --check src/wavestack/web/static/app.js` -- expected: aucune erreur de syntaxe

**Manual checks (if no CLI):**
- `uv run wavestack` avec deux GGUF : envoyer un message, changer de modèle depuis la barre haute, vérifier chronomètre, conversation gardée, rejeu joué par le nouveau modèle et modèle affiché par colonne dans « Comparer ».

## Hypothèses à valider

- **« Depuis la configuration »** (CAP-34) : il s'agit de `selected_model` dans `settings.json` et des entrées `[[cloud.models]]`, lus au lancement (déjà livré). Aucune surveillance de `settings.json` à chaud : la convention dit qu'il s'édite WaveStack arrêté.
- **Sélecteur dans la barre haute** : ajouté par cette story (`model-picker` d'EXPERIENCE.md), à côté de `model-indicator`, qui reste le lien vers le diagnostic. La saisie de clé et le chemin libre restent au diagnostic (entrée « Autre fichier ou clé API… »). La liste vient du dernier diagnostic, sans nouvelle découverte à l'ouverture.
- **Taille affichée** (DESIGN.md « 2B ») : `general.size_label` du GGUF, mémorisé par la sonde ; absente tant que le fichier n'a pas été sondé.
- **Ordre budget, libération, sonde** : la sonde d'un GGUF jamais chargé a lieu après la libération de l'ancien modèle, pour ne jamais avoir deux modèles génératifs en mémoire, sonde comprise (NFR-2). Le budget d'un fichier jamais sondé est donc estimé sur sa taille.
- **Retour arrière** : une sonde ou un chargement en échec après libération recharge le modèle précédent (AD-3 : « laisse actifs le modèle et la fenêtre précédents ») ; le choix n'est mémorisé qu'après un succès.
- **Coût estimé** : `rss_bytes` de la sonde (mesuré à `n_ctx = 16`, interpréteur compris) + cache KV `4 × block_count × head_count_kv × head_dim` octets par token (f16, K et V) × fenêtre + marge de 256 Mo ; le coût libéré est celui accordé au modèle actif. Sur-estimation assumée (modèles hybrides comme Qwen3.5).
- **LoadRegistry** : créé ici s'il n'existe pas encore ; les stories 15 et 16 (embedding, reranking), rédigées en parallèle, y ajouteront leurs composants non génératifs.
- **Chronomètre** : ancré sur deux nouveaux `kind` hors tour, `model_load_started` / `model_load_ended` (AD-1, AD-2), émis aussi au démarrage ; ils n'apparaissent pas dans le rail « Préparation du harnais », seulement dans le journal des événements, la barre haute et la Vue humain.
- **Comparaison entre modèles** : `turn_started` porte `active_model`, pour la ligne « Modèle : … » de la Vue humain et l'en-tête des colonnes de « Comparer » ; c'est le cas d'usage principal du rejeu après changement.
- **Réinitialisation** (CAP-41) et « Vider la conversation » ne changent pas de modèle, et sont refusées pendant `model_load`, comme l'arrêt, car un chargement n'est pas interruptible (AD-24).
- **Modèle par défaut de 2B au plus** : le banc de mesure reste différé ; la story documente le modèle recommandé (Qwen3.5-2B Q4_K_M amont, validé au test manuel de la story 9 sur le PC cible) dans le README, sans téléchargement (`download_model` hors périmètre).
- **Serveur local déjà lancé** : toujours listé sans bouton ni entrée choisissable (story 18).
- **Contrôle mémoire du diagnostic** (« le diagnostic affiche la même mesure », AD-8) : inchangé ici ; son seuil fixe (`MEMORY_WARN_MB`) reste à aligner sur le budget dans une story ultérieure.

## Auto Run Result

Status: ready-for-dev
Blocking condition: aucune (arrêt demandé après la planification)
