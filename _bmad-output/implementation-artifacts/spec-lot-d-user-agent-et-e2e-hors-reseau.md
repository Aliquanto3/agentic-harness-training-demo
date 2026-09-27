---
title: 'Lot D : User-Agent avec contact et parcours E2E sans réseau sortant'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: 'dc193ca72199508b3fe069f1c5420a5f4d247639'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/plan-corrections-palier-2.md'
  - '{project-root}/CLAUDE.md'
  - '{project-root}/tools/e2e/README.md'
warnings: ['multiple-goals']
deferred:
  - summary: >-
      L'environnement réellement passé au processus WaveStack par `running_stack` n'est pas testé hors du parcours complet.
    evidence: |-
      Un test de sous-processus démarrerait trois serveurs ; dans le conteneur, les hôtes publics sont déjà refusés (403) et ne distinguent pas la coupe. Se vérifie par le parcours sur le PC connecté (0 échec attendu).
    location: >-
      tools/e2e/stack.py:running_stack
    severity: low
---

<intent-contract>

## Intent

**Problem:** (D1) Wikipédia répond 403 à `wikipedia_summary` et `fetch_page` : la politique robots de Wikimedia exige un contact dans l'User-Agent, et `WaveStack/0.1 (demonstrateur pedagogique)` n'en a pas ; vérifié à la main, l'URL du dépôt suffit (200). (D2) Le parcours E2E suppose un poste sans Internet : sur le PC cible connecté, 30 vérifications échouent parce que `public_holidays`, data.gouv et Microsoft Learn répondent.

**Approach:** D1 : ajouter l'URL du dépôt à `USER_AGENT` (`WaveStack/0.1 (demonstrateur pedagogique; https://github.com/Aliquanto3/agentic-harness-training-demo)`), avec un test qui exige un contact. D2 : le lanceur E2E coupe lui-même le réseau sortant de l'application qu'il démarre, pour que le parcours donne le même résultat partout, en gardant les vérifications qui attendent une requête sortante tracée puis un échec expliqué.

## Boundaries & Constraints

**Always:** code en anglais, textes en français ; `uv`, `ruff`, `pytest` ; en-têtes HTTP en ASCII ; le parcours E2E garde toutes ses vérifications actuelles (dont « la requête sortante est tracée » et « la requête part » d'H5, qui exigent que la garde réseau laisse passer la requête et qu'elle échoue ensuite) ; seuls le faux serveur, l'application et les faux serveurs locaux (boucle locale) restent joignables ; le résultat est identique sur un poste connecté, derrière un proxy d'entreprise ou hors ligne, sous Linux comme sous Windows.

**Never:** changer `allowed_hosts` de `wavestack.toml` ou la garde réseau de l'application (AD-15) ; retirer ou assouplir une vérification E2E ; toucher au réseau du poste en dehors du processus lancé (pas de pare-feu, pas de droits administrateur).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Wikipédia | Requête sortante de WaveStack | En-tête `User-Agent` avec l'URL du dépôt (contact) | — |
| E2E, poste connecté | Internet joignable | `public_holidays`, data.gouv, Microsoft Learn : requête sortante tracée, puis échec expliqué (service injoignable), comme hors ligne | — |
| E2E, derrière un proxy d'entreprise | `HTTPS_PROXY` du poste posé | Même résultat : le lanceur remplace les variables de proxy du processus lancé | — |
| E2E, boucle locale | Faux serveur OpenAI, faux llama-server et faux Ollama sur 127.0.0.1 | Toujours joignables (contournement du proxy pour la boucle locale) | — |

</intent-contract>

## Code Map

