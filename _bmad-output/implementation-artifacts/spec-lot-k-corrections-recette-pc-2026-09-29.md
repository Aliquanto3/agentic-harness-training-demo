---
title: 'Lot K : corrections issues de la recette sur PC cible du 2026-09-29 (stories 22 à 27, 31 à 34)'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: '23701e33e69fe94ce24d1ee771be54dcda048b67'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/resultats-test-pc-2026-09-29.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La recette sur PC cible du 2026-09-29 (`resultats-test-pc-2026-09-29.md`, anomalies
A1 à A8) relève huit défauts : coût du cache des modèles hybrides annoncé 4 fois trop haut (A2),
puce « · lié » tronquée dans la barre haute (A1), quatre scénarios du lot H sans leur leçon avec
le 2B (A5), aucun conseil quand llama-server est borné sous la fenêtre choisie (A3), sélecteur de
thème faux après « Précédent » (A4), `aria-expanded` figé et « Appliquer » hors de vue (A8),
compte rendu du skill sur le mauvais fichier (A7), bloc d'installation de llama-server cassé
(A6).

**Approach:** Huit corrections, dans l'ordre de la demande, un commit par point, chacune avec un
test automatique qui échouait avant. Base : `origin/claude/lucid-cori-1rkbjf` (story 29
comprise), branche `claude/lot-k-recette-pc`. Comportement du 2B (point 3) : corrigé surtout par
le contenu, vérifié sur PC par des lignes « À vérifier sur PC ».

**Décision (Anaël, 2026-09-29) :** l'action forcée de kind `tool` s'ouvre aux outils MCP d'un
serveur connecté et actif (brique `mcp`) : arguments convertis et vérifiés par le schéma de
l'outil, hooks et données sortantes comme un appel du modèle, définition ajoutée à `tools` en
lazy loading (spine l. 633, FR-42), bouton « Forcer l'appel » par outil dans la carte MCP avec
préréglages (`local__define_term` « MCP », `datagouv__search_datasets` « cybersécurité ») ; les
consignes de Lazy loading et Souveraineté passent à ce secours. Le refus du 2026-09-25 est levé.

## Boundaries & Constraints

**Always:** textes en français, code en anglais ; `uv`, `ruff`, `pytest` ; E2E sans FAIL (ici
sous Windows, polices de Windows, faute de conteneur) ; dossier de données réel jamais touché
(tests et E2E sous `WAVESTACK_DATA_DIR` temporaire) ; décisions par défaut consignées dans les
Implementation Notes.

