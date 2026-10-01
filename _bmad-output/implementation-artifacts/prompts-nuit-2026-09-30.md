# Prompts de la nuit du 2026-09-30

Trois phases, un seul prompt maître à coller dans **une** session Claude Code ouverte dans
`agentic-harness-training-demo-main`. Les prompts de phase servent à relancer une phase seule.

## Avant de dormir (10 minutes, à faire soi-même)

1. Dans l'autre working tree (`agentic-harness-training-demo`), committer l'état de la story
   Langues (5/5) tel quel (les traductions restantes sont faites en fin de nuit), arrêter son
   serveur (port 8421) et fermer sa session Claude Code. Si vous savez lesquelles restent,
   listez-les en deux minutes dans
   `_bmad-output/implementation-artifacts/traductions-restantes-2026-09-30.md` (fichier,
   clé ou écran, langue) ; sinon la nuit les relève mécaniquement.
2. Outlook et Teams fermés (fait). **Chrome fermé** ; **Edge ouvert** sur un seul onglet vide,
   connecté à Claude, extension Claude in Chrome active, **autorisation du site `127.0.0.1`
   déjà accordée** dans l'extension (sinon une demande bloquerait la nuit). Avec Chrome fermé,
   Edge est le seul navigateur connecté et les outils le prennent sans question.
