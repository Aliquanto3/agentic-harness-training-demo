# Rapport de la nuit du 2026-10-15 : V1.1, vague 1

Plan : `plan-nuit-2026-10-15-v1-1.md`. Spec : `_bmad-output/specs/spec-wavestack-v1-1-vague-1/`.
État final : `main` à `3b9d4db`, les 5 stories fusionnées, une seule branche distante (`main`).

## Bilan

| Story | PR | Statut | Relecture (second avis → reviewer) | Tests ciblés | E2E (Edge) |
|---|---|---|---|---|---|
| 0. Cadrage | #34 | fusionnée | — | — | — |
| 1. Installeurs | #39 (remplace #35) | fusionnée | 6 constats, 1 high → 7 corrigés | 15 | aucun prévu |
| 2. README et docs | #37 | fusionnée | 10 constats → 9 corrigés, 1 écarté, 2 de plus | 15 | aucun prévu |
| 3. Séquence agrandie | #38 | fusionnée | 6 constats → 3 corrigés, 3 écartés | 87 | `mcp_lab_page`, Séquence RAG dans `rag_lab` : verts |
| 4. Démarrage sans scan | #36 | fusionnée | 4 constats → 2 corrigés, 2 écartés | 92 | `model_catalog` 66/66 (2e passage) |
| 5. Menu 🏠/☁️ | #40 | fusionnée | 3 low → 2 corrigés, 1 à l'œil | 245 | 118/118 + 92/92 |
| Correctif de test (CAP-4) | #41 | fusionnée | — | 35 | — |
| Correctif E2E `rag_rerank` | #42 | fusionnée | — | — | `rag rag_rerank` 75/75 |

### Par story
- **1. Installeurs** (`install.bat`, `install.ps1`, `install.sh`, `tests/test_installers.py`).
  - Corrigés à la relecture : GGUF partiel pris pour présent (téléchargement en `.part` puis
    renommage) ; échec natif ignoré sous PowerShell (`$LASTEXITCODE`) ; réglages uv qui fuyaient
    dans la session sous `irm | iex` (bloc `& { }`) ; git absent (repli sur l'archive de
    `main`) ; `pause` au double-clic ; `WAVESTACK_DATA_DIR` exporté avant le lancement.
  - Non vérifié : `irm | iex` réel sur un PC sans droits admin ; `install.sh` sur macOS et
    Linux ; vraies URL du zip et du tarball GitHub ; `shellcheck` (absent du poste, seul
    `bash -n`).
- **2. README et docs** : README de 99 lignes, installeur en premier, consigne proxy avant
  `irm`, blocs manuels « dans PowerShell (pas CMD) », domaines proxy
  `raw.githubusercontent.com` et `codeload.github.com`, `| bash` sous macOS/Linux, options via
  `.\install.ps1` ou `& ([scriptblock]::Create((irm <url>))) -DryRun`. Écarté :
  `docs/modeles.md` (hors périmètre, blocs sans la mention PowerShell). Le reviewer a corrigé
  deux erreurs de plus : `irm | iex` n'installe jamais sur place (seul `install.bat` le fait) ;
  pas d'attente après le clic sur « Ajouter d'autres modèles ».
- **3. Séquence agrandie** : `/mcp` réutilise le « Mode focus » de `panes.js`, avec Échap et
  `aria-pressed` en plus ; `/rag` a son bouton ⛶ propre. Corrigé : l'Échap de `panes.js`
  passait avant celui d'`app.js` (tiroirs, menus, dialogues de l'atelier) → opt-in pour `/mcp`
  seulement. Écartés : Échap dans un champ, recouvrement RAG non modal, `aria-pressed` du
  setter. Non vérifié : rendu du recouvrement RAG et position du ⛶.
- **4. Démarrage sans scan** : `discover(..., extended=False)` ; au démarrage, `models_dir`,
  chemins explicites (dont le modèle enregistré) et Ollama ; `POST
  /api/intentions/search_more` derrière « Ajouter d'autres modèles… ». Corrigé : la recherche
  sondait chaque GGUF trouvé, sous verrou, dans la requête (relevé en high) → liste sans sonder,
  sondage au choix. Écarté par un test : la régression supposée au redémarrage avec un modèle
  HF enregistré. Non vérifié : choix à chaud d'un modèle trouvé par le bouton.
- **5. Menu 🏠/☁️** : emoji selon `hosting`, fonds par jetons existants (contrastes 17,2/12,0
  et 18,0/11,0). Corrigé : options désactivées de nouveau grisées ; doc E2E. À l'œil :
  l'option surlignée dans la liste native d'Edge.

## Vérification finale (sur `main`)
- pytest complet en quatre quarts : 4 093 + 812 + 545 + 613 = 6 063 passés, 3 ignorés,
  13 désélectionnés (marqueur `model`, GGUF réel requis : `addopts = "-m 'not model'"`).
  Un échec au 3e quart, corrigé par #41 :
  `test_rag_lab_embeddings::test_an_embedding_gguf_in_the_hf_cache_is_incompatible_never_chosen`
  supposait le scan du cache HF au démarrage. Les tests ciblés de la story 4 ne couvraient pas
  ce fichier.
- E2E : `mcp_lab_page mcp_lab model_switch model_catalog` 142/142. `rag rag_rerank rag_lab`
  148/149 : `rag_rerank`, « brique RAG rallumée : Reranking de nouveau réglable » (contrôle lu
  sans attente juste après `set_brick`). Pas une régression : vert sur `568ae6f` au repos, puis vert au second passage sur `main` ; contrôle rendu robuste par #42 (attente de 5 s), `rag rag_rerank` 75/75.
