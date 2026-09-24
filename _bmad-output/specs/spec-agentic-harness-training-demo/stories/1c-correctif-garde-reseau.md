---
title: 'Correctif de la garde réseau (1c) : les IP résolues d''un hôte autorisé passent'
type: 'bugfix'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '1a6472453270e29e02e8dc4c6c83df10fae69a1f'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dans l'application, toute sortie réseau échoue, même vers un hôte autorisé. Le filtre `socket.connect` de la garde (AD-15) compare l'adresse IP obtenue par la résolution DNS à la liste des **noms** d'hôtes autorisés. Il refuse donc toute connexion réelle : reproduit avec la garde installée, `HEAD https://huggingface.co` lève `NetworkBlocked('Adresse réseau non autorisée : 18.155.129.60')` en 0,04 s. Conséquences : le diagnostic affiche « Accès réseau indisponible », et les trois outils réseau de la story 5b ne peuvent rien envoyer. Aucun test ne l'a vu : ceux de la garde s'arrêtent à `getaddrinfo`, et ceux des outils passent par `MockTransport`.

**Approach:** La garde retient les adresses renvoyées par la résolution d'un hôte autorisé (ou de l'hôte du proxy), et le filtre `socket.connect` les accepte. Une IP littérale absente de la liste reste refusée, comme tout hôte non autorisé.

## Boundaries & Constraints

**Always:**
- AD-15 inchangé pour ce qui est refusé : hôte hors liste refusé à `getaddrinfo` ; IP littérale non autorisée refusée à `socket.connect` ; boucle locale et hôte du proxy toujours acceptés ; même garde dans les processus enfants (sonde).
- La garde reste stdlib seule et s'installe avant tout import tiers (`cli`, `probe`).
- Aucun test ne sort du poste : les résolutions sont simulées, et le filtre `connect` est éprouvé par `sys.audit("socket.connect", …)`, sans connexion réelle, dans un sous-processus (la garde de `conftest.py` ne se désinstalle pas).
- Plafond assumé, marqué `ponytail:` : une IP apprise pour un hôte autorisé reste acceptée pour tout le processus (même serveur, CDN partagé compris).

**Never:** pas de liste d'IP dans la configuration ; pas de nouvelle dépendance ; pas de changement de la fabrique `net/factory.py` ni des outils ; pas de travail sur le cache HTTP du navigateur ni sur le cache des échecs de sonde (passe suivante).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Hôte autorisé | `getaddrinfo("fr.wikipedia.org")` → `185.15.58.224`, puis `connect(("185.15.58.224", 443))` | Connexion acceptée | N/A |
| Hôte refusé | `getaddrinfo("example.com")` | `NetworkBlocked` avant résolution ; rien n'est appris | Appelant |
| IP littérale inconnue | `connect(("198.51.100.7", 443))` sans résolution préalable | `NetworkBlocked` | Appelant |
| IP littérale via `getaddrinfo` | `getaddrinfo("198.51.100.7")` | `NetworkBlocked` (hors liste) | Appelant |
| Joker | `getaddrinfo("cdn-lfs.hf.co")` avec `*.hf.co` | Adresses apprises, connexion acceptée | N/A |
| Proxy | Hôte du proxy résolu | Adresses du proxy acceptées | N/A |
| Boucle locale | `connect(("127.0.0.1", 11434))` | Acceptée | N/A |
| IPv6 | Résolution rendant `2001:db8::1` (tuple à 4 éléments) | Acceptée au `connect` | N/A |
| Application réelle | `uv run wavestack` avec réseau | Diagnostic « Accès réseau disponible » ; `public_holidays` rend un résultat | N/A |

</frozen-after-approval>

## Code Map

- `src/wavestack/net/guard.py` -- `install(allowed_hosts)` (L56) : en plus de l'audit hook, envelopper `socket.getaddrinfo` (attribut du module, relu à l'appel par `socket.create_connection` et par `asyncio`) pour ajouter à un ensemble `_resolved` les adresses (`sockaddr[0]`) rendues pour un hôte accepté ; l'audit hook refuse toujours l'hôte non autorisé avant la résolution. Filtre `socket.connect` (L66) : accepter `host in _resolved` en plus de `is_host_allowed`. Garder `is_host_allowed`, `is_loopback`, `_matches`, `_proxy_hosts` tels quels.
- `src/wavestack/cli.py` (L21-24), `src/wavestack/models/probe.py` (L116-119) -- appellent `install` ; aucun changement attendu.
- `tests/test_net_guard.py` -- motifs existants (refus par `getaddrinfo`, Proactor). Ajouter les tests de la matrice dans un sous-processus `sys.executable -c …` : remplacer `socket.getaddrinfo` par un résolveur simulé **avant** `install([...])`, puis appeler `socket.getaddrinfo(...)` et `sys.audit("socket.connect", None, (ip, port))`.
- `tests/conftest.py` -- garde de session limitée à la boucle locale ; ne pas modifier.

## Tasks & Acceptance

