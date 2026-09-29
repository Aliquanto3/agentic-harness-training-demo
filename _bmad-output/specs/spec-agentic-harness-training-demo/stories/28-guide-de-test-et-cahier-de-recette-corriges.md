---
title: 'Guide de test et cahier de recette corrigés'
type: 'chore'
created: '2026-09-28'
status: 'done'
baseline_revision: '69f0cf398a14b0ea964fbc59956ae72517e22043'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/retours-recette-palier-2-2026-09-28.md'
  - '{project-root}/_bmad-output/implementation-artifacts/plan-nuit-2026-09-28.md'
  - '{project-root}/_bmad-output/implementation-artifacts/cahier-recette-palier-2.html'
  - '{project-root}/_bmad-output/implementation-artifacts/guide-test-pc-palier-2.md'
  - '{project-root}/README.md'
warnings:
  - oversized
deferred:
  - summary: >-
      Procédures PowerShell (llama-server, D11, Z2, Z3) jamais exécutées sous Windows ; chemins de clic du cahier non rejoués sur l'interface vivante.
    evidence: |-
      Pas de pwsh dans le conteneur ; libellés vérifiés contre le code seulement.
    severity: medium (unverified)
  - summary: >-
      Contrôle Playwright du cahier jetable, hors du dépôt, qui imprime au lieu d'affirmer.
    evidence: |-
      Le cahier n'a aucun test dans tests/ ni tools/.
    severity: low (unverified)
---

<intent-contract>

## Intent

**Problem:** La recette du 2026-09-28 n'a pas pu être menée jusqu'au bout. llama-server n'était pas installé et le guide ne dit pas comment l'obtenir sans droits d'administrateur (C9, C10). Plusieurs tests du cahier sont restés « non faits » parce que leur consigne était incompréhensible : D1, D2m, X1, X3, Z1, Z2, M3, M6, ainsi que D11 et « Réinitialiser » dans M1. Enfin, beaucoup de tests n'ont qu'une liste « À vérifier », sans geste pas à pas.

**Approach:** Réécrire les trois documents sans toucher au code. Le README et le guide donnent une procédure PowerShell exacte pour obtenir llama-server (archive `bin-win-cpu-x64` de la release llama.cpp, décompressée dans le profil, lancée par son chemin complet avec `-c 4096`) et un repli si le proxy bloque GitHub. Dans le cahier, chaque test reçoit un geste pas à pas qui donne le chemin exact dans l'interface actuelle ; les tests jugés incompréhensibles sont réécrits, et Z2 dit comment vider les clés. Le cahier ne détaille pas les stories 22 à 34 : il renvoie vers le prompt du PC cible et vers le futur cahier détaillé.

## Boundaries & Constraints

