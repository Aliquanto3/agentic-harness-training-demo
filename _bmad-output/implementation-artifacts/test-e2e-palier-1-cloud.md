# Test de bout en bout du palier 1 avec un faux modèle cloud

- **Date :** 2026-09-26
- **Base testée :** `81dba76` (palier 1, stories 1 à 11b)
- **Environnement :** conteneur Linux sans GPU, sans GGUF, sans accès à Internet hors PyPI (proxy
  de sortie qui refuse les autres hôtes), Chromium 141 sans affichage (Playwright 1.56).
- **Outillage :** `tools/e2e/` (voir `tools/e2e/README.md`). Relance :
  `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` (90 s environ).
- **Résultat :** 133 vérifications réussies, 0 échec, 4 anomalies (A1 à A4), aucune correction du
  code applicatif.

## Méthode

1. `tools/e2e/fake_openai.py` sert `/v1/chat/completions` (flux SSE, `usage` en fin de flux quand
   `stream_options.include_usage` est demandé) et `/v1/models` sur `127.0.0.1`. Les réponses sont
   scriptées et déterministes : elles dépendent du dernier message utilisateur (le texte ajouté par
   H3 est ignoré), des outils proposés et des résultats d'outils déjà reçus dans le tour. Des
   déclencheurs (`[mal-formé]`, `[erreur429]`, `[lent]`…) provoquent les cas d'erreur.
2. `tools/e2e/stack.py` crée un dossier de données temporaire (`WAVESTACK_DATA_DIR`) dont le
   `settings.json` déclare une entrée `[[cloud.models]]` complète, `id = "fake"`,
   `base_url = "http://127.0.0.1:<port>/v1"` (le `http` est admis pour la boucle locale),
   `stream_usage = true`, `tools = true`, `context = 32768`, `key_env = "WAVESTACK_FAKE_API_KEY"`.
   `wavestack.toml` n'est pas modifié. WaveStack est lancé par `python -m wavestack.cli` avec
   `BROWSER=true` (aucun navigateur ouvert) et `HF_HOME`/`OLLAMA_MODELS` dans le dossier
   temporaire (aucun GGUF trouvé).
3. `tools/e2e/run_e2e.py` pilote l'interface avec Playwright : choix du modèle au diagnostic
   comme un utilisateur (« Tester », « Choisir », avertissement, « Utiliser ce modèle »), puis chaque
   scénario. Les assertions portent sur l'interface, sur le journal lu en parallèle sur
   `/api/stream`, et sur les corps de requête reçus par le faux modèle (`/_e2e/requests`).

## Ce qui marche

