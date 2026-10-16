---
title: 'WaveStack V1.1 vague 2 (13/10) : installation des garde-fous depuis la brique et Prompt Guard 2 optionnel'
type: 'feature'
created: '2026-10-16'
status: 'done'
baseline_commit: '80e5567'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/guardrails.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/ux/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/stories/4-garde-fous-entree-sortie.md'
  - '{project-root}/_bmad-output/specs/spec-wavestack-v1-1-vague-2/stories/5-garde-fous-branches-dans-le-tour.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CAP-5. Story 5 a branché les garde-fous dans le tour mais a laissé deux trous
exprès pour cette story : `injection` reste toujours `not_installed` (aucun modèle), et la
brique n'a pas de vrai bouton « Installer » quand son extra pip manque — seulement une
commande à copier dans un terminal.

**Approach:**
- `PromptGuardGuardrail` (nouveau, `guardrails/injection.py`) : l'export ONNX quantifié de
  `gravitee-io/Llama-Prompt-Guard-2-22M-onnx` (dérivé de `meta-llama/Llama-Prompt-Guard-2-22M`),
  chargé par `onnxruntime` — aucune dépendance de plus que l'extra `guardrails` existant
  (onnxruntime, tokenizers), aucun torch. `ensure_loaded()` lève `NotInstalled`
  (`contract.py`, nouveau) sans jeton Hugging Face (`config.hf_token()`), sinon télécharge
  (si besoin) avec `Authorization: Bearer …` puis construit la session ONNX.
- `GuardrailsManager` : `injection` a maintenant une factory (comme toxicité et données
  personnelles) ; `check()` ne traite plus `injection` à part, `_check_one` capte
  `NotInstalled` en `not_installed` jamais mis en cache (vérifier un fichier de jeton est bon
  marché, contrairement à un téléchargement). `install_injection(on_progress)` (nouveau) :
  chargement explicite et avide pour le bouton « Installer », réutilisé par `check()`
  ensuite. `injection_ready()`/`load_error()` (nouveaux) donnent à la brique de quoi choisir
  son état sans fouiller l'instance privée.
- `AppSession.install_guardrails_extra()` (nouveau, classe b) : `uv sync --extra guardrails
  --inexact` (le `--inexact` évite de désinstaller un autre extra déjà présent) dans un fil
  dédié, état `download` partagé avec les téléchargements RAG (même ligne de progression,
  même « Arrêter »). Succès : `importlib.invalidate_caches()` puis la disponibilité relue ;
  si elle redevient installée, la brique s'active sans relancer WaveStack, sinon le message
  dit de relancer. Échec : `harness_error`, la brique reste « non installés ».
- `AppSession.install_prompt_guard(token)` (nouveau, classe b) : enregistre le jeton
  (`config.write_hf_token`, hors dépôt) puis appelle `install_injection` dans le même état
  `download`, avec une ligne de progression dédiée (`guardrails.injection.model_noun`).
  Échec : `harness_error` avec la marche à suivre, le jeton reste enregistré (l'utilisateur
  peut corriger et réessayer).
- `_guardrails_card()` : `injection` affiche `needs_token` + marche à suivre tant qu'il n'a
  pas de modèle chargé, `loading` pendant `install_prompt_guard`, `error` sur un échec gardé
  en cache, puis le même commutateur que les deux autres une fois `injection_ready()`.
  `BrickState.installable` (nouveau) porte le bouton « Installer » de l'extra.
- UI (`app.js`/`app.css`) : `installExtraParts()` (le bouton de l'extra, ou la ligne de
  progression partagée) et `tokenForm()` (le champ du jeton + « Installer » de `injection`),
  tous deux appelant `ragAction` (déjà générique) sur les deux nouvelles routes.

**Decisions (prises par Claude, sans effet sur le contrat) :**
- ONNX, jamais torch (CAP-5, contrainte RAM) : `gravitee-io`'s export quantifié (~70 Mo),
  même éditeur et même motif que le modèle de toxicité de la story 4.
