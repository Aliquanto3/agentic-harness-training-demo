---
title: 'Outils réseau (5b) : jours fériés, Wikipedia, page web, données sortantes'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '8c3e99c6a1627b04da344d4c52cda3949053ed00'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le catalogue d'outils (5a) est entièrement hors ligne : rien ne montre qu'un outil peut faire sortir des données du poste, ni ce qui sort exactement (FR-13, FR-22, NFR-4).

**Approach:** Trois outils réseau dans le registre et l'exécuteur de 5a : `public_holidays`, `wikipedia_summary`, `fetch_page`. La fabrique `net` (AD-15) refuse tout hôte hors liste, trace l'adresse et le corps exact avant l'envoi, revérifie chaque redirection. L'étape d'un outil réseau affiche ses données sortantes ; le schéma montre l'état de contact de chaque outil réseau.

## Boundaries & Constraints

**Always:**
- AD-14 : chaque outil réseau déclare `network=True`, `hosting="network_service"`, et `preview(args) → {method, url, body}`. Son exécution envoie exactement cet aperçu (construit par la même fonction), jamais autre chose.
- AD-15 : `create_client` refuse (`NetworkBlocked`, rien n'est envoyé ni tracé) tout hôte hors `cfg.allowed_hosts` et hors boucle locale ; sinon émet `outbound_request{origin, method, url, body}` avant l'envoi. Les redirections passent par le même contrôle à chaque saut.
- `fetch_page` n'accepte que `https://` vers `[tools] fetch_page_hosts` (défaut `fr.wikipedia.org`, `calendrier.api.gouv.fr`) ; refus avant tout envoi. Page HTML convertie en texte (stdlib), coupée à `fetch_page_max_chars` avec une mention de la coupe.
- État de contact d'un outil réseau (AD-12) : `not_contacted` jusqu'au premier appel envoyé ; puis `available` si le service a répondu (même une erreur HTTP), `unavailable` avec sa raison si la connexion a échoué ou a été refusée. Un refus avant envoi ne change pas l'état.
- AD-16 : toute erreur réseau devient `tool_ended{status: error}` en français, réinjectée ; le tour continue.
- Aucun test ne touche le réseau : `httpx.MockTransport` injecté dans la fabrique, sous la garde de `conftest.py`.
- UX : `hosting-tag-network` « RÉSEAU » sur les sous-options réseau ; `outbound-payload` (en-tête jaune « RÉSEAU », globe, adresse ; corps en code, bordure tirets) ouvert par défaut dans l'étape d'exécution de l'outil ; nœud schéma en zone réseau, « non contacté » visible.

**Décisions (2026-09-24, entrée différée) :** outils réseau désactivés par défaut à l'activation de la brique ; `fetch_page` limité aux hôtes des API ; état de contact selon le dernier appel, sans sonde à l'activation ; à livrer avant la story 6. Repli hors ligne de `fetch_page` (FR-13) reporté à la story sous-agent/compression (décision d'Anaël, 2026-09-24).

**Never:** pas de hook H5 ni d'écart aperçu/envoi affiché (story 8) ; pas de client async ni de MCP (story 6) ; pas de nouvelle dépendance ; le front ne calcule aucun état (AD-1).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Jours fériés | `public_holidays(year=2026)` | GET `calendrier.api.gouv.fr/jours-feries/metropole/2026.json` tracé, liste « date : nom » réinjectée, nœud `available` | N/A |
| Wikipedia | `wikipedia_summary(title="Tour Eiffel")` | GET `fr.wikipedia.org/api/rest_v1/page/summary/Tour_Eiffel`, titre + extrait | 404 : « page absente », nœud `available` |
| Page web | `fetch_page(url="https://fr.wikipedia.org/wiki/Paris")` | Texte sans balises, coupé à la borne avec mention | N/A |
| Hôte refusé | `fetch_page(url="https://example.com")` ou `http://` | Refus en français, aucun `outbound_request`, état inchangé | `tool_ended{error}` |
| Redirection hors liste | 302 vers un hôte non autorisé | Saut refusé, pas de trace pour ce saut | `tool_ended{error}`, nœud `unavailable` |
| Hors ligne | Connexion impossible ou garde | Erreur réinjectée | nœud `unavailable` + raison |
| Désactivé par défaut | Brique activée | Les 3 outils réseau éteints, absents du catalogue du modèle | N/A |
| Hôte hors `allowed_hosts` | Requête de la fabrique | `NetworkBlocked` avant envoi, rien de tracé | Appelant |

</frozen-after-approval>

## Code Map

- `src/wavestack/net/factory.py` -- `create_client(*, timeout, transport=None)` : `transport` pour les tests ; `_trace_request` vérifie `is_host_allowed(host, load_config().allowed_hosts)` (lève `NetworkBlocked`) puis trace avec `body` (`request.content` décodé, `""` si vide). Utilisé aussi par `session/diagnostic.py` et `models/discovery.py` (hôtes déjà autorisés ou boucle locale : comportement inchangé).
- `src/wavestack/net/guard.py` -- réutiliser `is_host_allowed`, `NetworkBlocked` ; ne pas modifier.
- `src/wavestack/trace/catalog.py` -- `OutboundRequestPayload` + `body: str = ""` ; `ArchitectureNode` + `contact: Literal["not_contacted", "available", "unavailable"] | None = None`.
- `src/wavestack/tools/registry.py` -- `ToolSpec` + `preview: Callable[..., dict] | None = None` ; `class Unreachable(ToolError)`.
- `src/wavestack/tools/network.py` (nouveau) -- `network_tools(cfg) -> list[ToolSpec]` (fermetures sur la config) ; `send(preview)` : `create_client()` puis `request(..., follow_redirects=True)` (le hook httpx s'exécute à chaque saut, ce qui revérifie les redirections) ; `httpx.TransportError`/`NetworkBlocked` → `Unreachable` ; statut HTTP ≥ 400 → `ToolError`. HTML → texte par `html.parser.HTMLParser` (ignorer `script`/`style`).
- `src/wavestack/tools/executor.py` -- `run` : pour un outil réseau, `spec.preview(**args)` d'abord (une `ToolError` = refus avant envoi) ; puis `self.contact[name] = ("unavailable", msg)` sur `Unreachable`, `("available", None)` sinon.
- `src/wavestack/session/app_session.py` -- `ToolRegistry(NATIVE_TOOLS + network_tools(self.cfg), …)` (L205) ; L207-208 déjà : réseau éteint par défaut ; `_emit_architecture` (L236) : `contact` et raison pour les nœuds d'outils réseau ; ré-émettre l'architecture après l'exécution d'un outil réseau dans `_turn` (L863).
- `src/wavestack/bricks/registry.py` -- trois `Component` `tools.{name}`, `hosting="network_service"`, `edges_to=["core.harness"]` ; brique `network=True`.
- `src/wavestack/config.py`, `wavestack.toml` -- `[net] allowed_hosts` + `fr.wikipedia.org`, `calendrier.api.gouv.fr` ; `[tools] fetch_page_hosts`, `fetch_page_max_chars = 4000` (propriétés comme `tool_max_calls`).
- `content/tools.yaml` -- libellés et descriptions des trois outils (vus par le modèle).
- `src/wavestack/web/static/app.js` -- réduire `outbound_request` sur la dernière étape `tool` du tour (L181-194) ; `toolCard` (L775) : bloc `outbound-payload` (corps vide : « Aucun corps : seule l'adresse sort du poste ») ; `renderSchema` (L983) : classe `is-not-contacted` + « non contacté » dans le `title`.
- `src/wavestack/web/static/app.css` -- `.hosting-tag-network` (absente aujourd'hui, DESIGN.md L220), `.outbound-payload`, `.arch-node.is-not-contacted`.
- `tests/test_net_factory.py`, `tests/test_tools.py` -- `create_client` monkeypatché avec `MockTransport` ; motifs de session existants (L415).

## Tasks & Acceptance

**Execution:**
- [x] `net/factory.py`, `trace/catalog.py`, `tests/test_net_factory.py` -- refus hors liste, `body`, `transport`, redirection revérifiée -- AD-15
- [x] `tools/registry.py`, `tools/network.py`, `tools/executor.py`, `content/tools.yaml`, `config.py`, `wavestack.toml` -- trois outils, aperçu, état de contact -- AD-14, AD-19
- [x] `bricks/registry.py`, `session/app_session.py` -- composants réseau, nœuds et `contact`, ré-émission -- AD-12
- [x] `web/static/app.js`, `app.css` -- étiquette RÉSEAU, données sortantes, « non contacté » -- AD-1, DESIGN
- [x] `tests/test_tools.py` -- les 8 lignes de la matrice ; aperçu = requête envoyée (méthode, URL, corps) ; conversion HTML et coupe

**Acceptance Criteria:**
- Given `wikipedia_summary` activé, when le modèle l'appelle, then l'étape d'exécution montre en jaune l'adresse exacte appelée et son corps, avant le résultat.
- Given la brique outils activée, when on déplie ses sous-options, then les trois outils réseau portent « RÉSEAU », sont éteints, et le schéma ne les dessine qu'une fois allumés, d'abord « non contacté ».
- Given aucun réseau, when un outil réseau est appelé, then l'erreur est réinjectée, le nœud passe indisponible avec sa raison, et les outils locaux restent utilisables.

## Implementation Notes

- Implémenté par un sous-agent (dispatch), diff relu dans cette session. `ruff check`, `ruff format --check` : propres. `pytest` : 125 passed, 2 deselected (tests `model`).
- Audit de la matrice I/O : les 8 lignes sont couvertes par `tests/test_tools.py` (jours fériés, Wikipedia + 404, page web, hôte refusé ×2, redirection hors liste, hors ligne, désactivé par défaut) et `tests/test_net_factory.py` (refus hors `allowed_hosts`, corps exact, redirection revérifiée), tous exécutés, aucun sauté.
- Choix : User-Agent ASCII (httpx refuse les accents dans les en-têtes) ; `public_holidays` borne l'année à 1900-2100 ; `send` suit les redirections avec `follow_redirects=True`, le hook de la fabrique s'exécutant à chaque saut ; libellé de sous-option « RÉSEAU » ; globe sur l'étiquette et les nœuds réseau.
- Appels réels hors pytest par le sous-agent : API jours fériés, résumé Wikipedia, page absente et `fetch_page` sur Paris conformes. Interface vérifiée par `node --check` seulement ; passe navigateur et vrai modèle non faites.
- Correctifs de revue P1 à P9 appliqués par le même sous-agent (redirections revérifiées par `check_page_url` à chaque saut, extraction HTML par blocs sans `nav`/`header`/`footer`, délai par défaut, casse du type de contenu, `extract` nul, filtre `origin`, émission hors portée, tests d'état de contact et de configuration). `pytest` final : 130 passed, 2 deselected ; `ruff` propre.
- Risques signalés : `fetch_page` sur Wikipedia rend surtout le menu dans ses 4 000 premiers caractères ; une redirection n'est revérifiée que contre `allowed_hosts` (pas `fetch_page_hosts`, ni le schéma https) ; description de `fetch_page` avec les hôtes par défaut en dur ; `create_client` relit la configuration à chaque requête.

## Spec Change Log

## Review Triage Log

Passe 1 (blind-hunter, edge-case-hunter, verification-gap ; 3 couches, 36 constats) :

- [EC1/BH1/EC21/VG-o2] Une redirection n'est revérifiée que contre `allowed_hosts` : `fetch_page` suit un saut https→http ou vers un hôte autorisé hors `fetch_page_hosts` — `medium`, confirmé (`send` : seul le hook de la fabrique à chaque saut). → P1 `patch`.
- [EC13/BH6] `html_to_text` colle les éléments de bloc (`<li>A</li><li>B</li>` → « AB ») et garde `nav`/`header`/`footer` : sur Wikipedia, les 4 000 premiers caractères sont surtout le menu — `medium`, confirmé (rapport d'implémentation, appel réel). → P2 `patch`.
- [EC10/BH7] Arrêt non honoré pendant une requête : 10 s par phase et par saut — `low`, confirmé (`TIMEOUT_S`, contrôle d'annulation seulement avant `run`) ; correction directe (délai par défaut de la fabrique). → P3 `patch`.
- [EC12] `"html" in content-type` sensible à la casse — `low`, confirmé ; correction directe `.lower()`. → P4 `patch`.
- [EC14] `extract: null` rendu « None » — `low`, confirmé (`summary.get('extract', '')`) ; correction directe. → P5 `patch`.
- [EC17/BH8] Toute requête sortante (diagnostic, téléchargement) rattachée à la dernière étape d'outil — `low`, confirmé (`applyEnvelope` ignore `origin`) ; correction directe d'une ligne. → P6 `patch`.
- [EC19] `architecture_changed` émis dans la portée de l'étape d'outil — `low`, confirmé (`_turn`, `scoped(step_id, component)`) ; correction directe (sortir du bloc). → P7 `patch`.
- [VG1] État de contact testé seulement depuis `not_contacted` (retour à `available` après `unavailable`, refus après contact) — `medium`, pré-vérifié. → P8 `patch`.
- [VG2] `fetch_page_hosts` et `fetch_page_max_chars` jamais lus avec des valeurs non par défaut ; plancher non testé — `medium`, pré-vérifié. → P9 `patch`.
- [VG3] Front non vérifié (bloc données sortantes, « non contacté », étiquette RÉSEAU) : aucun banc de test JS — `medium`, pré-vérifié. → `defer`.
- [EC2/BH3/VG-o1] `fetch_page_hosts` hors `allowed_hosts` : aperçu accepté puis refus de la fabrique, nœud `unavailable` — `low`, rejeté : erreur de configuration du développeur, message explicite (« Connexion refusée par le harnais »), garde supplémentaire.
- [EC3/BH3] `fetch_page_hosts` saisi en chaîne → découpé en caractères — `low`, rejeté : même motif que `allowed_hosts` existant, erreur de saisie de configuration.
- [EC4] Joker ou majuscules dans `fetch_page_hosts` — `low`, rejeté : httpx met l'hôte en minuscules ; jokers non prévus, liste par défaut exacte.
- [EC5] Port non 443 sur un hôte autorisé — `low`, rejeté : même hôte autorisé, sans fuite de données ; branche supplémentaire.
- [EC6/BH12] Corps en flux → `RequestNotRead` dans le hook — `low`, rejeté : aucun appelant n'envoie de corps en flux.
- [EC7/EC20] Corps non UTF-8 tracé avec remplacement — `low`, rejeté : aucun outil n'envoie de corps binaire (GET sans corps).
- [EC8/BH2] `load_config()` relu à chaque requête, indépendant de la config injectée ; tests dépendants du `settings.json` réel — `false` pour les tests (`conftest._isolated_data_dir` isole le dossier de données) ; `low` pour le reste, rejeté : en production la session et la garde lisent la même configuration disque (AD-15), coût négligeable, paramètre supplémentaire.
- [EC9] `TooManyRedirects`/`DecodingError` classés « injoignable » — `low`, rejeté : improbable sur les deux API, branche supplémentaire.
- [EC11/BH5] Réponse entière en mémoire avant coupe ; types binaires non filtrés — `low`, rejeté : hôtes limités aux deux API, pages de taille raisonnable.
- [EC15] `{}` de l'API jours fériés → résultat vide `ok` — `low`, rejeté : année hors couverture improbable, garde supplémentaire.
- [EC16] Échec entre aperçu et envoi (truststore) → `available` — `low`, rejeté : improbable, drapeau supplémentaire.
- [EC18] `closedPayloads` croît sans borne — `low`, rejeté : quelques entrées par session.
- [BH4] Description de `fetch_page` avec les hôtes par défaut en dur — `low`, rejeté : ne diverge que si le développeur change la liste ; gabarit supplémentaire.
- [BH9/VG-o3] `network=True` de la brique jamais lu — `false` : champ de déclaration exigé par AD-12 (« besoin de réseau »), pas un défaut.
- [BH10] Nœud réseau sans texte « RÉSEAU », globe emoji lu par les lecteurs d'écran — `low`, rejeté : la zone réseau (jaune, tirets) suffit au schéma selon la spec ; accessibilité du globe mineure.
- [BH11] User-Agent sans contact — `low`, rejeté : accepté par Wikimedia (appels réels réussis), dépôt sans remote pour une URL.
- [BH13] Pas de test 5xx ni de 200 non JSON — `low`, rejeté : erreur enrobée en français par l'exécuteur ; branche 5xx identique au 404 générique testé.

Groupes routés en `patch` : P1 à P9 ; `defer` : VG3 ; aucun `intent_gap` ni `bad_spec`, pas de loopback.

## Design Notes

`public_holidays` : zone métropole seule (paramètre unique `year`, entier). `wikipedia_summary` : `title` encodé (`quote`, espaces → `_`), résultat = titre + `extract`. User-Agent explicite (« WaveStack/0.1 (démonstrateur pédagogique) ») dans la fabrique : Wikimedia refuse les agents génériques.

## Verification

**Commands:**
- `uv run ruff check .` et `uv run ruff format --check .` -- expected: aucune erreur
- `uv run pytest` -- expected: tous les tests passent (tests `model` exclus)

**Manual checks (if no CLI):**
- `uv run wavestack` : activer `public_holidays` et `get_datetime`, demander « quel est le prochain jour férié ? » ; vérifier le bloc données sortantes, le nœud réseau passé de « non contacté » à disponible ; couper le réseau et vérifier l'état indisponible.
