---
id: SPEC-wavestack-v1-1-vague-2-story-9
status: review
companions:
  - SPEC.md
  - ux/DESIGN.md
  - ux/EXPERIENCE.md
  - stories/1-politique-dautorisation-par-outil-mcp-et-journal-de-securite.md
  - stories/6-finops-cache-compression.md
  - stories/7-finops-subagent-kv-cache.md
---

# Story 9 : barre commune, bouton Dépense (économisé, bilan de séance) et bouton Journal

## Ce qui est livré

- **Backend, économies de la séance** (`models/cloud_base.py`) : le registre global de la
  dépense (`_spend`, déjà `in`/`out`/`calls`/les empreintes) gagne trois totaux courants,
  incrémentés au même instant que le reste (jamais recalculés en relisant le journal) :
  `cache_saved_usd` (le net signé de chaque appel cloud, `cache_savings`, même à 0 sans
  remise déclarée — jamais une fausse économie), `compression_saved_usd` (`saved_usd` de
  chaque passe de compression, seulement quand il est chiffré), `kv_time_saved_s` (le
  KV-cache local d'un appel, `kv_cache_tokens ÷ kv_prompt_per_second`). `record_spend` prend
  trois paramètres optionnels de plus ; `ConsumptionUpdatedPayload` les porte (défaut 0.0).
  `_count_impact` (session/app_session.py) accepte `kv_time_saved_s` et journalise même sans
  empreinte estimée. La compression (`_compress_step`) appelle `record_spend` après son
  `compression_ended` quand `saved_usd` est chiffré.
- **Backend, aperçu du journal de sécurité** : `AppSession.security_journal_preview()`
  (5 derniers événements, newest first, et `denied_count`) exposé dans `GET /api/state`
  (`security_journal_preview`). Un nouveau kind de trace, `security_event`
  (`SecurityEventPayload`), émis par `AppSession._emit_security` à chaque
  `SecurityJournal.record(...)` (politique MCP et garde-fous) : la page qui l'écoute met à
  jour compteur et aperçu sans jamais relire tout le journal.
- **Front, la barre commune** (`web/static/bar.js`, nouveau module, chargé après
  `site-nav.js` par les cinq pages) : les deux boutons et leurs panneaux (bar-button,
  bar-flyout de `ux/DESIGN.md`), même HTML statique sur `index.html`, `llm.html`, `rag.html`,
  `mcp.html` et `diagnostic.html`.
  - « Dépense » : masqué avant tout appel payant ou à empreinte (comme l'ancienne jauge) ;
    « économisé {montant} » en pastille `accent-soft`/`ink`. Son panneau (« Bilan de la
    séance ») : deux barres (sans optimisation / coût réel, segments entrée/sortie, lien
    « Détail par appel » vers `/`), le pourcentage économisé, la répartition cache/
    compression, le temps évité en local si connu.
  - « Journal » : compteur rouge des refus et blocages de la séance (texte complet pour le
    lecteur d'écran, « Journal, *n* refus ou blocages »), jamais de pastille à 0. Son
    panneau : les 5 derniers événements (motif disclosure-row, chevron + pastille d'état +
    détail déplié avec l'horodatage et la raison déjà localisée), lien « Tout le journal »
    vers `/security` (la page vient en story 10 ; le lien ne casse rien tant qu'elle
    n'existe pas).
  - Non modal, un seul panneau ouvert à la fois, Échap ferme et rend le focus, un clic
    ailleurs ferme aussi (`ux/EXPERIENCE.md`).
  - État : `GET /api/state` au chargement et à chaque ouverture d'un panneau (comme le
    sélecteur de langue de `site-nav.js` sur les quatre pages qu'il ne nourrit pas en
    direct) ; sur l'écran principal, `app.js` relaie en plus les événements
    `consumption_updated` et `security_event` de son propre flux SSE, en O(1), sans jamais
    relire le journal.
- **Textes** : `content/ui.yaml` (+ `i18n/en`, `i18n/de`) — `common.bar.spend.*`,
  `common.bar.log.*`, et le libellé du nouveau kind de trace (`common.log.kinds.security_event`,
  sous `main.log.kinds`).
- **CSS** (`pages.css`, partagé par les cinq pages) : `.bar-button`, `.bar-flyout`,
  `.status-chip` (low/mid/high/off), le motif `.disclosure-row` générique, `.bar-group`
  (regroupe les deux boutons à droite, indépendamment du masquage de « Dépense »).

## Décisions

- **Formule du bilan** : « sans optimisation » = coût réel (`total_usd`, déjà la somme de
  tous les appels cloud de la séance, sous-agent inclus une seule fois) + `cache_saved_usd`
  + `compression_saved_usd`. Jamais de double compte du sous-agent : ces deux économies sont
  déjà les sommes des appels individuels, pas une addition séparée d'un total par tour.
  Pourcentage = économies ÷ sans-optimisation. L'économie affichée sur le bouton est
  bornée à 0 (`Math.max(0, …)`) : un net signé négatif (une séance surtout en écriture de
  cache) ne s'affiche jamais comme une économie négative, mais ne fabrique pas non plus un
  gain inventé.
- **Compteur Journal** : `SecurityJournal.denied_count()` (refus `deny`/`blocked`
  seulement) ; `cancelled`, `masked`, `allow*` n'y entrent pas (déjà la définition de la
  story 1, réutilisée telle quelle, conforme à la consigne « refus et blocages »).
- **`security_event`** est émis à chaque `SecurityJournal.record(...)`, pas relu par
  l'aperçu : la charge porte l'entrée elle-même et le `denied_count` déjà calculé, pour que
  la page qui l'écoute n'ait jamais à parcourir le journal pour se tenir à jour.
- **Mise à jour en direct** limitée à l'écran principal (`app.js`, la scène des flux 1 et 3
  de `ux/EXPERIENCE.md`) : les quatre autres pages affichent l'état lu à l'ouverture du
  panneau, comme le fait déjà `site-nav.js` pour son sélecteur de langue sur ces mêmes
  pages. Les y câbler aussi est un raffinement possible, pas requis par le succès de CAP-9
  (« depuis n'importe quelle page, le bouton Journal montre les 5 derniers événements » —
  vrai dès l'ouverture, pas nécessairement sans un ré-affichage).
- **L'ancienne jauge `#consumption`** (Dépense/Empreinte estimée, écran principal
  seulement) n'est pas retirée : `ux/EXPERIENCE.md` dit qu'elle est « remplacée » par le
  bouton de la barre, mais la retirer casserait une dizaine de repères déjà posés dans
  `tools/e2e/run_e2e.py` (`#consumption`, `#consumption-label`, `#consumption-money`,
  `#consumption-footprint`) par d'autres scénarios (FinOps, GreenOps) hors du périmètre de
  cette story. Reporté : un futur ménage qui retire la jauge et met à jour ces scénarios en
  même temps.
- **Lien « Détail par appel »** renvoie à `/` (l'écran principal, où le détail par appel vit
  dans Orchestration) plutôt qu'à un ancrage précis, qui dépendrait d'un tour en cours.

## Hors périmètre (reste à faire)

- La page `/security` (story 10) : le lien « Tout le journal » y pointe déjà.
- Le câblage en direct du compteur Journal sur `/llm`, `/rag`, `/mcp` et `/diagnostic`
  (aujourd'hui : à l'ouverture du panneau seulement).
- Le retrait de l'ancienne jauge `#consumption` de l'écran principal (voir Décisions).
- Le segment « sous-agent » des barres du bilan (DESIGN.md en prévoit un jeton de couleur) :
  non tenu au niveau de la séance aujourd'hui (seulement par tour, story 7) ; les barres
  montrent entrée/sortie seulement, un chiffre honnête plutôt qu'une part devinée.

## Tests

- `tests/test_cloud_cap.py` :
  `test_the_sessions_economies_sum_across_calls_and_reset` (`cache_saved_usd`,
  `compression_saved_usd`, `kv_time_saved_s` s'additionnent dans `record_spend`/
  `session_spend`, remis à zéro par `reset_spend`).
- `tests/test_compression.py` : `test_chat_mode_sends_the_compressed_reply_with_estimated_tokens`
  étendu : `compression_saved_usd` rejoint le total de la séance (`consumption_updated`).
- `tests/test_reasoning_budget.py` : `test_the_kv_cache_time_saved_joins_the_sessions_running_total`
  (100 tokens ÷ 50/s = 2 s, dans `consumption_updated`).
- `tests/test_mcp_policy_http.py` :
  `test_security_journal_preview_in_api_state_keeps_the_5_most_recent` (7 décisions
  enregistrées, `GET /api/state` renvoie les 5 plus récentes, newest first, et
  `denied_count` à 7).
- Suite existante vérifiée sans régression : `tests/test_mcp_lab_policy.py`,
  `tests/test_mcp_policy_http.py`, `tests/test_guardrails_turn.py`, `tests/test_cloud_cap.py`,
  `tests/test_cloud.py`, `tests/test_compression.py`, `tests/test_reasoning_budget.py`,
  `tests/test_turn.py`, `tests/test_subagent.py`, `tests/test_model_servers.py`,
  `tests/test_web_app.py`, `tests/test_i18n.py`, `tests/test_ui_texts.py` — tous verts.

## E2E à rejouer

- Scénario ajouté : `bar_panels` (ouvre et ferme chaque panneau de la barre sur deux pages,
  Harnais et MCP ; Échap ferme et rend le focus ; « Dépense » testé seulement si un appel a
  laissé une empreinte GreenOps, sinon noté sans faire échouer le scénario). Non lancé par
  le développeur (consigne de l'orchestrateur) :
  `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only bar_panels`.
- À rejouer avec lui, par prudence (zone FinOps et sécurité déjà couverte) :
  `mcp_lab_page`, `gemini_shape`, `priced_estimate` (la barre ne doit rien changer à leurs
  vérifications de `#consumption`).

## Revue

(pas encore de relecture)