- `src/wavestack/net/factory.py:27-28` -- `USER_AGENT` (commentaire : ASCII), utilisé par `create_client` (l.82, `trust_env=True`), `create_loopback_client` (l.106, `trust_env=False`), `create_async_client` (l.133, `trust_env=True`). `_check_and_trace` : la garde lève `NetworkBlocked` avant `outbound_request` pour un hôte refusé, ce qui interdit de couper le réseau par `allowed_hosts` sans casser les vérifications de trace.
- `src/wavestack/net/guard.py:55-60` -- `is_host_allowed` accepte la boucle locale et l'hôte du proxy.
- `tests/test_net_factory.py:56,108` -- vérifient seulement le préfixe `WaveStack/`.
- `tools/e2e/stack.py` -- `settings()` (l.100-115), `_env(data_dir)` (l.184-196 : copie `os.environ`, donc hérite des proxys du poste), `running_stack` (l.200+ : `free_port()`), `Stack`.
- `tools/e2e/run_e2e.py` -- vérifications qui supposent l'absence d'Internet : l.551-556 (`s_network_tools`), l.599-606 (H5), l.655-660 (`s_mcp_full`), l.1004-1009 (`s_data_flows`), l.1183-1201 (`_public_server_offline`, `iam` l.1222, `sovereignty` l.1245), l.1224-1232 ; l.551 et l.601 exigent une requête tracée.
- `tools/e2e/README.md` -- prérequis et hypothèses du parcours.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- entrées du 2026-09-27 « Wikipédia répond 403 » et « Le parcours E2E suppose un poste sans Internet » (lot D), à fermer.

## Tasks & Acceptance

**Execution:**
- `src/wavestack/net/factory.py` -- `USER_AGENT = "WaveStack/0.1 (demonstrateur pedagogique; https://github.com/Aliquanto3/agentic-harness-training-demo)"`, commentaire qui dit pourquoi (politique robots de Wikimedia : un contact).
- `tests/test_net_factory.py` -- test : l'User-Agent envoyé contient une URL `https://` ou une adresse électronique, et reste ASCII.
- `tools/e2e/stack.py` -- `_env` : pour le processus de WaveStack, `HTTP_PROXY`, `HTTPS_PROXY` et `ALL_PROXY` (et leurs minuscules) pointent vers un port de la boucle locale sur lequel rien n'écoute, `NO_PROXY`/`no_proxy` = `127.0.0.1,localhost,::1` ; les requêtes sortantes passent la garde, sont tracées, puis échouent (proxy injoignable) ; commentaire qui explique le choix (garder la trace des vérifications l.551 et l.601).
- `tools/e2e/README.md` -- le parcours coupe lui-même le réseau sortant (proxy fermé) : même résultat sur un poste connecté, derrière un proxy ou hors ligne.
- `tests/test_e2e_stack.py` (nouveau) -- sans navigateur : l'environnement de `_env` remplace les proxys hérités, contourne la boucle locale, et un client `create_client` construit avec cet environnement échoue sur un hôte public après avoir tracé la requête, sans toucher la boucle locale.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- fermer les deux entrées du lot D.