3. Anti-veille, dans une fenêtre PowerShell à part, laissée ouverte toute la nuit (sans droits
   d'administrateur, c'est la méthode des utilitaires « caffeine ») :

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\keep_awake.ps1
   ```

   La fenêtre affiche une ligne par minute. La nuit vérifie qu'il tourne et le relance sinon.
   Écran éteint autorisé par le bouton, pas par le délai : le script tient aussi l'écran.
4. Vérifier que `%LOCALAPPDATA%\wavestack\api_keys.json` contient la clé Gemini (elle y est).
5. Lancer Claude Code depuis `agentic-harness-training-demo-main`, en **mode auto** (pas de
   demande d'autorisation), avec la variable qui empêche l'arrêt des processus d'arrière-plan
   quand la mémoire baisse, puisque WaveStack doit rester lancé pendant la recette :

   ```powershell
   $env:CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP = "1"
   claude --model claude-fable-5-1
   ```

   (En invite `cmd` : `set CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1` puis `claude`.)
   Effort : **high**. Modèle : Fable 5.1, pour un long run non supervisé à plusieurs lots ; c'est
   le seul cas où la gamme le recommande. `/clear` : oui, session neuve.
6. Coller le prompt maître. Ne pas lancer d'autre session Claude Code sur ce dépôt.

## Prompt maître (à coller)

```
Nuit autonome du 2026-09-30. Vérifie d'abord que tools/keep_awake.ps1 tourne (fichier %TEMP%\wavestack-keep-awake.pid, PID vivant), sinon lance-le en arrière-plan, et revérifie-le au début de chaque phase. Lis ensuite _bmad-output/implementation-artifacts/etat-nuit-2026-09-30.md s'il existe et reprends où il s'arrête ; sinon crée-le. Puis suis _bmad-output/implementation-artifacts/plan-nuit-2026-09-30.md phase par phase, sans t'arrêter pour me demander quoi que ce soit : je dors, toute question a pour réponse « décide, note la décision au rapport, continue ». La story 7 (traductions restantes de Langues 5 et des lots de la nuit) vient en dernier de la phase 2, après tout ajout fonctionnel. La recette de la phase 3 passe par l'extension Claude in Chrome dans Edge, seul navigateur ouvert : ne jamais appeler switch_browser. Autorisations données pour cette nuit : fusionner la PR « Langues 2 à 5 » dans main (phase 1), fermer la PR #10, supprimer les branches feat/i18n-2, feat/i18n-3, feat/i18n-4 et spec/langues après cette fusion, tuer un processus WaveStack périmé sur le port 8420, committer et pousser sur feat/i18n-5 puis feat/nuit-2026-09-30, ouvrir la PR de la nuit sans la fusionner, lire la clé Gemini dans api_keys.json pour la poser dans GEMINI_API_KEY du processus (jamais l'afficher, jamais l'écrire ailleurs), dépenser 1 € au plus sur Google AI Studio. Interdits : fusionner la PR de la nuit, pip, une dépendance nouvelle sans nécessité démontrée, deux suites de tests en même temps, un modèle local chargé pendant pytest, toucher au working tree agentic-harness-training-demo autrement que pour la phase 1. Mets à jour etat-nuit-2026-09-30.md après chaque étape, sur la branche courante, commité avec l'étape. Termine par rapport-nuit-2026-09-30.md, commité et poussé, avec le bloc « Étape suivante ».
```

## Prompts de phase (relance d'une phase seule)

### Phase 1 seule : fusion des langues

```
Phase 1 de _bmad-output/implementation-artifacts/plan-nuit-2026-09-30.md, et elle seule : fusionner feat/i18n-5 (Langues 2 à 5, working tree agentic-harness-training-demo) dans main, après y avoir fusionné main (Gemma) et vérifié ruff, pytest en deux moitiés et l'E2E par tranches. Autorisations : commit du reste de la story 5 s'il y en a, gh pr merge de la PR Langues, fermeture de la PR #10, suppression de feat/i18n-2, feat/i18n-3, feat/i18n-4 et spec/langues après la fusion, arrêt d'un processus périmé sur le port 8420. Ne me pose aucune question ; note tes décisions dans etat-nuit-2026-09-30.md.
```

### Phase 2 seule : les lots

```
Phase 2 de _bmad-output/implementation-artifacts/plan-nuit-2026-09-30.md, et elle seule, sur feat/nuit-2026-09-30 depuis main à jour : /bmad-spec pour découper plan-corrections-2026-09-30.md en stories dans _bmad-output/specs/spec-corrections-2026-09-30/ (ordre du plan de nuit), puis une story à la fois par /bmad-build-auto en mode dossier + id, avec ruff, pytest en deux moitiés, tranches E2E, commit et push après chacune. Règles Langues (ui.yaml, t(), *_text, trois langues) et UX (DESIGN.md et EXPERIENCE.md mis à jour dans la story) du plan. La story 7, traductions restantes (Langues 5 et textes des lots de la nuit), vient en dernier. Une story bloquée passe en blocked et n'arrête rien. Finis par la PR feat/nuit-2026-09-30 vers main, sans la fusionner. Ne me pose aucune question ; etat-nuit-2026-09-30.md à jour après chaque story.
```

### Phase 3 seule : validation, y compris Claude in Chrome

```
Phase 3 de _bmad-output/implementation-artifacts/plan-nuit-2026-09-30.md, et elle seule, sur feat/nuit-2026-09-30 : batterie automatique complète (ruff, pytest en deux moitiés, tests model si les variables sont posées, E2E complet par tranches), puis WaveStack réel sur 8420 et recette par l'extension Claude in Chrome dans Edge, seul navigateur ouvert (skill claude-in-chrome d'abord, jamais switch_browser) : toutes les pages en fr, en, de, deux thèmes, trois largeurs, chaque lot de la nuit, deux scénarios avec le SLM local, Gemini et Gemma avec la clé lue dans api_keys.json posée dans GEMINI_API_KEY (jamais affichée), 1 € au plus. Consigne tout dans resultats-nuit-2026-09-30.md au fil de l'eau, captures dans tools/e2e/screenshots/nuit-2026-09-30/, corrige et commite les KO petits et locaux, décris les autres. Vérifie l'absence de fuite de clé. Livre cahier-recette-nuit-2026-09-30.html (artefact avec enregistrement des résultats) pour ce que la machine n'a pas pu vérifier, puis rapport-nuit-2026-09-30.md avec le bloc « Étape suivante », commités et poussés, description de la PR mise à jour. Ne me pose aucune question.
```

## Le matin

1. Lire `rapport-nuit-2026-09-30.md`, puis `resultats-nuit-2026-09-30.md`.
2. `/bmad-walkthrough` sur la PR de la nuit (Opus 5.5, effort high, `/clear` avant) :
   « Walk me through la PR feat/nuit-2026-09-30, lot par lot, à partir du rapport de nuit. »
3. Jouer le cahier de recette HTML sur le PC pour ce que la machine n'a pas vu.
4. Décider la fusion de la PR.