**Always:**
- Textes en français ; commandes en PowerShell (Windows 11, sans droits d'administrateur) ; conventions de `CLAUDE.md` (`uv`, jamais pip).
- Chaque libellé d'interface cité (bouton, menu, carte, étape, message) est relu dans le code **au moment de l'implémentation**, après les stories 23 à 27 et 29 à 34 (recherche dans `src/wavestack/web/static/app.js`, `index.html`, `content/**/*.yaml`, `src/wavestack/**/*.py`). Aucun libellé n'est recopié de mémoire ni tiré de cette spec sans vérification : les stories de la nuit renomment et déplacent des éléments (sélecteur de modèles, volets numérotés, onglets, nouveaux écrans).
- Le mécanisme d'enregistrement du cahier est conservé tel quel : `db` de l'artefact (`window.claude.use("db")`, collection de résultats), repli dans le navigateur (`localStorage`), compte rendu à copier, filtres et compteurs. La page reste autonome : un seul fichier HTML, sans script externe (la feuille Google Fonts actuelle peut rester).
- Ne rien affirmer de faux sur le comportement livré par les stories 22 à 34 : quand une attente d'un test existant a changé (par exemple C3, dont les en-têtes sont visibles depuis la story 23), l'attente est corrigée sans ajouter de test sur la nouvelle fonctionnalité.
- Le guide et le cahier disent la même chose : mêmes gestes, mêmes commandes, mêmes critères.

**Never:**
- Aucun changement de code, de test, de configuration ni de dépendance ; aucun vrai modèle ; aucune modification de `tools/e2e/run_e2e.py`, puisque l'interface de l'application ne change pas.
- Ne pas publier d'artefact : le fichier local suffit, Anaël le republiera.
- Ne pas créer les tests détaillés des stories 22 à 34 ni le fichier `prompt-test-pc-2026-09-29.md`.
- Ne pas faire télécharger un exécutable ailleurs que depuis `github.com/ggml-org/llama.cpp` ou une copie de cette archive remise par le formateur ; ne pas proposer winget, Chocolatey, un installeur ni une élévation de droits.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| API GitHub joignable | Procédure PowerShell, proxy ouvert vers `api.github.com` et les hôtes de téléchargement | `$asset.name` vaut `llama-bNNNNN-bin-win-cpu-x64.zip` ; l'archive est décompressée dans `%LOCALAPPDATA%\llama.cpp\bNNNNN` ; `llama-server.exe --version` répond | — |
| API bloquée, github.com ouvert | `Invoke-RestMethod` échoue (403 ou 407) | Repli : URL fixe `https://github.com/ggml-org/llama.cpp/releases/download/b11239/llama-b11239-bin-win-cpu-x64.zip` | 407 : relancer avec `-ProxyUseDefaultCredentials` |
| GitHub entièrement bloqué | Téléchargement impossible | Repli : récupérer la même archive sur un autre réseau ou un autre poste, ou auprès du formateur, puis la copier (partage interne, OneDrive, clé USB) et reprendre à `Expand-Archive` ; sinon, C9 et C10 sont marqués « non fait (poste) » et le mode serveur est vérifié avec Ollama | — |
| Exécutable bloqué | AppLocker, SmartScreen ou DLL d'exécution absente (`VCRUNTIME140.dll`, `MSVCP140.dll`) | Le guide dit quoi relever (message exact) et renvoie au support ; C9 et C10 passent à « non fait (poste) » | Pas de contournement |
| Cahier enregistré | Statut, champ ou note saisis | Enregistré dans le `db` de l'artefact, sinon dans le navigateur ; le compte rendu reprend le tout | Stockage indisponible : la page marche sans lui |

</intent-contract>

## Code Map

- `_bmad-output/implementation-artifacts/cahier-recette-palier-2.html` -- Page autonome. En-tête l.193-195 (« palier 2 · lot J », obsolète) ; intro « Avant de commencer » l.221-228 (lot J non commité : obsolète). `GROUPS` l.242-249 ; `PEAK_CMD` l.251-253 ; `TESTS` l.255-381 (P1 l.256, P2 l.261, C1-C10 l.267-316, M1-M6 l.318-339, X1-X4 l.341-353, D1 l.355, D2m l.357, D3m l.361, D4m l.363, Z1-Z3 l.366-380). Champs d'un test : `steps` (« Geste »), `checks` (« À vérifier », cases à cocher), `cmds`, `expect`, `crit` (HTML via `innerHTML`), `known` (« Déjà mesuré »), `fields`. Aujourd'hui, M1-M6, X1-X3 et D1-D4m n'ont pas de `steps`. `KEY` l.384 ; rendu `renderCase` l.489-564 ; `report()` l.616-639 (titre « lot J » l.617) ; synchronisation `db`, collection `results`, l.669-704.
- `_bmad-output/implementation-artifacts/guide-test-pc-palier-2.md` -- Sections du guide :
  - 0 : proxy l.22-25, « `llama-server.exe` » en option l.31-32 ;
  - 5.5 E1 : llama-server sans `-c`, l.361-378 (commande l.368) ;
  - 6, module 1 : Réinitialiser et D11, l.485-492 ;
  - 6, M3 : l.499-508 ;
  - 6, M6 : l.527-533 ;
  - 6, transverses : l.541-553 ;
  - 6, « Modèles » : l.557-606 (llama-server l.568-581) ;
  - 7 : D2, l.624-631 ; D3, l.633-651 (clés : l.649-651).
- `README.md` -- l.29-33 : domaines du proxy. l.176-199 : « Utiliser un serveur déjà lancé » (commande llama-server l.193).
- Ancres d'interface, à revérifier. Les stories 25 et 34 touchent la barre haute et les volets.
  - `index.html` l.31-35 : barre haute, avec l'indicateur du modèle, `model-picker` (« Changer de modèle… »), « Charger » et « ⟲ Réinitialiser ».
  - `index.html` l.64-93 : tiroir de la mémoire (croix, « Tout effacer », « Fermer »).
  - `index.html` l.104-110 : actions de la Vue humain (« Rejouer le dernier prompt », « Vider la conversation »).
  - `app.js` l.1260-1266 : `FORCE_LABELS`.
  - `app.js` l.1314 : « Afficher les actions forcées ».
  - `app.js` l.1702 : « Modifier la mémoire ».
  - `app.js` l.1209 : « · brique éteinte » sur la carte MCP.
  - `app.js` l.2098-2100 : options du sélecteur, dont « Autre fichier ou clé API… ».
  - `app.js` l.2266 : « Modèle : … ».
- `src/wavestack/session/app_session.py:4465-4495` -- « Réinitialiser » (`reset`) ramène au LLM nu, sans scénario, et restaure la mémoire de démonstration. Un scénario marqué `restore_memory` la restaure aussi (`content/scenarios.yaml`, `global_memory` l.111) : une mémoire remplie à la main est donc écrasée par le lancement du scénario « Mémoire globale ».
- `src/wavestack/memory.py:26-27` -- `MAX_ENTRIES = 20`, `MAX_CHARS = 300`. `memory.json` est une liste JSON de `{id, text, created_at, source}`, chaque texte sur une ligne. Le test du dépôt : `tests/test_global_memory.py:559`.
- `src/wavestack/config.py:688-699` -- `cloud_key` : `api_keys.json` d'abord, puis la variable `key_env` (`GROQ_API_KEY`, `MISTRAL_API_KEY`). Une variable vide compte comme absente. L'interface n'a aucun bouton pour supprimer une clé.
- `content/scenarios.yaml:300-312` -- `data_flows` : briques `short_memory`, `system_prompt` et `tools` ; `mcp_lazy: true` avec MCP éteint (la cause de la confusion X1, traitée par la story 22).
- Specs de la nuit, stories 22 à 27 et 29 à 34, dans `stories/*.md` : sections « À vérifier sur PC » et « Auto Run Result » pour savoir quels libellés ont changé. La story 22 (faite) a changé le tiroir de la mémoire, les sous-options grisées, les onglets « Agent principal » / « Sous-agent », « Tour N » après « Réinitialiser » et « Annuler » du formulaire forcé.
- Faits vérifiés le 2026-09-28 pour llama.cpp :
  - Dernière étiquette : `b11239`, commit `66e665c`, du 2026-09-28 à 21:31 (+02:00). Source : `git ls-remote` et un clone creux.
  - Nom de l'archive : `llama-${tag}-bin-win-cpu-x64.zip`, lu dans `.github/workflows/release.yml` à ce tag (l.963 : `7z a -snl llama-bin-win-cpu-x64.zip .\build\bin\Release\*` ; renommage l.1899-1904 ; lien de la note de release l.1986).
  - Contenu : l'exécutable et ses DLL à la racine de l'archive, dont les variantes `ggml-cpu-*`, puisque `GGML_CPU_ALL_VARIANTS=ON` en x64.
  - Limite : l'API `api.github.com/repos/ggml-org/llama.cpp/releases/latest` a répondu 403 depuis le conteneur (politique de la session). La publication de la release `b11239` n'est donc pas confirmée par l'API ; la procédure choisit l'archive par l'API sur le poste.

## Tasks & Acceptance

**Execution:**
- `README.md` -- Dans « Utiliser un serveur déjà lancé », ajouter le paragraphe « Obtenir llama-server sans droits d'administrateur (Windows) » avec la procédure des Design Notes (API, téléchargement, `Expand-Archive` dans le profil, `Unblock-File`, `--version`, lancement par chemin complet avec `-c 4096`), le repli et les blocages possibles. Ajouter `api.github.com` et les hôtes de téléchargement des releases (`objects.githubusercontent.com`, `release-assets.githubusercontent.com`) à la liste du proxy, marqués « pour llama-server, facultatif ». -- La cause de C9 et C10 est un poste sans llama-server.
- `_bmad-output/implementation-artifacts/guide-test-pc-palier-2.md` -- (1) Titre, section 0 et section 1 : la séance vise le commit de la nuit du 2026-09-28. Les stories 22 à 34 sont vérifiées par le Claude Code du PC (`prompt-test-pc-2026-09-29.md`), puis par le cahier détaillé qu'il générera ; ce guide et ce cahier ne les détaillent pas. (2) Nouvelle sous-section « Installer llama-server » (section 2 ou 4) : procédure identique au README, avec le repli. Section 0 : hôtes du proxy. (3) Toutes les commandes llama-server (l.368, l.571) passent par `$llama`, le chemin complet résolu dans le profil. (4) Réécrire, avec le geste exact, les points repris dans le cahier : D11, « Réinitialiser » (M1), M3, M6, X1, X3, D1, D2m, Z1 (D2) et Z2 (D3, clés vidées : variable de session, variable utilisateur posée par `setx`, `api_keys.json` mis de côté). (5) Corriger toute attente que les stories 22 à 27 rendent fausse dans ces points, sans rien ajouter sur leurs nouveautés. -- Point (4) de la story : le guide reprend les corrections du cahier.
- `_bmad-output/implementation-artifacts/cahier-recette-palier-2.html` -- (1) En-tête, intro et titre du compte rendu : « recette suivante » au lieu de « lot J ». L'intro renvoie au prompt `prompt-test-pc-2026-09-29.md` et au futur cahier détaillé des stories 22 à 34. (2) Nouveau test `P3` « Installer llama-server » dans `prep`, avec les `cmds` de la procédure, le repli dans `expect` et un champ « Version (bNNNNN) ». (3) Donner des `steps` à **chaque** test. Pour les tests qui ont des `checks`, les `steps` disent où cliquer et quoi saisir ; les `checks` restent la liste de ce qu'il faut voir. (4) Réécrire D1, D2m, X1, X3, Z1, Z2, M3 et M6, ainsi que D11 et « Réinitialiser » de M1, selon les Design Notes. (5) C9 et C10 : `cmds` avec `$llama`. (6) `known` : ajouter le résultat du 2026-09-28 de chaque test (« Le 28/09 : KO, … »). (7) Passer `KEY` et la collection `db` à une version nouvelle (`recette-palier-2-v2`, `results-v2`) ; le reste du mécanisme ne change pas. -- Points (2) et (3) de la story, avec le point (3) remplacé.

**Acceptance Criteria:**
- Given le cahier ouvert dans Chromium (`file://`), when la page se charge, then aucune erreur de script (`pageerror`, console `error` hors échec réseau des polices), autant d'articles `.case` que d'entrées `TESTS`, et chaque article contient un bloc « Geste » non vide.
- Given le cahier ouvert, when on clique « OK » sur un test, qu'on saisit un champ et qu'on recharge, then le statut et le champ reviennent (repli `localStorage`), et « Afficher le compte rendu » les reprend.
- Given le guide, le README et le test `P3`, when on les compare, then la procédure llama-server est identique aux trois endroits : nom d'archive `llama-bNNNNN-bin-win-cpu-x64.zip`, dossier `%LOCALAPPDATA%\llama.cpp\<tag>`, appel par `& $llama` avec `-c 4096 -np 1 --port 8080`, même repli.
- Given les tests D1, D2m, X1, X3, Z1, Z2, M3 et M6, ainsi que D11 et « Réinitialiser » dans M1, when on les lit, then chaque geste nomme le volet, le contrôle et le libellé exact à cliquer ou à saisir, et chaque libellé cité existe dans le code du commit (vérifié par recherche).
- Given Z2, when on le lit, then il vide la variable de session (`Remove-Item Env:GROQ_API_KEY`, idem pour Mistral), la variable utilisateur posée par `setx` (`[Environment]::SetEnvironmentVariable("GROQ_API_KEY", $null, "User")`, puis un nouveau terminal) et `api_keys.json` (mis de côté), et il dit comment tout restaurer.

## Spec Change Log

- 2026-09-29 (lot K, point 8, recette sur PC anomalie A6) : `releases/latest` de
  ggml-org/llama.cpp pointe désormais sur `v0.5.0`, dont le seul fichier est
  `nightly-tag.txt` ; les builds `bNNNNN` restent publiées à côté. La procédure des Design
  Notes lit donc `/releases?per_page=10` et prend la première release qui porte
  `llama-b*-bin-win-cpu-x64.zip` ; le repli `b11239` reste (vérifié sur le PC cible le
  2026-09-29 : version affichée, sans élévation). Le cahier du 2026-09-28 (P5) est corrigé de
  même ; le README et le cahier du palier 2 que cette story écrit doivent reprendre ce bloc.
- 2026-09-29 (fusion du lot K sur cette story) : le README, le guide et le cahier du palier 2
  reprennent ce bloc, message d'arrêt compris (« dans les dix dernières releases ») ;
  `tests/test_recette_docs.py` vérifie les trois procédures, identiques mot pour mot.

## Review Triage Log

### 2026-09-29 — Review pass
- verdicts: 26 findings — high 3, medium 7, low 12, false 0, maybe-false 4 (l'auditeur d'intention confirme la lecture « précision de l'appelant » : pas de tests détaillés 22 à 34 dans le cahier, renvoi ; il relève que le renvoi ignore le cahier de la nuit déjà publié — retenu ci-dessous)
- findings:
  - `[low]` `[patch]` (intention + blind) renvoi qui ignore `cahier-recette-nuit-2026-09-28.html` et le prompt intermédiaire — renvoi complet.
  - `[maybe-false]` `[defer]` (intention) procédures PowerShell jamais exécutées sous Windows ; chemins de clic non rejoués sur l'interface vivante — première passe sur PC.
  - `[low]` `[patch]` (vérif.) nouvelle clé et collection du cahier sans contrôle — vérification « chaque test à faire à la première ouverture » ajoutée.
  - `[maybe-false]` `[defer]` (vérif.) contrôle Playwright jetable qui imprime au lieu d'affirmer, hors du dépôt.
  - `[high]` `[patch]` (blind + edge ×3) Z2 : clés permanentes effacées, conservées en mémoire d'un terminal que l'étape suivante ferme ; « Défaire » qui peut supprimer les GGUF ou les clés — Z2 réécrit sans aucun déplacement ni suppression, variables d'environnement du seul processus, dossier de données temporaire.
  - `[high]` `[patch]` (blind + edge) scripts « mettre de côté » qui détruisent leur sauvegarde s'ils sont relancés (clés, `memory.json`) — sauvegarde gardée, relance refusée.
  - `[medium]` `[patch]` (blind + edge) contrôle des clés au niveau Machine placé après les déplacements, sans Mistral — en premier, pour les deux.
  - `[medium]` `[patch]` (blind + edge) Z2 ne neutralise ni le cache Hugging Face, ni LM Studio, ni Ollama — dossiers vides pour le processus, lignes attendues décrites.
  - `[high]` `[patch]` (blind + edge) Z3 qui écrase ou supprime toute la clé `cloud` de `settings.json` — sauvegarde, modification de la seule entrée, restauration.
  - `[low]` `[patch]` (blind) D1 encore édité à la main (BOM) — mêmes commandes Python.
  - `[medium]` `[patch]` (blind) budget mémoire dynamique non relevé ; attentes C4, C5, X4 figées sur 4,0 Go ; guide et cahier en désaccord — budget relevé en P2, attentes rapportées à lui.
  - `[low]` `[patch]` (blind) nombre de tests périmé, sauts de l'extra non expliqués — mis à jour.
  - `[low]` `[patch]` (blind) cahier de la nuit non cité — regroupé avec l'intention.
  - `[medium]` `[patch]` (blind) téléchargement de llama-server ni épinglé ni vérifié ; `Unblock-File` contre la consigne « ne pas contourner » — empreinte comparée, limite dite, arrêt si la politique l'interdit.
  - `[low]` `[patch]` (blind) résultats impossibles à consigner (Z2, code d'erreur de P3), étapes de C4 différentes entre guide et cahier — champs ajoutés, textes alignés.
  - `[medium]` `[patch]` (edge ×2) remède au 407 inopérant sans `-Proxy`, repli b11239 idem — proxy du système passé explicitement.
  - `[low]` `[patch]` (edge) aucun fichier ne correspond au motif de l'archive : erreurs confuses — message qui renvoie au repli.
  - `[high]` → regroupé (relance de D11, edge).
  - `[high]` → regroupé (relance de la mise de côté, edge).
  - `[medium]` → regroupé (dossiers de modèles, edge).
  - `[high]` → regroupé (« Défaire » destructeur, edge).
  - `[high]` → regroupé (nouveau terminal sans `$gk`, edge).
  - `[high]` → regroupé (Windows Terminal fermé, edge).
  - `[medium]` `[patch]` (edge) garde de lancement qui imprime False sans arrêter — arrêt explicite.
  - `[maybe-false]` `[patch]` (edge « claim ») copie de C4 sondée au lancement : la sonde interrompue n'est jamais testée — copie créée pendant que WaveStack tourne, choisie à chaud.
  - `[maybe-false]` `[patch]` (edge « deletion ») porte « la fusion attend le lot H » retirée — état du lot H rétabli.

## Design Notes

**Procédure llama-server** (Windows PowerShell 5.1 et PowerShell 7) :

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12   # PowerShell 5.1
$rels = Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"
$rel = $rels | Where-Object { $_.assets.name -match '^llama-b\d+-bin-win-cpu-x64\.zip$' } | Select-Object -First 1
$asset = $rel.assets | Where-Object name -match '^llama-b\d+-bin-win-cpu-x64\.zip$'
$zip = "$env:TEMP\$($asset.name)"; $dest = "$env:LOCALAPPDATA\llama.cpp\$($rel.tag_name)"
Invoke-WebRequest -UseBasicParsing $asset.browser_download_url -OutFile $zip
Expand-Archive $zip -DestinationPath $dest -Force; Get-ChildItem $dest -Recurse | Unblock-File
$llama = "$dest\llama-server.exe"; & $llama --version
& $llama -m "$env:LOCALAPPDATA\WaveStack\models\Qwen3.5-2B-Q4_K_M.gguf" --port 8080 -np 1 -c 4096
```

Dans un nouveau terminal, sans rien retélécharger :

```powershell
$llama = Get-ChildItem "$env:LOCALAPPDATA\llama.cpp" -Recurse -Filter llama-server.exe | Sort-Object LastWriteTime | Select-Object -Last 1 -ExpandProperty FullName
```

Repli si l'API est bloquée : `$tag = "b11239"`, puis l'URL `https://github.com/ggml-org/llama.cpp/releases/download/$tag/llama-$tag-bin-win-cpu-x64.zip`. Sur une erreur 407, ajouter `-ProxyUseDefaultCredentials` aux deux appels. L'exécutable doit rester avec ses DLL : il ne faut ni le copier seul, ni le décompresser dans `Program Files`.

**Gestes à réécrire.** Les libellés ci-dessous sont à revérifier dans le code.
- **M1, « Réinitialiser »** : cliquer « ⟲ Réinitialiser » dans la barre haute. On revient au LLM nu, sans scénario, et la mémoire de démonstration est restaurée. Pour le vérifier, ouvrir « Modifier la mémoire » sur la carte Mémoire globale : les entrées de démonstration sont revenues, et Orchestration repart à « Tour 1 ».
- **D11, mémoire pleine** :
  1. WaveStack arrêté, sauvegarder `memory.json`.
  2. Écrire, avec un script PowerShell fourni, 20 entrées de 300 caractères au format du Code Map.
  3. Relancer WaveStack. Ne pas lancer le scénario « Mémoire globale » (il restaure la démonstration) : allumer la brique à la main dans le Panneau des briques.
  4. Lire la jauge de la barre haute, puis restaurer la sauvegarde.
- **M3** : dire où se trouve chaque élément. L'interrupteur Reranking est dans la carte RAG, la case « Recherche RAG » et l'étape « Reranking » sont dans Orchestration, l'index est dans le Schéma.
- **M6** : le formulaire forcé « Déléguer au sous-agent » (et son « Annuler »), puis les onglets du Contexte LLM.
- **X1** : lancer le scénario « Où vont mes données ? », allumer la brique MCP, puis cocher le serveur local et data.gouv.fr dans la carte MCP. L'attente « lazy loading actif » ne vaut qu'une fois la brique allumée, conformément à la story 22.
- **X3** : IAM puis Souveraineté, avec chacun son prompt suggéré. Pour chaque appel de Souveraineté, ouvrir « Données sortantes » dans Orchestration et y chercher les deux hôtes.
- **D1** : « Changer de modèle… », puis `qwen3.5:2b` servi par Ollama, puis « Charger ». Ensuite « Rejouer le dernier prompt » et « Comparer ».
- **D2m** : `ollama serve`, puis `ollama ps`. L'alerte « transparence réduite » est à chercher dans le Journal des événements.
- **Z1** : la commande qui met le reranker de côté, puis l'endroit où se lit « indisponible » sur la carte RAG.

## Verification

**Commands:**
- `uv run ruff check .` -- expected: aucune erreur (aucun code touché)
- `uv run ruff format --check .` -- expected: aucun fichier à reformater
- `uv run pytest -q` -- expected: tout vert, même compte qu'avant la story
- Un seul rendu Playwright du cahier, par un script jetable hors dépôt : `uv run --with playwright==1.56.0 python <scratchpad>/check_cahier.py` (Chromium de `PLAYWRIGHT_BROWSERS_PATH` ou `/opt/pw-browsers`). -- expected: 0 `pageerror` ; articles = `TESTS.length` ; « Geste » dans chaque article ; statut et champ retrouvés après rechargement ; compte rendu non vide.
- `rg -o '« [^»]+ »' cahier-recette-palier-2.html`, puis rechercher chaque libellé d'interface dans `src/` et `content/`. -- expected: chaque libellé d'interface cité est trouvé. Les messages de journal, de terminal et les citations de fournisseurs sont exclus.

**Manual checks (if no CLI):**
- La procédure llama-server est identique dans le README, le guide et `P3`. La page reste lisible à 390 px de large, sans défilement horizontal.

## Décisions prises par défaut

- Le point (3) de la story (couvrir les stories 22 à 30 dans le cahier) est remplacé par la précision d'Anaël : le cahier renvoie seulement vers `prompt-test-pc-2026-09-29.md` et vers le cahier détaillé que le Claude Code du PC cible générera. Si ce fichier de prompt n'existe pas encore au moment de l'implémentation, on cite quand même son chemin (il est prévu par le plan de la nuit).
- Les attentes des tests existants rendues fausses par les stories de la nuit (C1, C3, C4, M3, M6, X1…) sont corrigées, sans ajouter de test. Motif : ne pas laisser d'attente fausse.
- Tous les tests du 2026-09-28 restent au cahier, y compris ceux qui étaient OK, avec leur résultat du 28/09 dans « Déjà mesuré ». Le filtre « À faire » suffit pour s'y retrouver.
- La clé `localStorage` et la collection `db` changent de version : la séance suivante repart à zéro, et les résultats du 28/09 restent dans `retours-recette-palier-2-2026-09-28.md`. Le mécanisme lui-même ne change pas.
- llama-server s'installe dans `%LOCALAPPDATA%\llama.cpp\<tag>` : le profil n'exige pas de droits, et un dossier par version évite de mélanger les DLL de deux versions. L'archive est choisie par l'API (dernière release), avec l'étiquette `b11239` en repli fixe, observée le 2026-09-28.
- Le nom de l'archive a été établi par le workflow de release et non par l'API, que la politique de la session refusait (403). Le motif `^llama-b\d+-bin-win-cpu-x64\.zip$` reste valable quel que soit le numéro.
- Pas de winget ni d'installeur : ils peuvent demander des droits et ne sont pas prévus par la story.
- `tools/e2e/run_e2e.py` n'est pas modifié : l'interface de l'application ne change pas. La page du cahier est vérifiée par un rendu Playwright unique, comme demandé.
- Type `chore` : documentation seulement.

## À vérifier sur PC

- **Installation de llama-server**
  - **Geste** : ouvrir un nouveau terminal PowerShell, coller le bloc « Procédure llama-server » du guide (test `P3`) ligne par ligne, puis relever `$asset.name` et la sortie de `& $llama --version`.
  - **Attendu** : archive `llama-bNNNNN-bin-win-cpu-x64.zip` téléchargée, puis décompressée dans `%LOCALAPPDATA%\llama.cpp\bNNNNN` ; la version s'affiche.
  - **Critère** : aucune demande d'élévation ; code de sortie 0 pour `--version`.
  - **Moyen** : à la main, ou par le Claude Code du PC.
- **Proxy qui bloque**
  - **Geste** : si `Invoke-RestMethod` échoue, noter le code (403 ou 407), réessayer avec `-ProxyUseDefaultCredentials`, puis avec l'URL fixe.
  - **Attendu** : un des trois chemins aboutit, sinon le repli par copie.
  - **Critère** : le chemin qui a marché est noté dans le champ du test `P3`.
  - **Moyen** : à la main.
- **Exécutable autorisé**
  - **Geste** : lancer `& $llama --version`.
  - **Attendu** : pas de blocage AppLocker ou SmartScreen, pas de « VCRUNTIME140.dll introuvable ».
  - **Critère** : la version s'affiche. Sinon, le message exact est relevé et C9 et C10 passent à « non fait (poste) ».
  - **Moyen** : à la main.
- **Lancement avec -c 4096**
  - **Geste** : lancer la commande de C10, WaveStack arrêté et le 2B non chargé ailleurs, puis lancer WaveStack.
  - **Attendu** : « Local · llama-server » au diagnostic, sans avertissement de contexte.
  - **Critère** : RSS de `llama-server` (commande `PEAK_CMD`) bien sous 5 137 Mo.
  - **Moyen** : script AppSession ou à la main.
- **Clarté des gestes réécrits**
  - **Geste** : Anaël exécute D1, D2m, X1, X3, Z1, Z2, M3, M6, ainsi que D11 et « Réinitialiser » (M1), en suivant seulement le cahier.
  - **Attendu** : aucun « Que dois-je tester ici ? ».
  - **Critère** : chaque test reçoit un statut OK ou KO, pas « non fait » pour cause de consigne.
  - **Moyen** : à la main (œil humain).
- **Vider les clés (Z2)**
  - **Geste** : suivre Z2 dans un nouveau terminal, puis lancer `uv run wavestack` et ouvrir le diagnostic.
  - **Attendu** : aucune ligne « Clé fournie par la variable… » ni clé enregistrée ; le diagnostic demande de choisir un modèle servi.
  - **Critère** : les lignes Groq et Mistral du diagnostic indiquent qu'aucune clé n'est fournie (libellé exact relevé). Après « Défaire », les clés reviennent.
  - **Moyen** : à la main.
- **Mémoire pleine (D11)**
  - **Geste** : lancer le script D11, relancer WaveStack, allumer « Mémoire globale » à la main, puis lire la jauge.
  - **Attendu** : 20 entrées dans le tiroir ; la jauge compte environ 1 550 tokens de mémoire.
  - **Critère** : la jauge reste sous la fenêtre utilisable (sans débordement). `memory.json` est restauré ensuite.
  - **Moyen** : script AppSession pour la jauge, à la main pour l'affichage.
- **Cahier publié**
  - **Geste** : une fois l'artefact republié par Anaël, saisir un statut sous Edge, puis rouvrir la page sous Chrome.
  - **Attendu** : « Enregistré sur claude.ai » ; le statut est retrouvé.
  - **Critère** : même statut dans les deux navigateurs.
  - **Moyen** : à la main.

## Auto Run Result
Statut : done (2026-09-29, orchestrateur de nuit ; étapes 1 à 4 menées par l'orchestrateur ; une limite d'usage a interrompu l'implémentation, reprise ensuite sans perte).

**Changement :** guide `guide-test-pc-palier-2.md`, cahier `cahier-recette-palier-2.html` et README corrigés. Installation de llama-server sans droits d'administrateur (bloc PowerShell identique aux trois endroits : proxy d'entreprise, contrôle SHA-256 quand l'API fournit l'empreinte, repli sur b11239, `Unblock-File` expliqué, arrêt « non fait (poste) » si la politique bloque). Tests peu clairs réécrits (geste, attendu, critère) ; Z2, D11, Z3 et D1 sans risque de perte de données (rien déplacé ni supprimé, sauvegardes gardées, relance refusée) ; budget mémoire dynamique relevé en P2 et repris en C4, C5, X4 ; nouveau test P3 ; clé `recette-palier-2-v2`, collection `results-v2`. Renvoi vers le cahier de la nuit et `prompt-test-pc-2026-09-29.md` pour les stories 22 à 34 (le cahier détaillé de la nuit est généré sur le PC cible).

**Fichiers :** README.md (section llama-server, ligne proxy), `_bmad-output/implementation-artifacts/{guide-test-pc-palier-2.md,cahier-recette-palier-2.html}`.

**Revue :** 26 constats — 18 corrigés (3 high, 6 medium, 7 low, 2 maybe-false), 2 différés, 6 regroupés ; voir le triage. Revue de suivi recommandée : false (les trois high portent sur des procédures documentaires, corrigées et relues).

**Vérification :** ruff check et format verts ; pytest : 1294 passés, 3 ignorés (aucun code touché) ; rendu Playwright du cahier : 0 erreur de page, 30 tests pour 30 entrées, statuts et champs restaurés après rechargement, aucun défilement horizontal à 390 px ; blocs llama-server identiques caractère pour caractère dans les trois fichiers. E2E non concerné (documentation).

**Risques résiduels :** aucune commande PowerShell exécutée (pas de pwsh dans le conteneur) : première passe sur le PC cible.