**Execution:**
- [x] `src/wavestack/net/guard.py` -- apprendre les adresses résolues des hôtes acceptés ; les accepter au `connect` ; commentaire `ponytail:` sur le plafond -- AD-15
- [x] `tests/test_net_guard.py` -- les 8 lignes de la matrice sans réseau, en sous-processus ; test de non-régression du bogue (résolution d'un hôte autorisé vers une IP publique, puis `connect` accepté)

**Acceptance Criteria:**
- Given la garde installée avec `huggingface.co` autorisé, when une requête HTTPS réelle part vers `huggingface.co`, then elle n'est plus refusée par la garde (vérification manuelle hors pytest).
- Given un hôte ou une IP hors liste, when une connexion est tentée, then `NetworkBlocked` est toujours levée avant tout envoi.

## Implementation Notes

- Implémenté par un sous-agent (dispatch), diff relu dans cette session. `ruff` propre ; `pytest` : 160 passed, 2 deselected. Avec l'ancien `guard.py`, 7 des nouveaux tests échouent, dont le test de non-régression.
- Audit de la matrice : lignes 1 à 8 couvertes par `tests/test_net_guard.py` (sous-processus, résolveur simulé, `sys.audit`), tous exécutés ; ligne 9 vérifiée hors pytest dans cette session, garde installée comme dans `cli` : `huggingface.co` et `calendrier.api.gouv.fr` → 200, `example.com` et `https://1.1.1.1` → `NetworkBlocked`.
- Ajout hors spec : `anyio` (httpx asynchrone) passe l'hôte en `bytes` IDNA ; `check_host` le décode (l'ancien hook avait le même défaut). Test `bytes-host-anyio`.
- Correctifs de revue P1 à P6 appliqués par le même sous-agent (pré-contrôle du wrapper retiré, refus laissé au hook ; résolveur simulé émettant l'événement d'audit ; cas `create_connection` et asyncio avec sentinelle ; décodage `ascii` ; aucun apprentissage pour `host=None` ; contrôle négatif du proxy, registre neutralisé). `pytest` final : 164 passed, 2 deselected ; `ruff` propre. Vérification réelle refaite dans cette session : `huggingface.co` et `fr.wikipedia.org` → 200, `example.com` et `1.1.1.1` → `NetworkBlocked`.
- Vérification manuelle dans l'interface non faite.

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 17 constats) :

- [BH1/BH2/VG2] Le résolveur simulé n'émet pas l'événement d'audit : les refus passent tous par le pré-contrôle du wrapper, la branche `socket.getaddrinfo` du hook n'est plus testée ; en production ce pré-contrôle est redondant et double `getproxies()` — `medium`, confirmé (préambule des tests, hook déclenché par le résolveur C avant résolution). → P1 `patch`.
- [VG1/BH3] Aucun test ne fait passer un vrai appelant (`socket.create_connection`, asyncio) de la résolution au `connect` : le bogue d'origine pourrait revenir, suite verte — `medium`, pré-vérifié. → P2 `patch`.
- [BH5/EC1/VG-o1] `bytes.decode("idna")` : labels `xn--` convertis en Unicode, `UnicodeError` au lieu de `NetworkBlocked` sur des octets invalides — `low`, confirmé ; correction directe. → P3 `patch`.
- [BH6/EC6] `getaddrinfo(None, port)` apprend `0.0.0.0` et `::` — `low`, confirmé ; correction directe. → P4 `patch`.
- [BH7] Docstring d'`install` périmée (remplacement de `socket.getaddrinfo` non mentionné) — `low`, confirmé ; correction directe. → P5 `patch`.
- [BH4] Test du proxy sans contrôle négatif ; sous Windows, `getproxies()` lit le proxy du registre, tests dépendants du poste — `low`, confirmé ; correction directe. → P6 `patch`.
- [EC5] `socket.gethostbyname` et `socket.sendto` non filtrés (résolution ou UDP hors liste) — `medium`, préexistant (AD-15 ne filtre que deux événements). → `defer`.
- [EC2] Hôte en majuscules ou avec point final refusé — `low`, rejeté : préexistant dans `is_host_allowed`, httpx met l'hôte en minuscules, échec fermé.
- [EC3] Forme textuelle différente de l'IP au `connect` (`::ffff:`, majuscules) — `false` : `create_connection` et asyncio se connectent au `sockaddr` rendu par la même résolution.
- [EC4] Résolution par `gethostbyname` ou un résolveur hors `socket` : IP non apprise — `low`, rejeté : échec fermé (connexion refusée), aucun appelant actuel.
- [EC7] IP littérale ouverte par asyncio sous Proactor sans événement `connect` — `false` comme défaut : plafond assumé et écrit dans AD-15.
- [BH-autre] Vérification d'interface non faite, spec non suivie — rejeté : vérification manuelle laissée à l'utilisateur, spec commitée avec le correctif.

Groupes routés en `patch` : P1 à P6 ; `defer` : EC5 ; aucun `intent_gap` ni `bad_spec`.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)
- Hors pytest, garde installée comme dans `cli` : `create_client(timeout=3.0).head("https://huggingface.co")` -- expected: statut HTTP, pas `NetworkBlocked`

**Manual checks (if no CLI):**
- `uv run wavestack` : le diagnostic affiche « Accès réseau disponible » ; activer `public_holidays`, demander les jours fériés 2026 ; le bloc données sortantes et le nœud réseau « disponible » apparaissent.
