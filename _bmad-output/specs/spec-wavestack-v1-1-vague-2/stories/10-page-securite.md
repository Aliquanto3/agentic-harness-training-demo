---
id: SPEC-wavestack-v1-1-vague-2-story-10
status: review
companions:
  - SPEC.md
  - mcp-tools.md
  - limites-harnais.md
  - ux/DESIGN.md
  - ux/EXPERIENCE.md
  - stories/1-politique-dautorisation-par-outil-mcp-et-journal-de-securite.md
  - stories/9-barre-commune-depense-journal.md
---

# Story 10 : page Sécurité

## Ce qui est livré

- **Page `/security`** (`security.html`, `security.js`), entrée « Sécurité » de la barre
  commune entre MCP et Diagnostic (les six pages partagent de nouveau une barre identique) :
  - **4 cartes-questions** (`security-question-card`) : « Quels outils peuvent écrire ? »
    (compté sur les lignes « écriture » de la matrice, un fait du catalogue, pas la règle du
    moment), « Qui a autorisé quoi ? » (`allow_once` du journal de la séance), « Qu'est-ce qui
    a été bloqué ? » (refus d'outil + blocages de garde-fou de la séance), « Qu'est-ce qui
    n'est pas couvert ? » (nombre de limites, `len()` du contenu). Aucun chiffre figé.
  - **Matrice des risques** (7 lignes de `mcp-tools.md`) : nature et libellé viennent du
    contenu, risque et règle sont lus en direct sur `ToolPolicy` (`MATRIX_ROWS`,
    `src/wavestack/mcp/policy.py`) par un outil représentatif de chaque ligne — jamais une
    valeur dupliquée. Lien « Régler dans MCP » vers `/mcp`.
  - **Contrôles actifs dépliables** (motif disclosure-row) : autorisations des outils locaux
    (répartition autoriser/demander/refuser), les 3 garde-fous (`_guardrails_card`, story 5),
    les hooks (`_hook_options`, story 8), la liste blanche réseau (`cfg.allowed_hosts`) et la
    connexion GitHub (`_github_state`, `github_auth.SCOPE`/`MCP_URL`) — chacun lu sur sa propre
    source existante.
  - **Journal complet** : `GET /api/security_journal` (déjà la route de la story 1),
    téléchargeable en CSV (déjà `GET /api/security_journal.csv`) ; chaque ligne se déplie sur
    place et dit la raison déjà localisée (qui a décidé, ce qui n'est pas parti).
  - **12 limites dépliables** (`limites-harnais.md`, `content/messages.yaml` >
    `security.limits.*`, ordre fixé par `AppSession._LIMIT_IDS`).
  - Mises à jour en direct : `security.js` ouvre `/api/diagnostic/stream` (déjà générique),
    passe chaque enveloppe à `feedBar` (story 9) et, pour `security_event`, ajoute la ligne en
    tête du journal et recalcule en O(1) les deux cartes mobiles (« qui a autorisé »,
    « bloqué ») à partir de compteurs tenus par le flux, jamais une relecture du journal.
- **Libellés lisibles du journal** (report de la story 9) : `AppSession._security_label_text`
  (`guardrails.pii` → « Garde-fou données personnelles », `local__create_path` → « Créer
  fichier ou dossier »), ajouté en `label_text` à `security_journal_entries`,
  `security_journal_preview` et l'événement `security_event` (`SecurityEventPayload`) ;
  `bar.js` (story 9) affiche maintenant `label_text` dans son aperçu, plus le nom technique.
- **Les trois niveaux de refus GitHub** (`mcp-tools.md`) : un refus de la politique WaveStack
  sur un outil GitHub nomme désormais GitHub explicitement (`policy_denied_github`, « …Envoyé
  à GitHub : non. »), lu déplié dans le journal (flux 1, étape 7) ; le refus lecture-seule
  (outil non proposé) et le 403 GitHub restent de la story 3, inchangés.
- **Contenu** : `content/ui.yaml` (+ `i18n/{en,de}`) section `security` (textes statiques de la
  page) et `common.links.security*` ; `content/messages.yaml` (+ `i18n/{en,de}`) section
  `security` (noms d'outils et de garde-fous lisibles, matrice, cartes-questions, 12 limites).

## Décisions

- **Une seule source de données** : la matrice des risques et les contrôles actifs lisent
  `ToolPolicy`, `_guardrails_card`, `_hook_options`, `cfg.allowed_hosts` et `_github_state`
  existants ; rien n'est recopié en dur côté page. Les réglages restent dans MCP (lien) et
  dans la brique Garde-fous (story 5) ; la page Sécurité ne règle rien.
- **Complexité** : `SecurityJournal` gagne trois compteurs O(1) (`allow_once`, `tool_denied`,
  `guardrail_blocked`, même motif que `denied_count` de la story 9) plutôt qu'un parcours du
  journal à chaque appel de `security_state()` ou à chaque événement ; `security.js` ne relit
  jamais le journal entier sur un événement (une ligne ajoutée en tête, des compteurs tenus
  côté page).
- **Les deux cartes mobiles dupliquent leur texte** (`content/ui.yaml` et
  `content/messages.yaml`, `security.questions.*`) : le texte initial vient du serveur
  (`_t`, format correct dans la langue de la séance), celui d'un événement en direct est
  recalculé côté page sans aller-retour serveur. `shortcut` documenté dans `content/ui.yaml` :
  si le texte change, le changer aux deux endroits.
- **GitHub, trois niveaux de refus** : seul le refus par la politique WaveStack (niveau 2)
  avait un texte générique ; il nomme maintenant GitHub explicitement
  (`_policy_denied_key`), conforme à `ux/EXPERIENCE.md` > Voice and Tone (« ce qui n'est pas
  parti »). Les niveaux 1 (lecture seule) et 3 (403 GitHub) restent ceux de la story 3.
- **Risque et nature des lignes de la matrice** ne sont pas des outils vérifiés tous au
  pas-à-pas (la liste des outils réels change avec `X-MCP-Toolsets`) : chaque ligne est
  identifiée par un outil représentatif (`MATRIX_ROWS`, `policy.py`), partageant son risque et
  sa règle avec les autres de sa catégorie (validé dans `mcp-tools.md`).

## Hors périmètre (reste à faire)

- Pas de connexion GitHub réelle dans l'E2E ajouté (OAuth hors de portée d'un scénario
  automatisé) : le refus est injecté sur la route du journal, comme `bar_panels` l'avait fait
  pour `/api/state` (story 9).
- Le compteur « nouveau » sur l'onglet Sécurité de la barre (maquette) : pas de jeton CSS
  existant pour ce badge hors de la brique Garde-fous ; omis, cosmétique seulement.

## Tests

- `tests/test_security_page.py` (nouveau) : `security_state()` calcule les 4 cartes depuis la
  politique et le journal réels (pas de chiffre figé), une ligne d'écriture change avec
  `set_rule` ; `_security_label_text` lisible pour un outil et un garde-fou connus, nom brut
  gardé pour un outil GitHub non nommé ; `security_journal_entries` porte `label_text` ;
  `GET /api/security` répond avec `risk_matrix`, `controls`, `limits` ; le refus GitHub de la
  politique dit « Envoyé à GitHub : non ».
- Suite existante vérifiée sans régression : `tests/test_mcp_policy_http.py`,
  `tests/test_mcp_lab_policy.py`, `tests/test_mcp_github.py`, `tests/test_ui_texts.py`,
  `tests/test_i18n.py`, `tests/test_web_app.py` — tous verts.

## E2E à rejouer

- Scénario ajouté : `security_page` (flux 1, étapes 7-8 : un refus de fusion GitHub injecté
  sur `/api/security_journal`, la ligne dépliée dit « Envoyé à GitHub : non », le CSV se
  télécharge). Non lancé par le développeur (consigne de l'orchestrateur) :
  `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py --channel msedge --only security_page`.
- À rejouer avec lui, par prudence (barre commune et libellés du journal touchés) :
  `bar_panels`, `mcp_lab_page`.

## Revue

Revue Opus du 16/10 (base 39672a2, commit ce73934), avec la liste du second avis. Décisions
ci-dessus corrigées par la revue : la matrice ne lit plus un outil représentatif
(`ToolPolicy.matrix`), les textes des deux cartes mobiles ne sont plus dupliqués (le serveur
les rend dans `security_event`), le 403 GitHub est journalisé (niveau 3).

- HIGH · revue · corrigé — le flux `/api/diagnostic/stream` s'ouvre sans `Last-Event-ID` et rejoue la séance depuis 0 : chaque `security_event` déjà chargé était ajouté une 2e fois au journal et recompté dans les cartes. Chaque entrée porte son rang `n` ; la page ignore `n` ≤ dernier rang affiché.
- HIGH · second avis 1 · corrigé — au-delà de 500 entrées, les cartes recomptaient la fenêtre. `SecurityJournal.counts()` (O(1)) ; `/api/security` et chaque `security_event` portent les compteurs de séance et les deux cartes rendues ; la page ne recompte rien.
- MEDIUM · second avis 2 · corrigé — clés `guardrails.modes.*` absentes de ui.yaml : la puce lit le libellé du mode fourni par `_guardrails_card`, sinon `main.bricks.status.*`, jamais une clé brute.
- MEDIUM · second avis 3 · corrigé — « Autorisations des outils » compte les 5 outils locaux (`define_term` compris).
- MEDIUM · second avis 4 · corrigé — `MATRIX_ROWS` liste les outils de chaque ligne ; `ToolPolicy.matrix()` lit la règle de chacun, plus les outils réglés dans MCP qui relèvent de la ligne, plus la règle par défaut des outils non nommés (réseau, « toute écriture GitHub ») ; « Mixte (selon l'outil) » quand elles divergent.
- MEDIUM · second avis 5 · corrigé — « Quels outils peuvent écrire ? » compte les outils d'écriture (3 nommés et ceux réglés dans MCP) et dit combien sont autorisés, sur demande, refusés, plus « toute autre écriture GitHub est refusée par défaut ».
- MEDIUM · second avis 6 · corrigé — un 401/403 de GitHub (lu sur l'`outbound_response` de la fabrique réseau, le SDK MCP ne garde qu'une erreur JSON-RPC générique) est journalisé `deny`, « Refusé par GitHub (403) … Envoyé à GitHub : oui », compté dans « bloqué » ; test avec un faux serveur 403.
- MEDIUM · second avis 7 · corrigé — aucun événement perdu entre le chargement et le flux : le flux rejoue la séance, le rang `n` déduplique (voir le HIGH ci-dessus).
- MEDIUM · revue · corrigé — `bar.js` affichait encore le nom technique (`entry.name`) contrairement à « Ce qui est livré » : il lit `label_text`.
- LOW · second avis · déjà couvert — texte « Envoyé à GitHub : non » produit par le serveur : `test_github_write_refusal_names_what_did_not_reach_github`.
- LOW · second avis · corrigé — `aria-controls` sur les replis ; cellules CSV commençant par = + - @ tab CR préfixées d'une apostrophe ; liste du DOM bornée à 500 ; guillemets “ ” (en) et „ “ (de) dans les textes de la story.
- LOW · second avis · corrigé — textes dupliqués ui.yaml/messages.yaml : une seule source (messages.yaml, rendus par le serveur).
- LOW · second avis · rejeté — GET `/api/security` qui appelle `poll()`/`access_token()` : même lecture que `GET /api/mcp_lab`, limitée par l'intervalle du device flow et `_RETRY_S` ; sans elle un jeton juste expiré s'afficherait « erreur réseau ».
- Reporté — 403 GitHub réel (compte sans droit) : vérifier avec Anaël que le serveur distant répond bien en HTTP 403 et pas en résultat `isError` ; dans ce cas, le refus n'est pas encore distingué (le texte d'erreur reste dans la Séquence).
- E2E à rejouer : `security_page`, `bar_panels`, `mcp_lab_page`.