- `settings.json` d'Anaël : empreinte identique avant et après chaque E2E (l'E2E travaille dans
  un dossier temporaire).

## Écarts au plan et décisions prises seul
- **Fusion automatique refusée** par le classifieur du mode auto (« Merge Without Review ») :
  non contournée. Les PR ont été empilées, puis fusionnées le 16/10 sur autorisation d'Anaël.
- **Erreur de l'orchestrateur** : #34 fusionnée avec `--delete-branch` sans recibler d'abord les
  PR empilées (la mémoire le disait) → GitHub a fermé #35, #36 et #38. Base recréée, #36 et
  #38 rouvertes ; #35, rebasée, n'était plus rouvrable → remplacée par #39. Chaque story a été
  rebasée sur `main` et ses tests ciblés rejoués avant fusion. Branches distantes supprimées
  sur autorisation d'Anaël.
- **Sauvegarde et restauration du `settings.json`** refusées par le classifieur (« Irreversible
  Local Destruction ») : remplacées par une empreinte en lecture avant et après chaque E2E.
- **Ordre de la lane A** : story 3 avant la 2 (fichiers disjoints, créneau libre) ; story 2
  bâtie sur la story 1 relue, pour décrire les installeurs finaux.
- **Incidents d'agents** : 4 blocages du flux (watchdog de 600 s) et 1 coupure réseau, tous
  repris avec leur contexte, sans perte. Un agent a relancé un `python -` avec heredoc (shell
  bloqué), sans effet sur le poste.
- **Résidu** : un dossier `--keep` de l'E2E reste dans `%TEMP%` (`wavestack-e2e-49komurf`).

## Recherches de la vague 2 (lane R)
Fichiers dans `_bmad-output/planning-artifacts/research/`.

**MCP en ligne** (`recon-mcp-en-ligne-2026-10-15.md`)
1. GitHub MCP distant : le plus parlant pour un RSSI (alertes de sécurité, secrets,
   Dependabot), OAuth réel et gratuit avec un compte GitHub.
2. Atlassian (Jira, Confluence) : OAuth 2.1, gratuit jusqu'à 10 utilisateurs ; URL déjà changée
   une fois (v1 → v2).
3. Notion : le plus simple, outils marqués « Read-only » ou « Destructive » ; peu parlant pour un
   public sécurité.
4. Appels refusés de démo : fusion de PR en lecture seule, suppression sans rôle admin,
   archivage par un outil « Destructive ».
5. Réserve : statut GA de la version distante de GitHub non confirmé par une annonce officielle.

**Guardrails sur CPU** (`recon-guardrails-cpu-2026-10-15.md`)
1. Seuls les classifieurs encodeurs légers tiennent bien sur CPU et 16 Go ; les juges décodeurs
   (Llama Guard, Granite Guardian 2B+, ShieldGemma) sont plus lourds.
2. Recommandation : Granite-Guardian-HAP-38M (Apache 2.0, toxicité seule), puis Llama Guard
   3-1B-INT4 (licence Meta à accepter, multi-catégories), puis Presidio + `presidio-fr` (PII).
3. NeMo Guardrails écarté comme moteur principal : latence CPU et faux positifs hors anglais
   documentés par NVIDIA.
4. Le français est partout le point faible (Llama Guard 3 nettement plus faible qu'en anglais ;
   Presidio à calibrer).
5. SGuard, GLiGuard, PolyGuard, gpt-oss-safeguard : à suivre, trop récents ou trop gros.

**FinOps du harnais** (`recon-finops-harnais-2026-10-15.md`)
1. WaveStack mesure déjà beaucoup : coûts cloud par appel, tour et séance, tokens de cache des
   trois fournisseurs, débit local, compression Headroom, coût du sous-agent sommé.
2. Ce qui manque, c'est l'affichage : économie du cache, gain de compression en continu, coût
   du sous-agent isolé, champs `timings` de llama-server peu exploités.
3. Le plus rentable à montrer sans nouvelle mesure : cache de prompt, compression, surcoût du
   sous-agent.
4. Pas de plafond de dépense (hors périmètre).
5. Réserve : prix cloud de 2026 contradictoires entre sources tierces (à revérifier sur les pages
   officielles) ; le « 15× » multi-agents d'Anthropic n'a pas de source primaire retrouvée.

## Recette d'Anaël
- Installer depuis un compte Windows sans droits admin, ou le PC d'un collègue :
  - `install.bat` en double-clic, puis `install.ps1` via `irm | iex` ;
  - relancer l'appli ensuite, sans repasser par l'installeur ;
  - vérifier qu'aucun gros fichier n'arrive dans OneDrive.
- Menu des modèles : 🏠/☁️ et fonds de couleur dans Edge, en thème clair puis en thème sombre ;
  l'option survolée et les options grisées restent lisibles.
- Démarrage rapide, sans scan, puis le bouton « Ajouter d'autres modèles ».
- Séquence agrandie sur les pages MCP et RAG ; sur l'atelier, Échap ferme toujours tiroirs et
  menus.
- Mesurer le coût de la nuit avec `/agent-cost-kit:mesurer-couts`, et le comparer à la story
  médiane de la V1 (16,57 $).