- 22M seulement, pas 86M : le quantifié 22M tient largement dans le budget 1,5 Go aux côtés
  de toxicité et données personnelles ; le gain d'exactitude du 86M (anglais surtout,
  guardrails.md) ne justifie pas de mesurer son empreinte sur ce poste pour une démo —
  reporté si une story future le demande.
- Le jeton reste exigé même si `gravitee-io/Llama-Prompt-Guard-2-22M-onnx` répond
  `gated: false` sur le Hub (vérifié le 16/10) : le poids reste un dérivé sous licence
  Llama 4 Community, et le point de la story est l'acceptation de la licence par
  l'utilisateur, pas la laxité actuelle d'un miroir. Le jeton part en en-tête
  `Authorization`, masqué par la liste blanche des en-têtes (AD-15) avant tout journal,
  trace ou log ; stocké dans `data_dir()/hf_token.json` (hors dépôt, effaçable à la main).
- L'extra pip et le modèle de Prompt Guard ont chacun leur propre « Installer » (deux
  routes) : l'extra est commun aux trois garde-fous (onnxruntime, Presidio, spaCy) et ne
  demande aucun secret ; le modèle demande un jeton et une licence acceptée par
  l'utilisateur. Les confondre aurait caché le jeton derrière un bouton générique.
- Après un `install_prompt_guard` réussi, le mode reste inchangé (`off` par défaut) : la
  brique arrête seulement de dire « non installé », l'utilisateur choisit Bloquer/Signaler
  comme pour les deux autres garde-fous (cohérence de l'interface, story 5). Ce n'est pas
  l'« actif » automatique que `ux/EXPERIENCE.md` (flux 2 de Karim) pourrait laisser croire.
- `install_guardrails_extra`/`install_prompt_guard` réutilisent l'état `download` déjà
  partagé par les téléchargements RAG (un seul job en arrière-plan à la fois, AD-3) plutôt
  qu'un nouvel état dédié : aucune nouvelle machine à états pour une seule story.
- Pas de bouton pour retirer le jeton : le supprimer (le fichier `hf_token.json`) suffit et
  est documenté (`docs/installation.md`) ; construire un bouton dédié est hors de proportion.

## Boundaries & Constraints

**Always:**
- Aucun modèle gated requis par défaut : `injection` reste `off`/`not_installed` sans jeton,
  les deux autres garde-fous et le reste du harnais fonctionnent sans lui.
- Le jeton Hugging Face n'apparaît jamais dans le journal, la trace, un log ni le dépôt.
- Aucun pytest ne télécharge un modèle ni n'installe un paquet réel : `subprocess.run` et le
  classifieur de `injection` sont toujours des fakes dans les tests.
- L'installation de l'extra et de Prompt Guard fonctionnent sans droits administrateur et
  derrière le proxy déjà documenté (`docs/installation.md`) : `uv sync` et `download_files`
  utilisent l'environnement et le client réseau existants, rien de nouveau à ouvrir.

**Never:**
- Pas de modification du périmètre de la story 5 (portée : conversation principale
  seulement) ni de `src/wavestack/mcp/` (lane A).
- Pas de téléchargement réel de Prompt Guard pendant le développement, sauf un seul essai
  manuel si un jeton Hugging Face est déjà présent sur ce poste (voir Verification) — sinon
  reporté, à faire avec Anaël.

## Code Map

- `src/wavestack/config.py` — `hf_token_path`/`hf_token`/`write_hf_token` (nouveaux, motif de
  `api_keys.json`).
- `src/wavestack/models/download.py` — `download_files`/`_download_one` : paramètre
  `headers` (nouveau), jamais journalisé en clair (liste blanche des en-têtes, AD-15).
- `src/wavestack/guardrails/contract.py` — `NotInstalled` (nouveau).
- `src/wavestack/guardrails/injection.py` (nouveau) — `PromptGuardGuardrail`.
- `src/wavestack/guardrails/manager.py` — factory `injection`, `_check_one` capte
  `NotInstalled`, `install_injection`/`injection_ready`/`load_error` (nouveaux),
  `withholds_output` n'exclut plus `injection`.
- `src/wavestack/session/app_session.py` — `install_guardrails_extra`,
  `install_prompt_guard` et leurs fils (`_run_install_extra`, `_run_prompt_guard_install`),
  `_guardrails_card` (états `injection`), `set_guardrail_mode` (injection autorisée une fois
  prête), `_injection_loading` (nouveau).
- `src/wavestack/trace/catalog.py` — `GuardrailCard.status` (+ `loading`/`error`),
  `GuardrailCard.needs_token`, `BrickState.installable`,
  `EffectAppliedPayload.effect` (+ `guardrails_extra_installed`).
- `src/wavestack/web/app.py` — `InstallPromptGuardIntention`, routes
  `install_guardrails_extra`/`install_prompt_guard`.
- `content/messages.yaml` (+ i18n en/de) — `guardrails.install_extra.*`,
  `guardrails.injection.*` (dont les exemples CAP-6), `web.unknown.guardrail_mode` mis à jour.
- `content/ui.yaml` (+ i18n en/de) — `main.bricks.status.{loading,error}`,
  `main.bricks.guardrails_install`, `main.bricks.guardrails_token_placeholder`.
- `src/wavestack/web/static/app.js`/`app.css` — `installExtraParts`, `tokenForm`,
  `.status-chip.is-flagged`, `.guardrail-token-form`.
- `docs/installation.md` — la ligne `guardrails` complétée (bouton, Prompt Guard, jeton).
- `tests/test_guardrails_injection.py` (nouveau) — le manager, fakes seulement.
- `tests/test_guardrails_install.py` (nouveau) — `AppSession`, subprocess et classifieur
  fakés.
- `tests/test_config_paths.py`, `tests/test_rag_download.py` — `hf_token`, en-têtes du
  téléchargement.

## Tasks & Acceptance

**Execution:**
- [x] `PromptGuardGuardrail` (ONNX, sans torch), `NotInstalled`.
- [x] `GuardrailsManager` : factory `injection`, `install_injection`, pas de cache pour
  `not_installed`.
- [x] `AppSession.install_guardrails_extra`/`install_prompt_guard`, cartes mises à jour.
- [x] Catalogue, routes HTTP, textes fr/en/de.
- [x] `app.js`/`app.css` : bouton de l'extra, champ du jeton.
- [ ] E2E (non lancés par le développeur, consigne de l'orchestrateur) : voir Verification.
- [ ] Essai réel (RAM de Prompt Guard) : reporté, à faire avec Anaël (voir Verification).

**Acceptance Criteria:**
- Given la brique Garde-fous sans son extra installé, when l'utilisateur clique
  « Installer », then `uv sync --extra guardrails --inexact` s'exécute, la progression
  s'affiche, et en cas de succès la brique devient utilisable sans relancer WaveStack (sauf
  message explicite demandant un relancement).
- Given un échec (réseau, proxy, disque), when l'installation de l'extra se termine, then un
  message clair apparaît et la brique reste « non installés ».
- Given `injection` sans jeton Hugging Face, then la brique affiche « non installé » avec la
  marche à suivre (compte, licence, jeton), et aucun commutateur n'agit sur lui.
- Given un jeton valide collé puis « Installer » cliqué, when le téléchargement réussit,
  then la brique affiche le même commutateur que toxicité et données personnelles,
  initialement désactivé.
- Given le même exemple neutre d'injection directe (guardrails.md), when `injection` est en
  mode Bloquer, then le modèle ne le reçoit jamais ; en Signaler, le verdict apparaît sans
  rien changer.
- Given aucun test de ce lot, then aucun ne télécharge un modèle ni n'installe un paquet.

## Implementation Notes

- Le jeton Hugging Face n'est jamais relu par ce qui trace ou journalise : l'en-tête
  `Authorization` suit le même masquage que toute autre clé (AD-15, `net/factory.py`),
  vérifié par un test qui lit les en-têtes vus par le faux serveur.
- `gravitee-io/Llama-Prompt-Guard-2-22M-onnx` (vérifié le 16/10 via l'API Hugging Face) :
  `gated: false`, `sha256` de `model.quant.onnx` relevé, `tokenizer.json` non LFS (taille
  seule, pas de sha256 déclaré sur le Hub, comme tout fichier sans sha256 ailleurs dans ce
  dépôt). `config.json` : `id2label` `{0: BENIGN, 1: MALICIOUS}`, `max_position_embeddings`
  512 — une seule fenêtre par message (pas de découpe en phrases comme la toxicité : un
  message d'injection dépasse rarement 512 tokens).
- Testé : `uv run pytest -q --tb=short tests/test_guardrails_injection.py
  tests/test_guardrails_install.py tests/test_guardrails.py tests/test_guardrails_turn.py`
  (35 passés, 1 skip) ; `tests/test_rag_download.py tests/test_config_paths.py` (16 passés,
  en-têtes et stockage du jeton) ; `tests/test_bricks.py tests/test_web_app.py` (93 passés,
  non-régression) ; `tests/test_i18n.py tests/test_ui_texts.py` (176 passés, textes et pages)
  — tous verts. `python .claude/cost-kit/controle_rapide.py` propre.
- Pas de suite complète ni d'E2E lancés (consigne de l'orchestrateur).

## Spec Change Log

## Review Triage Log

(pas encore de relecture)

## Verification

**Commands:**
- `uv run pytest -q --tb=short tests/test_guardrails_injection.py tests/test_guardrails_install.py tests/test_guardrails.py tests/test_guardrails_turn.py` — 35 passés, 1 skip.
- `uv run pytest -q --tb=short tests/test_rag_download.py tests/test_config_paths.py` — 16 passés.
- `uv run pytest -q --tb=short tests/test_bricks.py tests/test_web_app.py` — 93 passés (pas de régression).
- `uv run pytest -q --tb=short tests/test_i18n.py tests/test_ui_texts.py` — 176 passés (textes fr/en/de, pages).
- `python .claude/cost-kit/controle_rapide.py` — propre (lint et format).
- E2E (non lancés par le développeur, consigne de l'orchestrateur) : `s_hooks` et
  `s_native_tools` (E031, motif le plus proche des nouveaux états de carte) ; aucun scénario
  E2E dédié à la brique Garde-fous n'existe encore (même report que la story 5) — à créer
  dans une story qui construit la brique de bout en bout à l'écran, ou la page Sécurité
  (story 10).
- **Essai réel reporté, à faire avec Anaël** : aucun jeton Hugging Face n'était présent dans
  l'environnement de ce développement ; l'essai autorisé par l'orchestrateur (mesurer la RAM
  réelle de Prompt Guard 22M quantifié, un seul essai) n'a donc pas pu être fait. À faire sur
  le poste de référence : coller un vrai jeton, cliquer « Installer », lire la RAM avec le
  diagnostic, et confirmer que toxicité + données personnelles + injection tiennent
  ensemble sous 1,5 Go.

</frozen-after-approval>

## Décision licence (revue, orchestrateur, 16/10)

Le miroir `gravitee-io/Llama-Prompt-Guard-2-22M-onnx` n'étant pas gated, le jeton seul ne
prouvait pas l'acceptation de la licence Llama 4 Community. Désormais :
(a) la brique affiche, avant « Installer », un lien vers la page officielle
`meta-llama/Llama-Prompt-Guard-2-22M` (licence) et une case « J'ai accepté la licence Llama 4
Community sur Hugging Face » ; sans elle le bouton reste inactif et la route répond 409
(`licence_accepted`) ;
(b) avant tout téléchargement, `injection.check_licence` fait un `HEAD` avec le jeton sur
`config.json` du dépôt gated de Meta (aucun poids) : 401/403 → refus « acceptez d'abord la
licence sur la page Meta du modèle » avec le lien, rien n'est téléchargé ;
(c) la carte du garde-fou injection affiche « Built with Llama » une fois installé ;
(d) cette section. Tests avec faux hub (`httpx.MockTransport`) : accès accordé, refusé
(401, 403), réseau en échec ; aucun appel réseau réel.

## Revue

Revue Opus du 16/10 (rebase : déjà sur `origin/main` d46e514), liste du second avis reprise.

| Sévérité | Source | Constat | Issue |
|---|---|---|---|
| high | second avis 1 | Aucune acceptation explicite de la licence Llama 4 Community (miroir non gated) | Corrigé : case, lien, sonde du dépôt gated de Meta avant téléchargement, « Built with Llama » (voir Décision licence) |
| medium | second avis 2 | « Arrêter » sans effet sur `uv sync` | Corrigé : pas de jeton d'arrêt pour cette étape, `session_state.stoppable: false` (champ optionnel), bouton masqué, `stop()` renvoie `false` ; pas d'interruption à mi-chemin |
| medium | revue | « Arrêter » sans effet non plus sur le téléchargement de Prompt Guard (`ensure_loaded` créait son propre `CancelToken`) | Corrigé : le `StopToken` de la session est transmis ; arrêt = `model_download_stopped`, pas d'erreur ; bouton « Arrêter » ajouté dans la ligne `injection` pendant le chargement |
| medium | second avis 3 | Échec d'installation jamais mis dans `_load_errors` : état « erreur » inatteignable | Corrigé : `install_injection` l'enregistre (sauf arrêt), la carte montre la cause |
| medium | second avis 4 | Softmax sans soustraction du max, NaN → fail-open silencieux | Corrigé : `malicious_score` stable, logits non finis → exception → verdict `error` ; testé |
| medium | revue | Après « Éteindre » la brique (`unload_idle`) ou un redémarrage, la carte redemandait le jeton alors que fichiers et jeton sont présents | Corrigé : `PromptGuardGuardrail.is_installed()` (jeton + fichiers de bonne taille) lu par `injection_ready()` |
| medium | revue | `uv sync` réinstallerait le projet lui-même (lanceur `wavestack.exe` verrouillé par Windows pendant l'exécution) | Corrigé : `--no-install-project` ; `UV_PROJECT_ENVIRONMENT=sys.prefix` et `UV` (l'uv qui a lancé WaveStack) ; à confirmer à l'essai réel |
| medium | second avis 5 | Hôtes CDN de Hugging Face (`cas-bridge.xethub.hf.co`) | Rejeté pour le code : `*.hf.co` est un suffixe (`net/guard.py`), déjà couvert ; documenté pour le proxy dans `docs/installation.md` |
| low | second avis | Jeton écrit avant le refus 409 (pas `idle`) | Corrigé : job d'abord, jeton ensuite ; état rendu si l'écriture échoue ; testé |
| low | second avis | Analyse limitée aux 512 premiers tokens | Corrigé : `partial` = `enc.overflowing` (vérifié avec `tokenizers`), verdict « analysé en partie » ; ligne ajoutée dans `limites-harnais.md` |
| low | second avis | `str(Message(...))` en français dans `NotInstalled` | Rejeté : inatteignable en pratique (pas de commutateur sans jeton), même traitement que les erreurs de chargement existantes (`str(exc)`) |
| low | second avis | `cwd=config.repo_root()` avec `install.ps1` | Rejeté après lecture : projet installé en éditable, `repo_root()` = dossier d'installation ; l'environnement sous `%LOCALAPPDATA%` est désormais imposé par `UV_PROJECT_ENVIRONMENT=sys.prefix` |
| low | revue | `tests/test_bricks.py::test_outbound_line_without_network_tool_or_public_server` échoue | Hors story : échoue déjà sans ce lot (serveur MCP GitHub, story 3) ; à corriger à part |

**Reporté à l'essai réel avec Anaël** : avec un vrai jeton, vérifier (1) refus propre quand la
licence n'est pas acceptée sur la page Meta, puis téléchargement après acceptation ; (2) que
le `HEAD` sur le dépôt gated renvoie bien 200 (et non 302/403) pour un compte accepté ; (3) le
bouton « Installer » de l'extra sur le poste installé par `install.ps1` (`uv sync
--no-install-project` dans `%LOCALAPPDATA%\WaveStack`, activation sans relancer) ; (4) la RAM
de toxicité + données personnelles + injection sous 1,5 Go. E2E à rejouer : `s_hooks`,
`s_native_tools` (aucun scénario dédié à la brique Garde-fous).