**Acceptance Criteria:**
- Given un poste connecté à Internet, when `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` tourne, then aucune vérification n'échoue à cause d'un service public qui répond.
- Given une requête vers fr.wikipedia.org, when WaveStack l'envoie, then son User-Agent contient l'URL du dépôt.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 17 findings (constats des quatre couches, doublons regroupés avec leurs sources) — high 0, medium 3, low 8, false 1, maybe-false 5
- findings:
  - `[medium]` `[patch]` Opérateur `_loopback` du lanceur non testé : derrière un proxy sans exception locale, `wait_http` attendrait 60 s (verification-gap) — test ajouté.
  - `[medium]` `[patch]` Test du proxy fermé vacant hors ligne : `ConnectError` avec ou sans proxy (blind) — la preuve du passage par le proxy est exigée.
  - `[medium]` `[patch]` Vérification E2E de `s_network_tools` acceptant n'importe quelle erreur (blind) — « Service injoignable » exigé.
  - `[low]` `[patch]` User-Agent codé en dur sur GitHub alors que le dépôt doit passer sur GitLab (blind) — `[net] contact` configurable, défaut : l'URL du dépôt.
  - `[low]` `[patch]` Test qui répète le chemin littéral du dépôt (blind) — contact configuré vérifié.
  - `[low]` `[patch]` `closed_port` sous Windows sans `SO_EXCLUSIVEADDRUSE` (blind, edge) — ajouté.
  - `[low]` `[patch]` Exploration manuelle privée du vrai réseau (blind) — option `--network`.
  - `[low]` `[patch]` README : Wikipédia et `public_holidays` absents des tests manuels, Windows non vérifié, ligne trop longue (blind) — complété.
  - `[low]` `[patch]` Module de test chargé à la collecte (blind) — chargé dans une fixture.
  - `[low]` `[defer]` Environnement réellement passé au processus lancé par `running_stack` non testé (verification-gap) — il faudrait un test de sous-processus à trois serveurs ; vérifié par le parcours sur le PC connecté.
  - `[maybe-false]` `[reject]` Contact vers un dépôt privé : lien en 404 pour Wikimedia, nom du dépôt exposé (blind) — chaîne vérifiée à la main (200) et demandée par le plan ; désormais configurable ; si vrai : low.
  - `[maybe-false]` `[reject]` Adresse de boucle locale autre que 127.0.0.1/localhost/::1 envoyée au proxy (edge) — le lanceur n'en utilise aucune ; si vrai : low.
  - `[maybe-false]` `[reject]` Client du processus lancé qui ignore les variables de proxy (edge, intent) — les deux clients de la fabrique les suivent (sonde de la couche edge) ; si vrai : medium, visible au parcours sur PC.
  - `[maybe-false]` `[reject]` Mécanisme différent de la parenthèse du plan (`allowed_hosts`) (intent) — `allowed_hosts` casserait les vérifications de trace (la garde lève avant `outbound_request`) ; choix consigné.
  - `[maybe-false]` `[reject]` Entrées fermées alors que la preuve sur PC reste à faire (blind, intent) — consigne de l'utilisateur : fermer ce qui est corrigé, avec « à vérifier sur PC ».
  - `[false]` `[reject]` Le test d'User-Agent ne couvre pas `create_loopback_client` (blind) — ce client ne parle qu'à la boucle locale, jamais à Wikimedia.
  - `[low]` `[reject]` Version `0.1` codée en dur (blind) — hors du lot ; correctif sans lien avec le 403.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucun problème
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- expected: 0 échec (Chromium de `/opt/pw-browsers`)

## Auto Run Result

Status: done

**Résumé.** D1 : l'User-Agent porte un contact (`WaveStack/0.1 (demonstrateur pedagogique; <contact>)`), tiré de `[net] contact` (défaut : l'URL du dépôt, qui fait répondre Wikipédia 200 d'après le test à la main du plan ; réglable pour le passage sur GitLab), vérifié ASCII et sans retour à la ligne. D2 : le lanceur E2E coupe lui-même le réseau sortant de WaveStack en pointant ses variables de proxy vers un port de la boucle locale fermé (et gardé) avec contournement de la boucle locale : la garde laisse passer, la requête est tracée, puis échoue « Service injoignable », sur un poste connecté comme hors ligne ; `allowed_hosts` inchangé (sinon la garde refuserait avant la trace). Les requêtes du lanceur vers la boucle locale ignorent le proxy du poste ; `stack.py --network` garde le vrai réseau pour l'exploration manuelle.

**Fichiers.** `src/wavestack/net/factory.py`, `src/wavestack/config.py`, `wavestack.toml` (`[net] contact`), `tests/test_net_factory.py`, `tools/e2e/stack.py`, `tools/e2e/run_e2e.py`, `tools/e2e/README.md`, `tests/test_e2e_stack.py` (nouveau), `deferred-work.md` (deux entrées fermées).

**Revue.** 9 patchs (3 medium, 6 low), 1 différé (environnement du sous-processus), 7 rejetés (voir le journal). `followup_review_recommended: false`.

**Vérification.** `ruff check`, `ruff format --check` : OK ; `pytest -q` : 868 réussis, 4 sautés ; parcours E2E complet : 327 vérifications réussies, 0 en échec (captures restaurées).

**Risques résiduels (à vérifier sur PC).** Wikipédia 200 avec le nouvel User-Agent ; parcours E2E sur le poste Windows connecté : 0 échec attendu (connexion refusée plus lente sous Windows, 1 à 2 s).
