---
title: 'Correctif 1d : pages non mises en cache, échecs de sonde mémorisés'
type: 'bugfix'
created: '2026-09-24'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
baseline_commit: '71ef365efee7f43eab04869f73823ecaaf19df81'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** (1) Le navigateur garde d'anciennes versions de `diagnostic.html`, `index.html` et des fichiers de `/static` (dont `app.js`) après une mise à jour du code : `web/app.py` n'envoie aucun `Cache-Control`. (2) Seules les sondes réussies sont mémorisées dans `settings.json` (`probed_models`). Un GGUF incompatible est donc resondé dans un sous-processus à chaque lancement, soit un chargement complet des poids pour rien.

**Approach:**
- Un middleware HTTP de `create_app` ajoute `Cache-Control: no-cache` à toute réponse hors `/api/`. `no-cache` garde la revalidation (ETag, Last-Modified) : le navigateur reçoit un 304 quand rien n'a changé.
- Un échec de sonde est mémorisé dans une clé distincte `failed_probes` de `settings.json` : chemin → taille, date de modification (mtime), raison, version de `llama-cpp-python`. L'entrée n'est valable que si la taille, la date et la version sont inchangées. Une mise à jour de `llama-cpp-python` relance donc la sonde. Tant que l'entrée est valable, `_discover` marque le fichier incompatible avec la raison mémorisée, sans sous-processus, au lancement comme lors d'un choix explicite.
- Seuls les échecs déterministes sont mémorisés : un refus rendu par la sonde (`ok: false`) ou un plantage du sous-processus. Ne sont pas mémorisés : le dépassement de délai (`TimeoutExpired`), un fichier introuvable, et le cas où `llama-cpp-python` est absent (version illisible). Une sonde réussie efface l'entrée d'échec du fichier.
- Une écriture dans `settings.json` qui échoue passe par `_persist` : l'erreur est tracée, jamais fatale (AD-16).

</frozen-after-approval>

## Implementation Notes

- `web/app.py` : middleware `_revalidate_pages`, `Cache-Control: no-cache` hors `/api/`. Vérifié : `/static/app.js` rend un 304 sur `If-None-Match`. Pour `/` et `/diagnostic`, `FileResponse` renvoie toujours 200 : la page reste fraîche, mais sans 304. C'est un écart mineur avec l'Intent, sans effet visible.
- `models/probe.py` : `record_failure`, `failed_entry`, clé `failed_probes`, version lue par `importlib.metadata` sans importer `llama_cpp`. `record_success` efface l'échec. `_same_file` est partagé avec `probed_entry`.
- `session/diagnostic.py` : `_discover` consulte `failed_entry` après `probed_entry`. Le « plantage du sous-processus » a été précisé en revue : seul un code de sortie autre que 0 ou 1 (plantage natif du chargement) est mémorisé. Le code 1 (exception Python : config, garde), l'absence de processus et le dépassement de délai ne le sont pas.
- Tests : `test_probe.py` (validité, conditions de non-écriture, effacement), `test_cli_diagnostic.py` (pas de nouvelle sonde, plantage natif ou erreur Python, choix explicite, délai), `test_web_app.py` (en-tête). `ruff` propre ; `pytest` : 172 passed, 2 deselected.

## Review Triage Log

Passe 1 (blind-hunter, 10 constats) :

- Plantage lié à l'environnement mémorisé comme défaut du fichier (`OSError`, sortie vide, code 1) — `medium`, confirmé (exception Python dans l'enfant → code 1). → `patch` : mémorisation limitée aux codes de sortie autres que 0 et 1, avec un test.
- Branche de plantage non testée, choix explicite non testé — `low`, confirmé. → `patch` (tests ajoutés).
- Raison vide `""` mémorisée — `low`, confirmé (message « Fichier introuvable. » affiché à tort). → `patch` : même texte de repli que pour le plantage.
- Double lecture de `settings.json` par candidat — `low`, confirmé ; correction triviale (`failed_entry` seulement dans le `elif`). → `patch`.
- Promesse d'ETag et de 304 non vérifiée — `low`, en partie réel : 304 sur `/static`, 200 sur les pages. La docstring est corrigée ; le test de 304 est rejeté (le comportement voulu, une page fraîche, est tenu).
- `ok: false` dû à un manque de mémoire mémorisé, et aucun moyen de forcer une nouvelle sonde (le choix explicite rend la raison mémorisée) — `maybe-false` / `medium` : il faudrait savoir si un échec d'allocation de llama.cpp au chargement arrive vraiment sur un poste CPU chargé. Le comportement du choix explicite est fixé par l'Intent gelé. → `defer`.
- Délai dépassé jamais mémorisé — `false` : exclusion voulue par l'Intent.
- `failed_probes` jamais purgé — `low`, rejeté : même comportement que `probed_models`, croissance négligeable.
- Story incomplète (notes, statut) — `false` : complétée à la finalisation.
