---
id: SPEC-wavestack-v1-1-vague-2-story-12
status: review
companions:
  - SPEC.md
  - ux/EXPERIENCE.md
  - limites-harnais.md
  - mcp-tools.md
  - guardrails.md
  - stories/1-politique-dautorisation-par-outil-mcp-et-journal-de-securite.md
  - stories/3-serveur-mcp-github-par-oauth-device-flow.md
  - stories/4-garde-fous-entree-sortie.md
  - stories/6-finops-cache-compression.md
  - stories/7-finops-subagent-kv-cache.md
  - stories/9-barre-commune-depense-journal.md
  - stories/13-installer-prompt-guard.md
---

# Story 12 (partie docs) : documenter la vague 2

## Ce qui est livré

Documentation seulement, pour un lecteur non développeur (vouvoiement, phrases courtes) ;
aucun code touché. Le comportement décrit vient des sections « Revue »/« Décisions » des
stories 1, 3, 4, 6, 7, 9 et 13 (déjà en revue ou fusionnées), pas seulement de leur intention, et
de `ux/EXPERIENCE.md` pour la page Sécurité (story 10), en relecture et non fusionnée au moment
de ce lot : décrite ici d'après sa spec (CAP-9), sans dépendre de son code.

- **`docs/securite.md`** (nouveau) : page Sécurité et bouton Journal, autorisations des outils
  MCP (risque/règle, les trois décisions), connexion GitHub (device flow, expiration à 8 h, les
  trois niveaux de refus), garde-fous (modes, portée limitée à la conversation principale,
  installation, Prompt Guard et sa licence), un résumé des limites de `limites-harnais.md`, et
  la FinOps vague 2 (cache de prompt, compression, sous-agent, mémoire de contexte locale,
  bilan de séance).
- **`docs/guide.md`** : ajout de l'onglet « Sécurité » (`/security`) et de la brique
  « garde-fous » dans le tableau et la liste des briques ; les boutons **Dépense** et
  **Journal**, désormais dans la barre de navigation (et non plus la barre du bas), remplacent
  l'ancienne « Dépense estimée » dans les paragraphes FinOps et GreenOps — liens vers
  `securite.md` pour le détail.
- **`docs/installation.md`** : ajout de `api.githubcopilot.com` (serveur MCP distant de GitHub)
  à la liste des hôtes à autoriser derrière un proxy d'entreprise ; les autres hôtes demandés
  (`github.com`, `huggingface.co`, `*.hf.co`, releases GitHub pour spaCy) y étaient déjà, ajoutés
  par les stories 3 et 13.
- **`README.md`** : une ligne « Sécurité » dans le tableau « Aller plus loin », vers
  `docs/securite.md` ; toujours 100 lignes au plus (une ligne gagnée en resserrant la légende du
  GIF, sans changer son contenu), aucune ancre avec « -- ».

## Décisions

- Pas de traduction : aucun `docs/en` ni `docs/de` n'existe dans ce dépôt (seul `content/i18n/`
  traduit l'interface de l'application). Rien à signaler de ce côté.
- FinOps vague 2 (cache, compression, sous-agent, mémoire locale) documentée dans
  `securite.md` plutôt que dans une nouvelle section longue de `guide.md` : c'est la même
  famille de sujets que la page Sécurité (ce qui se voit en coût et en contrôle), et
  `guide.md` y renvoie depuis ses paragraphes FinOps/GreenOps existants plutôt que de dupliquer.
- Garde-fou injection (jeton Hugging Face, licence Llama 4 Community) : la marche à suivre
  détaillée reste dans `installation.md` (déjà écrite par la story 13) ; `securite.md` la résume
  et y renvoie, sans la dupliquer.

## Hors périmètre (reste à faire)

- **Le GIF du README** (`tools/demo/drive.py` puis `compose.py`) n'a pas été refait : il lance
  l'application et un navigateur, sur le même port (8420) et la même RAM que l'orchestrateur
  utilise pour fusionner et vérifier les autres stories de la vague 2. L'orchestrateur le
  referra lui-même après la fusion de la story 10 (page Sécurité), pour que le GIF montre un
  état complet. Si la vague 2 doit apparaître dans le scénario de capture, il faudra ajouter un
  passage par la page Sécurité (et éventuellement un refus MCP ou GitHub) au scénario de
  `tools/demo/drive.py` avant de le rejouer — à faire par qui refait le GIF.
- Le reste de la vague 1 à documenter : « Ajouter d'autres modèles… » et ⛶ sur la Séquence
  étaient déjà décrits (`docs/installation.md`, `docs/guide.md`) ; les icônes 🏠/☁️ du sélecteur
  de modèle manquaient, ajoutées dans `docs/modeles.md` (« Lire le sélecteur »).
- La page Sécurité elle-même (story 10) n'est pas encore fusionnée : `docs/securite.md` décrit
  son contrat (`ux/EXPERIENCE.md`, CAP-9) ; à relire une fois la story 10 fusionnée, au cas où
  son code s'écarterait de la spec.

## Tests

- `uv run pytest -q --tb=short tests/test_docs_links.py` : 8 passés (liens et ancres, dont la
  nouvelle page, aucune ancre avec « -- »).
- `uv run pytest -q --tb=short tests/test_recette_docs.py tests/test_content_language.py` :
  59 passés (pas de régression sur les docs ou les textes existants).
- `uv run pytest -q --tb=short tests/test_installers.py` : 8 passés (le README lu par
  l'installeur n'a pas changé d'URL ni de structure).
- `python .claude/cost-kit/controle_rapide.py` : propre.
- Aucun E2E (consigne de l'orchestrateur : documentation seulement).

## Review Triage Log

(pas encore de relecture)