| Domaine | Vérifié |
|---|---|
| Diagnostic et modèle cloud (11, 11b) | Ligne « Clé fournie par la variable WAVESTACK_FAKE_API_KEY », valeur de la clé absente de la page ; « Tester » réussit (appel d'outil `get_datetime` reçu, réponse, débit) ; avertissement dans la page, nommant le fournisseur ; « actif » après confirmation ; indicateur « RÉSEAU · Faux fournisseur (e2e) » dans la barre haute. Relance : `settings.json` retient `{kind: cloud, ref: fake}`, le modèle est repris sans nouvel avertissement (« choisi lors d'un lancement précédent ») et un tour aboutit. |
| Scénarios (10) | Sélecteur par module, consigne et puces ; une puce remplit le champ sans rien envoyer ; chaque scénario applique ses briques et sous-options ; après rechargement, sélecteur, consigne et prompts réapparaissent ; hors `idle`, sélecteur et « Réinitialiser » désactivés, API en 409 ; scénario inconnu en 404. |
| LLM nu (3) | Corps envoyé : un seul message `user`, aucun outil ; réponse affichée ; Contexte LLM en corps JSON avec bandeau cloud ; un champ `reasoning` du fournisseur s'affiche replié. |
| Mémoire courte (4) | Le prénom revient au second prompt ; brique éteinte, le modèle ne voit plus l'historique. |
| Prompt système, rejeu, Comparer (4, 9b) | Prompt système en tête ; modifié dans le tiroir puis « Rejouer le dernier prompt » : réponse changée, badge « Rejeu », l'historique du rejeu ne contient pas le tour d'origine (AD-17) ; « Comparer » et le badge ouvrent la comparaison. |
| Outils natifs (5) | `get_datetime`, `calculator` (1234 × 5678 = 7006652), `read_file` : appel, exécution, réinjection, réponse finale ; Orchestration montre « Demande d'outil ». |
| Appels mal formés (AD-10) | JSON invalide : `tool_call_malformed`, nouvel essai, tour abouti ; toujours invalide : borne « 3 appels refusés » expliquée dans la Vue humain ; outil inconnu refusé avec la liste des outils ; `tool_use_failed` (400 façon Groq) suit le même chemin. |
| Refus du fournisseur (AD-16) | 429 (« quota dépassé par minute », « Attendez 7 s »), 500, 401 (« Clé refusée… »), erreur au milieu du flux, `finish_reason: length` : message français dans la Vue humain et Orchestration, WaveStack reste utilisable. |
| Outils réseau (5b) | Requête sortante tracée (`outbound_request`, URL exacte) ; l'échec est expliqué : « Service injoignable (ProxyError) : le poste n'a pas accès à calendrier.api.gouv.fr. » (idem Wikipédia) ; le tour se termine. |
| H5, validation humaine (8b, 8c) | Le tour s'arrête avant l'outil réseau ; la carte montre destination et requête exacte ; « Refuser » : rien ne sort ; « Autoriser » : la requête part et son échec est expliqué ; après rechargement la validation en attente réapparaît, active ; « Arrêter » pendant la validation annule (décision `cancelled`, rien ne sort) ; « Autoriser et ne plus demander » décoche H5 dans la carte. |
| MCP (6, 6b) | Serveur local connecté (2 outils), `local__define_term` appelé ; data.gouv.fr : « Service injoignable (ProxyError) : le poste n'a pas accès à mcp.data.gouv.fr. » ; lazy loading : seul `load_tool_doc` est décrit, puis documentation chargée et outil appelé ; « Charger la documentation » forcé au tour suivant. |
| Skills et Caveman (7, 9) | `load_skill` chargé par le modèle, contenu du skill dans le contexte ; Caveman armé (« Déclencher le skill »), puce au-dessus du champ, rejeu : 483 → 83 caractères, comparaison « Sortie : 20 tokens (−100) ». |
| Hooks (8) | H1 bloque `confidentiel/budget_projet.txt` (décision `block`, contenu absent de la réponse) ; H2 écrit le journal d'audit (ligne « appel bloqué par H1 ») ; forçage `read_file` avec le préréglage « Fichier sensible » puis rejeu : bloqué aussi, attribué à l'utilisateur, « Forcé par l'utilisateur » dans Orchestration. |
| Où vont mes données ? | MCP local puis data.gouv.fr activés à la main ; seule l'arête `mcp.datagouv` franchit la frontière, le serveur local reste sur le poste. |
| Déclenchement forcé (9) | Outil sans paramètre armé en un clic, puce qui désarme ; calculatrice avec préréglage « Multiplication » exécutée avant l'appel au modèle, le modèle reçoit 444. |
| Arrêt | « Arrêter » pendant un flux lent : tour `cancelled`, « Arrêté à votre demande ». |
| Réinitialisation (10) | Message « WaveStack réinitialisé : LLM nu. », aucune brique, sélecteur vide, trois volets en « Aucun tour », journal affiché limité à la suite (5 événements), rien à rejouer ; état identique après rechargement. |

## Anomalies

Par gravité décroissante. Chacune est aussi une vérification `KNOWN [Ax]` du script, qui ne fait pas
échouer la séance.

### A1 — Moyenne : un onglet resté ouvert pendant une relance de WaveStack se bloque

**Reproduction.** Ouvrir `/`, envoyer quelques messages, arrêter puis relancer `uv run wavestack`
(ce que demande « Choix enregistré : relancez WaveStack pour l'utiliser. ») sans recharger
l'onglet, puis envoyer un message depuis cet onglet. Le serveur traite le tour (`turn_ended`
émis), mais la Vue humain affiche « Préparation du contexte… » avec un chronomètre qui ne s'arrête
pas, Orchestration montre un tour « en cours », et la réponse n'apparaît jamais. Recharger la
page répare tout (capture `18-onglet-ouvert-apres-relance.jpg`).

**Cause probable.** Le nouveau processus repart d'un journal neuf (`seq` à partir de 1, tours
`t1`, `t2`…), tandis que l'onglet se reconnecte avec le `Last-Event-ID` de l'ancien processus
(plus de 1 000 dans la séance, contre 24 après la relance) : `events_since` ne renvoie rien de ce qui est
plus ancien, et les identifiants de tour déjà connus du store désignent d'anciens tours.
`session_epoch` existe dans l'enveloppe mais le front ne s'en sert pas.

**Fichiers suspects.** `src/wavestack/web/static/app.js` (`streamEvents`, reprise à `lastSeq` ;
`applyEnvelope`, recherche du tour par `turn_id`), `src/wavestack/web/app.py` (`_sse_stream`),
`src/wavestack/trace/journal.py`. Piste : un identifiant de lancement (dans `/api/health` ou dans
chaque enveloppe) ; s'il change, le front recharge la page.

**Impact.** L'animateur qui relance WaveStack pour changer de modèle garde souvent l'ancien onglet :
la démo semble figée. La commande de relance ouvre un nouvel onglet, ce qui limite le risque.

### A2 — Faible à moyenne : la zone Réseau du schéma est rognée de 60 px

**Reproduction.** Scénario « Où vont mes données ? », activer la brique MCP puis data.gouv.fr. À
1 600 × 1 000 comme à 1 366 × 768, `.pane-body-schema` déborde de 60 px (`scrollWidth` 1 356 pour
1 296) : la colonne « Serveurs MCP » de la zone Réseau est coupée au bord droit, le nœud
data.gouv.fr n'y montre que « indisponible » ; les outils réseau (scénario « Outils réseau ») sont
coupés de même. Il faut faire défiler le schéma horizontalement pour voir ce que ce scénario
cherche justement à montrer (captures `15-ou-vont-mes-donnees-schema.jpg`,
`09-h5-validation-humaine.jpg`).

