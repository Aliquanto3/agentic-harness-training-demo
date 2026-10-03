---
title: 'R1 : premier calcul du tableau des modèles (models_payload) hors du chemin de /api/diagnostic'
type: 'bugfix'
created: '2026-10-02'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sur le PC pro, le premier `GET /api/diagnostic` qui suit la fin de la recherche des modèles a pris 14,7 s, dont 14,7 s dans `_models` (`catalog.models_payload`), puis 75 ms aux appels suivants (recette du 02/10 au soir, `resultats-test-pc-2026-10-02.md`). Mesure du 02/10 sur ce même PC, avec les vrais modèles (39 candidats, 21 fichiers GGUF distincts, Ollama compris) : `models_payload` prend 5,4 s à froid et 6 ms à chaud, en isolé. Tout le temps est dans `catalog.header_metadata` → `gguf_meta.read_metadata`, qui saute le vocabulaire et les fusions du tokenizer chaîne par chaîne (environ 500 000 lectures et `seek` par fichier, 0,07 à 0,48 s par fichier) ; le cache des en-têtes est en mémoire, froid à chaque lancement. Sous la charge du serveur, le même travail a coûté 14,7 s.

**Approach:** Trois volets, dans cet ordre. 1) Instrumenter `models_payload` : durée de chaque étape (éditeurs, entrées locales, entrées cloud, groupes) et, par candidat, lecture d'en-tête et reste, ajoutées à la ligne de log R1 existante (`debug` sous `SLOW_DIAGNOSTIC_S`, `warning` au-delà) ; reproduire sur ce PC avec le vrai serveur. 2) Accélérer le saut des tableaux de chaînes non gardés (longueurs parcourues dans un tampon lu par blocs, résultat identique), mesuré 3 fois plus rapide (5,1 s → 1,75 s pour les 21 fichiers). 3) Sortir la lecture du chemin de la requête : dès que la recherche connaît ses candidats, un thread de fond lit leurs en-têtes dans le cache du tableau ; les lectures sont sérialisées pour qu'une requête qui arrive pendant le préchauffage attende le fichier en cours au lieu de le relire. Pas de cache sur disque.

</frozen-after-approval>

## Implementation Notes

**Mesures (PC pro, 02/10, vrais modèles : 39 candidats, 21 fichiers GGUF distincts).**

| Où | Avant | Après |
|---|---|---|
| 21 en-têtes, isolé (`gguf_meta.read_metadata`) | 5 086 ms | 1 753 ms (saut par blocs, résultats identiques) |
| `models_payload` isolé, froid / chaud | 5 417 ms / 6 ms | — |
| Vrai serveur (`uv run wavestack` sans navigateur), 1er `/api/diagnostic` après la recherche | 21 009 ms, dont `_models` 20 988 ms et en-têtes 20 893 ms (0,3 à 2,2 s par fichier) | 1 753 ms, dont `_models` 1 368 ms et en-têtes 1 186 ms ; appel suivant 54 ms |

- Avant correctif, deux requêtes concurrentes (n° 16 et 17, dont un onglet Edge resté ouvert sur 8420) relisaient chacune les 21 en-têtes en même temps : chaque fichier coûtait deux fois plus (GIL). C'est l'écart avec les 5,4 s en isolé, et sans doute la raison des 14,7 s de la recette.
- Le reste après correctif (1,2 s) : toutes les sondes étaient en cache, la recherche s'est donc terminée juste après `discover`, et la requête a attendu la fin du préchauffage, sans relire de fichier. Quand des sondes tournent, le préchauffage finit avant elles. La ligne reste en `warning` (≥ `SLOW_DIAGNOSTIC_S`). Un cache des en-têtes sur disque supprimerait ce reste aux lancements suivants : écarté par l'intention, à proposer si besoin.
- Fichiers : `gguf_meta.py` (`_skip_strings`, blocs de `_SKIP_BLOCK` = 1 Mio, mêmes erreurs `GGUFError`) ; `catalog.py` (`PayloadTimings`, `header_path` factorisé depuis `_local_entry`, `_READ_LOCK` dans `header_metadata`, `warm_headers` en thread démon qui journalise toute exception) ; `diagnostic.py` (`_discover` appelle `catalog.warm_headers` juste après `discovery.discover`) ; `app.py` (détail de `_models` entre crochets dans la ligne R1).
- Tests : saut par blocs avec un bloc plus petit qu'une chaîne, coupure dans le vocabulaire, chaîne trop longue (`test_probe.py`) ; `header_path`, préchauffage qui lit chaque fichier une fois, deux threads sur un en-tête froid = une lecture, `PayloadTimings.summary` (`test_model_catalog.py`) ; la recherche appelle `warm_headers` (`test_cli_diagnostic.py`) ; détail de `_models` dans la ligne R1 (`test_web_app.py`).

## Review Triage Log

Relecture Blind Hunter (02/10, 13 constats).

- Temps d'attente du verrou compté dans « en-têtes » — low, réel : la ligne R1 ne distingue pas lecture et attente. Corrigé indirectement : le préchauffage écrit sa propre ligne (`debug`, fichiers et durée), qu'on lit à côté de la ligne R1.
- Le préchauffage ne journalise pas sa fin — medium, réel. Corrigé (ligne `debug`, rien après une exception déjà journalisée).
- Test de concurrence pouvant passer sans verrou — medium, réel (le second thread pouvait arriver après la fin de la lecture). Corrigé : espion sur `_READ_LOCK`, on attend que le second thread y entre avant de libérer la lecture.
- Threads de préchauffage non attendus dans les autres tests — medium, réel (tous les tests qui passent par `_discover`). Corrigé : fixture autouse `_joined_header_warm_up` (`conftest.py`) qui attend la fin du thread.
- Coût du préchauffage pendant la recherche non mesuré — low, rejeté : c'est le même travail que celui que faisait la requête, en 3 fois moins de temps, dans un thread à part ; les sondes tournent dans des processus enfants.
- Chiffre de 21 s sans source — false : mesuré au vrai serveur, consigné dans les Implementation Notes.
- Spec inachevée — false : spec en cours au moment de la relecture ; notes et tri ajoutés.
- Libellés d'étape répétés dans trois fichiers — low, corrigé (constante `LOCAL_STEP`, simple). Les étapes portent les noms des fonctions (`load_publishers`, `local_entries`, `cloud_entries`, `group_models`, `headers`), comme les étapes R1 existantes : un libellé français hors `log.*` faisait échouer `test_no_french_literal_is_left_in_the_perimeter[models/catalog.py]` (suite complète : 1 échec, 5 080 réussis).
- En-tête mis en cache deux fois (`probe._header_kv`) — antérieur, différé (`deferred-work.md`).
- Noms de candidats en double dans la ligne — low, rejeté : deux tags Ollama ont des noms différents, un fichier porte son extension `.gguf`.
- Crochets vides si `_models` échoue avant la première étape — low, corrigé (une condition).
- Cas limites de `_skip_strings` (aucune chaîne, fin pile sur un bloc, fin de fichier) — false : avec `count == 0`, la boucle ne tourne pas et `seek(0)` ; quand `offset == len(buffer)`, `seek(0)` ; quand la fin du fichier tombe après la dernière chaîne, aucune lecture de plus n'a lieu.
- Chemin d'échec de `warm_headers` non testé — low, corrigé (un test : exception journalisée, la requête relit ensuite).