**Never:** changer AD-17 (un tour non `completed` reste hors de l'historique) : si c'est
souhaitable, écrire la question pour Anaël ; réécrire `settings.json` pour corriger d'anciennes
sondes ; relancer une sonde de tous les modèles.

## I/O & Edge-Case Matrix

| Scénario | Entrée / état | Attendu |
|---|---|---|
| KV hybride | `head_count_kv` entier, `full_attention_interval` 4 (2B : 24 couches, 2 têtes KV, 256 + 256) | 12 288 octets par token ; 4B (32 couches, 4 têtes) : 32 768 |
| KV liste par couche | `head_count_kv` liste (0 pour les couches linéaires) | somme de la liste, intervalle ignoré |
| KV sans intervalle | intervalle absent, 0 ou 1 | toutes les couches (inchangé) |
| Sonde ancienne | entrée `probed_models` à 49 152, en-tête lisible | valeur recalculée depuis l'en-tête à la lecture ; `settings.json` inchangé |
| En-tête illisible | fichier déplacé ou abîmé | valeur enregistrée gardée |
| llama-server court | `-c 4096`, fenêtre choisie 8 192 | conseil `-np 1 -c 8192` au diagnostic ; bouton « Fenêtre 4 096 ▾ », infobulle avec « 8 192 choisi » |
| llama-server large | `-c 32768`, fenêtre 4 096 | conseil existant inchangé |

</frozen-after-approval>

## Code Map

- `src/wavestack/models/probe.py` -- `kv_bytes_per_token` (l. 75-108), `probed_entry` (l. 341),
  `gguf_kv_bytes_per_token` / `_header_kv` (l. 347-364, `lru_cache`, en-tête seul) ;
  `PROBE_VERSION = 2` (le monter ferait resonder tous les modèles et invaliderait `failed_probes`).
- Lecteurs de la valeur sondée : `load_registry.py:140-152` (`file_cost` : `max(rss, taille) + kv ×
  (fenêtre − probe_window) + marge`), `app_session.py:1514` (`_cost`), `app_session.py:2227`
  (`_kv_per_token` → panneau Fenêtre `_window_choice` l. 2233), `diagnostic.py:421`. Tous passent
  par `probed_entry` : y recalculer suffit.
- Tests KV : `tests/test_probe.py` (`HYBRID` l. 282, `write_gguf`), `tests/test_model_switch.py:666`,
  `tests/test_context_window_setting.py:303`.
- `src/wavestack/web/static/app.css` -- `.top-bar` l. 173, `.top-bar > :not(.gauge)` l. 561,
  sélecteur de scénario l. 568 / 3607 / 3877 / 4589, indicateur du modèle l. 573, `model-picker`
  l. 588, `.pane-chips` l. 613-618 (`flex: 0 1000 auto`), `.pane-chips > .pane-chip` l. 620 / 629,
  `.gauge-stack` l. 636 (300 px), `.gauge-figures` l. 706, sélecteur de thème l. 4142-4168
  (`@media (max-width:1400px)`), projection `:root.projection` l. 4563-4590 (`.gauge` en
  `flex-shrink: 1000000` : les chiffres disparaissent), fenêtre l. 3833-3952.
- `src/wavestack/web/static/app.js` -- `renderChips` l. 5571-5607 ; `renderWindowPicker`
  l. 2364 (infobulle de `#window-toggle`) ; `forceButton` l. 1561, `cardForce` l. 1590 (`aria-expanded`
  posé à la construction, pas à l'ouverture), `forceForm` l. 1631, `forceUiChanged` l. 1056.
- `src/wavestack/web/static/theme.js` -- `pageshow` seulement si `persisted` (l. 69) ; pickers
  `index.html:59`, `diagnostic.html:73`, `models.html:117`, `llm.html:19`.
- `src/wavestack/web/static/index.html` -- panneau Fenêtre l. 25-43 ; tiroir de la mémoire
  l. 97-123 (`drawer-head` / `drawer-scroll` / `drawer-foot`, colonne flex, CSS l. 2672-2778 : à
  reprendre).
- `src/wavestack/models/servers.py:888-904` -- `context_warning_fr` (seul cas « trop grand ») ;
  appelant `discovery.py:222` avec la fenêtre configurée ; affichage `diagnostic.py:623` / `792`,
  `diagnostic.html:290-296`. Tests `tests/test_model_servers.py:1332-1408`.
- `content/scenarios.yaml` -- `mcp_lazy` l. 206-228, `skills` l. 230-249, `soc` l. 357-393, `iam`
  l. 395-426, `sovereignty` l. 428-463 ; secours décrits en prose dans `description_fr`.
- `src/wavestack/session/app_session.py` -- `arm` l. 4005 (kind `tool` l. 4010-4029),
  `_consume_armed` l. 6120, `_armed_unavailable` l. 6213, `_tool_options` l. 1283, `Exchange`
  l. 412, AD-17 l. 5452 ; plafond des résultats global `[tools] result_max_tokens = 1200`
  (`wavestack.toml:140`).
- `tests/test_program.py` -- `FIRST_RESULT_ROOM` l. 69, `_verdict` l. 403, test `fits` l. 434-524
  (premier prompt seulement) ; `test_small_model_prompts_name_the_tool_or_skill_and_the_fallback`
  l. 215 (libellés des consignes).
- `content/skills/meeting_minutes/SKILL.md` -- description qui invite à lire `notes_reunion.txt`.
- `_bmad-output/implementation-artifacts/cahier-recette-nuit-2026-09-28.html` -- bloc
  `llama-install` l. 296-302, repli l. 303-308, P5 l. 439-450, N26-6 l. 1171-1178, N26-7
  l. 1183-1192. Story 28 (`ready-for-dev`, non commencée) reprend les mêmes blocs.
- `tools/e2e/run_e2e.py` -- `s_linked_view` l. 1958 (contrôle l. 2278-2301), `s_themes` l. 1628,
  `_bar_fits` l. 1572, `s_context_window` l. 5228, `Run.check` l. 111.

## Tasks & Acceptance

**Execution:**
- [x] 1 · `probe.py` -- si `head_count_kv` est un entier et `{arch}.full_attention_interval` = n > 1,
  couches à cache = `block_count // n` ; la liste par couche reste prioritaire. `probed_entry`
  remplace `kv_bytes_per_token` par la valeur de l'en-tête (`_header_kv`, en cache) quand il est
  lisible. Tests : métadonnées réelles 2B et 4B, entrée ancienne recalculée sans réécriture,
  coût `file_cost` et choix du panneau (8 192 : +48 Mio au lieu de +192).
- [x] 2 · `app.css` -- puce non rétrécissable (normal et projection) ; cèdent d'abord indicateur
  et sélecteur de modèle, chiffres de la jauge, sélecteur de scénario ; sélecteur de thème
  compact jusqu'à 1 600 px en projection ; chiffres de la jauge visibles quand la place le
  permet ; plus de recouvrement de la légende par « 4096 ▾ » à 1 024 px. E2E : puce entière
  (manque ≤ 1 px, 10 px de marge) à 1 280, 1 366, 1 440 et 1 600, normal et projection, légende
  non recouverte, et à 1 024.
- [x] 3a · `app_session.py` (`arm`, `_armed_unavailable`, `_consume_armed`, options de la carte
  MCP), `app.js` (bouton « Forcer l'appel » par outil MCP), `content/mcp.yaml` (préréglages) --
  appel MCP forcé selon la décision ; `test_kind_tool_refuses_an_mcp_tool_and_a_meta_tool` ne
  refuse plus que les méta-outils ; tests d'appel forcé en lazy loading et en documentation
  complète, serveur déconnecté ou brique éteinte (abandon motivé).
- [x] 3b · `content/scenarios.yaml` et tests -- SOC : chronologie « en 8 lignes au plus » ; IAM :
  deux liens cités, « Vider la conversation » entre les prompts dans la consigne ; Lazy et
  Souveraineté : prompts sans « Charge la documentation », secours « Forcer l'appel » de l'outil MCP (décision) ; test
  `fits` étendu à tous les prompts avec historique simulé (échange précédent : prompt, résultat
  borné, réponse à la réserve), IAM compté sans historique. Question AD-17 écrite pour Anaël.
- [x] 4 · `servers.py`, `app.js`, cahier -- conseil `-np 1 -c {fenêtre}` quand le contexte d'un
  emplacement est sous la fenêtre choisie ; infobulle « …, 8 192 choisi » quand configurée ≠
  effective ; N26-6 et N26-7 alignés (bouton sur la fenêtre effective).
- [x] 5 · `theme.js`, `index.html`, `diagnostic.html`, `models.html`, `llm.html` --
  `autocomplete="off"` et relecture de `wavestack.theme` à chaque `pageshow`. E2E : « Sombre »,
  `/diagnostic`, « Clair », `page.go_back()` : sélecteur sur « Clair ».
- [x] 6 · `app.js`, `index.html`, `app.css` -- `aria-expanded` suit l'ouverture du formulaire
  d'action forcée ; panneau Fenêtre en colonne avec pied épinglé « Appliquer » / « Fermer ».
  E2E à 1 280 × 650.
- [x] 7 · `SKILL.md`, `scenarios.yaml` -- ne lire le fichier que si le message ne donne aucune
  note ; prompt « à partir des éléments ci-dessous, sans lire de fichier ». Test sur les textes.
- [x] 8 · cahier (et story 28 dans ses notes) -- lire `/releases?per_page=10`, prendre la
  première release qui porte `llama-b*-bin-win-cpu-x64.zip` ; repli `b11239` gardé. Test : le
  bloc ne contient plus `releases/latest`.
- [x] Fin · Implementation Notes (décisions, « À vérifier sur PC » : geste, attendu, critère) et
  prompt de recette pour le Claude Code du PC, limité aux huit points.

**Acceptance Criteria:**
- Given le 2B sondé avant le lot, when le panneau Fenêtre s'ouvre, then 4 096 annonce 48 Mo,
  8 192 96 Mo, et le 4B à 16 384 sous budget fixe 6 144 Mo n'est plus refusé.
- Given chaque point, when on lance `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest -q` et l'E2E, then tout est vert et le test du point échoue sur le commit
  précédent.

## Implementation Notes

Commits, un par point, sur `claude/lot-k-recette-pc` (base `23701e3`) : `d50c1c4` (1),
`11589ec` (2), `24b261e` (3a), `e1bd196` (3b), `a7e2892` (4), `d8a9757` (5), `cdb50a4` (6),
`ab86ce9` (7), `1297e2b` (8), puis `05e83d8` (suite du point 2, trouvée par l'E2E complet). Chaque test nouveau a été lancé sur le code d'avant son point
(fichiers du commit précédent remis en place le temps du test) : il échouait, sauf
les exceptions notées plus bas (points 3a et 6).

### Décisions prises par défaut

- **Point 1.** `probed_entry` remplace `kv_bytes_per_token` par la valeur de l'en-tête seulement
  quand l'entrée porte déjà la clé (une entrée sans elle reste « à resonder » pour `measured`)
  et que l'en-tête donne une valeur ; sinon la valeur enregistrée reste. `PROBE_VERSION` reste
  à 2. `servers.served_bytes` et `served_kv` (Ollama, llama-server) passent par la même formule
  et sont corrigés du même coup.
- **Point 2.** Seule la puce `.is-linked` (« · lié », ou validation H5 en attente) est non
  rétrécissable : avec trois volets masqués à 1 280 px, trois puces entières ne tiennent pas
  avec le reste (l'E2E complet l'a montré, contrôle « disciplines »). Les puces deviennent des
  éléments de la barre (`display: contents` sur `.pane-chips`). Ordre de repli, par facteurs
  très écartés : indicateur, sélecteur de modèle et nom du scénario (10⁹, jusqu'à leur largeur
  minimale), puis les autres puces (10⁶, ellipse, texte entier en infobulle), puis les chiffres
  de la jauge (1, jamais sous la barre et sa légende : 300 px + écart). Le nom du scénario cède
  donc avec les noms du modèle, avant les chiffres, pour que ceux-ci restent entiers quand la
  place le permet (1 366 px sans puce). Jusqu'à 1 600 px, les noms descendent à 3 à 4 rem ; en
  projection, la barre compacte de moins de 1 400 px (« Projection », « LLM », « Fenêtre » sans
  le mot, sélecteur de thème compact) vaut jusqu'à 1 600 px, et sous 1 400 px les noms
  descendent encore (2 à 2,5 rem) pour garder 10 px de marge à la puce à 1 280. Sous 1 100 px
  (1 280 à 125 %), le titre « WaveStack » disparaît et la puce « · lié » peut céder, en dernier :
  à 1 024 px la barre tient et la légende n'est plus recouverte, la puce peut y être tronquée
  (le critère de la spec à 1 024 ne porte que sur la légende). Mesures Chromium avec la puce
  « · lié » : chiffres entiers ou presque à 1 366, 1 600 et 1 700 px en mode normal, coupés à
  1 280 (ellipse, infobulle) et masqués à 1 440 (les mots de « Fenêtre », « LLM nu » et du
  sélecteur de thème reviennent) ; en projection, coupés sauf à 1 600. Contrôle « disciplines »
  adapté : à 1 280 px avec trois puces, chiffres entiers ou coupés avec leur texte entier en
  infobulle. Le contrôle E2E de la puce la mesure telle quelle puis élargie de 10 px (padding),
  aux quatre largeurs, projection puis normal.
- **Point 3a.** `arm(kind="tool")` accepte un outil MCP dès que la brique MCP a son contenu ;
  seuls les méta-outils (`source = harness`) restent refusés (404). La disponibilité se juge à
  la consommation, comme pour les autres cibles : brique MCP inactive, ou outil ni dans `tools`
  ni dans `loadable` (serveur déconnecté ou décoché) → `action_dropped` motivé. Un argument
  facultatif du schéma laissé vide dans le formulaire n'est pas envoyé. En lazy loading, l'outil
  forcé rejoint `_loaded_docs` (donc `tools` aux tours suivants) et, dans le tour même, sort de
  `loadable` et entre dans `tools` avant le premier appel (`_with_loaded`), en local comme en
  chat : rien n'est encore rendu à ce moment, le préfixe reste en ajout seul. La réponse de
  l'outil reste un `tool_result` borné (`result_max_tokens`), pas une documentation. Carte MCP :
  un bouton « Forcer l'appel · {outil} » par outil de chaque serveur connecté (nom accessible
  « Forcer l'appel : {outil} »), dans les deux modes ; formulaire d'un champ par paramètre du
  schéma, décrit par le serveur, « (facultatif) » sinon requis ; préréglages dans
  `content/mcp.yaml`, clé `call_presets` ; un outil sans paramètre s'arme en un clic.
- **Point 3b.** Souveraineté fait aussi « Vider la conversation » entre ses deux prompts : deux
  résultats de recherche publics (1 200 tokens chacun au plus) ne tiennent pas ensemble à 4 096
  (le test `fits` étendu le montre : 892 × 1,1 + 1 930 + 1 200 > 3 584). La consigne de
  `mcp_full` ne dit plus « un appel MCP ne se force pas » et renvoie au scénario suivant ; celle
  de `mcp_lazy` garde « Charger la documentation » comme variante. Test `fits` : l'échange
  précédent seul (prompt, résultat plafonné à `result_max_tokens`, réponse à la réserve, 40
  tokens de balises) ; résultat estimé par ce que le prompt demande : sous-agent = la réserve,
  glossaire local = réponse mesurée, serveur public = la borne, outil réseau = 400 tokens
  (premier prompt : la borne, comme avant), fichier lu = son contenu entier, fichier confidentiel
  ou déjà lu au prompt précédent = 0. IAM et Souveraineté sont comptés sans historique.
  **Reporté** : seul l'échange précédent est simulé, pas l'historique cumulé. Au pire cas de
  chaque échange, un scénario de plus de deux prompts déborde (`subagent` p4 : 1 326 + 2 267 >
  3 584) alors que ses vraies réponses sont courtes ; un décompte cumulé demande des réponses
  mesurées sur le PC (le test s'appelle désormais
  `test_every_scenario_fits_the_default_window_with_every_prompt`).
- **Point 4.** Conseil au diagnostic quand le contexte d'un emplacement est strictement sous la
  fenêtre choisie : « … relancez-le avec `-np 1 -c {fenêtre}` », toujours avec `-np 1`. Le bouton
  montre la fenêtre effective (comme N26-6) ; infobulle « Fenêtre de contexte : 4 096 tokens,
  bornée à 4 096 par llama-server (-c), 8 192 choisi. ».
- **Point 5.** `pageshow` relit le choix à chaque affichage, bfcache ou non.
- **Point 6.** Le pied « Appliquer » / « Fermer » est épinglé par un conteneur `.window-scroll`
  (le panneau garde sa hauteur maximale, le reste défile). **Exception au « échoue avant »** :
  sous Chromium, `aria-expanded` de « Déléguer au sous-agent » valait déjà `true` formulaire
  ouvert, car la reconstruction du panneau le reposait ; le `false` relevé dans Edge venait
  probablement d'une lecture de l'ancien bouton, avant la reconstruction. Le bouton pose
  désormais l'attribut dès le clic ; le contrôle E2E du panneau Fenêtre, lui, échouait avant.
- **Point 7.** La description du skill (lue dans le catalogue) ne nomme plus
  `notes_reunion.txt` ; le corps ne lit le fichier que si le message ne donne aucune note.
- **Point 8.** Le test lit les documents BMAD et se saute s'ils manquent (archive sans
  `_bmad-output`). Story 28 : procédure des Design Notes corrigée et entrée datée dans son Spec
  Change Log ; son README et son cahier du palier 2, pas encore écrits, doivent reprendre le bloc.

### Question pour Anaël (AD-17, non modifié)

Le tour SOC coupé par la réserve de sortie (`limit`) est sorti de l'historique (AD-17 : seul un
tour `completed` y entre) ; le prompt 2 est alors parti sans la chronologie du prompt 1. Le lot
contourne le cas par le contenu (« en 8 lignes au plus »). Faut-il qu'un tour `limit` dont la
réponse est seulement tronquée par la réserve (`stop_reason` length, sans appel d'outil en
cours) garde sa réponse tronquée dans l'historique, marquée comme telle ? Cela touche AD-17 et
le cache de préfixe ; rien n'est changé sans ta décision.

### À vérifier sur PC (2B, fenêtre 4 096 sauf mention)

| Point | Geste | Attendu | Critère |
|---|---|---|---|
| 1 | Dossier de données jetable avec le `settings.json` réel (2B et 4B sondés avant le lot) ; lancer, ouvrir « Fenêtre ▾ » | 4 096 « 48 Mo », 8 192 « 96 Mo », 16 384 « 192 Mo » ; `settings.json` inchangé (empreinte) | 48 / 96 Mo ; empreinte identique avant et après |
| 1 | Budget fixe 6 144 Mo, 4B chargé, « Fenêtre ▾ » → 16 384 → « Appliquer » | « ✓ Tient », rechargement ; hausse de RSS ≈ 384 Mio annoncés (± 30 %) | pas de refus ; hausse mesurée dans ± 30 % |
| 2 | Chrome et Edge, 1 280, 1 366, 1 440, 1 600 px, normal puis « Mode projection » ; clic sur le nœud Calculatrice, « — » de Contexte LLM | puce « ● + Contexte LLM · lié » entière, barre sur une ligne, « Réinitialiser » entier | « · lié » lisible partout ; aucune commande coupée |
| 2 | 1 280 × 650 à 125 % (zoom réel) | barre sur une ligne, légende de la jauge non recouverte par « 4096 ▾ » | légende lisible en entier |
| 3a | « Lazy loading », prompt 1 ; si réponse de tête : « Afficher les actions forcées », « Forcer l'appel · local__define_term », préréglage « MCP », « Armer », « Rejouer le dernier prompt » | Orchestration : appel forcé (👆), résultat du glossaire ; réponse « Model Context Protocol » | appel `trigger user` ; « Model Context Protocol » dans la réponse |
| 3b | « Métier SOC », prompts 1 puis 2 | prompt 1 `completed` (pas `limit`) ; prompt 2 : lecture bloquée par H1, escalade | tour 1 `completed` ; `hook_decided h1 block` au tour 2 |
| 3b | « Métier IAM », prompt 1, « Vider la conversation », prompt 2 | ≥ 1 appel par prompt, deux liens learn.microsoft.com par réponse, aucun « Contexte dépassé » | liens présents ; pas de `context_overflow` |
| 3b | « Métier Souveraineté », prompt 1 ; secours « Forcer l'appel · datagouv__search_datasets », préréglage « cybersécurité » ; « Vider la conversation » ; prompt 2 (secours mslearn si besoin) | requête sortante vers mcp.data.gouv.fr puis learn.microsoft.com, vrais jeux de données cités | une `outbound_request` par serveur ; aucune réponse inventée |
| 4 | Fenêtre 8 192 enregistrée, llama-server `-np 1 -c 4096`, relancer WaveStack | bouton « Fenêtre 4 096 ▾ », infobulle « …, 8 192 choisi. » ; `/diagnostic` : « relancez-le avec `-np 1 -c 8192` » | texte du conseil présent ; infobulle juste |
| 5 | Chrome et Edge : « Sombre », `/diagnostic`, « Clair », « Précédent » | atelier clair, sélecteur « ☀ Clair » | sélecteur = thème appliqué |
| 6 | Edge, lecteur d'écran ou DevTools : « Sous-agent », « Déléguer au sous-agent » | `aria-expanded="true"` formulaire ouvert, `false` fermé | valeur juste dans l'arbre d'accessibilité |
| 6 | 1 280 × 650, 100 % puis 125 % et 150 %, « Fenêtre ▾ » | « Appliquer » et « Fermer » visibles en pied, les choix défilent au-dessus | boutons visibles sans défiler |
| 7 | « Skills », prompt suggéré | `load_skill`, puis un compte rendu de la réunion du prompt (Paul, Julie, lundi 10 h), sans `read_file` | aucun appel de `read_file` ; ni Alice ni Bruno |
| 8 | Bloc « Installation » de P5 dans un PowerShell 5.1 | `$asset.name` = `llama-bNNNNN-bin-win-cpu-x64.zip`, version affichée | archive trouvée ; `$LASTEXITCODE` 0 |

### Vérification faite ici

Windows 11 (poste de développement, polices de Windows), dossier de données temporaire pour
tous les tests et l'E2E. `uv run ruff check .` et `uv run ruff format --check .` : propres.
`uv run pytest -q` : 1 251 réussis, 3 sautés, 7 désélectionnés (8 min, avant `05e83d8`, qui ne
touche que la CSS et l'E2E ; `test_web_tokens` et `test_web_app` relancés après : 34 réussis).
`uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` sur la tête `05e83d8` :
652 vérifications réussies, 0 en échec ; 5 `harness_error` voulus (429, 500, flux cassé, 401,
téléchargement d'embedding) et 3 erreurs de console attendues (réseau coupé du parcours), comme
dans le rapport de recette. Le test `fits` n'a tourné qu'en estimation (2 caractères par token) :
relancé ensuite en décompte exact avec `WAVESTACK_TEST_GGUF` = le 2B du poste (lecture seule du
GGUF, dossier de données temporaire) : réussi, plus petite marge `mcp_full` p1 380 ; en-têtes
réels lus par `gguf_kv_bytes_per_token` : 2B 12 288, 4B 32 768 octets par token.
« Échoue avant » vérifié point par point : point 1 (4 tests), 2 (E2E, 7 px à 1 280 projection),
3a (non relancé sur l'ancien code : les nouveaux tests arment un outil MCP, que l'ancien
`arm` refusait en 404, échec certain par construction), 3b (`fits` étendu débordait sur
Souveraineté p2 avec l'ancien contenu ; ancien test des consignes en échec), 4 (2 tests), 5 (E2E : sélecteur `dark`), 6
(E2E du panneau, sauf `aria-expanded` : voir plus haut), 7 (test des textes), 8 (2 tests).

Prompt de recette pour le Claude Code du PC :
`_bmad-output/implementation-artifacts/prompt-recette-lot-k-2026-09-29.md`.

### Vérification finale (après la revue, tête `bfe28eb`)

`uv run ruff check .` et `uv run ruff format --check .` : propres. `uv run pytest -q` : 1 253
réussis, 3 sautés. `fits` exact (`WAVESTACK_TEST_GGUF` = le 2B du poste) : réussi. E2E complet
(`PYTHONUTF8=1`, sortie redirigée vers un fichier ; sans cette variable, la console cp1252 lève
`UnicodeEncodeError` et fait échouer la suite en cascade) : 653 vérifications réussies, 0 en
échec. Deux constats reportés dans `deferred-work.md` (contrôle d'`aria-expanded`, historique
cumulé du test `fits`) ; ajouter sur le PC la jauge du prompt 4 du scénario « Sous-agent ».

### Suite après la contre-vérification sur PC (2026-09-29, soir)

La contre-vérification (`resultats-lot-k-2026-09-29.md`, dernière section) a trouvé une
régression du point 2 et trois reliquats du point 3. Ils sont corrigés par
`spec-lot-k-suite-contre-verification-2026-09-29.md` (même branche, commits `e4da3d3` à
`dc4b911`) :

- **Point 2, régression K1.** Au zoom 150 % (853 px CSS), « Réinitialiser » sortait de la barre
  de 114 px et la page défilait en largeur. Correction : un palier sous 1 000 px CSS masque la
  légende de la jauge (chaque segment garde son `aria-label` et son infobulle), réduit la barre
  de la jauge à 180 px et les noms à leur minimum, et affiche « Aa » sur le bouton de
  projection. Dès 1 100 px, les espacements de la barre se resserrent : au vrai zoom 125 %
  (≈ 1 010 px), « Réinitialiser » dépassait de 4 à 9 px. La puce « · lié » reste entière aux
  quatre largeurs du point 2 ; sous 1 100 px, elle cède comme avant. E2E : 840, 853 et 911 px
  en normal et en projection, 1 005 et 1 024 px avec la légende visible.
- **Point 3b, reliquats K2.** IAM p1 et p2 : « en 5 lignes au plus : d'abord deux liens
  Microsoft Learn tirés du résultat, puis l'explication ». Souveraineté p1 : trois jeux au
  plus, chacun avec son lien. SOC p2 : transmettre à « un analyste SOC habilité, en 3 lignes
  au plus ».
- **Point 3a, décision d'Anaël (K3).** Avec le 2B, les secours restent la règle, et c'est la
  leçon. Les consignes de Lazy loading et de Souveraineté disent désormais ce qu'on observe (le
  modèle s'arrête après `load_tool_doc`, voire écrit « j'ai cherché » sans appel), pourquoi
  (petit modèle) et le geste « Forcer l'appel » comme démonstration du harnais. Le harnais et
  AD-17 sont inchangés ; la question AD-17 plus haut reste ouverte.
- **Mineur K7.** Une icône est servie (`/static/favicon.svg`, déclarée sur les quatre pages)
  et `/favicon.ico` répond 200.

Lignes « À vérifier sur PC » remplacées ou ajoutées (détail dans la spec de la suite) :

| Point | Geste | Attendu | Critère |
|---|---|---|---|
| 2 | Edge, 1 280 × 650 au vrai zoom 150 % puis 125 % ; aussi 853 × 433 et 911 × 512 émulés, normal et projection | barre sur une ligne, « Réinitialiser » entier, aucun défilement horizontal ; « Aa » sur le bouton de projection sous 1 000 px ; légende visible à 125 % | `scrollWidth − clientWidth` ≤ 1 ; aucune commande coupée |
| 3b | « Métier IAM », p1, « Vider la conversation », p2, sans secours | deux liens learn.microsoft.com en tête, réponse courte | tour `completed` (pas `limit`) ; deux liens par réponse |
| 3b | « Métier Souveraineté », p1 sans secours, puis avec | trois jeux au plus, chacun avec son lien | tour `completed` ; liens présents |
| 3b | « Métier SOC », p2 | `h1 block`, escalade vers un analyste SOC habilité | « analyste » dans la réponse, pas de « Démonstrateur » |
| 3a | Consignes de Lazy loading et de Souveraineté face au 2B sans secours | elles décrivent ce qu'on voit | avis d'Anaël |
| K7 | Edge, profil neuf | icône dans l'onglet, aucun 404 | console sans `favicon.ico` |

Prompt de recette : `prompt-recette-lot-k-suite-2026-09-29.md`.

## Spec Change Log

## Review Triage Log

Revue du 2026-09-29, passe 1 (Blind Hunter, Edge Case Hunter, Verification Gap).

| # | Source | Constat | Verdict | Preuve | Suite |
|---|---|---|---|---|---|
| 1 | VG | Aucun test n'arme un outil MCP avec un argument facultatif vide (préréglage « cybersécurité » : `page`, `page_size` = "") | medium | écart de vérification déposé ; sans le filtre de `arm`, `check` refuse l'entier vide (422) et rien n'échoue | patch |
| 2 | VG | Chemin « un clic » d'un outil MCP sans paramètre (`option.target ?? option.id`) et boutons en documentation complète jamais exercés | medium | écart déposé ; `list_terms` absent de l'E2E | patch |
| 3 | VG | Le contrôle E2E d'`aria-expanded` passait déjà avant le lot (reconstruction du panneau) | medium | notes du point 6 ; cause dans Edge non confirmée | defer |
| 4 | VG, ECH | Appel MCP forcé : définition ajoutée à `_loaded_docs` avant l'exécution, gardée si le tour est arrêté | low | vrai à l'arrêt (`ran is None`) ; bloqué par un hook, conforme à la spine (l'action forcée ajoute la définition) ; arrêt pendant l'appel rare, effet : une définition de plus au tour suivant | rejeté |
| 5 | BH | U+FEFF doublés : lignes de tableaux coupées dans `resultats-test-pc-2026-09-29.md` | low | 15 lignes vérifiées ; correction directe | patch |
| 6 | BH | Le prompt de recette ne peut pas éprouver le recalcul d'une ancienne sonde (clés `probed_models` sur les chemins réels, modèles en liens physiques) | medium | la séance du 29/09 a dû réécrire ces chemins ; sans cela le 2B est resondé à 12 288 | patch |
| 7 | BH | Test `fits` : définitions chargées (documentation, appel forcé) non comptées aux prompts suivants | low | quelques dizaines à ~100 tokens ; marge `mcp_lazy` p2 ≈ 600 ; correction non directe | rejeté |
| 8 | BH | Test `fits` : seul l'échange précédent est simulé ; nom « first_prompt » ; commentaire mal coupé | medium | historique cumulé au pire (réponses à la réserve) : `subagent` p4 1 326 + 2 267 > 3 584 (2B, décompte exact) ; N27-1 réel passait | patch (nom, commentaire, docstring) ; defer (modèle d'historique) |
| 9 | BH | Secours mslearn sans préréglage ; `iam` absent du commentaire d'en-tête ; consigne IAM non testée | low | vérifié dans `mcp.yaml` et le test ; ajout de contenu direct | patch |
| 10 | BH | Consigne `mcp_full` renvoie au scénario suivant alors que l'appel se force aussi en documentation complète | low | contredit la règle d'en-tête du fichier | patch |
| 11 | BH | Consigne Souveraineté : « Vider la conversation » avant le secours du prompt 1 | low | ordre du texte vérifié | patch |
| 12 | BH | Rien ne vérifie les `call_presets` face aux schémas des serveurs | medium | `_mcp_call_option` retire en silence un argument non déclaré | patch |
| 13 | BH | Nom accessible « Forcer l'appel : X » contre texte visible « Forcer l'appel · X » | low | seule la ponctuation diffère (ignorée par les aides vocales) ; même motif que les boutons existants | rejeté |
| 14 | BH | Point 3a sans vérification PC en documentation complète ni mise en page de la carte MCP | low | E2E ajouté au patch 2 ; mise en page : peu probable de gêner | rejeté |
| 15 | BH | Correction Ollama / llama-server annoncée sans test | false | `served_kv` passe par `gguf_kv_bytes_per_token` → `kv_bytes_per_token`, testée | rejeté |
| 16 | BH, ECH | Infobulle « N choisi » aussi pour les bornes `tpm`, `native` ou modèle cloud verrouillé | low | la valeur citée est bien la fenêtre configurée ; correction = nouvelle branche | rejeté |
| 17 | BH | E2E A8 : pas de `false` après « Annuler » ; pied du panneau testé à 100 % seulement | false / low | `run_e2e.py` vérifie `false` après fermeture (l. 2891, 2901) ; zooms : vérification PC | rejeté |
| 18 | BH | Règles CSS du sélecteur compact dupliquées pour la projection jusqu'à 1 600 px | low | une requête média ne peut viser `:root.projection` sans répéter les sélecteurs ; dérive possible mais rare | rejeté |
| 19 | BH, ECH | Écarts du point 2 : seule la puce liée protégée, ordre de repli, puce coupable sous 1 100 px, chiffres coupés en projection | low | écarts consignés dans les notes ; sous 1 100 px, garder la puce pousserait « Réinitialiser » hors de la barre (critère E2E) | rejeté |
| 20 | ECH | Même tour : appel forcé de X puis documentation forcée de X → documentation en double | low | combinaison improbable ; correction touche `loaded_in_turn` | rejeté |
| 21 | ECH | Modèle sans analyseur d'appels : abandon avec la raison « serveur non connecté » | low | la brique MCP n'est alors pas disponible, l'abandon dit « brique non active » d'abord | rejeté |
| 22 | ECH | Conseil `-c` au-delà du contexte natif | low | choix limités à 16 384, contextes natifs bien plus grands | rejeté |
| 23 | ECH | Bloc d'installation : aucune archive dans les dix releases | low | builds quotidiennes ; bloc « Repli » juste en dessous | rejeté |
| 24 | ECH | Deux puces liées (H5 + lien) entre 1 101 et 1 279 px | low | cas rare, non mesuré | rejeté |
| 25 | ECH | `#window-alert` sous la ligne de flottaison de `.window-scroll` à 1 280 × 650 | medium | l'alerte suit les choix dans la zone qui défile ; un refus après « Appliquer » peut rester caché | patch |
| 26 | ECH | Historique SOC / Compression : résultat de `read_file` borné à tort dans le test | false | SOC 601 < borne ; Compression : Headroom allumé au prompt 2 (consigne) | rejeté |
| 27 | ECH | Nom de fichier absent : `ToolError` fait échouer `fits` | false | échec bruyant sur un contenu fautif : comportement voulu | rejeté |

## Design Notes

Point 1, choix du recalcul à la lecture plutôt que `probe_version = 3` : la sonde mesure la RSS à
`probe_window` (cache compris) et seul le coût marginal `kv × (fenêtre − probe_window)` dépend de
la formule ; relire l'en-tête (Python pur, en cache par taille et date) corrige toutes les
entrées sans resonder 39 GGUF ni invalider `failed_probes`, et sans réécrire `settings.json`.

## Verification

**Commands:**
- `uv run ruff check . ; uv run ruff format --check .` -- propre
- `uv run pytest -q` -- vert
- `uv run --with playwright==1.56.0 python tools/e2e/run_e2e.py` -- 0 FAIL