**Fichiers suspects.** `src/wavestack/web/static/app.css` (`.arch-zone-network { flex: 0 1 230px }`,
trop étroite pour le modèle et une colonne de nœuds), rendu de la zone dans `app.js`
(`renderSchema`).

### A3 — Faible : en-tête de Contexte LLM contradictoire en mode cloud

**Reproduction.** Tout tour sur le modèle cloud quand le fournisseur renvoie `usage` : l'en-tête
indique « Tour t1 · 14 tokens envoyés (somme des segments) (total renvoyé par le fournisseur) ».
Le chiffre est le total du fournisseur, pas la somme des segments, et les deux précisions se
suivent. Le tour y est nommé « t1 » alors qu'Orchestration, la comparaison et le rail disent
« Tour 1 ».

**Fichier suspect.** `src/wavestack/web/static/app.js`, `renderContext` (vers la ligne 1429 :
`source` s'ajoute au lieu de remplacer « (somme des segments) » ; `turn.id` au lieu de `turnName`).

### A4 — Faible : le message « WaveStack réinitialisé : LLM nu. » déforme la barre haute

**Reproduction.** Cliquer « ⟲ Réinitialiser » à 1 600 px de large : le message s'insère dans la
barre et comprime les voisins (jauge 220 → 124 px, « Volets ▾ » et « Réinitialiser » passent sur
deux lignes), jusqu'au tour suivant (capture `17-reinitialisation.jpg`).

**Fichiers suspects.** `src/wavestack/web/static/app.css` (`.top-status`, sans largeur bornée ni
`white-space`), `app.js` (`renderScenarioControls`).

### Observations sans gravité

- Hors réseau, le scénario « MCP en documentation complète » n'a qu'un serveur connecté : la jauge
  n'est pas « presque pleine » comme l'annonce la consigne (la consigne prévoit ce cas).
- Les lignes d'audit H2 d'un appel bloqué ne nomment pas l'outil (« appel bloqué par H1 | Bloqué par
  le hook garde-fou : « confidentiel/budget_projet.txt »… ») : le chemin suffit à comprendre.
- Les numéros de tour continuent après « Vider la conversation » ou un lancement de scénario
  (« Tour 29 »), ce qui reste cohérent avec le journal.

## Limites du test

- **Faux modèle.** Il suit un script : il ne dit rien de la qualité des réponses, ni de la capacité
  d'un vrai modèle à appeler les outils, à charger un skill ou à se corriger. Les scénarios passent
  parce que le script appelle l'outil attendu.
- **Boucle locale.** La fabrique réseau ne trace pas les destinations en boucle locale : les appels
  au faux modèle ne produisent pas d'`outbound_request`, donc les « Données sortantes » d'un appel
  au modèle cloud ne sont pas vérifiées (seules celles des outils réseau et de MCP le sont).
- **Spécificités des fournisseurs non couvertes.** `usage` de Groq dans `x_groq`, blocs
  `thinking`/`text` de Mistral, `stream_usage = false` (tokens estimés), paramètres de raisonnement,
  fenêtre bornée par `tpm`, espacement `min_interval_s`, erreurs 413 et contexte dépassé.
- **Modèle local non testé.** Pas de GGUF : chargement llama.cpp, rendu du gabarit, tokens exacts,
  analyse des appels d'outils côté harnais et préfixe réutilisé restent couverts par les seuls
  tests pytest.
- **Réseau.** Sans Internet, les outils réseau, data.gouv.fr et Microsoft Learn ne sont testés que
  sur le chemin d'échec ; le chemin nominal (résultat réel, `fetch_page` coupé, catalogue MCP
  public, débordement de contexte attendu) ne l'est pas. Le proxy du conteneur, en boucle locale,
  est admis par la garde : l'échec vient du proxy (`ProxyError`), pas de la garde.
- **Poste cible.** Linux et Chromium seulement : ni Windows (proxy d'entreprise, `setx`,
  `%LOCALAPPDATA%`), ni Edge, ni l'ouverture automatique du navigateur au lancement.
- **Couverture de l'interface.** Clavier, lecteur d'écran, redimensionnement des volets (8f),
  mode focus, infobulles et popovers d'explication n'ont pas été exercés.

## Captures

`tools/e2e/screenshots/` (15 fichiers JPEG, 2,9 Mo) : diagnostic et avertissement cloud, LLM nu,
prompt système avec rejeu et comparaison, outils natifs et Orchestration, appel mal formé corrigé,
erreur 429, outils réseau en échec expliqué, H5 en attente, MCP complet, lazy loading forcé,
Caveman comparé, H1 bloquant, « Où vont mes données ? », réinitialisation, onglet bloqué après
relance (A1).
